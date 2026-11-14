from datetime import datetime, timezone
from typing import List, Optional, Tuple

KNOWN_ZONE_CODES = {"Z-CENTER", "Z-NORTH", "Z-SOUTH", "Z-SUBURB", "Z-PORT"}

MIN_ACTUAL_MIN = 1.0
MAX_ACTUAL_MIN = 1440.0
MIN_PLANNED_MIN = 10.0
MAX_PLANNED_MIN = 720.0
MIN_DISTANCE_KM = 0.1
MAX_DISTANCE_KM = 500.0
MAX_SPEED_KMH = 150.0


def validate_reading(
    zone_code: str,
    actual_min: Optional[float],
    ts: datetime,
    planned_min: float = 60.0,
    distance_km: float = 10.0,
    now: Optional[datetime] = None,
    known_zones: Optional[set] = None,
) -> List[str]:
    """
    Чистая функция проверки события доставки перед расчётом SLA и записью в БД.
    Возвращает список текстов ошибок (пустой список, если данные корректны).
    """
    errors: List[str] = []
    allowed_zones = known_zones if known_zones is not None else KNOWN_ZONE_CODES

    norm_code = (zone_code or "").strip().upper()
    if not norm_code or norm_code not in allowed_zones:
        errors.append(f"неизвестная зона доставки: {zone_code}")

    if actual_min is None:
        errors.append("отсутствует фактическое время доставки")
        return errors

    if not (MIN_ACTUAL_MIN <= actual_min <= MAX_ACTUAL_MIN):
        errors.append(
            f"фактическое время {actual_min} вне диапазона [{MIN_ACTUAL_MIN}; {MAX_ACTUAL_MIN}] мин"
        )

    if not (MIN_PLANNED_MIN <= planned_min <= MAX_PLANNED_MIN):
        errors.append(
            f"плановый норматив SLA {planned_min} вне диапазона [{MIN_PLANNED_MIN}; {MAX_PLANNED_MIN}] мин"
        )

    if not (MIN_DISTANCE_KM <= distance_km <= MAX_DISTANCE_KM):
        errors.append(
            f"дистанция маршрута {distance_km} вне диапазона [{MIN_DISTANCE_KM}; {MAX_DISTANCE_KM}] км"
        )

    if actual_min >= MIN_ACTUAL_MIN and distance_km >= MIN_DISTANCE_KM:
        speed_kmh = distance_km / (actual_min / 60.0)
        if speed_kmh > MAX_SPEED_KMH:
            errors.append(
                f"аномальная средняя скорость {speed_kmh:.1f} км/ч превышает порог {MAX_SPEED_KMH} км/ч"
            )

    ref_now = now if now is not None else datetime.now(timezone.utc)
    ts_cmp = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    now_cmp = ref_now if ref_now.tzinfo is not None else ref_now.replace(tzinfo=timezone.utc)

    if ts_cmp > now_cmp:
        errors.append("метка времени доставки из будущего")

    return errors


def evaluate_sla(
    planned_min: float,
    actual_min: float,
    max_delay_min: float,
) -> Tuple[bool, float, Optional[str], Optional[str]]:
    """
    Чистая функция расчёта соблюдения SLA и классификации алерта.
    Возвращает кортеж: (sla_met, delay_min, severity, alert_message).
    """
    delay_min = round(max(0.0, actual_min - planned_min), 2)
    sla_met = actual_min <= planned_min

    if sla_met:
        return True, 0.0, None, None

    if delay_min >= max_delay_min:
        severity = "CRITICAL"
        msg = (
            f"Критическое нарушение SLA: опоздание {delay_min:.1f} мин "
            f"(порог {max_delay_min:.0f} мин, факт {actual_min:.1f} мин при плане {planned_min:.0f} мин)"
        )
    else:
        severity = "WARNING"
        msg = (
            f"Нарушение SLA: опоздание {delay_min:.1f} мин "
            f"(факт {actual_min:.1f} мин при плане {planned_min:.0f} мин)"
        )
    return False, delay_min, severity, msg
