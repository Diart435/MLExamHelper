package com.examassistant.ml.payload;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Разбор одного вопроса в результате проверки попытки.
 *
 * correct_answer и student_answer приходят строками (текст правильного варианта
 * или эталон для open_answer). В БД они не сохраняются: correct_answer
 * выводится из answer_key вопроса при чтении попытки, student_answer backend
 * пишет сам при сдаче.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record MlGradedItem(
        @JsonProperty("question_id") String questionId,
        @JsonProperty("is_correct") Boolean isCorrect,
        @JsonProperty("score") Double score,
        @JsonProperty("feedback") String feedback,
        @JsonProperty("correct_answer") String correctAnswer,
        @JsonProperty("student_answer") String studentAnswer) {
}
