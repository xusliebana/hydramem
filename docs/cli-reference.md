# CLI Reference

Complete reference for all `hydramem` CLI commands.

## Primary workflow

### `hydramem init`

Scaffold a new HydraMem workspace with configuration, directories, and MCP client snippet.

```bash
hydramem init [path] [--provider auto|local|ollama|openai|anthropic] [--force] [--no-input]
```

| Flag | Description |
|------|-------------|
| `path` | Workspace directory (default: current directory) |
| `--provider` | LLM provider to write into `config.yml` |
| `--force` | Overwrite an existing `config.yml` |
| `--no-input` | Never prompt; use defaults |

---

### `hydramem ingest`

Ingest Markdown files or directories into the knowledge base.

```bash
hydramem ingest <path> [--project default] [--no-recursive]
```

| Flag | Description |
|------|-------------|
| `path` | Markdown file or directory to ingest |
| `--project` | Project namespace (default: `default`) |
| `--no-recursive` | Do not descend into subdirectories |

---

### `hydramem search`

Perform hybrid (vector + graph) search over the knowledge base.

```bash
hydramem search <query> [--project default] [--top-k 10] [--json]
```

| Flag | Description |
|------|-------------|
| `query` | Natural-language query |
| `--project` | Project to search in (default: `default`) |
| `--top-k` | Number of results to return (default: 10) |
| `--json` | Output the full result as JSON |

---

### `hydramem serve`

Start the HydraMem MCP server (18 tools).

```bash
hydramem serve [--transport stdio|http|streamable-http] [--host HOST] [--port PORT]
```

| Flag | Description |
|------|-------------|
| `--transport` | MCP transport protocol (default: `streamable-http`) |
| `--host` | Bind address for HTTP transport |
| `--port` | Bind port for HTTP transport |

---

## Observability

### `hydramem stats`

Show token-saving statistics with a rich table (savings %, cost, VoG, garden metrics).

```bash
hydramem stats [--project PROJECT] [--days N] [--last-7d] [--export md|csv] [--raw]
```

| Flag | Description |
|------|-------------|
| `--project` | Filter stats to a specific project (default: all projects) |
| `--days N` | Number of days to include (default: 7) |
| `--last-7d` | Shorthand for `--days 7` |
| `--export` | Export as `md` (Markdown table) or `csv` |
| `--raw` | Print raw per-event rows for auditing |

---

### `hydramem telemetry`

Manage local telemetry data (opt-in/out, show, wipe, send).

```bash
hydramem telemetry [--project PROJECT] --show|--wipe|--send|--opt-in|--opt-out
```

| Flag | Description |
|------|-------------|
| `--project` | Filter telemetry to a specific project |
| `--show` | Print aggregated metrics as JSON |
| `--wipe` | Delete the local `metrics.db` |
| `--send` | Send anonymous aggregate (if opted in) |
| `--opt-in` | Opt in to anonymous aggregate telemetry |
| `--opt-out` | Opt out of anonymous aggregate telemetry |

---

### `hydramem projects`

List all known projects from telemetry events and the knowledge store.

```bash
hydramem projects [--json]
```

| Flag | Description |
|------|-------------|
| `--json` | Print the project list as a JSON array |

Use this to discover which `--project` values are available for `stats` and `telemetry`.

---

### `hydramem garden-status`

Show Night Gardener cumulative status and filtering metrics.

```bash
hydramem garden-status [--json]
```

| Flag | Description |
|------|-------------|
| `--json` | Print raw garden status as JSON |

---

### `hydramem dashboard`

Run the read-only HTML dashboard on localhost.

```bash
hydramem dashboard [--host 127.0.0.1] [--port 8765] [--days 7]
```

| Flag | Description |
|------|-------------|
| `--host` | Bind address (default: `127.0.0.1`) |
| `--port` | Bind port (default: `8765`) |
| `--days` | Number of days of data to display (default: 7) |

---

## Ingestion & data management

### `hydramem ingest-async`

Resumable async ingest of a directory with on-disk checkpointing.

```bash
hydramem ingest-async <directory> [--project default] [--concurrency 4] [--no-recursive] [--checkpoint PATH]
```

| Flag | Description |
|------|-------------|
| `directory` | Directory containing Markdown files |
| `--project` | Project namespace (default: `default`) |
| `--concurrency` | Number of parallel workers (default: 4) |
| `--no-recursive` | Do not descend into subdirectories |
| `--checkpoint` | Override the default checkpoint file path |

