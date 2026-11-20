# Generador de planos de vivienda (DXF)

## 1. Generar plantas (funciona ya, sin GPU)

```bash
pip install -r requirements.txt
python generador_planos.py --dormitorios 3 --banos 2 --area 95 --variantes 4
```

| Opción | Qué hace |
|---|---|
| `--dormitorios N` | cantidad de dormitorios (uno es el principal) |
| `--banos N` | cantidad de baños (con 2 o más, uno queda junto al principal) |
| `--area M2` | superficie construida objetivo |
| `--ancho-max M` | frente máximo del terreno |
| `--variantes N` | cuántas propuestas generar (se eligen las mejores) |
| `--semilla N` | repite exactamente el mismo resultado |
| `--salida CARPETA` | dónde guardar (por defecto `salida/`) |

Salida: un `.dxf` por variante, con las capas `MUROS`, `PUERTAS`,
`VENTANAS`, `TEXTOS` y `COTAS`, en metros. También se guarda un `.png` de
vista previa y un `resumen.json` con todos los ambientes y sus superficies.

Hay ejemplos en `ejemplos/`.

Medidas mínimas que respeta: dormitorio principal 3.20 m, dormitorio 2.80 m,
baño 1.80 m, cocina 2.60 m, estar 3.60 m, pasillo 1.00 m. Muros exteriores de
0.20 m y tabiques de 0.10 m. Se pueden cambiar al principio de
`generador_planos.py`.

> Son anteproyectos. Siempre hay que verificarlos con la normativa local y
> que los revise un profesional.

## 2. Buscar plantas reales en el dataset ResPlan (17.000 viviendas)

[ResPlan](https://github.com/m-agour/ResPlan) es un dataset de 17.000
plantas de vivienda reales en formato vectorial, con licencia CC BY 4.0
(hay que citar a la fuente si se publica).

```bash
bash descargar_resplan.sh          # una sola vez: ~100 MB, o 260 MB descomprimido
python resplan_a_dxf.py --dormitorios 3 --banos 2 --area-min 90 --area-max 110 --cantidad 5
python resplan_a_dxf.py --dormitorios 2 --banos 1 --con cochera jardin
python resplan_a_dxf.py --catalogo  # CSV con las 17.000 plantas para filtrar en Excel
python resplan_a_dxf.py --id 7947 12115   # exportar plantas concretas
```

Cada plano se exporta a DXF en metros, con una capa por tipo de ambiente
(`A-DORMITORIOS`, `A-BANOS`, `A-COCINA`...) además de `MUROS`, `PUERTAS`,
`VENTANAS` y `TEXTOS`, y con la superficie de cada ambiente. El catálogo
completo está en `ejemplos/resplan/catalogo.csv`.

Nota: en ResPlan el número de "baños" incluye los toilettes.

## 3. Preparar tus planos para entrenar IA

```bash
python preparar_dataset.py --entrada mis_planos/ --salida dataset/
```

Lee todos los `.dxf` y `.dwg` de la carpeta y genera:

- `dataset/imagenes/*.png`: los planos limpios, sin cotas ni mobiliario.
- `dataset/metadatos.jsonl`: los textos de los ambientes y las medidas generales.

Para leer DWG directamente hay que instalar el
[ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter),
que es gratuito. La otra opción es exportarlos a DXF desde AutoCAD.

El siguiente paso es entrenar el modelo generativo con este dataset en una
máquina con GPU (Colab, Kaggle o Google Cloud).

## Skill de Claude: ver videos de YouTube

En `.claude/skills/ver-youtube/` hay una skill para Claude Code que obtiene
metadatos, transcripción con marcas de tiempo y fotogramas de un video de
YouTube para resumirlo o analizarlo. Requiere `yt-dlp` y `ffmpeg`.

```bash
python3 .claude/skills/ver-youtube/scripts/ver_youtube.py "https://youtu.be/ID" --salida yt --fotogramas 30
```
