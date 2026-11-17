package com.examassistant.ml.payload;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Результат генерации теста (ml-results:create_test).
 *
 * При status="ok" приходит test с вопросами, при status="error" — поле error
 * и test_id (чтобы backend знал, какую строку в tests перевести в error).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record MlCreateTestResult(
        @JsonProperty("task_id") String taskId,
        @JsonProperty("status") String status,
        @JsonProperty("test_id") String testId,
        @JsonProperty("test") MlTestData test,
        @JsonProperty("error") String error) {

    public boolean isOk() {
        return "ok".equals(status);
    }
}
