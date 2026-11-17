package com.examassistant.ml.payload;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/**
 * Вопрос сгенерированного теста в ответе ML.
 *
 * answer_key — эталон ответа as-is: single_choice → {correct_index, explanation},
 * multi_choice → {correct_indexes[], explanation}, open_answer → {reference_answer, explanation}.
 * key_points — плоский список строк (критерии для open_answer, [] у закрытых типов).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record MlQuestionData(
        @JsonProperty("id") Integer id,
        @JsonProperty("type") String type,
        @JsonProperty("text") String text,
        @JsonProperty("options") List<String> options,
        @JsonProperty("answer_key") Map<String, Object> answerKey,
        @JsonProperty("key_points") List<String> keyPoints,
        @JsonProperty("source_chunk_id") String sourceChunkId) {
}
