package com.examassistant.tests.entity;

import com.examassistant.tests.TestDifficulty;
import com.examassistant.tests.enums.TestStatus;
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
@Table(name = "tests")
public class Test {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "test_id")
    private UUID testId;

    @Column(name = "title", nullable = false)
    private String title;

    @Column(name = "num_questions", nullable = false)
    private int numQuestions;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "status_test", nullable = false, length = 50)
    private TestStatus statusTest;

    @Enumerated(EnumType.STRING)
    @Column(name = "difficulty", length = 20)
    @Builder.Default
    private TestDifficulty difficulty = TestDifficulty.MEDIUM;

    @Column(name = "course_id", nullable = false)
    private UUID courseId;
}