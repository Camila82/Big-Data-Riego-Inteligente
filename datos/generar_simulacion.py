"""
Simulación de telemetría - Sistema IoT de Riego Inteligente (Gachancipá, Cundinamarca)
---------------------------------------------------------------------------------------
Genera los CSV que se cargan en la base transaccional RiegoInteligente:
  Propietario, Finca, Cultivo, Lote, Dispositivo, Lectura (>1.000.000), EventoRiego.

Reproducible: semilla fija (SEMILLA). Ejecutar:  python generar_simulacion.py
Reglas de control = las del firmware del ESP32 (ver informe):
  - Inicia riego si suelo_pct < humedad_min del cultivo, temperatura > 5 °C,
    sensor sin falla y han pasado >= 30 min desde el último riego.
  - Detiene al alcanzar humedad_max (HUM_OBJETIVO), a los 5 min (TIEMPO_MAX)
    o si el sensor falla (FALLA_SENSOR).
"""
import numpy as np
import pandas as pd
from pathlib import Path

SEMILLA = 20250101
rng = np.random.default_rng(SEMILLA)
OUT = Path(__file__).parent / "csv"
OUT.mkdir(exist_ok=True)

INICIO = pd.Timestamp("2025-01-01 00:00:00")
MINUTOS = 143_200                 # ≈ 99,4 días: 2025-01-01 → 2025-04-10
N_DUPLICADOS = 1_000              # reenvíos desde la cola de pendientes

# ---------------------------------------------------------------- maestros
propietario = pd.DataFrame({
    "id_propietario": range(1, 8),
    "nombre": ["Hellen Beltran", "Carlos Pérez", "María Gómez", "Juan Rodríguez",
               "Lucía Torres", "Camilo Sichaca", "Pedro Martí"],
    "documento": [str(1001234567 + i * 1111111) for i in range(7)],
    "telefono": ["3101234567", "3202345678", "3303456789", "3404567890",
                 "3505678901", "3606789012", "3707890123"],
    "email": ["hellen@fincas.com", "carlos@fincas.com", "maria@fincas.com", "juan@fincas.com",
              "lucia@fincas.com", "camilo@fincas.com", "pedro@fincas.com"],
})
finca = pd.DataFrame({
    "id_finca": range(1, 8), "id_propietario": range(1, 8),
    "nombre": ["Finca El Progreso", "Finca San José", "Finca La Esperanza", "Finca El Mirador",
               "Finca Villa Luz", "Finca La Virginia", "Finca Santa Bárbara"],
    "departamento": "Cundinamarca", "municipio": "Gachancipá",
    "vereda": ["Vereda El Salitre", "Vereda Patio Bonito", "Vereda Hato Grande", "Vereda Cascajal",
               "Sector Centro", "Vereda Hato Grande", "Vereda San Martín"],
    "latitud": [4.9123, 4.9200, 4.9050, 4.9300, 4.9150, 4.9080, 4.9250],
    "longitud": [-73.8765, -73.8800, -73.8650, -73.8900, -73.8700, -73.8680, -73.8850],
    "altitud_msnm": [2560, 2575, 2550, 2600, 2565, 2555, 2580],
})
cultivo = pd.DataFrame({
    "id_cultivo": range(1, 8),
    "nombre": ["Papa Pastusa", "Papa Criolla", "Maíz Forrajero", "Tomate Chonto",
               "Hortalizas Varias", "Papa Sabanera", "Fríjol Cargamanto"],
    "humedad_min": [60, 62, 50, 65, 63, 58, 55],
    "humedad_max": [75, 77, 68, 80, 78, 74, 70],
})
lote = pd.DataFrame({
    "id_lote": range(1, 8), "id_finca": range(1, 8), "id_cultivo": range(1, 8),
    "nombre": ["Lote Norte 1", "Lote Principal", "Lote Bajo", "Invernadero 1",
               "Huerta Central", "Lote La Virginia", "Lote San Martín"],
    "area_ha": [1.50, 2.00, 3.20, 0.80, 1.00, 2.50, 1.80],
    "tipo_suelo": ["Franco-Arcilloso", "Franco", "Arenoso", "Orgánico",
                   "Franco-Limoso", "Franco", "Arcilloso"],
    "fecha_siembra": ["2024-12-10", "2024-12-01", "2024-12-15", "2024-12-20",
                      "2024-12-12", "2024-12-05", "2024-12-18"],
})
dispositivo = pd.DataFrame({
    "id_dispositivo": ["ESP32_Progreso_01", "ESP32_SanJose_02", "ESP32_Esperanza_03",
                       "ESP32_Mirador_04", "ESP32_VillaLuz_05", "ESP32_Virginia_06",
                       "ESP32_StBarbara_07"],
    "id_lote": range(1, 8),
    "codigo": [f"NODO-{i:02d}" for i in range(1, 8)],
    "modelo": "DOIT ESP32 DEVKIT V1",
    "fecha_instalacion": "2024-12-28",
    "raw_seco": [3520, 3480, 3550, 3500, 3510, 3490, 3530],
    "raw_mojado": [1240, 1260, 1220, 1250, 1230, 1270, 1210],
    "activo": 1,
})

