package com.examassistant.tests.enums;

import jakarta.persistence.EnumeratedValue;
import lombok.Getter;

@Getter
public enum QuestionType {
    SINGLE_CHOICE("single_choice"),
    MULTI_CHOICE("multi_choice"),
    OPEN_ANSWER("open_answer");

    @EnumeratedValue
    private final String value;

    QuestionType(String value) {
        this.value = value;
    }

    public static QuestionType fromValue(String value) {
        for (QuestionType type : QuestionType.values()) {
            if (type.value.equals(value)) {
                return type;
            }
        }
        throw new IllegalArgumentException("Unknown question type: " + value);
    }
}