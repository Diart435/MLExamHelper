package com.examassistant.tests;

import com.examassistant.tests.enums.TestDifficulty;
import com.examassistant.tests.enums.TestStatus;
import lombok.Data;

import java.time.OffsetDateTime;
import java.util.UUID;

@Data
public class TestDTO {
    private UUID testId;
    private UUID courseId;
    private String title;
    private OffsetDateTime createdAt;
    private TestStatus statusTest;
    private TestDifficulty difficulty;
}
