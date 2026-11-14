import logging
from typing import Callable, Iterable, List, Tuple
from . import rules
from .domain import ShipmentReading, UnknownSensor
from .repository import ShipmentRepository

log = logging.getLogger(__name__)


def ingest(
    readings: Iterable[ShipmentReading],
    repo: ShipmentRepository,
    check: Callable[[ShipmentReading], List[str]] = rules.check,
) -> Tuple[int, List[Tuple[ShipmentReading, str]]]:
    """
    Сценарий приёма и контроля SLA событий доставки.
    Принимает хранилище и правило проверки аргументами (внедрение зависимостей).
    """
    accepted = 0
    rejected: List[Tuple[ShipmentReading, str]] = []

    for r in readings:
        errors = check(r)
        if errors:
            reason = "; ".join(errors)
            log.warning("заказ %s отклонён правилами: %s", r.order_no, reason)
            rejected.append((r, reason))
            continue
        try:
            repo.add(r)
            accepted += 1
        except UnknownSensor:
            log.warning("заказ %s отклонён: неизвестная зона %s", r.order_no, r.zone_code)
            rejected.append((r, "неизвестная зона доставки"))

    return accepted, rejected
