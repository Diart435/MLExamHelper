package com.examassistant.tests.DTO;

import com.examassistant.messaging.StudentAnswerPayload;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class SubmitAttemptRequest {
    @NotNull
    private List<@Valid Answer> answers;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Answer {
        @NotNull
        private UUID questionId;

        @NotNull
        @JsonProperty("student_answer")
        private StudentAnswerPayload studentAnswer;
    }
}
