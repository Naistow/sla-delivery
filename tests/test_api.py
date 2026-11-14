from fastapi.testclient import TestClient
from integration.api import create_app
from integration.repository import InMemoryRepository


def test_post_valid_shipment_and_get_summary():
    repo = InMemoryRepository(known_zones=("Z-CENTER",))
    client = TestClient(create_app(repo))

    r = client.post(
        "/shipments",
        json={
            "order_no": "ORD-101",
            "zone_code": "Z-CENTER",
            "planned_min": 45.0,
            "actual_min": 52.0,
            "distance_km": 9.5,
            "ts": "2026-01-01T10:00:00Z",
        },
    )
    assert r.status_code == 201
    assert r.json() == {"accepted": 1}

    cnt = client.get("/shipments/count")
    assert cnt.status_code == 200 and cnt.json() == {"count": 1}

    summary = client.get("/shipments/summary").json()
    assert len(summary) == 1
    assert summary[0]["breached_count"] == 1
    assert summary[0]["alerts_count"] == 1

    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "Дашборд контроля соблюдения SLA" in dash.text


def test_post_out_of_range_gives_422():
    client = TestClient(create_app(InMemoryRepository()))
    r = client.post(
        "/shipments",
        json={
            "order_no": "ORD-102",
            "zone_code": "Z-CENTER",
            "planned_min": 45.0,
            "actual_min": 9999.0,
            "distance_km": 10.0,
            "ts": "2026-01-01T10:00:00Z",
        },
    )
    assert r.status_code == 422
    assert "вне диапазона" in r.json()["detail"]


def test_post_malformed_body_gives_422():
    client = TestClient(create_app(InMemoryRepository()))
    r = client.post(
        "/shipments",
        json={"order_no": "ORD-103", "zone_code": "Z-CENTER", "actual_min": "abc"},
    )
    assert r.status_code == 422