---

### `hydramem sessions-merge`

CRDT merge of two `sessions.json` files (Last-Writer-Wins union by fingerprint).

```bash
hydramem sessions-merge <local> <remote> [--out PATH]
```

| Flag | Description |
|------|-------------|
| `local` | Local `sessions.json` (modified in place by default) |
| `remote` | Remote `sessions.json` to merge in |
| `--out` | Optional output path (instead of modifying local in place) |

---

## Federation

### `hydramem export`

Sign and export a project (entities + relations + chunks) for sharing with trusted peers.

```bash
hydramem export <output> [--project default] [--secret-env HYDRAMEM_FEDERATION_SECRET] [--issuer local]
```

| Flag | Description |
|------|-------------|
| `output` | Output file path |
| `--project` | Project to export (default: `default`) |
| `--secret-env` | Env var holding the shared HMAC secret |
| `--issuer` | Issuer identifier for this export |

---

### `hydramem import`

Verify a signed export and merge it into the local store.

```bash
hydramem import <input> [--project PROJECT] [--secret-env HYDRAMEM_FEDERATION_SECRET] [--accept-issuer ISSUER]
```

| Flag | Description |
|------|-------------|
| `input` | Path to a previously exported file |
| `--project` | Override target project name |
| `--secret-env` | Env var holding the shared HMAC secret |
| `--accept-issuer` | Whitelist an issuer (repeatable) |

---

## Calibration & training

### `hydramem calibrate-srmkg`

Train a per-project logistic calibration of SR-MKG component weights using recorded decisions.

```bash
hydramem calibrate-srmkg [--project default] [--min-samples 50] [--test-fraction 0.2] [--l2 1.0] [--lr 0.1] [--epochs 500] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--project` | Project to calibrate (default: `default`) |
| `--min-samples` | Minimum decisions required to train (default: 50) |
| `--test-fraction` | Fraction held out for evaluation (default: 0.2) |
| `--l2` | L2 regularisation strength (default: 1.0) |
| `--lr` | Learning rate (default: 0.1) |
| `--epochs` | Training epochs (default: 500) |
| `--dry-run` | Train but do not write the weights file |

---

### `hydramem review`

Label queued spurious-edge prune candidates to build the golden dataset.

```bash
hydramem review [--project default] [--limit 20] [--status] [--export PATH]
```

| Flag | Description |
|------|-------------|
| `--project` | Project to review (default: `default`) |
| `--limit` | Maximum candidates to show per session (default: 20) |
| `--status` | Print queue counts as JSON and exit |
| `--export` | Export the labelled golden dataset to a JSONL path |

---

### `hydramem train-pruner`

Train the learned spurious-edge scorer from labelled prune reviews.

```bash
hydramem train-pruner [--project default] [--min-samples 20] [--test-fraction 0.2] [--l2 1.0] [--lr 0.1] [--epochs 500] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--project` | Project to train on (default: `default`) |
| `--min-samples` | Minimum labelled reviews required (default: 20) |
| `--test-fraction` | Fraction held out for evaluation (default: 0.2) |
| `--l2` | L2 regularisation strength (default: 1.0) |
| `--lr` | Learning rate (default: 0.1) |
| `--epochs` | Training epochs (default: 500) |
| `--dry-run` | Train but do not write the weights file |

---

## Cross-project entity linking

When multiple projects exist, HydraMem links entities across them via **federation** and **cross-project hits**:

1. **Shared entity recognition:** During ingestion, entities are identified by their normalised name. If the same entity (e.g., a library, concept, or person) appears in project A and project B, the knowledge graph can recognise the overlap.

2. **Cross-project search:** When `hydra_search` runs, it can detect that a retrieved chunk references an entity that also exists in another project. These are recorded as `cross_project_hit` events in telemetry and displayed in `hydramem stats`.

3. **Federation (export/import):** The `hydramem export` and `hydramem import` commands let you explicitly share entities and relations between HydraMem installations. Imported entities are merged into the target project's graph, creating cross-references.

4. **Night Gardener inference:** The autonomous Night Gardener can propose new relations between entities — including those that span project boundaries — based on co-occurrence patterns, semantic similarity, and structural graph features.

The `--project` flag on `stats` and `telemetry` lets you inspect metrics for a single project, while omitting it shows the aggregate across all projects (including cross-project interactions).
