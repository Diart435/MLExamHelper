package com.examassistant.tests.DTO;

import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;

public record AttemptAnswerResponse(
        UUID answerId,
        UUID questionId,
        Map<String, Object> studentAnswer,
        Boolean isCorrect,
        Map<String, Object> correctAnswer,
        BigDecimal score,
        String feedback
) {
}
