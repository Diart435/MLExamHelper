package com.examassistant.tests.repository;

import com.examassistant.tests.entity.Question;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface QuestionRepository extends JpaRepository<Question, UUID> {
    // Порядок вопросов теста — по колонке question_order (миграция 006).
    List<Question> findByTestIdOrderByQuestionOrderAsc(UUID testId);
}
