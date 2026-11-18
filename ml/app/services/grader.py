"""Grader: проверяет ответы студента по вопросам из TestStore.

Три типа вопросов:
  - `single_choice` — детерминированно: индекс ответа vs `correct_index`;
  - `multi_choice`  — детерминированно: набор индексов vs `correct_indexes`,
                      дробный балл со штрафом за лишние отметки;
  - `open_answer`    — LLM-судья (`services/open_answer_judge.py`): score 0..1 + feedback.

Откуда берётся эталон
=====================
Приоритет источников — **БД → Redis → LLM-судья**:

  1. **БД** — колонка `test_questions.answer_key` (контракт v4.1: backend пишет
     туда эталон, который ML отдал в `create-test:ml-to-be`). Это основной
     источник: он живёт вместе с вопросом и не имеет TTL.
  2. **Redis** — `services/answer_store.py`, резервная копия эталона (TTL 30
     дней). Ищется по нормализованному тексту вопроса: `question_id` на момент
     генерации теста ML не знал.
  3. **LLM-судья** — страховка, когда эталона нет ни там, ни там:
     - `single_choice` / `multi_choice` — `services/choice_judge.py` определяет
       правильные варианты;
     - `open_answer` — `services/open_answer_judge.py` оценивает ответ ТОЛЬКО по
       `key_points` (критериям) и тексту вопроса, без reference_answer.

Шкала оценки:
  score_pct = round(100 * sum(score_i) / total_questions)
  total_questions — ВСЕ вопросы теста, а не только те, на которые ответили:
  пропущенный вопрос должен давать 0, иначе попытка без ответов набрала бы 100%.
  grade: ≥90 → 5, ≥70 → 4, ≥50 → 3, иначе 2.

Feedback per question:
  - single_choice, верно:   "Верно. <explanation>"
  - single_choice, неверно: "Неверно. Правильный ответ: <текст правильного варианта>. <explanation>"
  - multi_choice, верно:    "Верно. <explanation>"
  - multi_choice, частично: "Частично верно: отмечено X из Y. Правильные варианты: ... <explanation>"
  - multi_choice, неверно:  "Неверно. Правильные варианты: ... <explanation>"
  - open_answer:            разбор от LLM-судьи (что верно, чего не хватает)
  - Пусто/неизвестный тип:  "Ответ не распознан."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.contracts import GradeAttemptTask, GradedItem, StudentAnswer
from app.models import AnswerKey, QuestionRow
from app.services.answer_store import AnswerStore
from app.services.choice_judge import ChoiceJudge
from app.services.open_answer_judge import OpenAnswerJudge
from app.services.test_store import TestStore


# Порог, с которого ответ считается «в целом верным». score остаётся дробным —
# это точная мера, is_correct — грубый флаг для UI. Один порог на оба типа
# с частичным баллом: открытый вопрос и multi_choice.
PARTIAL_CORRECT_THRESHOLD = 0.5

# Feedback, когда оценить не удалось: LLM упал и эталона нет.
FALLBACK_FEEDBACK = "Не удалось автоматически оценить ответ."


@dataclass
class GradingOutcome:
    """Итог проверки попытки."""

    score_pct: float
    grade: int
    items: list[GradedItem] = field(default_factory=list)
    total_questions: int = 0   # ВСЕ вопросы теста, а не только отвеченные


class Grader:
    __test__ = False  # не pytest-класс

    def __init__(
        self,
        store: TestStore | None = None,
        judge: OpenAnswerJudge | None = None,
        choice_judge: ChoiceJudge | None = None,
        answer_store: AnswerStore | None = None,
    ) -> None:
        self.store = store or TestStore(dsn=self._default_dsn())
        # Судью создаём лениво: без open_answer-вопросов LLM-клиент не нужен,
        # а его конструктор требует настроек (ключ, модель).
        self._judge = judge
        self._choice_judge = choice_judge
        # Хранилище эталонов (Redis). Без него работает только LLM-страховка.
        self.answer_store = answer_store

    @property
    def judge(self) -> OpenAnswerJudge:
        if self._judge is None:
            self._judge = OpenAnswerJudge()
        return self._judge

    @property
    def choice_judge(self) -> ChoiceJudge:
        if self._choice_judge is None:
            self._choice_judge = ChoiceJudge()
        return self._choice_judge

    @staticmethod
    def _default_dsn() -> str:
        from app.core.config import get_settings
        return get_settings().database_url

    async def grade(self, task: GradeAttemptTask) -> GradingOutcome:
        """Сопоставить ответы вопросам, посчитать score_pct и grade.

        Raises:
            ValueError: test_id не найден в БД, или answers ссылаются на
                        вопросы не из этого теста.
        """
        questions = await self.store.fetch_questions(task.test_id)
        if not questions:
            raise ValueError(f"no questions found for test_id={task.test_id}")

        by_id: dict[str, QuestionRow] = {q.question_id: q for q in questions}
        # sanity-check: все ответы должны принадлежать этому тесту
        unknown = [a.question_id for a in task.answers if a.question_id not in by_id]
        if unknown:
            raise ValueError(f"answers reference unknown question_ids: {unknown}")

        items: list[GradedItem] = []
        for ans in task.answers:
            q = by_id[ans.question_id]
            items.append(await self._grade_one(q, ans, task.test_id))

        score_pct, grade = _aggregate(items, total_questions=len(questions))
        return GradingOutcome(
            score_pct=score_pct, grade=grade, items=items,
            total_questions=len(questions),
        )

    # ------------------------------------------------------------------
    #  Эталоны
    # ------------------------------------------------------------------

    async def _reference(self, q: QuestionRow, test_id: str) -> dict[str, Any] | None:
        """Найти эталон вопроса: БД → Redis → LLM-судья.

        Возвращает словарь в одном и том же виде:
        `{"type": ..., "text": ..., "options": [...], "answer_key": AnswerKey}`.
        None — определить правильный ответ не удалось.

        Эталон из БД (`q.answer_key`) берём, только если по нему реально можно
        назвать правильный ответ: у `single_choice` есть `correct_index`, у
        `multi_choice` — непустой `correct_indexes`, у `open_answer` — непустой
        `reference_answer`. Иначе идём к следующему источнику.
        """
        from_db = _reference_from_db(q)
        if from_db is not None:
            return from_db

        if self.answer_store is not None:
            ref = await self.answer_store.find_by_text(test_id, q.text_question)
            if ref:
                parsed = _answer_key_from_ref(ref)
                if parsed is not None:
                    return {
                        "type": ref.get("type") or q.type_question,
                        "text": ref.get("text") or q.text_question,
                        "options": list(ref.get("options") or q.options),
                        "answer_key": parsed,
                    }
                logger.warning(
                    f"Grader: эталон из Redis для вопроса {q.question_id} имеет "
                    f"неверную форму — идём к следующему источнику"
                )

        # Страховка: эталона нет — определяем правильный вариант через LLM.
        if q.type_question not in ("single_choice", "multi_choice"):
            # Для open_answer эталона нет — судья оценивает по key_points,
            # это делает _grade_open_answer.
            return None

        verdict = await self.choice_judge.judge(
            question=q.text_question,
            options=q.options,
            question_type=q.type_question,
        )
        if not verdict.found:
            return None
        if q.type_question == "single_choice":
            answer_key = AnswerKey(
                correct_index=verdict.correct_indexes[0],
                explanation=verdict.explanation or None,
            )
        else:
            answer_key = AnswerKey(
                correct_indexes=list(verdict.correct_indexes),
                explanation=verdict.explanation or None,
            )
        return {
            "type": q.type_question,
            "text": q.text_question,
            "options": list(q.options),
            "answer_key": answer_key,
        }

    # ------------------------------------------------------------------
    #  Проверка по типам
    # ------------------------------------------------------------------

    async def _grade_one(
        self, q: QuestionRow, ans: StudentAnswer, test_id: str
    ) -> GradedItem:
        if q.type_question == "open_answer":
            return await self._grade_open_answer(q, ans, test_id)
        if q.type_question == "multi_choice":
            return await self._grade_multi_choice(q, ans, test_id)
        if q.type_question != "single_choice":
            # Текущая итерация таких вопросов не генерит, но если backend пришлёт —
            # явно отказываемся, а не угадываем.
            return GradedItem(
                question_id=q.question_id, is_correct=False, score=0.0,
                feedback=f"Автопроверка для типа «{q.type_question}» пока не реализована.",
            )
        return await self._grade_single_choice(q, ans, test_id)

    async def _grade_single_choice(
        self, q: QuestionRow, ans: StudentAnswer, test_id: str
    ) -> GradedItem:
        """Проверка single_choice: индекс ответа vs correct_index эталона."""
        ref = await self._reference(q, test_id)
        correct = _correct_index(ref)
        if correct is None:
            return GradedItem(
                question_id=q.question_id, is_correct=False, score=0.0,
                feedback=FALLBACK_FEEDBACK,
            )

        correct_text = q.options[correct] if 0 <= correct < len(q.options) else ""
        student_idx = ans.student_answer_index
        if student_idx is None or not (0 <= student_idx < len(q.options)):
            return GradedItem(
                question_id=q.question_id, is_correct=False, score=0.0,
                correct_answer=correct_text,
                feedback="Ответ не выбран.",
            )

        is_correct = (student_idx == correct)
        explanation = _explanation(ref)
        if is_correct:
            feedback = "Верно." + (f" {explanation}" if explanation else "")
        else:
            feedback = (
                f"Неверно. Правильный ответ: «{correct_text}»."
                + (f" {explanation}" if explanation else "")
            )

        return GradedItem(
            question_id=q.question_id,
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            correct_answer=correct_text,
            student_answer=q.options[student_idx],
            feedback=feedback,
        )

    async def _grade_open_answer(
        self, q: QuestionRow, ans: StudentAnswer, test_id: str
    ) -> GradedItem:
        """Оценка открытого вопроса LLM-судьёй.

        Эталон есть (из БД или Redis) — судья получает `reference_answer` из
        `answer_key` плюс `key_points` как критерии. Эталона нет — судья
        оценивает ТОЛЬКО по `key_points` и тексту вопроса, без
        reference_answer.
        """
        ref = await self._reference(q, test_id)
        reference = _reference_answer(ref)
        criteria = q.criteria()
        student_text = ans.student_answer_text or ""

        if not reference and not criteria:
            # Ни эталона, ни критериев — оценивать нечем, LLM не тратим.
            return GradedItem(
                question_id=q.question_id, is_correct=False, score=0.0,
                student_answer=student_text,
                feedback=FALLBACK_FEEDBACK,
            )

        verdict = await self.judge.judge(
            question=q.text_question,
            reference_answer=reference,
            criteria=criteria,
            student_answer=student_text,
        )

        return GradedItem(
            question_id=q.question_id,
            is_correct=verdict.score >= PARTIAL_CORRECT_THRESHOLD,
            score=verdict.score,
            student_answer=student_text,
            correct_answer=reference,
            feedback=verdict.feedback,
        )

    async def _grade_multi_choice(
        self, q: QuestionRow, ans: StudentAnswer, test_id: str
    ) -> GradedItem:
        """Оценка multi_choice: набор отмеченных индексов против набора правильных.

        Балл частичный, со штрафом за лишние отметки:
            score = max(0, |верные ∩ отмеченные| − |отмеченные неверные|) / |верные|

        Так «отметил 1 из 2 правильных» — это 0.5, а «отметил 2 правильных и
        1 лишний» — тоже 0.5: лишняя отметка съедает найденное верное.
        """
        ref = await self._reference(q, test_id)
        correct = set(_correct_indexes(ref))
        if not correct:
            return GradedItem(
                question_id=q.question_id, is_correct=False, score=0.0,
                feedback=FALLBACK_FEEDBACK,
            )

        student = set(ans.student_answer_indexes or [])
        if not student:
            return GradedItem(
                question_id=q.question_id, is_correct=False, score=0.0,
                correct_answer=_options_text(q, sorted(correct)),
                feedback="Ответ не выбран.",
            )

        hits = len(correct & student)
        # Отметки вне диапазона вариантов тоже считаются неверными: мусорный
        # payload не должен улучшать оценку.
        wrong = len(student - correct)
        score = max(0, hits - wrong) / len(correct)

        correct_text = _options_text(q, sorted(correct))
        explanation = _explanation(ref)
        if score == 1.0:
            feedback = "Верно." + (f" {explanation}" if explanation else "")
        elif score > 0:
            feedback = (
                f"Частично верно: отмечено {hits} из {len(correct)}. "
                f"Правильные варианты: {correct_text}."
                + (f" {explanation}" if explanation else "")
            )
        else:
            feedback = (
                f"Неверно. Правильные варианты: {correct_text}."
                + (f" {explanation}" if explanation else "")
            )

        return GradedItem(
            question_id=q.question_id,
            is_correct=score >= PARTIAL_CORRECT_THRESHOLD,
            score=score,
            student_answer=_options_text(q, sorted(student)),
            correct_answer=correct_text,
            feedback=feedback,
        )


def _answer_key(ref: dict[str, Any] | None) -> AnswerKey:
    """`answer_key` эталона (пустой, если эталона нет)."""
    if not isinstance(ref, dict):
        return AnswerKey()
    ak = ref.get("answer_key")
    return ak if isinstance(ak, AnswerKey) else AnswerKey()


def _answer_key_from_ref(ref: dict[str, Any]) -> AnswerKey | None:
    """Эталон из Redis (словарь) → модель `AnswerKey`.

    None — форма эталона неверна (или его нет): идём к следующему источнику.
    """
    raw = ref.get("answer_key") if isinstance(ref, dict) else None
    if raw is None:
        return None
    if isinstance(raw, AnswerKey):
        return raw
    if not isinstance(raw, dict):
        return None
    try:
        return AnswerKey.model_validate(raw)
    except ValidationError as e:
        logger.warning(f"Grader: эталон из Redis не прошёл валидацию ({e})")
        return None


def _reference_from_db(q: QuestionRow) -> dict[str, Any] | None:
    """Эталон из БД (`test_questions.answer_key`) — в общем виде эталона.

    None — эталона в БД нет либо по нему нельзя назвать правильный ответ
    (например, `answer_key` пустой или в нём нет ключа, нужного типу
    вопроса). Тогда источник ищется дальше: Redis → LLM-судья.
    """
    ak = q.answer_key

    if q.type_question == "single_choice":
        if ak.correct_index is None:
            return None
    elif q.type_question == "multi_choice":
        if not ak.correct_indexes:
            return None
    elif q.type_question == "open_answer":
        if not (ak.reference_answer or "").strip():
            return None
    else:
        # Тип, для которого автопроверки нет — эталон из БД не понадобится.
        return None

    return {
        "type": q.type_question,
        "text": q.text_question,
        "options": list(q.options),
        "answer_key": ak,
    }


def _correct_index(ref: dict[str, Any] | None) -> int | None:
    """Правильный индекс варианта из эталона (None, если нет)."""
    return _answer_key(ref).correct_index


def _correct_indexes(ref: dict[str, Any] | None) -> list[int]:
    """Правильные индексы вариантов из эталона (пусто, если нет)."""
    return sorted(set(_answer_key(ref).correct_indexes))


def _reference_answer(ref: dict[str, Any] | None) -> str:
    """Эталонный ответ open_answer из эталона (пусто, если нет)."""
    return (_answer_key(ref).reference_answer or "").strip()


def _explanation(ref: dict[str, Any] | None) -> str:
    """Короткое объяснение правильного ответа из эталона."""
    return (_answer_key(ref).explanation or "").strip()


def _options_text(q: QuestionRow, indexes: list[int]) -> str:
    """Тексты вариантов по индексам — «А», «Б» (для feedback и разбора попытки)."""
    texts = [q.options[i] for i in indexes if 0 <= i < len(q.options)]
    return ", ".join(f"«{t}»" for t in texts)


def _aggregate(items: list[GradedItem], total_questions: int) -> tuple[float, int]:
    """Перевести список per-question scores в score_pct + grade по 5-балльной.

    total_questions — количество ВСЕХ вопросов теста: неотвеченные дают 0,
    поэтому попытка без ответов не может набрать 100%.
    """
    if total_questions <= 0:
        return 0.0, 2
    earned = sum(i.score for i in items)
    pct = round(100.0 * earned / total_questions, 2)
    if pct >= 90:
        grade = 5
    elif pct >= 70:
        grade = 4
    elif pct >= 50:
        grade = 3
    else:
        grade = 2
    logger.info(f"Grader: {earned}/{total_questions} = {pct}% → grade={grade}")
    return pct, grade
