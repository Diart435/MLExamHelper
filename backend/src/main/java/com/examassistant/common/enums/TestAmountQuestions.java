package com.examassistant.common.enums;


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

    /**
     * Размер теста в терминах контракта ML: целое число 1..30 — «ровно столько
     * вопросов». Бакеты backend'а разворачиваются в конкретные числа, потому что
     * ML генерирует ровно заданное число вопросов (жёсткая JSON Schema), а
     * «размер по материалу» у ML — отдельный режим ("min"), в котором размер
     * выбирает планировщик.
     */
    public int toMlAmount() {
        return switch (this) {
            case MIN -> 5;
            case MEDIUM -> 10;
            case MAX -> 20;
        };
    }
}
