#!/usr/bin/env python3
"""Obtiene metadatos, transcripción y (opcional) fotogramas de un video de YouTube."""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys


def asegurar_ytdlp():
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("Instalando yt-dlp...", file=sys.stderr)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"], check=True)
    return [sys.executable, "-m", "yt_dlp"]


def hms(seg):
    seg = int(seg)
    return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"


def a_segundos(t):
    partes = [float(p) for p in t.replace(",", ".").split(":")]
    s = 0.0
    for p in partes:
        s = s * 60 + p
    return s


def escribir_info(info, ruta):
    lineas = [
        f"# {info.get('title', '')}",
        "",
        f"- **Canal:** {info.get('channel') or info.get('uploader', '')}",
        f"- **Fecha:** {info.get('upload_date', '')}",
        f"- **Duración:** {hms(info.get('duration') or 0)}",
        f"- **Vistas:** {info.get('view_count', '')}",
        f"- **URL:** {info.get('webpage_url', '')}",
        f"- **ID:** {info.get('id', '')}",
    ]
    if info.get("chapters"):
        lineas += ["", "## Capítulos", ""]
        lineas += [f"- [{hms(c['start_time'])}] {c['title']}" for c in info["chapters"]]
    lineas += ["", "## Descripción", "", info.get("description") or "(sin descripción)", ""]
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))


def vtt_a_texto(ruta_vtt, con_tiempos=True):
    """Convierte VTT (incluidos los automáticos con texto repetido) en texto limpio."""
    with open(ruta_vtt, encoding="utf-8") as f:
        contenido = f.read()
    bloques = re.split(r"\n\s*\n", contenido)
    salida, previas = [], set()
    for b in bloques:
        m = re.search(r"(\d+:\d+:\d+[.,]\d+|\d+:\d+[.,]\d+)\s*-->", b)
        if not m:
            continue
        inicio = a_segundos(m.group(1))
        for linea in b.split("\n"):
            if "-->" in linea or not linea.strip():
                continue
            texto = re.sub(r"<[^>]+>", "", linea).strip()
            texto = re.sub(r"\s+", " ", texto)
            if not texto or texto in previas:
                continue
            previas.add(texto)
            salida.append(f"[{hms(inicio)}] {texto}" if con_tiempos else texto)
    return "\n".join(salida) if con_tiempos else " ".join(salida)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url")
    ap.add_argument("--salida", default="yt_salida")
    ap.add_argument("--idiomas", default="es,en")
    ap.add_argument("--sin-tiempos", action="store_true")
    ap.add_argument("--fotogramas", type=int, default=0, help="segundos entre fotogramas")
    ap.add_argument("--desde", default=None, help="hh:mm:ss")
    ap.add_argument("--hasta", default=None, help="hh:mm:ss")
    a = ap.parse_args()

    os.makedirs(a.salida, exist_ok=True)
    ytdlp = asegurar_ytdlp()

    # Metadatos
    r = subprocess.run(ytdlp + ["-J", "--no-warnings", "--no-playlist", a.url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Error al leer el video:\n{r.stderr.strip()}")
    info = json.loads(r.stdout)
    escribir_info(info, os.path.join(a.salida, "info.md"))
    print(f"Título: {info.get('title')}  |  Duración: {hms(info.get('duration') or 0)}")

    # Subtítulos: manuales primero, luego automáticos, en orden de idioma
    idiomas = [i.strip() for i in a.idiomas.split(",") if i.strip()]
    manuales = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}

    def buscar(dic):
        for idi in idiomas:
            for k in dic:
                if k == idi or k.startswith(idi + "-"):
                    return k
        return None

    elegido, tipo = buscar(manuales), "manual"
    if not elegido:
        elegido, tipo = buscar(autos), "automático"
    if not elegido and (manuales or autos):
        # Cualquier idioma original disponible
        elegido = next(iter(manuales or autos))
        tipo = "manual" if manuales else "automático"

    ruta_txt = os.path.join(a.salida, "transcripcion.txt")
    if elegido:
        for v in glob.glob(os.path.join(a.salida, "subs*.vtt")):
            os.remove(v)
        flag = "--write-subs" if tipo == "manual" else "--write-auto-subs"
        subprocess.run(ytdlp + ["--skip-download", flag, "--sub-langs", elegido,
                                "--sub-format", "vtt", "--no-warnings", "--no-playlist",
                                "-o", os.path.join(a.salida, "subs.%(ext)s"), a.url],
                       capture_output=True, text=True)
        vtts = glob.glob(os.path.join(a.salida, "subs*.vtt"))
        if vtts:
            texto = vtt_a_texto(vtts[0], not a.sin_tiempos)
            with open(ruta_txt, "w", encoding="utf-8") as f:
                f.write(f"# Subtítulos {tipo} ({elegido})\n\n{texto}\n")
            print(f"Transcripción ({tipo}, {elegido}): {ruta_txt} ({len(texto.split())} palabras)")
        else:
            print("No se pudieron descargar los subtítulos.")
    else:
        print("El video no tiene subtítulos. Usa --fotogramas para analizar la imagen.")

    # Fotogramas
    if a.fotogramas > 0:
        if not shutil.which("ffmpeg"):
            sys.exit("Falta ffmpeg para extraer fotogramas.")
        video = os.path.join(a.salida, "video.mp4")
        cmd = ytdlp + ["-f", "bv*[height<=480][ext=mp4]/bv*[height<=480]/b[height<=480]/b",
                       "--no-warnings", "--no-playlist", "--remux-video", "mp4",
                       "-o", video, "--force-overwrites"]
        if a.desde or a.hasta:
            cmd += ["--download-sections", f"*{a.desde or '0'}-{a.hasta or 'inf'}"]
        r = subprocess.run(cmd + [a.url], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(video):
            sys.exit(f"Error al descargar el video:\n{r.stderr.strip()}")
        dir_f = os.path.join(a.salida, "fotogramas")
        shutil.rmtree(dir_f, ignore_errors=True)
        os.makedirs(dir_f)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", video,
                        "-vf", f"fps=1/{a.fotogramas},scale=768:-2",
                        "-q:v", "4", os.path.join(dir_f, "tmp_%05d.jpg")], check=True)
        base = a_segundos(a.desde) if a.desde else 0
        archivos = sorted(glob.glob(os.path.join(dir_f, "tmp_*.jpg")))
        for i, f in enumerate(archivos):
            t = hms(base + i * a.fotogramas).replace(":", "-")
            os.rename(f, os.path.join(dir_f, f"f_{t}.jpg"))
        os.remove(video)
        print(f"Fotogramas: {len(archivos)} en {dir_f}")

    print(f"Listo. Archivos en: {os.path.abspath(a.salida)}")


if __name__ == "__main__":
    main()
