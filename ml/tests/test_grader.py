"""Грейдер детерминированный — проверяем его целиком, без моков на БД и LLM."""

import pytest

from app.contracts import GradeAttemptTask, StudentAnswer
from app.db.questions import QuestionRow
from app.services.grader import grade


def q(
    question_id: str,
    correct: int | None = 0,
    options: list[str] | None = None,
    type_question: str = "single_choice",
) -> QuestionRow:
    options = options if options is not None else ["верно", "неверно", "третий"]
    answer_key = {} if correct is None else {"correct_index": correct}
    return QuestionRow(
        question_id=question_id,
        text=f"Вопрос {question_id}",
        type_question=type_question,
        options=options,
        answer_key=answer_key,
    )


def task(*answers: tuple[str, int | None], test_id: str = "te1") -> GradeAttemptTask:
    return GradeAttemptTask(
        task_id="t1",
        attempt_id="a1",
        test_id=test_id,
        answers=[StudentAnswer(question_id=qid, student_answer_index=idx) for qid, idx in answers],
    )


def test_all_correct():
    graded = grade(task(("q1", 0), ("q2", 0)), [q("q1", 0), q("q2", 0)])
    assert graded.score_pct == 100.0
    assert graded.grade == 5
    assert graded.mistakes == []


def test_half_correct():
    graded = grade(task(("q1", 0), ("q2", 2)), [q("q1", 0), q("q2", 0)])
    assert graded.score_pct == 50.0
    assert graded.grade == 3
    assert [i.score for i in graded.items] == [1.0, 0.0]


def test_unanswered_question_scores_zero():
    """Попытка без единого ответа обязана давать 0%, а не 100%."""
    graded = grade(task(), [q("q1", 0), q("q2", 0), q("q3", 0)])
    assert graded.score_pct == 0.0
    assert graded.grade == 2
    assert len(graded.mistakes) == 3


def test_answers_for_unknown_questions_are_ignored():
    graded = grade(task(("q1", 0), ("ghost", 0)), [q("q1", 0)])
    assert graded.score_pct == 100.0
    assert len(graded.items) == 1


def test_wrong_index_is_a_mistake_with_both_texts():
    graded = grade(task(("q1", 1)), [q("q1", 0)])
    assert graded.score_pct == 0.0
    mistake = graded.mistakes[0]
    assert mistake.student_answer == "неверно"
    assert mistake.correct_answer == "верно"


def test_question_without_answer_key_cannot_be_graded():
    graded = grade(task(("q1", 0)), [q("q1", correct=None)])
    assert graded.items[0].score == 0.0
    assert "не реализована" in (graded.mistakes[0].reason or "")


def test_unsupported_question_type_is_not_a_crash():
    graded = grade(task(("q1", 0)), [q("q1", 0, type_question="multiple_choice")])
    assert graded.score_pct == 0.0
    assert "multiple_choice" in (graded.mistakes[0].reason or "")


def test_test_without_questions_is_an_error():
    with pytest.raises(ValueError):
        grade(task(), [])


def test_score_pct_is_rounded_to_two_decimals():
    graded = grade(task(("q1", 0), ("q2", 1), ("q3", 0)), [q("q1", 0), q("q2", 0), q("q3", 0)])
    assert graded.score_pct == 66.67
    assert graded.grade == 3