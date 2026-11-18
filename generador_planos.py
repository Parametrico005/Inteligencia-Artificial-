"""
Generador paramétrico de plantas de vivienda -> DXF (abrible en AutoCAD).

Ejemplo:
    python generador_planos.py --dormitorios 3 --banos 2 --area 95 --variantes 4

Genera en la carpeta de salida:
    vivienda_XX.dxf   plano editable (capas MUROS, PUERTAS, VENTANAS, TEXTOS, COTAS)
    vivienda_XX.png   vista previa
    resumen.json      ambientes y superficies de cada variante

Esquema de la planta (una sola planta, rectangular):
    banda posterior : dormitorios + baños
    pasillo         : 1.00 m, recorre todo el ancho
    banda frontal   : estar-comedor + cocina (acceso por la fachada)

Las propuestas son anteproyectos: deben ser revisadas por un profesional
(normativa local, estructura, instalaciones).
"""

import argparse
import json
import math
import os
import random
from dataclasses import dataclass, field

import ezdxf
from ezdxf.enums import TextEntityAlignment

# ---------------------------------------------------------------- parámetros
MURO_EXT = 0.20   # espesor muro exterior (m)
MURO_INT = 0.10   # espesor tabique interior (m)
PASILLO = 1.00

ANCHO_MIN = {"dorm_principal": 3.2, "dormitorio": 2.8, "bano": 1.8,
             "cocina": 2.6, "estar": 3.6}
PESO = {"dorm_principal": 1.25, "dormitorio": 1.0, "bano": 0.45,
        "cocina": 0.7, "estar": 1.3}
NOMBRE = {"dorm_principal": "DORMITORIO PRINCIPAL", "dormitorio": "DORMITORIO",
          "bano": "BAÑO", "cocina": "COCINA", "estar": "ESTAR-COMEDOR",
          "pasillo": "PASILLO"}


@dataclass
class Ambiente:
    tipo: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def ancho(self):
        return self.x1 - self.x0

    @property
    def fondo(self):
        return self.y1 - self.y0

    @property
    def area_util(self):
        return max(self.ancho - MURO_INT, 0) * max(self.fondo - MURO_INT, 0)


@dataclass
class Abertura:
    tipo: str          # "puerta" | "ventana" | "vano"
    x0: float
    x1: float
    abre_hacia: int = 1  # +1 hacia +y, -1 hacia -y (solo puertas)


@dataclass
class Muro:            # muros horizontales o verticales sobre su eje
    a: tuple
    b: tuple
    espesor: float
    aberturas: list = field(default_factory=list)


@dataclass
class Planta:
    ancho: float
    fondo: float
    ambientes: list
    muros: list
    puntaje: float = 0.0

    @property
    def area_construida(self):
        return (self.ancho + MURO_EXT) * (self.fondo + MURO_EXT)


# ---------------------------------------------------------------- distribución
def repartir(tipos, total, rnd):
    """Reparte un ancho total respetando mínimos y pesos (con variación)."""
    mins = [ANCHO_MIN[t] for t in tipos]
    pesos = [PESO[t] * rnd.uniform(0.85, 1.15) for t in tipos]
    sobra = max(total - sum(mins), 0)
    return [m + sobra * p / sum(pesos) for m, p in zip(mins, pesos)]


