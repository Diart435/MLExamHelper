package com.examassistant.jobs.DTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.UUID;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class CreateTestResultMessage {
    @JsonProperty("task_id")
    private UUID taskId;
    private String status;
    @JsonProperty("test_id")
    private UUID testId;
    private String error;
    private TestDataMessage test;
}