# Parámetros físicos de la simulación (no se cargan a la BD; documentados en el informe)
FACTOR_SUELO = {"Franco-Arcilloso": 0.90, "Franco": 1.00, "Arenoso": 1.55, "Orgánico": 0.85,
                "Franco-Limoso": 1.00, "Arcilloso": 0.75}
GANANCIA_RIEGO = {"Arenoso": 4.5, "Arcilloso": 2.8}          # % de humedad por minuto de bomba
SECADO_BASE = [0.020, 0.022, 0.019, 0.026, 0.024, 0.019, 0.020]  # % por minuto, por cultivo
CAUDAL_LPM = [2.5, 2.4, 2.8, 2.2, 2.5, 2.6, 2.4]                  # caudal de la bomba (L/min)
INVERNADERO = [False, False, False, True, False, False, False]
# Falla de sensor: prob. de inicio de episodio por minuto (VillaLuz_05 se degrada en el tiempo)
P_FALLA_BASE = 0.0008
# Wi-Fi: Virginia_06 tiene cobertura débil
P_WIFI = [0.0003, 0.0003, 0.0003, 0.0003, 0.0003, 0.0025, 0.0003]

# ---------------------------------------------------------------- clima diario (compartido)
n_dias = MINUTOS // 1440 + 2
fechas_dia = pd.date_range(INICIO.normalize(), periods=n_dias, freq="D")
mes = fechas_dia.month.values
tmin_mu = np.select([mes == 1, mes == 2, mes == 3], [4.6, 5.4, 7.4], 8.4)
tmin_sd = np.select([mes == 1, mes == 2, mes == 3], [2.2, 2.0, 1.5], 1.2)
tmax_mu = np.select([mes == 1, mes == 2, mes == 3], [21.0, 21.4, 20.0], 19.2)
tmin_d = rng.normal(tmin_mu, tmin_sd)
tmax_d = rng.normal(tmax_mu, 1.4)
p_lluvia = np.select([mes == 1, mes == 2, mes == 3], [0.10, 0.16, 0.45], 0.62)
llueve = rng.random(n_dias) < p_lluvia
lluvia_ini = rng.integers(13 * 60, 20 * 60, n_dias)       # tormentas de tarde
lluvia_dur = rng.integers(60, 241, n_dias)
lluvia_int = rng.uniform(0.12, 0.30, n_dias)               # % de humedad por minuto

i = np.arange(MINUTOS)
dia = i // 1440
m_dia = i % 1440
h = m_dia / 60.0
sol = np.clip(np.sin(np.pi * (h - 6) / 12), 0, None)

