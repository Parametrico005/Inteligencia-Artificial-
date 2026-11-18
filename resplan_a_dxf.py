"""
Busca plantas reales en el dataset ResPlan (17.000 viviendas) y las exporta a DXF.

Descarga del dataset (una sola vez, ~100 MB):
    bash descargar_resplan.sh

Ejemplos:
    # 5 plantas de 3 dormitorios, 2 baños, entre 90 y 110 m²
    python resplan_a_dxf.py --dormitorios 3 --banos 2 --area-min 90 --area-max 110 --cantidad 5

    # catálogo CSV con las 17.000 plantas (para filtrar en Excel)
    python resplan_a_dxf.py --catalogo

Dataset: ResPlan, Abouagour & Garyfallidis (2025), licencia CC BY 4.0
https://github.com/m-agour/ResPlan  - hay que citarlo si se publica.
"""

import argparse
import csv
import math
import os
import pickle
import random

import ezdxf
from ezdxf.enums import MTextEntityAlignment

RUTA_PKL = os.path.join("datos", "ResPlan", "ResPlan.pkl")

# El pickle solo contiene geometrías shapely y escalares numpy. Se carga con un
# lector restringido: cualquier otra clase se rechaza (un pickle puede ejecutar código).
PERMITIDOS = {("shapely.io", "from_wkb"), ("numpy._core.multiarray", "scalar"),
              ("numpy", "dtype"), ("numpy.core.multiarray", "scalar")}


class LectorSeguro(pickle.Unpickler):
    def find_class(self, modulo, nombre):
        if (modulo, nombre) not in PERMITIDOS:
            raise pickle.UnpicklingError(f"clase no permitida en el pickle: {modulo}.{nombre}")
        return super().find_class(modulo, nombre)


def cargar(ruta=RUTA_PKL):
    if not os.path.exists(ruta):
        raise SystemExit(f"No se encuentra {ruta}. Ejecute primero: bash descargar_resplan.sh")
    with open(ruta, "rb") as f:
        return LectorSeguro(f).load()


# categoría ResPlan -> (capa DXF, color ACI, nombre en el plano)
AMBIENTES = {
    "living":   ("A-ESTAR", 3, "ESTAR-COMEDOR"),
    "kitchen":  ("A-COCINA", 30, "COCINA"),
    "bedroom":  ("A-DORMITORIOS", 5, "DORMITORIO"),
    "bathroom": ("A-BANOS", 4, "BAÑO"),
    "storage":  ("A-DEPOSITO", 8, "DEPÓSITO"),
    "balcony":  ("A-BALCON", 6, "BALCÓN"),
    "stair":    ("A-ESCALERA", 8, "ESCALERA"),
    "parking":  ("A-COCHERA", 9, "COCHERA"),
    "pool":     ("A-PILETA", 150, "PILETA"),
    "garden":   ("A-JARDIN", 94, "JARDÍN"),
}


