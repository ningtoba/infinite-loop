FROM python:3.12-slim

LABEL org.opencontainers.image.title="Hermes Loop Web UI"
LABEL org.opencontainers.image.description="Web UI and containerized runtime for the Hermes infinite loop daemon"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl procps && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi uvicorn python-dotenv && \
    pip install --no-cache-dir -e . 2>/dev/null || true

COPY web_app/ ./web_app/
COPY hermes_loop/ ./hermes_loop/

ENV WEB_PORT=8090
ENV PYTHONUNBUFFERED=1

EXPOSE ${WEB_PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -fs http://localhost:${WEB_PORT}/api/health || exit 1

ENTRYPOINT ["sh", "-c", "exec python -m web_app --host 0.0.0.0 --port ${WEB_PORT:-8090}"]
