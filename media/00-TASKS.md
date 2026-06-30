# HydraMem — Plan de 5.000 ⭐ en 60 días (LISTA DE TAREAS)

> **Cómo usar este archivo:** es el hub. Cada tarea tiene un `[ ]` que marcas al
> completarla y un enlace a su **accionable** (el "cómo" detallado) y/o al **post**
> listo para pegar. Trabaja una fase a la vez.

- Estrategia completa de referencia: este archivo.
- Targets + mensajes en frío: [01-RESEARCH-outreach.md](./01-RESEARCH-outreach.md)
- Cómo hacer cada cosa: [actionables/](./actionables/)
- Contenido listo para pegar: [posts/](./posts/)

---

## Encuadre honesto (léelo antes de empezar)

5.000 ⭐ en 2 meses es un objetivo **stretch**. Requiere que coincidan: (1) un Show HN
en portada, (2) un hit en r/LocalLLaMA, (3) ≥1 pickup de newsletter/influencer. Base
realista sin esas alineaciones: **1.000–2.500 ⭐**. Este plan maximiza la probabilidad.

### 5 ángulos de venta (del repo, sin hype)
1. "La alternativa **local y privada** a mem0/Zep" — zero exfiltration.
2. **MCP-native** — Claude Desktop / Cursor / OpenCode.
3. **Honestidad/auditable** — `hydramem stats --raw`; "cero relaciones sin evidencia".
4. **Pequeño y legible** — ~5k LOC, se lee en una tarde. No es caja negra.
5. **ROI** — ~70% ahorro de tokens vs RAG naive (auditable).

### Números reales que SÍ puedes usar (honesty contract)
- ~5k LOC · 18 herramientas MCP · MIT · Python 3.11–3.13
- ~70% ahorro de tokens (auditable, no garantizado)
- Verificación en 2 etapas: SR-MKG (topológico) + VoG (groundedness)
- Benchmark sanity reproducible: hybrid_full MRR **0.52** vs vector_only **0.16**
  (con stub embedder — es un sanity check, **NO** un resultado SOTA)
- Night Gardener (inferencia/poda offline)
- ❌ NO uses cifras inventadas de LongMemEval/MuSiQue hasta tener corridas reales.

---

## FASE 0 — El repo debe convertir (semana 0)  ← 80% del resultado
> Accionable: [actionables/A0-repo-ready.md](./actionables/A0-repo-ready.md) · [actionables/A1-assets.md](./actionables/A1-assets.md)

- [ ] GIF/vídeo 30–60s arriba del README (ingest → search → recall entre sesiones)
- [ ] Tagline de 1 línea sin jerga
- [ ] `uv tool install` / `pip install` probado en VM limpia (<2 min)
- [ ] Tabla comparativa honesta vs mem0 / Zep / Letta
- [ ] Sección "What it does NOT do"
- [ ] Tabla del benchmark visible en el README
- [ ] LICENSE MIT + CONTRIBUTING + 3–5 "good first issue"
- [ ] Reemplazar placeholder `github.com/hydramem/hydramem` por el repo real
- [ ] Assets listos (ver [actionables/A1-assets.md](./actionables/A1-assets.md))

## FASE 1 — Soft launch / semilla (semana 1)
> Accionable: [actionables/A2-soft-launch.md](./actionables/A2-soft-launch.md)

- [ ] 15–30 amigos/colegas dan ⭐ genuina (objetivo ~50–100 ⭐ base) — NUNCA bots
- [ ] Post técnico en Dev.to/Hashnode/Medium → [posts/14-devto-technical-blog.md](./posts/14-devto-technical-blog.md)
- [ ] PRs a 3–4 listas awesome → [posts/20-awesome-list-pr.md](./posts/20-awesome-list-pr.md)
- [ ] Publicar en directorios MCP (glama, registro oficial) → [actionables/A8-directories.md](./actionables/A8-directories.md)

## FASE 2 — Lanzamiento grande (semanas 3–4)
> Accionables: [A3-hacker-news](./actionables/A3-hacker-news.md) · [A4-reddit](./actionables/A4-reddit.md) · [A5-producthunt](./actionables/A5-producthunt.md)

