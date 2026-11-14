-- Методичка 4: Проверочные и отчётные SQL-запросы для темы №11
USE sla_delivery;
GO

-- Запрос 1. Агрегация соблюдения SLA по всем зонам доставки (с LEFT JOIN для зон без доставок)
SELECT
    z.code AS zone_code,
    z.name AS zone_name,
    z.sla_target_min,
    COUNT(e.id) AS total_deliveries,
    SUM(CASE WHEN e.sla_met = 1 THEN 1 ELSE 0 END) AS on_time_cnt,
    SUM(CASE WHEN e.sla_met = 0 THEN 1 ELSE 0 END) AS breached_cnt,
    ROUND(
        CASE WHEN COUNT(e.id) = 0 THEN 100.0
             ELSE 100.0 * SUM(CASE WHEN e.sla_met = 1 THEN 1.0 ELSE 0.0 END) / COUNT(e.id)
        END, 2
    ) AS sla_compliance_pct,
    ROUND(AVG(e.actual_min), 2) AS avg_actual_min,
    ROUND(MAX(e.delay_min), 2) AS max_delay_min
FROM dbo.delivery_zone z
LEFT JOIN dbo.shipment_event e ON e.zone_id = z.id
GROUP BY z.code, z.name, z.sla_target_min
ORDER BY z.code;
GO

-- Запрос 2. Соединение доставок и сработавших алертов SLA (детализация инцидентов)
SELECT
    a.id AS alert_id,
    a.severity,
    z.code AS zone_code,
    z.name AS zone_name,
    e.order_no,
    e.courier_code,
    e.planned_min,
    e.actual_min,
    e.delay_min,
    a.alert_message,
    a.created_at
FROM dbo.sla_alert a
INNER JOIN dbo.shipment_event e ON e.id = a.shipment_id
INNER JOIN dbo.delivery_zone z ON z.id = e.zone_id
ORDER BY a.created_at DESC, a.id DESC;
GO

-- Запрос 3. Фильтрация нарушений SLA и отклонённых событий за последние 24 часа
SELECT
    order_no,
    zone_code,
    raw_value,
    reason,
    rejected_at
FROM dbo.rejected_event
WHERE delivered_at >= DATEADD(HOUR, -24, SYSDATETIME())
ORDER BY id DESC;
GO

-- Команды резервного копирования и восстановления (Шаг 6 Методички 4)
-- BACKUP DATABASE sla_delivery TO DISK = N'/var/opt/mssql/data/sla_delivery.bak' WITH INIT;
-- ALTER DATABASE sla_delivery SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
-- RESTORE DATABASE sla_delivery FROM DISK = N'/var/opt/mssql/data/sla_delivery.bak' WITH REPLACE;
-- ALTER DATABASE sla_delivery SET MULTI_USER;
