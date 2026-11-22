package com.examassistant.jobs.DTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Data;

import java.util.List;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class TestDataMessage {
    private String title;
    private List<QuestionDataMessage> questions;
}
