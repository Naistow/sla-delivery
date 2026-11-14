from typing import Dict, List, Protocol, Tuple
from .domain import ShipmentReading, SlaAlertRecord, UnknownSensor, ZoneSlaSummary
from .rules import evaluate_alert
from .settings import Settings


class ShipmentRepository(Protocol):
    def add(self, reading: ShipmentReading) -> None: ...
    def count(self) -> int: ...
    def alerts(self) -> List[SlaAlertRecord]: ...
    def summary_by_zone(self) -> List[ZoneSlaSummary]: ...


class InMemoryRepository:
    """Реализация хранилища в памяти для быстрых модульных и API-тестов без SQL Server."""

    def __init__(self, known_zones: Tuple[str, ...] = ("Z-CENTER", "Z-NORTH", "Z-SOUTH", "Z-SUBURB")):
        self.zones: Dict[str, Tuple[str, int, int]] = {
            code: (f"Зона {code}", 60, 20) for code in known_zones
        }
        if "Z-CENTER" in self.zones:
            self.zones["Z-CENTER"] = ("Центральный район (экспресс)", 45, 15)
        self.items: List[ShipmentReading] = []
        self.alert_items: List[SlaAlertRecord] = []

    def add(self, reading: ShipmentReading) -> None:
        code = reading.zone_code.strip().upper()
        if code not in self.zones:
            raise UnknownSensor(reading.zone_code)
        _, _, max_delay = self.zones[code]
        self.items.append(reading)
        _, _, alert = evaluate_alert(reading, max_delay_min=float(max_delay))
        if alert is not None:
            self.alert_items.append(alert)

    def count(self) -> int:
        return len(self.items)

    def alerts(self) -> List[SlaAlertRecord]:
        return list(self.alert_items)

    def summary_by_zone(self) -> List[ZoneSlaSummary]:
        result: List[ZoneSlaSummary] = []
        for code in sorted(self.zones.keys()):
            name, target, _ = self.zones[code]
            zone_items = [r for r in self.items if r.zone_code.strip().upper() == code]
            total = len(zone_items)
            on_time = sum(1 for r in zone_items if r.actual_min <= r.planned_min)
            breached = total - on_time
            sla_pct = round(100.0 * on_time / total, 2) if total else 100.0
            avg_act = round(sum(r.actual_min for r in zone_items) / total, 2) if total else None
            delays = [max(0.0, r.actual_min - r.planned_min) for r in zone_items]
            max_del = round(max(delays), 2) if delays else None
            z_alerts = sum(1 for a in self.alert_items if a.zone_code == code)
            result.append(
                ZoneSlaSummary(
                    zone_code=code,
                    zone_name=name,
                    sla_target_min=target,
                    total_count=total,
                    on_time_count=on_time,
                    breached_count=breached,
                    sla_percent=sla_pct,
                    avg_actual_min=avg_act,
                    max_delay_min=max_del,
                    alerts_count=z_alerts,
                )
            )
        return result


class MssqlRepository:
    """Реализация хранилища для Microsoft SQL Server."""

    def __init__(self, conn):
        self.conn = conn

    def add(self, reading: ShipmentReading) -> None:
        cur = self.conn.cursor()
        code = reading.zone_code.strip().upper()
        cur.execute(
            "SELECT id, max_delay_min FROM dbo.delivery_zone WHERE code = %s",
            (code,),
        )
        row = cur.fetchone()
        if not row:
            raise UnknownSensor(reading.zone_code)

        zone_id, max_delay_min = int(row[0]), float(row[1])
        sla_met, delay_min, alert = evaluate_alert(reading, max_delay_min=max_delay_min)
        ts_naive = reading.ts.replace(tzinfo=None)

        cur.execute(
            "INSERT INTO dbo.shipment_event "
            "(order_no, zone_id, courier_code, planned_min, actual_min, delay_min, distance_km, sla_met, delivered_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                reading.order_no,
                zone_id,
                reading.courier_code,
                reading.planned_min,
                reading.actual_min,
                delay_min,
                reading.distance_km,
                1 if sla_met else 0,
                ts_naive,
            ),
        )
        if alert is not None:
            cur.execute("SELECT SCOPE_IDENTITY()")
            shipment_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO dbo.sla_alert (shipment_id, zone_code, severity, alert_message, created_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (shipment_id, code, alert.severity, alert.message, ts_naive),
            )

    def count(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.shipment_event")
        return int(cur.fetchone()[0])

    def alerts(self) -> List[SlaAlertRecord]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT TOP 50 e.order_no, a.zone_code, a.severity, a.alert_message, e.delay_min, a.created_at "
            "FROM dbo.sla_alert a "
            "INNER JOIN dbo.shipment_event e ON e.id = a.shipment_id "
            "ORDER BY a.id DESC"
        )
        return [
            SlaAlertRecord(
                order_no=r[0],
                zone_code=r[1],
                severity=r[2],
                message=r[3],
                delay_min=float(r[4]),
                ts=r[5],
            )
            for r in cur.fetchall()
        ]

    def summary_by_zone(self) -> List[ZoneSlaSummary]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT z.code, z.name, z.sla_target_min, COUNT(e.id), "
            "SUM(CASE WHEN e.sla_met = 1 THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN e.sla_met = 0 THEN 1 ELSE 0 END), "
            "AVG(e.actual_min), MAX(e.delay_min), "
            "(SELECT COUNT(*) FROM dbo.sla_alert a WHERE a.zone_code = z.code) "
            "FROM dbo.delivery_zone z "
            "LEFT JOIN dbo.shipment_event e ON e.zone_id = z.id "
            "GROUP BY z.code, z.name, z.sla_target_min "
            "ORDER BY z.code"
        )
        res: List[ZoneSlaSummary] = []
        for code, name, target, total, on_t, br, avg_a, max_d, al_cnt in cur.fetchall():
            on_t_val = int(on_t or 0)
            br_val = int(br or 0)
            sla_pct = round(100.0 * on_t_val / total, 2) if total else 100.0
            res.append(
                ZoneSlaSummary(
                    zone_code=code,
                    zone_name=name,
                    sla_target_min=int(target),
                    total_count=int(total),
                    on_time_count=on_t_val,
                    breached_count=br_val,
                    sla_percent=sla_pct,
                    avg_actual_min=round(float(avg_a), 2) if avg_a is not None else None,
                    max_delay_min=round(float(max_d), 2) if max_d is not None else None,
                    alerts_count=int(al_cnt or 0),
                )
            )
        return res


def connect_mssql(settings: Settings):
    import pymssql

    return pymssql.connect(
        server=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        autocommit=True,
        charset="UTF-8",
    )
