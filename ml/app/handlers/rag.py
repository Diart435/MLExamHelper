"""Task handlers for the RAG worker.

=== КОНТРАКТ СООБЩЕНИЙ (для backend-команды) ===

Один тип задачи — один канал в каждом направлении. Имя канала:
'<слаг-типа-задачи>:<направление>', где направление — `be-to-ml` или `ml-to-be`.

Backend публикует в канал задачи:
    XADD ingest:be-to-ml * payload '<JSON IngestTask>'
    XADD create-test:be-to-ml * payload '<JSON CreateTestTask>'

Worker публикует в зеркальный канал результата:
    XADD ingest:ml-to-be * payload '<JSON IngestResult>'
    XADD create-test:ml-to-be * payload '<JSON CreateTestResult>'

Тип задачи задаёт ИМЯ КАНАЛА, а не поле в payload: поля `type` нет ни в
задачах, ни в результатах.

Поле 'payload' — JSON-строка. Полная схема dataclass'ов — в `app/contracts.py`.
Краткая выжимка:

  IngestTask      → IngestResult     { material_id, status }
  RAGQuestionTask → RAGQuestionResult{ answer, sources }
  CreateTestTask  → CreateTestResult { test: { title, questions: [...] } }

В каждом результате есть status="ok"|"error" и (для error) поле error. Исключение —
grade-test:ml-to-be: там статуса нет, признак ошибки — поле `error`.

=== КТО ЧТО ДЕЛАЕТ ===
- app/handlers/rag.py  — process_ingest / process_question / process_create_test
                          (чистые функции, НЕ знают про Redis; вызываются из
                          workers/ и из demo)
- app/workers/rag.py   — RAGWorker: Redis consumer loop, роутит по каналу, XADD + XACK
- app/contracts.py     — dataclass'ы задач/результатов + parse_task() dispatch
"""

from loguru import logger

from app.contracts import (
    CreateTestResult,
    CreateTestTask,
    GradeAttemptResult,
    GradeAttemptTask,
    IngestResult,
    IngestTask,
    RAGQuestionResult,
    RAGQuestionTask,
)
from app.parsers.base import UnsupportedFormatError, download_and_extract
from app.services.answer_store import AnswerStore
from app.services.grader import Grader
from app.services.rag import RAGService
from app.services.test_generator import TestGenerator


async def process_ingest(task: dict | IngestTask, rag: RAGService) -> dict:
    """Handle задачу из канала ingest:be-to-ml: скачать файл из MinIO и проиндексировать.

    Принимает и dict (сырой payload из Redis), и IngestTask (для прямого вызова
    из тестов). На выходе — dict (то, что XADD-ит воркер).
    """
    raw_mid = (
        task.get("material_id") if isinstance(task, dict) and task.get("material_id") is not None
        else (task.material_id if isinstance(task, IngestTask) else None)
    )
    raw_mid = str(raw_mid) if raw_mid is not None else None

    try:
        t = task if isinstance(task, IngestTask) else IngestTask.from_dict(task)
    except (KeyError, ValueError, TypeError) as e:
        # material_id известен из raw dict — передаём в err, чтобы backend обновил status_material
        return IngestResult.err(
            f"invalid ingest task: {e}", material_id=raw_mid,
        )._as_dict()

    try:
        text = await download_and_extract(t.storage_key)
        await rag.index_material(t.material_id, text)
        return IngestResult.ok(material_id=t.material_id)._as_dict()
    except UnsupportedFormatError as e:
        logger.error(f"Ingest failed for {t.storage_key}: {e}")
        return IngestResult.err(f"unsupported format: {e}", material_id=t.material_id)._as_dict()
    except FileNotFoundError as e:
        logger.error(f"Ingest failed for {t.storage_key}: {e}")
        return IngestResult.err(str(e), material_id=t.material_id)._as_dict()
    except Exception as e:
        logger.exception(f"Ingest failed for {t.storage_key}")
        return IngestResult.err(f"{type(e).__name__}: {e}", material_id=t.material_id)._as_dict()


async def process_question(task: dict | RAGQuestionTask, rag: RAGService) -> dict:
    """Handle задачу из канала rag-question:be-to-ml: ответить по материалу.

    Optional fields:
      - top_k: int   (default 4)  — сколько чанков отдать в LLM
      - retrieve_n: int (default = top_k) — сколько кандидатов взять из retriever'а
      - rerank: bool (default False) — включить LLM-пересортировку
        (имеет смысл только при retrieve_n > top_k; на коротких материалах
        бесполезен, потому что дороже стоит лишний LLM-вызов).
    """
    try:
        t = task if isinstance(task, RAGQuestionTask) else RAGQuestionTask.from_dict(task)
    except (KeyError, ValueError, TypeError) as e:
        return RAGQuestionResult.err(
            str(task.get("task_id", "") if isinstance(task, dict) else ""),
            f"invalid rag_question task: {e}",
        )._as_dict()

    if not await rag.has_material(t.material_id):
        return RAGQuestionResult.err(
            t.task_id, f"material {t.material_id} not indexed yet",
        )._as_dict()

    try:
        result = await rag.answer(
            t.material_id, t.question,
            top_k=t.top_k, retrieve_n=t.retrieve_n, rerank=t.rerank,
        )
        return RAGQuestionResult.ok(
            task_id=t.task_id,
            answer=result.answer,
            sources=[h.chunk_id for h in result.sources],
        )._as_dict()
    except Exception as e:
        # Лог одной строкой без traceback — иначе в demo.py сыпется много шума.
        # Полный stack есть в `error`, логи worker'а его подхватят.
        logger.error(f"Question failed for task {t.task_id}: {type(e).__name__}: {e}")
        return RAGQuestionResult.err(t.task_id, f"{type(e).__name__}: {e}")._as_dict()


