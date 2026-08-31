FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/data/models

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# sentence-transformers pulls torch, and the default PyPI wheel bundles CUDA
# (~2.5 GB). EMBEDDING_DEVICE defaults to cpu, so install the CPU-only wheel
# first; pip then treats torch as already satisfied below.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# RAGAS and its LangChain dependencies, used only by the generation benchmark.
# Build with --build-arg INSTALL_EVAL=false for a slimmer runtime image.
ARG INSTALL_EVAL=true
COPY requirements-eval.txt .
RUN if [ "$INSTALL_EVAL" = "true" ]; then \
      pip install --no-cache-dir -r requirements-eval.txt; \
    fi

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
# The benchmark harness ships with the image so it can be run against the
# live database: docker compose exec api python -m evaluation
COPY evaluation ./evaluation
COPY entrypoint.sh entrypoint-worker.sh ./
RUN chmod +x entrypoint.sh entrypoint-worker.sh

EXPOSE 8000
# The same image serves the API and the worker; compose overrides the command
# for the worker service. One image means one build and no chance of the two
# running different versions of the ingestion code.
CMD ["./entrypoint.sh"]
