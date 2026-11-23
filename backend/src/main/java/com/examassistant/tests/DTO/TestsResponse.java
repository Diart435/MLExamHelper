package com.examassistant.tests.DTO;

import com.examassistant.common.enums.TestDifficulty;
import com.examassistant.tests.enums.TestStatus;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TestsResponse {
    private UUID testId;
    private String title;
    private TestStatus statusTest;
    private TestDifficulty difficulty;
    // Фактическое число вопросов в тесте (пишет CreateTestResultService
    // по ответу ML). Размер теста выбирает ML-планировщик.
    private String amountQuestions;
}