def poligonos(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [x for x in getattr(g, "geoms", []) if x.geom_type == "Polygon" and not x.is_empty]


def contar(plan, clave):
    return len(poligonos(plan.get(clave)))


def escala(plan):
    """metros por unidad: el pickle está en un lienzo de 256 unidades;
    'area' es la superficie interior real en m²."""
    interior = plan["inner"].area
    return math.sqrt(plan["area"] / interior) if interior > 0 else 0.05


def ficha(plan):
    return {
        "id": plan["id"],
        "dormitorios": contar(plan, "bedroom"),
        "banos": contar(plan, "bathroom"),
        "area_m2": round(float(plan["area"]), 1),
        "balcon": contar(plan, "balcony") > 0,
        "cochera": contar(plan, "parking") > 0,
        "jardin": contar(plan, "garden") > 0,
        "pileta": contar(plan, "pool") > 0,
        "escalera": contar(plan, "stair") > 0,
    }


# ---------------------------------------------------------------- DXF
def exportar(plan, ruta_dxf):
    s = escala(plan)
    x0, y0, _, y1 = plan["inner"].bounds
    # metros, origen abajo-izquierda, eje Y hacia arriba (el lienzo tiene Y hacia abajo)
    tr = lambda x, y: ((x - x0) * s, (y1 - y) * s)

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.M
    for capa, color in (("MUROS", 7), ("PUERTAS", 3), ("VENTANAS", 4), ("TEXTOS", 7)):
        doc.layers.add(capa, color=color)
    for capa, color, _ in AMBIENTES.values():
        doc.layers.add(capa, color=color)
    msp = doc.modelspace()

    def anillo(coords):
        return [tr(x, y) for x, y in coords]

    def poli(p, capa, relleno=None):
        ext = anillo(p.exterior.coords)
        msp.add_lwpolyline(ext, close=True, dxfattribs={"layer": capa})
        for hueco in p.interiors:
            msp.add_lwpolyline(anillo(hueco.coords), close=True, dxfattribs={"layer": capa})
        if relleno is not None:
            h = msp.add_hatch(color=relleno, dxfattribs={"layer": capa})
            h.paths.add_polyline_path(ext, is_closed=True, flags=1)
            for hueco in p.interiors:
                h.paths.add_polyline_path(anillo(hueco.coords), is_closed=True, flags=16)

    for clave, (capa, _, nombre) in AMBIENTES.items():
        for i, p in enumerate(poligonos(plan.get(clave)), 1):
            poli(p, capa)
            area = p.area * s * s
            if area < 1.0:
                continue
            c = p.representative_point()
            etiqueta = f"{nombre} {i}" if clave == "bedroom" and contar(plan, clave) > 1 else nombre
            mt = msp.add_mtext(f"{etiqueta}\\P{area:.2f} m²",
                               dxfattribs={"layer": "TEXTOS", "char_height": 0.15})
            mt.set_location(tr(c.x, c.y), attachment_point=MTextEntityAlignment.MIDDLE_CENTER)

    for p in poligonos(plan.get("wall")):
        poli(p, "MUROS", relleno=8)
    for p in poligonos(plan.get("window")):
        poli(p, "VENTANAS")
    for p in poligonos(plan.get("door")) + poligonos(plan.get("front_door")):
        poli(p, "PUERTAS")

    f = ficha(plan)
    msp.add_text(f"RESPLAN #{f['id']} - {f['dormitorios']}D/{f['banos']}B - {f['area_m2']} m²",
                 height=0.3, dxfattribs={"layer": "TEXTOS"}).set_placement((0, -1.0))
    msp.add_text("Fuente: ResPlan (CC BY 4.0)", height=0.15,
                 dxfattribs={"layer": "TEXTOS"}).set_placement((0, -1.4))
    doc.saveas(ruta_dxf)
    return doc


def vista_previa(doc, ruta_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy

    fig = plt.figure(figsize=(9, 9))
    ax = fig.add_axes([0, 0, 1, 1])
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(doc.modelspace())
    fig.savefig(ruta_png, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Plantas reales de ResPlan -> DXF")
    ap.add_argument("--dormitorios", type=int)
    ap.add_argument("--banos", type=int)
    ap.add_argument("--area-min", type=float, default=0)
    ap.add_argument("--area-max", type=float, default=1e9)
    ap.add_argument("--con", nargs="*", default=[],
                    choices=["balcon", "cochera", "jardin", "pileta", "escalera"])
    ap.add_argument("--id", type=int, nargs="*", help="exportar planos concretos por id")
    ap.add_argument("--cantidad", type=int, default=5)
    ap.add_argument("--semilla", type=int, default=None)
    ap.add_argument("--salida", default="salida_resplan")
    ap.add_argument("--catalogo", action="store_true", help="solo escribe catalogo.csv")
    ap.add_argument("--sin-png", action="store_true")
    ap.add_argument("--pkl", default=RUTA_PKL)
    a = ap.parse_args()

    datos = cargar(a.pkl)
    os.makedirs(a.salida, exist_ok=True)

    if a.catalogo:
        ruta = os.path.join(a.salida, "catalogo.csv")
        fichas = [ficha(p) for p in datos]
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(fichas[0]))
            w.writeheader()
            w.writerows(fichas)
        print(f"{len(fichas)} plantas en {ruta}")
        return

    if a.id:
        ids = set(a.id)
        elegidos = [p for p in datos if p["id"] in ids]
    else:
        elegidos = []
        for p in datos:
            f = ficha(p)
            if a.dormitorios is not None and f["dormitorios"] != a.dormitorios:
                continue
            if a.banos is not None and f["banos"] != a.banos:
                continue
            if not (a.area_min <= f["area_m2"] <= a.area_max):
                continue
            if not all(f[c] for c in a.con):
                continue
            elegidos.append(p)
        print(f"{len(elegidos)} plantas cumplen los criterios")
        random.Random(a.semilla).shuffle(elegidos)
        elegidos = elegidos[:a.cantidad]

    for p in elegidos:
        f = ficha(p)
        base = os.path.join(a.salida, f"resplan_{f['id']}")
        doc = exportar(p, base + ".dxf")
        if not a.sin_png:
            vista_previa(doc, base + ".png")
        print(f"{base}.dxf  {f['dormitorios']}D/{f['banos']}B  {f['area_m2']} m²")


if __name__ == "__main__":
    main()
