package com.examassistant.tests;

import com.examassistant.tests.enums.QuestionType;
import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Data;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Data
@AllArgsConstructor
public class QuestionDTO {
    private UUID testId;

    private QuestionType typeQuestion;

    private String textQuestion;

    private List<String> options;

    private Map<String, Object> keyPoints;

    private UUID sourceChunkId;
}
