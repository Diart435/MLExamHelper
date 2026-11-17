"""Тесты проверки ответов: LLM-судья open_answer и Grader.

Без реального OpenRouter — мокаем LLMClient. Цель — убедиться, что:
  - single_choice проверяется детерминированно (0.0 / 1.0)
  - open_answer оценивается судьёй: дробный score и feedback
  - упавший LLM не роняет попытку: score=0.0, остальные вопросы не пострадали
  - score_pct считается от ВСЕХ вопросов теста: пропущенный вопрос даёт 0
"""

from __future__ import annotations

import pytest

from app.contracts import GradeAttemptTask, StudentAnswer
from app.services.grader import Grader
from app.services.open_answer_judge import (
    FALLBACK_FEEDBACK,
    OpenAnswerJudge,
    Verdict,
    parse_verdict,
)
from app.services.test_store import QuestionRow, _split_key_points


# ============================================================================
# Моки
# ============================================================================

class FakeLLM:
    """LLMClient-заглушка: отдаёт заранее заданный вердикт."""

    def __init__(self, verdict: dict | None = None, error: Exception | None = None):
        self.verdict = verdict
        self.error = error
        self.calls: list[dict] = []

    async def chat_json(self, user_message, *, validator, system_prompt=None, max_retries=3, schema=None):
        self.calls.append({"user": user_message, "system": system_prompt, "schema": schema})
        if self.error:
            raise self.error
        return validator(self.verdict or {})


class FakeStore:
    """TestStore-заглушка: отдаёт заранее заданные вопросы."""

    def __init__(self, questions: list[QuestionRow]):
        self._questions = questions

    async def fetch_questions(self, test_id: str) -> list[QuestionRow]:
        return self._questions


def single_choice_q(qid: str, correct: int = 0) -> QuestionRow:
    return QuestionRow(
        question_id=qid, type_question="single_choice",
        text_question=f"Вопрос {qid}?",
        options=["A", "B", "C", "D"],
        answer_key={"correct_index": correct, "explanation": "потому что A"},
        key_points=[],
    )


def open_q(qid: str, reference: str = "Эталонный ответ") -> QuestionRow:
    return QuestionRow(
        question_id=qid, type_question="open_answer",
        text_question=f"Открытый вопрос {qid}?",
        options=[],
        answer_key={"reference_answer": reference, "explanation": "пояснение"},
        key_points=["пункт 1", "пункт 2"],
    )


def multi_q(qid: str, correct: list[int] | None = None) -> QuestionRow:
    return QuestionRow(
        question_id=qid, type_question="multi_choice",
        text_question=f"Вопрос {qid}?",
        options=["A", "Б", "В", "Г"],
        answer_key={"correct_indexes": correct if correct is not None else [0, 2],
                    "explanation": "потому что A и В"},
        key_points=[],
    )


# ============================================================================
# parse_verdict
# ============================================================================

class TestParseVerdict:
    def test_ok(self):
        v = parse_verdict({"score": 0.5, "feedback": "частично"})
        assert v.score == 0.5
        assert v.feedback == "частично"

    def test_score_out_of_range_raises(self):
        with pytest.raises(ValueError, match="score"):
            parse_verdict({"score": 1.5, "feedback": "x"})

    def test_missing_score_raises(self):
        with pytest.raises(ValueError, match="score"):
            parse_verdict({"feedback": "x"})

    def test_empty_feedback_raises(self):
        with pytest.raises(ValueError, match="feedback"):
            parse_verdict({"score": 0.5, "feedback": "  "})


# ============================================================================
# OpenAnswerJudge
# ============================================================================