def generar_variante(dormitorios, banos, area_obj, ancho_max, rnd):
    # orden de la banda posterior: principal en un extremo, baño junto a él
    otros = ["dormitorio"] * (dormitorios - 1)
    banos_l = ["bano"] * banos
    posterior = ["dorm_principal"]
    if banos >= 2:
        posterior.append(banos_l.pop())        # baño en suite
    resto = otros + banos_l
    rnd.shuffle(resto)
    posterior += resto
    if rnd.random() < 0.5:
        posterior.reverse()

    frontal = ["estar", "cocina"] if rnd.random() < 0.5 else ["cocina", "estar"]

    # dimensiones generales
    f_frontal = rnd.uniform(3.6, 4.4)
    f_posterior = rnd.uniform(3.3, 3.9)
    fondo = f_frontal + PASILLO + f_posterior
    ancho_min = max(sum(ANCHO_MIN[t] for t in posterior),
                    sum(ANCHO_MIN[t] for t in frontal))
    ancho = max(area_obj / fondo, ancho_min)
    if ancho_max and ancho > ancho_max:
        return None
    # si queda muy alargada, se gana fondo
    if ancho / fondo > 2.4:
        extra = (area_obj / (2.4 * fondo) - 1) * fondo if area_obj / fondo > ancho_min else 0
        f_frontal += extra * 0.5
        f_posterior += extra * 0.5
        fondo = f_frontal + PASILLO + f_posterior
        ancho = max(area_obj / fondo, ancho_min)

    yf = f_frontal
    yc = f_frontal + PASILLO
    amb = []

    # banda frontal
    x = 0
    for t, w in zip(frontal, repartir(frontal, ancho, rnd)):
        amb.append(Ambiente(t, x, 0, x + w, yf))
        x += w
    # pasillo
    amb.append(Ambiente("pasillo", 0, yf, ancho, yc))
    # banda posterior
    x = 0
    for t, w in zip(posterior, repartir(posterior, ancho, rnd)):
        amb.append(Ambiente(t, x, yc, x + w, fondo))
        x += w

    muros = construir_muros(amb, ancho, fondo, yf, yc)
    p = Planta(ancho, fondo, amb, muros)
    p.puntaje = puntuar(p, area_obj)
    return p


def construir_muros(amb, W, D, yf, yc):
    front = [a for a in amb if a.y0 == 0]
    back = [a for a in amb if a.y0 == yc]
    m_front = Muro((0, 0), (W, 0), MURO_EXT)
    m_back = Muro((0, D), (W, D), MURO_EXT)
    m_izq = Muro((0, 0), (0, D), MURO_EXT)
    m_der = Muro((W, 0), (W, D), MURO_EXT)
    m_yf = Muro((0, yf), (W, yf), MURO_INT)
    m_yc = Muro((0, yc), (W, yc), MURO_INT)
    muros = [m_front, m_back, m_izq, m_der, m_yf, m_yc]

    # tabiques verticales entre ambientes de cada banda
    for banda, y0, y1 in ((front, 0, yf), (back, yc, D)):
        for a in banda[:-1]:
            muros.append(Muro((a.x1, y0), (a.x1, y1), MURO_INT))

    # aberturas banda frontal
    for a in front:
        if a.tipo == "estar":
            pd = a.x0 + 0.35 if a.x0 == 0 else a.x1 - 1.25
            m_front.aberturas.append(Abertura("puerta", pd, pd + 0.90, +1))
            libre = (a.x0 + 1.6, a.x1 - 0.4) if a.x0 == 0 else (a.x0 + 0.4, a.x1 - 1.6)
            wv = min(2.0, libre[1] - libre[0])
            c = (libre[0] + libre[1]) / 2
            m_front.aberturas.append(Abertura("ventana", c - wv / 2, c + wv / 2))
            c = (a.x0 + a.x1) / 2
            m_yf.aberturas.append(Abertura("vano", c - 0.75, c + 0.75))
        else:  # cocina
            c = (a.x0 + a.x1) / 2
            m_front.aberturas.append(Abertura("ventana", c - 0.6, c + 0.6))
            pd = a.x0 + 0.2 if a.x0 > 0 else a.x1 - 1.0
            m_yf.aberturas.append(Abertura("puerta", pd, pd + 0.80, -1))

    # aberturas banda posterior
    for a in back:
        bano = a.tipo == "bano"
        wp = 0.70 if bano else 0.80
        m_yc.aberturas.append(Abertura("puerta", a.x0 + 0.15, a.x0 + 0.15 + wp, +1))
        wv = 0.60 if bano else min(1.6, a.ancho - 0.8)
        c = (a.x0 + a.x1) / 2
        m_back.aberturas.append(Abertura("ventana", c - wv / 2, c + wv / 2))
    return muros


