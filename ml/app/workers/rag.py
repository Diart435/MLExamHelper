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
2. В цикле: XREADGROUP с блокировкой 5s сразу по всем каналам. Отдельно и не
   чаще раза в `worker_claim_interval_ms` выполняется reclaim-проход —
   XAUTOCLAIM забирает зависшие сообщения (pending-список).
3. Для каждого сообщения: тип задачи берётся из ИМЕНИ КАНАЛА → роутит →
   публикует результат в зеркальный канал результата → XACK в канал задачи →
   XDEL из канала задачи (чтобы стрим задач не рос бесконечно).
4. На любую непредвиденную ошибку в цикле — пауза 5s, чтобы не зациклиться.

Backend хранилища выбирается через env `VECTOR_STORE_BACKEND` (mem | pg).
См. `app/services/vector_store.py::create_vector_store`.
"""

import asyncio
import json
import time

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import ResponseError, TimeoutError as RedisTimeoutError

from app.contracts import (
    TASK_TYPES,
    channel_task_type,
    mirror_channel,
    result_channel,
    task_channel,
)
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis_client import get_redis
from app.handlers.rag import process_create_test, process_grade_attempt, process_ingest, process_question
from app.services.answer_store import AnswerStore
from app.services.llm import payloads_enabled
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
        self.group = s.consumer_group
        self.consumer = s.consumer_name
        self.worker_claim_idle_ms = s.worker_claim_idle_ms
        self.worker_claim_max_attempts = s.worker_claim_max_attempts
        self.worker_claim_interval_ms = s.worker_claim_interval_ms
        # id сообщений, для которых результат УЖЕ опубликован, но XACK не прошёл:
        # такие сообщения нельзя переотправлять ошибкой — успешный результат
        # уже у backend'а.
        self._published: set[str] = set()
        # Время последнего reclaim-прохода (None = ещё не было). Первый проход
        # выполняется сразу после старта, чтобы воркер подхватил pending.
        self._last_reclaim_at: float | None = None
        # Эталоны правильных ответов: по контракту заказчика они не отдаются
        # наружу и в БД backend'а их нет, поэтому ML держит их у себя в Redis.
        self.answer_store = AnswerStore(self.redis)
        # Один тип задачи — один канал в каждом направлении.
        self.task_channels = {t: task_channel(t) for t in TASK_TYPES}
        self.result_channels = {t: result_channel(t) for t in TASK_TYPES}
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
                    await self._maybe_reclaim()
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

    async def _maybe_reclaim(self) -> None:
        """Выполнить reclaim-проход, но не чаще раза в `worker_claim_interval_ms`.

        Первый выход после старта проход обязателен: свежий воркер должен сразу
        подхватить сообщения, оставшиеся в pending-списке (например, после
        падения предыдущего воркера). Дальше — по интервалу, чтобы не дёргать
        Redis XAUTOCLAIM на каждом цикле чтения.
        """
        now = time.monotonic()
        if (
            self._last_reclaim_at is not None
            and (now - self._last_reclaim_at) * 1000 < self.worker_claim_interval_ms
        ):
            return
        self._last_reclaim_at = now
        await self._reclaim_pending()

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
                    idle=self.worker_claim_idle_ms,
                )
                if not pending:
                    continue
                deliveries = {p["message_id"]: p["times_delivered"] for p in pending}

                response = await self.redis.xautoclaim(
                    name=channel,
                    groupname=self.group,
                    consumername=self.consumer,
                    min_idle_time=self.worker_claim_idle_ms,
                    start_id="0-0",
                    count=self.RECLAIM_BATCH,
                )
                # [next-start-id, entries, deleted-ids] — deleted-ids есть
                # только в Redis 7+, поэтому берём entries по индексу.
                entries = response[1]
                for msg_id, fields in entries:
                    times = deliveries.get(msg_id, 1)
                    if times > self.worker_claim_max_attempts:
                        await self._drop_poison(channel, msg_id, fields, times)
                        continue
                    logger.warning(
                        f"Reclaimed message {msg_id} on {channel} "
                        f"(idle, {times} deliveries so far)"
                    )
                    await self._handle(msg_id, fields, channel)
            except Exception:
                logger.exception(f"Reclaim failed on {channel}")

    async def _drop_poison(
        self, channel: str, msg_id: str, fields: dict, times: int
    ) -> None:
        """Сообщение, которое не удалось обработать слишком много раз.

        Backend не должен вечно ждать вердикта, поэтому публикуем ошибочный
        результат в зеркальный канал результата этого типа задачи (формат —
        как у `_error_result`), а затем подтверждаем сообщение и удаляем его из
        канала задач.

        Исключение: если результат по этому сообщению УЖЕ опубликован (упал
        только XACK) — ошибку не публикуем, иначе она испортила бы успешный
        результат, который backend уже получил.
        """
        task_type = self.channel_types.get(channel) or channel_task_type(channel)
        if msg_id in self._published:
            logger.error(
                f"Message {msg_id} on {channel} was delivered {times} times, but the "
                f"result was already published — acking and deleting without a new error"
            )
        else:
            logger.error(
                f"Message {msg_id} on {channel} was delivered {times} times — "
                f"publishing an error result"
            )
            task = self._task_from_payload(fields)
            await self._publish_error(
                task_type,
                msg_id,
                channel,
                self._error_result(
                    task_type,
                    task,
                    f"message was delivered {times} times and could not be processed",
                ),
            )

        await self.redis.xack(channel, self.group, msg_id)
        self._published.discard(msg_id)
        await self._delete(channel, msg_id)

    @staticmethod
    def _task_from_payload(fields: dict) -> dict:
        """Разобрать payload'а сообщения в задачу (пустой dict, если не читается)."""
        payload = fields.get("payload", "{}")
        try:
            task = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return {}
        return task if isinstance(task, dict) else {}

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
            return await process_create_test(task, self.rag, answer_store=self.answer_store)
        if task_type == "grade_attempt":
            return await process_grade_attempt(task, answer_store=self.answer_store)
        return self._error_result(
            task_type, task, f"unknown task type: {task_type!r}"
        )

    @staticmethod
    def _error_result(task_type: str, task: dict, error: str) -> dict:
        """Ошибка в форме, которую ждёт канал результата этого типа задачи.

        Идентификаторы берутся из payload'а задачи, и они у разных типов
        разные: у `ingest` это `material_id` (поля `task_id` в контракте
        нет вовсе), у `create_test` и `grade_attempt` — `task_id` плюс
        `test_id`/`attempt_id`, если известны. Идентификатор нужен backend'у,
        чтобы поставить в «ошибка» правильную строку.

        В `grade-test:ml-to-be` поля `status` нет — там признак ошибки само
        наличие `error`. Во всех остальных каналах `status: "error"` обязателен.
        """
        result: dict = {}
        if task_type == "ingest":
            material_id = str(task.get("material_id") or "")
            if material_id:
                result["material_id"] = material_id
        else:
            for field in ("task_id", "test_id", "attempt_id"):
                value = str(task.get(field) or "")
                if value:
                    result[field] = value
        if task_type != "grade_attempt":
            result["status"] = "error"
        result["error"] = error
        return result

    async def _handle(self, msg_id: str, fields: dict, channel: str) -> None:
        task_type = self.channel_types.get(channel) or channel_task_type(channel)
        result_channel = self.result_channels.get(task_type) or mirror_channel(channel)
        payload = fields.get("payload", "{}")
        try:
            task = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Bad payload in msg {msg_id}: {payload!r}")
            # Отвечаем ошибкой вместо молчаливого XACK: сообщение без ответа
            # backend'у неотличимо от «задача ещё в работе».
            await self._publish(
                self._error_result(task_type, {}, f"payload is not valid JSON: {e}"),
                msg_id, channel, result_channel,
            )
            return

        if not isinstance(task, dict):
            await self._publish(
                self._error_result(
                    task_type, {},
                    f"payload must be a JSON object, got {type(task).__name__}",
                ),
                msg_id, channel, result_channel,
            )
            return

        try:
            result = await self._route(task_type, task)
        except Exception as e:
            logger.exception(f"Handler crashed for msg {msg_id}")
            result = self._error_result(
                task_type, task, f"{type(e).__name__}: {e}"
            )

        await self._publish(result, msg_id, channel, result_channel)

    async def _publish(
        self,
        result: dict,
        msg_id: str,
        task_channel: str,
        result_channel: str,
    ) -> None:
        """Опубликовать результат, подтвердить исходное сообщение и удалить его.

        Порядок: XADD (канал результата) → XACK (канал задачи) → XDEL (канал
        задачи). XDEL нужен, чтобы стрим задач не рос бесконечно.

        Публикация, подтверждение и удаление — разные шаги с разными
        последствиями:
        - не опубликовали → сообщение остаётся в pending, его заберёт reclaim;
        - опубликовали, но не подтвердили → задача выполнится ещё раз, backend
          получит результат дважды. Поэтому запись в БД у backend'а идемпотентна;
        - не удалили → стиль канала чуть больше, но на семантику не влияет.
        """
        try:
            payload_text = json.dumps(result, ensure_ascii=False)
            # Что уходит в Redis — владелец просит видеть это целиком.
            if payloads_enabled():
                logger.info(
                    "[Redis] → channel={} payload: {}",
                    result_channel,
                    json.dumps(result, ensure_ascii=False, indent=2),
                )
            await self.redis.xadd(
                result_channel,
                {"payload": payload_text},
            )
        except Exception:
            logger.exception(f"Failed to publish result for msg {msg_id}")
            # НЕ ack'аем: результат не опубликован, сообщение должно вернуться
            # в обработку через reclaim.
            return

        # Результат опубликован, но XACK ещё не прошёл: помечаем сообщение,
        # чтобы poison-ветка не отправила поверх успешного результата ошибку.
        self._published.add(msg_id)

        try:
            await self._ack(task_channel, msg_id)
        except Exception:
            logger.exception(
                f"Published but not acked msg {msg_id} — the task will run again"
            )
            # id остаётся в _published: результат backend'у уже ушёл, и
            # poison-ветка не должна слать поверх него ошибку.
            return
        self._published.discard(msg_id)

        await self._delete(task_channel, msg_id)

        logger.info(
            f"Processed task {result.get('task_id', '?')} ({task_channel}) "
            f"from msg {msg_id}"
        )

    async def _publish_error(
        self,
        task_type: str,
        msg_id: str,
        task_channel: str,
        result: dict,
    ) -> None:
        """Опубликовать ошибочный результат БЕЗ подтверждения исходного сообщения.

        Нужен для poison-ветки: результат backend'у отправить надо (иначе он
        ждёт вердикта вечно), но исходное сообщение подтверждает и удаляет
        вызывающий код — так реже расходится логика XACK/XDEL.
        """
        result_channel = self.result_channels.get(task_type) or mirror_channel(task_channel)
        try:
            if payloads_enabled():
                logger.info(
                    "[Redis] → channel={} payload (error): {}",
                    result_channel,
                    json.dumps(result, ensure_ascii=False, indent=2),
                )
            await self.redis.xadd(
                result_channel,
                {"payload": json.dumps(result, ensure_ascii=False)},
            )
        except Exception:
            logger.exception(f"Failed to publish error result for msg {msg_id}")
            return
        logger.info(f"Published error result for msg {msg_id} to {result_channel}")

    async def _delete(self, task_channel: str, msg_id: str) -> None:
        """XDEL обработанного сообщения из канала задач.

        Стим задач должен оставаться плоским: без удаления он растёт
        бесконечно. Ошибка здесь не критична — сообщение уже подтверждено,
        единственное последствие — канал станет чуть больше.
        """
        try:
            await self.redis.xdel(task_channel, msg_id)
        except Exception:
            logger.exception(f"Failed to delete msg {msg_id} from {task_channel}")

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
