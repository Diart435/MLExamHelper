"""Воркер: три независимых Redis-цикла, по одному на пару стримов.

У каждой задачи свой входящий стрим `ml:tasks:<канал>` и свой исходящий
`ml:results:<канал>`, поэтому циклы не мешают друг другу: зависшая генерация
теста не блокирует очередь ingest.

Порядок обработки сообщения: XADD результата → XACK задачи. Наоборот нельзя —
между ACK и XADD воркер может умереть, и backend не узнает о результате.
Сообщение, которое невозможно разобрать, ACK-ается с логом: иначе оно вернётся
по XAUTOCLAIM вечно.
"""

from __future__ import annotations

import asyncio
import json
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.contracts import (
    ContractError,
    CreateTestResult,
    CreateTestTask,
    GradeAttemptResult,
    GradeAttemptTask,
    IngestResult,
    parse_task,
)
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.core.redis_client import get_redis
from app.db.pool import close_pool
from app.handlers.create_test import process_create_test
from app.handlers.grade_attempt import process_grade_attempt
from app.handlers.ingest import process_ingest

READ_BLOCK_MS = 5000
READ_BATCH = 10


@dataclass(frozen=True)
class Channel:
    """Одна пара стримов и её обработчик."""

    name: str
    tasks_stream: str
    results_stream: str
    handler: Callable[[Any], Awaitable[Any]]


def channels_of(settings: Settings) -> list[Channel]:
    return [
        Channel(
            "ingest",
            settings.stream_tasks_ingest,
            settings.stream_results_ingest,
            process_ingest,
        ),
        Channel(
            "create_test",
            settings.stream_tasks_create_test,
            settings.stream_results_create_test,
            process_create_test,
        ),
        Channel(
            "grade_attempt",
            settings.stream_tasks_grade_attempt,
            settings.stream_results_grade_attempt,
            process_grade_attempt,
        ),
    ]


class Worker:
    def __init__(self, settings: Settings | None = None, redis: Redis | None = None) -> None:
        self._settings = settings or get_settings()
        self._redis = redis or get_redis(self._settings)
        self._channels = channels_of(self._settings)

    async def run(self) -> None:
        for channel in self._channels:
            await self._ensure_group(channel.tasks_stream)
            await self._claim_stale(channel)

        logger.info(
            f"Worker {self._settings.consumer_name} listening: "
            + ", ".join(c.tasks_stream for c in self._channels)
        )
        await asyncio.gather(*(self._loop(c) for c in self._channels))

    async def stop(self) -> None:
        await self._redis.aclose()
        await close_pool()

    async def _loop(self, channel: Channel) -> None:
        while True:
            try:
                messages = await self._read(channel)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — цикл обязан пережить любой сбой Redis
                logger.exception(f"[{channel.name}] read failed: {e}")
                await asyncio.sleep(2)
                continue

            for message_id, payload in messages:
                await self._handle_one(channel, message_id, payload)

    async def _read(self, channel: Channel) -> list[tuple[str, str]]:
        response = await self._redis.xreadgroup(
            groupname=self._settings.consumer_group,
            consumername=self._settings.consumer_name,
            streams={channel.tasks_stream: ">"},
            count=READ_BATCH,
            block=READ_BLOCK_MS,
        )
        if not response:
            return []
        # payload берём через get: сообщение без него иначе уронит чтение всего
        # батча, и вся очередь этого канала встанет до перезапуска.
        return [(mid, fields.get("payload", "")) for _, entries in response for mid, fields in entries]

    async def _handle_one(self, channel: Channel, message_id: str, payload: str) -> None:
        try:
            task = parse_task(channel.name, payload)
        except ContractError as e:
            logger.warning(f"[{channel.name}] message {message_id} rejected: {e}")
            await self._reject(channel, message_id, payload, str(e))
            return

        try:
            result = await channel.handler(task)
        except Exception as e:  # noqa: BLE001 — хендлер ловит своё, это последняя стена
            logger.exception(f"[{channel.name}] handler crashed for task {task.task_id}: {e}")
            result = _error_result(channel.name, task.task_id, str(e), task)

        await self._redis.xadd(channel.results_stream, {"payload": result.to_json()})
        await self._ack(channel, message_id)
        logger.info(f"[{channel.name}] task {task.task_id} done: status={result.status}")

    async def _reject(self, channel: Channel, message_id: str, payload: str, error: str) -> None:
        """Payload разобрать нельзя, но task_id в нём может быть — тогда backend
        хотя бы переведёт статус своей строки из queued в error."""
        task_id = _peek_task_id(payload)
        if task_id is not None:
            result = _error_result(channel.name, task_id, error, None)
            await self._redis.xadd(channel.results_stream, {"payload": result.to_json()})
        await self._ack(channel, message_id)

    async def _ack(self, channel: Channel, message_id: str) -> None:
        await self._redis.xack(channel.tasks_stream, self._settings.consumer_group, message_id)

    async def _ensure_group(self, stream: str) -> None:
        try:
            await self._redis.xgroup_create(
                stream, self._settings.consumer_group, id="0-0", mkstream=True
            )
            logger.info(f"Created consumer group {self._settings.consumer_group} on {stream}")
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            logger.info(f"Consumer group {self._settings.consumer_group} already exists on {stream}")

    async def _claim_stale(self, channel: Channel) -> None:
        """Забрать сообщения, которые остались в pending — например, воркер убили."""
        claimed = await self._redis.xautoclaim(
            channel.tasks_stream,
            self._settings.consumer_group,
            self._settings.consumer_name,
            min_idle_time=self._settings.worker_claim_idle_ms,
            count=READ_BATCH,
        )
        entries = claimed[1] if isinstance(claimed, (list, tuple)) else []
        for message_id, fields in entries:
            logger.info(f"[{channel.name}] claimed stale message {message_id}")
            await self._handle_one(channel, message_id, fields.get("payload", ""))


def _error_result(channel: str, task_id: str, error: str, task: Any) -> Any:
    """Собрать status=error под конкретный тип задачи. Идентификаторы нужны
    backend'у, чтобы обновить нужную строку, поэтому подставляем известное."""
    if isinstance(task, CreateTestTask):
        return CreateTestResult.err(task_id, error, task.test_id)
    if isinstance(task, GradeAttemptTask):
        return GradeAttemptResult.err(task_id, error, task.attempt_id, task.test_id)
    return IngestResult.err(task_id, error)


def _peek_task_id(payload: str) -> str | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    task_id = data.get("task_id")
    return None if task_id in (None, "") else str(task_id)


async def main() -> None:
    settings = get_settings()
    setup_logging()
    worker = Worker(settings)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # ProactorEventLoop на Windows без signal handlers — в Docker это
            # не воспроизводится, но локальный запуск падать не должен.
            logger.warning("Signal handlers unavailable on this platform")

    runner = asyncio.create_task(worker.run())
    await stop.wait()
    logger.info("Shutting down")
    runner.cancel()
    try:
        await runner
    except asyncio.CancelledError:
        pass
    await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())