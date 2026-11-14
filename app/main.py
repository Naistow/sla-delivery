import argparse
import csv
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

from . import db
from .validate import evaluate_sla, validate_reading

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

REPORT_SQL = """
SELECT
    z.code,
    z.name,
    z.sla_target_min,
    COUNT(e.id) AS total_cnt,
    SUM(CASE WHEN e.sla_met = 1 THEN 1 ELSE 0 END) AS on_time_cnt,
    SUM(CASE WHEN e.sla_met = 0 THEN 1 ELSE 0 END) AS breached_cnt,
    AVG(e.actual_min) AS avg_actual_min,
    MAX(e.delay_min) AS max_delay_min,
    (SELECT COUNT(*) FROM dbo.sla_alert a WHERE a.zone_code = z.code) AS alert_cnt
FROM dbo.delivery_zone z
LEFT JOIN dbo.shipment_event e ON e.zone_id = z.id
GROUP BY z.code, z.name, z.sla_target_min
ORDER BY z.code;
"""


def simulate(
    zones: List[Tuple[int, str, str, int, int]],
    count: int = 200,
    seed: int = 42,
) -> Iterator[Tuple[str, str, float, float, float, datetime]]:
    """
    Генератор событий доставки с контролируемым seed.
    Намеренно подмешивает как нарушения SLA (для срабатывания алертов),
    так и некорректные записи (выбросы времени 9999 мин, время из будущего, сверхскорость).
    """
    rng = random.Random(seed)
    base_now = datetime.now(timezone.utc)

    for idx in range(1, count + 1):
        _, code, _, sla_target, max_delay = rng.choice(zones)
        order_no = f"ORD-{10000 + idx}"
        planned_min = float(sla_target)
        distance_km = round(rng.uniform(2.5, 28.0), 2)
        ts = base_now - timedelta(minutes=rng.randint(1, 600))

        # Около 8% записей содержат ошибки валидации (для таблицы rejected_event)
        roll = rng.random()
        if roll < 0.03:
            actual_min = 9999.0  # Выброс за пределы диапазона [1; 1440]
        elif roll < 0.06:
            actual_min = round(rng.uniform(25.0, float(sla_target)), 1)
            ts = base_now + timedelta(hours=3)  # Метка времени из будущего
        elif roll < 0.08:
            actual_min = 2.0
            distance_km = 120.0  # Аномальная скорость > 150 км/ч
        elif roll < 0.28:
            # Нарушение SLA (опоздание от +3 до +max_delay*1.6 минут)
            actual_min = round(planned_min + rng.uniform(3.0, max_delay * 1.6), 1)
        else:
            # Штатная доставка в пределах SLA
            actual_min = round(rng.uniform(max(12.0, planned_min * 0.55), planned_min), 1)

        yield order_no, code, planned_min, actual_min, distance_km, ts


def cmd_init() -> None:
    db.run_init_script(Path("db/init.sql"))


def cmd_ingest(count: int, seed: int) -> None:
    conn = db.connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, code, name, sla_target_min, max_delay_min FROM dbo.delivery_zone ORDER BY code")
        zones = cur.fetchall()
        if not zones:
            raise RuntimeError("справочник зон пуст; сначала выполните init или import1c")

        by_code: Dict[str, Tuple[int, str, str, int, int]] = {row[1].strip().upper(): row for row in zones}
        known_codes = set(by_code.keys())
        now_utc = datetime.now(timezone.utc)

        ok_cnt = 0
        bad_cnt = 0
        alert_cnt = 0

        for idx, (order_no, code, planned_min, actual_min, distance_km, ts) in enumerate(
            simulate(zones, count=count, seed=seed), start=1
        ):
            errors = validate_reading(
                zone_code=code,
                actual_min=actual_min,
                ts=ts,
                planned_min=planned_min,
                distance_km=distance_km,
                now=now_utc,
                known_zones=known_codes,
            )
            ts_naive = ts.replace(tzinfo=None)
            if errors:
                cur.execute(
                    "INSERT INTO dbo.rejected_event (order_no, zone_code, raw_value, delivered_at, reason) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (order_no, code, f"actual={actual_min};dist={distance_km}", ts_naive, "; ".join(errors)),
                )
                bad_cnt += 1
                continue

            zone_id, _, _, _, max_delay_min = by_code[code]
            sla_met, delay_min, severity, alert_msg = evaluate_sla(planned_min, actual_min, float(max_delay_min))
            courier_code = f"CR-{(idx % 12) + 1:02d}"

            cur.execute(
                "INSERT INTO dbo.shipment_event "
                "(order_no, zone_id, courier_code, planned_min, actual_min, delay_min, distance_km, sla_met, delivered_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    order_no,
                    zone_id,
                    courier_code,
                    planned_min,
                    actual_min,
                    delay_min,
                    distance_km,
                    1 if sla_met else 0,
                    ts_naive,
                ),
            )
            cur.execute("SELECT SCOPE_IDENTITY()")
            shipment_id = int(cur.fetchone()[0])
            ok_cnt += 1

            if not sla_met and severity and alert_msg:
                cur.execute(
                    "INSERT INTO dbo.sla_alert (shipment_id, zone_code, severity, alert_message, created_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (shipment_id, code, severity, alert_msg, ts_naive),
                )
                alert_cnt += 1

        log.info("принято доставок: %d, отклонено: %d, создано алертов SLA: %d", ok_cnt, bad_cnt, alert_cnt)
    finally:
        conn.close()