class TestOpenAnswerJudge:
    @pytest.mark.asyncio
    async def test_verdict_passthrough(self):
        llm = FakeLLM(verdict={"score": 0.5, "feedback": "Верно по сути"})
        judge = OpenAnswerJudge(llm=llm)
        verdict = await judge.judge(
            question="Что такое RAG?",
            reference_answer="RAG подтягивает чанки в контекст",
            criteria=["не меняет веса"],
            student_answer="Подтягивает чанки в контекст",
        )
        assert verdict.score == 0.5
        assert verdict.feedback == "Верно по сути"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_zero(self):
        llm = FakeLLM(error=RuntimeError("LLM down"))
        judge = OpenAnswerJudge(llm=llm)
        verdict = await judge.judge(
            question="q", reference_answer="r", criteria=[], student_answer="a",
        )
        assert verdict.score == 0.0
        assert verdict.feedback == FALLBACK_FEEDBACK

    @pytest.mark.asyncio
    async def test_empty_student_answer_not_asked_from_llm(self):
        llm = FakeLLM(verdict={"score": 1.0, "feedback": "верно"})
        judge = OpenAnswerJudge(llm=llm)
        verdict = await judge.judge(
            question="q", reference_answer="r", criteria=[], student_answer="   ",
        )
        assert verdict.score == 0.0
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_missing_reference_answer_not_asked_from_llm(self):
        llm = FakeLLM(verdict={"score": 1.0, "feedback": "верно"})
        judge = OpenAnswerJudge(llm=llm)
        verdict = await judge.judge(
            question="q", reference_answer="", criteria=[], student_answer="a",
        )
        assert verdict.score == 0.0
        assert llm.calls == []


# ============================================================================
# Grader
# ============================================================================

def attempt(answers: list[StudentAnswer]) -> GradeAttemptTask:
    return GradeAttemptTask(
        task_id="t1", attempt_id="a1", test_id="T1", user_id="u1", answers=answers,
    )


class TestGrader:
    @pytest.mark.asyncio
    async def test_single_choice_correct(self):
        gr = Grader(store=FakeStore([single_choice_q("q1", correct=1)]))
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=1)]))
        assert out.score_pct == 100.0
        assert out.grade == 5
        assert out.items[0].score == 1.0
        assert out.items[0].is_correct is True
        assert out.items[0].student_answer == "B"
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_single_choice_wrong(self):
        gr = Grader(store=FakeStore([single_choice_q("q1", correct=1)]))
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=0)]))
        assert out.score_pct == 0.0
        assert out.grade == 2
        assert "Неверно" in out.items[0].feedback
        assert out.items[0].student_answer == "A"
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_unanswered_question_counts_as_zero(self):
        """Пропущенный вопрос обнуляет оценку: база — все вопросы теста."""
        gr = Grader(store=FakeStore([single_choice_q("q1"), single_choice_q("q2")]))
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=0)]))
        assert out.total_questions == 2
        assert out.score_pct == 50.0
        assert out.grade == 3

    @pytest.mark.asyncio
    async def test_open_answer_scored_by_judge(self):
        class Judge:
            async def judge(self, *, question, reference_answer, criteria, student_answer):
                return Verdict(score=0.5, feedback="Частично верно")

        gr = Grader(store=FakeStore([open_q("q1")]), judge=Judge())
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_text="мой ответ"),
        ]))
        assert out.items[0].score == 0.5
        assert out.items[0].feedback == "Частично верно"
        assert out.items[0].student_answer == "мой ответ"
        assert out.items[0].correct_answer == "Эталонный ответ"
        assert out.score_pct == 50.0

    @pytest.mark.asyncio
    async def test_unexpected_judge_error_propagates(self):
        """Ошибка самого судьи (не LLM) — наружу: попытка уходит в status=error."""
        class BrokenJudge:
            async def judge(self, **kwargs):
                raise RuntimeError("judge exploded")

        gr = Grader(store=FakeStore([single_choice_q("q1"), open_q("q2")]), judge=BrokenJudge())
        with pytest.raises(RuntimeError, match="judge exploded"):
            await gr.grade(attempt([
                StudentAnswer(question_id="q1", student_answer_index=0),
                StudentAnswer(question_id="q2", student_answer_text="мой ответ"),
            ]))

    @pytest.mark.asyncio
    async def test_judge_failure_inside_grader_falls_back(self):
        """Судья внутри Grader не бросает наружу: score=0.0, попытка считается."""
        llm = FakeLLM(error=RuntimeError("LLM down"))
        gr = Grader(store=FakeStore([open_q("q1")]), judge=OpenAnswerJudge(llm=llm))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_text="мой ответ"),
        ]))
        assert out.score_pct == 0.0
        assert out.items[0].feedback == FALLBACK_FEEDBACK

    @pytest.mark.asyncio
    async def test_unknown_question_id_raises(self):
        gr = Grader(store=FakeStore([single_choice_q("q1")]))
        with pytest.raises(ValueError, match="unknown question_ids"):
            await gr.grade(attempt([StudentAnswer(question_id="qX", student_answer_index=0)]))

    @pytest.mark.asyncio
    async def test_unknown_type_is_not_guessed(self):
        q = single_choice_q("q1")
        q.type_question = "true_false"
        gr = Grader(store=FakeStore([q]))
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=0)]))
        assert out.items[0].score == 0.0
        assert "не реализована" in out.items[0].feedback


