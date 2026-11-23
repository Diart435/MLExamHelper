"""TestGenerator: собрать контекст по материалам и попросить LLM сгенерировать тест.

Контракт:
  - На входе: список material_ids + параметры теста (title, num_questions, difficulty).
  - На выходе: app.contracts.Test (валидный, прошедший через Test.from_dict).

Типы вопросов и их соотношение задаёт заказчик:

    | difficulty | single_choice | multi_choice | open_answer |
    |------------|---------------|-------------|-------------|
    | easy       | 70 %          | 30 %        | 0 %         |
    | medium     | 40 %          | 30 %        | 30 %        |
    | hard       | 10 %          | 30 %        | 60 %        |

Микс считаем МЫ (ML), а не backend: иначе пришлось бы держать две реализации
одного правила и синхронизировать их.

Логика:
  1. RAGService.context_for_materials(...) — top-N чанков на материал (с id).
  2. Собираем текстовый «дайджест» с разделителями; каждый чанк помечен
     короткой меткой («C7»), по ней вопрос привязывается к источнику.
  3. Если num_questions не задан — планировщик (services/test_planner.py) решает,
     сколько вопросов покрывает материал, и на какие темы.
  4. Считаем микс (question_mix) и раскладываем типы по вопросам (spread_types),
     чтобы они чередувались, а не шли блоками.
  5. LLMClient.chat_json() с промптом и JSON Schema: ровно N вопросов нужных типов.
  6. Если LLM вернула неверный микс — ещё одна попытка с уточняющим промптом.
  7. Если и вторая попытка не сошлась — ValueError. Молча заменять open_answer
     на single_choice нельзя: тест получится не того состава, о котором просили.

Никаких обращений к Redis, MinIO, файлам — сервис чистый и тестируется в юнитах.
"""

from __future__ import annotations

import json
import math
from typing import Any

from loguru import logger

from app.contracts import CreateTestTask, Test, TestQuestion
from app.services.llm import LLMClient, payloads_enabled
from app.services.rag import ChunkRef, RAGService
from app.services.test_planner import plan_test


# Доли типов вопросов по уровню сложности (требование заказчика).
MIX_SHARES: dict[str, dict[str, float]] = {
    "easy": {"single_choice": 0.7, "multi_choice": 0.3, "open_answer": 0.0},
    "medium": {"single_choice": 0.4, "multi_choice": 0.3, "open_answer": 0.3},
    "hard": {"single_choice": 0.1, "multi_choice": 0.3, "open_answer": 0.6},
}

# Порядок типов в контракте и в примерах — от простого к сложному.
QUESTION_TYPE_ORDER = ("single_choice", "multi_choice", "open_answer")

# «Сложность» типа. Используется как тай-брейк: при равенстве долей/остатков
# побеждает более сложный тип — так микс смещается в сторону «сложнее», а не
# «проще».
TYPE_PRIORITY: dict[str, int] = {"open_answer": 3, "multi_choice": 2, "single_choice": 1}

# Чем определяется глубина вопроса внутри его типа.
_DIFFICULTY_TEXT: dict[str, str] = {
    "easy": (
        "Базовое понимание: вспомнить термин, определение, формулу, факт, дату; "
        "прямое применение по образцу. Вопрос закрывается однозначным коротким ответом."
    ),
    "medium": (
        "Применение и связывание: применить факт в новой ситуации, объяснить причину, "
        "сравнить два понятия, решить типовую задачу в два шага."
    ),
    "hard": (
        "Анализ и обобщение: разобрать нестандартный пример, вывести следствие из правила, "
        "оценить противоречие, связать две темы, сформулировать вывод самому."
    ),
}

# Первая попытка + одна догенерация с уточнением.
_MAX_GENERATION_ATTEMPTS = 2


