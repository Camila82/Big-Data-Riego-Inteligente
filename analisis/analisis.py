"""Calcula KPIs, análisis univariados, bivariados y multivariado, y genera los
gráficos SVG de evidencia y resultados.json. Ejecutar: python analisis.py"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from etl_y_modelo import cargar, etl

OUT = Path(__file__).parent / "salida"
OUT.mkdir(exist_ok=True)
lect, dim, evt = cargar()
v, cuar, balance = etl(lect, dim)

FIN = v["fecha"].max()
INI = v["fecha"].min()
DIAS = {1: 31, 2: 28, 3: 31, 4: (FIN - pd.Timestamp("2025-04-01")).total_seconds() / 86400 + 1 / 1440}
DIAS_TOT = sum(DIAS.values())
MESES = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr (1–10)"}
CORTO = {d: d.replace("ESP32_", "") for d in dim["id_dispositivo"]}

e = evt.merge(dim[["id_dispositivo", "cultivo", "tipo_suelo", "es_invernadero", "finca", "lote", "area_ha"]],
              on="id_dispositivo")
e["mes"] = e["inicio"].dt.month
e["hora"] = e["inicio"].dt.hour
e["franja"] = pd.cut(e["hora"], [-1, 5, 11, 17, 23], labels=["Madrugada", "Mañana", "Tarde", "Noche"])
e["temporada"] = np.where(e["mes"] <= 2, "Seca (ene–feb)", "Lluviosa (mar–abr)")
e["ubicacion"] = np.where(e["es_invernadero"], "Invernadero", "Campo abierto")

R = {}
R["periodo"] = dict(inicio=str(INI), fin=str(FIN), dias=round(DIAS_TOT, 2))
R["balance_etl"] = balance
R["cuarentena_motivos"] = balance["rechazos_por_motivo"]

# ------------------------------------------------------------ KPIs
sinf = v[v.falla_bit == 0]
R["kpi"] = dict(
    lecturas_validas=int(len(v)),
    dispositivos_activos=int(v["id_dispositivo"].nunique()),
    humedad_suelo_prom=round(sinf["suelo_pct"].mean(), 2),
    pct_tiempo_bomba=round(v["bomba_on_bit"].mean() * 100, 3),
    pct_falla_sensor=round(v["falla_bit"].mean() * 100, 2),
    pct_sin_wifi=round((1 - v["wifi_ok_bit"].mean()) * 100, 2),
    eventos_riego=int(len(e)),
    litros_total=round(e["litros_est"].sum(), 1),
    litros_dia=round(e["litros_est"].sum() / DIAS_TOT, 1),
    duracion_media_s=round(e["duracion_seg"].mean(), 1),
    alertas_logicas=int(v["alerta_logica"].sum()),
)

# ------------------------------------------------------------ Univariados
s = v["suelo_pct"]
R["u1_suelo"] = dict(
    n=int(len(s)), media=round(s.mean(), 2), mediana=round(s.median(), 2), de=round(s.std(), 2),
    p25=round(s.quantile(.25), 2), p75=round(s.quantile(.75), 2),
    n_cero=int((s == 0).sum()), pct_cero=round((s == 0).mean() * 100, 2),
    n_cero_con_falla=int(((s == 0) & (v.falla_bit == 1)).sum()),
    media_sin_falla=round(sinf["suelo_pct"].mean(), 2), mediana_sin_falla=round(sinf["suelo_pct"].median(), 2),
    de_sin_falla=round(sinf["suelo_pct"].std(), 2),
    n_clamp_100=int((v["suelo_pct"] == 100).sum()),
)
t = v["temperatura_c"]
R["u2_temp"] = dict(media=round(t.mean(), 2), mediana=round(t.median(), 2), de=round(t.std(), 2),
                    min=round(t.min(), 2), max=round(t.max(), 2),
                    pct_le5=round((t <= 5).mean() * 100, 2), n_le5=int((t <= 5).sum()),
                    pct_bajo0=round((t < 0).mean() * 100, 3), n_bajo0=int((t < 0).sum()),
                    max_campo=round(v.loc[~v.es_invernadero, "temperatura_c"].max(), 2),
                    max_invernadero=round(v.loc[v.es_invernadero, "temperatura_c"].max(), 2))
mot = e["motivo_fin"].value_counts()
R["u3_riego"] = dict(motivos={k: int(c) for k, c in mot.items()},
                     motivos_pct={k: round(c / len(e) * 100, 2) for k, c in mot.items()},
                     dur_media=round(e.duracion_seg.mean(), 1), dur_mediana=float(e.duracion_seg.median()),
                     dur_de=round(e.duracion_seg.std(), 1), litros_media=round(e.litros_est.mean(), 2))

# ------------------------------------------------------------ Bivariados
g = v.groupby("id_dispositivo")
b1 = pd.DataFrame({"n": g.size(), "fallas": g.falla_bit.sum(), "pct": g.falla_bit.mean() * 100}).round(2)
R["b1_falla_disp"] = b1.reset_index().to_dict("records")
otros = v[v.id_dispositivo != "ESP32_VillaLuz_05"]
R["b1_resumen"] = dict(villaluz_pct=float(b1.loc["ESP32_VillaLuz_05", "pct"]),
                       otros_pct=round(otros.falla_bit.mean() * 100, 2),
                       villaluz_fallas=int(b1.loc["ESP32_VillaLuz_05", "fallas"]),
                       total_fallas=int(v.falla_bit.sum()))
vl = v[v.id_dispositivo == "ESP32_VillaLuz_05"].groupby("mes")
R["b1_villaluz_mes"] = [dict(mes=MESES[m], n=int(len(x)), pct=round(x.falla_bit.mean() * 100, 2))
                        for m, x in vl]
om = otros.groupby("mes").falla_bit.mean() * 100
R["b1_otros_mes"] = [dict(mes=MESES[m], pct=round(p, 2)) for m, p in om.items()]

w = pd.DataFrame({"n": g.size(), "sin_wifi": g.wifi_ok_bit.apply(lambda x: (x == 0).sum())})
w["pct"] = (w["sin_wifi"] / w["n"] * 100).round(2)
R["b4_wifi_disp"] = w.reset_index().to_dict("records")
otros_w = v[v.id_dispositivo != "ESP32_Virginia_06"]
dup_virginia = int((lect["id_lectura"] > 1_002_400).sum() and
                   lect.loc[lect.id_lectura > 1_002_400, "id_dispositivo"].eq("ESP32_Virginia_06").sum())
R["b4_resumen"] = dict(virginia_pct=float(w.loc["ESP32_Virginia_06", "pct"]),
                       otros_pct=round((1 - otros_w.wifi_ok_bit.mean()) * 100, 2),
                       pend_max_virginia=int(v.loc[v.id_dispositivo == "ESP32_Virginia_06", "pendientes"].max()),
                       duplicados_total=balance["duplicados"], duplicados_virginia=dup_virginia)

lpd = (e.groupby(["mes", "ubicacion"]).litros_est.sum().unstack())
lpd = lpd.div(pd.Series(DIAS), axis=0)
lpd["Campo abierto"] /= 6
R["b2_litros_mes"] = [dict(mes=MESES[m], campo=round(r["Campo abierto"], 2), invernadero=round(r["Invernadero"], 2))
                      for m, r in lpd.iterrows()]
temp = e.groupby(["temporada", "ubicacion"]).litros_est.sum().unstack()
dias_temp = {"Seca (ene–feb)": DIAS[1] + DIAS[2], "Lluviosa (mar–abr)": DIAS[3] + DIAS[4]}
temp = temp.div(pd.Series(dias_temp), axis=0); temp["Campo abierto"] /= 6
R["b2_temporada"] = {k: {c: round(val, 2) for c, val in r.items()} for k, r in temp.iterrows()}
ev_mes = e.groupby(["mes", "ubicacion"]).size().unstack()
R["b2_eventos_mes"] = {MESES[m]: {c: int(x) for c, x in r.items()} for m, r in ev_mes.iterrows()}

b3 = e.groupby(["tipo_suelo", "id_dispositivo", "cultivo", "es_invernadero"]).agg(
    eventos=("id_evento", "size"), litros=("litros_est", "sum")).reset_index()
b3["eventos_dia"] = (b3["eventos"] / DIAS_TOT).round(2)
b3["litros_dia"] = (b3["litros"] / DIAS_TOT).round(2)
R["b3_suelo"] = b3.sort_values("eventos_dia", ascending=False).to_dict("records")

# ------------------------------------------------------------ Multivariado (cálculo conjunto)
m = (e.groupby(["cultivo", "temporada", "franja"], observed=False).litros_est.sum()
       .reset_index())
m["dias"] = m["temporada"].map(dias_temp)
m["litros_dia"] = (m["litros_est"] / m["dias"]).round(2)
R["m1"] = m[["cultivo", "temporada", "franja", "litros_est", "litros_dia"]].to_dict("records")
fr = e.groupby("franja", observed=False).litros_est.sum()
R["m1_franja_pct"] = {k: round(x / fr.sum() * 100, 1) for k, x in fr.items()}
fr_ub = e.groupby(["ubicacion", "temporada", "franja"], observed=False).litros_est.sum()
fr_ub = (fr_ub / fr_ub.groupby(level=[0, 1]).transform("sum") * 100).round(1)
R["m1_tarde_pct"] = {f"{u} · {t}": float(fr_ub[(u, t, "Tarde")]) for u in ["Campo abierto", "Invernadero"]
                     for t in ["Seca (ene–feb)", "Lluviosa (mar–abr)"]}
cs = m.groupby(["cultivo", "temporada"]).litros_dia.sum().unstack()
cs["cambio_pct"] = ((cs["Lluviosa (mar–abr)"] / cs["Seca (ene–feb)"] - 1) * 100).round(1)
R["m1_cultivo_temporada"] = cs.round(2).reset_index().to_dict("records")

# ------------------------------------------------------------ Validaciones
R["validacion"] = dict(
    lecturas_por_disp_min=int(g.size().min()), lecturas_por_disp_max=int(g.size().max()),
    eventos_por_disp_min=int(e.groupby("id_dispositivo").size().min()),
    eventos_por_disp_max=int(e.groupby("id_dispositivo").size().max()),
    eventos_por_celda_m1_min=int(e.groupby(["cultivo", "temporada", "franja"], observed=False).size().min()),
    lecturas_deficit=int(v.en_deficit.sum()), pct_deficit=round(v.en_deficit.mean() * 100, 3),
)
(OUT / "resultados.json").write_text(json.dumps(R, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

# ============================================================ GRÁFICOS SVG
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
FONT = "font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif"


def fmt(x, d=1):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def nice(raw):
    """Máximo de eje 'redondo' divisible en 4 marcas."""
    paso = raw / 4
    mag = 10 ** np.floor(np.log10(paso))
    for f in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 10):
        if f * mag >= paso:
            return f * mag * 4
    return 10 * mag * 4


def svg(w, hgt, body, label):
    return (f'<svg viewBox="0 0 {w} {hgt}" role="img" aria-label="{label}" '
            f'xmlns="http://www.w3.org/2000/svg" style="{FONT};width:100%;height:auto">{body}</svg>')


def txt(x, y, s, size=12, color=INK2, anchor="start", weight=400):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{s}</text>')


def rect(x, y, w, hgt, color, tip, rx=3):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w,0):.1f}" height="{max(hgt,0):.1f}" rx="{rx}" '
            f'fill="{color}"><title>{tip}</title></rect>')


def histograma(valores, bins, color, xlab, unidad, lineas, nombre, label, destacar_cero=None):
    W, H, L, Rm, T, B = 720, 300, 60, 20, 20, 50
    cnt, edges = np.histogram(valores, bins=bins)
    pw, ph = W - L - Rm, H - T - B
    ymax = nice(cnt.max() * 1.05)
    x = lambda val: L + (val - edges[0]) / (edges[-1] - edges[0]) * pw
    y = lambda c: T + ph - c / ymax * ph
    body = ""
    for k in range(5):
        yy = T + ph - k / 4 * ph
        body += f'<line x1="{L}" x2="{W-Rm}" y1="{yy}" y2="{yy}" stroke="{GRID}"/>'
        body += txt(L - 8, yy + 4, fmt(ymax * k / 4 / 1000, 0) + " mil", 11, MUTED, "end")
    bw = pw / len(cnt)
    for c, a, b_ in zip(cnt, edges[:-1], edges[1:]):
        col = color
        if destacar_cero is not None and a <= 0 < b_:
            col = C2
        body += rect(x(a) + 1, y(c), bw - 2, T + ph - y(c), col,
                     f"{fmt(a,0)}–{fmt(b_,0)} {unidad}: {c:,} lecturas".replace(",", "."), 2)
    for val, lab, col in lineas:
        body += f'<line x1="{x(val)}" x2="{x(val)}" y1="{T}" y2="{T+ph}" stroke="{col}" stroke-width="2" stroke-dasharray="4 3"/>'
        body += txt(x(val) + 4, T + 12, lab, 11, INK, "start", 600)
    step = (edges[-1] - edges[0]) / 8
    for k in range(9):
        val = edges[0] + k * step
        body += txt(x(val), H - B + 18, fmt(val, 0), 11, MUTED, "middle")
    body += txt(L + pw / 2, H - 10, xlab, 12, INK2, "middle")
    (OUT / nombre).write_text(svg(W, H, body, label), encoding="utf-8")


def barras_h(items, nombre, label, unidad="%", destacar=None, dec=2, xmax=None, L=170):
    W = 720; fila = 34; T = 10; Rm = 120
    H = T + fila * len(items) + 30
    pw = W - L - Rm
    xmax = xmax or nice(max(vv for _, vv, _ in items) * 1.02)
    body = ""
    for k in range(5):
        xx = L + k / 4 * pw
        body += f'<line x1="{xx}" x2="{xx}" y1="{T}" y2="{H-30}" stroke="{GRID}"/>'
        body += txt(xx, H - 12, fmt(xmax * k / 4, 1 if xmax < 20 else 0) + (" " + unidad if k == 4 else ""), 11, MUTED, "middle")
    for j, (nom, val, extra) in enumerate(items):
        yy = T + j * fila + 6
        col = C2 if destacar and nom == destacar else C1
        body += txt(L - 8, yy + 15, nom, 12, INK, "end")
        body += rect(L, yy, val / xmax * pw, 20, col, f"{nom}: {fmt(val, dec)} {unidad} ({extra})")
        body += txt(L + val / xmax * pw + 6, yy + 15, f"{fmt(val, dec)} {unidad}", 12, INK, "start", 600)
        body += txt(W - 4, yy + 15, extra, 11, MUTED, "end")
    (OUT / nombre).write_text(svg(W, H, body, label), encoding="utf-8")


def lineas(cats, series, nombre, label, ylab, ymax):
    W, H, L, Rm, T, B = 720, 300, 60, 130, 20, 45
    pw, ph = W - L - Rm, H - T - B
    x = lambda k: L + 30 + k * (pw - 60) / (len(cats) - 1)
    y = lambda val: T + ph - val / ymax * ph
    body = ""
    for k in range(5):
        yy = T + ph - k / 4 * ph
        body += f'<line x1="{L}" x2="{L+pw}" y1="{yy}" y2="{yy}" stroke="{GRID}"/>'
        body += txt(L - 8, yy + 4, fmt(ymax * k / 4, 0), 11, MUTED, "end")
    for k, c in enumerate(cats):
        body += txt(x(k), H - B + 20, c, 12, INK2, "middle")
    for nom, vals, col in series:
        pts = " ".join(f"{x(k):.1f},{y(val):.1f}" for k, val in enumerate(vals))
        body += f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"/>'
        for k, val in enumerate(vals):
            body += (f'<circle cx="{x(k):.1f}" cy="{y(val):.1f}" r="5" fill="{col}" stroke="#fcfcfb" stroke-width="2">'
                     f'<title>{nom} · {cats[k]}: {fmt(val, 2)}</title></circle>')
            body += txt(x(k), y(val) - 10, fmt(val, 1), 11, INK, "middle")
        body += txt(x(len(cats) - 1) + 14, y(vals[-1]) + 4, nom, 12, INK, "start", 600)
    body += txt(14, T + ph / 2, ylab, 11, INK2, "middle").replace("<text ", f'<text transform="rotate(-90 14 {T+ph/2})" ')
    (OUT / nombre).write_text(svg(W, H, body, label), encoding="utf-8")


# U1 humedad de suelo
histograma(v["suelo_pct"], np.arange(0, 102, 2), C1, "Humedad del suelo (%) · lecturas válidas ene–abr 2025", "%",
           [(R["u1_suelo"]["media"], f"Media {fmt(R['u1_suelo']['media'],1)} %", INK),
            (R["u1_suelo"]["mediana"] + 0.01, "", INK2)],
           "u1_humedad_suelo.svg", "Histograma de humedad del suelo", destacar_cero=True)
# U2 temperatura
histograma(v["temperatura_c"], np.arange(-2, 32, 1), C1, "Temperatura ambiente (°C) · lecturas válidas ene–abr 2025", "°C",
           [(5, "Umbral 5 °C (bloquea riego)", C2)], "u2_temperatura.svg", "Histograma de temperatura")
# U3 motivo de fin de riego
barras_h([("Humedad objetivo", R["u3_riego"]["motivos_pct"].get("HUM_OBJETIVO", 0), f"{mot.get('HUM_OBJETIVO',0)} eventos"),
          ("Tiempo máximo (5 min)", R["u3_riego"]["motivos_pct"].get("TIEMPO_MAX", 0), f"{mot.get('TIEMPO_MAX',0)} eventos"),
          ("Falla de sensor", R["u3_riego"]["motivos_pct"].get("FALLA_SENSOR", 0), f"{mot.get('FALLA_SENSOR',0)} eventos")],
         "u3_motivo_fin.svg", "Motivo de finalización del riego", xmax=100)
# B1 falla por dispositivo
items = sorted([(CORTO[r["id_dispositivo"]], r["pct"], f"{int(r['fallas']):,} de {int(r['n']):,}".replace(",", "."))
                for r in R["b1_falla_disp"]], key=lambda z: -z[1])
barras_h(items, "b1_falla_dispositivo.svg", "Porcentaje de lecturas con falla de sensor por dispositivo", destacar="VillaLuz_05")
# B1b tendencia VillaLuz
lineas([r["mes"] for r in R["b1_villaluz_mes"]],
       [("VillaLuz_05", [r["pct"] for r in R["b1_villaluz_mes"]], C2),
        ("Otros 6 nodos", [r["pct"] for r in R["b1_otros_mes"]], C1)],
       "b1b_falla_mes.svg", "Tendencia mensual de fallas de sensor", "% de lecturas con falla", 15)
# B2 litros por día por mes
lineas([r["mes"] for r in R["b2_litros_mes"]],
       [("Invernadero", [r["invernadero"] for r in R["b2_litros_mes"]], C2),
        ("Campo abierto", [r["campo"] for r in R["b2_litros_mes"]], C1)],
       "b2_litros_mes.svg", "Litros por día por nodo según mes y ubicación", "Litros / día por nodo", 25)
# B3 eventos por día por tipo de suelo
barras_h([(f"{r['tipo_suelo']} · {CORTO[r['id_dispositivo']]}", r["eventos_dia"],
           f"{r['eventos']} eventos") for r in R["b3_suelo"]],
         "b3_eventos_suelo.svg", "Eventos de riego por día según tipo de suelo", unidad="ev/día",
         destacar=None, L=230)
# B4 wifi
items = sorted([(CORTO[r["id_dispositivo"]], r["pct"], f"{int(r['sin_wifi']):,} de {int(r['n']):,}".replace(",", "."))
                for r in R["b4_wifi_disp"]], key=lambda z: -z[1])
barras_h(items, "b4_wifi_dispositivo.svg", "Porcentaje de lecturas sin Wi-Fi por dispositivo", destacar="Virginia_06")

# M1 heatmap cultivo × (temporada, franja) — litros por día
seq = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
cultivos = list(m.groupby("cultivo").litros_dia.sum().sort_values(ascending=False).index)
cols = [(t_, f_) for t_ in ["Seca (ene–feb)", "Lluviosa (mar–abr)"] for f_ in ["Madrugada", "Mañana", "Tarde", "Noche"]]
vmax = m["litros_dia"].max()
W, L, T = 760, 150, 52; cw, chh = 74, 34
H = T + chh * len(cultivos) + 70
body = txt(L + 2 * cw, 18, "Temporada seca (ene–feb)", 12, INK, "middle", 600)
body += txt(L + 6 * cw + 8, 18, "Temporada lluviosa (mar–abr)", 12, INK, "middle", 600)
for j, (t_, f_) in enumerate(cols):
    xx = L + j * cw + (8 if j >= 4 else 0)
    body += txt(xx + cw / 2, 42, f_, 11, INK2, "middle")
for i_, cu in enumerate(cultivos):
    yy = T + i_ * chh
    body += txt(L - 8, yy + chh / 2 + 4, cu, 12, INK, "end")
    for j, (t_, f_) in enumerate(cols):
        xx = L + j * cw + (8 if j >= 4 else 0)
        row = m[(m.cultivo == cu) & (m.temporada == t_) & (m.franja == f_)].iloc[0]
        val = row.litros_dia
        k = min(int(val / vmax * (len(seq) - 1) + 0.5), len(seq) - 1)
        body += rect(xx + 1, yy + 1, cw - 2, chh - 2, seq[k],
                     f"{cu} · {t_} · {f_}: {fmt(val,2)} L/día ({fmt(row.litros_est,1)} L en total)", 2)
        body += txt(xx + cw / 2, yy + chh / 2 + 4, fmt(val, 1), 11, "#fcfcfb" if k >= 3 else INK, "middle")
ly = H - 28
body += txt(L, ly + 4, "Litros/día:", 11, INK2, "start")
for k, c in enumerate(seq):
    body += f'<rect x="{L+70+k*34}" y="{ly-8}" width="32" height="14" rx="2" fill="{c}"/>'
body += txt(L + 70, ly + 22, "0", 11, MUTED, "start") + txt(L + 70 + 7 * 34, ly + 22, fmt(vmax, 1), 11, MUTED, "end")
(OUT / "m1_cultivo_temporada_franja.svg").write_text(svg(W, H, body, "Mapa de calor litros por día por cultivo, temporada y franja"), encoding="utf-8")

print(json.dumps(R["kpi"], ensure_ascii=False, indent=1))
print("tarde%", R["m1_tarde_pct"], R["m1_franja_pct"])
print(pd.DataFrame(R["m1_cultivo_temporada"]))
print(R["validacion"], R["b4_resumen"], R["b1_resumen"])
