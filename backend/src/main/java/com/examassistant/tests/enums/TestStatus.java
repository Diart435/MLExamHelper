package com.examassistant.tests.enums;

import jakarta.persistence.EnumeratedValue;

public enum TestStatus {
    CREATING("creating"),
    CREATED("created"),
    PASSED("passed");

    @EnumeratedValue
    private final String value;

    TestStatus(String value) {
        this.value = value;
    }

    public static TestStatus fromValue(String value) {
        for (TestStatus status : TestStatus.values()) {
            if (status.value.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown question type: " + value);
    }
}