def question_mix(num_questions: int, difficulty: str) -> dict[str, int]:
    """Сколько вопросов каждого типа нужно для теста заданной сложности.

    Доли переводятся в целые числа методом наибольших остатков: сначала
    floor по каждому типу, потом остаток (N − сумма) раздаётся типам с
    наибольшей дробной частью; при равенстве побеждает более сложный тип.

    Плюс гарантия: тип с наибольшей долей получает хотя бы один вопрос. Это
    и есть «характер» сложности — при N=1 тест easy остаётся single_choice,
    а hard — open_answer.

    Returns:
        {"single_choice": n, "multi_choice": n, "open_answer": n} — сумма равна N.

    Raises:
        ValueError: неизвестная сложность или неположительное число вопросов.
    """
    shares = MIX_SHARES.get(difficulty)
    if shares is None:
        raise ValueError(f"unknown difficulty: {difficulty!r}")
    if num_questions < 1:
        raise ValueError(f"num_questions must be >= 1, got {num_questions}")

    exact = {t: num_questions * shares[t] for t in QUESTION_TYPE_ORDER}
    counts = {t: math.floor(exact[t]) for t in QUESTION_TYPE_ORDER}

    remainder = num_questions - sum(counts.values())
    ranked = sorted(
        QUESTION_TYPE_ORDER,
        key=lambda t: (-(exact[t] - counts[t]), -TYPE_PRIORITY[t]),
    )
    for t in ranked[:remainder]:
        counts[t] += 1

    dominant = max(QUESTION_TYPE_ORDER, key=lambda t: (shares[t], TYPE_PRIORITY[t]))
    if counts[dominant] == 0:
        donor = max(QUESTION_TYPE_ORDER, key=lambda t: (counts[t], TYPE_PRIORITY[t]))
        if counts[donor] > 0:
            counts[donor] -= 1
            counts[dominant] += 1

    return counts


def spread_types(counts: dict[str, int]) -> list[str]:
    """Разложить типы по вопросам так, чтобы они чередувались.

    Метод Д'Хондта: на каждое место отдаётся тип с наибольшим частным
    count/номер, где count — ВСЕГО вопросов этого типа, а номер — какое по
    счёту место этого типа мы сейчас раздаём. Блок «сначала 10 single, потом
    10 open» читается тяжелее, чем чередование, а вопросов по типам — ровно
    столько же.

    При равенстве частных побеждает тип, который в QUESTION_TYPE_ORDER стоит
    раньше (single_choice → multi_choice → open_answer): выбор детерминирован,
    иначе один и тот же тест генерировался бы по-разному от запуска к запуску.

    Returns:
        Список длиной sum(counts) с типами вопросов.
    """
    given = {t: 0 for t in QUESTION_TYPE_ORDER}
    order: list[str] = []
    for _ in range(sum(counts.values())):
        best_type: str | None = None
        best_quotient = -1.0
        for t in QUESTION_TYPE_ORDER:
            if given[t] >= counts.get(t, 0):
                continue
            seat = given[t] + 1
            quotient = counts[t] / seat
            if quotient > best_quotient:
                best_quotient = quotient
                best_type = t
        if best_type is None:
            break
        given[best_type] += 1
        order.append(best_type)
    return order


def _count_types(questions: list[TestQuestion]) -> dict[str, int]:
    counts = {t: 0 for t in QUESTION_TYPE_ORDER}
    for q in questions:
        if q.type_question in counts:
            counts[q.type_question] += 1
    return counts


def _plan_lines(types: list[str], topics: list[str] | None) -> str:
    """Строки плана для промпта: номер, тип, тема."""
    lines: list[str] = []
    for i, qtype in enumerate(types, start=1):
        topic = topics[i - 1] if topics and i - 1 < len(topics) else None
        if topic:
            lines.append(f'{i}. [{qtype}] тема: «{topic}»')
        else:
            lines.append(f"{i}. [{qtype}]")
    return "\n".join(lines)


