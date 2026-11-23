"""Тесты Redis-воркера: каналы, маршрутизация и ответы на любую ошибку.

Redis мокается: проверяем, что воркер читает ВСЕ каналы задач, отвечает в
зеркальный канал результата и XACK'ает исходный канал. Тип задачи определяется
именем канала, поэтому в payload поля `type` нет.
"""

from __future__ import annotations

import json

import pytest

from app.contracts import TASK_TYPES, result_channel, task_channel
from app.services.answer_store import AnswerStore
from app.workers.rag import RAGWorker


class FakeRedis:
    def __init__(self):
        self.published: list[dict] = []
        self.acked: list[tuple[str, str]] = []
        self.deleted: list[tuple[str, str]] = []
        self.groups: list[str] = []
        self.read_streams: dict | None = None
        self.pending: dict[str, list[dict]] = {}
        self.claimed: dict[str, list[tuple[str, dict]]] = {}
        self.autoclaim_calls: list[dict] = []

    async def xadd(self, stream, fields):
        self.published.append({"stream": stream, "payload": json.loads(fields["payload"])})
        return b"1-1"

    async def xack(self, stream, group, msg_id):
        self.acked.append((stream, msg_id))
        return 1

    async def xdel(self, stream, msg_id):
        self.deleted.append((stream, msg_id))
        return 1

    async def xgroup_create(self, **kwargs):
        self.groups.append(kwargs["name"])
        return True

    async def xreadgroup(self, **kwargs):
        self.read_streams = kwargs.get("streams")
        return []

    async def xpending_range(self, name, groupname, min, max, count, consumername=None, idle=None):
        return self.pending.get(name, [])

    async def xautoclaim(self, name, groupname, consumername, min_idle_time,
                         start_id="0-0", count=None, justid=False):
        self.autoclaim_calls.append({"stream": name, "idle": min_idle_time})
        return ["0-0", self.claimed.get(name, []), []]

    async def aclose(self):
        return None


def _worker() -> tuple[RAGWorker, FakeRedis]:
    redis = FakeRedis()
    worker = RAGWorker.__new__(RAGWorker)
    worker.rag = None
    worker.redis = redis
    worker.group = "ml-workers"
    worker.consumer = "w1"
    worker.worker_claim_idle_ms = 30_000
    worker.worker_claim_max_attempts = 5
    worker.worker_claim_interval_ms = 60_000
    # id сообщений, для которых результат уже опубликован, но XACK не прошёл.
    worker._published = set()
    # Время последнего reclaim-прохода: None = прохода ещё не было.
    worker._last_reclaim_at = None
    worker.task_channels = {t: task_channel(t) for t in TASK_TYPES}
    worker.result_channels = {t: result_channel(t) for t in TASK_TYPES}
    worker.channel_types = {ch: t for t, ch in worker.task_channels.items()}
    # Хранилище эталонов ответов: по контракту заказчика эталона нет ни в
    # payload'е, ни в БД backend'а — ML держит его у себя в Redis.
    worker.answer_store = AnswerStore(redis)
    return worker, redis


class TestWorkerChannels:
    def test_one_channel_per_task_type(self):
        worker, _ = _worker()
        assert set(worker.task_channels) == set(TASK_TYPES)
        assert worker.task_channels["ingest"] == "ingest:be-to-ml"
        assert worker.task_channels["create_test"] == "create-test:be-to-ml"
        assert worker.task_channels["grade_attempt"] == "grade-test:be-to-ml"

    def test_result_channels_are_mirrors(self):
        worker, _ = _worker()
        assert worker.result_channels["ingest"] == "ingest:ml-to-be"
        assert worker.result_channels["create_test"] == "create-test:ml-to-be"
        assert worker.result_channels["grade_attempt"] == "grade-test:ml-to-be"

    @pytest.mark.asyncio
    async def test_group_created_on_every_task_channel(self):
        worker, redis = _worker()
        await worker.ensure_group()
        assert set(redis.groups) == set(worker.task_channels.values())


