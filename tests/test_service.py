from datetime import datetime, timezone
from integration.domain import ShipmentReading
from integration.repository import InMemoryRepository
from integration.service import ingest

NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)


def test_ingest_accepts_valid_and_rejects_invalid():
    repo = InMemoryRepository(known_zones=("Z-CENTER",))
    items = [
        ShipmentReading("ORD-1", "Z-CENTER", 45.0, 40.0, 8.0, NOW),
        ShipmentReading("ORD-2", "Z-CENTER", 45.0, 9999.0, 8.0, NOW),
        ShipmentReading("ORD-3", "NO-SUCH", 45.0, 35.0, 8.0, NOW),
    ]
    accepted, rejected = ingest(items, repo)
    assert accepted == 1
    assert repo.count() == 1
    assert len(rejected) == 2
    assert "вне диапазона" in rejected[0][1]
    assert "неизвестная зона" in rejected[1][1]


def test_ingest_generates_sla_alert_on_delay():
    repo = InMemoryRepository(known_zones=("Z-CENTER",))
    items = [
        ShipmentReading("ORD-10", "Z-CENTER", 45.0, 65.0, 12.0, NOW),
    ]
    accepted, rejected = ingest(items, repo)
    assert accepted == 1 and rejected == []
    alerts = repo.alerts()
    assert len(alerts) == 1
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].delay_min == 20.0


def test_custom_rule_can_be_injected():
    repo = InMemoryRepository(known_zones=("Z-CENTER",))
    reading = ShipmentReading("ORD-11", "Z-CENTER", 45.0, 30.0, 5.0, NOW)
    accepted, rejected = ingest([reading], repo, check=lambda r: ["запрещено тестовым правилом"])
    assert accepted == 0
    assert len(rejected) == 1
    assert rejected[0][1] == "запрещено тестовым правилом"