def _example_questions(
    types: list[str],
    topics: list[str] | None,
) -> list[dict]:
    """Пример JSON-вопросов по одному на каждый тип, который есть в тесте.

    Пример берём из самого плана: у первого вопроса с таким типом — его id и
    его тема. Иначе пример противоречил бы плану (в старой версии он показывал
    id 1 и 2 с типами, не совпадающими с реальным порядком вопросов, и модель
    читала это как два разных требования).

    Типов без вопросов в примере нет — иначе модель нарисует лишние.
    """
    examples: list[dict] = []
    seen: set[str] = set()
    for i, qtype in enumerate(types):
        if qtype in seen:
            continue
        seen.add(qtype)
        qid = i + 1
        topic = topics[i] if topics and i < len(topics) else None
        text = f"<текст вопроса по теме «{topic}»>" if topic else "<текст вопроса>"

        if qtype == "single_choice":
            examples.append({
                "id": qid,
                "type_question": "single_choice",
                "options": ["<вариант A>", "<вариант B>", "<вариант C>", "<вариант D>"],
                "text": text,
                "answer_key": {"correct_index": 1, "explanation": "<короткое объяснение>"},
                "key_points": [],
                "source_chunk_ref": "<метка блока>",
            })
        elif qtype == "multi_choice":
            examples.append({
                "id": qid,
                "type_question": "multi_choice",
                "options": [
                    "<вариант A>", "<вариант B>", "<вариант C>",
                    "<вариант D>", "<вариант E>", "<вариант F>",
                ],
                "text": text,
                "answer_key": {"correct_indexes": [0, 2], "explanation": "<короткое объяснение>"},
                "key_points": [],
                "source_chunk_ref": "<метка блока>",
            })
        else:
            examples.append({
                "id": qid,
                "type_question": "open_answer",
                "options": [],
                "text": text,
                "answer_key": {
                    "reference_answer": "<полный эталонный ответ>",
                    "explanation": "<короткое объяснение>",
                },
                "key_points": ["<опорный пункт 1>", "<опорный пункт 2>"],
                "source_chunk_ref": "<метка блока>",
            })
    return examples


def _system_prompt(
    num_questions: int,
    difficulty: str,
    types: list[str],
    topics: list[str] | None,
) -> str:
    difficulty_text = _DIFFICULTY_TEXT.get(difficulty, "")
    example = {
        "title": "<название теста, до 80 символов>",
        "questions": _example_questions(types, topics),
    }
    return f"""\
Ты — преподаватель, составляющий тест по учебным материалам.

=== ПЛАН ТЕСТА ===
Вопросов ровно {num_questions}. У каждого вопроса свой тип и своя тема — не меняй тип, \
не меняй тему, не добавляй вопросов сверх плана.

{_plan_lines(types, topics)}

=== ЧТО ЭТО ЗА ТИПЫ ===
- single_choice: 4 варианта ответа, правильный РОВНО ОДИН, его индекс 0..3 → \
answer_key.correct_index.
- multi_choice: 4-6 вариантов ответа, правильных РОВНО 2 или 3, их индексы по \
возрастанию → answer_key.correct_indexes.
- open_answer: вариантов нет (options=[]), полный эталонный ответ → \
answer_key.reference_answer.

=== СЛОЖНОСТЬ: {difficulty} ===
{difficulty_text}
Сложность задаёт ГЛУБИНУ вопроса внутри его типа, а не сам тип. Если материал не позволяет \
спросить на полную глубину — сформулируй проще, но тип вопроса НЕ меняй. Это важнее, чем \
«сложный» open_answer превратился в single_choice.

=== ТРЕБОВАНИЯ К КАЖДОМУ ВОПРОСУ ===
1. Только по материалу. Не придумывай фактов, которых нет в тексте.
2. Вопросы не повторяются: каждый — про свою тему из плана.
3. Один вопрос — одна мысль. В single_choice не должно быть двух верных вариантов.
4. Формулировка на русском, без отсылок к «лекции», «слайду», «документу»: вопрос должен \
читаться как самостоятельный.
5. Варианты ответа — в одну грамматическую форму и сопоставимой длины; правильный вариант \
не выделяется ни длиной, ни формулировкой.
6. В multi_choice отметь ровно 2 или 3 правильных варианта — не один и не все.
7. open_answer: ответ — 1-3 предложения (не одно слово, не список из десяти пунктов); \
reference_answer — полный эталон.
8. id у вопросов — подряд 1..{num_questions}.
9. answer_key.explanation — короткое объяснение правильного ответа, ОДНО предложение. \
Обязательно для каждого типа вопроса.
10. key_points — для open_answer это 2-4 опорных пункта, по которым ответ студента будут \
сверять; для single_choice и multi_choice — пустой массив [].
11. source_chunk_ref — метка блока, из которого взят вопрос, РОВНО как она помечена в \
тексте материала (например «C7»). Метка стоит в квадратных скобках в начале блока. \
Поле обязательное: null не допускается — у каждого вопроса есть блок-источник. \
В сам текст вопроса метку не вставляй.

=== ФОРМАТ ОТВЕТА ===
{json.dumps(example, ensure_ascii=False, indent=2)}
Никакого текста до или после JSON. Никаких ```-обёрток. Один объект, начинается с {{ и \
заканчивается }}.
"""


