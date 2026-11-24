package com.examassistant.tests.DTO;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public record AttemptResponse(
        UUID attemptId,
        UUID testId,
        String status,
        OffsetDateTime startedAt,
        OffsetDateTime finishedAt,
        BigDecimal scorePct,
        Integer grade,
        List<AttemptAnswerResponse> answers
) {
}
