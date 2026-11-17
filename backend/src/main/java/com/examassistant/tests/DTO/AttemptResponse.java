package com.examassistant.tests.DTO;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Попытка прохождения теста с разбором по вопросам.
 *
 * isCorrect выводится из score (порог 0.5), correctAnswer — из answer_key
 * вопроса: в БД обе колонки не хранятся.
 *
 * status: "processing" — ML ещё не проверил попытку, "graded" — проверена.
 */
public record AttemptResponse(
        UUID attemptId,
        UUID testId,
        UUID userId,
        String status,
        OffsetDateTime startedAt,
        OffsetDateTime finishedAt,
        BigDecimal scorePct,
        Integer grade,
        List<Item> items) {

    public record Item(
            UUID questionId,
            String type,
            String questionText,
            Map<String, Object> studentAnswer,
            Boolean isCorrect,
            BigDecimal score,
            String feedback,
            String correctAnswer) {
    }
}
