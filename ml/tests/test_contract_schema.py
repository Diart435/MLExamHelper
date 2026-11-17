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
     (`to_json()`); для ML → BE дополнительно учитывается `input_msg_id`,
     который воркер добавляет при публикации;
  f. имя канала в `$id` и описании схемы — то, что реально использует код
     (`task_channel()` / `result_channel()`);
  g. набор файлов полон: шесть схем и шесть примеров, лишних нет.

Требование (g) — не формальность: осиротевшая схема (канал переименовали, а
файл забыли) валидировала бы саму себя и молча разъезжалась бы с кодом.

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
                task_id=example.get("task_id", ""),
                course_id=example.get("course_id"),
            ).to_json()
        )

    if task_type == "create_test":
        raw_n = example.get("amountQuestions")
        if isinstance(raw_n, str):
            # Строковый режим: ML сам выбирает размер теста.
            num_questions = None
        else:
            num_questions = None if raw_n is None else int(raw_n)
        return json.loads(
            CreateTestTask(
                task_id=example["task_id"],
                test_id=example["test_id"],
                material_ids=list(example["material_ids"]),
                title=example["title"],
                num_questions=num_questions,
                difficulty=example.get("difficulty", "medium"),
                course_id=example.get("course_id"),
            ).to_json()
        )

    if task_type == "grade_attempt":
        return json.loads(
            GradeAttemptTask(
                task_id=example["task_id"],
                attempt_id=example["attempt_id"],
                test_id=example["test_id"],
                user_id=example["user_id"],
                answers=[StudentAnswer.from_dict(a) for a in example["answers"]],
            ).to_json()
        )

    raise AssertionError(f"нет контракта для типа задачи {task_type!r}")


def expected_result_payload(channel: str, example: dict[str, Any]) -> dict[str, Any]:
    """То, что ML отправит в канал — сериализация dataclass'а результата.

    `input_msg_id` в dataclass'е нет: воркер добавляет его при публикации
    (`app/workers/rag.py`). Значение берём из файла-примера, поэтому тест не
    зависит от конкретного Redis Stream ID.
    """
    task_type = channel_task_type(channel)
    input_msg_id = example.get("input_msg_id")

    if task_type == "ingest":
        result = IngestResult(
            task_id=example.get("task_id", ""),
            status=example["status"],
            material_id=example.get("material_id"),
            chunks_indexed=example.get("chunks_indexed"),
            error=example.get("error"),
        )
    elif task_type == "create_test":
        test = Test.from_dict(example["test"]) if example.get("test") else None
        result = CreateTestResult(
            task_id=example.get("task_id", ""),
            status=example["status"],
            test=test,
            test_id=example.get("test_id"),
            error=example.get("error"),
        )
    elif task_type == "grade_attempt":
        result = GradeAttemptResult(
            task_id=example.get("task_id", ""),
            status=example["status"],
            attempt_id=example.get("attempt_id"),
            test_id=example.get("test_id"),
            score_pct=example.get("score_pct"),
            grade=example.get("grade"),
            items=[GradedItem(**item) for item in example.get("items", [])],
            error=example.get("error"),
        )
    else:
        raise AssertionError(f"нет контракта для типа задачи {task_type!r}")

    payload = json.loads(result.to_json())
    if input_msg_id is not None:
        payload["input_msg_id"] = input_msg_id
    return payload


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
#  e. Пример ML → BE == сериализация dataclass'а результата + input_msg_id
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
            f"(to_json() + input_msg_id). "
            f"Ожидалось: {json.dumps(expected, ensure_ascii=False, sort_keys=True)}"
        )

    @pytest.mark.parametrize(
        "channel",
        [ch for ch in ALL_CHANNELS if ch.endswith(f":{ML_TO_BE}")],
    )
    def test_result_example_carries_input_msg_id(self, channel: str):
        """`input_msg_id` добавляет воркер при публикации — в примере он обязан
        быть, иначе backend не сможет сопоставить результат с запросом."""
        payload = load_json(example_path(channel))
        assert "input_msg_id" in payload, (
            f"{channel}: в примере результата нет поля input_msg_id"
        )
        assert isinstance(payload["input_msg_id"], str) and payload["input_msg_id"], (
            f"{channel}: input_msg_id должен быть непустой строкой"
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
