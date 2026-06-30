# syntax=docker/dockerfile:1
# Slim, single-stage image. Ollama is NOT bundled — run it as a separate
# service (or use an external API) and point HydraMem at it via config.
FROM python:3.12-slim

# Optional extras baked into the image, e.g.:
#   docker build --build-arg EXTRAS="sentence-transformers,gnn" -t hydramem .
ARG EXTRAS=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # One mounted volume captures graph, vectors, metrics and sessions.
    HYDRAMEM_DATA_DIR=/data \
    # Default to stdio so `docker run -i` plugs straight into MCP clients.
    HYDRAMEM_TRANSPORT=stdio

WORKDIR /app
COPY . .

# Core deps ship manylinux wheels (fastembed/ONNX, lancedb, pyarrow, grafeo),
# so no compiler toolchain is required for the default install.
RUN pip install --upgrade pip \
 && if [ -n "$EXTRAS" ]; then pip install ".[${EXTRAS}]"; else pip install .; fi \
 && mkdir -p /data

VOLUME ["/data"]

# HTTP transport (optional):
#   docker run -p 3000:3000 hydramem serve --transport http --host 0.0.0.0
EXPOSE 3000

# The CLI is the entrypoint; the default command serves MCP over stdio.
#   docker run -i --rm -v hydramem-data:/data hydramem          # MCP server
#   docker run --rm -v hydramem-data:/data -v $PWD:/work hydramem ingest /work
ENTRYPOINT ["hydramem"]
CMD ["serve", "--transport", "stdio"]
