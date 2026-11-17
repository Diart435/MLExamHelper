"""
Redis Streams consumer for RAG tasks.

Запуск: python -m app.workers.rag

Использует consumer groups (XREADGROUP), что позволяет масштабироваться
горизонтально при наличии shared vector store (pgvector). С in-memory
backend'ом — single worker для MVP, иначе несколько процессов не поделят
состояние.

Поток:
1. При старте создаёт consumer group на КАЖДОМ канале задач (если уже есть —
   игнорирует BUSYGROUP).
2. В цикле: XAUTOCLAIM забирает зависшие сообщения (pending-список), затем
   XREADGROUP с блокировкой 5s сразу по всем каналам.
3. Для каждого сообщения: тип задачи берётся из ИМЕНИ КАНАЛА → роутит →
   публикует результат в зеркальный канал результата → XACK в канал задачи.
4. На любую непредвиденную ошибку в цикле — пауза 5s, чтобы не зациклиться.

Backend хранилища выбирается через env `VECTOR_STORE_BACKEND` (mem | pg).
См. `app/services/vector_store.py::create_vector_store`.
"""

import asyncio
import json

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import ResponseError, TimeoutError as RedisTimeoutError

from app.contracts import TASK_TYPES, channel_task_type, stream_channel
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis_client import get_redis
from app.handlers.rag import process_create_test, process_grade_attempt, process_ingest, process_question
from app.services.rag import RAGService


