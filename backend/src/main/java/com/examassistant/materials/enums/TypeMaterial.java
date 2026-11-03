package com.examassistant.materials.enums;

import jakarta.persistence.EnumeratedValue;
import lombok.Getter;

@Getter
public enum TypeMaterial {
    PDF("pdf"),
    DOCX("docx");

    @EnumeratedValue
    private final String value;

    TypeMaterial(String value) {
        this.value = value;
    }

    public static TypeMaterial fromValue(String value) {
        for (TypeMaterial type : TypeMaterial.values()) {
            if (type.value.equals(value)) {
                return type;
            }
        }
        throw new IllegalArgumentException("Unknown question type: " + value);
    }
}
