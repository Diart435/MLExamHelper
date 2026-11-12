package com.examassistant.messaging.enums;

import jakarta.persistence.EnumeratedValue;
import lombok.Getter;

@Getter
public enum StatusTask {
    PROCESSING("processing"),
    FINISHED("finished");

    @EnumeratedValue
    private final String value;

    StatusTask(String value) {
        this.value = value;
    }

    public static StatusTask fromValue(String value) {
        for (StatusTask status : StatusTask.values()) {
            if (status.value.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown question type: " + value);
    }
}