def temperatura_base():
    tmin_hoy, tmax_hoy = tmin_d[dia], tmax_d[dia]
    tmin_man = tmin_d[dia + 1]
    tmax_ayer = tmax_d[np.maximum(dia - 1, 0)]
    t = np.empty(MINUTOS)
    a = h < 6
    b = (h >= 6) & (h <= 14)
    c = h > 14
    t[a] = tmin_hoy[a] + (tmax_ayer[a] - tmin_hoy[a]) * (1 + np.cos(np.pi * (h[a] + 10) / 16)) / 2
    t[b] = tmin_hoy[b] + (tmax_hoy[b] - tmin_hoy[b]) * (1 - np.cos(np.pi * (h[b] - 6) / 8)) / 2
    t[c] = tmin_man[c] + (tmax_hoy[c] - tmin_man[c]) * (1 + np.cos(np.pi * (h[c] - 14) / 16)) / 2
    return t

T_BASE = temperatura_base()
LLUVIA_GLOBAL = llueve[dia] & (m_dia >= lluvia_ini[dia]) & (m_dia < lluvia_ini[dia] + lluvia_dur[dia])


def episodios(p, dur_min, dur_max):
    """Vector booleano con episodios (fallas / caídas de red) de duración aleatoria."""
    inicio = rng.random(MINUTOS) < p
    marca = np.zeros(MINUTOS + 1, dtype=np.int32)
    for s in np.flatnonzero(inicio):
        d = rng.integers(dur_min, dur_max + 1)
        marca[s] += 1
        marca[min(s + d, MINUTOS)] -= 1
    return np.cumsum(marca[:-1]) > 0


