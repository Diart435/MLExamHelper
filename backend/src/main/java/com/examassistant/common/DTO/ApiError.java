package com.examassistant.common.DTO;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.time.Instant;

@Data
@AllArgsConstructor
public class ApiError {
    Instant timestamp;
    int status;
    String error;
    String message;
    String path;
}
