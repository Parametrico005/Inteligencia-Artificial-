---
name: ver-youtube
description: "Ver" un video de YouTube - obtiene título, canal, duración, descripción, capítulos y la transcripción con marcas de tiempo, y opcionalmente fotogramas para analizar lo que se ve en pantalla. Úsala cuando el usuario comparta un enlace de YouTube (youtube.com, youtu.be, shorts) y pida resumirlo, explicarlo, sacar notas, citar partes, responder preguntas sobre el video o describir lo que aparece en él.
---

# Ver videos de YouTube

Claude no puede reproducir video, así que "ver" un video significa:
1. **Escuchar** → leer la transcripción (subtítulos manuales o automáticos).
2. **Mirar** → extraer fotogramas cada N segundos y leerlos como imágenes.

## Requisitos

- `yt-dlp` (se instala solo si falta: `pip install -U yt-dlp`)
- `ffmpeg` (solo para fotogramas)

## Paso 1: transcripción y metadatos (siempre)

```bash
python3 .claude/skills/ver-youtube/scripts/ver_youtube.py "URL" --salida /tmp/yt
```

Opciones útiles:
- `--idiomas es,en` — orden de preferencia de subtítulos (por defecto `es,en`).
- `--sin-tiempos` — transcripción en texto corrido, sin marcas `[mm:ss]`.

Genera en la carpeta de salida:
- `info.md` — título, canal, fecha, duración, vistas, capítulos y descripción.
- `transcripcion.txt` — texto con marcas `[hh:mm:ss]`, sin líneas repetidas.

Lee primero `info.md` y luego `transcripcion.txt` (si es muy largo, léelo por partes).

## Paso 2: fotogramas (solo si hace falta ver la imagen)

Úsalo cuando la pregunta trate de algo visual (diagramas, código en pantalla,
planos, diapositivas) o el video no tenga subtítulos:

```bash
python3 .claude/skills/ver-youtube/scripts/ver_youtube.py "URL" --salida /tmp/yt --fotogramas 30
```

- `--fotogramas N` — un fotograma cada N segundos (descarga el video en baja resolución).
- `--desde 00:05:00 --hasta 00:08:00` — limita a un tramo concreto.
- Los fotogramas quedan en `fotogramas/` con su marca de tiempo en el nombre
  (`f_00-05-30.jpg`). Ábrelos con la herramienta Read para verlos.
- Máximo recomendado: ~40 imágenes por análisis; ajusta N según la duración.

## Cómo responder

- Cita momentos con su marca de tiempo y enlace directo:
  `https://youtu.be/ID?t=SEGUNDOS`.
- Si no hay subtítulos, dilo y ofrece analizar fotogramas.
- Si yt-dlp falla (video privado, con restricción de edad, red bloqueada),
  informa el error tal cual; no inventes el contenido del video.
