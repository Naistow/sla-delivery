from datetime import datetime, timezone
from typing import List, Optional, Tuple
from .domain import ShipmentReading, SlaAlertRecord

MIN_ACTUAL_MIN = 1.0
MAX_ACTUAL_MIN = 1440.0
MIN_PLANNED_MIN = 10.0
MAX_PLANNED_MIN = 720.0
MIN_DISTANCE_KM = 0.1
MAX_DISTANCE_KM = 500.0
MAX_SPEED_KMH = 150.0


def check(reading: ShipmentReading, now: Optional[datetime] = None) -> List[str]:
    """
    Чистая функция проверки события доставки (ядро системы, не зависит от БД и сети).
    """
    errors: List[str] = []

    if not reading.order_no or not reading.order_no.strip():
        errors.append("пустой номер заказа")

    if not (MIN_ACTUAL_MIN <= reading.actual_min <= MAX_ACTUAL_MIN):
        errors.append(
            f"значение {reading.actual_min} вне диапазона [{MIN_ACTUAL_MIN}; {MAX_ACTUAL_MIN}]"
        )

    if not (MIN_PLANNED_MIN <= reading.planned_min <= MAX_PLANNED_MIN):
        errors.append(
            f"плановое время {reading.planned_min} вне диапазона [{MIN_PLANNED_MIN}; {MAX_PLANNED_MIN}]"
        )

    if not (MIN_DISTANCE_KM <= reading.distance_km <= MAX_DISTANCE_KM):
        errors.append(
            f"дистанция {reading.distance_km} вне диапазона [{MIN_DISTANCE_KM}; {MAX_DISTANCE_KM}]"
        )

    if reading.actual_min >= MIN_ACTUAL_MIN and reading.distance_km >= MIN_DISTANCE_KM:
        speed_kmh = reading.distance_km / (reading.actual_min / 60.0)
        if speed_kmh > MAX_SPEED_KMH:
            errors.append(
                f"скорость {speed_kmh:.1f} км/ч превышает максимум {MAX_SPEED_KMH} км/ч"
            )

    ref_now = now if now is not None else datetime.now(timezone.utc)
    ts_cmp = reading.ts if reading.ts.tzinfo is not None else reading.ts.replace(tzinfo=timezone.utc)
    now_cmp = ref_now if ref_now.tzinfo is not None else ref_now.replace(tzinfo=timezone.utc)

    if ts_cmp > now_cmp:
        errors.append("метка времени из будущего")

    return errors


def evaluate_alert(
    reading: ShipmentReading,
    max_delay_min: float = 20.0,
) -> Tuple[bool, float, Optional[SlaAlertRecord]]:
    """
    Расчёт соблюдения SLA и формирование алерта при превышении планового времени.
    """
    delay = round(max(0.0, reading.actual_min - reading.planned_min), 2)
    if reading.actual_min <= reading.planned_min:
        return True, 0.0, None

    severity = "CRITICAL" if delay >= max_delay_min else "WARNING"
    message = (
        f"Заказ {reading.order_no}: опоздание {delay:.1f} мин в зоне {reading.zone_code} "
        f"(факт {reading.actual_min:.1f} мин, норматив {reading.planned_min:.0f} мин)"
    )
    alert = SlaAlertRecord(
        order_no=reading.order_no,
        zone_code=reading.zone_code,
        severity=severity,
        message=message,
        delay_min=delay,
        ts=reading.ts,
    )
    return False, delay, alert
