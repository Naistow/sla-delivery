from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class UnknownSensor(Exception):
    """Исключение при обращении к неизвестной зоне/источнику доставки."""


class DirectoryError(Exception):
    """Ошибка при обращении к внешнему HTTP-справочнику зон 1С."""


@dataclass(frozen=True)
class ShipmentReading:
    order_no: str
    zone_code: str
    planned_min: float
    actual_min: float
    distance_km: float
    ts: datetime
    courier_code: str = "CR-01"


@dataclass(frozen=True)
class SlaAlertRecord:
    order_no: str
    zone_code: str
    severity: str
    message: str
    delay_min: float
    ts: datetime


@dataclass(frozen=True)
class ZoneSlaSummary:
    zone_code: str
    zone_name: str
    sla_target_min: int
    total_count: int
    on_time_count: int
    breached_count: int
    sla_percent: float
    avg_actual_min: Optional[float]
    max_delay_min: Optional[float]
    alerts_count: int
