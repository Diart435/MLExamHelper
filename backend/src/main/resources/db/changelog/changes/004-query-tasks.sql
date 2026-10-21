CREATE TABLE query_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id UUID NOT NULL,
    title TEXT NOT NULL,
    num_questions INT NOT NULL,
    difficulty VARCHAR(20),
    course_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    status_task VARCHAR(50) NOT NULL DEFAULT 'processing',

    CONSTRAINT fk_query_tasks_tests
            FOREIGN KEY (test_id) REFERENCES tests (test_id) ON DELETE CASCADE,
    CONSTRAINT fk_query_tasks_courses
            FOREIGN KEY (course_id) REFERENCES courses (course_id) ON DELETE CASCADE
);

CREATE TABLE query_tasks_materials (
    task_id     UUID NOT NULL,
    material_id UUID NOT NULL,

    PRIMARY KEY (task_id, material_id),

    CONSTRAINT fk_qtm_task
        FOREIGN KEY (task_id) REFERENCES query_tasks (task_id) ON DELETE CASCADE,
    CONSTRAINT fk_qtm_material
        FOREIGN KEY (material_id) REFERENCES materials (material_id) ON DELETE CASCADE
);

CREATE INDEX idx_query_tasks_course   ON query_tasks(course_id);
CREATE INDEX idx_query_tasks_test     ON query_tasks(test_id);
CREATE INDEX idx_query_tasks_status   ON query_tasks(status_task);
CREATE INDEX idx_qtm_material         ON query_tasks_materials(material_id);