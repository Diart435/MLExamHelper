"""Grader: проверяет ответы студента по вопросам из TestStore.

Три типа вопросов:
  - `single_choice` — детерминированно: индекс ответа vs `answer_key.correct_index`;
  - `multi_choice`  — детерминированно: набор индексов vs `answer_key.correct_indexes`,
                      дробный балл со штрафом за лишние отметки;
  - `open_answer`    — LLM-судья (`services/open_answer_judge.py`): score 0..1 + feedback.

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

from loguru import logger

from app.contracts import GradeAttemptTask, GradedItem, StudentAnswer
from app.services.open_answer_judge import OpenAnswerJudge
from app.services.test_store import QuestionRow, TestStore


# Порог, с которого ответ считается «в целом верным». score остаётся дробным —
# это точная мера, is_correct — грубый флаг для UI. Один порог на оба типа
# с частичным баллом: открытый вопрос и multi_choice.
PARTIAL_CORRECT_THRESHOLD = 0.5


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
    ) -> None:
        self.store = store or TestStore(dsn=self._default_dsn())
        # Судью создаём лениво: без open_answer-вопросов LLM-клиент не нужен,
        # а его конструктор требует настроек (ключ, модель).
        self._judge = judge

    @property
    def judge(self) -> OpenAnswerJudge:
        if self._judge is None:
            self._judge = OpenAnswerJudge()
        return self._judge

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
            items.append(await self._grade_one(q, ans))

        score_pct, grade = _aggregate(items, total_questions=len(questions))
        return GradingOutcome(
            score_pct=score_pct, grade=grade, items=items,
            total_questions=len(questions),
        )

    async def _grade_one(self, q: QuestionRow, ans: StudentAnswer) -> GradedItem:
        if q.type_question == "open_answer":
            return await self._grade_open_answer(q, ans)
        if q.type_question == "multi_choice":
            return self._grade_multi_choice(q, ans)
        if q.type_question != "single_choice":
            # Текущая итерация таких вопросов не генерит, но если backend пришлёт —
            # явно отказываемся, а не угадываем.
            return GradedItem(
                question_id=q.question_id, is_correct=False, score=0.0,
                feedback=f"Автопроверка для типа «{q.type_question}» пока не реализована.",
            )

        correct = q.correct_index()
        if correct is None:
            return GradedItem(
                question_id=q.question_id, is_correct=False, score=0.0,
                feedback="Не удалось прочитать правильный ответ из БД.",
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
        explanation = q.explanation()
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

    async def _grade_open_answer(self, q: QuestionRow, ans: StudentAnswer) -> GradedItem:
        """Оценка открытого вопроса LLM-судьёй.

        Судья возвращает дробный score; при недоступности LLM он сам
        отдаёт score=0.0 с явным feedback (см. open_answer_judge.FALLBACK_FEEDBACK).
        """
        reference = str(q.answer_key.get("reference_answer") or "").strip()
        criteria = q.criteria()
        student_text = ans.student_answer_text or ""

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

    def _grade_multi_choice(self, q: QuestionRow, ans: StudentAnswer) -> GradedItem:
        """Оценка multi_choice: набор отмеченных индексов против набора правильных.

        Балл частичный, со штрафом за лишние отметки:
            score = max(0, |верные ∩ отмеченные| − |отмеченные неверные|) / |верные|

        Так «отметил 1 из 2 правильных» — это 0.5, а «отметил 2 правильных и
        1 лишний» — тоже 0.5: лишняя отметка съедает найденное верное.
        """
        correct = set(q.correct_indexes())
        if not correct:
            return GradedItem(
                question_id=q.question_id, is_correct=False, score=0.0,
                feedback="Не удалось прочитать правильные варианты из БД.",
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
        explanation = q.explanation()
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