lecturas, eventos = [], []
for k, dev in dispositivo.iterrows():
    lt = lote.iloc[k]
    cu = cultivo.iloc[k]
    fi = finca.iloc[k]
    hmin, hmax = float(cu.humedad_min), float(cu.humedad_max)
    raw_s, raw_m = int(dev.raw_seco), int(dev.raw_mojado)
    fsuelo = FACTOR_SUELO[lt.tipo_suelo]
    gan = GANANCIA_RIEGO.get(lt.tipo_suelo, 3.5)
    inv = INVERNADERO[k]

    # temperatura y humedad del aire del nodo
    offset_alt = (2560 - fi.altitud_msnm) * 0.0065
    T = T_BASE + offset_alt - 2.0 * LLUVIA_GLOBAL + rng.normal(0, 0.3, MINUTOS)
    if inv:
        T = T + 2.5 + 3.5 * sol
    recibe = rng.random(n_dias) < 0.85                 # no todas las fincas reciben cada aguacero
    lluvia = LLUVIA_GLOBAL & recibe[dia] & (not inv)
    rango = np.maximum(tmax_d[dia] - tmin_d[dia], 1)
    HR = 97 - 50 * (T - tmin_d[dia] - offset_alt) / rango + 8 * LLUVIA_GLOBAL + (5 if inv else 0)
    HR = np.clip(HR + rng.normal(0, 2, MINUTOS), 30, 99)

    secado = SECADO_BASE[k] * fsuelo * (0.35 + 1.6 * sol) * np.maximum(0.3, 1 + 0.05 * (T - 14))
    ganancia_lluvia = np.where(lluvia, lluvia_int[dia], 0.0)

    if dev.id_dispositivo == "ESP32_VillaLuz_05":     # sensor que se degrada
        p_f = np.linspace(0.0015, 0.012, MINUTOS)
        falla = episodios(p_f, 3, 18)
    else:
        falla = episodios(P_FALLA_BASE, 3, 18)
    caida = episodios(P_WIFI[k], 10, 90) if P_WIFI[k] > 0.001 else episodios(P_WIFI[k], 3, 15)

    ruido_raw = rng.normal(0, 14, MINUTOS)
    S = rng.uniform(hmin + 3, hmax - 2)
    bombeando, ini_bomba, fin_ultimo = False, 0, -999
    ev = None
    raw_arr = np.empty(MINUTOS, dtype=np.int32)
    pct_arr = np.empty(MINUTOS)
    bomba_arr = np.zeros(MINUTOS, dtype=bool)
    pend_arr = np.zeros(MINUTOS, dtype=np.int32)
    pend = 0
    for t in range(MINUTOS):
        if bombeando:
            S += gan
        else:
            S -= secado[t]
        S += ganancia_lluvia[t]
        S = min(max(S, 5.0), 98.0)
        if falla[t]:
            raw = 4095
            pct = 0.0
        else:
            raw = int(round(raw_s - S / 100 * (raw_s - raw_m) + ruido_raw[t]))
            pct = min(max((raw_s - raw) / (raw_s - raw_m) * 100, 0.0), 100.0)
        # reglas del firmware
        if bombeando:
            motivo = None
            if falla[t]:
                motivo = "FALLA_SENSOR"
            elif pct >= hmax:
                motivo = "HUM_OBJETIVO"
            elif t - ini_bomba >= 5:
                motivo = "TIEMPO_MAX"
            if motivo:
                bombeando = False
                fin_ultimo = t
                dur = (t - ini_bomba) * 60 - int(rng.integers(0, 59))
                dur = max(dur, 20)
                ev.update(fin=t, duracion_seg=dur, suelo_fin=round(pct, 2), motivo_fin=motivo,
                          litros_est=round(dur / 60 * CAUDAL_LPM[k], 2))
                eventos.append(ev)
                ev = None
        else:
            if (not falla[t]) and pct < hmin and T[t] > 5.0 and (t - fin_ultimo) >= 30:
                bombeando = True
                ini_bomba = t
                ev = dict(id_dispositivo=dev.id_dispositivo, inicio=t, suelo_inicio=round(pct, 2))
        pend = pend + 1 if caida[t] else 0
        raw_arr[t], pct_arr[t], bomba_arr[t], pend_arr[t] = raw, pct, bombeando, pend

    wifi = np.where(caida, np.where(rng.random(MINUTOS) < 0.10, "ERR", "NO"), "SI")
    lecturas.append(pd.DataFrame({
        "minuto": i, "orden": k,
        "id_dispositivo": dev.id_dispositivo,
        "raw_suelo": raw_arr,
        "suelo_pct": np.round(pct_arr, 2),
        "temperatura_c": np.round(T, 2),
        "humedad_rel_pct": np.round(HR, 2),
        "bomba_on": np.where(bomba_arr, "ON", "OFF"),
        "wifi_ok": wifi,
        "pendientes": pend_arr,
        "falla_sensor": np.where(falla, "ERR_SENSOR", "OK"),
    }))
    print(f"{dev.id_dispositivo}: {len(eventos)} eventos acumulados")

lect = pd.concat(lecturas, ignore_index=True).sort_values(["minuto", "orden"], ignore_index=True)
lect["fecha_hora"] = INICIO + pd.to_timedelta(lect["minuto"], unit="min")
lect = lect.drop(columns=["minuto", "orden"])
lect["fecha_hora"] = lect["fecha_hora"].dt.strftime("%Y-%m-%d %H:%M:%S")
lect = lect.astype({"raw_suelo": "object", "suelo_pct": "object", "temperatura_c": "object",
                    "humedad_rel_pct": "object", "id_dispositivo": "object", "falla_sensor": "object",
                    "bomba_on": "object"})

# ---------------------------------------------------------------- registros sucios (para el ETL)
n = len(lect)
idx = rng.permutation(n)
pos = 0
def tomar(c):
    global pos
    sel = idx[pos:pos + c]
    pos += c
    return sel

