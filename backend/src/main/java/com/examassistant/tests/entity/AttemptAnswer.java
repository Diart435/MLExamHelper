package com.examassistant.tests.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

@Entity
@NoArgsConstructor
@AllArgsConstructor
@Builder
@Getter
@Setter
@Table(name = "attempt_answers")
public class AttemptAnswer {
    @Id
    @Column(name = "answer_id")
    private UUID answerId;

    @Column(name = "attempt_id", nullable = false)
    private UUID attemptId;

    @Column(name = "question_id", nullable = false)
    private UUID questionId;

    @Column(name = "is_correct")
    private Boolean correct;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "student_answer", nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> studentAnswer;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "correct_answer", columnDefinition = "jsonb")
    private Map<String, Object> correctAnswer;

    @Column(precision = 3, scale = 2)
    private BigDecimal score;

    private String feedback;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;
}
