"""Тесты JSON-схем контрактов Redis Streams (BE ↔ ML).

Что защищаем. `ml/docs/contracts/` — это машино-читаемое описание контракта:
шесть JSON Schema (draft 2020-12) и шесть канонических примеров payload'ов.
Их читает не только человек, но и код (backend-разработчик строит по ним
record'ы, тесты генерируются по ним). Если схема разойдётся с реальным кодом в
`ml/app/contracts.py`, расхождение всплывёт не сразу — а в рантайме, когда
backend уже отвергнет сообщение.

Поэтому здесь четыре независимых слоя проверки:

  a. схема — валидный JSON Schema draft 2020-12 (`check_schema`);
  b. пример — валиден по своей схеме (с разбором ошибок, а не `assert False`);
  c. `examples[0]` в схеме — тот же payload, что лежит в файле-примере;
  d/e. пример — то, что реально сериализуют dataclass'ы `app/contracts.py`
     (`to_json()`);
  f. имя канала в `$id` и описании схемы — то, что реально использует код
     (`task_channel()` / `result_channel()`);
  g. набор файлов полон: шесть схем и шесть примеров, лишних нет;
  h. в примерах и схемах нет полей, которых нет в контракте заказчика
     (`input_msg_id`, `course_id`, `user_id`, `answer_key`, `chunks_indexed`).

Требование (g) — не формальность: осиротевшая схема (канал переименовали, а
файл забыли) валидировала бы саму себя и молча разъезжалась бы с кодом.

Требование (h) — то же самое, только про лишние поля: поле, которого нет в
контракте заказчика, в payload'е — это молчаливый разъезд с backend'ом, и
backend об этом узнаёт только в рантайме.

Тест детерминированный: ни сети, ни БД, ни LLM.

Зависимость `jsonschema` — dev-only (см. `ml/requirements-dev.txt`): в образе
ML её нет, поэтому при отсутствии пакета модуль пропускается целиком.

Запуск:
    из ml/:     python -m pytest -q
    из корня:   python -m pytest ml/tests/test_contract_schema.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# jsonschema — dev-зависимость: в образе ML её нет, тест там запускаться
# не должен. importorskip на уровне модуля пропускает весь файл.
# exc_type=ImportError — чтобы pytest не ругался предупреждением: без
# отсутствующего пакета это штатная ситуация, а не ошибка импорта.
pytest.importorskip("jsonschema", exc_type=ImportError)

from jsonschema import Draft202012Validator  # noqa: E402

# `app.contracts` лежит рядом с тестом, но не в корне репозитория — добавляем
# корень ml/ в sys.path, чтобы тест не зависел от того, откуда запущен pytest.
ML_ROOT = Path(__file__).resolve().parents[1]
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from app.contracts import (  # noqa: E402
    BE_TO_ML,
    ML_TO_BE,
    CreateTestResult,
    CreateTestTask,
    GradeAttemptResult,
    GradeAttemptTask,
    GradedItem,
    IngestResult,
    IngestTask,
    StudentAnswer,
    Test,
    TestQuestion,
    channel_task_type,
    result_channel,
    task_channel,
)

# Пути считаем от корня репозитория, а не от текущего каталога.
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "ml" / "docs" / "contracts"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"

# Каналы под контрактом: (внутренний тип задачи, направление).
# `rag_question` — legacy-канал, контракта у него нет (см. CLAUDE.md).
CONTRACT_CHANNELS: tuple[tuple[str, str], ...] = (
    ("ingest", BE_TO_ML),
    ("ingest", ML_TO_BE),
    ("create_test", BE_TO_ML),
    ("create_test", ML_TO_BE),
    ("grade_attempt", BE_TO_ML),
    ("grade_attempt", ML_TO_BE),
)


def channel_name(task_type: str, direction: str) -> str:
    """Настоящее имя канала из кода: 'create-test:be-to-ml'."""
    return task_channel(task_type) if direction == BE_TO_ML else result_channel(task_type)


def file_stem(channel: str) -> str:
    """Имя файла артефакта по имени канала: 'create-test:be-to-ml' →
    'create-test-be-to-ml'. Разделитель канала — двоеточие, разделитель в
    имени файла — дефис, поэтому замена однозначна."""
    return channel.replace(":", "-")


def schema_path(channel: str) -> Path:
    return CONTRACTS_DIR / f"{file_stem(channel)}.schema.json"


def example_path(channel: str) -> Path:
    return EXAMPLES_DIR / f"{file_stem(channel)}.json"


def load_json(path: Path) -> Any:
    assert path.exists(), f"нет файла: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
#  Сборка ожидаемых payload'ов из dataclass'ов app/contracts.py
# ---------------------------------------------------------------------------

def expected_task_payload(channel: str, example: dict[str, Any]) -> dict[str, Any]:
    """То, что backend отправит в канал — сериализация dataclass'а задачи.

    Значения берём из самого файла-примера: проверка не должна зависеть от
    конкретных id/значений, зашитых в примере. Важно, чтобы поле, которого
    нет в примере, не появилось в сериализации, — и наоборот.
    """
    task_type = channel_task_type(channel)

    if task_type == "ingest":
        return json.loads(
            IngestTask(
                material_id=example["material_id"],
                storage_key=example["storage_key"],
            ).to_json()
        )

    if task_type == "create_test":
        # Контракт v4.1: числа вопросов в задаче нет — размер выбирает ML.
        return json.loads(
            CreateTestTask(
                task_id=example["task_id"],
                test_id=example["test_id"],
                material_ids=list(example["material_ids"]),
                title=example["title"],
                difficulty=example.get("difficulty", "medium"),
            ).to_json()
        )

    if task_type == "grade_attempt":
        return json.loads(
            GradeAttemptTask(
                task_id=example["task_id"],
                attempt_id=example["attempt_id"],
                test_id=example["test_id"],
                answers=[StudentAnswer.from_dict(a) for a in example["answers"]],
            ).to_json()
        )

    raise AssertionError(f"нет контракта для типа задачи {task_type!r}")


def expected_result_payload(channel: str, example: dict[str, Any]) -> dict[str, Any]:
    """То, что ML отправит в канал — сериализация dataclass'а результата.

    Статус у grade-ответа внутри dataclass'а остался (для удобства вызывающего
    кода), но наружу не сериализуется: в контракте заказчика признак ошибки —
    поле `error`.
    """
    task_type = channel_task_type(channel)

    if task_type == "ingest":
        result = IngestResult(
            status=example["status"],
            material_id=example.get("material_id"),
            error=example.get("error"),
        )
    elif task_type == "create_test":
        # `Test.from_dict` — валидатор для выхода LLM-генератора: там
        # `answer_key` обязателен. Собираем вопросы напрямую, перенося эталон
        # из примера (контракт v4.1: `answer_key` выходит наружу).
        test = None
        if example.get("test"):
            test = Test(
                title=example["test"]["title"],
                questions=[
                    TestQuestion(
                        id=int(q["id"]),
                        text=str(q["text"]),
                        type_question=str(q["type"]),
                        options=list(q.get("options") or []),
                        answer_key=dict(q.get("answer_key") or {}),
                        key_points=list(q.get("key_points") or []),
                        source_chunk_id=q.get("source_chunk_id"),
                    )
                    for q in example["test"]["questions"]
                ],
            )
        result = CreateTestResult(
            task_id=example.get("task_id", ""),
            status=example["status"],
            test=test,
            test_id=example.get("test_id"),
            error=example.get("error"),
        )
    elif task_type == "grade_attempt":
        # Статус в примере не выводим: в grade-ответе его нет.
        status = "ok" if "error" not in example else "error"
        result = GradeAttemptResult(
            task_id=example.get("task_id", ""),
            status=status,
            attempt_id=example.get("attempt_id"),
            test_id=example.get("test_id"),
            score_pct=example.get("score_pct"),
            grade=example.get("grade"),
            items=[GradedItem(**item) for item in example.get("items", [])],
            error=example.get("error"),
        )
    else:
        raise AssertionError(f"нет контракта для типа задачи {task_type!r}")

    return json.loads(result.to_json())


# ---------------------------------------------------------------------------
#  Параметризация
# ---------------------------------------------------------------------------

ALL_CHANNELS = tuple(channel_name(tt, d) for tt, d in CONTRACT_CHANNELS)
CHANNEL_IDS = [pytest.param(ch, id=ch) for ch in ALL_CHANNELS]


# ---------------------------------------------------------------------------
#  a. Схемы — валидный JSON Schema draft 2020-12
# ---------------------------------------------------------------------------

class TestSchemasAreValid:
    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_schema_is_valid_draft_2020_12(self, channel: str):
        schema = load_json(schema_path(channel))
        Draft202012Validator.check_schema(schema)

    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_schema_declares_draft_2020_12(self, channel: str):
        schema = load_json(schema_path(channel))
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", (
            f"{channel}: схема должна объявлять draft 2020-12, "
            f"а не {schema.get('$schema')!r}"
        )


# ---------------------------------------------------------------------------
#  b. Примеры валидны по своим схемам
# ---------------------------------------------------------------------------

class TestExamplesMatchSchema:
    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_example_validates_against_schema(self, channel: str):
        schema = load_json(schema_path(channel))
        example = load_json(example_path(channel))
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(example), key=lambda e: list(e.absolute_path))
        if errors:
            details = "\n".join(
                f"  - {list(e.absolute_path)}: {e.message}" for e in errors
            )
            pytest.fail(
                f"{channel}: пример не соответствует своей схеме:\n{details}"
            )

    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_schema_embedded_example_validates(self, channel: str):
        """Пример, вшитый в схему (examples[0]), тоже должен ей соответствовать."""
        schema = load_json(schema_path(channel))
        examples = schema.get("examples") or []
        assert examples, f"{channel}: в схеме нет ни одного примера"
        for index, embedded in enumerate(examples):
            validator = Draft202012Validator(schema)
            errors = sorted(validator.iter_errors(embedded), key=lambda e: list(e.absolute_path))
            if errors:
                details = "\n".join(
                    f"  - {list(e.absolute_path)}: {e.message}" for e in errors
                )
                pytest.fail(
                    f"{channel}: examples[{index}] не соответствует схеме:\n{details}"
                )


# ---------------------------------------------------------------------------
#  c. examples[0] в схеме == файл-пример
# ---------------------------------------------------------------------------

class TestSchemaExampleMatchesFile:
    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_schema_example_equals_example_file(self, channel: str):
        schema = load_json(schema_path(channel))
        example = load_json(example_path(channel))
        embedded = schema.get("examples") or []
        assert embedded, f"{channel}: в схеме нет ни одного примера"
        assert embedded[0] == example, (
            f"{channel}: examples[0] в схеме отличается от файла-примера "
            f"{example_path(channel).name}. Перегенерируй примеры: "
            f"python tools/generate_contract_examples.py"
        )


# ---------------------------------------------------------------------------
#  d. Пример BE → ML == сериализация dataclass'а задачи
# ---------------------------------------------------------------------------

class TestTaskExampleMatchesDataclass:
    @pytest.mark.parametrize(
        "channel",
        [ch for ch in ALL_CHANNELS if ch.endswith(f":{BE_TO_ML}")],
    )
    def test_task_example_matches_to_json(self, channel: str):
        payload = load_json(example_path(channel))
        expected = expected_task_payload(channel, payload)
        assert payload == expected, (
            f"{channel}: файл-пример расходится с сериализацией "
            f"dataclass'а задачи (to_json()). "
            f"Ожидалось: {json.dumps(expected, ensure_ascii=False, sort_keys=True)}"
        )


# ---------------------------------------------------------------------------
#  e. Пример ML → BE == сериализация dataclass'а результата
# ---------------------------------------------------------------------------

class TestResultExampleMatchesDataclass:
    @pytest.mark.parametrize(
        "channel",
        [ch for ch in ALL_CHANNELS if ch.endswith(f":{ML_TO_BE}")],
    )
    def test_result_example_matches_to_json(self, channel: str):
        payload = load_json(example_path(channel))
        expected = expected_result_payload(channel, payload)
        assert payload == expected, (
            f"{channel}: файл-пример расходится с сериализацией результата "
            f"(to_json()). "
            f"Ожидалось: {json.dumps(expected, ensure_ascii=False, sort_keys=True)}"
        )


# ---------------------------------------------------------------------------
#  h. Лишних полей нет ни в примерах, ни в схемах
# ---------------------------------------------------------------------------

# Поля, которых нет в контракте заказчика. Если такое поле появится в
# payload'е — это молчаливый разъезд с backend'ом.
#
# ⚠️ `answer_key` НЕ входит в список: по контракту v4.1 эталон правильного
# ответа выходит в `create-test:ml-to-be` (backend пишет его в
# `test_questions.answer_key`). В остальных каналах его по-прежнему нет —
# это проверяется отдельно, см. ANSWER_KEY_ALLOWED.
FORBIDDEN_FIELDS = ("input_msg_id", "course_id", "user_id", "chunks_indexed")

# Каналы, в ответе которых `answer_key` допустим.
ANSWER_KEY_ALLOWED = ("create-test:ml-to-be",)


def walk_keys(node: Any) -> set[str]:
    """Все ключи объектов в JSON-дереве."""
    keys: set[str] = set()
    if isinstance(node, dict):
        keys.update(node.keys())
        for value in node.values():
            keys.update(walk_keys(value))
    elif isinstance(node, list):
        for item in node:
            keys.update(walk_keys(item))
    return keys


class TestNoForbiddenFields:
    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_example_has_no_forbidden_fields(self, channel: str):
        example = load_json(example_path(channel))
        found = sorted(walk_keys(example) & set(FORBIDDEN_FIELDS))
        assert not found, (
            f"{channel}: в примере есть поля, которых нет в контракте "
            f"заказчика: {found}"
        )

    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_schema_has_no_forbidden_fields(self, channel: str):
        schema = load_json(schema_path(channel))
        found = sorted(walk_keys(schema) & set(FORBIDDEN_FIELDS))
        assert not found, (
            f"{channel}: в схеме есть поля, которых нет в контракте "
            f"заказчика: {found}"
        )

    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_embedded_example_has_no_forbidden_fields(self, channel: str):
        schema = load_json(schema_path(channel))
        for index, embedded in enumerate(schema.get("examples") or []):
            found = sorted(walk_keys(embedded) & set(FORBIDDEN_FIELDS))
            assert not found, (
                f"{channel}: в examples[{index}] схемы есть поля, которых "
                f"нет в контракте заказчика: {found}"
            )

    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_answer_key_only_in_create_test_result(self, channel: str):
        """Эталон `answer_key` по контракту v4.1 выходит только в ответе
        `create-test:ml-to-be` — в остальных каналах его быть не должно."""
        example = load_json(example_path(channel))
        found = sorted(walk_keys(example) & {"answer_key"})
        if channel in ANSWER_KEY_ALLOWED:
            assert found, f"{channel}: в ответе должен быть эталон answer_key"
        else:
            assert not found, (
                f"{channel}: в примере есть answer_key — эталон по контракту "
                f"выходит только в create-test:ml-to-be"
            )

    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_schema_answer_key_only_in_create_test_result(self, channel: str):
        schema = load_json(schema_path(channel))
        found = sorted(walk_keys(schema) & {"answer_key"})
        if channel in ANSWER_KEY_ALLOWED:
            assert found, f"{channel}: в схеме должен быть описан answer_key"
        else:
            assert not found, (
                f"{channel}: в схеме есть answer_key — эталон по контракту "
                f"выходит только в create-test:ml-to-be"
            )


# ---------------------------------------------------------------------------
#  f. Имена каналов в схемах совпадают с кодом
# ---------------------------------------------------------------------------

class TestChannelNamesInSchemas:
    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_schema_id_contains_channel_name(self, channel: str):
        schema = load_json(schema_path(channel))
        schema_id = schema.get("$id", "")
        assert schema_id, f"{channel}: у схемы нет $id"
        assert schema_id.endswith(f":{channel}"), (
            f"{channel}: $id схемы должен заканчиваться на имя канала "
            f"':{channel}', а не {schema_id!r}"
        )

    @pytest.mark.parametrize("channel", CHANNEL_IDS)
    def test_schema_text_mentions_channel_name(self, channel: str):
        schema = load_json(schema_path(channel))
        text = " ".join(
            str(schema.get(key, "")) for key in ("title", "description")
        )
        assert channel in text, (
            f"{channel}: название канала не упомянуто в title/description схемы"
        )

    @pytest.mark.parametrize(
        ("task_type", "direction"),
        CONTRACT_CHANNELS,
    )
    def test_channel_name_comes_from_contracts_module(
        self, task_type: str, direction: str
    ):
        """Имя канала в схемах — то же, что считает код: никаких «своих»
        строковых литералов, иначе каналы разъедутся тихо."""
        expected = channel_name(task_type, direction)
        if direction == BE_TO_ML:
            assert expected == task_channel(task_type)
        else:
            assert expected == result_channel(task_type)
        assert channel_task_type(expected) == task_type

    def test_legacy_rag_question_has_no_contract_schema(self):
        """`rag-question` — legacy-канал вне контракта: лишняя схема в
        `docs/contracts/` была бы недостижимым кодом."""
        assert not (CONTRACTS_DIR / "rag-question-be-to-ml.schema.json").exists()
        assert not (EXAMPLES_DIR / "rag-question-be-to-ml.json").exists()


# ---------------------------------------------------------------------------
#  g. Набор файлов полон
# ---------------------------------------------------------------------------

class TestContractFileSet:
    def test_exactly_six_schemas(self):
        found = {p.name for p in CONTRACTS_DIR.glob("*.schema.json")}
        expected = {f"{file_stem(ch)}.schema.json" for ch in ALL_CHANNELS}
        assert found == expected, (
            f"набор схем не совпадает с контрактом.\n"
            f"  лишние: {sorted(found - expected)}\n"
            f"  отсутствуют: {sorted(expected - found)}"
        )

    def test_exactly_six_examples(self):
        found = {p.name for p in EXAMPLES_DIR.glob("*.json")}
        expected = {f"{file_stem(ch)}.json" for ch in ALL_CHANNELS}
        assert found == expected, (
            f"набор примеров не совпадает с контрактом.\n"
            f"  лишние: {sorted(found - expected)}\n"
            f"  отсутствуют: {sorted(expected - found)}"
        )

    def test_no_orphan_json_files_in_contracts_dir(self):
        """В каталоге контрактов нет «просто JSON»-файлов без схемы —
        иначе такой файл осиротеет и никто его не проверит."""
        found = {p.name for p in CONTRACTS_DIR.glob("*.json")}
        expected = {f"{file_stem(ch)}.schema.json" for ch in ALL_CHANNELS}
        assert found == expected, (
            f"в docs/contracts/ есть JSON-файлы, не являющиеся схемами: "
            f"{sorted(found - expected)}"
        )

    def test_every_channel_has_schema_and_example(self):
        for channel in ALL_CHANNELS:
            assert schema_path(channel).exists(), f"нет схемы для {channel}"
            assert example_path(channel).exists(), f"нет примера для {channel}"

    def test_example_files_are_valid_json_objects(self):
        for channel in ALL_CHANNELS:
            payload = load_json(example_path(channel))
            assert isinstance(payload, dict), (
                f"{channel}: payload должен быть JSON-объектом, "
                f"а не {type(payload).__name__}"
            )


# ---------------------------------------------------------------------------
#  i. Контракт v4.1: числа вопросов нет, эталон answer_key — есть
# ---------------------------------------------------------------------------

class TestContractV41:
    """Контракт v4.1: `amountQuestions` убран из задачи, `answer_key` вернулся
    в ответ на создание теста."""

    def test_create_test_task_schema_has_no_amount_questions(self):
        schema = load_json(schema_path("create-test:be-to-ml"))
        assert "amountQuestions" not in schema.get("properties", {})
        assert "amountQuestions" not in schema.get("required", [])

    def test_create_test_task_example_has_no_amount_questions(self):
        example = load_json(example_path("create-test:be-to-ml"))
        assert "amountQuestions" not in example

    def test_create_test_task_schema_accepts_legacy_payload(self):
        """Legacy-payload с `amountQuestions` должен остаться валидным.

        `additionalProperties` в схеме не запрещён, поэтому лишнее поле
        `amountQuestions` не ломает валидацию старых сообщений из Redis
        Streams."""
        schema = load_json(schema_path("create-test:be-to-ml"))
        example = load_json(example_path("create-test:be-to-ml"))
        legacy = {**example, "amountQuestions": 7}
        Draft202012Validator(schema).validate(legacy)

    def test_create_test_result_schema_requires_answer_key(self):
        """Эталон правильного ответа обязателен у каждого вопроса."""
        schema = load_json(schema_path("create-test:ml-to-be"))
        question = schema["$defs"]["question"]
        assert "answer_key" in question["required"]
        assert question["properties"]["answer_key"] == {
            "$ref": "#/$defs/answer_key",
        }

    def test_answer_key_schema_shape(self):
        schema = load_json(schema_path("create-test:ml-to-be"))
        answer_key = schema["$defs"]["answer_key"]
        assert answer_key["type"] == "object"
        assert answer_key["additionalProperties"] is False
        assert answer_key["minProperties"] == 1
        props = answer_key["properties"]
        assert props["correct_index"]["type"] == "integer"
        assert props["correct_index"]["minimum"] == 0
        assert props["correct_indexes"]["type"] == "array"
        assert props["correct_indexes"]["items"]["minimum"] == 0
        assert props["reference_answer"]["type"] == "string"
        assert props["explanation"]["type"] == "string"

    def test_question_without_answer_key_fails_validation(self):
        """Вопрос без эталона — невалиден по схеме: backend не сможет проверить
        ответ."""
        schema = load_json(schema_path("create-test:ml-to-be"))
        example = load_json(example_path("create-test:ml-to-be"))
        broken = json.loads(json.dumps(example))
        broken["test"]["questions"][0].pop("answer_key")
        errors = list(Draft202012Validator(schema).iter_errors(broken))
        assert errors, "вопрос без answer_key должен не проходить валидацию"

    def test_answer_key_with_unknown_field_fails_validation(self):
        """`additionalProperties: false` — лишние ключи в эталоне запрещены."""
        schema = load_json(schema_path("create-test:ml-to-be"))
        example = load_json(example_path("create-test:ml-to-be"))
        broken = json.loads(json.dumps(example))
        broken["test"]["questions"][0]["answer_key"]["criteria"] = ["пункт"]
        errors = list(Draft202012Validator(schema).iter_errors(broken))
        assert errors, "answer_key с лишним ключом должен не проходить валидацию"

    def test_empty_answer_key_fails_validation(self):
        """Пустой эталон бесполезен — `minProperties: 1` его не пускает."""
        schema = load_json(schema_path("create-test:ml-to-be"))
        example = load_json(example_path("create-test:ml-to-be"))
        broken = json.loads(json.dumps(example))
        broken["test"]["questions"][0]["answer_key"] = {}
        errors = list(Draft202012Validator(schema).iter_errors(broken))
        assert errors, "пустой answer_key должен не проходить валидацию"
