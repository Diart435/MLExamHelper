package com.examassistant.tests.entity;

import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * Попытка прохождения теста. Создаётся backend'ом ДО публикации задачи в ML:
 * ML читает вопросы теста из test_questions, а результат проверки backend
 * записывает в эту же строку (finished_at, score_pct, grade).
 */
@Entity
@NoArgsConstructor
@Setter
@Getter
@Builder
@AllArgsConstructor
@Table(name = "student_attempts")
public class StudentAttempt {

    @Id
    @Column(name = "attempt_id")
    private UUID attemptId;

    @Column(name = "test_id", nullable = false)
    private UUID testId;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    @Column(name = "started_at", nullable = false)
    private OffsetDateTime startedAt;

    @Column(name = "finished_at")
    private OffsetDateTime finishedAt;

    @Column(name = "score_pct", precision = 5, scale = 2)
    private BigDecimal scorePct;

    @Column(name = "grade")
    private Integer grade;
}
