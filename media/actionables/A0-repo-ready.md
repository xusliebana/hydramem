# A0 — Repo listo para convertir (Fase 0)  ← el 80% del resultado

**Objetivo:** que un visitante entienda el valor y quiera dar ⭐ en <20 segundos.
**Bloquea el lanzamiento hasta completar esto.**

## Por qué importa
Tráfico sin conversión = ⭐ perdidas. El día del Show HN llegarán miles de visitantes
de golpe; si el README no convierte, los pierdes para siempre.

## Pasos (en orden)

1. **GIF demo arriba del README** (lo #1).
   - Ver [A1-assets.md](./A1-assets.md) para cómo grabarlo.
   - Debe mostrar: `hydramem ingest` → `hydramem search` → un agente recordando algo
     entre sesiones. 30–60s, sin audio.

2. **Tagline de 1 línea, sin jerga**, justo bajo el título:
   > *Local, private long-term memory for your AI coding agent — graph+vector, runs on
   > your machine, zero cloud by default.*

3. **Bloque de instalación copiable** que funcione en <2 min:
   ```bash
   uv tool install <repo-url>      # o: pipx install <repo-url>
   hydramem init ~/my-memory
   ```
   - **Pruébalo en una VM/contenedor limpio** antes de lanzar. Si falla, lo arreglas
     ahora, no durante el Show HN.

4. **Tabla comparativa honesta** (genera el PNG en A1):
   | | HydraMem | mem0 | Zep | Letta |
   |---|---|---|---|---|
   | 100% local / zero exfiltration | ✅ | parcial | parcial | parcial |
   | MCP-native | ✅ | — | — | — |
   | Verificación de relaciones (2 etapas) | ✅ | — | — | — |
   | Auditable (`stats --raw`) | ✅ | — | — | — |
   | LOC legibles | ~5k | grande | grande | grande |
   - **Sé justo** con los competidores (no caricaturices). La honestidad es el activo.

5. **Sección "What it does NOT do"** (genera confianza enorme):
   - "No es el primer sistema de memoria, graph-RAG ni filtro de alucinaciones."
   - "El benchmark incluido es un sanity check, no un resultado SOTA."
   - "Sin LLM, VoG reporta `n/a`, nunca un score inventado."

6. **Tabla del benchmark** en el README (real, del repo):
   | Condition | R@1 | R@3 | R@5 | MRR |
   |-----------|-----|-----|-----|-----|
   | vector_only | 0.00 | 0.30 | 0.50 | 0.16 |
   | hybrid_full | 0.30 | 0.70 | 0.80 | 0.52 |
   - Añade la nota: *"sanity benchmark con stub embedder; no es SOTA; el run de
     MuSiQue/LongMemEval está en progreso."*

7. **Higiene del repo:**
   - [ ] LICENSE MIT visible
   - [ ] CONTRIBUTING.md
   - [ ] 3–5 issues etiquetados `good first issue`
   - [ ] Reemplaza el placeholder `github.com/hydramem/hydramem` por la URL real
   - [ ] Badges (license, python, MCP) ya están — verifica que apuntan bien

## Criterio de "hecho"
Un amigo que NO conoce el proyecto lo instala y entiende el valor en 2 minutos sin que
le expliques nada. Si no, sigue puliendo.
