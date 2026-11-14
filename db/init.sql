IF DB_ID('sla_delivery') IS NULL
    CREATE DATABASE sla_delivery;
GO

USE sla_delivery;
GO

IF OBJECT_ID('dbo.delivery_zone') IS NULL
CREATE TABLE dbo.delivery_zone (
    id             INT IDENTITY PRIMARY KEY,
    code           NVARCHAR(32)  NOT NULL UNIQUE,
    name           NVARCHAR(128) NOT NULL,
    sla_target_min INT           NOT NULL,
    max_delay_min  INT           NOT NULL
);
GO

IF OBJECT_ID('dbo.shipment_event') IS NULL
CREATE TABLE dbo.shipment_event (
    id           BIGINT IDENTITY PRIMARY KEY,
    order_no     NVARCHAR(32) NOT NULL,
    zone_id      INT          NOT NULL REFERENCES dbo.delivery_zone(id),
    courier_code NVARCHAR(32) NOT NULL,
    planned_min  FLOAT        NOT NULL,
    actual_min   FLOAT        NOT NULL,
    delay_min    FLOAT        NOT NULL,
    distance_km  FLOAT        NOT NULL,
    sla_met      BIT          NOT NULL,
    delivered_at DATETIME2    NOT NULL
);
GO

IF OBJECT_ID('dbo.sla_alert') IS NULL
CREATE TABLE dbo.sla_alert (
    id            BIGINT IDENTITY PRIMARY KEY,
    shipment_id   BIGINT        NOT NULL REFERENCES dbo.shipment_event(id),
    zone_code     NVARCHAR(32)  NOT NULL,
    severity      NVARCHAR(16)  NOT NULL,
    alert_message NVARCHAR(256) NOT NULL,
    created_at    DATETIME2     NOT NULL
);
GO

IF OBJECT_ID('dbo.rejected_event') IS NULL
CREATE TABLE dbo.rejected_event (
    id           BIGINT IDENTITY PRIMARY KEY,
    order_no     NVARCHAR(32)  NOT NULL,
    zone_code    NVARCHAR(32)  NOT NULL,
    raw_value    NVARCHAR(128) NOT NULL,
    delivered_at DATETIME2     NOT NULL,
    reason       NVARCHAR(256) NOT NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.delivery_zone)
INSERT INTO dbo.delivery_zone (code, name, sla_target_min, max_delay_min) VALUES
    (N'Z-CENTER', N'Центральный район (экспресс)', 45, 15),
    (N'Z-NORTH',  N'Северный жилой массив',        60, 20),
    (N'Z-SOUTH',  N'Южная промзона',               90, 30),
    (N'Z-SUBURB', N'Пригородное направление',     120, 40);
GO
