package com.examassistant.ml.payload;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Результат индексации материала (ml-results:ingest).
 *
 * Статус успеха — "ready" (тот же смысл, что у materials.status_material),
 * ошибки — "error" с обязательным полем error.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record MlIngestResult(
        @JsonProperty("task_id") String taskId,
        @JsonProperty("status") String status,
        @JsonProperty("material_id") String materialId,
        @JsonProperty("chunks_indexed") Integer chunksIndexed,
        @JsonProperty("error") String error) {

    public boolean isReady() {
        return "ready".equals(status);
    }
}
