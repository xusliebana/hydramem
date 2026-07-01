# Guía completa de uso — HydraMem

Esta guía documenta todos los comandos CLI, cómo configurar y usar las Agent Skills,
cómo funciona la compactación de contexto (ahorro de tokens), y cómo arrancar
HydraMem con el protocolo MCP.

---

## Tabla de contenidos

1. [Arranque con MCP](#arranque-con-mcp)
2. [Referencia completa de la CLI](#referencia-completa-de-la-cli)
3. [Compactación de conversación (ahorro de tokens)](#compactación-de-conversación)
4. [Configuración de Skills](#configuración-de-skills)
5. [Descripción de cada Skill](#descripción-de-cada-skill)
6. [Flujo recomendado de uso](#flujo-recomendado-de-uso)

---

## Arranque con MCP

HydraMem expone sus 18 herramientas a cualquier cliente AI compatible con el
**Model Context Protocol (MCP)**. El servidor se inicia con:

```bash
# Transporte stdio (ideal para MCP clients como Claude Desktop)
hydramem serve

# Transporte HTTP (ideal para OpenCode, Cursor, VS Code Copilot)
hydramem serve --transport http

# HTTP en puerto personalizado
hydramem serve --transport streamable-http --host 0.0.0.0 --port 3000
```

### Cómo conectar tu cliente AI

#### Claude Desktop

Añade a `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hydramem": {
      "command": "hydramem",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```

#### OpenCode (HTTP)

Añade a `~/.config/opencode/config.json`:

```json
{
  "mcp": {
    "hydramem": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

#### VS Code Copilot / Cursor

Añade a `.vscode/mcp.json` o `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "hydramem": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

### ¿Qué pasa al arrancar?

1. Se carga `config.yml` (o valores por defecto).
2. Se inicializa FastMCP con las 18 herramientas registradas.
3. Se crean singletons lazy de: `SearchService`, `IngestionPipeline`, `NightGardener`, `VerificationPipeline`.
4. El servidor escucha conexiones MCP — cada llamada a herramienta se loguea en telemetría.
5. Se asigna un `session_id` UUID único por arranque del servidor.

---

## Referencia completa de la CLI

El binario `hydramem` agrupa todos los comandos. Se instala con `pip install hydramem`
o `uv tool install hydramem`.

### Comandos del flujo principal

#### `hydramem init`

Crea un workspace nuevo con configuración, directorios y snippet MCP.

```bash
hydramem init [path] [--provider auto|local|ollama|openai|anthropic] [--force] [--no-input]
```

| Flag | Descripción |
|------|-------------|
| `path` | Directorio del workspace (por defecto: directorio actual) |
| `--provider` | Proveedor LLM a escribir en `config.yml` |
| `--force` | Sobrescribir un `config.yml` existente |
| `--no-input` | No preguntar; usar defaults |

**Ejemplo:**
```bash
hydramem init ~/mi-memoria --provider local
```

Genera: `config.yml`, `kms/`, `data/` y muestra el snippet JSON para el cliente MCP.

---

#### `hydramem ingest`

Ingesta archivos Markdown o directorios completos a la base de conocimiento.

```bash
hydramem ingest <path> [--project default] [--no-recursive]
```

| Flag | Descripción |
|------|-------------|
| `path` | Archivo `.md` o directorio a ingestar |
| `--project` | Namespace del proyecto (default: `default`) |
| `--no-recursive` | No descender a subdirectorios |

**Ejemplo:**
```bash
hydramem ingest ./docs --project mi-proyecto
```

---

#### `hydramem search`

Búsqueda híbrida (vector + grafo) sobre la base de conocimiento.

```bash
hydramem search <query> [--project default] [--top-k 10] [--json]
```

| Flag | Descripción |
|------|-------------|
| `query` | Pregunta en lenguaje natural |
| `--project` | Proyecto donde buscar |
| `--top-k` | Número de resultados (default: 10) |
| `--json` | Salida completa en JSON |

**Ejemplo:**
```bash
hydramem search "¿cómo funciona el Night Gardener?" --top-k 5
```

---

#### `hydramem serve`

Arranca el servidor MCP de HydraMem (18 herramientas).

```bash
hydramem serve [--transport stdio|http|streamable-http] [--host HOST] [--port PORT]
```

| Flag | Descripción |
|------|-------------|
| `--transport` | Protocolo MCP (default: `streamable-http`) |
| `--host` | Dirección de binding para HTTP |
| `--port` | Puerto de binding para HTTP |

---

### Comandos de observabilidad

#### `hydramem stats`

Muestra estadísticas de ahorro de tokens con tabla enriquecida (savings %, coste, VoG, métricas del garden).

```bash
hydramem stats [--project PROJECT] [--days N] [--last-7d] [--export md|csv] [--raw]
```

| Flag | Descripción |
|------|-------------|
| `--project` | Filtrar stats a un proyecto específico |
| `--days N` | Número de días a incluir (default: 7) |
| `--last-7d` | Atajo para `--days 7` |
| `--export` | Exportar como Markdown o CSV |
| `--raw` | Imprimir filas crudas por evento (modo auditoría) |

**Ejemplo:**
```bash
hydramem stats --last-7d --export md
```

---

#### `hydramem telemetry`

Gestión de datos de telemetría local (opt-in/out, mostrar, borrar, enviar).

```bash
hydramem telemetry [--project PROJECT] --show|--wipe|--send|--opt-in|--opt-out
```

| Flag | Descripción |
|------|-------------|
| `--show` | Mostrar métricas agregadas como JSON |
| `--wipe` | Eliminar la `metrics.db` local |
| `--send` | Enviar agregado anónimo (si se optó in) |
| `--opt-in` | Activar envío de telemetría anónima |
| `--opt-out` | Desactivar envío de telemetría |

---

#### `hydramem projects`

Lista todos los proyectos conocidos (de telemetría y del store de conocimiento).

```bash
hydramem projects [--json]
```

Útil para descubrir qué valores `--project` existen.

---

#### `hydramem garden-status`

Muestra el estado acumulativo del Night Gardener.

```bash
hydramem garden-status [--json]
```

---

#### `hydramem dashboard`

Ejecuta un dashboard HTML de solo lectura en localhost.

```bash
hydramem dashboard [--host 127.0.0.1] [--port 8765] [--days 7]
```

---

### Comandos de ingesta avanzada

#### `hydramem ingest-async`

Ingesta asíncrona y reanudable de un directorio con checkpoint en disco.

```bash
hydramem ingest-async <directory> [--project default] [--concurrency 4] [--no-recursive] [--checkpoint PATH]
```

| Flag | Descripción |
|------|-------------|
| `directory` | Directorio con archivos Markdown |
| `--concurrency` | Número de workers paralelos (default: 4) |
| `--checkpoint` | Ruta al archivo de checkpoint personalizado |

---

#### `hydramem sessions-merge`

Merge CRDT de dos archivos `sessions.json` (unión Last-Writer-Wins por fingerprint).

```bash
hydramem sessions-merge <local> <remote> [--out PATH]
```

---

### Comandos de federación

#### `hydramem export`

Firma y exporta un proyecto (entidades + relaciones + chunks) para compartir con peers.

```bash
hydramem export <output> [--project default] [--secret-env HYDRAMEM_FEDERATION_SECRET] [--issuer local]
```

#### `hydramem import`

Verifica una exportación firmada y la fusiona en el store local.

```bash
hydramem import <input> [--project PROJECT] [--secret-env HYDRAMEM_FEDERATION_SECRET] [--accept-issuer ISSUER]
```

---

### Comandos de calibración y entrenamiento

#### `hydramem calibrate-srmkg`

Entrena una calibración logística de los pesos de componentes SR-MKG usando decisiones registradas.

```bash
hydramem calibrate-srmkg [--project default] [--min-samples 50] [--test-fraction 0.2] [--l2 1.0] [--lr 0.1] [--epochs 500] [--dry-run]
```

---

#### `hydramem review`

Etiqueta candidatos de poda de edges espurios para construir el golden dataset.

```bash
hydramem review [--project default] [--limit 20] [--status] [--export PATH]
```

Interactivo: para cada edge candidato puedes elegir `[p]rune`, `[k]eep`, `[s]kip` o `[q]uit`.

---

#### `hydramem train-pruner`

Entrena el scorer de edges espurios a partir del golden dataset etiquetado con `review`.

```bash
hydramem train-pruner [--project default] [--min-samples 20] [--test-fraction 0.2] [--l2 1.0] [--lr 0.1] [--epochs 500] [--dry-run]
```

---

## Compactación de conversación

### ¿Qué es?

HydraMem **no envía toda la conversación ni todos los documentos** al LLM.
En su lugar, utiliza un sistema de **compactación de contexto** que reduce
dramáticamente los tokens inyectados manteniendo la calidad de las respuestas.

### ¿Cómo funciona?

El concepto clave es que HydraMem reemplaza el enfoque "naive RAG" (inyectar
los top-20 chunks por vector similarity sin filtrar) con un pipeline inteligente:

```
                  Naive RAG (sin HydraMem)
┌─────────────────────────────────────────────────┐
│ Query → embed → top-20 chunks → enviar TODO     │
│ al LLM (miles de tokens, mucho ruido)           │
└─────────────────────────────────────────────────┘

           HydraMem (con compactación)
┌─────────────────────────────────────────────────┐
│ Query → embed → top-k chunks                    │
│       → expansión por grafo (entidades vecinas) │
│       → filtro SR-MKG (topológico, sin LLM)     │
│       → filtro VoG (semántico, si es borderline)│
│       → solo contexto verificado al LLM         │
│ (resultado: ~70% menos tokens)                  │
└─────────────────────────────────────────────────┘
```

### Las dos vías de recuperación

| Vía | Herramienta MCP | Latencia | Uso de LLM | Tokens inyectados |
|-----|----------------|----------|------------|-------------------|
| **Rápida** | `priming_context_tool` | < 100 ms | Ninguno | Mínimos (top-3 chunks + vecinos) |
| **Completa** | `hydra_search_tool` | 100–2000 ms | Solo VoG en casos borderline | Reducidos (~70% menos que naive) |

### Mecanismo de ahorro

1. **Baseline (shadow estimator):** Para cada consulta, HydraMem calcula cuántos
   tokens hubiera inyectado un RAG convencional (top-20 chunks sin filtrar).

2. **Tokens inyectados:** Lo que realmente se envía al LLM después de pasar por
   el pipeline de verificación (SR-MKG + VoG).

3. **Ahorro:** `(baseline - injected) / baseline × 100%`

### Ejemplo de resultado de `hydramem stats`

```
┌───────────────────────────────────────────────┐
│ HydraMem Stats – last 7 days                  │
├──────────────────────────┬────────────────────┤
│ Tokens (naive RAG)       │             1.4M   │
│ Tokens injected          │           312.5K   │
│ Tokens saved             │  1.1M (77.8%)      │
│ Cost saved (est.)        │  $5.47             │
└──────────────────────────┴────────────────────┘
```

### ¿Por qué se llama "compactación"?

Porque en lugar de enviar toda la información bruta al LLM (que consume la
ventana de contexto rápidamente), HydraMem **compacta** la información relevante:

- Selecciona solo los chunks más relevantes semánticamente.
- Expande por el grafo de conocimiento para encontrar relaciones implícitas.
- Filtra chunks espurios o irrelevantes mediante SR-MKG y VoG.
- El resultado es un contexto **denso, verificado y mucho más corto**.

Esto permite que agentes AI mantengan conversaciones más largas sin agotar la
ventana de contexto, ya que cada turno recibe solo la evidencia estrictamente
necesaria en lugar de todo el corpus.

### Auditar el ahorro

```bash
# Ver métricas de ahorro de tokens
hydramem stats --last-7d

# Inspeccionar cada evento individual (modo auditoría)
hydramem stats --raw

# Consultar la base SQLite directamente
sqlite3 ~/.hydramem/metrics.db \
  "SELECT tool_name, tokens_baseline, tokens_injected FROM events ORDER BY ts DESC LIMIT 10"
```

---

## Configuración de Skills

Las **Agent Skills** son archivos Markdown con frontmatter YAML que describen
secuencias de herramientas MCP para que el agente AI las ejecute de forma
predecible. Se encuentran en `.github/skills/`.

### Estructura de una Skill

Cada skill tiene un archivo `SKILL.md` con este formato:

```markdown
---
description: >
  Descripción corta de lo que hace la skill.
tools:
  - hydramem-server
---

# nombre-de-la-skill

Instrucciones detalladas para el agente...
```

### Skills disponibles

HydraMem incluye 6 skills en `.github/skills/`:

```
.github/skills/
├── hydramem-garden/SKILL.md
├── hydramem-ingest/SKILL.md
├── hydramem-ingest-smart/SKILL.md
├── hydramem-link/SKILL.md
├── hydramem-query/SKILL.md
└── hydramem-reason/SKILL.md
```

### Cómo se activan las Skills

Las skills se activan de distintas formas según el cliente:

#### En GitHub Copilot (VS Code / Agent Mode)

Las skills de `.github/skills/` se detectan automáticamente cuando el
repositorio tiene esta estructura. El agente las usa cuando detecta que la
petición del usuario coincide con el patrón descrito en la skill.

#### En OpenCode

Se invocan con el prefijo `@`:
```
> @hydramem-query ¿Qué es el Night Gardener?
> @hydramem-ingest Ingesta los docs en ./kms
```

#### En Claude Desktop

Se activan cuando el MCP server está conectado — Claude identifica las
herramientas disponibles y las skills proporcionan el "cómo" estructurado.

---

## Descripción de cada Skill

### 1. `hydramem-query` — Consulta directa con citas

**Cuándo se usa:** Preguntas factuales directas ("¿Qué dice X sobre Y?").

**Flujo:**
1. Llama a `priming_context_tool(query=<pregunta>, k=3)`.
2. Inyecta el contexto devuelto en el prompt del sistema.
3. Responde con citas inline `[1]`, `[2]`... y una sección de fuentes.

**Herramientas MCP:** `priming_context_tool`

**Ejemplo de uso:**
```
> @hydramem-query ¿Cómo funciona la verificación SR-MKG?
```

---

### 2. `hydramem-reason` — Razonamiento multi-hop

**Cuándo se usa:** Preguntas que requieren conectar información de múltiples
documentos, cadenas causales, o relaciones implícitas.

**Flujo:**
1. Llama a `hydra_search_tool(query=<pregunta>, max_hops=3)`.
2. El pipeline ejecuta: vector ANN → expansión de grafo → SR-MKG → VoG.
3. Usa `result.final_context` como contexto verificado.
4. Incluye una traza de razonamiento mostrando qué entidades/chunks se conectaron.

**Herramientas MCP:** `hydra_search_tool`

**Ejemplo de uso:**
```
> @hydramem-reason ¿Cómo afecta la configuración de LanceDB al rendimiento del Night Gardener?
```

---

### 3. `hydramem-ingest` — Ingesta de archivos

**Cuándo se usa:** Añadir documentos nuevos a la base de conocimiento.

**Flujo:**
- Archivo individual: `ingest_markdown(file_path=<path>)`
- Directorio: `ingest_directory_tool(directory=<path>, recursive=true)`

**Herramientas MCP:** `ingest_markdown`, `ingest_directory_tool`

**Ejemplo de uso:**
```
> @hydramem-ingest Ingesta todos los archivos en ./docs/nuevos
```

**Después de la ingesta:** sugiere ejecutar `hydramem-garden` para que el
Night Gardener construya relaciones entre el contenido nuevo y el existente.

---

### 4. `hydramem-ingest-smart` — Ingesta semántica por el agente

**Cuándo se usa:** Cuando el agente puede leer el documento y hacer chunking
semántico + extracción de entidades/relaciones con su propio modelo (mayor
calidad que el regex fallback).

**Flujo:**
1. El agente lee el documento.
2. Lo divide en chunks de ~400 tokens respetando fronteras semánticas.
3. Extrae entidades por chunk (`concept`, `tool`, `module`, `person`...).
4. Extrae relaciones dirigidas entre entidades (`USES`, `PART_OF`, `IMPLEMENTS`...).
5. Llama a `ingest_prechunked(source=<path>, chunks=[...])`.

**Herramientas MCP:** `ingest_prechunked`, `submit_session_extraction`

**Cuándo NO usar:** Si el documento tiene >200 chunks o >1000 entidades (usar `hydramem-ingest` estándar).

**Ventaja:** Las relaciones propuestas por el agente pasan por SR-MKG + VoG, así que las alucinaciones se rechazan automáticamente.

---

### 5. `hydramem-link` — Curación manual del grafo

**Cuándo se usa:** Establecer o eliminar relaciones explícitas entre entidades
que el Night Gardener aún no ha inferido.

**Flujos:**

- **Crear relación:**
  ```
  create_relation(from_entity=<nombre>, to_entity=<nombre>,
                  relation_type="caused", verify=true)
  ```

- **Eliminar relación:**
  ```
  delete_relation(from_entity=<id>, to_entity=<id>, relation_type=<tipo>)
  ```

- **Verificar conflicto:**
  ```
  check_conflict_tool(text_a=<pasaje_A>, text_b=<pasaje_B>)
  ```

**Herramientas MCP:** `create_relation`, `delete_relation`, `check_conflict_tool`, `list_entities_tool`

---

### 6. `hydramem-garden` — Ciclo de mantenimiento autónomo

**Cuándo se usa:** Después de ingestas pesadas, periódicamente (diario), o
cuando se quiere optimizar el grafo de conocimiento.

**Flujo:**
1. Verifica estado: `get_garden_status_tool()` (si `is_running: true`, informa y para).
2. Ejecuta el ciclo completo: `run_night_gardener(project=<proyecto>)`.
3. Opcional — poda neuronal: `train_gnn_tool(project=<proyecto>, dry_run=false)`.

**Lo que hace el ciclo:**
- **Inferencia de relaciones:** analiza sesiones Q&A recientes con LLM.
- **Verificación de dos niveles:** SR-MKG (topológico) + VoG (semántico).
- **Poda rule-based:** elimina entidades aisladas/huérfanas.
- **Poda LightGNN (opcional):** elimina edges estructuralmente espurios.

**Herramientas MCP:** `get_garden_status_tool`, `run_night_gardener`, `train_gnn_tool`

**Después del ciclo:** recomienda ejecutar `hydramem stats --last-7d` para ver
cómo las mejoras de calidad se traducen en ahorro de tokens.

---

## Flujo recomendado de uso

### Setup inicial (una vez)

```bash
# 1. Instalar
uv tool install hydramem

# 2. Crear workspace
hydramem init ~/mi-memoria --provider local
cd ~/mi-memoria

# 3. (Opcional) Pull modelo local
ollama pull gemma4:e4b

# 4. Arrancar servidor MCP
hydramem serve --transport http
```

### Uso diario

```bash
# Ingestar documentos nuevos
hydramem ingest ./kms

# Buscar desde CLI
hydramem search "¿cómo funciona X?"

# Ver métricas
hydramem stats --last-7d
hydramem garden-status
```

### Desde el agente AI

1. **Ingestar** docs/notas → `hydramem-ingest` o `hydramem-ingest-smart`.
2. **Preguntar** cuestiones factuales → `hydramem-query`.
3. **Razonar** sobre relaciones complejas → `hydramem-reason`.
4. **Curar** relaciones manualmente → `hydramem-link`.
5. **Mantener** calidad del grafo → `hydramem-garden` (periódico o post-ingesta).

### Ciclo de mejora continua

```
Ingestar → Consultar → El agente aprende patrones →
Night Gardener infiere relaciones → Verificación automática →
Grafo más denso y preciso → Mejores respuestas futuras
```

---

## Skills más útiles y cuándo usarlas

| Situación | Skill recomendada |
|-----------|-------------------|
| "¿Qué dice la documentación sobre X?" | `hydramem-query` |
| "¿Cómo se relacionan A y B?" | `hydramem-reason` |
| "Guarda estas notas de la reunión" | `hydramem-ingest-smart` |
| "Indexa todo el directorio ./docs" | `hydramem-ingest` |
| "Marca que X depende de Y" | `hydramem-link` |
| "Optimiza el grafo de conocimiento" | `hydramem-garden` |
| Después de ingestar muchos docs | `hydramem-garden` |
| Pregunta simple y rápida | `hydramem-query` |
| Pregunta que cruza múltiples docs | `hydramem-reason` |
