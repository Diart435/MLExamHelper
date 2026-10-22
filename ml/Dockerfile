FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libpq-dev нужен для сборки asyncpg, build-essential — для его C-расширений.
# Оба остаются в образе: pip upgrade меняет набор пакетов и без них сборка падает.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 10001 ml && chown -R ml:ml /srv/app
USER ml

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import app.workers.worker" || exit 1

ENTRYPOINT ["python", "-m", "app.workers.worker"]