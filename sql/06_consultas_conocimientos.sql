/* =====================================================================
   06 - Consultas que reproducen cada indicador y conocimiento del sitio
   (procedimiento repetible: mismos números que el dashboard)
   ===================================================================== */
USE RiegoInteligente_DW;
GO
/* Días observados por mes (denominador de las tasas por día) */
DROP TABLE IF EXISTS #dias;
SELECT t.mes, COUNT(DISTINCT f.fecha_hora) / 1440.0 AS dias
INTO #dias
FROM dbo.Fact_Lectura f JOIN dbo.Dim_Tiempo t ON t.sk_fecha = f.sk_fecha GROUP BY t.mes;

/* ---------- KPIs generales ---------- */
SELECT COUNT_BIG(*)                                              AS lecturas_validas,
       COUNT(DISTINCT sk_dispositivo)                            AS dispositivos_activos,
       AVG(CASE WHEN falla_sensor = 0 THEN suelo_pct END)        AS humedad_suelo_prom_sin_fallas,   -- 71,76
       100.0 * SUM(CAST(bomba_on AS INT)) / COUNT(*)             AS pct_tiempo_bomba,                -- 0,45
       100.0 * SUM(CAST(falla_sensor AS INT)) / COUNT(*)         AS pct_falla_sensor,                -- 1,67
       100.0 * SUM(CASE WHEN wifi_ok = 0 THEN 1 ELSE 0 END) / COUNT(*) AS pct_sin_wifi               -- 1,83
FROM dbo.Fact_Lectura;
SELECT COUNT(*) AS eventos, SUM(litros_est) AS litros, SUM(litros_est) / (SELECT SUM(dias) FROM #dias) AS litros_dia,
       AVG(1.0 * duracion_seg) AS duracion_media_s                                               -- 992 · 9.967,9 · 100,2 · 244,4
FROM dbo.Fact_EventoRiego;

/* ---------- C1 (univariado): humedad del suelo, media vs mediana, con y sin fallas ---------- */
SELECT 'Todas' AS grupo, COUNT(*) AS n, AVG(suelo_pct) AS media,
       (SELECT DISTINCT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY suelo_pct) OVER () FROM dbo.Fact_Lectura) AS mediana,
       STDEV(suelo_pct) AS desv
FROM dbo.Fact_Lectura
UNION ALL
SELECT 'Sin falla', COUNT(*), AVG(suelo_pct),
       (SELECT DISTINCT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY suelo_pct) OVER () FROM dbo.Fact_Lectura WHERE falla_sensor = 0),
       STDEV(suelo_pct)
FROM dbo.Fact_Lectura WHERE falla_sensor = 0;
-- Esperado: Todas 70,57 / 70,44 / 13,45 · Sin falla 71,76 / 70,63 / 9,90

/* ---------- C2 (bivariado): fallas de sensor por dispositivo y por mes ---------- */
SELECT d.id_dispositivo, COUNT(*) AS lecturas, SUM(CAST(f.falla_sensor AS INT)) AS fallas,
       100.0 * SUM(CAST(f.falla_sensor AS INT)) / COUNT(*) AS pct_falla
FROM dbo.Fact_Lectura f JOIN dbo.Dim_Dispositivo d ON d.sk_dispositivo = f.sk_dispositivo
GROUP BY d.id_dispositivo ORDER BY pct_falla DESC;
SELECT t.mes, CASE WHEN d.id_dispositivo = 'ESP32_VillaLuz_05' THEN 'VillaLuz_05' ELSE 'Otros 6' END AS grupo,
       COUNT(*) AS lecturas, 100.0 * SUM(CAST(f.falla_sensor AS INT)) / COUNT(*) AS pct_falla
FROM dbo.Fact_Lectura f JOIN dbo.Dim_Dispositivo d ON d.sk_dispositivo = f.sk_dispositivo
JOIN dbo.Dim_Tiempo t ON t.sk_fecha = f.sk_fecha
GROUP BY t.mes, CASE WHEN d.id_dispositivo = 'ESP32_VillaLuz_05' THEN 'VillaLuz_05' ELSE 'Otros 6' END
ORDER BY grupo, t.mes;

/* ---------- C3 (bivariado): conectividad por dispositivo ---------- */
SELECT d.id_dispositivo, COUNT(*) AS lecturas, SUM(CASE WHEN f.wifi_ok = 0 THEN 1 ELSE 0 END) AS sin_wifi,
       100.0 * SUM(CASE WHEN f.wifi_ok = 0 THEN 1 ELSE 0 END) / COUNT(*) AS pct_sin_wifi,
       MAX(f.pendientes) AS max_pendientes
