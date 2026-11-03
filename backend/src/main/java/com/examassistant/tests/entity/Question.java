package com.examassistant.tests.entity;

import com.examassistant.tests.enums.QuestionType;
import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

@Entity
@NoArgsConstructor
@Setter
@Getter
@Builder
@AllArgsConstructor
@Table(name = "test_questions")
public class Question {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "question_id")
    private UUID questionId;

    @Column(name = "test_id", nullable = false)
    private UUID testId;

    @Enumerated(EnumType.STRING)
    @Column(name = "type_question", nullable = false)
    private QuestionType typeQuestion;

    @Column(name = "text_question", nullable = false)
    private String textQuestion;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", name = "options")
    private Map<String, Object> options;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", name = "answer_key")
    private Map<String, Object> answerKey;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", name = "key_points")
    private Map<String, Object> keyPoints;

    @Column(name = "source_chunk_id")
    private UUID sourceChunkId;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;
}
