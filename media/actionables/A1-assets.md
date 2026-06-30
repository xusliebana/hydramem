# A1 — Crear los assets

Sin assets visuales pierdes la mitad de las ⭐. Prioridad: **GIF > vídeo > tablas**.

## 1. GIF demo (30–60s) — el activo #1
**Qué mostrar:** `ingest` → `search` → recall entre sesiones (lo que diferencia a HydraMem).

**Cómo grabarlo (terminal):**
- Linux: graba la terminal con [`asciinema`](https://asciinema.org) → convierte a GIF con
  [`agg`](https://github.com/asciinema/agg):
  ```bash
  asciinema rec demo.cast
  # ... ejecuta los comandos reales ...
  agg demo.cast demo.gif
  ```
- Alternativa GUI: [`peek`](https://github.com/phw/peek) o [`vhs`](https://github.com/charmbracelet/vhs)
  (vhs permite un script reproducible — recomendado para regrabar limpio).

**Ejemplo de script `vhs` (demo.tape):**
```
Output demo.gif
Set FontSize 18
Set Width 1100
Set Height 640
Type "hydramem ingest ./kms" Enter  Sleep 3s
Type "hydramem search 'what does my doc say about the Night Gardener?'" Enter  Sleep 4s
Type "hydramem stats --raw" Enter  Sleep 3s
```

**Reglas:** sin audio, texto grande y legible, <8 MB para que cargue en el README.

## 2. Vídeo 3–5 min (YouTube)
- Guion completo en [posts/18-youtube-script.md](../posts/18-youtube-script.md).
- Graba pantalla con OBS Studio. Sube a YouTube (no listado primero, luego público).
- Es el activo que mandas a influencers/newsletters.

## 3. Tablas como imagen (para X/PH/LinkedIn)
- La tabla comparativa y la del benchmark también las quieres como PNG.
- Genera PNG desde Markdown con [`carbon.now.sh`](https://carbon.now.sh) (estética code) o
  renderiza una tabla HTML y captura. Mantén fuente grande.

## 4. Logo y banner social
- Logo PNG 240×240 (ya existe SVG en `docs/assets/hydramem-logo.svg` → exporta a PNG).
- Banner social 1200×630 para Open Graph (que el link se vea bien al compartir).
  Añade `og:image` al README/landing si tienes.

## 5. Screenshots
- `hydramem stats` (el panel bonito del README)
- Resultado de `hydramem search`
- Dashboard read-only (`hydramem-dashboard`) si aplica

## Checklist
- [ ] demo.gif (<8 MB) en el README
- [ ] vídeo 3–5 min subido
- [ ] tabla comparativa PNG
- [ ] tabla benchmark PNG
- [ ] logo PNG + banner 1200×630
- [ ] 3 screenshots
