package com.examassistant.tests.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

/**
 * Ответ студента на один вопрос в попытке.
 *
 * student_answer пишет backend при сдаче попытки: {"index": N} / {"indexes": [...]}
 * / {"text": "..."}. score и feedback приходят от ML при проверке.
 * is_correct и correct_answer в схеме нет — они выводятся при чтении попытки
 * из score и answer_key вопроса.
 */
@Entity
@NoArgsConstructor
@Setter
@Getter
@Builder
@AllArgsConstructor
@Table(name = "attempt_answers")
public class AttemptAnswer {

    @Id
    @Column(name = "answer_id")
    private UUID answerId;

    @Column(name = "attempt_id", nullable = false)
    private UUID attemptId;

    @Column(name = "question_id", nullable = false)
    private UUID questionId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", name = "student_answer", nullable = false)
    private Map<String, Object> studentAnswer;

    @Column(name = "score", precision = 3, scale = 2)
    private BigDecimal score;

    @Column(name = "feedback", columnDefinition = "text")
    private String feedback;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;
}
