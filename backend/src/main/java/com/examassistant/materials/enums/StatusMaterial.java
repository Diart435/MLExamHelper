package com.examassistant.materials.enums;

import jakarta.persistence.EnumeratedValue;
import lombok.Getter;

@Getter
public enum StatusMaterial {
    PROCESSING("processing"),
    READY("ready"),
    ERROR("error");

    @EnumeratedValue
    private final String value;

    StatusMaterial(String value) {
        this.value = value;
    }

    public static StatusMaterial fromValue(String value) {
        for (StatusMaterial status : StatusMaterial.values()) {
            if (status.value.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown question type: " + value);
    }
}
