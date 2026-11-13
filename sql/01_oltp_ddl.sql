/* =====================================================================
   01 - Base transaccional (OLTP) RiegoInteligente  ·  SQL Server 2017+
   Modelo relacional en 3FN (mismo diagrama del informe)
   Propietario 1─N Finca 1─N Lote N─1 Cultivo
   Lote 1─N Dispositivo 1─N Lectura / 1─N EventoRiego
   ===================================================================== */
IF DB_ID('RiegoInteligente') IS NULL CREATE DATABASE RiegoInteligente;
GO
USE RiegoInteligente;
GO
DROP TABLE IF EXISTS dbo.EventoRiego, dbo.Lectura, dbo.Dispositivo, dbo.Lote, dbo.Cultivo, dbo.Finca, dbo.Propietario;
GO
CREATE TABLE dbo.Propietario (
    id_propietario INT          NOT NULL PRIMARY KEY,
    nombre         NVARCHAR(80) NOT NULL,
    documento      VARCHAR(20)  NOT NULL UNIQUE,
    telefono       VARCHAR(20)  NULL,
    email          VARCHAR(100) NULL
);
CREATE TABLE dbo.Finca (
    id_finca       INT          NOT NULL PRIMARY KEY,
    id_propietario INT          NOT NULL REFERENCES dbo.Propietario(id_propietario),
    nombre         NVARCHAR(80) NOT NULL,
    departamento   NVARCHAR(50) NOT NULL,
    municipio      NVARCHAR(50) NOT NULL,
    vereda         NVARCHAR(80) NULL,
    latitud        DECIMAL(9,6) NULL,
    longitud       DECIMAL(9,6) NULL,
    altitud_msnm   INT          NULL
);
CREATE TABLE dbo.Cultivo (
    id_cultivo   INT          NOT NULL PRIMARY KEY,
    nombre       NVARCHAR(60) NOT NULL,
    humedad_min  DECIMAL(5,2) NOT NULL,   -- umbral de inicio de riego (HUM_INICIO)
    humedad_max  DECIMAL(5,2) NOT NULL,   -- humedad objetivo (HUM_FIN)
    CONSTRAINT CK_Cultivo_Umbrales CHECK (humedad_min < humedad_max)
);
CREATE TABLE dbo.Lote (
    id_lote       INT          NOT NULL PRIMARY KEY,
    id_finca      INT          NOT NULL REFERENCES dbo.Finca(id_finca),
    id_cultivo    INT          NOT NULL REFERENCES dbo.Cultivo(id_cultivo),
    nombre        NVARCHAR(60) NOT NULL,
    area_ha       DECIMAL(6,2) NULL,
    tipo_suelo    NVARCHAR(40) NULL,
    fecha_siembra DATE         NULL
);
CREATE TABLE dbo.Dispositivo (
    id_dispositivo    VARCHAR(30)  NOT NULL PRIMARY KEY,   -- ej. ESP32_SanJose_02
    id_lote           INT          NOT NULL REFERENCES dbo.Lote(id_lote),
    codigo            VARCHAR(20)  NOT NULL,
    modelo            VARCHAR(40)  NOT NULL,
    fecha_instalacion DATE         NULL,
    raw_seco          INT          NOT NULL,   -- calibración ADC suelo seco
    raw_mojado        INT          NOT NULL,   -- calibración ADC suelo saturado
    activo            BIT          NOT NULL DEFAULT 1
);
/* Lectura: telemetría tal como llega del ESP32 (HTTP POST / JSON).
   Los campos de texto (bomba_on, wifi_ok, falla_sensor) se guardan como
   vienen; la homologación se hace en el ETL. */
CREATE TABLE dbo.Lectura (
    id_lectura      BIGINT       NOT NULL PRIMARY KEY,
    id_dispositivo  VARCHAR(30)  NULL REFERENCES dbo.Dispositivo(id_dispositivo),
    fecha_hora      DATETIME2(0) NOT NULL,
    raw_suelo       INT          NULL,
    suelo_pct       DECIMAL(6,2) NULL,
    temperatura_c   DECIMAL(6,2) NULL,
    humedad_rel_pct DECIMAL(6,2) NULL,
    bomba_on        VARCHAR(5)   NULL,   -- ON/OFF (formato antiguo SI/NO)
    wifi_ok         VARCHAR(5)   NULL,   -- SI/NO/ERR
    pendientes      INT          NULL,   -- eventos en cola sin enviar
    falla_sensor    VARCHAR(30)  NULL    -- OK / ERR_SENSOR
);
CREATE INDEX IX_Lectura_Disp_Fecha ON dbo.Lectura(id_dispositivo, fecha_hora);
CREATE TABLE dbo.EventoRiego (
    id_evento      INT          NOT NULL PRIMARY KEY,
    id_dispositivo VARCHAR(30)  NOT NULL REFERENCES dbo.Dispositivo(id_dispositivo),
    inicio         DATETIME2(0) NOT NULL,
    fin            DATETIME2(0) NOT NULL,
    duracion_seg   INT          NOT NULL,
    suelo_inicio   DECIMAL(6,2) NULL,
    suelo_fin      DECIMAL(6,2) NULL,
    litros_est     DECIMAL(8,2) NULL,
    motivo_fin     VARCHAR(20)  NULL     -- HUM_OBJETIVO / TIEMPO_MAX / FALLA_SENSOR
);
GO
