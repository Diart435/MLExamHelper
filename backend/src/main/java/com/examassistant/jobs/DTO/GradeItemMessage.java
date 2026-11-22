package com.examassistant.jobs.DTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class GradeItemMessage {
    @JsonProperty("question_id")
    private UUID questionId;
    private BigDecimal score;
    @JsonProperty("is_correct")
    private Boolean correct;
    @JsonProperty("correct_answer")
    private Map<String, Object> correctAnswer;
    private String feedback;
}
