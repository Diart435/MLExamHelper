package com.examassistant.jobs.DTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.UUID;

@Data
@AllArgsConstructor
public class TestResultResponse {
    @JsonProperty("task_id")
    private UUID taskId;

    private String status;

    @JsonProperty("test_id")
    private UUID testId;

    @JsonProperty("test")
    private TestData testData;
}
