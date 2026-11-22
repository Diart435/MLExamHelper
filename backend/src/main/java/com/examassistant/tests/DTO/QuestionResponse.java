package com.examassistant.tests.DTO;

import java.util.List;
import java.util.UUID;

public record QuestionResponse(
        UUID questionId,
        Integer questionOrder,
        String type,
        String text,
        List<String> options
) {
}