def _question_schema(
    num_questions: int,
    counts: dict[str, int],
    chunk_refs: list[str],
) -> dict[str, Any]:
    """JSON Schema ответа LLM: объект test с массивом questions.

    Схема — не украшение, а способ убрать целый класс поломок: на свободном
    json_object модель отдаёт `{}`, дублирует ключи и обрывает ответ по лимиту
    токенов. Ограничения ниже делают часть ошибок структурно невозможными:
      - ровно num_questions вопросов (minItems/maxItems);
      - у single_choice обязателен answer_key.correct_index, у multi_choice —
        answer_key.correct_indexes (2-3 штуки), у open_answer —
        answer_key.reference_answer;
      - answer_key.explanation обязателен у всех типов;
      - key_points — массив строк: 2-4 критерия у open_answer, пустой у
        закрытых типов;
      - options у open_answer — пустой массив;
      - source_chunk_ref — только из списка реальных меток блоков (enum).
        null в enum'е НЕДОПУСТИМ: у вопроса всегда есть блок-источник, а
        разрешение «не ссылаться» превращалось в то, что модель писала null
        во все вопросы подряд и привязка терялась целиком.
    Соотношение типов схема не выражает (нужен порядок вопросов) — его по-прежнему
    проверяет генератор и при несовпадении просит переделать.
    """
    # Метки блоков, которые реально попали в контекст. Модель выбирает из
    # этого списка — UUID'ы она всё равно не выдумает.
    ref_enum: list[Any] = list(chunk_refs)

    branches: list[dict[str, Any]] = []

    if counts.get("single_choice"):
        branches.append({
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "type_question", "options", "text", "answer_key",
                         "key_points", "source_chunk_ref"],
            "properties": {
                "id": {"type": "integer", "minimum": 1, "maximum": num_questions},
                "type_question": {"enum": ["single_choice"]},
                "options": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string"}},
                "text": {"type": "string"},
                "answer_key": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["correct_index", "explanation"],
                    "properties": {
                        "correct_index": {"type": "integer", "minimum": 0, "maximum": 3},
                        "explanation": {"type": "string"},
                    },
                },
                "key_points": {
                    "type": "array",
                    "maxItems": 0,
                    "items": {"type": "string"},
                },
                "source_chunk_ref": {"type": "string", "enum": ref_enum},
            },
        })

    if counts.get("multi_choice"):
        branches.append({
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "type_question", "options", "text", "answer_key",
                         "key_points", "source_chunk_ref"],
            "properties": {
                "id": {"type": "integer", "minimum": 1, "maximum": num_questions},
                "type_question": {"enum": ["multi_choice"]},
                "options": {"type": "array", "minItems": 4, "maxItems": 6, "items": {"type": "string"}},
                "text": {"type": "string"},
                "answer_key": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["correct_indexes", "explanation"],
                    "properties": {
                        "correct_indexes": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 3,
                            "items": {"type": "integer", "minimum": 0, "maximum": 5},
                        },
                        "explanation": {"type": "string"},
                    },
                },
                "key_points": {
                    "type": "array",
                    "maxItems": 0,
                    "items": {"type": "string"},
                },
                "source_chunk_ref": {"type": "string", "enum": ref_enum},
            },
        })

    if counts.get("open_answer"):
        branches.append({
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "type_question", "options", "text", "answer_key",
                         "key_points", "source_chunk_ref"],
            "properties": {
                "id": {"type": "integer", "minimum": 1, "maximum": num_questions},
                "type_question": {"enum": ["open_answer"]},
                "options": {"type": "array", "maxItems": 0, "items": {"type": "string"}},
                "text": {"type": "string"},
                "answer_key": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["reference_answer", "explanation"],
                    "properties": {
                        "reference_answer": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                },
                "key_points": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {"type": "string"},
                },
                "source_chunk_ref": {"type": "string", "enum": ref_enum},
            },
        })

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "questions"],
        "properties": {
            "title": {"type": "string"},
            "questions": {
                "type": "array",
                "minItems": num_questions,
                "maxItems": num_questions,
                "items": branches[0] if len(branches) == 1 else {"anyOf": branches},
            },
        },
    }


