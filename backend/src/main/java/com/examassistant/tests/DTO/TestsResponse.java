package com.examassistant.tests.DTO;

import com.examassistant.tests.TestDifficulty;
import com.examassistant.tests.enums.TestStatus;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TestsResponse {
    private UUID testId;
    private String title;
    private TestStatus statusTest;
    private TestDifficulty difficulty;
    private int numQuestions;
}