class RAGWorker:
    BLOCK_MS = 5000
    RETRY_PAUSE_S = 5
    BATCH_COUNT = 1
    RECLAIM_BATCH = 10
    ACK_RETRIES = 3

    def __init__(self, rag: RAGService | None = None, redis: Redis | None = None) -> None:
        s = get_settings()
        self.rag = rag or RAGService()
        self.redis = redis or get_redis(s)
        # Префиксы каналов: 'ml-tasks' → 'ml-tasks:create_test' и т.д.
        self.tasks_prefix = s.ml_tasks_stream
        self.results_prefix = s.ml_results_stream
        self.group = s.consumer_group
        self.consumer = s.consumer_name
        self.reclaim_idle_ms = s.reclaim_idle_ms
        self.reclaim_max_attempts = s.reclaim_max_attempts
        # Один тип задачи — один канал в каждом направлении.
        self.task_channels = {t: stream_channel(self.tasks_prefix, t) for t in TASK_TYPES}
        self.result_channels = {t: stream_channel(self.results_prefix, t) for t in TASK_TYPES}
        self.channel_types = {ch: t for t, ch in self.task_channels.items()}

    async def ensure_group(self) -> None:
        for channel in self.task_channels.values():
            try:
                await self.redis.xgroup_create(
                    name=channel,
                    groupname=self.group,
                    id="0",
                    mkstream=True,
                )
                logger.info(f"Created consumer group '{self.group}' on '{channel}'")
            except ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"Consumer group '{self.group}' already exists on '{channel}'")
                else:
                    raise

    async def run(self) -> None:
        await self.ensure_group()
        logger.info(
            f"Worker '{self.consumer}' started, listening on "
            f"{sorted(self.task_channels.values())} -> {sorted(self.result_channels.values())}"
        )
        try:
            while True:
                try:
                    await self._reclaim_pending()
                except Exception:
                    logger.exception("reclaim pass failed")

                try:
                    msgs = await self.redis.xreadgroup(
                        groupname=self.group,
                        consumername=self.consumer,
                        streams={ch: ">" for ch in self.task_channels.values()},
                        count=self.BATCH_COUNT,
                        block=self.BLOCK_MS,
                    )
                except asyncio.CancelledError:
                    raise
                except (TimeoutError, RedisTimeoutError):
                    # redis-py 8.x: XREADGROUP BLOCK при таймауте кидает
                    # redis.exceptions.TimeoutError (НЕ встроенный TimeoutError).
                    # Трактовка: «сообщений нет», идём на следующий круг.
                    continue
                except Exception:
                    logger.exception("xreadgroup failed, retrying")
                    await asyncio.sleep(self.RETRY_PAUSE_S)
                    continue

                if not msgs:
                    continue
                for stream, entries in msgs:
                    for msg_id, fields in entries:
                        await self._handle(msg_id, fields, stream)
        finally:
            await self.redis.aclose()
            logger.info("Worker stopped")

    async def _reclaim_pending(self) -> None:
        """Забрать сообщения, оставшиеся в pending-списке канала.

        XREADGROUP с ">" отдаёт только новые сообщения: если воркер упал между
        чтением и XACK, задача навсегда остаётся в pending и её больше никто не
        прочитает. XAUTOCLAIM возвращает такие сообщения в обработку.

        Доставка получается "как минимум один раз": та же задача может быть
        выполнена повторно, поэтому запись результата в БД должна быть
        идемпотентной (backend пишет по детерминированным id + ON CONFLICT).
        """
        for channel in self.task_channels.values():
            try:
                pending = await self.redis.xpending_range(
                    channel,
                    self.group,
                    "-",
                    "+",
                    self.RECLAIM_BATCH,
                    idle=self.reclaim_idle_ms,
                )
                if not pending:
                    continue
                deliveries = {p["message_id"]: p["times_delivered"] for p in pending}

                response = await self.redis.xautoclaim(
                    name=channel,
                    groupname=self.group,
                    consumername=self.consumer,
                    min_idle_time=self.reclaim_idle_ms,
                    start_id="0-0",
                    count=self.RECLAIM_BATCH,
                )
                # [next-start-id, entries, deleted-ids] — deleted-ids есть
                # только в Redis 7+, поэтому берём entries по индексу.
                entries = response[1]
                for msg_id, fields in entries:
                    times = deliveries.get(msg_id, 1)
                    if times > self.reclaim_max_attempts:
                        logger.error(
                            f"Message {msg_id} on {channel} was delivered {times} times — "
                            f"dropping it without a result"
                        )
                        await self.redis.xack(channel, self.group, msg_id)
                        continue
                    logger.warning(
                        f"Reclaimed message {msg_id} on {channel} "
                        f"(idle, {times} deliveries so far)"
                    )
                    await self._handle(msg_id, fields, channel)
            except Exception:
                logger.exception(f"Reclaim failed on {channel}")

    async def _route(self, task_type: str, task: dict) -> dict:
        """Dispatch по типу задачи. Тип приходит из имени канала.

        Добавляешь новый тип — добавляешь ветку и handler (и канал, который
        заведётся из реестра TASK_TYPES).
        """
        if task_type == "ingest":
            return await process_ingest(task, self.rag)
        if task_type == "rag_question":
            return await process_question(task, self.rag)
        if task_type == "create_test":
            return await process_create_test(task, self.rag)
        if task_type == "grade_attempt":
            return await process_grade_attempt(task)
        return {
            "task_id": str(task.get("task_id", "")),
            "status": "error",
            "error": f"unknown task type: {task_type!r}",
        }

    async def _handle(self, msg_id: str, fields: dict, channel: str) -> None:
        task_type = self.channel_types.get(channel) or channel_task_type(channel)
        result_channel = self.result_channels.get(task_type, self.results_prefix)
        payload = fields.get("payload", "{}")
        try:
            task = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Bad payload in msg {msg_id}: {payload!r}")
            # Отвечаем ошибкой вместо молчаливого XACK: сообщение без ответа
            # backend'у неотличимо от «задача ещё в работе».
            await self._publish(
                {
                    "task_id": "",
                    "status": "error",
                    "error": f"payload is not valid JSON: {e}",
                },
                msg_id, channel, result_channel,
            )
            return

        if not isinstance(task, dict):
            await self._publish(
                {
                    "task_id": "",
                    "status": "error",
                    "error": f"payload must be a JSON object, got {type(task).__name__}",
                },
                msg_id, channel, result_channel,
            )
            return

        try:
            result = await self._route(task_type, task)
        except Exception as e:
            logger.exception(f"Handler crashed for msg {msg_id}")
            result = {
                "task_id": str(task.get("task_id", "")),
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
            }
        result["input_msg_id"] = msg_id

        await self._publish(result, msg_id, channel, result_channel)

    async def _publish(
        self,
        result: dict,
        msg_id: str,
        task_channel: str,
        result_channel: str,
    ) -> None:
        """Опубликовать результат в канал результата и подтвердить исходное сообщение.

        Публикация и подтверждение — разные шаги с разными последствиями:
        - не опубликовали → сообщение остаётся в pending, его заберёт reclaim;
        - опубликовали, но не подтвердили → задача выполнится ещё раз, backend
          получит результат дважды. Поэтому запись в БД у backend'а идемпотентна.
        """
        try:
            await self.redis.xadd(
                result_channel,
                {"payload": json.dumps(result, ensure_ascii=False)},
            )
        except Exception:
            logger.exception(f"Failed to publish result for msg {msg_id}")
            # НЕ ack'аем: результат не опубликован, сообщение должно вернуться
            # в обработку через reclaim.
            return

        try:
            await self._ack(task_channel, msg_id)
        except Exception:
            logger.exception(
                f"Published but not acked msg {msg_id} — the task will run again"
            )
            return

        logger.info(
            f"Processed task {result.get('task_id', '?')} ({task_channel}) "
            f"from msg {msg_id}"
        )

    async def _ack(self, task_channel: str, msg_id: str) -> None:
        """XACK в тот канал, откуда пришло сообщение. Несколько попыток —
        дешевле, чем повторное выполнение задачи."""
        for attempt in range(1, self.ACK_RETRIES + 1):
            try:
                await self.redis.xack(task_channel, self.group, msg_id)
                return
            except Exception:
                if attempt == self.ACK_RETRIES:
                    raise
                await asyncio.sleep(0.2 * attempt)


async def main() -> None:
    setup_logging()
    worker = RAGWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