def puntuar(p, area_obj):
    s = -abs(p.area_construida - area_obj) * 0.5
    for a in p.ambientes:
        if a.tipo == "pasillo":
            continue
        prop = max(a.ancho, a.fondo) / min(a.ancho, a.fondo)
        s -= max(prop - 1.6, 0) * 3          # penaliza ambientes muy alargados
    return round(s, 2)


# ---------------------------------------------------------------- DXF
def preparar_doc():
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.M
    doc.header["$INSUNITS"] = 6
    for nombre, color in (("MUROS", 7), ("PUERTAS", 3), ("VENTANAS", 4),
                          ("TEXTOS", 2), ("COTAS", 1)):
        doc.layers.add(nombre, color=color)
    ds = doc.dimstyles.get("EZDXF")
    ds.dxf.dimtxt = 0.18
    ds.dxf.dimasz = 0.12
    ds.dxf.dimexe = 0.08
    ds.dxf.dimexo = 0.05
    ds.dxf.dimdec = 2
    ds.dxf.dimlfac = 1   # cotas en metros
    return doc


def rect(msp, x0, y0, x1, y1, capa, relleno=False):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": capa})
    if relleno:
        h = msp.add_hatch(color=8, dxfattribs={"layer": capa})
        h.paths.add_polyline_path(pts, is_closed=True)


def dibujar_muro(msp, m):
    (ax, ay), (bx, by) = m.a, m.b
    t = m.espesor / 2
    ext = MURO_EXT / 2  # prolonga para cerrar esquinas y encuentros
    if ay == by:  # horizontal
        cortes = sorted((o.x0, o.x1) for o in m.aberturas)
        x = ax - ext
        for c0, c1 in cortes + [(bx + ext, bx + ext)]:
            if c0 > x:
                rect(msp, x, ay - t, c0, ay + t, "MUROS", relleno=True)
            x = c1
        for o in m.aberturas:
            if o.tipo == "puerta":
                w = o.x1 - o.x0
                s = o.abre_hacia
                yb = ay + s * t
                msp.add_line((o.x0, yb), (o.x0, yb + s * w), dxfattribs={"layer": "PUERTAS"})
                a0, a1 = (0, 90) if s > 0 else (270, 360)
                msp.add_arc((o.x0, yb), w, a0, a1, dxfattribs={"layer": "PUERTAS"})
            elif o.tipo == "ventana":
                for dy in (-t, 0, t):
                    msp.add_line((o.x0, ay + dy), (o.x1, ay + dy), dxfattribs={"layer": "VENTANAS"})
                for xx in (o.x0, o.x1):
                    msp.add_line((xx, ay - t), (xx, ay + t), dxfattribs={"layer": "VENTANAS"})
    else:  # vertical (sin aberturas en este esquema)
        y0, y1 = (ay - ext, by + ext) if m.espesor == MURO_EXT else (ay, by)
        rect(msp, ax - t, y0, ax + t, y1, "MUROS", relleno=True)


def cota(msp, p1, p2, base, angulo):
    msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angulo,
                       dimstyle="EZDXF", dxfattribs={"layer": "COTAS"}).render()


