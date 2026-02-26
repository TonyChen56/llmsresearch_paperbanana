# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /build

# System dependencies for Pillow/matplotlib runtime.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libgl1 \
        libglib2.0-0 \
        libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY paperbanana/ paperbanana/
COPY api/ api/
COPY mcp_server/ mcp_server/
COPY prompts/ prompts/
COPY data/ data/
COPY configs/ configs/
COPY scripts/ scripts/

RUN pip install --no-cache-dir ".[api,all-providers]"

# Generate static API docs from OpenAPI schema.
RUN python -m scripts.build_static_docs

FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -r appuser
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build/paperbanana paperbanana/
COPY --from=builder /build/api api/
COPY --from=builder /build/mcp_server mcp_server/
COPY --from=builder /build/prompts prompts/
COPY --from=builder /build/data data/
COPY --from=builder /build/configs configs/
COPY --from=builder /build/scripts scripts/

RUN mkdir -p outputs && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

