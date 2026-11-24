package com.examassistant.messaging;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class GradeTestRedisRequest {
    @JsonProperty("task_id")
    private UUID taskId;

    @JsonProperty("attempt_id")
    private UUID attemptId;

    @JsonProperty("test_id")
    private UUID testId;

    private List<Answer> answers;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Answer {
        @JsonProperty("question_id")
        private UUID questionId;

        @JsonProperty("student_answer")
        private StudentAnswerPayload studentAnswer;
    }
}
