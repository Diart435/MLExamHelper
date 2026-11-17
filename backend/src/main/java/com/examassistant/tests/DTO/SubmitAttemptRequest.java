package com.examassistant.tests.DTO;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Ответы студента при сдаче попытки.
 *
 * studentAnswer — формат контракта ML: {"index": N} для single_choice,
 * {"indexes": [N, M]} для multi_choice, {"text": "..."} для open_answer.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SubmitAttemptRequest {

    @NotEmpty(message = "Answers must not be empty")
    @Valid
    private List<Answer> answers;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class Answer {

        @NotNull(message = "Question ID must not be null")
        private UUID questionId;

        @NotNull(message = "Student answer must not be null")
        private Map<String, Object> studentAnswer;
    }
}
