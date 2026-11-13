# Guía: ajustar el paquete SSIS al nuevo DW

El paquete que ya tienen (`Package.dtsx`, con OLE DB Source → Derived Column → Conditional Split → Sort → Destinos) sirve casi igual. Estos son los cambios para cargar el millón de lecturas en `RiegoInteligente_DW`. El script `04_etl_tsql.sql` aplica las mismas reglas: úsenlo para comprobar que SSIS da los mismos conteos.

## 0. Preparación
1. Ejecuten `01_oltp_ddl.sql`, `02_carga_csv.sql` y `03_dw_ddl.sql`, en ese orden.
2. Connection Managers (OLE DB): `RiegoInteligente` (origen) y `RiegoInteligente_DW` (destino).

## 1. Control Flow (orden)
| # | Tarea | Contenido |
|---|---|---|
| 1 | Execute SQL Task "Limpiar DW" | `TRUNCATE TABLE dbo.Fact_Lectura; TRUNCATE TABLE dbo.Fact_EventoRiego; TRUNCATE TABLE dbo.Lectura_Cuarentena; DELETE FROM dbo.Dim_Dispositivo; DBCC CHECKIDENT('dbo.Dim_Dispositivo', RESEED, 0);` |
| 2 | Data Flow "DF_Dim_Dispositivo" | Origen: consulta del bloque 1 de `04_etl_tsql.sql` (JOIN de Dispositivo, Lote, Cultivo, Finca y Propietario) → Destino `Dim_Dispositivo` |
| 3 | Data Flow "DF_Fact_Lectura" | Sección 2 |
| 4 | Data Flow "DF_Fact_EventoRiego" | Sección 3 |
| 5 | Execute SQL Task "Balance" | Consulta V1 de `05_validaciones.sql` |

`Dim_Tiempo` y `Dim_Hora` se llenan una sola vez con `03_dw_ddl.sql`.

## 2. DF_Fact_Lectura
**OLE DB Source:** `SELECT * FROM dbo.Lectura`

**Derived Column** (reemplazar la columna o agregar una nueva):
| Columna | Expresión SSIS |
|---|---|
| id_dispositivo_clean | `UPPER(TRIM(id_dispositivo))` |
| bomba_on_bit | `UPPER(TRIM(bomba_on)) == "ON" \|\| UPPER(TRIM(bomba_on)) == "SI" ? (DT_BOOL)1 : (DT_BOOL)0` |
| wifi_ok_bit | `UPPER(TRIM(wifi_ok)) == "SI" ? (DT_BOOL)1 : (DT_BOOL)0` |
| suelo_pct_clean | `ISNULL(suelo_pct) ? NULL(DT_NUMERIC,6,2) : (suelo_pct > 100 ? (DT_NUMERIC,6,2)100 : (suelo_pct < 0 ? (DT_NUMERIC,6,2)0 : suelo_pct))` |
| falla_sensor_clean | `(DT_STR,30,1252)TRIM(REPLACE(ISNULL(falla_sensor) ? "OK" : (DT_WSTR,30)falla_sensor, "#", ""))` |
| falla_sensor_bit | `(DT_STR,30,1252)TRIM(REPLACE(ISNULL(falla_sensor) ? "OK" : (DT_WSTR,30)falla_sensor, "#", "")) != "OK"` |
| sk_fecha | `YEAR(fecha_hora) * 10000 + MONTH(fecha_hora) * 100 + DAY(fecha_hora)` |
| sk_hora | `(DT_UI1)DATEPART("hh", fecha_hora)` |

> El error que se ve en su captura ("cannot convert between unicode and non-unicode") se corrige con el cast `(DT_STR,30,1252)` que tiene `falla_sensor_clean`.

**Conditional Split.** El orden importa porque gana la primera regla que se cumple:
| Salida | Condición |
|---|---|
| Sin_Dispositivo_O_Nulos | `ISNULL(id_dispositivo) \|\| LEN(TRIM(id_dispositivo)) == 0 \|\| (ISNULL(raw_suelo) && ISNULL(suelo_pct) && ISNULL(temperatura_c) && ISNULL(humedad_rel_pct))` |
| Fecha_Invalida | `fecha_hora < (DT_DBTIMESTAMP2,0)"2025-01-01 00:00:00" \|\| fecha_hora > GETDATE()` |
| Sensor_Fuera_Rango_Critico | `temperatura_c > 80 \|\| temperatura_c < -10 \|\| humedad_rel_pct > 100 \|\| humedad_rel_pct < 0 \|\| raw_suelo < 0 \|\| raw_suelo > 4095` |
| (Default) Datos_Validos | — |

Cada salida de rechazo pasa por un **Derived Column** que agrega `motivo_rechazo` (por ejemplo, `"Fecha_Invalida"`). Las tres se unen en un **Union All** que va a `Lectura_Cuarentena`.

**Datos_Validos:**
1. **Lookup** contra `Dim_Dispositivo`: `id_dispositivo_clean = id_dispositivo_nk`, devuelve `sk_dispositivo`. Configúrenlo con *Redirect rows to no match output* y manden esa salida a cuarentena con `motivo_rechazo = "Sin_Dispositivo_O_Nulos"`.
2. **Sort** por `id_dispositivo_clean` y `fecha_hora`, con **Remove rows with duplicate sort values** activado. Así se eliminan las 1.000 retransmisiones.
3. **Derived Column** `alerta_logica`: `suelo_pct_clean > 85 && bomba_on_bit`.
4. **OLE DB Destination** `Fact_Lectura`. Mapeo: `id_lectura → id_lectura_origen`, `suelo_pct_clean → suelo_pct`, `bomba_on_bit → bomba_on`, `wifi_ok_bit → wifi_ok`, `falla_sensor_bit → falla_sensor`, `falla_sensor_clean → falla_sensor_desc`.

## 3. DF_Fact_EventoRiego
OLE DB Source `EventoRiego` → Derived Column (`UPPER(TRIM(id_dispositivo))`, `sk_fecha` y `sk_hora` calculados a partir de `inicio`) → Lookup `Dim_Dispositivo` → OLE DB Destination `Fact_EventoRiego` (`id_evento → id_evento_origen`).

## 4. Resultado esperado (evidencia para el informe)
| Métrica | Filas |
|---|---|
| Extraídos (origen) | 1.003.400 |
| Sin_Dispositivo_O_Nulos | 300 |
| Fecha_Invalida | 300 |
| Sensor_Fuera_Rango_Critico | 600 |
| **Total cuarentena** | **1.200** |
| Duplicados eliminados (Sort) | 1.000 |
| **Cargados en Fact_Lectura** | **1.001.200** |
| Eventos de riego cargados | 992 |

Balance: 1.003.400 = 1.200 + 1.000 + 1.001.200. Tomen captura del Data Flow terminado (con los conteos de filas sobre cada flecha) y del resultado de la consulta V1.
