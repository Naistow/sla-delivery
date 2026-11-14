from datetime import datetime, timedelta, timezone
import pytest
from app.validate import evaluate_sla, validate_reading

NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)


def test_correct_reading_has_no_errors():
    errors = validate_reading("Z-CENTER", 40.0, NOW, planned_min=45.0, distance_km=10.0, now=NOW)
    assert errors == []


def test_value_out_of_range():
    errors = validate_reading("Z-CENTER", 9999.0, NOW, planned_min=45.0, distance_km=10.0, now=NOW)
    assert len(errors) == 1 and "вне диапазона" in errors[0]


def test_future_timestamp():
    future_ts = NOW + timedelta(minutes=5)
    errors = validate_reading("Z-CENTER", 35.0, future_ts, planned_min=45.0, distance_km=10.0, now=NOW)
    assert len(errors) == 1 and "будущего" in errors[0]


def test_unknown_zone_code():
    errors = validate_reading("Z-UNKNOWN", 35.0, NOW, planned_min=45.0, distance_km=10.0, now=NOW)
    assert len(errors) == 1 and "неизвестная зона" in errors[0]


def test_missing_value():
    errors = validate_reading("Z-CENTER", None, NOW, planned_min=45.0, distance_km=10.0, now=NOW)
    assert len(errors) == 1 and "отсутствует" in errors[0]


@pytest.mark.parametrize(
    "actual_min, ok",
    [
        (1.0, True),       # ровно нижняя граница фактического времени
        (1440.0, True),    # ровно верхняя граница (24 часа)
        (1440.1, False),   # чуть выше верхней границы
        (0.9, False),      # чуть ниже нижней границы
        (-5.0, False),     # отрицательное значение
    ],
)
def test_actual_duration_bounds(actual_min, ok):
    errors = validate_reading("Z-CENTER", actual_min, NOW, planned_min=60.0, distance_km=2.0, now=NOW)
    assert (errors == []) == ok


@pytest.mark.parametrize(
    "planned_min, ok",
    [
        (10.0, True),      # ровно нижняя граница норматива SLA
        (720.0, True),     # ровно верхняя граница норматива SLA
        (9.9, False),      # ниже минимального норматива
        (720.1, False),    # выше максимального норматива
    ],
)
def test_planned_sla_bounds(planned_min, ok):
    errors = validate_reading("Z-NORTH", 30.0, NOW, planned_min=planned_min, distance_km=5.0, now=NOW)
    assert (errors == []) == ok


@pytest.mark.parametrize(
    "distance_km, actual_min, ok",
    [
        (150.0, 60.0, True),   # ровно 150.0 км/ч — верхний порог допустимой скорости
        (150.1, 60.0, False),  # 150.1 км/ч — превышение порога скорости
        (0.1, 10.0, True),     # ровно минимальная дистанция 0.1 км
        (0.05, 10.0, False),   # меньше минимальной дистанции
        (500.0, 300.0, True),  # ровно максимальная дистанция 500 км (100 км/ч)
        (500.1, 300.0, False),   # превышение максимальной дистанции
    ],
)
def test_distance_and_speed_bounds(distance_km, actual_min, ok):
    errors = validate_reading("Z-SOUTH", actual_min, NOW, planned_min=90.0, distance_km=distance_km, now=NOW)
    assert (errors == []) == ok


@pytest.mark.parametrize(
    "planned_min, actual_min, max_delay_min, expected_met, expected_severity",
    [
        (45.0, 45.0, 15.0, True, None),          # ровно на пороге SLA — в срок
        (45.0, 45.1, 15.0, False, "WARNING"),    # опоздание 0.1 мин — WARNING
        (45.0, 59.9, 15.0, False, "WARNING"),    # опоздание 14.9 мин (чуть ниже порога CRITICAL)
        (45.0, 60.0, 15.0, False, "CRITICAL"),   # опоздание ровно 15.0 мин — CRITICAL
    ],
)
def test_evaluate_sla_alert_thresholds(planned_min, actual_min, max_delay_min, expected_met, expected_severity):
    sla_met, delay, severity, msg = evaluate_sla(planned_min, actual_min, max_delay_min)
    assert sla_met is expected_met
    assert severity == expected_severity
    if expected_met:
        assert delay == 0.0 and msg is None
    else:
        assert delay > 0.0 and msg is not None