def exportar(p, ruta_dxf, titulo):
    doc = preparar_doc()
    msp = doc.modelspace()
    for m in p.muros:
        dibujar_muro(msp, m)

    for a in p.ambientes:
        cx, cy = (a.x0 + a.x1) / 2, (a.y0 + a.y1) / 2
        txt = NOMBRE[a.tipo] if a.tipo == "pasillo" else f"{NOMBRE[a.tipo]}\\P{a.area_util:.2f} m²"
        alto = 0.13 if a.ancho < 2.5 else 0.18
        mt = msp.add_mtext(txt, dxfattribs={"layer": "TEXTOS", "char_height": alto})
        mt.set_location((cx, cy + (0 if a.tipo == "pasillo" else 0.5)),
                        attachment_point=ezdxf.enums.MTextEntityAlignment.MIDDLE_CENTER)

    W, D = p.ancho, p.fondo
    e = MURO_EXT / 2
    cota(msp, (-e, -e), (W + e, -e), (0, -1.3), 0)
    cota(msp, (-e, -e), (-e, D + e), (-1.3, 0), 90)
    back = sorted((a for a in p.ambientes if a.y1 == D), key=lambda a: a.x0)
    for a in back:
        cota(msp, (a.x0, D + e), (a.x1, D + e), (0, D + 0.9), 0)
    front = sorted((a for a in p.ambientes if a.y0 == 0), key=lambda a: a.x0)
    for a in front:
        cota(msp, (a.x0, -e), (a.x1, -e), (0, -0.7), 0)

    msp.add_text(titulo, height=0.3, dxfattribs={"layer": "TEXTOS"}).set_placement(
        (-e, -2.2), align=TextEntityAlignment.LEFT)
    msp.add_text(f"Sup. construida: {p.area_construida:.2f} m²", height=0.2,
                 dxfattribs={"layer": "TEXTOS"}).set_placement((-e, -2.6))
    doc.saveas(ruta_dxf)
    return doc


def vista_previa(doc, ruta_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_axes([0, 0, 1, 1])
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE,
                        color_policy=ColorPolicy.BLACK)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(doc.modelspace())
    fig.savefig(ruta_png, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Genera plantas de vivienda en DXF")
    ap.add_argument("--dormitorios", type=int, default=3)
    ap.add_argument("--banos", type=int, default=2)
    ap.add_argument("--area", type=float, default=90, help="m² construidos objetivo")
    ap.add_argument("--ancho-max", type=float, default=None, help="frente máximo del terreno (m)")
    ap.add_argument("--variantes", type=int, default=4)
    ap.add_argument("--semilla", type=int, default=None)
    ap.add_argument("--salida", default="salida")
    ap.add_argument("--sin-png", action="store_true")
    a = ap.parse_args()

    if a.dormitorios < 1 or a.banos < 1:
        ap.error("se necesita al menos 1 dormitorio y 1 baño")

    rnd = random.Random(a.semilla)
    candidatos = []
    for _ in range(a.variantes * 25):
        p = generar_variante(a.dormitorios, a.banos, a.area, a.ancho_max, rnd)
        if p:
            candidatos.append(p)
    if not candidatos:
        raise SystemExit("No hay solución con ese ancho máximo: aumente --ancho-max o reduzca ambientes.")
    candidatos.sort(key=lambda p: p.puntaje, reverse=True)

    os.makedirs(a.salida, exist_ok=True)
    resumen = []
    for i, p in enumerate(candidatos[:a.variantes], 1):
        base = os.path.join(a.salida, f"vivienda_{i:02d}")
        titulo = f"VIVIENDA {a.dormitorios}D/{a.banos}B - VARIANTE {i}"
        doc = exportar(p, base + ".dxf", titulo)
        if not a.sin_png:
            vista_previa(doc, base + ".png")
        resumen.append({
            "archivo": base + ".dxf",
            "ancho_m": round(p.ancho + MURO_EXT, 2),
            "fondo_m": round(p.fondo + MURO_EXT, 2),
            "superficie_construida_m2": round(p.area_construida, 2),
            "puntaje": p.puntaje,
            "ambientes": [{"tipo": NOMBRE[x.tipo], "ancho": round(x.ancho, 2),
                           "fondo": round(x.fondo, 2), "area_util_m2": round(x.area_util, 2)}
                          for x in p.ambientes],
        })
        print(f"{base}.dxf  {p.ancho + MURO_EXT:.2f} x {p.fondo + MURO_EXT:.2f} m  "
              f"= {p.area_construida:.1f} m²")
    with open(os.path.join(a.salida, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
