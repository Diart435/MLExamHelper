package com.examassistant.ml.payload;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

/**
 * Результат проверки попытки (ml-results:grade_attempt).
 *
 * score_pct — процент по ВСЕМ вопросам теста (0..100), grade — 2..5.
 * items — разбор по вопросам: question_id — это question_id из БД.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record MlGradeAttemptResult(
        @JsonProperty("task_id") String taskId,
        @JsonProperty("status") String status,
        @JsonProperty("attempt_id") String attemptId,
        @JsonProperty("test_id") String testId,
        @JsonProperty("score_pct") Double scorePct,
        @JsonProperty("grade") Integer grade,
        @JsonProperty("items") List<MlGradedItem> items,
        @JsonProperty("error") String error) {

    public boolean isOk() {
        return "ok".equals(status);
    }
}
