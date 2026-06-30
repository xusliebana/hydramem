# Ejemplo: Ingesta y Night Gardener (dogfood)

# 1. Ingesta de toda la documentación y KMS
# (esto puede ejecutarse dentro del contenedor)
uv run python -c "from hydramem.ingest.pipeline import IngestionPipeline; print(IngestionPipeline().ingest_directory('./docs', project='default'))"
uv run python -c "from hydramem.ingest.pipeline import IngestionPipeline; print(IngestionPipeline().ingest_directory('./kms', project='default'))"

# 2. Ejecuta el Night Gardener para inferencia y verificación automática
docker exec hydramem python -c "from hydramem.garden.gardener import NightGardener; print(NightGardener().run())"

# 3. Consulta desde tu cliente MCP (OpenCode, Claude Desktop, Cursor, Copilot)
# Ejemplo en OpenCode:
# > @hydramem-query ¿Qué es el Night Gardener?

# 4. Ver métricas y estadísticas
uv run hydramem stats --last-7d
uv run hydramem stats --days 30 --export md > report.md

# 5. (Opcional) Añade tus propios .md a kms/ y repite el proceso
