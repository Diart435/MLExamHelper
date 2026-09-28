-- =============================================================================
-- 0. Подключение расширений
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- 1. Таблица users (Пользователи)
-- =============================================================================
CREATE TABLE users (
    user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    first_name    VARCHAR(100) NOT NULL,
    last_name     VARCHAR(100) NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE users IS 'Пользователи системы';

-- =============================================================================
-- 2. Таблица courses (Учебные курсы)
-- =============================================================================
CREATE TABLE courses (
    course_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    UUID NOT NULL,
    title       VARCHAR(255) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_courses_owner FOREIGN KEY (owner_id) 
        REFERENCES users (user_id) ON DELETE CASCADE
);

COMMENT ON TABLE courses IS 'Учебные курсы';

-- =============================================================================
-- 3. Таблица materials (Учебные материалы: файлы/ссылки/видео)
-- =============================================================================
CREATE TABLE materials (
    material_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id   UUID NOT NULL,
    type        VARCHAR(50) NOT NULL, -- file, link, video, web
    title       VARCHAR(255) NOT NULL,
    source_uri  TEXT NOT NULL,       -- путь в S3/MinIO или URL
    status      VARCHAR(50) NOT NULL DEFAULT 'queued', -- queued, processing, ready, error
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_materials_course FOREIGN KEY (course_id) 
        REFERENCES courses (course_id) ON DELETE CASCADE
);

COMMENT ON TABLE materials IS 'Учебные материалы (файлы/ссылки/видео)';

-- =============================================================================
-- 4. Таблица material_chunks (Фрагменты текста для RAG и векторного поиска)
-- =============================================================================
CREATE TABLE material_chunks (
    chunk_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_id UUID NOT NULL,
    text        TEXT NOT NULL,       -- текст чанка (400-800 токенов)
    page_number INT,                 -- номер страницы (для PDF/DOCX)
    heading     VARCHAR(255),        -- заголовок/раздел
    embedding   vector(1536),        -- векторное представление (размерность 1536)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_chunks_material FOREIGN KEY (material_id) 
        REFERENCES materials (material_id) ON DELETE CASCADE
);

COMMENT ON TABLE material_chunks IS 'Фрагменты текста материалов для RAG и векторного поиска';

-- =============================================================================
-- 5. Таблица tests (Сгенерированные тесты)
-- =============================================================================
CREATE TABLE tests (
    test_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id          UUID NOT NULL,
    title              VARCHAR(255) NOT NULL,
    mode               VARCHAR(50) NOT NULL DEFAULT 'training', -- training, exam
    time_limit_minutes INT,          -- лимит времени (в минутах)
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_tests_course FOREIGN KEY (course_id) 
        REFERENCES courses (course_id) ON DELETE CASCADE
);

COMMENT ON TABLE tests IS 'Сгенерированные тесты';

-- =============================================================================
-- 6. Таблица test_questions (Вопросы теста)
-- =============================================================================
CREATE TABLE test_questions (
    question_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id         UUID NOT NULL,
    type            VARCHAR(50) NOT NULL, -- single_choice, multi_choice, true_false, open_answer
    text            TEXT NOT NULL,
    options         JSONB,               -- варианты ответов (для закрытых вопросов)
    answer_key      JSONB,               -- эталонный правильный ответ / ключи
    key_points      JSONB,               -- критерии/пункты оценки для открытых вопросов
    difficulty      VARCHAR(20) DEFAULT 'medium', -- easy, medium, hard
    source_chunk_id UUID,                -- привязка к чанку (Groundedness / цитирование)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_questions_test FOREIGN KEY (test_id) 
        REFERENCES tests (test_id) ON DELETE CASCADE,
    CONSTRAINT fk_questions_chunk FOREIGN KEY (source_chunk_id) 
        REFERENCES material_chunks (chunk_id) ON DELETE SET NULL
);

COMMENT ON TABLE test_questions IS 'Вопросы теста';

-- =============================================================================
-- 7. Таблица student_attempts (Попытки прохождения тестов студентом)
-- =============================================================================
CREATE TABLE student_attempts (
    attempt_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id     UUID NOT NULL,
    user_id     UUID NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    score_pct   NUMERIC(5, 2), -- процент правильных ответов (0-100%)
    grade       INT,           -- итоговая оценка по шкале 2-5

    CONSTRAINT fk_attempts_test FOREIGN KEY (test_id) 
        REFERENCES tests (test_id) ON DELETE CASCADE,
    CONSTRAINT fk_attempts_user FOREIGN KEY (user_id) 
        REFERENCES users (user_id) ON DELETE CASCADE
);

COMMENT ON TABLE student_attempts IS 'Попытки прохождения тестов студентом';

-- =============================================================================
-- 8. Таблица attempt_answers (Ответы студента на отдельные вопросы)
-- =============================================================================
CREATE TABLE attempt_answers (
    answer_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id     UUID NOT NULL,
    question_id    UUID NOT NULL,
    student_answer JSONB NOT NULL, -- текст или выбранные ID вариантов
    score          NUMERIC(3, 2), -- баллы за вопрос (0.0-1.0)
    feedback       TEXT,          -- разбор ошибки и фидбэк от LLM
    confidence     NUMERIC(3, 2), -- уверенность LLM-судьи
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_answers_attempt FOREIGN KEY (attempt_id) 
        REFERENCES student_attempts (attempt_id) ON DELETE CASCADE,
    CONSTRAINT fk_answers_question FOREIGN KEY (question_id) 
        REFERENCES test_questions (question_id) ON DELETE CASCADE
);

COMMENT ON TABLE attempt_answers IS 'Ответы студента на отдельные вопросы попытки';

-- =============================================================================
-- Индексы для оптимизации
-- =============================================================================
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_courses_owner ON courses(owner_id);
CREATE INDEX idx_materials_course ON materials(course_id);
CREATE INDEX idx_chunks_material ON material_chunks(material_id);
CREATE INDEX idx_tests_course ON tests(course_id);
CREATE INDEX idx_questions_test ON test_questions(test_id);
CREATE INDEX idx_attempts_user ON student_attempts(user_id);
CREATE INDEX idx_attempts_test ON student_attempts(test_id);
CREATE INDEX idx_answers_attempt ON attempt_answers(attempt_id);

-- Векторный HNSW индекс для косинусного поиска по эмбеддингам
CREATE INDEX idx_chunks_embedding ON material_chunks 
USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- Функция и триггеры автоматического обновления updated_at
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_courses_updated_at
    BEFORE UPDATE ON courses
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();