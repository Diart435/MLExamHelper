"""Тесты Pydantic-моделей границы БД (`app/models.py`).

Что защищаем
============
Форма данных из Postgres проверяется, а не угадывается. Раньше JSONB-строка
молча превращалась в мусор: `key_points` `'["пункт 1"]'` давал `kp[0] == "["` —
студенту уходил ответ «[» вместо первого критерия.

Теперь:
  - строка вместо объекта/списка → `ValidationError` (громко, не тихо);
  - legacy-форма `key_points` (объект `{points, explanation, criteria}`)
    нормализуется в плоский список критериев — единственное исключение;
  - `answer_key=None` — «эталона нет», а не ошибка;
  - лишние поля в `AnswerKey` игнорируются (обратная совместимость с новым
    backend'ом), но неверный тип ИЗВЕСТНОГО поля — ошибка;
  - `question_id` из Postgres приходит объектом `UUID` → приводится к строке
    (домен ждёт строку, а Pydantic не сужает `UUID` → `str` сам).
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models import AnswerKey, QuestionRow, split_key_points


def _row(**kwargs) -> QuestionRow:
    """Вопрос с дефолтами — чтобы тест писал только нужное поле."""
    base = {
        "question_id": "q1",
        "type_question": "single_choice",
        "text_question": "Вопрос?",
    }
    base.update(kwargs)
    return QuestionRow(**base)


# ---------------------------------------------------------------------------
# key_points
# ---------------------------------------------------------------------------

class TestKeyPoints:
    def test_flat_list_is_kept(self):
        row = _row(key_points=["пункт 1", "пункт 2"])
        assert row.key_points == ["пункт 1", "пункт 2"]
        assert row.criteria() == ["пункт 1", "пункт 2"]

    def test_legacy_object_is_flattened(self):
        """Legacy-форма {points, explanation, criteria} → плоский список."""
        row = _row(key_points={"points": 2, "explanation": "пояснение", "criteria": ["пункт 1"]})
        assert row.key_points == ["пункт 1"]

    def test_legacy_object_without_criteria_gives_empty(self):
        row = _row(key_points={"points": 2, "explanation": "пояснение"})
        assert row.key_points == []

    def test_none_gives_empty(self):
        assert _row(key_points=None).key_points == []

    def test_string_is_rejected(self):
        """Строка вместо списка — ошибка формы, а не список символов."""
        with pytest.raises(ValidationError):
            _row(key_points='["пункт 1"]')

    def test_split_key_points_is_available_for_tests(self):
        assert split_key_points(["пункт 1"]) == (["пункт 1"], "")


# ---------------------------------------------------------------------------
# answer_key
# ---------------------------------------------------------------------------

class TestAnswerKey:
    def test_none_gives_empty_reference(self):
        row = _row(answer_key=None)
        assert row.answer_key == AnswerKey()
        assert row.answer_key.correct_index is None
        assert row.answer_key.correct_indexes == []

    def test_dict_is_validated_into_model(self):
        row = _row(answer_key={"correct_index": 2, "explanation": "потому что C"})
        assert row.answer_key.correct_index == 2
        assert row.answer_key.explanation == "потому что C"

    def test_string_is_rejected(self):
        """JSONB-строка вместо объекта — ошибка, а не «эталон в строке»."""
        with pytest.raises(ValidationError):
            _row(answer_key='{"correct_index": 1}')

    def test_list_is_rejected(self):
        with pytest.raises(ValidationError):
            _row(answer_key=["мусор"])

    def test_extra_field_is_ignored(self):
        """Лишние поля от нового backend'а не ломают разбор."""
        ak = AnswerKey.model_validate({"correct_index": 1, "some_new_field": "x"})
        assert ak.correct_index == 1

    def test_wrong_type_of_known_field_is_rejected(self):
        """Неверный тип ИЗВЕСТНОГО поля — ошибка, а не тихая подстановка."""
        with pytest.raises(ValidationError):
            AnswerKey.model_validate({"correct_indexes": "1,2"})

    def test_correct_indexes_must_be_list_of_ints(self):
        with pytest.raises(ValidationError):
            AnswerKey.model_validate({"correct_indexes": ["a"]})


# ---------------------------------------------------------------------------
# options
# ---------------------------------------------------------------------------

class TestOptions:
    def test_missing_options_gives_empty(self):
        assert _row().options == []

    def test_wrong_type_is_rejected(self):
        """Список чисел вместо строк — ошибка формы."""
        with pytest.raises(ValidationError):
            _row(options=[1, 2])

    def test_string_instead_of_list_is_rejected(self):
        with pytest.raises(ValidationError):
            _row(options="A, B")


# ---------------------------------------------------------------------------
# question_id
# ---------------------------------------------------------------------------

class TestQuestionId:
    def test_uuid_object_becomes_string(self):
        """Колонка uuid отдаётся asyncpg объектом UUID — домен ждёт строку.

        Без этого вся проверка попытки падала с ValidationError.
        """
        qid = uuid.uuid4()
        row = _row(question_id=qid)
        assert row.question_id == str(qid)
        assert isinstance(row.question_id, str)

    def test_string_stays_string(self):
        assert _row(question_id="q1").question_id == "q1"
