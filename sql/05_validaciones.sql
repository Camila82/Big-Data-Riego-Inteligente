/* =====================================================================
   05 - Validaciones de calidad y consistencia (antes de analizar)
   Ejecutar después del ETL (SSIS o script 04). Los valores esperados
   corresponden a los CSV de la simulación con semilla 20250101.
   ===================================================================== */
USE RiegoInteligente_DW;
GO
-- V1. Período, registros y dispositivos del DW
SELECT MIN(fecha_hora) AS desde, MAX(fecha_hora) AS hasta,
       COUNT_BIG(*) AS lecturas, COUNT(DISTINCT sk_dispositivo) AS dispositivos,
       COUNT(DISTINCT fecha_hora) / 1440.0 AS dias_observados
FROM dbo.Fact_Lectura;
-- Esperado: 2025-01-01 00:00 → 2025-04-10 10:39 · 1.001.200 · 7 · 99,44

-- V2. Tamaño de los grupos comparados (lecturas y eventos por dispositivo)
SELECT d.id_dispositivo, d.cultivo, d.ubicacion,
       (SELECT COUNT(*) FROM dbo.Fact_Lectura f WHERE f.sk_dispositivo = d.sk_dispositivo)     AS lecturas,
       (SELECT COUNT(*) FROM dbo.Fact_EventoRiego e WHERE e.sk_dispositivo = d.sk_dispositivo) AS eventos
FROM dbo.Dim_Dispositivo d ORDER BY d.id_dispositivo;
-- Esperado: 143.015 a 143.041 lecturas por nodo; 92 a 216 eventos por nodo

-- V3. Integridad referencial (debe dar 0 en todas)
SELECT
  (SELECT COUNT(*) FROM dbo.Fact_Lectura f LEFT JOIN dbo.Dim_Dispositivo d ON d.sk_dispositivo = f.sk_dispositivo WHERE d.sk_dispositivo IS NULL) AS huerfanos_disp,
  (SELECT COUNT(*) FROM dbo.Fact_Lectura f LEFT JOIN dbo.Dim_Tiempo t ON t.sk_fecha = f.sk_fecha WHERE t.sk_fecha IS NULL) AS huerfanos_fecha,
  (SELECT COUNT(*) FROM (SELECT sk_dispositivo, fecha_hora FROM dbo.Fact_Lectura GROUP BY sk_dispositivo, fecha_hora HAVING COUNT(*) > 1) x) AS duplicados_restantes;

-- V4. Valores faltantes por columna en el DW
SELECT SUM(CASE WHEN suelo_pct IS NULL THEN 1 ELSE 0 END) AS nulos_suelo,
       SUM(CASE WHEN temperatura_c IS NULL THEN 1 ELSE 0 END) AS nulos_temp,
       SUM(CASE WHEN humedad_rel_pct IS NULL THEN 1 ELSE 0 END) AS nulos_hr
FROM dbo.Fact_Lectura;

-- V5. Atípicos: lecturas con suelo = 0 % ¿son sequía real o falla del sensor?
SELECT falla_sensor, COUNT(*) AS lecturas_suelo_cero
FROM dbo.Fact_Lectura WHERE suelo_pct = 0 GROUP BY falla_sensor;
-- Esperado: 16.706 con falla (raw = 4095) y 167 sin falla (valores negativos acotados a 0 por el ETL)

-- V6. Atípicos de temperatura: ¿heladas reales o error?
SELECT d.ubicacion, COUNT(*) AS lecturas_bajo_cero, MIN(f.temperatura_c) AS minima,
       MIN(t.fecha) AS primera, MAX(t.fecha) AS ultima
FROM dbo.Fact_Lectura f JOIN dbo.Dim_Dispositivo d ON d.sk_dispositivo = f.sk_dispositivo
JOIN dbo.Dim_Tiempo t ON t.sk_fecha = f.sk_fecha
WHERE f.temperatura_c < 0 GROUP BY d.ubicacion;
-- Se conservan: son madrugadas de temporada seca (heladas), físicamente posibles en la Sabana.

-- V7. Alertas lógicas (bomba encendida con suelo > 85 %)
SELECT COUNT(*) AS alertas FROM dbo.Fact_Lectura WHERE alerta_logica = 1;   -- Esperado: 1

-- V8. Coherencia entre hechos: minutos con bomba ON vs. duración de eventos
SELECT (SELECT COUNT(*) FROM dbo.Fact_Lectura WHERE bomba_on = 1) AS minutos_bomba_on_lecturas,
       (SELECT SUM(duracion_seg) / 60.0 FROM dbo.Fact_EventoRiego) AS minutos_bomba_eventos;
-- Deben ser del mismo orden (los eventos se miden cada 2 s; las lecturas cada 60 s).