async def process_create_test(
    task: dict | CreateTestTask,
    rag: RAGService,
    generator: TestGenerator | None = None,
    answer_store: AnswerStore | None = None,
) -> dict:
    """Handle задачу из канала create-test:be-to-ml: сгенерировать тест через LLM.

    Архитектура: handler валидирует задачу и формат ответа, держит LLM-вызовы
    и парсинг в TestGenerator. Сам по себе — тонкий, не делает работы.

    Эталоны правильных ответов (`answer_key`) по контракту v4.1 ВЫХОДЯТ наружу:
    backend пишет их в `test_questions.answer_key`. Дополнительно ML складывает
    их в Redis (`AnswerStore`) — это резервная копия эталона на случай, если
    в БД его нет (старые тесты) или Redis нужен как страховка. Если хранилища
    нет — тест всё равно создаётся, при проверке сработает LLM-судья.
    """
    try:
        t = task if isinstance(task, CreateTestTask) else CreateTestTask.from_dict(task)
    except (KeyError, ValueError, TypeError) as e:
        # test_id известен из raw dict — передаём в err, чтобы backend обновил status_test
        raw_tid = str(task.get("test_id", "")) if isinstance(task, dict) else ""
        return CreateTestResult.err(
            str(task.get("task_id", "") if isinstance(task, dict) else ""),
            f"invalid create_test task: {e}",
            test_id=raw_tid or None,
        )._as_dict()

    gen = generator or TestGenerator(rag=rag)
    try:
        test = await gen.generate(t)
        if answer_store is not None:
            try:
                await answer_store.save(t.test_id, test.questions)
            except Exception as e:
                # Эталоны не сохранились — тест всё равно отдаём: при проверке
                # попытки сработает LLM-судья как страховка.
                logger.warning(
                    f"create_test: не удалось сохранить эталоны в Redis "
                    f"({type(e).__name__}: {e}) — проверка пойдёт через LLM-судью"
                )
        return CreateTestResult.ok(
            task_id=t.task_id,
            test=test,
            test_id=t.test_id,
        )._as_dict()
    except ValueError as e:
        # Не проиндексированы материалы, или LLM не смогла дать валидный JSON
        logger.error(f"create_test failed for task {t.task_id}: {e}")
        return CreateTestResult.err(t.task_id, str(e), test_id=t.test_id)._as_dict()
    except Exception as e:
        logger.exception(f"create_test failed for task {t.task_id}")
        return CreateTestResult.err(t.task_id, f"{type(e).__name__}: {e}", test_id=t.test_id)._as_dict()


async def process_grade_attempt(
    task: dict | GradeAttemptTask,
    grader: Grader | None = None,
    answer_store: AnswerStore | None = None,
) -> dict:
    """Handle задачу из канала grade-test:be-to-ml: проверка ответов.

    Backend прислал попытку — список (question_id, student_answer).
    Достаём вопросы из test_questions, эталоны — из БД (`answer_key`), затем
    из Redis (AnswerStore), а если их нет — определяет LLM-судья.
    single_choice/multi_choice проверяем детерминированно по эталону,
    open_answer — LLM-судьёй (services/open_answer_judge.py). Считаем
    score_pct + grade.
    """
    raw_attempt_id = str(task.get("attempt_id", "")) if isinstance(task, dict) else task.attempt_id
    raw_test_id = str(task.get("test_id", "")) if isinstance(task, dict) else task.test_id

    try:
        t = task if isinstance(task, GradeAttemptTask) else GradeAttemptTask.from_dict(task)
    except (KeyError, ValueError, TypeError) as e:
        return GradeAttemptResult.err(
            str(task.get("task_id", "") if isinstance(task, dict) else ""),
            f"invalid grade_attempt task: {e}",
            attempt_id=raw_attempt_id or None,
            test_id=raw_test_id or None,
        )._as_dict()

    gr = grader or Grader(answer_store=answer_store)
    try:
        outcome = await gr.grade(t)
        return GradeAttemptResult.ok(
            task_id=t.task_id,
            attempt_id=t.attempt_id,
            test_id=t.test_id,
            score_pct=outcome.score_pct,
            grade=outcome.grade,
            items=outcome.items,
        )._as_dict()
    except ValueError as e:
        logger.error(f"grade_attempt failed for task {t.task_id}: {e}")
        return GradeAttemptResult.err(
            t.task_id, str(e),
            attempt_id=t.attempt_id, test_id=t.test_id,
        )._as_dict()
    except Exception as e:
        logger.exception(f"grade_attempt failed for task {t.task_id}")
        return GradeAttemptResult.err(
            t.task_id, f"{type(e).__name__}: {e}",
            attempt_id=t.attempt_id, test_id=t.test_id,
        )._as_dict()
