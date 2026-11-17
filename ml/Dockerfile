# ML worker: Redis Stream consumer (ingest / create_test / grade_attempt).
# Не держит HTTP — это фоновый процесс. Healthcheck проверяет только одно:
# жив ли процесс. Если main() упал — process exit → restart policy в compose
# переподнимет. Подробности проверки — ниже, у HEALTHCHECK.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Системные зависимости:
#   - build-essential / libpq-dev для сборки asyncpg
#   - curl — для healthcheck/debug
# ffmpeg НЕ установлен: текущая итерация только PDF/DOCX, whisper не активен.
# Когда добавим аудио — раскомментируем ffmpeg здесь и в спеке §11.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Сначала только requirements — это самый часто меняющийся слой. Кэш Docker
# переиспользует слой с зависимостями пока requirements.txt не изменился,
# даже если исходники поменялись.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Затем сам код.
COPY app/ ./app/
COPY tools/ ./tools/

# Не дефолтный user — ограничим права. UID 1000 совпадает с большинством
# dev-окружений на хосте, что важно для монтирования томов.
RUN useradd --uid 1000 --create-home --shell /bin/bash mluser \
    && chown -R mluser:mluser /app
USER mluser

# Не нужен EXPOSE — у воркера нет входящих портов.
# Healthcheck: проверяем, что процесс жив, ЧТЕНИЕ /proc/1/cmdline.
# Раньше было `python -c "import app.workers.rag"` — так нельзя: импорт тянет
# всё дерево приложения (openai SDK — 3.4 с, суммарно 7.4 с) и не укладывается
# в таймаут 5 с. Контейнер с живым воркером светился «unhealthy».
# procps в образе нет, поэтому pgrep недоступен — читаем /proc напрямую.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0 if b'app.workers.rag' in open('/proc/1/cmdline','rb').read() else 1)" || exit 1

# Точка входа. python -m обеспечивает корректные относительные импорты app.*
# (а не запуск скрипта, который не нашёл бы app.workers.rag без sys.path).
ENTRYPOINT ["python", "-m", "app.workers.rag"]