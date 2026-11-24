package com.examassistant.jobs.service;

import com.examassistant.jobs.DTO.GradeItemMessage;
import com.examassistant.jobs.DTO.GradeTestResultMessage;
import com.examassistant.support.TestFixtures;
import com.examassistant.tests.entity.AttemptAnswer;
import com.examassistant.tests.repository.AttemptAnswerRepository;
import com.examassistant.tests.repository.QuestionRepository;
import com.examassistant.tests.repository.StudentAttemptRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class GradeTestResultServiceTest {
    @Mock private StudentAttemptRepository attemptRepository;
    @Mock private AttemptAnswerRepository answerRepository;
    @Mock private QuestionRepository questionRepository;
    @InjectMocks private GradeTestResultService service;

    @Test
    void apply_derivesCorrectnessAndAnswerKeyAndIsRepeatable() {
        var attempt = TestFixtures.attempt();
        AttemptAnswer answer = AttemptAnswer.builder()
                .answerId(TestFixtures.QUESTION_ID)
                .attemptId(TestFixtures.ATTEMPT_ID)
                .questionId(TestFixtures.QUESTION_ID)
                .build();
        when(attemptRepository.findByIdForUpdate(TestFixtures.ATTEMPT_ID)).thenReturn(Optional.of(attempt));
        when(answerRepository.findByAttemptIdAndQuestionId(TestFixtures.ATTEMPT_ID, TestFixtures.QUESTION_ID))
                .thenReturn(Optional.of(answer));
        when(questionRepository.findById(TestFixtures.QUESTION_ID)).thenReturn(Optional.of(TestFixtures.question()));
        GradeTestResultMessage message = result(item(new BigDecimal("0.75")));

        service.apply(message);
        service.apply(message);

        assertThat(attempt.getScorePct()).isEqualByComparingTo("83.30");
        assertThat(attempt.getGrade()).isEqualTo(4);
        assertThat(attempt.getFinishedAt()).isNotNull();
        assertThat(answer.getCorrect()).isTrue();
        assertThat(answer.getCorrectAnswer()).isEqualTo(Map.of("correct_index", 1));
        assertThat(answer.getScore()).isEqualByComparingTo("0.75");
        verify(answerRepository, times(2))
                .findByAttemptIdAndQuestionId(TestFixtures.ATTEMPT_ID, TestFixtures.QUESTION_ID);
    }

    @Test
    void apply_usesExplicitVerdictCorrectAnswerAndFeedback() {
        var attempt = TestFixtures.attempt();
        AttemptAnswer answer = AttemptAnswer.builder()
                .attemptId(TestFixtures.ATTEMPT_ID)
                .questionId(TestFixtures.QUESTION_ID)
                .build();
        when(attemptRepository.findByIdForUpdate(TestFixtures.ATTEMPT_ID)).thenReturn(Optional.of(attempt));
        when(answerRepository.findByAttemptIdAndQuestionId(TestFixtures.ATTEMPT_ID, TestFixtures.QUESTION_ID))
                .thenReturn(Optional.of(answer));
        GradeItemMessage item = item(new BigDecimal("0.9"));
        item.setCorrect(false);
        item.setCorrectAnswer(Map.of("correct_index", 0));
        item.setFeedback("Review the topic");

        service.apply(result(item));

        assertThat(answer.getCorrect()).isFalse();
        assertThat(answer.getCorrectAnswer()).isEqualTo(Map.of("correct_index", 0));
        assertThat(answer.getFeedback()).isEqualTo("Review the topic");
        verifyNoInteractions(questionRepository);
    }

    @Test
    void apply_missingAttempt_returnsWithoutWrites() {
        when(attemptRepository.findByIdForUpdate(TestFixtures.ATTEMPT_ID)).thenReturn(Optional.empty());

        service.apply(result(item(BigDecimal.ONE)));

        verifyNoInteractions(answerRepository, questionRepository);
    }

    private GradeTestResultMessage result(GradeItemMessage item) {
        GradeTestResultMessage message = new GradeTestResultMessage();
        message.setTaskId(TestFixtures.TASK_ID);
        message.setAttemptId(TestFixtures.ATTEMPT_ID);
        message.setTestId(TestFixtures.TEST_ID);
        message.setScorePct(new BigDecimal("83.30"));
        message.setGrade(4);
        message.setItems(List.of(item));
        return message;
    }

    private GradeItemMessage item(BigDecimal score) {
        GradeItemMessage item = new GradeItemMessage();
        item.setQuestionId(TestFixtures.QUESTION_ID);
        item.setScore(score);
        return item;
    }
}