class TestWorkerRouting:
    @pytest.mark.asyncio
    async def test_unknown_type_answered_with_error(self):
        worker, _ = _worker()
        result = await worker._route("wat", {"task_id": "t1"})
        assert result["status"] == "error"
        assert "unknown task type" in result["error"]

    @pytest.mark.asyncio
    async def test_broken_json_gets_error_answer_not_silent_ack(self):
        worker, redis = _worker()
        await worker._handle("1-1", {"payload": "{не json"}, "ingest:be-to-ml")
        assert len(redis.published) == 1
        payload = redis.published[0]["payload"]
        assert payload["status"] == "error"
        assert "not valid JSON" in payload["error"]
        assert redis.acked == [("ingest:be-to-ml", "1-1")]

    @pytest.mark.asyncio
    async def test_non_object_payload_gets_error_answer(self):
        worker, redis = _worker()
        await worker._handle("1-2", {"payload": "[1, 2, 3]"}, "ingest:be-to-ml")
        payload = redis.published[0]["payload"]
        assert payload["status"] == "error"
        assert "JSON object" in payload["error"]
        assert redis.acked == [("ingest:be-to-ml", "1-2")]

    @pytest.mark.asyncio
    async def test_handler_crash_gets_error_answer(self):
        worker, redis = _worker()

        async def boom(task_type, task):
            raise RuntimeError("kaboom")

        worker._route = boom  # type: ignore[method-assign]
        await worker._handle("2-2", {"payload": json.dumps(
            {"task_id": "t9"}
        )}, "create-test:be-to-ml")
        payload = redis.published[0]["payload"]
        assert payload["status"] == "error"
        assert payload["task_id"] == "t9"
        assert "kaboom" in payload["error"]

    @pytest.mark.asyncio
    async def test_ingest_error_carries_material_id_not_task_id(self):
        """У `ingest` идентификатор — `material_id`: backend должен знать, какой
        материал поставить в «ошибка». Поля `task_id` в контракте нет вовсе."""
        worker, redis = _worker()

        async def boom(task_type, task):
            raise RuntimeError("kaboom")

        worker._route = boom  # type: ignore[method-assign]
        await worker._handle("2-3", {"payload": json.dumps(
            {"material_id": "m1", "storage_key": "s3://bucket/f.pdf"}
        )}, "ingest:be-to-ml")
        payload = redis.published[0]["payload"]
        assert payload["status"] == "error"
        assert payload["material_id"] == "m1"
        assert "task_id" not in payload
        assert "kaboom" in payload["error"]

    @pytest.mark.asyncio
    async def test_create_test_error_carries_task_and_test_ids(self):
        """У `create_test` в ошибку идут `task_id` и `test_id` — по ним backend
        ставит в «ошибка» нужную строку."""
        worker, redis = _worker()

        async def boom(task_type, task):
            raise RuntimeError("kaboom")

        worker._route = boom  # type: ignore[method-assign]
        await worker._handle("2-4", {"payload": json.dumps(
            {"task_id": "t9", "test_id": "te9"}
        )}, "create-test:be-to-ml")
        payload = redis.published[0]["payload"]
        assert payload["status"] == "error"
        assert payload["task_id"] == "t9"
        assert payload["test_id"] == "te9"

    @pytest.mark.asyncio
    async def test_grade_error_answer_has_no_status_field(self):
        """В `grade-test:ml-to-be` поля `status` нет по контракту: признак
        ошибки — само наличие `error`. Backend читает результат строго."""
        worker, redis = _worker()
        await worker._handle("5-5", {"payload": "{не json"}, "grade-test:be-to-ml")
        payload = redis.published[0]["payload"]
        assert "status" not in payload
        assert "not valid JSON" in payload["error"]
        assert redis.published[0]["stream"] == "grade-test:ml-to-be"
        assert redis.acked == [("grade-test:be-to-ml", "5-5")]

    @pytest.mark.asyncio
    async def test_other_channels_keep_status_in_error_answer(self):
        """У остальных каналов `status: "error"` обязателен — backend различает
        ветки по нему."""
        worker, redis = _worker()
        await worker._handle("5-6", {"payload": "{не json"}, "create-test:be-to-ml")
        assert redis.published[0]["payload"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_result_carries_no_input_msg_id(self):
        """`input_msg_id` в контракте заказчика нет: воркер его не добавляет.
        Корреляция идёт по task_id (и material_id у ingest)."""
        worker, redis = _worker()
        worker._route = _async_result  # type: ignore[method-assign]
        await worker._handle("3-3", {"payload": json.dumps(
            {"task_id": "t1"}
        )}, "ingest:be-to-ml")
        assert "input_msg_id" not in redis.published[0]["payload"]

    @pytest.mark.asyncio
    async def test_result_goes_to_mirrored_channel_and_ack_to_source(self):
        worker, redis = _worker()
        worker._route = _async_result  # type: ignore[method-assign]
        await worker._handle("4-4", {"payload": json.dumps(
            {"task_id": "t1"}
        )}, "create-test:be-to-ml")
        assert redis.published[0]["stream"] == "create-test:ml-to-be"
        assert redis.acked == [("create-test:be-to-ml", "4-4")]

    @pytest.mark.asyncio
    async def test_unknown_channel_gets_error_in_mirror_and_is_acked(self):
        worker, redis = _worker()
        await worker._handle("4-5", {"payload": json.dumps(
            {"task_id": "t1"}
        )}, "foo:be-to-ml")
        assert len(redis.published) == 1
        assert redis.published[0]["stream"] == "foo:ml-to-be"
        assert redis.published[0]["payload"]["status"] == "error"
        assert "unknown task type" in redis.published[0]["payload"]["error"]
        assert redis.acked == [("foo:be-to-ml", "4-5")]

    @pytest.mark.asyncio
    async def test_payload_has_no_type_field(self):
        """Тип задачи задаёт канал, а не поле в payload."""
        worker, redis = _worker()
        worker._route = _async_result  # type: ignore[method-assign]
        await worker._handle("5-5", {"payload": json.dumps(
            {"task_id": "t1"}
        )}, "grade-test:be-to-ml")
        assert "type" not in redis.published[0]["payload"]
        assert redis.published[0]["stream"] == "grade-test:ml-to-be"


def _result(task: dict) -> dict:
    """Успешный результат-заглушка — по форме своего канала.

    У `ingest` идентификатор — `material_id` и статус `ready`, у остальных
    типов — `task_id` и статус `ok` (в `grade-test:ml-to-be` поля `status`
    нет, но заглушка тут не проверяется по форме).
    """
    if task.get("material_id"):
        return {"material_id": task["material_id"], "status": "ready"}
    return {"task_id": task.get("task_id", ""), "status": "ok"}


async def _async_result(task_type: str, task: dict) -> dict:
    """Мок роутера: `_handle` делает `await self._route(...)`, поэтому мок обязан
    быть асинхронным — синхронный lambda падал бы с TypeError и тест проверял
    бы ветку ошибки вместо успешной обработки."""
    return _result(task)


class TestReclaim:
    """Зависшее сообщение (прочитанное, но не XACK-нутое) возвращается в работу.

    XREADGROUP с ">" отдаёт только новые сообщения — без reclaim такое
    сообщение пропадало бы навсегда.
    """

    @pytest.mark.asyncio
    async def test_no_pending_means_no_claim(self):
        worker, redis = _worker()
        await worker._reclaim_pending()
        assert redis.autoclaim_calls == []

    @pytest.mark.asyncio
    async def test_reclaimed_message_is_processed_and_acked(self):
        worker, redis = _worker()
        redis.pending["ingest:be-to-ml"] = [
            {"message_id": "9-9", "consumer": "w0",
             "time_since_delivered": 500000, "times_delivered": 2}
        ]
        redis.claimed["ingest:be-to-ml"] = [
            ("9-9", {"payload": json.dumps({"material_id": "m7"})})
        ]
        worker._route = _async_result  # type: ignore[method-assign]

        await worker._reclaim_pending()

        assert redis.autoclaim_calls == [
            {"stream": "ingest:be-to-ml", "idle": 30_000}
        ]
        assert len(redis.published) == 1
        assert redis.published[0]["payload"]["material_id"] == "m7"
        assert redis.acked == [("ingest:be-to-ml", "9-9")]

    @pytest.mark.asyncio
    async def test_poison_message_gets_error_result_and_is_acked_and_deleted(self):
        """Сообщение, которое ломает обработку, не крутится вечно: backend
        получает ошибочный результат, а сообщение подтверждается и удаляется."""
        worker, redis = _worker()
        redis.pending["ingest:be-to-ml"] = [
            {"message_id": "9-9", "consumer": "w0",
             "time_since_delivered": 500000, "times_delivered": 9}
        ]
        redis.claimed["ingest:be-to-ml"] = [
            ("9-9", {"payload": json.dumps({"material_id": "m7"})})
        ]
        worker._route = _async_result  # type: ignore[method-assign]

        await worker._reclaim_pending()

        assert len(redis.published) == 1
        assert redis.published[0]["stream"] == "ingest:ml-to-be"
        payload = redis.published[0]["payload"]
        assert payload["status"] == "error"
        # У ingest идентификатор — material_id; лишнего task_id в контракте нет.
        assert payload["material_id"] == "m7"
        assert "task_id" not in payload
        assert "9 times" in payload["error"]
        assert redis.acked == [("ingest:be-to-ml", "9-9")]
        assert redis.deleted == [("ingest:be-to-ml", "9-9")]

    @pytest.mark.asyncio
    async def test_poison_message_already_published_gets_no_error(self):
        """Результат по этому сообщению УЖЕ опубликован (упал только XACK) —
        поздняя ошибка испортила бы успешный результат, поэтому её не шлём.
        Сообщение всё равно подтверждается и удаляется."""
        worker, redis = _worker()
        redis.pending["ingest:be-to-ml"] = [
            {"message_id": "9-9", "consumer": "w0",
             "time_since_delivered": 500000, "times_delivered": 9}
        ]
        redis.claimed["ingest:be-to-ml"] = [
            ("9-9", {"payload": json.dumps({"material_id": "m7"})})
        ]
        worker._published.add("9-9")

        await worker._reclaim_pending()

        assert redis.published == []
        assert redis.acked == [("ingest:be-to-ml", "9-9")]
        assert redis.deleted == [("ingest:be-to-ml", "9-9")]

    @pytest.mark.asyncio
    async def test_poison_message_in_grade_channel_has_no_status(self):
        """В `grade-test:ml-to-be` поля `status` нет — признак ошибки само
        наличие `error`."""
        worker, redis = _worker()
        redis.pending["grade-test:be-to-ml"] = [
            {"message_id": "7-7", "consumer": "w0",
             "time_since_delivered": 500000, "times_delivered": 9}
        ]
        redis.claimed["grade-test:be-to-ml"] = [
            ("7-7", {"payload": json.dumps({"task_id": "a1"})})
        ]

        await worker._reclaim_pending()

        assert len(redis.published) == 1
        assert redis.published[0]["stream"] == "grade-test:ml-to-be"
        payload = redis.published[0]["payload"]
        assert "status" not in payload
        assert payload["task_id"] == "a1"
        assert "error" in payload
        assert redis.acked == [("grade-test:be-to-ml", "7-7")]
        assert redis.deleted == [("grade-test:be-to-ml", "7-7")]

    @pytest.mark.asyncio
    async def test_reclaim_failure_does_not_stop_the_worker(self):
        worker, redis = _worker()

        async def boom(*args, **kwargs):
            raise RuntimeError("redis down")

        worker.redis.xpending_range = boom  # type: ignore[method-assign]
        await worker._reclaim_pending()  # не должно бросать наружу


class TestReclaimInterval:
    """Reclaim-проход выполняется не чаще раза в `worker_claim_interval_ms`."""

    @pytest.mark.asyncio
    async def test_first_call_runs_reclaim(self):
        worker, redis = _worker()
        await worker._maybe_reclaim()
        assert redis.autoclaim_calls == []

    @pytest.mark.asyncio
    async def test_immediate_second_call_is_skipped(self):
        worker, redis = _worker()
        redis.pending["ingest:be-to-ml"] = [
            {"message_id": "9-9", "consumer": "w0",
             "time_since_delivered": 500000, "times_delivered": 1}
        ]
        redis.claimed["ingest:be-to-ml"] = [
            ("9-9", {"payload": json.dumps({"task_id": "t7"})})
        ]
        worker._route = _async_result  # type: ignore[method-assign]

        await worker._maybe_reclaim()
        first = len(redis.autoclaim_calls)
        assert first == 1

        await worker._maybe_reclaim()
        assert len(redis.autoclaim_calls) == first  # интервал не истёк — прохода нет

    @pytest.mark.asyncio
    async def test_call_after_interval_runs_reclaim(self):
        worker, redis = _worker()
        redis.pending["ingest:be-to-ml"] = [
            {"message_id": "9-9", "consumer": "w0",
             "time_since_delivered": 500000, "times_delivered": 1}
        ]
        redis.claimed["ingest:be-to-ml"] = [
            ("9-9", {"payload": json.dumps({"task_id": "t7"})})
        ]
        worker._route = _async_result  # type: ignore[method-assign]

        await worker._maybe_reclaim()
        first = len(redis.autoclaim_calls)

        # Отматываем время последнего прохода за интервал.
        worker._last_reclaim_at -= worker.worker_claim_interval_ms / 1000
        await worker._maybe_reclaim()
        assert len(redis.autoclaim_calls) == first + 1


class TestPublishCleanup:
    """Обработанное сообщение подтверждается И удаляется из канала задач."""

    @pytest.mark.asyncio
    async def test_processed_message_is_acked_and_deleted(self):
        worker, redis = _worker()
        worker._route = _async_result  # type: ignore[method-assign]

        await worker._handle("6-6", {"payload": json.dumps(
            {"task_id": "t1"}
        )}, "ingest:be-to-ml")

        assert redis.published[0]["stream"] == "ingest:ml-to-be"
        assert redis.acked == [("ingest:be-to-ml", "6-6")]
        assert redis.deleted == [("ingest:be-to-ml", "6-6")]
        # Сообщение подтверждено — из множества «уже опубликовано» оно ушло.
        assert "6-6" not in worker._published

    @pytest.mark.asyncio
    async def test_failed_ack_keeps_message_marked_as_published(self):
        """Результат опубликован, но XACK не прошёл — id остаётся в `_published`.

        Иначе poison-ветка позже отправит ошибку поверх уже доставленного
        успешного результата.
        """
        worker, redis = _worker()
        worker._route = _async_result  # type: ignore[method-assign]

        async def boom(*args, **kwargs):
            raise RuntimeError("redis down")

        worker.redis.xack = boom  # type: ignore[method-assign]
        await worker._handle("7-7", {"payload": json.dumps(
            {"task_id": "t1"}
        )}, "ingest:be-to-ml")

        assert len(redis.published) == 1
        assert "7-7" in worker._published
        assert redis.deleted == []