class TestGenerator:
    __test__ = False  # не pytest-класс
    def __init__(self, rag: RAGService | None = None, llm: LLMClient | None = None) -> None:
        self.rag = rag or RAGService()
        self.llm = llm or LLMClient()

    async def generate(self, task: CreateTestTask) -> Test:
        """Сгенерировать тест по task. Возвращает валидный Test или кидает ValueError.

        Raises:
            ValueError: если какие-то материалы не проиндексированы, LLM не смогла
                        дать валидный JSON, или соотношение типов вопросов не
                        совпало с требуемым для этой сложности.
        """
        missing = [
            mid for mid in task.material_ids
            if not await self.rag.has_material(mid)
        ]
        if missing:
            raise ValueError(f"materials not indexed: {missing}")

        context = await self.rag.context_for_materials(
            task.material_ids, max_chunks_total=60,
        )
        if not context:
            raise ValueError("no context retrieved for given material_ids")

        digest = _format_digest(context)
        # Метки блоков: LLM выбирает источник вопроса из этого списка, мы
        # разворачиваем метку в настоящий chunk_id.
        chunk_refs = [c.ref for _mid, chunks in context for c in chunks]
        ref_to_chunk = {c.ref: c.chunk_id for _mid, chunks in context for c in chunks}

        # Размер теста: задан явно (внутренний вызов) — уважаем; не задан —
        # решает планировщик по тому же контексту, по которому потом пишутся
        # вопросы. Размер = число проверяемых фактов в материале (1..30);
        # backend в этом не участвует, сложность на размер не влияет.
        topics: list[str] | None = None
        if task.num_questions is None:
            plan = await plan_test(self.llm, digest)
            num_questions = plan.num_questions
            topics = plan.topics
        else:
            num_questions = task.num_questions

        counts = question_mix(num_questions, task.difficulty)
        types = spread_types(counts)
        sys_prompt = _system_prompt(num_questions, task.difficulty, types, topics)
        base_prompt = (
            f"Название теста: {task.title}\n\n"
            f"Материалы:\n{digest}\n\n"
            f"Сгенерируй тест строго в указанном JSON-формате."
        )

        logger.info(
            f"TestGenerator: materials={task.material_ids}, "
            f"num_questions={num_questions}, difficulty={task.difficulty}, "
            f"chunks={len(chunk_refs)}, "
            f"mix={counts['single_choice']} single_choice + "
            f"{counts['multi_choice']} multi_choice + "
            f"{counts['open_answer']} open_answer"
        )

        correction = ""
        for attempt in range(1, _MAX_GENERATION_ATTEMPTS + 1):
            try:
                test = await self.llm.chat_json(
                    base_prompt + correction,
                    validator=Test.from_dict,
                    system_prompt=sys_prompt,
                    max_retries=2,
                    schema=_question_schema(num_questions, counts, chunk_refs),
                )
            except RuntimeError as e:
                # chat_json исчерпал попытки: LLM вернула невалидный JSON
                # или структура вопроса не прошла валидацию.
                raise ValueError(f"LLM did not return a valid test: {e}") from e

            # Подстраховка: если LLM выдала title короче, чем в задании —
            # оставляем то, что прислал пользователь.
            if not test.title or len(test.title) < 3:
                test.title = task.title

            for q in test.questions:
                # Метка блока → настоящий chunk_id. Неизвестная метка (LLM
                # ответила вне enum'а) даёт NULL — вопрос без привязки лучше,
                # чем привязка к чужому чанку.
                q.source_chunk_id = ref_to_chunk.get(q.source_chunk_ref or "")

            # Разобранный JSON вопросов — целиком, на каждой попытке: так видно
            # сами вопросы и то, почему пошла вторая попытка (неверный микс).
            # Логируем ПОСЛЕ подстановки source_chunk_id — в логе должен быть
            # тот же тест, который уйдёт наружу.
            if payloads_enabled():
                logger.info(
                    "[TestGenerator] attempt {}/{} — test JSON:",
                    attempt, _MAX_GENERATION_ATTEMPTS,
                )
                logger.info(
                    "[TestGenerator] attempt {}/{} — questions: {}",
                    attempt, _MAX_GENERATION_ATTEMPTS,
                    json.dumps(test.to_dict(), ensure_ascii=False, indent=2),
                )

            got = _count_types(test.questions)
            if len(test.questions) == num_questions and got == counts:
                # Перенумеровываем вопросы в 1..N по порядку списка. JSON Schema
                # ограничивает `id` диапазоном 1..N, но не гарантирует ни
                # уникальность, ни порядок: модель может вернуть [1,1,3] или
                # [3,2,1]. Backend выводит `question_id = uuid5(test_id, "q:"+N)`
                # из порядкового номера, поэтому ids должны быть ровно 1..N и по
                # порядку — иначе вопросы в БД разъедутся по порядку.
                for i, q in enumerate(test.questions, start=1):
                    q.id = i
                return test

            logger.warning(
                f"TestGenerator: attempt {attempt} gave {len(test.questions)} questions "
                f"({got['single_choice']} single_choice + {got['multi_choice']} multi_choice "
                f"+ {got['open_answer']} open_answer), expected {num_questions} "
                f"({counts['single_choice']} single_choice + {counts['multi_choice']} multi_choice "
                f"+ {counts['open_answer']} open_answer)"
            )
            correction = (
                "\n\nВНИМАНИЕ: предыдущий ответ был неверным — "
                f"{len(test.questions)} вопросов ({got['single_choice']} single_choice, "
                f"{got['multi_choice']} multi_choice, {got['open_answer']} open_answer). "
                f"Нужно ровно {num_questions} вопросов: {counts['single_choice']} single_choice, "
                f"{counts['multi_choice']} multi_choice, {counts['open_answer']} open_answer. "
                "Сверься с планом — у каждого номера вопроса указан его тип. "
                "Пересчитай type_question у каждого вопроса перед отправкой."
            )

        raise ValueError(
            f"LLM did not produce the required question-type mix after "
            f"{_MAX_GENERATION_ATTEMPTS} attempts: expected {counts['single_choice']} single_choice "
            f"+ {counts['multi_choice']} multi_choice + {counts['open_answer']} open_answer"
        )


def _format_digest(per_material: list[tuple[str, list[ChunkRef]]]) -> str:
    """Склеить чанки всех материалов в один текст с разделителями.

    Каждый чанк помечен короткой меткой в квадратных скобках — по ней LLM
    ссылается на источник вопроса (`source_chunk_ref`), а мы потом разворачиваем
    метку в `chunk_id`.

    Формат:
        [Материал 15716]
        [C1] <чанк 1>

        [C2] <чанк 2>

        ---

        [Материал 87891]
        [C3] ...
    """
    parts: list[str] = []
    for mid, chunks in per_material:
        parts.append(f"[Материал {mid}]")
        parts.append("\n\n".join(f"[{c.ref}] {c.text}" for c in chunks))
    return "\n\n---\n\n".join(parts)
