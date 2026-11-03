package com.examassistant.messaging;

import com.examassistant.messaging.enums.StatusTask;
import lombok.AllArgsConstructor;
import lombok.Data;

import java.time.OffsetDateTime;
import java.util.UUID;

@Data
@AllArgsConstructor
public class TaskDTO {
    private UUID testId;
    private UUID courseId;
    private String title;
    private OffsetDateTime createdAt;
    private OffsetDateTime finishedAt;
    private StatusTask statusTask;
    private int numQuestions;
    private String difficulty;
}