# Rechazos esperados (cada fila con un único defecto)
s = tomar(150); lect.loc[s, "id_dispositivo"] = None                                   # sin dispositivo
s = tomar(150); lect.loc[s, ["raw_suelo", "suelo_pct", "temperatura_c", "humedad_rel_pct"]] = None  # métricas nulas
s = tomar(150); lect.loc[s, "fecha_hora"] = "1970-01-01 " + lect.loc[s, "fecha_hora"].str[11:]      # reset RTC
s = tomar(150); lect.loc[s, "fecha_hora"] = "2099-" + lect.loc[s, "fecha_hora"].str[5:]             # memoria corrupta
s = tomar(200); lect.loc[s, "temperatura_c"] = np.round(rng.uniform(85, 150, 200), 2)               # temperatura imposible
s = tomar(200); lect.loc[s, "humedad_rel_pct"] = np.round(rng.uniform(101, 250, 200), 2)            # humedad imposible
s = tomar(200); lect.loc[s, "raw_suelo"] = -rng.integers(1, 500, 200)                                # ADC negativo
# Defectos que se CORRIGEN (no se rechazan)
s = tomar(150); lect.loc[s, "suelo_pct"] = np.round(rng.uniform(100.1, 108, 150), 2)                # clamping a 100
s = tomar(150); lect.loc[s, "suelo_pct"] = np.round(-rng.uniform(0.1, 5, 150), 2)                   # clamping a 0
s = tomar(200); lect.loc[s, "id_dispositivo"] = lect.loc[s, "id_dispositivo"].str.lower() + " "  # minúsculas + espacio final
s = tomar(200); lect.loc[s, "bomba_on"] = lect.loc[s, "bomba_on"].map({"ON": "SI", "OFF": "NO"})   # formato antiguo
s = tomar(1000); lect.loc[s, "falla_sensor"] = lect.loc[s, "falla_sensor"] + "#"                     # carácter basura
s = tomar(800); lect.loc[s, "falla_sensor"] = None                                                    # nulo

lect.insert(0, "id_lectura", np.arange(1, n + 1))
# Duplicados exactos por reenvío de la cola (70 % del nodo con Wi-Fi débil)
limpias = np.sort(idx[pos:])
lim_df = lect.iloc[limpias]
dup_v = lim_df[lim_df.id_dispositivo == "ESP32_Virginia_06"].sample(700, random_state=SEMILLA)
dup_o = lim_df[lim_df.id_dispositivo != "ESP32_Virginia_06"].sample(300, random_state=SEMILLA)
dups = pd.concat([dup_v, dup_o]).copy()
dups["id_lectura"] = np.arange(n + 1, n + 1 + N_DUPLICADOS)
lect = pd.concat([lect, dups], ignore_index=True)

cols = ["id_lectura", "id_dispositivo", "fecha_hora", "raw_suelo", "suelo_pct", "temperatura_c",
        "humedad_rel_pct", "bomba_on", "wifi_ok", "pendientes", "falla_sensor"]
lect[cols].to_csv(OUT / "Lectura.csv", index=False, encoding="utf-8")

evt = pd.DataFrame(eventos)
evt = evt.sort_values(["inicio", "id_dispositivo"], ignore_index=True)
evt.insert(0, "id_evento", np.arange(1, len(evt) + 1))
evt["inicio"] = (INICIO + pd.to_timedelta(evt["inicio"], unit="min")).dt.strftime("%Y-%m-%d %H:%M:%S")
evt["fin"] = (INICIO + pd.to_timedelta(evt["fin"], unit="min")).dt.strftime("%Y-%m-%d %H:%M:%S")
evt[["id_evento", "id_dispositivo", "inicio", "fin", "duracion_seg", "suelo_inicio", "suelo_fin",
     "litros_est", "motivo_fin"]].to_csv(OUT / "EventoRiego.csv", index=False, encoding="utf-8")

for nombre, df in [("Propietario", propietario), ("Finca", finca), ("Cultivo", cultivo),
                   ("Lote", lote), ("Dispositivo", dispositivo)]:
    df.to_csv(OUT / f"{nombre}.csv", index=False, encoding="utf-8")

print("Lecturas:", len(lect), " Eventos de riego:", len(evt))