# ============================================================================
# multi_choice — детерминированная проверка с частичным баллом
# ============================================================================

class TestMultiChoiceGrading:
    @pytest.mark.asyncio
    async def test_all_correct(self):
        gr = Grader(store=FakeStore([multi_q("q1")]))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 2]),
        ]))
        assert out.items[0].score == 1.0
        assert out.items[0].is_correct is True
        assert out.items[0].feedback.startswith("Верно.")
        assert out.score_pct == 100.0

    @pytest.mark.asyncio
    async def test_partial_credit(self):
        """Отметил один из двух правильных — половина балла."""
        gr = Grader(store=FakeStore([multi_q("q1")]))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0]),
        ]))
        assert out.items[0].score == 0.5
        assert out.items[0].is_correct is True
        assert "Частично верно" in out.items[0].feedback
        assert "1 из 2" in out.items[0].feedback
        assert out.score_pct == 50.0

    @pytest.mark.asyncio
    async def test_extra_wrong_option_cancels_a_hit(self):
        """Лишняя отметка съедает найденное верное: 2 верных + 1 лишний → 0.5."""
        gr = Grader(store=FakeStore([multi_q("q1")]))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 2, 3]),
        ]))
        assert out.items[0].score == 0.5
        assert out.items[0].is_correct is True
        assert "Частично верно" in out.items[0].feedback

    @pytest.mark.asyncio
    async def test_all_wrong(self):
        gr = Grader(store=FakeStore([multi_q("q1")]))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[1, 3]),
        ]))
        assert out.items[0].score == 0.0
        assert out.items[0].is_correct is False
        assert "Неверно" in out.items[0].feedback
        assert out.score_pct == 0.0

    @pytest.mark.asyncio
    async def test_no_answer(self):
        gr = Grader(store=FakeStore([multi_q("q1")]))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[]),
        ]))
        assert out.items[0].score == 0.0
        assert "Ответ не выбран" in out.items[0].feedback

    @pytest.mark.asyncio
    async def test_unanswered_multi_choice_counts_as_zero(self):
        """Пропущенный multi_choice обнуляет оценку, как и остальные."""
        gr = Grader(store=FakeStore([multi_q("q1"), multi_q("q2")]))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 2]),
        ]))
        assert out.total_questions == 2
        assert out.score_pct == 50.0

    @pytest.mark.asyncio
    async def test_feedback_lists_correct_options(self):
        gr = Grader(store=FakeStore([multi_q("q1")]))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[1]),
        ]))
        assert "«A»" in out.items[0].feedback
        assert "«В»" in out.items[0].feedback

    @pytest.mark.asyncio
    async def test_item_keeps_student_picks(self):
        gr = Grader(store=FakeStore([multi_q("q1")]))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[1, 3]),
        ]))
        assert out.items[0].student_answer == "«Б», «Г»"
        assert out.items[0].correct_answer == "«A», «В»"

    @pytest.mark.asyncio
    async def test_broken_answer_key_gives_zero(self):
        gr = Grader(store=FakeStore([multi_q("q1", correct=[])]))
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 2]),
        ]))
        assert out.items[0].score == 0.0
        assert "Не удалось прочитать" in out.items[0].feedback


# ============================================================================
# key_points из БД — нормализация
# ============================================================================

class TestKeyPointsNormalisation:
    """fetch_questions приводит key_points к каноническому виду.

    Канон: key_points — список критериев, объяснение — в answer_key. Старая
    форма (объект {points, explanation, criteria}) ещё встречается в БД.
    """

    def test_flat_list_is_kept(self):
        assert _split_key_points(["пункт 1", "пункт 2"]) == (["пункт 1", "пункт 2"], "")

    def test_legacy_object_is_unpacked(self):
        criteria, explanation = _split_key_points(
            {"points": 2, "explanation": "пояснение", "criteria": ["пункт 1"]}
        )
        assert criteria == ["пункт 1"]
        assert explanation == "пояснение"

    def test_legacy_object_without_criteria(self):
        criteria, explanation = _split_key_points({"points": 2, "explanation": "пояснение"})
        assert criteria == []
        assert explanation == "пояснение"

    def test_null_and_garbage_give_empty(self):
        assert _split_key_points(None) == ([], "")
        assert _split_key_points("не json") == ([], "")
