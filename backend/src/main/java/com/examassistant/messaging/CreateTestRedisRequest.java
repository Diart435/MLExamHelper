package com.examassistant.messaging;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.UUID;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateTestRedisRequest {
    private UUID taskId;
    private UUID testId;
    private List<UUID> materialIds;
    private String title;
    private int numQuestions;
    private String difficulty;
    private UUID courseId;
}
