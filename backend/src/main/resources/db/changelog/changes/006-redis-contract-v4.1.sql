ALTER TABLE test_questions ADD COLUMN answer_key JSONB;
ALTER TABLE test_questions ADD COLUMN question_order INT;

WITH numbered AS (
    SELECT question_id,
           ROW_NUMBER() OVER (
               PARTITION BY test_id
               ORDER BY created_at, question_id
           ) AS rn
    FROM test_questions
)
UPDATE test_questions q
SET question_order = n.rn
FROM numbered n
WHERE q.question_id = n.question_id;

ALTER TABLE test_questions ALTER COLUMN question_order SET NOT NULL;
ALTER TABLE test_questions
    ADD CONSTRAINT uq_questions_test_order UNIQUE (test_id, question_order);

ALTER TABLE attempt_answers ALTER COLUMN is_correct DROP NOT NULL;
ALTER TABLE attempt_answers ALTER COLUMN correct_answer DROP NOT NULL;

DELETE FROM attempt_answers a
USING attempt_answers b
WHERE a.attempt_id = b.attempt_id
  AND a.question_id = b.question_id
  AND a.ctid > b.ctid;

ALTER TABLE attempt_answers
    ADD CONSTRAINT uq_answers_attempt_question UNIQUE (attempt_id, question_id);
