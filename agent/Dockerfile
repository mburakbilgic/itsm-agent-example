FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/root/.cache/huggingface/sentence-transformers \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

# Build deps for chromadb + sentence-transformers; curl is also used by the
# compose healthcheck against /health.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package metadata first to maximize layer cache when only source changes.
COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN pip install --no-cache-dir /app

# Pre-create writable dirs (mounted as volumes at runtime)
RUN mkdir -p /app/chroma_data /app/reports /app/kb

EXPOSE 8002

# Long-running REST API by default. The CLI module
# (`itsm_agent.interfaces.cli`) is still installed and can be invoked via:
#     docker compose run --rm agent python -m itsm_agent.interfaces.cli INC-1001
CMD ["uvicorn", "itsm_agent.interfaces.rest:app", "--host", "0.0.0.0", "--port", "8002"]