FROM dbo.Fact_Lectura f JOIN dbo.Dim_Dispositivo d ON d.sk_dispositivo = f.sk_dispositivo
GROUP BY d.id_dispositivo ORDER BY pct_sin_wifi DESC;
-- Duplicados por reenvío de la cola, por dispositivo (desde el origen OLTP)
SELECT UPPER(LTRIM(RTRIM(id_dispositivo))) AS dispositivo, COUNT(*) - COUNT(DISTINCT fecha_hora) AS duplicados
FROM RiegoInteligente.dbo.Lectura GROUP BY UPPER(LTRIM(RTRIM(id_dispositivo))) ORDER BY duplicados DESC;

/* ---------- C4 (bivariado): litros por día por nodo según mes y ubicación ---------- */
SELECT t.mes, d.ubicacion, COUNT(*) AS eventos, SUM(e.litros_est) AS litros,
       SUM(e.litros_est) / MAX(dd.dias) / COUNT(DISTINCT d.sk_dispositivo) AS litros_dia_por_nodo
FROM dbo.Fact_EventoRiego e JOIN dbo.Dim_Dispositivo d ON d.sk_dispositivo = e.sk_dispositivo
JOIN dbo.Dim_Tiempo t ON t.sk_fecha = e.sk_fecha JOIN #dias dd ON dd.mes = t.mes
GROUP BY t.mes, d.ubicacion ORDER BY d.ubicacion, t.mes;
-- Esperado campo abierto: 16,02 · 15,51 · 10,10 · 10,23 | invernadero: 19,14 · 19,77 · 19,53 · 18,27

/* ---------- C5 (multivariado): cultivo × temporada × franja horaria ---------- */
DROP TABLE IF EXISTS #dias_temp;
SELECT t.temporada, SUM(dd.dias) AS dias
INTO #dias_temp
FROM #dias dd JOIN (SELECT DISTINCT mes, temporada FROM dbo.Dim_Tiempo) t ON t.mes = dd.mes GROUP BY t.temporada;

SELECT d.cultivo, t.temporada, h.franja, COUNT(*) AS eventos, SUM(e.litros_est) AS litros,
       SUM(e.litros_est) / MAX(dt.dias) AS litros_dia
FROM dbo.Fact_EventoRiego e
JOIN dbo.Dim_Dispositivo d ON d.sk_dispositivo = e.sk_dispositivo
JOIN dbo.Dim_Tiempo t      ON t.sk_fecha = e.sk_fecha
JOIN dbo.Dim_Hora h        ON h.sk_hora = e.sk_hora
JOIN #dias_temp dt         ON dt.temporada = t.temporada
GROUP BY d.cultivo, t.temporada, h.franja, h.orden_franja
ORDER BY d.cultivo, t.temporada DESC, h.orden_franja;

-- Cambio de consumo seca → lluviosa por cultivo (litros/día)
SELECT d.cultivo, d.ubicacion,
       SUM(CASE WHEN t.temporada = 'Seca' THEN e.litros_est END) / (SELECT dias FROM #dias_temp WHERE temporada = 'Seca') AS ld_seca,
       SUM(CASE WHEN t.temporada = 'Lluviosa' THEN e.litros_est END) / (SELECT dias FROM #dias_temp WHERE temporada = 'Lluviosa') AS ld_lluviosa
FROM dbo.Fact_EventoRiego e JOIN dbo.Dim_Dispositivo d ON d.sk_dispositivo = e.sk_dispositivo
JOIN dbo.Dim_Tiempo t ON t.sk_fecha = e.sk_fecha
GROUP BY d.cultivo, d.ubicacion ORDER BY d.ubicacion, d.cultivo;

-- Participación de la franja tarde (12–17 h) en los litros, por ubicación y temporada
SELECT d.ubicacion, t.temporada,
       100.0 * SUM(CASE WHEN h.franja = N'Tarde' THEN e.litros_est ELSE 0 END) / SUM(e.litros_est) AS pct_litros_tarde
FROM dbo.Fact_EventoRiego e JOIN dbo.Dim_Dispositivo d ON d.sk_dispositivo = e.sk_dispositivo
JOIN dbo.Dim_Tiempo t ON t.sk_fecha = e.sk_fecha JOIN dbo.Dim_Hora h ON h.sk_hora = e.sk_hora
GROUP BY d.ubicacion, t.temporada;
