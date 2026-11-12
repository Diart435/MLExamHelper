package com.examassistant.common.enums;

import com.fasterxml.jackson.annotation.JsonCreator;
import jakarta.persistence.EnumeratedValue;
import lombok.Getter;

@Getter
public enum TestDifficulty {
    EASY("easy"),
    MEDIUM("medium"),
    HARD("hard");

    @EnumeratedValue
    private final String value;

    TestDifficulty(String value) {
        this.value = value;
    }

    @JsonCreator
    public static TestDifficulty fromValue(String value) {
        for (TestDifficulty difficulty : TestDifficulty.values()) {
            if (difficulty.value.equals(value)) {
                return difficulty;
            }
        }
        throw new IllegalArgumentException("Unknown question type: " + value);
    }
}