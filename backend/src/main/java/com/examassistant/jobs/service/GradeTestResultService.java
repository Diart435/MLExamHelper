package com.examassistant.jobs.service;

import com.examassistant.jobs.DTO.GradeItemMessage;
import com.examassistant.jobs.DTO.GradeTestResultMessage;
import com.examassistant.tests.entity.AttemptAnswer;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.entity.StudentAttempt;
import com.examassistant.tests.repository.AttemptAnswerRepository;
import com.examassistant.tests.repository.QuestionRepository;
import com.examassistant.tests.repository.StudentAttemptRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class GradeTestResultService {
    private static final BigDecimal CORRECT_THRESHOLD = new BigDecimal("0.5");

    private final StudentAttemptRepository attemptRepository;
    private final AttemptAnswerRepository answerRepository;
    private final QuestionRepository questionRepository;

    @Transactional
    public void apply(GradeTestResultMessage message) {
        if (message.getAttemptId() == null) {
            throw new IllegalArgumentException("attempt_id is required");
        }
        StudentAttempt attempt = attemptRepository.findByIdForUpdate(message.getAttemptId()).orElse(null);
        if (attempt == null) {
            log.warn("Attempt {} no longer exists; grade result is acknowledged without changes", message.getAttemptId());
            return;
        }

        attempt.setScorePct(message.getScorePct());
        attempt.setGrade(message.getGrade());
        attempt.setFinishedAt(OffsetDateTime.now());

        for (GradeItemMessage item : message.getItems() == null ? List.<GradeItemMessage>of() : message.getItems()) {
            if (item == null || item.getQuestionId() == null) {
                throw new IllegalArgumentException("question_id is required for every grade item");
            }
            answerRepository.findByAttemptIdAndQuestionId(attempt.getAttemptId(), item.getQuestionId())
                    .ifPresent(answer -> applyItem(answer, item));
        }
    }

    private void applyItem(AttemptAnswer answer, GradeItemMessage item) {
        answer.setScore(item.getScore());
        answer.setCorrect(item.getCorrect() != null
                ? item.getCorrect()
                : item.getScore() != null && item.getScore().compareTo(CORRECT_THRESHOLD) >= 0);
        answer.setCorrectAnswer(item.getCorrectAnswer() != null ? item.getCorrectAnswer() : answerKey(answer));
        answer.setFeedback(item.getFeedback());
    }

    private Map<String, Object> answerKey(AttemptAnswer answer) {
        return questionRepository.findById(answer.getQuestionId())
                .map(Question::getAnswerKey)
                .orElse(null);
    }
}
