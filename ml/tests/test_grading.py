"""Тесты проверки ответов: LLM-судья open_answer и Grader.

Без реального OpenRouter и без реального Redis — мокаем LLMClient и
AnswerStore. Цель — убедиться, что:
  - single_choice проверяется детерминированно (0.0 / 1.0) по эталону из Redis;
  - open_answer оценивается судьёй: дробный score и feedback;
  - если эталона нет (Redis пуст) — включается LLM-страховка;
  - упавший LLM не роняет попытку: score=0.0, остальные вопросы не пострадали;
  - score_pct считается от ВСЕХ вопросов теста: пропущенный вопрос даёт 0;
  - `correct_answer` — это ТЕКСТ правильного варианта, а не индекс.
"""

from __future__ import annotations

import uuid

import pytest

from app.contracts import GradeAttemptTask, StudentAnswer, TestQuestion
from app.models import QuestionRow, split_key_points
from app.services.answer_store import AnswerStore
from app.services.grader import FALLBACK_FEEDBACK as GRADER_FALLBACK_FEEDBACK
from app.services.grader import Grader
from app.services.open_answer_judge import (
    FALLBACK_FEEDBACK,
    OpenAnswerJudge,
    Verdict,
    parse_verdict,
)


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
    """TestStore-заглушка: отдаёт заранее заданные вопросы.

    ⚠️ `QuestionRow.answer_key` — по умолчанию пусто: эталона может не быть ни
    в БД, ни в Redis, тогда включается LLM-страховка. Эталон из БД задаётся
    явно (см. `single_choice_q(..., answer_key=...)`).
    """

    def __init__(self, questions: list[QuestionRow]):
        self._questions = questions

    async def fetch_questions(self, test_id: str) -> list[QuestionRow]:
        return self._questions


