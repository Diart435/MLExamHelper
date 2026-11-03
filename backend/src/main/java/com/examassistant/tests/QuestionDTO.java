package com.examassistant.tests;

import com.examassistant.tests.enums.QuestionType;
import jakarta.persistence.*;
import lombok.Data;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

@Data
public class QuestionDTO {
    private UUID questionId;

    private UUID testId;

    private QuestionType typeQuestion;

    private String textQuestion;

    private Map<String, Object> options;

    private Map<String, Object> answerKey;

    private Map<String, Object> keyPoints;

    private UUID sourceChunkId;

    private OffsetDateTime createdAt;
}
