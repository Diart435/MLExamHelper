package com.examassistant.jobs.DTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class QuestionDataMessage {
    private Integer id;
    private String type;
    private String text;
    private List<String> options;
    @JsonProperty("answer_key")
    private Map<String, Object> answerKey;
    @JsonProperty("source_chunk_id")
    private UUID sourceChunkId;
}
