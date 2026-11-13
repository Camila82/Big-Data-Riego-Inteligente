"""Arma index.html insertando los gráficos SVG del análisis y los diagramas."""
from pathlib import Path
import re

BASE = Path(__file__).parent
SVG_DIR = BASE.parent / "analisis" / "salida"
FONT = "font-family:'IBM Plex Sans',system-ui,sans-serif"


def caja(x, y, w, h, titulo, sub, fill="#e4eee7", stroke="#24573f"):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            f'<text x="{x+w/2}" y="{y+h/2-3}" text-anchor="middle" font-size="13" font-weight="600" fill="#14211a">{titulo}</text>'
            f'<text x="{x+w/2}" y="{y+h/2+14}" text-anchor="middle" font-size="11" fill="#4b5a51">{sub}</text>')


def flecha(x1, y1, x2, y2, etiqueta=""):
    s = (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#4b5a51" stroke-width="1.6" marker-end="url(#pt)"/>')
    if etiqueta:
        s += f'<text x="{(x1+x2)/2 + (8 if x1 == x2 else 0)}" y="{(y1+y2)/2 + (4 if x1 == x2 else 18)}" text-anchor="{'start' if x1 == x2 else 'middle'}" font-size="10.5" fill="#7d8a82">{etiqueta}</text>'
    return s


DEFS = ('<defs><marker id="pt" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#4b5a51"/></marker></defs>')

agua = ("#e3eefb", "#2a78d6")
arq = DEFS
arq += caja(10, 20, 150, 56, "Sensores", "FC-28 · DHT11 · RTC")
arq += caja(220, 20, 150, 56, "ESP32 (por lote)", "reglas · cola pendientes")
arq += caja(220, 120, 150, 50, "Relé + bomba DC", "riego del lote", "#fdeee6", "#eb6834")
arq += caja(430, 20, 150, 56, "SQL Server OLTP", "RiegoInteligente (3FN)", *agua)
arq += caja(610, 20, 140, 56, "SSIS (ETL)", "limpieza · cuarentena", *agua)
arq += caja(610, 120, 140, 56, "Data Warehouse", "modelo estrella", *agua)
arq += caja(430, 120, 150, 56, "Power BI", "dashboard publicado", *agua)
arq += caja(220, 210, 150, 50, "Sitio web PGC", "documentación + iframe")
arq += caja(430, 210, 150, 50, "Decisiones", "productor · técnico")
arq += flecha(160, 48, 218, 48, "cada 2 s")
arq += flecha(295, 76, 295, 118, "GPIO 5")
arq += flecha(370, 48, 428, 48, "Wi-Fi")
arq += flecha(580, 48, 608, 48)
arq += flecha(680, 76, 680, 118)
arq += flecha(610, 148, 582, 148)
arq += flecha(470, 176, 330, 208)
arq += flecha(520, 176, 520, 208)
ARQ = (f'<svg viewBox="0 0 760 270" role="img" aria-label="Arquitectura del sistema" '
       f'xmlns="http://www.w3.org/2000/svg" style="{FONT};width:100%;height:auto">{arq}</svg>')


def tabla(x, y, w, nombre, campos, fill="#e4eee7", stroke="#24573f", punteada=False):
    h = 28 + 17 * len(campos) + 8
    dash = ' stroke-dasharray="5 4"' if punteada else ""
    s = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#fff" stroke="{stroke}" stroke-width="1.5"{dash}/>'
         f'<rect x="{x}" y="{y}" width="{w}" height="26" rx="8" fill="{fill}"/>'
         f'<text x="{x+10}" y="{y+18}" font-size="13" font-weight="700" fill="#14211a">{nombre}</text>')
    for i, c in enumerate(campos):
        s += f'<text x="{x+10}" y="{y+44+17*i}" font-size="11" fill="#4b5a51" font-family="IBM Plex Mono,monospace">{c}</text>'
    return s, h


est = ""
s1, h1 = tabla(265, 10, 230, "Dim_Dispositivo", ["sk_dispositivo (PK)", "id_dispositivo_nk", "cultivo · humedad_min/max",
                                                 "lote · tipo_suelo · ubicacion", "finca · vereda · propietario"])
s2, h2 = tabla(30, 190, 220, "Fact_Lectura", ["sk_dispositivo · sk_fecha", "sk_hora · suelo_pct · raw_suelo",
                                              "temperatura_c · humedad_rel_pct", "bomba_on · wifi_ok", "falla_sensor · alerta_logica",
                                              "pendientes"], *agua)
s3, h3 = tabla(510, 190, 220, "Fact_EventoRiego", ["sk_dispositivo · sk_fecha", "sk_hora · inicio · fin", "duracion_seg",
                                                   "suelo_inicio · suelo_fin", "litros_est · motivo_fin"], *agua)
s4, h4 = tabla(150, 390, 200, "Dim_Tiempo", ["sk_fecha (AAAAMMDD)", "mes · nombre_mes · semana", "temporada (Seca/Lluviosa)"])
s5, h5 = tabla(410, 390, 200, "Dim_Hora", ["sk_hora (0–23)", "franja · orden_franja"])
s6, h6 = tabla(560, 40, 190, "Lectura_Cuarentena", ["campos de origen", "motivo_rechazo"], "#fdeee6", "#eb6834", True)
for a, b, c, d in [(330, 10 + h1, 160, 190), (430, 10 + h1, 600, 190), (140, 190 + h2, 220, 390),
                   (180, 190 + h2, 470, 390), (590, 190 + h3, 300, 390), (630, 190 + h3, 530, 390)]:
    est += f'<line x1="{a}" y1="{b}" x2="{c}" y2="{d}" stroke="#9fb0a6" stroke-width="1.4"/>'
est += s1 + s2 + s3 + s4 + s5 + s6
EST = (f'<svg viewBox="0 0 760 {390 + h4 + 10}" role="img" aria-label="Modelo estrella del Data Warehouse" '
       f'xmlns="http://www.w3.org/2000/svg" style="{FONT};width:100%;height:auto">{est}</svg>')

html = (BASE / "plantilla.html").read_text(encoding="utf-8")
html = html.replace("{{arquitectura}}", ARQ).replace("{{estrella}}", EST)


def svg(m):
    return (SVG_DIR / f"{m.group(1)}.svg").read_text(encoding="utf-8")


html = re.sub(r"\{\{svg:([a-z0-9_]+)\}\}", svg, html)
assert "{{" not in html
(BASE / "index.html").write_text(html, encoding="utf-8")
print("index.html", len(html) // 1024, "KB")
