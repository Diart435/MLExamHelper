package com.examassistant.tests;


import com.fasterxml.jackson.annotation.JsonCreator;
import jakarta.persistence.EnumeratedValue;
import lombok.Getter;

@Getter
public enum TestAmountQuestions {
    MIN("min"),
    MEDIUM("medium"),
    MAX("max");

    @EnumeratedValue
    private final String value;

    TestAmountQuestions(String value) {
        this.value = value;
    }

    @JsonCreator
    public static TestAmountQuestions fromValue(String value) {
        for (TestAmountQuestions difficulty : TestAmountQuestions.values()) {
            if (difficulty.value.equals(value)) {
                return difficulty;
            }
        }
        throw new IllegalArgumentException("Unknown question type: " + value);
    }
}
