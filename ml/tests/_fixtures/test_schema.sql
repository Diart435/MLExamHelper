-- Тестовая схема для тестов ML, работающих против живой Postgres.
--
-- Это то, что ML читает при проверке попытки (`app/services/test_store.py`):
-- таблица `test_questions` в том виде, в каком её оставит backend после своей
-- миграции 006 (`answer_key JSONB` + `question_order INT`).
--
-- Отличия от боевой схемы backend'а:
--   * нет внешних ключей на `tests` и `material_chunks` — родительские таблицы
--     тестам не нужны, а их создание тянет за собой половину схемы backend'а;
--   * `DROP TABLE` отсутствует: таблица создаётся, а не пересоздаётся, чтобы
--     фикстура не снесла данные в БД, указанной не по назначению.
--
-- Чистка строк — в фикстуре `live_pg` (DELETE, а не DROP), и только если
-- текущая база выглядит как тестовая (в имени есть "test").

CREATE TABLE IF NOT EXISTS test_questions (
    question_id     UUID        PRIMARY KEY,
    test_id         UUID        NOT NULL,
    source_chunk_id UUID,
    type_question   VARCHAR(32) NOT NULL,
    text_question   TEXT        NOT NULL,
    options         JSONB,
    key_points      JSONB,
    answer_key      JSONB,
    question_order  INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_test_questions_test_order
    ON test_questions (test_id, question_order);
