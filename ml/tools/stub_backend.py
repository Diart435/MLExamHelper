"""Stub backend для интеграционного теста ML-сервиса.

Эмулирует те взаимодействия, которые будет делать Java-backend
с ML-воркером через Redis Streams + MinIO:

  1) ingest       — залить файл в MinIO → XADD ingest:be-to-ml → дождаться ingest:ml-to-be
  2) create_test  — XADD create-test:be-to-ml → дождаться create-test:ml-to-be
  3) grade_attempt— XADD grade-test:be-to-ml → дождаться grade-test:ml-to-be

Один тип задачи — один канал: тип задаёт ИМЯ КАНАЛА, а не поле в payload
(в payload поля `type` нет).

Результаты читает через свой consumer group (ml-backend-stub), отдельный от
воркера. Это та же схема, которую потом возьмёт backend: его consumer group
будет `ml-backend`, у каждого replica — свой consumer name.

Stub создаёт строку `materials` в Postgres — ровно это делает настоящий backend
при загрузке файла. Без неё ML не сможет записать чанки: на `material_chunks`
есть FK на `materials`.

Stub также повторяет запись результатов в БД (`tests`/`test_questions` после
`create_test`, `student_attempts`/`attempt_answers` после `grade_attempt`) —
это работа Java-listener'а, которого в этой ветке ещё нет. Без неё
`grade-attempt` не найдёт вопросов: grader читает их из `test_questions`.

ЗАПУСК (после `docker compose up -d postgres redis seaweedfs ml`):

  # Полный demo-цикл: залить sample.pdf → подождать ingest → сгенерировать тест
  python -m tools.stub_backend demo

  # Только ingest конкретного файла
  python -m tools.stub_backend ingest data/sample.pdf

  # Только create_test по уже проиндексированным material_id
  # (размер теста выбирает ML сам по материалу)
  python -m tools.stub_backend create-test --material-ids 15716 87891 --title "Quiz"

  # Проверить попытку по готовому тесту (вопросы читаются из test_questions)
  python -m tools.stub_backend grade-attempt --test-id <uuid>

  # Посмотреть, что лежит в очереди (не consume'ит)
  python -m tools.stub_backend peek ingest:be-to-ml 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

from loguru import logger
from minio import Minio
from minio.error import S3Error
from redis.asyncio import Redis
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.contracts import TASK_TYPES, result_channel, task_channel
from app.core.db import connect as db_connect


# ============================================================================
# Конфиг — из тех же env, что и воркер (см. app/core/config.py)
# ============================================================================

STUB_GROUP = "ml-backend-stub"
STUB_CONSUMER = "stub-1"
DEFAULT_BUCKET = "materials"

# Родительские строки для materials: courses.owner_id → users.user_id.
STUB_USER = uuid.UUID("00000000-0000-4000-8000-00000000feed")
STUB_COURSE = uuid.UUID("00000000-0000-4000-8000-00000000c0de")


def _env(name: str, default: str) -> str:
    import os
    return os.environ.get(name, default)


def make_clients() -> tuple[Redis, Minio, dict]:
    """Поднять Redis + MinIO клиентов из env."""
    redis_url = _env("REDIS_URL", "redis://localhost:6379/0")
    minio_endpoint = _env("MINIO_ENDPOINT", "localhost:9000")
    minio_access = _env("MINIO_ACCESS_KEY", "minio_user")
    minio_secret = _env("MINIO_SECRET_KEY", "minio_password")
    minio_secure = _env("MINIO_SECURE", "false").lower() == "true"
    bucket = _env("MINIO_BUCKET", DEFAULT_BUCKET)
    redis = Redis.from_url(redis_url, decode_responses=True)
    minio = Minio(
        minio_endpoint, access_key=minio_access, secret_key=minio_secret, secure=minio_secure,
    )
    cfg = {
        "bucket": bucket,
        "task_channels": {t: task_channel(t) for t in TASK_TYPES},
        "result_channels": {t: result_channel(t) for t in TASK_TYPES},
    }
    return redis, minio, cfg


async def ensure_backend_group(redis: Redis, result_channels: dict[str, str]) -> None:
    """Создать consumer group для stub'а на каждом канале результатов.

    Consumer group привязана к одному стриму, поэтому группа нужна на каждом
    канале — иначе XREADGROUP по нему падает с NOGROUP.
    """
    from redis.exceptions import ResponseError
    for task_type, channel in result_channels.items():
        try:
            await redis.xgroup_create(
                name=channel, groupname=STUB_GROUP, id="0", mkstream=True,
            )
            logger.info(f"Created stub group '{STUB_GROUP}' on '{channel}'")
        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Stub group already exists on '{channel}'")
            else:
                raise


def ensure_bucket(minio: Minio, bucket: str) -> None:
    """Создать bucket если его нет. sync — Minio client не async."""
    if not minio.bucket_exists(bucket):
        minio.make_bucket(bucket)
        logger.info(f"Created bucket '{bucket}'")


# ============================================================================
# Воркер-функции (бизнес-логика stub'а)
# ============================================================================

async def publish_task(redis: Redis, channel: str, task: dict) -> str:
    """XADD в канал задачи. Возвращает msg_id."""
    msg_id = await redis.xadd(channel, {"payload": json.dumps(task, ensure_ascii=False)})
    logger.info(f"XADD {channel} {msg_id}  task_id={task.get('task_id')}")
    return msg_id


async def wait_for_result(
    redis: Redis, result_channels: dict[str, str], task_id: str,
    timeout_s: float = 300.0, block_ms: int = 5000, material_id: str | None = None,
) -> dict:
    """Блокирующее ожидание результата с нужным task_id (или material_id).

    Поведение:
      - XREADGROUP > по ВСЕМ каналам результатов одним вызовом — берём только
        новые сообщения (не из истории).
      - На каждом сообщении парсим payload, проверяем task_id. У ingest в
        контракте task_id нет — там корреляция по material_id.
      - Если наш — возвращаем, XACK в тот канал, откуда пришло.
      - Если чужой — XACK и продолжаем ждать (это маловероятно в stub'е, но
        правильно: в проде у backend'а может быть несколько consumer'ов).
    """
    streams = {ch: ">" for ch in result_channels.values()}
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            msgs = await redis.xreadgroup(
                groupname=STUB_GROUP,
                consumername=STUB_CONSUMER,
                streams=streams,
                count=10,
                block=block_ms,
            )
        except (TimeoutError, RedisTimeoutError):
            # redis-py 8.x: XREADGROUP BLOCK при таймауте кидает
            # redis.exceptions.TimeoutError (НЕ встроенный TimeoutError).
            # Трактовка: «сообщений пока нет», крутимся дальше.
            continue
        for stream, entries in msgs:
            for msg_id, fields in entries:
                try:
                    payload = json.loads(fields.get("payload", "{}"))
                except json.JSONDecodeError:
                    await redis.xack(stream, STUB_GROUP, msg_id)
                    continue
                matched = payload.get("task_id") == task_id
                if not matched and material_id is not None:
                    matched = payload.get("material_id") == material_id
                if matched:
                    await redis.xack(stream, STUB_GROUP, msg_id)
                    status = payload.get("status")
                    if status is None:
                        status = "error" if "error" in payload else "ok"
                    logger.info(
                        f"Got result for task_id={task_id} from {stream} {msg_id}: "
                        f"status={status}"
                    )
                    return payload
                # чужой task_id — у другого consumer'а это бы забрал тот,
                # но мы stub и в одиночку: всё равно ack'аем, чтобы не зациклиться
                await redis.xack(stream, STUB_GROUP, msg_id)
    raise TimeoutError(f"no result for task_id={task_id} after {timeout_s}s")


def upload_file(minio: Minio, bucket: str, local_path: Path, key: str | None = None) -> str:
    """Залить локальный файл в MinIO. Возвращает object key."""
    key = key or f"uploads/{local_path.name}"
    minio.fput_object(bucket, key, str(local_path))
    logger.info(f"Uploaded {local_path} → s3://{bucket}/{key}")
    return key


# ============================================================================
# Subcommands
# ============================================================================

async def cmd_ingest(args: argparse.Namespace) -> int:
    redis, minio, cfg = make_clients()
    try:
        ensure_bucket(minio, cfg["bucket"])
        await ensure_backend_group(redis, cfg["result_channels"])

        local = Path(args.file)
        if not local.is_file():
            print(f"[ERROR] file not found: {local}", file=sys.stderr)
            return 2

        key = upload_file(minio, cfg["bucket"], local)
        material_id = args.material_id if args.material_id is not None else _stable_id("path", str(local))
        await _ensure_material_row(material_id, local.name, f"s3://{cfg['bucket']}/{key}")

        task = {
            "material_id": material_id,
            "storage_key": key,
        }
        await publish_task(redis, cfg["task_channels"]["ingest"], task)
        result = await wait_for_result(
            redis, cfg["result_channels"], "", timeout_s=args.timeout, material_id=material_id,
        )
        await _update_material_status(material_id, result.get("status"))
    finally:
        await redis.aclose()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ready" else 1


async def cmd_create_test(args: argparse.Namespace) -> int:
    redis, _minio, cfg = make_clients()
    try:
        await ensure_backend_group(redis, cfg["result_channels"])

        material_ids = args.material_ids
        if not material_ids:
            print("[ERROR] --material-ids required", file=sys.stderr)
            return 2

        task = {
            "task_id": uuid.uuid4().hex,
            "test_id": args.test_id or str(uuid.uuid4()),
            "material_ids": material_ids,
            "title": args.title,
            "difficulty": args.difficulty,
        }
        # Контракт v4.1: числа вопросов в payload'е нет — размер выбирает ML
        # сам (планировщик смотрит на материал).
        await publish_task(redis, cfg["task_channels"]["create_test"], task)
        result = await wait_for_result(redis, cfg["result_channels"], task["task_id"], timeout_s=args.timeout)
    finally:
        await redis.aclose()

    if result.get("status") == "ok" and result.get("test"):
        await _persist_test(
            result.get("test_id") or task["test_id"],
            result["test"].get("title") or args.title,
            result["test"],
            amount_questions=len(result["test"].get("questions") or []),
            difficulty=args.difficulty,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


async def cmd_demo(args: argparse.Namespace) -> int:
    """Полный цикл: залить sample.pdf → ingest → create_test по нему."""
    redis, minio, cfg = make_clients()
    try:
        ensure_bucket(minio, cfg["bucket"])
        await ensure_backend_group(redis, cfg["result_channels"])

        local = Path(args.file)
        if not local.is_file():
            print(f"[ERROR] file not found: {local}", file=sys.stderr)
            return 2

        # 1) Ingest
        key = upload_file(minio, cfg["bucket"], local)
        material_id = _stable_id("path", str(local))
        await _ensure_material_row(material_id, local.name, f"s3://{cfg['bucket']}/{key}")
        ingest_task = {
            "material_id": material_id,
            "storage_key": key,
        }
        print(f"\n[1/2] INGEST  {local.name}  → material {material_id}")
        await publish_task(redis, cfg["task_channels"]["ingest"], ingest_task)
        ingest_result = await wait_for_result(
            redis, cfg["result_channels"], "", timeout_s=args.timeout, material_id=material_id,
        )
        print(json.dumps(ingest_result, ensure_ascii=False, indent=2))
        await _update_material_status(material_id, ingest_result.get("status"))
        if ingest_result.get("status") != "ready":
            return 1

        # 2) Create test
        test_task = {
            "task_id": uuid.uuid4().hex,
            "test_id": str(uuid.uuid4()),
            "material_ids": [material_id],
            "title": f"Quiz по {local.stem}",
            "difficulty": args.difficulty,
        }
        # Контракт v4.1: числа вопросов в payload'е нет — размер выбирает ML.
        print(f"\n[2/2] CREATE_TEST  размер выберет ML ({args.difficulty})")
        await publish_task(redis, cfg["task_channels"]["create_test"], test_task)
        test_result = await wait_for_result(
            redis, cfg["result_channels"], test_task["task_id"], timeout_s=args.timeout,
        )
        print(json.dumps(test_result, ensure_ascii=False, indent=2))
        if test_result.get("status") == "ok" and test_result.get("test"):
            await _persist_test(
                test_result.get("test_id") or test_task["test_id"],
                test_result["test"].get("title") or test_task["title"],
                test_result["test"],
                amount_questions=len(test_result["test"].get("questions") or []),
                difficulty=args.difficulty,
            )
        return 0 if test_result.get("status") == "ok" else 1
    finally:
        await redis.aclose()


async def cmd_grade_attempt(args: argparse.Namespace) -> int:
    """Отправить grade_attempt по готовому тесту.

    Вопросы читаются из `test_questions` (их туда положил backend-listener).
    Если ответы не заданы явно — отвечаем автоматически: на single_choice
    выбираем вариант 0, на multi_choice отмечаем первые два индекса, на
    open_answer пишем текст из --open-text. Так проверяется весь путь,
    включая LLM-судью.

    ⚠️ В контракте заказчика поля `user_id` нет: студент известен по
    `attempt_id`. Эталон правильного ответа (`answer_key`) по контракту v4.1
    есть и в БД (`test_questions.answer_key`), и в payload'е ML.
    """
    redis, _minio, cfg = make_clients()
    try:
        await ensure_backend_group(redis, cfg["result_channels"])

        questions = await _fetch_questions(args.test_id)
        if not questions:
            print(f"[ERROR] no questions for test {args.test_id}", file=sys.stderr)
            return 2

        answers = _build_answers(questions, args)
        attempt_id = args.attempt_id or str(uuid.uuid4())
        user_id = args.user_id or str(STUB_USER)
        task = {
            "task_id": uuid.uuid4().hex,
            "attempt_id": attempt_id,
            "test_id": args.test_id,
            "answers": answers,
        }
        # Как настоящий backend: ответы студента пишем в БД сразу при сдаче —
        # student_answer это и есть ответ, а оценка придёт из ML позже.
        await _persist_submission(attempt_id, task["test_id"], user_id, answers)
        await publish_task(redis, cfg["task_channels"]["grade_attempt"], task)
        result = await wait_for_result(
            redis, cfg["result_channels"], task["task_id"], timeout_s=args.timeout,
        )
    finally:
        await redis.aclose()

    # В grade-ответе поля `status` нет — признак ошибки это `error`.
    if "error" not in result:
        await _persist_grading(attempt_id, result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if "error" not in result else 1


def _build_answers(questions: list[dict], args: argparse.Namespace) -> list[dict]:
    """Собрать answers[] из аргументов или автоматически."""
    if args.answer or args.text_answer or args.indexes_answer:
        answers = []
        for spec in args.answer or []:
            qid, _, idx = spec.partition("=")
            answers.append({"question_id": qid, "student_answer": {"index": int(idx)}})
        for spec in args.indexes_answer or []:
            qid, _, idxs = spec.partition("=")
            answers.append({
                "question_id": qid,
                "student_answer": {"indexes": [int(i) for i in idxs.split(",") if i]},
            })
        for spec in args.text_answer or []:
            qid, _, text = spec.partition("=")
            answers.append({"question_id": qid, "student_answer": {"text": text}})
        return answers

    answers = []
    for q in questions:
        answers.append({"question_id": q["question_id"],
                        "student_answer": _auto_answer(q, args)})
    return answers


def _auto_answer(q: dict, args: argparse.Namespace) -> dict:
    """Ответ по умолчанию для вопроса — по типу вопроса.

    Эталона правильного ответа стенд не смотрит (он лежит в `answer_key`
    в БД), поэтому автоответы «угадывают»: single_choice — вариант 0,
    multi_choice — первые два индекса. Оценка может быть неполной — это
    нормально, стенд проверяет путь прохождения, а не правильность
    оценивания.
    """
    if q["type_question"] == "open_answer":
        return {"text": args.open_text}
    if q["type_question"] == "multi_choice":
        num_options = len(q.get("options") or [])
        indexes = [i for i in (0, 1) if i < num_options]
        return {"indexes": indexes or [0]}
    return {"index": 0}


async def cmd_peek(args: argparse.Namespace) -> int:
    """Посмотреть последние N сообщений в стриме (XRANGE без consume)."""
    redis, _minio, cfg = make_clients()
    try:
        stream = args.stream
        count = args.count
        # XREVRANGE — последние N в обратном порядке
        msgs = await redis.xrevrange(stream, count=count)
        out = []
        for msg_id, fields in msgs:
            try:
                payload = json.loads(fields.get("payload", "{}"))
            except json.JSONDecodeError:
                payload = fields.get("payload")
            out.append({"id": msg_id, "payload": payload})
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    finally:
        await redis.aclose()


# ============================================================================
# Helpers
# ============================================================================

def _stable_id(*keys: str) -> str:
    """Детерминированный UUID по ключам — чтобы повторный запуск того же файла
    переиспользовал тот же material_id (и не плодил дубли в `materials`)."""
    import hashlib
    h = hashlib.md5("|".join(keys).encode("utf-8")).hexdigest()
    return str(uuid.UUID(hex=h[:32]))


def _dsn() -> str:
    return _env("DATABASE_URL", "postgresql://ml:ml@localhost:5432/ml")


async def _ensure_material_row(material_id: str, title: str, source_uri: str) -> None:
    """Создать строку `materials` (+ её родителей) — как это делает backend.

    На `material_chunks` стоит FK на `materials`, поэтому без этой строки ML
    не запишет ни одного чанка (и create_test не найдёт контекст).
    """
    conn = await db_connect(_dsn())
    try:
        await conn.execute(
            """INSERT INTO users (user_id, email, password_hash, first_name, last_name)
               VALUES ($1, $2, 'x', 'Stub', 'Backend')
               ON CONFLICT (user_id) DO NOTHING""",
            STUB_USER, f"{STUB_USER}@stub.local",
        )
        await conn.execute(
            """INSERT INTO courses (course_id, owner_id, title)
               VALUES ($1, $2, 'stub-course') ON CONFLICT (course_id) DO NOTHING""",
            STUB_COURSE, STUB_USER,
        )
        await conn.execute(
            """INSERT INTO materials
               (material_id, course_id, type_material, title, source_uri,
                status_material, material_size)
               VALUES ($1, $2, 'file', $3, $4, 'processing', 0)
               ON CONFLICT (material_id) DO NOTHING""",
            uuid.UUID(material_id), STUB_COURSE, title, source_uri,
        )
    finally:
        await conn.close()


async def _update_material_status(material_id: str, status: str | None) -> None:
    """Перевести материал в статус по ответу ML на ingest.

    `ingest:ml-to-be`: `status: "ready"` → материал готов, `status: "error"` →
    материал в ошибке (текст ошибки backend хранит у себя). Допустимые значения
    колонки `status_material`: queued, processing, ready, error.
    """
    new_status = status if status in ("ready", "error") else "error"
    conn = await db_connect(_dsn())
    try:
        await conn.execute(
            "UPDATE materials SET status_material = $2 WHERE material_id = $1",
            uuid.UUID(material_id), new_status,
        )
    finally:
        await conn.close()


async def _fetch_questions(test_id: str) -> list[dict]:
    """Вопросы теста из `test_questions` — их туда пишет backend-listener.

    Эталон (`answer_key`) в таблице может быть (контракт v4.1) — но стенду он
    не нужен: автоответы стенда «угадывают».
    """
    conn = await db_connect(_dsn())
    try:
        rows = await conn.fetch(
            """SELECT question_id::text AS qid, type_question, options
               FROM test_questions WHERE test_id = $1 ORDER BY question_id""",
            uuid.UUID(test_id),
        )
    finally:
        await conn.close()
    out: list[dict] = []
    for r in rows:
        opts = r["options"]
        out.append({
            "question_id": r["qid"],
            "type_question": r["type_question"],
            "options": list(opts) if opts else [],
        })
    return out


async def _persist_test(
    test_id: str,
    title: str,
    test: dict,
    amount_questions: str | int = "min",
    difficulty: str = "medium",
) -> None:
    """Сохранить сгенерированный тест — ровно то, что делает backend-listener.

    ML не пишет в `tests`/`test_questions`: он только возвращает JSON. Backend
    разворачивает его в строки БД. Stub повторяет эту логику, иначе
    `grade-attempt` не найдёт вопросов (grader читает их из `test_questions`).

    `source_chunk_id` пишем через подзапрос: если чанка в `material_chunks` нет
    (ML работал с in-memory store или чанк удалили) — получим NULL, а не ошибку
    FK на весь вопрос.

    `answer_key` (эталон правильного ответа, контракт v4.1) пишем, если в
    `test_questions` есть такая колонка. Колонка появится у backend'а после его
    миграции, а на старой схеме её нет — тогда вопрос пишется без эталона, и
    grader возьмёт эталон из Redis (или определит его LLM-судьёй).

    Порядок вопроса в БД сейчас не сохраняется: для него нужна колонка
    `test_questions.question_order` (требование к backend'у). ML это не мешает —
    при проверке ML сопоставляет вопросы по `question_id` и по нормализованному
    тексту.
    """
    conn = await db_connect(_dsn())
    try:
        await conn.execute(
            """INSERT INTO tests
                 (test_id, course_id, title, amount_questions, status_test, difficulty)
               VALUES ($1, $2, $3, $4, 'ready', $5)
               ON CONFLICT (test_id) DO UPDATE SET
                 title = EXCLUDED.title,
                 amount_questions = EXCLUDED.amount_questions,
                 difficulty = EXCLUDED.difficulty""",
            uuid.UUID(test_id), STUB_COURSE, title[:255], str(amount_questions), difficulty,
        )
        has_answer_key = await _has_column(conn, "test_questions", "answer_key")
        for index, q in enumerate(test.get("questions", []), start=1):
            chunk_id = q.get("source_chunk_id")
            try:
                chunk_uuid = uuid.UUID(chunk_id) if chunk_id else None
            except (ValueError, AttributeError, TypeError):
                chunk_uuid = None
            ordinal = q.get("id", index)
            question_id = uuid.uuid5(uuid.UUID(test_id), f"q:{ordinal}")
            if has_answer_key:
                await conn.execute(
                    """INSERT INTO test_questions
                         (question_id, test_id, type_question, text_question,
                          options, key_points, answer_key, source_chunk_id)
                       VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb,
                               (SELECT chunk_id FROM material_chunks WHERE chunk_id = $8::uuid))
                       ON CONFLICT (question_id) DO UPDATE SET
                         type_question = EXCLUDED.type_question,
                         text_question = EXCLUDED.text_question,
                         options = EXCLUDED.options,
                         key_points = EXCLUDED.key_points,
                         answer_key = EXCLUDED.answer_key,
                         source_chunk_id = EXCLUDED.source_chunk_id""",
                    question_id, uuid.UUID(test_id),
                    q.get("type", "single_choice"),
                    q.get("text", ""),
                    q.get("options", []),
                    q.get("key_points", []),
                    q.get("answer_key") or {},
                    chunk_uuid,
                )
            else:
                await conn.execute(
                    """INSERT INTO test_questions
                         (question_id, test_id, type_question, text_question,
                          options, key_points, source_chunk_id)
                       VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb,
                               (SELECT chunk_id FROM material_chunks WHERE chunk_id = $7::uuid))
                       ON CONFLICT (question_id) DO UPDATE SET
                         type_question = EXCLUDED.type_question,
                         text_question = EXCLUDED.text_question,
                         options = EXCLUDED.options,
                         key_points = EXCLUDED.key_points,
                         source_chunk_id = EXCLUDED.source_chunk_id""",
                    question_id, uuid.UUID(test_id),
                    q.get("type", "single_choice"),
                    q.get("text", ""),
                    q.get("options", []),
                    q.get("key_points", []),
                    chunk_uuid,
                )
    finally:
        await conn.close()


async def _has_column(conn, table: str, column: str) -> bool:
    """Есть ли колонка в таблице — по information_schema.columns.

    Нужна для `test_questions.answer_key`: колонка появляется у backend'а с его
    миграцией, а на старой схеме её нет. Без проверки INSERT падал бы с
    UndefinedColumnError.
    """
    row = await conn.fetchrow(
        """SELECT 1 AS present FROM information_schema.columns
           WHERE table_name = $1 AND column_name = $2""",
        table, column,
    )
    return row is not None


async def _persist_submission(
    attempt_id: str, test_id: str, user_id: str, answers: list[dict],
) -> None:
    """Создать попытку и строки ответов — как backend при сдаче.

    student_answer пишется здесь: это и есть ответ студента, и колонка
    NOT NULL. NOT NULL-колонки `is_correct` и `correct_answer` пока заполняем
    заглушкой (`false` и пустой JSON-объект): реальные значения придут позже,
    из вердикта ML (см. `_persist_grading`).
    """
    conn = await db_connect(_dsn())
    try:
        await conn.execute(
            """INSERT INTO users (user_id, email, password_hash, first_name, last_name)
               VALUES ($1, $2, 'x', 'Stub', 'Backend')
               ON CONFLICT (user_id) DO NOTHING""",
            uuid.UUID(user_id), f"{user_id}@stub.local",
        )
        await conn.execute(
            """INSERT INTO student_attempts (attempt_id, test_id, user_id, started_at)
               VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
               ON CONFLICT (attempt_id) DO NOTHING""",
            uuid.UUID(attempt_id), uuid.UUID(test_id), uuid.UUID(user_id),
        )
        for a in answers:
            question_id = uuid.UUID(a["question_id"])
            # uuid5 ждёт имя строкой, а question_id здесь уже UUID.
            answer_id = uuid.uuid5(uuid.UUID(attempt_id), str(question_id))
            await conn.execute(
                """INSERT INTO attempt_answers
                     (answer_id, attempt_id, question_id, is_correct, student_answer,
                      correct_answer, score, feedback)
                   VALUES ($1, $2, $3, false, $4::jsonb, '{}'::jsonb, NULL, NULL)
                   ON CONFLICT (answer_id) DO NOTHING""",
                answer_id, uuid.UUID(attempt_id), question_id,
                a.get("student_answer", {}),
            )
    finally:
        await conn.close()


async def _persist_grading(attempt_id: str, result: dict) -> None:
    """Сохранить результат проверки — эмуляция ветки grade_attempt у listener'а.

    В `items[]` вердикта ML приходят `is_correct` и эталон-объект
    `correct_answer` (та же форма, что `test_questions.answer_key`). Колонка
    JSONB, и codec'а asyncpg (см. `app/core/db.py`) пишет объект как объект:
    в БД будет, например, `{"correct_index": 1}`, а не JSON-строка.
    """
    conn = await db_connect(_dsn())
    try:
        await conn.execute(
            """UPDATE student_attempts
                 SET finished_at = CURRENT_TIMESTAMP, score_pct = $2, grade = $3
               WHERE attempt_id = $1""",
            uuid.UUID(attempt_id), result.get("score_pct"), result.get("grade"),
        )
        for item in result.get("items", []):
            correct_answer = item.get("correct_answer")
            # Колонка NOT NULL: если ML не прислал correct_answer — пишем пустой
            # объект, иначе UPDATE упал бы на нарушении ограничения.
            await conn.execute(
                """UPDATE attempt_answers
                   SET is_correct = $2, correct_answer = $3::jsonb,
                       score = $4, feedback = $5
                   WHERE attempt_id = $1 AND question_id = $6""",
                uuid.UUID(attempt_id), bool(item.get("is_correct", False)),
                correct_answer if correct_answer is not None else {},
                item.get("score"), item.get("feedback"),
                uuid.UUID(item["question_id"]),
            )
    finally:
        await conn.close()


# ============================================================================
# CLI
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Stub backend: эмулирует взаимодействие с ML-воркером через Redis Streams",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="залить файл в MinIO и отправить ingest-задачу")
    p_ing.add_argument("file", help="локальный файл (PDF, PPTX, MD, ...)")
    p_ing.add_argument("--material-id", default=None, help="UUID материала (по умолчанию — детерминированный)")
    p_ing.add_argument("--timeout", type=float, default=300.0)
    p_ing.set_defaults(func=cmd_ingest)

    p_test = sub.add_parser("create-test", help="отправить create_test-задачу")
    p_test.add_argument("--material-ids", nargs="+", required=True, help="UUID'ы материалов")
    p_test.add_argument("--title", default="Тест")
    p_test.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    p_test.add_argument("--test-id", default=None)
    p_test.add_argument("--timeout", type=float, default=300.0)
    p_test.set_defaults(func=cmd_create_test)

    p_grade = sub.add_parser("grade-attempt", help="отправить grade_attempt по готовому тесту")
    p_grade.add_argument("--test-id", required=True, help="UUID теста")
    p_grade.add_argument("--attempt-id", default=None)
    p_grade.add_argument("--user-id", default=None)
    p_grade.add_argument("--answer", action="append", metavar="QID=INDEX",
                         help="ответ на single_choice: индекс выбранного варианта (можно повторять)")
    p_grade.add_argument("--indexes-answer", action="append", metavar="QID=I,I",
                         help="ответ на multi_choice: индексы отмеченных вариантов через запятую")
    p_grade.add_argument("--text-answer", action="append", metavar="QID=TEXT",
                         help="ответ на open_answer: текст ответа (можно повторять)")
    p_grade.add_argument("--open-text", default="Не знаю",
                         help="текст для авто-ответа на open_answer, если ответы не заданы явно")
    p_grade.add_argument("--timeout", type=float, default=300.0)
    p_grade.set_defaults(func=cmd_grade_attempt)

    p_demo = sub.add_parser("demo", help="полный цикл: ingest + create_test на одном файле")
    p_demo.add_argument("--file", default="data/sample.pdf")
    p_demo.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    p_demo.add_argument("--timeout", type=float, default=300.0)
    p_demo.set_defaults(func=cmd_demo)

    p_peek = sub.add_parser("peek", help="XRANGE последних N сообщений в канале")
    p_peek.add_argument("stream", help="имя канала: <slug>:be-to-ml или <slug>:ml-to-be")
    p_peek.add_argument("--count", type=int, default=5)
    p_peek.set_defaults(func=cmd_peek)

    return p


def main() -> None:
    args = build_parser().parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        rc = asyncio.run(args.func(args))
    except KeyboardInterrupt:
        rc = 130
    except Exception as e:
        logger.exception("stub failed")
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        rc = 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
