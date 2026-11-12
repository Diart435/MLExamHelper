package com.examassistant.messaging.entity;

import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.common.enums.TestAmountQuestions;
import com.examassistant.common.enums.TestDifficulty;
import jakarta.persistence.*;
import lombok.*;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@NoArgsConstructor
@Setter
@Getter
@Builder
@AllArgsConstructor
@Table(name = "query_tasks")
public class QueryTask {
    @Id
    @Column(name = "task_id", nullable = false)
    private UUID taskId;

    @Column(name = "test_id", nullable = false)
    private UUID testId;

    @Column(name = "title", nullable = false)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(name = "amount_questions", nullable = false)
    private TestAmountQuestions amountQuestions;

    @Enumerated(EnumType.STRING)
    @Column(name = "difficulty")
    private TestDifficulty difficulty;

    @Column(name = "course_id", nullable = false)
    private UUID courseId;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "finished_at")
    private OffsetDateTime finishedAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "status_task")
    private StatusTask statusTask;
}
