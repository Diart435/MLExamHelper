package com.examassistant.jobs.DTO;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;

@Data
@AllArgsConstructor
public class TestData {
    private String title;
    private List<QuestionData> questions;
}
