package com.examassistant.jobs.DTO;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;

@Data
@AllArgsConstructor
public class QuestionData {
    private int id;
    private String text;
    private String questionType;
    private List<String> options;
    private int points;
}
