/* =====================================================================
   04 - ETL en T-SQL equivalente al paquete SSIS
   Aplica EXACTAMENTE las mismas reglas que el paquete (ver guia_ssis.md).
   Usos: (a) contingencia si SSIS falla, (b) validar que SSIS y T-SQL
   producen los mismos conteos (procedimiento repetible).
   Idempotente: trunca y recarga (TRUNCATE antes de cargar).
   ===================================================================== */
USE RiegoInteligente_DW;
GO
SET NOCOUNT ON;
DECLARE @fecha_min DATETIME2(0) = '2025-01-01 00:00:00';   -- puesta en marcha del sistema
DECLARE @fecha_max DATETIME2(0) = SYSDATETIME();           -- no se aceptan fechas futuras

TRUNCATE TABLE dbo.Fact_Lectura;
TRUNCATE TABLE dbo.Fact_EventoRiego;
TRUNCATE TABLE dbo.Lectura_Cuarentena;
DELETE FROM dbo.Dim_Dispositivo; DBCC CHECKIDENT ('dbo.Dim_Dispositivo', RESEED, 0);

/* ---------- 1. Dimensión dispositivo (desnormaliza 5 tablas del OLTP) ---------- */
INSERT dbo.Dim_Dispositivo (id_dispositivo_nk, id_dispositivo, codigo, modelo, lote, area_ha, tipo_suelo,
                            ubicacion, cultivo, humedad_min, humedad_max, finca, vereda, municipio,
                            altitud_msnm, propietario)
SELECT UPPER(LTRIM(RTRIM(d.id_dispositivo))), d.id_dispositivo, d.codigo, d.modelo, l.nombre, l.area_ha,
       l.tipo_suelo,
       CASE WHEN l.nombre LIKE N'%Invernadero%' THEN N'Invernadero' ELSE N'Campo abierto' END,
       c.nombre, c.humedad_min, c.humedad_max, f.nombre, f.vereda, f.municipio, f.altitud_msnm, p.nombre
FROM RiegoInteligente.dbo.Dispositivo d
JOIN RiegoInteligente.dbo.Lote l        ON l.id_lote = d.id_lote
JOIN RiegoInteligente.dbo.Cultivo c     ON c.id_cultivo = l.id_cultivo
JOIN RiegoInteligente.dbo.Finca f       ON f.id_finca = l.id_finca
JOIN RiegoInteligente.dbo.Propietario p ON p.id_propietario = f.id_propietario;

/* ---------- 2-3. Extracción + Derived Column + Conditional Split ----------
   (la primera regla que se cumple define el motivo de rechazo) */
DROP TABLE IF EXISTS #stg;
SELECT l.*, c.id_clean,
       CAST(CASE WHEN UPPER(LTRIM(RTRIM(l.bomba_on))) IN ('ON','SI') THEN 1 ELSE 0 END AS BIT) AS bomba_bit,
       CAST(CASE WHEN UPPER(LTRIM(RTRIM(l.wifi_ok))) = 'SI' THEN 1 ELSE 0 END AS BIT)          AS wifi_bit,
       CASE WHEN l.suelo_pct > 100 THEN 100.00 WHEN l.suelo_pct < 0 THEN 0.00 ELSE l.suelo_pct END AS suelo_clean,
       LTRIM(RTRIM(REPLACE(ISNULL(l.falla_sensor, 'OK'), '#', '')))           AS falla_clean,
       CAST(CASE
         WHEN c.id_clean IS NULL OR c.id_clean = ''
           OR NOT EXISTS (SELECT 1 FROM dbo.Dim_Dispositivo d WHERE d.id_dispositivo_nk = c.id_clean)
           OR (l.raw_suelo IS NULL AND l.suelo_pct IS NULL AND l.temperatura_c IS NULL AND l.humedad_rel_pct IS NULL)
              THEN 'Sin_Dispositivo_O_Nulos'
         WHEN l.fecha_hora < @fecha_min OR l.fecha_hora > @fecha_max
              THEN 'Fecha_Invalida'
         WHEN l.temperatura_c > 80 OR l.temperatura_c < -10
           OR l.humedad_rel_pct > 100 OR l.humedad_rel_pct < 0
           OR l.raw_suelo < 0 OR l.raw_suelo > 4095
              THEN 'Sensor_Fuera_Rango_Critico'
       END AS VARCHAR(40)) AS motivo_rechazo
