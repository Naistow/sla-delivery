import os
from datetime import datetime, timezone
import pytest
from integration.domain import ShipmentReading, UnknownSensor
from integration.repository import MssqlRepository, connect_mssql
from integration.settings import Settings

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="нужна живая база SQL Server: RUN_DB_TESTS=1",
)


@pytest.fixture
def repo():
    conn = connect_mssql(Settings.from_env())
    yield MssqlRepository(conn)
    conn.close()


def test_mssql_add_and_count(repo):
    before = repo.count()
    reading = ShipmentReading(
        order_no="ORD-DB-1",
        zone_code="Z-CENTER",
        planned_min=45.0,
        actual_min=38.0,
        distance_km=7.5,
        ts=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    repo.add(reading)
    assert repo.count() == before + 1


def test_mssql_unknown_zone_raises(repo):
    reading = ShipmentReading(
        order_no="ORD-DB-2",
        zone_code="NO-ZONE",
        planned_min=45.0,
        actual_min=38.0,
        distance_km=7.5,
        ts=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(UnknownSensor):
        repo.add(reading)
