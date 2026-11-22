package com.examassistant.jobs.DTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class GradeTestResultMessage {
    @JsonProperty("task_id")
    private UUID taskId;
    @JsonProperty("attempt_id")
    private UUID attemptId;
    @JsonProperty("test_id")
    private UUID testId;
    @JsonProperty("score_pct")
    private BigDecimal scorePct;
    private Integer grade;
    private List<GradeItemMessage> items;
    private String error;
}
