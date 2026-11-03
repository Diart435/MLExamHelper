package com.examassistant.tests.DTO;

import com.examassistant.tests.enums.TestStatus;
import lombok.Data;

import java.util.UUID;

@Data
public class TestFilter {
    private UUID courseId;
    private TestStatus statusTest;
}