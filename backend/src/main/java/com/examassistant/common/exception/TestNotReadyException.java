package com.examassistant.common.exception;

import java.util.UUID;

public class TestNotReadyException extends RuntimeException {
    public TestNotReadyException(UUID testId) {
        super("Test is not ready: " + testId);
    }
}
