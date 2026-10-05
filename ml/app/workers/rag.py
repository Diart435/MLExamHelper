"""
Redis Streams consumer for RAG tasks.

Запуск: python -m app.workers.rag

Использует consumer groups (XREADGROUP), что позволит масштабироваться
горизонтально после перехода на pgvector. Сейчас single worker для MVP
(InMemoryVectorStore живёт в одном процессе).

Поток:
1. При старте создаёт consumer group (если уже есть — игнорирует BUSYGROUP).
2. В цикле: XREADGROUP с блокировкой 5s.
3. Для каждого сообщения: парсит payload → роутит по type (через handlers/rag.py) →
   публикует в ml-results → XACK.
4. На любую непредвиденную ошибку в цикле — пауза 5s, чтобы не зациклиться.
"""

import asyncio
import json

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis_client import get_redis
from app.handlers.rag import process_ingest, process_question
from app.services.rag import RAGService


class RAGWorker:
    BLOCK_MS = 5000
    RETRY_PAUSE_S = 5
    BATCH_COUNT = 1

    def __init__(self, rag: RAGService | None = None, redis: Redis | None = None) -> None:
        s = get_settings()
        self.rag = rag or RAGService()
        self.redis = redis or get_redis(s)
        self.stream_in = s.ml_tasks_stream
        self.stream_out = s.ml_results_stream
        self.group = s.consumer_group
        self.consumer = s.consumer_name

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(
                name=self.stream_in,
                groupname=self.group,
                id="0",
                mkstream=True,
            )
            logger.info(f"Created consumer group '{self.group}' on '{self.stream_in}'")
        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Consumer group '{self.group}' already exists")
            else:
                raise

    async def run(self) -> None:
        await self.ensure_group()
        logger.info(
            f"Worker '{self.consumer}' started, listening on '{self.stream_in}' -> '{self.stream_out}'"
        )
        try:
            while True:
                try:
                    msgs = await self.redis.xreadgroup(
                        groupname=self.group,
                        consumername=self.consumer,
                        streams={self.stream_in: ">"},
                        count=self.BATCH_COUNT,
                        block=self.BLOCK_MS,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("xreadgroup failed, retrying")
                    await asyncio.sleep(self.RETRY_PAUSE_S)
                    continue

                if not msgs:
                    continue
                for _stream, entries in msgs:
                    for msg_id, fields in entries:
                        await self._handle(msg_id, fields)
        finally:
            await self.redis.aclose()
            logger.info("Worker stopped")

    async def _route(self, task: dict) -> dict:
        """Dispatch by 'type' field. Добавляешь новый тип — добавляешь ветку и handler."""
        task_type = task.get("type")
        task_id = task.get("task_id", "")
        if task_type == "ingest":
            return await process_ingest(task, self.rag)
        if task_type == "rag_question":
            return await process_question(task, self.rag)
        return {
            "task_id": task_id,
            "status": "error",
            "error": f"unknown task type: {task_type!r}",
        }

    async def _handle(self, msg_id: str, fields: dict) -> None:
        payload = fields.get("payload", "{}")
        try:
            task = json.loads(payload)
        except json.JSONDecodeError:
            logger.error(f"Bad payload in msg {msg_id}: {payload!r}")
            await self.redis.xack(self.stream_in, self.group, msg_id)
            return

        result = await self._route(task)
        result["input_msg_id"] = msg_id

        try:
            await self.redis.xadd(
                self.stream_out,
                {"payload": json.dumps(result, ensure_ascii=False)},
            )
            await self.redis.xack(self.stream_in, self.group, msg_id)
            logger.info(
                f"Processed task {task.get('task_id', '?')} ({task.get('type')}) from msg {msg_id}"
            )
        except Exception:
            logger.exception(f"Failed to publish/ack msg {msg_id}")
            # НЕ ack'аем — сообщение останется в pending и может быть перечитано


async def main() -> None:
    setup_logging()
    worker = RAGWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