- [ ] **Show HN** (mar–jue 9–11am ET) → [posts/01-hackernews-show-hn.md](./posts/01-hackernews-show-hn.md)
- [ ] Hilo de Twitter el mismo día → [posts/07-twitter-launch-thread.md](./posts/07-twitter-launch-thread.md)
- [ ] **r/LocalLLaMA** → [posts/02-reddit-localllama.md](./posts/02-reddit-localllama.md)
- [ ] **r/mcp** → [posts/03-reddit-mcp.md](./posts/03-reddit-mcp.md)
- [ ] **Product Hunt** (día distinto) → [posts/15-producthunt.md](./posts/15-producthunt.md)
- [ ] Submit a 3 newsletters → [actionables/A7-cold-outreach.md](./actionables/A7-cold-outreach.md)

## FASE 3 — Amplificación (semanas 5–8)
> Accionables: [A6-social-cadence](./actionables/A6-social-cadence.md) · [A7-cold-outreach](./actionables/A7-cold-outreach.md)

- [ ] Cold outreach a 20–30 micro-influencers/newsletters → [posts/+ templates](./01-RESEARCH-outreach.md)
- [ ] Subreddits escalonados: r/selfhosted, r/ChatGPTCoding, r/MachineLearning, r/Python
  → [posts/04..06](./posts/)
- [ ] Build-in-public en X (2–3/sem) → [posts/08](./posts/08-twitter-buildinpublic-honesty.md), [09](./posts/09-twitter-benchmark.md), [11](./posts/11-twitter-vs-mem0-zep.md)
- [ ] Reply-marketing en X → [posts/10-twitter-reply-marketing.md](./posts/10-twitter-reply-marketing.md)
- [ ] LinkedIn (lanzamiento + privacidad) → [posts/12](./posts/12-linkedin-launch.md), [13](./posts/13-linkedin-enterprise-privacy.md)
- [ ] Vídeo YouTube 3–5 min → [posts/18-youtube-script.md](./posts/18-youtube-script.md)
- [ ] Intro en Discords (Ollama, MCP) → [posts/19-discord-communities-intro.md](./posts/19-discord-communities-intro.md)
- [ ] Lobsters + Indie Hackers → [posts/16](./posts/16-lobsters.md), [17](./posts/17-indiehackers.md)
- [ ] Pickups Tier 1/2 (post-tracción) → [01-RESEARCH-outreach.md](./01-RESEARCH-outreach.md)

## CONTINUO — Métricas y disciplina
> Accionable: [actionables/A9-metrics-and-pitfalls.md](./actionables/A9-metrics-and-pitfalls.md)

- [ ] Revisar GitHub Insights → Traffic a diario; anotar ⭐/día y fuente
- [ ] Duplicar el canal que mejor convierta
- [ ] Responder TODOS los comentarios el día de cada lanzamiento
- [ ] Actualizar CHANGELOG y atender PRs/issues

### ❌ Qué EVITAR (puede costar el repo)
- Comprar ⭐ / bots → viola ToS de GitHub, se detecta, mata credibilidad.
- Spamear el mismo post en 10 subs el mismo día.
- Outreach genérico sin personalizar.
- Sobre-prometer lo que el repo dice honestamente que no hace.

---

## Calendario resumido
| Sem | Foco | Accionable |
|-----|------|------------|
| 0 | Repo listo | A0, A1 |
| 1 | Soft launch | A2, A8 |
| 2 | Preparar assets/pitch + grabar vídeo | A1, A6 |
| 3 | Show HN + hilo X | A3, A6 |
| 4 | r/LocalLLaMA + r/mcp + Product Hunt + newsletters | A4, A5, A7 |
| 5 | Cold outreach (20–30) | A7 |
| 6 | Subreddits escalonados + build-in-public | A4, A6 |
| 7 | Pickups Tier 1/2 + 2º post técnico | A7 |
| 8 | Consolidar + responder comunidad | A9 |
