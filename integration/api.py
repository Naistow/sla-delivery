from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from . import service
from .domain import ShipmentReading
from .repository import ShipmentRepository


class ShipmentIn(BaseModel):
    order_no: str
    zone_code: str
    planned_min: float = 60.0
    actual_min: float
    distance_km: float = 10.0
    ts: datetime
    courier_code: str = "CR-01"


class ZoneSummaryOut(BaseModel):
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


def create_app(repo: ShipmentRepository) -> FastAPI:
    app = FastAPI(title="Модуль контроля соблюдения SLA по доставке")

    @app.post("/shipments", status_code=201)
    def add_shipment(body: ShipmentIn):
        reading = ShipmentReading(
            order_no=body.order_no,
            zone_code=body.zone_code,
            planned_min=body.planned_min,
            actual_min=body.actual_min,
            distance_km=body.distance_km,
            ts=body.ts,
            courier_code=body.courier_code,
        )
        accepted, rejected = service.ingest([reading], repo)
        if rejected:
            raise HTTPException(status_code=422, detail=rejected[0][1])
        return {"accepted": accepted}

    @app.get("/shipments/count")
    def get_count():
        return {"count": repo.count()}

    @app.get("/shipments/summary", response_model=List[ZoneSummaryOut])
    def get_summary():
        return [
            ZoneSummaryOut(**vars(item))
            for item in repo.summary_by_zone()
        ]

    @app.get("/alerts")
    def get_alerts():
        return [
            {
                "order_no": a.order_no,
                "zone_code": a.zone_code,
                "severity": a.severity,
                "message": a.message,
                "delay_min": a.delay_min,
                "ts": a.ts.isoformat(),
            }
            for a in repo.alerts()
        ]

    @app.get("/dashboard", response_class=HTMLResponse)
    def get_dashboard():
        summaries = repo.summary_by_zone()
        alerts = repo.alerts()
        total_deliv = sum(s.total_count for s in summaries)
        total_ontime = sum(s.on_time_count for s in summaries)
        overall_sla = round(100.0 * total_ontime / total_deliv, 1) if total_deliv else 100.0

        rows_html = "".join(
            f"<tr><td><b>{s.zone_code}</b></td><td>{s.zone_name}</td>"
            f"<td>{s.sla_target_min} мин</td><td>{s.total_count}</td>"
            f"<td>{s.on_time_count}</td><td>{s.breached_count}</td>"
            f"<td><b>{s.sla_percent:.1f}%</b></td>"
            f"<td>{s.avg_actual_min if s.avg_actual_min is not None else '-'}</td>"
            f"<td>{s.alerts_count}</td></tr>"
            for s in summaries
        )
        alerts_html = "".join(
            f"<li><b>[{a.severity}]</b> {a.message}</li>" for a in alerts[:15]
        ) or "<li>Активных нарушений SLA нет</li>"

        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Дашборд SLA доставки</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; background: #f8fafc; color: #0f172a; }}
    .kpi-grid {{ display: flex; gap: 16px; margin-bottom: 24px; }}
    .card {{ background: #fff; padding: 16px 20px; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; margin-bottom: 24px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; text-align: left; }}
    th {{ background: #1e293b; color: #fff; }}
  </style>
</head>
<body>
  <h1>Дашборд контроля соблюдения SLA по доставке</h1>
  <div class="kpi-grid">
    <div class="card"><div>Всего доставок</div><h2>{total_deliv}</h2></div>
    <div class="card"><div>Соблюдение SLA</div><h2>{overall_sla}%</h2></div>
    <div class="card"><div>Активных алертов</div><h2>{len(alerts)}</h2></div>
  </div>
  <h2>Метрики SLA по зонам доставки</h2>
  <table>
    <thead>
      <tr>
        <th>Код</th><th>Зона доставки</th><th>Норматив</th><th>Всего</th>
        <th>В срок</th><th>Нарушений</th><th>SLA %</th><th>Среднее (мин)</th><th>Алерты</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <h2>Лента алертов SLA</h2>
  <div class="card"><ul>{alerts_html}</ul></div>
</body>
</html>"""
        return HTMLResponse(content=html)

    return app