class FakeRedis:
    """Redis-заглушка: словарь значений, ничего настоящего."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int | None] = {}

    async def set(self, name: str, value: str, ex: int | None = None) -> bool:
        self.values[name] = value
        self.expirations[name] = ex
        return True

    async def get(self, name: str) -> str | None:
        return self.values.get(name)


class FakeChoiceJudge:
    """ChoiceJudge-заглушка: заранее заданные правильные индексы."""

    def __init__(self, correct_indexes: list[int] | None = None, found: bool = True):
        self.correct_indexes = correct_indexes or []
        self.found = found
        self.calls: list[dict] = []

    async def judge(self, *, question, options, question_type="single_choice"):
        self.calls.append({
            "question": question, "options": options, "question_type": question_type,
        })
        from app.services.choice_judge import ChoiceVerdict
        return ChoiceVerdict(
            correct_indexes=list(self.correct_indexes),
            explanation="судья решил",
        )


def single_choice_q(qid: str, correct: int = 0, answer_key: dict | None = None) -> QuestionRow:
    """Вопрос из БД + эталон для Redis (correct — индекс правильного варианта).

    `answer_key` — эталон в БД (`test_questions.answer_key`, контракт v4.1).
    По умолчанию пусто: эталона в БД нет, он лежит в Redis."""
    return QuestionRow(
        question_id=qid, type_question="single_choice",
        text_question=f"Вопрос {qid}?",
        options=["A", "B", "C", "D"],
        key_points=[],
        answer_key=dict(answer_key) if answer_key else {},
    )


def open_q(qid: str, reference: str = "Эталонный ответ", answer_key: dict | None = None) -> QuestionRow:
    return QuestionRow(
        question_id=qid, type_question="open_answer",
        text_question=f"Открытый вопрос {qid}?",
        options=[],
        key_points=["пункт 1", "пункт 2"],
        answer_key=dict(answer_key) if answer_key else {},
    )


def multi_q(qid: str, correct: list[int] | None = None, answer_key: dict | None = None) -> QuestionRow:
    return QuestionRow(
        question_id=qid, type_question="multi_choice",
        text_question=f"Вопрос {qid}?",
        options=["A", "Б", "В", "Г"],
        key_points=[],
        answer_key=dict(answer_key) if answer_key else {},
    )


def ref_single(text: str, correct: int, options: list[str]) -> dict:
    """Эталон single_choice в том виде, в каком он лежит в Redis."""
    return {
        "type": "single_choice",
        "text": text,
        "options": list(options),
        "answer_key": {"correct_index": correct, "explanation": "потому что A"},
    }


def ref_multi(text: str, correct: list[int], options: list[str]) -> dict:
    """Эталон multi_choice в том виде, в каком он лежит в Redis."""
    return {
        "type": "multi_choice",
        "text": text,
        "options": list(options),
        "answer_key": {"correct_indexes": list(correct), "explanation": "потому что A и В"},
    }


def ref_open(text: str, reference: str) -> dict:
    """Эталон open_answer в том виде, в каком он лежит в Redis."""
    return {
        "type": "open_answer",
        "text": text,
        "options": [],
        "answer_key": {"reference_answer": reference, "explanation": "пояснение"},
    }


def store_with(refs: dict[str, dict], test_id: str = "T1") -> AnswerStore:
    """AnswerStore с заранее записанными эталонами (номер вопроса → эталон)."""
    redis = FakeRedis()
    store = AnswerStore(redis)
    import json as _json
    redis.values[f"ml:answers:{test_id}"] = _json.dumps(
        {str(i): ref for i, ref in enumerate(refs.values(), start=1)},
        ensure_ascii=False,
    )
    return store


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
    async def test_missing_reference_and_criteria_not_asked_from_llm(self):
        llm = FakeLLM(verdict={"score": 1.0, "feedback": "верно"})
        judge = OpenAnswerJudge(llm=llm)
        verdict = await judge.judge(
            question="q", reference_answer="", criteria=[], student_answer="a",
        )
        assert verdict.score == 0.0
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_missing_reference_but_criteria_present_judged_by_criteria(self):
        """Эталона нет (Redis очистили), но key_points в БД есть — судья всё
        равно оценивает: по критериям и смыслу вопроса."""
        llm = FakeLLM(verdict={"score": 0.75, "feedback": "раскрыты пункты"})
        judge = OpenAnswerJudge(llm=llm)
        verdict = await judge.judge(
            question="q", reference_answer="", criteria=["пункт 1"], student_answer="a",
        )
        assert verdict.score == 0.75
        assert llm.calls, "судья должен позвать LLM — есть критерии"
        assert "пункт 1" in llm.calls[0]["user"]
        assert "—" in llm.calls[0]["user"], "пустой эталон помечается прочерком"


# ============================================================================
# Grader
# ============================================================================

def attempt(answers: list[StudentAnswer]) -> GradeAttemptTask:
    return GradeAttemptTask(
        task_id="t1", attempt_id="a1", test_id="T1", answers=answers,
    )


class TestGrader:
    @pytest.mark.asyncio
    async def test_single_choice_correct(self):
        q = single_choice_q("q1", correct=1)
        store = store_with({"1": ref_single(q.text_question, 1, q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=1)]))
        assert out.score_pct == 100.0
        assert out.grade == 5
        assert out.items[0].score == 1.0
        assert out.items[0].is_correct is True
        assert out.items[0].student_answer == "B"
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_single_choice_wrong(self):
        q = single_choice_q("q1", correct=1)
        store = store_with({"1": ref_single(q.text_question, 1, q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=0)]))
        assert out.score_pct == 0.0
        assert out.grade == 2
        assert "Неверно" in out.items[0].feedback
        assert out.items[0].student_answer == "A"
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_correct_answer_is_text_not_index(self):
        """`correct_answer` в контракте — строка: текст правильного варианта,
        а не его индекс."""
        q = single_choice_q("q1", correct=2)
        store = store_with({"1": ref_single(q.text_question, 2, q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=2)]))
        assert out.items[0].correct_answer == "C"
        assert out.items[0].correct_answer != "2"

    @pytest.mark.asyncio
    async def test_unanswered_question_counts_as_zero(self):
        """Пропущенный вопрос обнуляет оценку: база — все вопросы теста."""
        q1 = single_choice_q("q1")
        q2 = single_choice_q("q2")
        store = store_with({
            "1": ref_single(q1.text_question, 0, q1.options),
            "2": ref_single(q2.text_question, 0, q2.options),
        })
        gr = Grader(store=FakeStore([q1, q2]), answer_store=store)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=0)]))
        assert out.total_questions == 2
        assert out.score_pct == 50.0
        assert out.grade == 3

    @pytest.mark.asyncio
    async def test_open_answer_scored_by_judge(self):
        class Judge:
            async def judge(self, *, question, reference_answer, criteria, student_answer):
                return Verdict(score=0.5, feedback="Частично верно")

        q = open_q("q1")
        store = store_with({"1": ref_open(q.text_question, "Эталонный ответ")})
        gr = Grader(store=FakeStore([q]), judge=Judge(), answer_store=store)
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

        q = single_choice_q("q1")
        q2 = open_q("q2")
        store = store_with({
            "1": ref_single(q.text_question, 0, q.options),
            "2": ref_open(q2.text_question, "Эталон"),
        })
        gr = Grader(store=FakeStore([q, q2]), judge=BrokenJudge(), answer_store=store)
        with pytest.raises(RuntimeError, match="judge exploded"):
            await gr.grade(attempt([
                StudentAnswer(question_id="q1", student_answer_index=0),
                StudentAnswer(question_id="q2", student_answer_text="мой ответ"),
            ]))

    @pytest.mark.asyncio
    async def test_judge_failure_inside_grader_falls_back(self):
        """Судья внутри Grader не бросает наружу: score=0.0, попытка считается."""
        llm = FakeLLM(error=RuntimeError("LLM down"))
        q = open_q("q1")
        store = store_with({"1": ref_open(q.text_question, "Эталонный ответ")})
        gr = Grader(
            store=FakeStore([q]), judge=OpenAnswerJudge(llm=llm), answer_store=store,
        )
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_text="мой ответ"),
        ]))
        assert out.score_pct == 0.0
        assert out.items[0].feedback == FALLBACK_FEEDBACK

    @pytest.mark.asyncio
    async def test_unknown_question_id_raises(self):
        q = single_choice_q("q1")
        store = store_with({"1": ref_single(q.text_question, 0, q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        with pytest.raises(ValueError, match="unknown question_ids"):
            await gr.grade(attempt([StudentAnswer(question_id="qX", student_answer_index=0)]))

    @pytest.mark.asyncio
    async def test_unknown_type_is_not_guessed(self):
        q = single_choice_q("q1")
        q.type_question = "true_false"
        store = store_with({"1": ref_single(q.text_question, 0, q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=0)]))
        assert out.items[0].score == 0.0
        assert "не реализована" in out.items[0].feedback


# ============================================================================
# multi_choice — детерминированная проверка с частичным баллом
# ============================================================================

class TestMultiChoiceGrading:
    @pytest.mark.asyncio
    async def test_all_correct(self):
        q = multi_q("q1")
        store = store_with({"1": ref_multi(q.text_question, [0, 2], q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
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
        q = multi_q("q1")
        store = store_with({"1": ref_multi(q.text_question, [0, 2], q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
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
        q = multi_q("q1")
        store = store_with({"1": ref_multi(q.text_question, [0, 2], q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 2, 3]),
        ]))
        assert out.items[0].score == 0.5
        assert out.items[0].is_correct is True
        assert "Частично верно" in out.items[0].feedback

    @pytest.mark.asyncio
    async def test_all_wrong(self):
        q = multi_q("q1")
        store = store_with({"1": ref_multi(q.text_question, [0, 2], q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[1, 3]),
        ]))
        assert out.items[0].score == 0.0
        assert out.items[0].is_correct is False
        assert "Неверно" in out.items[0].feedback
        assert out.score_pct == 0.0

    @pytest.mark.asyncio
    async def test_no_answer(self):
        q = multi_q("q1")
        store = store_with({"1": ref_multi(q.text_question, [0, 2], q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[]),
        ]))
        assert out.items[0].score == 0.0
        assert "Ответ не выбран" in out.items[0].feedback

    @pytest.mark.asyncio
    async def test_unanswered_multi_choice_counts_as_zero(self):
        """Пропущенный multi_choice обнуляет оценку, как и остальные."""
        q1 = multi_q("q1")
        q2 = multi_q("q2")
        store = store_with({
            "1": ref_multi(q1.text_question, [0, 2], q1.options),
            "2": ref_multi(q2.text_question, [0, 2], q2.options),
        })
        gr = Grader(store=FakeStore([q1, q2]), answer_store=store)
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 2]),
        ]))
        assert out.total_questions == 2
        assert out.score_pct == 50.0

    @pytest.mark.asyncio
    async def test_feedback_lists_correct_options(self):
        q = multi_q("q1")
        store = store_with({"1": ref_multi(q.text_question, [0, 2], q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[1]),
        ]))
        assert "«A»" in out.items[0].feedback
        assert "«В»" in out.items[0].feedback

    @pytest.mark.asyncio
    async def test_item_keeps_student_picks(self):
        q = multi_q("q1")
        store = store_with({"1": ref_multi(q.text_question, [0, 2], q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[1, 3]),
        ]))
        assert out.items[0].student_answer == "«Б», «Г»"
        assert out.items[0].correct_answer == "«A», «В»"

    @pytest.mark.asyncio
    async def test_broken_answer_key_gives_zero(self):
        """Эталон без correct_indexes — оценить нечем: score=0.0."""
        q = multi_q("q1")
        ref = ref_multi(q.text_question, [], q.options)
        store = store_with({"1": ref})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 2]),
        ]))
        assert out.items[0].score == 0.0
        assert out.items[0].feedback == GRADER_FALLBACK_FEEDBACK


# ============================================================================
# Эталона нет — LLM-страховка
# ============================================================================

class TestJudgeFallbackWithoutReference:
    """Эталона в Redis нет (Redis очистился, тест сгенерирован до появления
    хранилища) — ML не должна зачислять попытку как «всё неверно»: включается
    LLM-страховка."""

    @pytest.mark.asyncio
    async def test_single_choice_falls_back_to_choice_judge(self):
        q = single_choice_q("q1")
        choice_judge = FakeChoiceJudge(correct_indexes=[1])
        gr = Grader(
            store=FakeStore([q]),
            answer_store=AnswerStore(FakeRedis()),
            choice_judge=choice_judge,
        )
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=1)]))
        assert len(choice_judge.calls) == 1
        assert out.items[0].score == 1.0
        assert out.items[0].is_correct is True
        assert out.items[0].correct_answer == "B"
        assert out.score_pct == 100.0

    @pytest.mark.asyncio
    async def test_multi_choice_falls_back_to_choice_judge(self):
        q = multi_q("q1")
        choice_judge = FakeChoiceJudge(correct_indexes=[0, 2])
        gr = Grader(
            store=FakeStore([q]),
            answer_store=AnswerStore(FakeRedis()),
            choice_judge=choice_judge,
        )
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 2]),
        ]))
        assert len(choice_judge.calls) == 1
        assert out.items[0].score == 1.0
        assert out.items[0].correct_answer == "«A», «В»"

    @pytest.mark.asyncio
    async def test_open_answer_judged_by_key_points_only(self):
        """Эталона нет, но key_points (критерии) в БД есть — судья оценивает
        по ним, без reference_answer."""
        q = open_q("q1")

        class Judge:
            def __init__(self):
                self.seen = {}

            async def judge(self, *, question, reference_answer, criteria, student_answer):
                self.seen = {
                    "question": question,
                    "reference_answer": reference_answer,
                    "criteria": criteria,
                    "student_answer": student_answer,
                }
                return Verdict(score=0.75, feedback="Раскрыты основные пункты")

        judge = Judge()
        gr = Grader(
            store=FakeStore([q]),
            judge=judge,
            answer_store=AnswerStore(FakeRedis()),
        )
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_text="мой ответ"),
        ]))
        assert judge.seen["reference_answer"] == ""
        assert judge.seen["criteria"] == ["пункт 1", "пункт 2"]
        assert out.items[0].score == 0.75
        assert out.items[0].is_correct is True

    @pytest.mark.asyncio
    async def test_llm_failure_without_reference_gives_zero(self):
        """Ни эталона, ни рабочего LLM — score=0.0 и явный feedback, попытка не
        падает."""
        q = single_choice_q("q1")
        choice_judge = FakeChoiceJudge(correct_indexes=[], found=False)
        gr = Grader(
            store=FakeStore([q]),
            answer_store=AnswerStore(FakeRedis()),
            choice_judge=choice_judge,
        )
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=0)]))
        assert out.items[0].score == 0.0
        assert out.items[0].is_correct is False
        assert out.items[0].feedback == GRADER_FALLBACK_FEEDBACK
        assert out.score_pct == 0.0

    @pytest.mark.asyncio
    async def test_one_broken_question_does_not_break_the_attempt(self):
        """Сбойный вопрос не роняет попытку: остальные вопросы проверяются."""
        q1 = single_choice_q("q1")
        q2 = single_choice_q("q2")

        class Judge:
            def __init__(self):
                self.n = 0

            async def judge(self, *, question, options, question_type="single_choice"):
                self.n += 1
                from app.services.choice_judge import ChoiceVerdict
                if self.n == 1:
                    return ChoiceVerdict(correct_indexes=[], explanation="")
                return ChoiceVerdict(correct_indexes=[0], explanation="")

        gr = Grader(
            store=FakeStore([q1, q2]),
            answer_store=AnswerStore(FakeRedis()),
            choice_judge=Judge(),
        )
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_index=0),
            StudentAnswer(question_id="q2", student_answer_index=0),
        ]))
        assert out.total_questions == 2
        assert out.items[0].score == 0.0
        assert out.items[1].score == 1.0
        assert out.score_pct == 50.0


# ============================================================================
# Приоритет эталона: БД → Redis → LLM-судья
# ============================================================================

class TestReferencePriority:
    """Контракт v4.1: эталон лежит в БД (`test_questions.answer_key`).

    Порядок источников: **БД → Redis → LLM-судья**. Redis — резервная копия
    (TTL 30 дней), LLM-судья — последняя страховка.
    """

    @pytest.mark.asyncio
    async def test_db_reference_wins_over_redis(self):
        """Эталон в БД главнее эталона в Redis — даже если они разные."""
        q = single_choice_q("q1", answer_key={"correct_index": 2})
        # В Redis лежит другой (устаревший) эталон — он не должен побеждать.
        store = store_with({"1": ref_single(q.text_question, 0, q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=2)]))
        assert out.items[0].is_correct is True
        assert out.items[0].correct_answer == "C"
        assert out.score_pct == 100.0

    @pytest.mark.asyncio
    async def test_db_reference_avoids_llm_judge(self):
        """Эталон в БД есть — LLM-судья НЕ вызывается вовсе.

        Это ровно та причина, по которой эталон вернули в контракт: LLM-фолбэк
        уже давал неверный вердикт (назвал 2 правильных варианта вместо 3)."""
        q = single_choice_q("q1", answer_key={"correct_index": 1})

        class FailingChoiceJudge:
            async def judge(self, **kwargs):
                raise AssertionError("LLM-судья не должен вызываться при эталоне в БД")

        gr = Grader(store=FakeStore([q]), choice_judge=FailingChoiceJudge())
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=1)]))
        assert out.items[0].is_correct is True
        assert out.items[0].score == 1.0
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_db_multi_choice_reference_is_deterministic(self):
        """multi_choice с эталоном в БД — детерминированный дробный балл."""
        q = multi_q("q1", answer_key={"correct_indexes": [0, 1, 2]})

        class FailingChoiceJudge:
            async def judge(self, **kwargs):
                raise AssertionError("LLM-судья не должен вызываться при эталоне в БД")

        gr = Grader(store=FakeStore([q]), choice_judge=FailingChoiceJudge())
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 1]),
        ]))
        assert out.items[0].score == pytest.approx(2 / 3)
        assert out.items[0].is_correct is True
        # correct_answer — все правильные варианты эталона, а не отмеченные.
        assert out.items[0].correct_answer == "«A», «Б», «В»"

    @pytest.mark.asyncio
    async def test_db_open_answer_reference_fills_correct_answer(self):
        """Эталон open_answer из БД → `correct_answer` непустой.

        Чинит баг с пустым `correct_answer`, когда эталона в Redis не было."""
        q = open_q("q1", answer_key={"reference_answer": "Эталон из БД"})

        class Judge:
            def __init__(self):
                self.seen = {}

            async def judge(self, *, question, reference_answer, criteria, student_answer):
                self.seen = {"reference_answer": reference_answer}
                return Verdict(score=1.0, feedback="Верно")

        judge = Judge()
        gr = Grader(store=FakeStore([q]), judge=judge)
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_text="мой ответ"),
        ]))
        assert judge.seen["reference_answer"] == "Эталон из БД"
        assert out.items[0].correct_answer == "Эталон из БД"
        assert out.items[0].score == 1.0

    @pytest.mark.asyncio
    async def test_redis_used_when_db_has_no_reference(self):
        """Эталона в БД нет — берём из Redis (резервная копия)."""
        q = single_choice_q("q1")
        store = store_with({"1": ref_single(q.text_question, 1, q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=1)]))
        assert out.items[0].is_correct is True
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_empty_db_answer_key_falls_through_to_redis(self):
        """Пустой `answer_key` в БД — это «эталона нет»: идём дальше, в Redis.

        Иначе пустой эталон «замаскировал» бы рабочий Redis-эталон."""
        q = single_choice_q("q1", answer_key={})
        store = store_with({"1": ref_single(q.text_question, 1, q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=1)]))
        assert out.items[0].is_correct is True
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_incomplete_db_answer_key_falls_through_to_redis(self):
        """Эталон в БД есть, но без ключа, нужного типу вопроса, — считаем,
        что эталона нет, и идём в Redis."""
        # multi_choice, а в answer_key лежит correct_index — тип не тот.
        q = multi_q("q1", answer_key={"correct_index": 1})
        store = store_with({"1": ref_multi(q.text_question, [0, 2], q.options)})
        gr = Grader(store=FakeStore([q]), answer_store=store)
        out = await gr.grade(attempt([
            StudentAnswer(question_id="q1", student_answer_indexes=[0, 2]),
        ]))
        assert out.items[0].score == 1.0
        assert out.items[0].correct_answer == "«A», «В»"

    @pytest.mark.asyncio
    async def test_llm_judge_used_when_neither_db_nor_redis(self):
        """Ни в БД, ни в Redis эталона нет — включается LLM-судья.

        Существующий фолбэк не должен сломаться от нового приоритета."""
        q = single_choice_q("q1")
        choice_judge = FakeChoiceJudge(correct_indexes=[1])
        gr = Grader(
            store=FakeStore([q]),
            answer_store=AnswerStore(FakeRedis()),
            choice_judge=choice_judge,
        )
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=1)]))
        assert len(choice_judge.calls) == 1
        assert out.items[0].is_correct is True
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_malformed_redis_reference_falls_through_to_llm_judge(self):
        """Эталон в Redis с неверной формой — источник считается недоступным.

        Иначе битый эталон молча превращался бы в «правильный ответ» или в
        пустоту, и попытка засчитывалась бы неверно."""
        q = single_choice_q("q1")
        broken = {
            "type": "single_choice",
            "text": q.text_question,
            "options": list(q.options),
            "answer_key": {"correct_indexes": "1,2"},  # строка вместо списка
        }
        store = store_with({"1": broken})
        choice_judge = FakeChoiceJudge(correct_indexes=[1])
        gr = Grader(store=FakeStore([q]), answer_store=store, choice_judge=choice_judge)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=1)]))
        assert len(choice_judge.calls) == 1
        assert out.items[0].is_correct is True
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_redis_reference_of_wrong_type_falls_through_to_llm_judge(self):
        """answer_key в Redis — не словарь (например, строка) → источник недоступен."""
        q = single_choice_q("q1")
        broken = {
            "type": "single_choice",
            "text": q.text_question,
            "options": list(q.options),
            "answer_key": '{"correct_index": 1}',
        }
        store = store_with({"1": broken})
        choice_judge = FakeChoiceJudge(correct_indexes=[2])
        gr = Grader(store=FakeStore([q]), answer_store=store, choice_judge=choice_judge)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=2)]))
        assert len(choice_judge.calls) == 1
        assert out.items[0].correct_answer == "C"


# ============================================================================
# key_points из БД — нормализация
# ============================================================================

class TestKeyPointsNormalisation:
    """fetch_questions приводит key_points к каноническому виду.

    Канон: key_points — список критериев. Старая форма (объект
    {points, explanation, criteria}) ещё встречается в БД.
    """

    def test_flat_list_is_kept(self):
        assert split_key_points(["пункт 1", "пункт 2"]) == (["пункт 1", "пункт 2"], "")

    def test_legacy_object_is_unpacked(self):
        criteria, explanation = split_key_points(
            {"points": 2, "explanation": "пояснение", "criteria": ["пункт 1"]}
        )
        assert criteria == ["пункт 1"]
        assert explanation == "пояснение"

    def test_legacy_object_without_criteria(self):
        criteria, explanation = split_key_points({"points": 2, "explanation": "пояснение"})
        assert criteria == []
        assert explanation == "пояснение"

    def test_null_and_garbage_give_empty(self):
        assert split_key_points(None) == ([], "")
        assert split_key_points("не json") == ([], "")


# ============================================================================
# Эталоны сохраняются в Redis и читаются обратно
# ============================================================================

class TestAnswerStoreIntegration:
    """Эталоны, сохранённые при генерации теста, должны находиться при
    проверке попытки — по тексту вопроса, а не по question_id (его ML не знает
    на момент генерации)."""

    @pytest.mark.asyncio
    async def test_saved_reference_is_found_by_question_text(self):
        redis = FakeRedis()
        store = AnswerStore(redis)
        question = TestQuestion(
            id=1, text="Что такое RAG?", type_question="single_choice",
            options=["A", "B"], answer_key={"correct_index": 1, "explanation": "потому что B"},
        )
        assert await store.save("T1", [question]) == 1

        found = await store.find_by_text("T1", "Что такое RAG?")
        assert found is not None
        assert found["answer_key"]["correct_index"] == 1

    @pytest.mark.asyncio
    async def test_reference_is_found_despite_whitespace_and_case(self):
        redis = FakeRedis()
        store = AnswerStore(redis)
        question = TestQuestion(
            id=1, text="Что такое RAG?", type_question="single_choice",
            options=["A", "B"], answer_key={"correct_index": 1},
        )
        await store.save("T1", [question])
        found = await store.find_by_text("T1", "  что   такое rag? ")
        assert found is not None

    @pytest.mark.asyncio
    async def test_uuid_representation_does_not_trigger_llm_fallback(self):
        """Эталон сохранён с дефисами, проверка пришла с hex — эталон найден."""
        test_id = uuid.uuid4()
        redis = FakeRedis()
        store = AnswerStore(redis)
        question = TestQuestion(
            id=1, text="Вопрос q1?", type_question="single_choice",
            options=["A", "B", "C", "D"],
            answer_key={"correct_index": 1, "explanation": "потому что B"},
        )
        await store.save(str(test_id), [question])

        class FailingChoiceJudge:
            async def judge(self, **kwargs):
                raise AssertionError("LLM-судья не должен вызываться при найденном эталоне")

        row = QuestionRow(
            question_id="q1", type_question="single_choice",
            text_question="Вопрос q1?", options=["A", "B", "C", "D"], key_points=[],
        )
        task = GradeAttemptTask(
            task_id="t1", attempt_id="a1", test_id=test_id.hex,
            answers=[StudentAnswer(question_id="q1", student_answer_index=1)],
        )
        gr = Grader(
            store=FakeStore([row]), answer_store=store, choice_judge=FailingChoiceJudge(),
        )
        out = await gr.grade(task)
        assert out.items[0].score == 1.0
        assert out.items[0].is_correct is True
        assert out.items[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_missing_reference_returns_none(self):
        store = AnswerStore(FakeRedis())
        assert await store.find_by_text("T1", "Что такое RAG?") is None

    @pytest.mark.asyncio
    async def test_saved_reference_is_used_by_grader(self):
        """Сквозной путь: сохранили эталон → grader нашёл его по тексту →
        проверил ответ детерминированно."""
        redis = FakeRedis()
        store = AnswerStore(redis)
        question = TestQuestion(
            id=1, text="Вопрос q1?", type_question="single_choice",
            options=["A", "B", "C", "D"],
            answer_key={"correct_index": 1, "explanation": "потому что B"},
        )
        await store.save("T1", [question])

        row = QuestionRow(
            question_id="q1", type_question="single_choice",
            text_question="Вопрос q1?", options=["A", "B", "C", "D"], key_points=[],
        )
        gr = Grader(store=FakeStore([row]), answer_store=store)
        out = await gr.grade(attempt([StudentAnswer(question_id="q1", student_answer_index=1)]))
        assert out.items[0].score == 1.0
        assert out.items[0].correct_answer == "B"