def cmd_report() -> None:
    conn = db.connect()
    try:
        cur = conn.cursor()
        cur.execute(REPORT_SQL)
        rows = cur.fetchall()
        header = (
            f"{'код':<10} {'зона доставки':<34} {'план':>5} {'всего':>6} "
            f"{'в срок':>6} {'наруш':>6} {'SLA %':>7} {'средн':>7} {'макс.оп':>8} {'алерты':>6}"
        )
        log.info(header)
        for code, name, target, total, on_time, breached, avg_act, max_del, alerts in rows:
            on_time = on_time or 0
            breached = breached or 0
            sla_pct = (100.0 * on_time / total) if total else 100.0
            avg_str = f"{avg_act:.2f}" if avg_act is not None else "-"
            max_str = f"{max_del:.2f}" if max_del is not None else "-"
            log.info(
                "%-10s %-34s %5d %6d %6d %6d %6.1f%% %7s %8s %6d",
                code,
                name[:34],
                target,
                total,
                on_time,
                breached,
                sla_pct,
                avg_str,
                max_str,
                alerts or 0,
            )

        cur.execute("SELECT COUNT(*) FROM dbo.rejected_event")
        rejected_total = cur.fetchone()[0]
        log.info("отклонено событий доставки: %d", rejected_total)
    finally:
        conn.close()


def cmd_import1c(file_path: Path) -> None:
    conn = db.connect()
    try:
        cur = conn.cursor()
        added = 0
        updated = 0
        with file_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if not row or not row.get("Код"):
                    continue
                code = row["Код"].strip().upper()
                name = (row.get("Наименование") or "").strip()
                sla_target = int(row.get("НормативМин") or 60)
                max_delay = int(row.get("КритОпозданиеМин") or 20)

                cur.execute("SELECT id FROM dbo.delivery_zone WHERE code = %s", (code,))
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        "UPDATE dbo.delivery_zone SET name = %s, sla_target_min = %s, max_delay_min = %s "
                        "WHERE code = %s",
                        (name, sla_target, max_delay, code),
                    )
                    updated += 1
                else:
                    cur.execute(
                        "INSERT INTO dbo.delivery_zone (code, name, sla_target_min, max_delay_min) "
                        "VALUES (%s, %s, %s, %s)",
                        (code, name, sla_target, max_delay),
                    )
                    added += 1
        log.info("справочник зон 1С: добавлено %d, обновлено %d", added, updated)
    finally:
        conn.close()


def cmd_export1c(file_path: Path) -> None:
    conn = db.connect()
    try:
        cur = conn.cursor()
        cur.execute(REPORT_SQL)
        rows = cur.fetchall()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(
                [
                    "Код",
                    "Наименование",
                    "ВсегоДоставок",
                    "В_Срок",
                    "Нарушений_SLA",
                    "Процент_SLA",
                    "СреднееВремяМин",
                    "МаксОпозданиеМин",
                    "АктивныхАлертов",
                ]
            )
            for code, name, _, total, on_time, breached, avg_act, max_del, alerts in rows:
                on_time_val = on_time or 0
                breached_val = breached or 0
                sla_pct = f"{(100.0 * on_time_val / total):.2f}" if total else ""
                avg_str = f"{avg_act:.2f}" if avg_act is not None else ""
                max_str = f"{max_del:.2f}" if max_del is not None else ""
                writer.writerow(
                    [
                        code,
                        name,
                        total,
                        on_time_val,
                        breached_val,
                        sla_pct,
                        avg_str,
                        max_str,
                        alerts or 0,
                    ]
                )
        log.info("сводка SLA для 1С выгружена в %s (%d строк)", file_path, len(rows))
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Модуль контроля соблюдения SLA по доставке")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Применить идемпотентную схему БД db/init.sql")

    p_ingest = sub.add_parser("ingest", help="Сгенерировать и обработать поток доставок")
    p_ingest.add_argument("--count", type=int, default=200)
    p_ingest.add_argument("--seed", type=int, default=42)

    sub.add_parser("report", help="Вывести агрегированный отчёт SLA в консоль")

    p_imp = sub.add_parser("import1c", help="Загрузить справочник зон доставки из CSV 1С")
    p_imp.add_argument("--file", type=Path, default=Path("exchange/spravochnik_zon.csv"))

    p_exp = sub.add_parser("export1c", help="Выгрузить сводку SLA для 1С в CSV")
    p_exp.add_argument("--file", type=Path, default=Path("exchange/svodka_sla_dlya_1c.csv"))

    p_all = sub.add_parser("run-all", help="Полный сквозной сценарий: init -> import1c -> ingest -> report -> export1c")
    p_all.add_argument("--count", type=int, default=200)
    p_all.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()
    if args.cmd == "init":
        cmd_init()
    elif args.cmd == "ingest":
        cmd_ingest(args.count, args.seed)
    elif args.cmd == "report":
        cmd_report()
    elif args.cmd == "import1c":
        cmd_import1c(args.file)
    elif args.cmd == "export1c":
        cmd_export1c(args.file)
    elif args.cmd == "run-all":
        cmd_init()
        cmd_import1c(Path("exchange/spravochnik_zon.csv"))
        cmd_ingest(args.count, args.seed)
        cmd_report()
        cmd_export1c(Path("exchange/svodka_sla_dlya_1c.csv"))


if __name__ == "__main__":
    main()
