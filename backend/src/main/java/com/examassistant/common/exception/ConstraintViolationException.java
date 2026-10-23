package com.examassistant.common.exception;

import java.util.Arrays;

public class ConstraintViolationException extends RuntimeException {
    public ConstraintViolationException(String message) {
        super(message);
    }

}
