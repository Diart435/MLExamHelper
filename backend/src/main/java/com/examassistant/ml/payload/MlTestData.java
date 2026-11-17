package com.examassistant.ml.payload;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public record MlTestData(
        @JsonProperty("title") String title,
        @JsonProperty("questions") List<MlQuestionData> questions) {
}
