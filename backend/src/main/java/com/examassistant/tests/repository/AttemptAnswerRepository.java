package com.examassistant.tests.repository;

import com.examassistant.tests.entity.AttemptAnswer;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface AttemptAnswerRepository extends JpaRepository<AttemptAnswer, UUID> {
    List<AttemptAnswer> findByAttemptIdOrderByCreatedAtAsc(UUID attemptId);
    Optional<AttemptAnswer> findByAttemptIdAndQuestionId(UUID attemptId, UUID questionId);
}