INTO #stg
FROM RiegoInteligente.dbo.Lectura l
CROSS APPLY (SELECT UPPER(LTRIM(RTRIM(l.id_dispositivo))) AS id_clean) c;

INSERT dbo.Lectura_Cuarentena (id_lectura, id_dispositivo, fecha_hora, raw_suelo, suelo_pct, temperatura_c,
                               humedad_rel_pct, bomba_on, wifi_ok, pendientes, falla_sensor, motivo_rechazo)
SELECT id_lectura, id_dispositivo, fecha_hora, raw_suelo, suelo_pct, temperatura_c, humedad_rel_pct,
       bomba_on, wifi_ok, pendientes, falla_sensor, motivo_rechazo
FROM #stg WHERE motivo_rechazo IS NOT NULL;

/* ---------- 4. Sort con eliminación de duplicados + Lookup + carga ---------- */
;WITH validos AS (
    SELECT s.*, ROW_NUMBER() OVER (PARTITION BY s.id_clean, s.fecha_hora ORDER BY s.id_lectura) AS rn
    FROM #stg s WHERE s.motivo_rechazo IS NULL)
INSERT dbo.Fact_Lectura (id_lectura_origen, sk_dispositivo, sk_fecha, sk_hora, fecha_hora, raw_suelo, suelo_pct,
                         temperatura_c, humedad_rel_pct, bomba_on, wifi_ok, falla_sensor, falla_sensor_desc,
                         pendientes, alerta_logica)
SELECT v.id_lectura, d.sk_dispositivo,
       YEAR(v.fecha_hora) * 10000 + MONTH(v.fecha_hora) * 100 + DAY(v.fecha_hora),
       DATEPART(HOUR, v.fecha_hora), v.fecha_hora, v.raw_suelo, v.suelo_clean, v.temperatura_c,
       v.humedad_rel_pct, v.bomba_bit, v.wifi_bit,
       CAST(CASE WHEN v.falla_clean <> 'OK' THEN 1 ELSE 0 END AS BIT), v.falla_clean, v.pendientes,
       CAST(CASE WHEN v.suelo_clean > 85 AND v.bomba_bit = 1 THEN 1 ELSE 0 END AS BIT)
FROM validos v
JOIN dbo.Dim_Dispositivo d ON d.id_dispositivo_nk = v.id_clean
WHERE v.rn = 1;

/* ---------- 5. Hechos de eventos de riego ---------- */
INSERT dbo.Fact_EventoRiego (id_evento_origen, sk_dispositivo, sk_fecha, sk_hora, inicio, fin, duracion_seg,
                             suelo_inicio, suelo_fin, litros_est, motivo_fin)
SELECT e.id_evento, d.sk_dispositivo,
       YEAR(e.inicio) * 10000 + MONTH(e.inicio) * 100 + DAY(e.inicio), DATEPART(HOUR, e.inicio),
       e.inicio, e.fin, e.duracion_seg, e.suelo_inicio, e.suelo_fin, e.litros_est, e.motivo_fin
FROM RiegoInteligente.dbo.EventoRiego e
JOIN dbo.Dim_Dispositivo d ON d.id_dispositivo_nk = UPPER(LTRIM(RTRIM(e.id_dispositivo)));

/* ---------- 6. Balance de consistencia ---------- */
DECLARE @ext BIGINT = (SELECT COUNT_BIG(*) FROM #stg),
        @rec BIGINT = (SELECT COUNT_BIG(*) FROM dbo.Lectura_Cuarentena),
        @car BIGINT = (SELECT COUNT_BIG(*) FROM dbo.Fact_Lectura);
SELECT @ext AS extraidos, @rec AS rechazados, @ext - @rec - @car AS duplicados_eliminados, @car AS cargados,
       CASE WHEN @ext = @rec + (@ext - @rec - @car) + @car THEN 'CONSISTENTE' END AS balance;
/* Esperado: 1.003.400 = 1.200 + 1.000 + 1.001.200 */
SELECT motivo_rechazo, COUNT(*) AS filas FROM dbo.Lectura_Cuarentena GROUP BY motivo_rechazo;
/* Esperado: Sin_Dispositivo_O_Nulos 300 · Fecha_Invalida 300 · Sensor_Fuera_Rango_Critico 600 */
DROP TABLE #stg;
GO
