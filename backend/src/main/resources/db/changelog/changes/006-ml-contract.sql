-- =============================================================================
-- Контракт с ML: эталон ответа, порядок вопросов, попытка без is_correct
-- =============================================================================

-- answer_key — эталон правильного ответа из ответа ML (JSONB):
--   single_choice → {correct_index, explanation}
--   multi_choice  → {correct_indexes[], explanation}
--   open_answer   → {reference_answer, explanation}
-- Читается ML при проверке попытки (test_questions.answer_key).
ALTER TABLE test_questions
    ADD COLUMN IF NOT EXISTS answer_key JSONB;

-- Порядок вопроса в тесте. Без этой колонки вопросы выдаются в порядке
-- случайных UUID (ORDER BY question_id), а не в порядке генерации ML.
ALTER TABLE test_questions
    ADD COLUMN IF NOT EXISTS question_order INT NOT NULL DEFAULT 0;

-- is_correct и correct_answer в схеме заказчика нет: первый выводится из
-- score (порог 0.5), второй — из answer_key вопроса при чтении попытки.
ALTER TABLE attempt_answers
    DROP COLUMN IF EXISTS is_correct;

ALTER TABLE attempt_answers
    DROP COLUMN IF EXISTS correct_answer;

CREATE INDEX IF NOT EXISTS idx_questions_test_order ON test_questions (test_id, question_order);
