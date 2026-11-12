CREATE TABLE materials_test (
    test_id     UUID NOT NULL,
    material_id UUID NOT NULL,

    PRIMARY KEY (test_id, material_id),

    CONSTRAINT fk_qtm_test
        FOREIGN KEY (test_id) REFERENCES tests (test_id) ON DELETE CASCADE,
    CONSTRAINT fk_qtm_material
        FOREIGN KEY (material_id) REFERENCES materials (material_id) ON DELETE CASCADE
);

CREATE INDEX idx_qtm_materials_test   ON materials_test(material_id);

