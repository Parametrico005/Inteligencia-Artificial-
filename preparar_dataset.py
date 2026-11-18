"""
Prepara tus planos DWG/DXF como dataset para entrenar un modelo generativo.

    python preparar_dataset.py --entrada mis_planos/ --salida dataset/

Por cada plano produce:
    dataset/imagenes/<nombre>.png   plano rasterizado (512x512, fondo blanco)
    dataset/metadatos.jsonl         una línea por plano: capas, textos
                                    (nombres de ambientes) y medidas generales

Los DWG se convierten a DXF con el ODA File Converter (gratuito):
https://www.opendesign.com/guestfiles/oda_file_converter
Si no está instalado, convierte los DWG a DXF desde AutoCAD (Guardar como -> DXF).
"""

import argparse
import json
import os
import re
from pathlib import Path

import ezdxf
from ezdxf import bbox

CAPAS_IGNORAR = re.compile(r"(cota|dim|mobil|mueble|eje|hatch|achur)", re.I)


def cargar(ruta: Path):
    if ruta.suffix.lower() == ".dwg":
        from ezdxf.addons import odafc
        return odafc.readfile(str(ruta))
    return ezdxf.readfile(str(ruta))


def rasterizar(doc, ruta_png, px=512):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy

    fig = plt.figure(figsize=(px / 100, px / 100))
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(doc)
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE,
                        color_policy=ColorPolicy.BLACK)
    Frontend(ctx, MatplotlibBackend(ax), config=cfg).draw_layout(
        doc.modelspace(),
        # oculta cotas y mobiliario para un dibujo limpio
        filter_func=lambda e: not CAPAS_IGNORAR.search(e.dxf.layer) and e.dxftype() != "DIMENSION",
    )
    ax.set_aspect("equal")
    fig.savefig(ruta_png, dpi=100)
    plt.close(fig)


def metadatos(doc, nombre):
    msp = doc.modelspace()
    textos = []
    for e in msp.query("TEXT MTEXT"):
        t = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
        t = " ".join(t.split())
        if t:
            textos.append(t)
    caja = bbox.extents(msp)
    return {
        "archivo": nombre,
        "capas": sorted(c.dxf.name for c in doc.layers),
        "textos": textos,
        "extension": [round(caja.size.x, 2), round(caja.size.y, 2)] if caja.has_data else None,
        "unidades": doc.units,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True)
    ap.add_argument("--salida", default="dataset")
    ap.add_argument("--px", type=int, default=512)
    a = ap.parse_args()

    img_dir = Path(a.salida) / "imagenes"
    img_dir.mkdir(parents=True, exist_ok=True)
    archivos = [p for p in Path(a.entrada).rglob("*") if p.suffix.lower() in (".dxf", ".dwg")]
    ok = 0
    with open(Path(a.salida) / "metadatos.jsonl", "w", encoding="utf-8") as f:
        for p in archivos:
            try:
                doc = cargar(p)
                rasterizar(doc, img_dir / f"{p.stem}.png", a.px)
                f.write(json.dumps(metadatos(doc, p.name), ensure_ascii=False) + "\n")
                ok += 1
                print("OK   ", p.name)
            except Exception as e:  # un plano dañado no detiene el resto
                print("ERROR", p.name, "->", e)
    print(f"\n{ok}/{len(archivos)} planos procesados en {a.salida}/")


if __name__ == "__main__":
    main()
