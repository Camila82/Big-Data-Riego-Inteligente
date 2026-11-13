/* =====================================================================
   03 - Data Warehouse RiegoInteligente_DW (modelo estrella)
   Hechos:      Fact_Lectura (grano: 1 lectura por dispositivo por minuto)
                Fact_EventoRiego (grano: 1 ciclo de riego)
   Dimensiones: Dim_Dispositivo (dispositivo + lote + cultivo + finca + propietario,
                desnormalizada), Dim_Tiempo (día), Dim_Hora (hora y franja)
   Auditoría:   Lectura_Cuarentena
   ===================================================================== */
IF DB_ID('RiegoInteligente_DW') IS NULL CREATE DATABASE RiegoInteligente_DW;
GO
USE RiegoInteligente_DW;
GO
DROP TABLE IF EXISTS dbo.Fact_Lectura, dbo.Fact_EventoRiego, dbo.Lectura_Cuarentena,
                     dbo.Dim_Dispositivo, dbo.Dim_Tiempo, dbo.Dim_Hora;
GO
CREATE TABLE dbo.Dim_Dispositivo (
    sk_dispositivo    INT IDENTITY(1,1) PRIMARY KEY,
    id_dispositivo_nk VARCHAR(30)  NOT NULL UNIQUE,   -- clave natural en MAYÚSCULAS (para el Lookup)
    id_dispositivo    VARCHAR(30)  NOT NULL,
    codigo            VARCHAR(20)  NOT NULL,
    modelo            VARCHAR(40)  NOT NULL,
    lote              NVARCHAR(60) NOT NULL,
    area_ha           DECIMAL(6,2) NULL,
    tipo_suelo        NVARCHAR(40) NULL,
    ubicacion         NVARCHAR(20) NOT NULL,          -- Invernadero / Campo abierto
    cultivo           NVARCHAR(60) NOT NULL,
    humedad_min       DECIMAL(5,2) NOT NULL,
    humedad_max       DECIMAL(5,2) NOT NULL,
    finca             NVARCHAR(80) NOT NULL,
    vereda            NVARCHAR(80) NULL,
    municipio         NVARCHAR(50) NOT NULL,
    altitud_msnm      INT          NULL,
    propietario       NVARCHAR(80) NOT NULL
);
CREATE TABLE dbo.Dim_Tiempo (
    sk_fecha     INT          NOT NULL PRIMARY KEY,   -- AAAAMMDD
    fecha        DATE         NOT NULL,
    anio         SMALLINT     NOT NULL,
    mes          TINYINT      NOT NULL,
    nombre_mes   NVARCHAR(12) NOT NULL,
    dia          TINYINT      NOT NULL,
    dia_semana   NVARCHAR(12) NOT NULL,
    semana_anio  TINYINT      NOT NULL,
    temporada    NVARCHAR(25) NOT NULL                -- régimen bimodal Sabana de Bogotá
);
CREATE TABLE dbo.Dim_Hora (
    sk_hora   TINYINT      NOT NULL PRIMARY KEY,      -- 0..23
    hora_txt  CHAR(5)      NOT NULL,
    franja    NVARCHAR(12) NOT NULL,
    orden_franja TINYINT   NOT NULL
);
CREATE TABLE dbo.Fact_Lectura (
    id_lectura_origen BIGINT       NOT NULL PRIMARY KEY,
    sk_dispositivo    INT          NOT NULL REFERENCES dbo.Dim_Dispositivo(sk_dispositivo),
    sk_fecha          INT          NOT NULL REFERENCES dbo.Dim_Tiempo(sk_fecha),
    sk_hora           TINYINT      NOT NULL REFERENCES dbo.Dim_Hora(sk_hora),
    fecha_hora        DATETIME2(0) NOT NULL,
    raw_suelo         INT          NULL,
    suelo_pct         DECIMAL(6,2) NULL,              -- acotado 0..100
    temperatura_c     DECIMAL(6,2) NULL,
    humedad_rel_pct   DECIMAL(6,2) NULL,
    bomba_on          BIT          NOT NULL,
    wifi_ok           BIT          NOT NULL,
    falla_sensor      BIT          NOT NULL,
    falla_sensor_desc VARCHAR(30)  NOT NULL,
    pendientes        INT          NULL,
    alerta_logica     BIT          NOT NULL           -- suelo > 85 % con bomba encendida
);
CREATE TABLE dbo.Fact_EventoRiego (
    id_evento_origen INT          NOT NULL PRIMARY KEY,
    sk_dispositivo   INT          NOT NULL REFERENCES dbo.Dim_Dispositivo(sk_dispositivo),
    sk_fecha         INT          NOT NULL REFERENCES dbo.Dim_Tiempo(sk_fecha),
    sk_hora          TINYINT      NOT NULL REFERENCES dbo.Dim_Hora(sk_hora),   -- hora de inicio
    inicio           DATETIME2(0) NOT NULL,
    fin              DATETIME2(0) NOT NULL,
    duracion_seg     INT          NOT NULL,
    suelo_inicio     DECIMAL(6,2) NULL,
    suelo_fin        DECIMAL(6,2) NULL,
    litros_est       DECIMAL(8,2) NULL,
    motivo_fin       VARCHAR(20)  NULL
);
CREATE TABLE dbo.Lectura_Cuarentena (
    id_cuarentena   BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_lectura      BIGINT       NULL,
    id_dispositivo  VARCHAR(30)  NULL,
    fecha_hora      DATETIME2(0) NULL,
    raw_suelo       INT          NULL,
    suelo_pct       DECIMAL(6,2) NULL,
    temperatura_c   DECIMAL(6,2) NULL,
    humedad_rel_pct DECIMAL(6,2) NULL,
    bomba_on        VARCHAR(5)   NULL,
    wifi_ok         VARCHAR(5)   NULL,
    pendientes      INT          NULL,
    falla_sensor    VARCHAR(30)  NULL,
    motivo_rechazo  VARCHAR(40)  NOT NULL,
    fecha_carga     DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
);
GO
/* ---------- Poblar Dim_Hora ---------- */
;WITH h AS (SELECT TOP (24) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS n FROM sys.all_objects)
INSERT dbo.Dim_Hora (sk_hora, hora_txt, franja, orden_franja)
SELECT n, RIGHT('0' + CAST(n AS VARCHAR(2)), 2) + ':00',
       CASE WHEN n <= 5 THEN N'Madrugada' WHEN n <= 11 THEN N'Mañana' WHEN n <= 17 THEN N'Tarde' ELSE N'Noche' END,
       CASE WHEN n <= 5 THEN 1 WHEN n <= 11 THEN 2 WHEN n <= 17 THEN 3 ELSE 4 END
FROM h;
/* ---------- Poblar Dim_Tiempo (2025-01-01 a 2025-12-31) ---------- */
SET LANGUAGE Spanish;
;WITH d AS (
    SELECT CAST('2025-01-01' AS DATE) AS f
    UNION ALL SELECT DATEADD(DAY, 1, f) FROM d WHERE f < '2025-12-31')
INSERT dbo.Dim_Tiempo
SELECT YEAR(f) * 10000 + MONTH(f) * 100 + DAY(f), f, YEAR(f), MONTH(f),
       UPPER(LEFT(DATENAME(MONTH, f), 1)) + SUBSTRING(DATENAME(MONTH, f), 2, 20),
       DAY(f), DATENAME(WEEKDAY, f), DATEPART(WEEK, f),
       CASE WHEN MONTH(f) IN (12, 1, 2, 6, 7, 8) THEN N'Seca' ELSE N'Lluviosa' END
FROM d OPTION (MAXRECURSION 400);
SET LANGUAGE us_english;
GO
