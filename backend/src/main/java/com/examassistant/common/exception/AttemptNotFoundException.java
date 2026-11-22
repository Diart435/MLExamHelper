package com.examassistant.common.exception;

import java.util.UUID;

public class AttemptNotFoundException extends RuntimeException {
    public AttemptNotFoundException(UUID attemptId) {
        super("Attempt not found: " + attemptId);
    }
}
