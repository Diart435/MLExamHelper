package com.examassistant.tests;

import com.examassistant.common.enums.TestDifficulty;
import com.examassistant.tests.enums.TestStatus;
import lombok.AllArgsConstructor;
import lombok.Data;

import java.time.OffsetDateTime;
import java.util.UUID;

@Data
@AllArgsConstructor
public class TestDTO {
    private UUID testId;
    private UUID courseId;
    private String title;
    // Фактическое число вопросов в тесте (пишет CreateTestResultService
    // по ответу ML). Размер теста выбирает ML-планировщик.
    private String amountQuestions;
    private OffsetDateTime createdAt;
    private TestStatus statusTest;
    private TestDifficulty difficulty;
}
