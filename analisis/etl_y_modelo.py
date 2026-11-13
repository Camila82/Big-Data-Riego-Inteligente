"""Réplica en Python de las reglas del ETL (SSIS / script T-SQL 04) para calcular
las cifras del análisis y validarlas contra el Data Warehouse."""
import numpy as np
import pandas as pd
from pathlib import Path

CSV = Path(__file__).resolve().parent.parent / "datos" / "csv"
FECHA_MIN = pd.Timestamp("2025-01-01")
FECHA_MAX = pd.Timestamp("2026-11-12")   # fecha de ejecución del ETL: lo posterior es inválido


def cargar():
    lect = pd.read_csv(CSV / "Lectura.csv", dtype={"id_dispositivo": "string", "falla_sensor": "string",
                                                    "bomba_on": "string", "wifi_ok": "string"})
    disp = pd.read_csv(CSV / "Dispositivo.csv")
    lote = pd.read_csv(CSV / "Lote.csv")
    cult = pd.read_csv(CSV / "Cultivo.csv")
    finca = pd.read_csv(CSV / "Finca.csv")
    prop = pd.read_csv(CSV / "Propietario.csv")
    evt = pd.read_csv(CSV / "EventoRiego.csv", parse_dates=["inicio", "fin"])
    dim = (disp.merge(lote, on="id_lote", suffixes=("", "_lote"))
               .merge(cult.rename(columns={"nombre": "cultivo"}), on="id_cultivo")
               .merge(finca.rename(columns={"nombre": "finca"}), on="id_finca")
               .merge(prop.rename(columns={"nombre": "propietario"})[["id_propietario", "propietario"]],
                      on="id_propietario"))
    dim = dim.rename(columns={"nombre": "lote"})
    dim["id_dispositivo_nk"] = dim["id_dispositivo"].str.upper()
    dim["es_invernadero"] = dim["lote"].str.contains("Invernadero")
    return lect, dim, evt


def etl(lect, dim):
    df = lect.copy()
    df["id_clean"] = df["id_dispositivo"].str.strip().str.upper()
    df["fecha"] = pd.to_datetime(df["fecha_hora"])
    metricas_nulas = df[["raw_suelo", "suelo_pct", "temperatura_c", "humedad_rel_pct"]].isna().all(axis=1)
    sin_disp = df["id_clean"].isna() | (df["id_clean"] == "") | ~df["id_clean"].isin(dim["id_dispositivo_nk"])
    r1 = sin_disp | metricas_nulas
    r2 = ~r1 & ((df["fecha"] < FECHA_MIN) | (df["fecha"] > FECHA_MAX))
    fuera = ((df["temperatura_c"] > 80) | (df["temperatura_c"] < -10) |
             (df["humedad_rel_pct"] > 100) | (df["humedad_rel_pct"] < 0) |
             (df["raw_suelo"] < 0) | (df["raw_suelo"] > 4095))
    r3 = ~r1 & ~r2 & fuera
    df["motivo_rechazo"] = np.select([r1, r2, r3],
                                     ["Sin_Dispositivo_O_Nulos", "Fecha_Invalida", "Sensor_Fuera_Rango_Critico"],
                                     None)
    cuarentena = df[df["motivo_rechazo"].notna()]
    validos = df[df["motivo_rechazo"].isna()].copy()
    validos = validos.sort_values(["id_clean", "fecha", "id_lectura"])
    antes = len(validos)
    validos = validos.drop_duplicates(["id_clean", "fecha"], keep="first")
    duplicados = antes - len(validos)
    v = validos
    v["suelo_pct"] = v["suelo_pct"].clip(0, 100)
    v["bomba_on_bit"] = v["bomba_on"].str.strip().str.upper().isin(["ON", "SI"]).astype(int)
    v["wifi_ok_bit"] = (v["wifi_ok"].str.strip().str.upper() == "SI").astype(int)
    v["falla_desc"] = v["falla_sensor"].fillna("OK").str.replace("#", "", regex=False).str.strip()
    v["falla_bit"] = (v["falla_desc"] != "OK").astype(int)
    v = v.merge(dim[["id_dispositivo_nk", "id_dispositivo", "cultivo", "finca", "lote", "tipo_suelo",
                     "humedad_min", "humedad_max", "es_invernadero", "area_ha"]],
                left_on="id_clean", right_on="id_dispositivo_nk", suffixes=("_src", ""))
    v["alerta_logica"] = ((v["suelo_pct"] > 85) & (v["bomba_on_bit"] == 1)).astype(int)
    v["en_deficit"] = ((v["falla_bit"] == 0) & (v["suelo_pct"] < v["humedad_min"])).astype(int)
    v["hora"] = v["fecha"].dt.hour
    v["mes"] = v["fecha"].dt.month
    v["franja"] = pd.cut(v["hora"], [-1, 5, 11, 17, 23],
                         labels=["Madrugada (00–05)", "Mañana (06–11)", "Tarde (12–17)", "Noche (18–23)"])
    balance = dict(extraidos=len(lect), rechazados=len(cuarentena),
                   rechazos_por_motivo=cuarentena["motivo_rechazo"].value_counts().to_dict(),
                   duplicados=duplicados, cargados=len(v))
    return v, cuarentena, balance


if __name__ == "__main__":
    lect, dim, evt = cargar()
    v, q, b = etl(lect, dim)
    print(b)
    print("check:", b["extraidos"] == b["rechazados"] + b["duplicados"] + b["cargados"])
