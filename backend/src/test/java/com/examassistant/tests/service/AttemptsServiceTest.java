package com.examassistant.tests.service;

import com.examassistant.common.exception.TestNotFoundException;
import com.examassistant.courses.CourseService;
import com.examassistant.messaging.GradeAttemptRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.ml.payload.MlGradeAttemptResult;
import com.examassistant.ml.payload.MlGradedItem;
import com.examassistant.support.TestFixtures;
import com.examassistant.tests.DTO.AttemptResponse;
import com.examassistant.tests.DTO.SubmitAttemptRequest;
import com.examassistant.tests.entity.AttemptAnswer;
import com.examassistant.tests.entity.StudentAttempt;
import com.examassistant.tests.repository.AttemptAnswerRepository;
import com.examassistant.tests.repository.QuestionRepository;
import com.examassistant.tests.repository.StudentAttemptRepository;
import com.examassistant.tests.repository.TestRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AttemptsServiceTest {

    @Mock
    private StudentAttemptRepository attemptRepository;
    @Mock
    private AttemptAnswerRepository answerRepository;
    @Mock
    private QuestionRepository questionRepository;
    @Mock
    private TestRepository testRepository;
    @Mock
    private CourseService courseService;
    @Mock
    private Producer redisProducer;

    @InjectMocks
    private AttemptsService attemptsService;

    @Test
    void submit_savesAttemptAndPublishesGradeTask() {
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.of(TestFixtures.readyTest()));
        when(questionRepository.findByTestIdOrderByQuestionOrder(TestFixtures.TEST_ID))
                .thenReturn(List.of(TestFixtures.question()));
        when(attemptRepository.save(any(StudentAttempt.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        AttemptResponse response = attemptsService.submit(
                TestFixtures.TEST_ID, submitRequest(), TestFixtures.USER_ID);

        assertThat(response.status()).isEqualTo("processing");
        assertThat(response.attemptId()).isNotNull();
        assertThat(response.items()).hasSize(1);
        assertThat(response.items().get(0).studentAnswer()).containsEntry("index", 1);
        assertThat(response.items().get(0).isCorrect()).isNull();
        assertThat(response.items().get(0).correctAnswer()).isEqualTo("4");

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<AttemptAnswer>> captor = ArgumentCaptor.forClass(List.class);
        verify(answerRepository).saveAll(captor.capture());
        assertThat(captor.getValue().get(0).getQuestionId()).isEqualTo(TestFixtures.QUESTION_ID);
        assertThat(captor.getValue().get(0).getScore()).isNull();

        ArgumentCaptor<GradeAttemptRedisRequest> published =
                ArgumentCaptor.forClass(GradeAttemptRedisRequest.class);
        verify(redisProducer).publishGradeAttempt(published.capture());
        assertThat(published.getValue().getTestId()).isEqualTo(TestFixtures.TEST_ID);
        assertThat(published.getValue().getUserId()).isEqualTo(TestFixtures.USER_ID);
        assertThat(published.getValue().getAnswers()).hasSize(1);
        assertThat(published.getValue().getAnswers().get(0))
                .containsEntry("question_id", TestFixtures.QUESTION_ID.toString());
    }

    @Test
    void submit_testNotReady_throws() {
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.of(TestFixtures.test()));

        assertThatThrownBy(() -> attemptsService.submit(
                TestFixtures.TEST_ID, submitRequest(), TestFixtures.USER_ID))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("not ready");

        verifyNoInteractions(redisProducer);
    }

    @Test
    void submit_testNotFound_throws() {
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> attemptsService.submit(
                TestFixtures.TEST_ID, submitRequest(), TestFixtures.USER_ID))
                .isInstanceOf(TestNotFoundException.class);
    }

    @Test
    void submit_answerFromAnotherTest_throws() {
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.of(TestFixtures.readyTest()));
        when(questionRepository.findByTestIdOrderByQuestionOrder(TestFixtures.TEST_ID)).thenReturn(List.of());
        SubmitAttemptRequest request = SubmitAttemptRequest.builder()
                .answers(List.of(SubmitAttemptRequest.Answer.builder()
                        .questionId(TestFixtures.QUESTION_ID)
                        .studentAnswer(Map.of("index", 1))
                        .build()))
                .build();

        assertThatThrownBy(() -> attemptsService.submit(TestFixtures.TEST_ID, request, TestFixtures.USER_ID))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("another test");

        verifyNoInteractions(redisProducer);
    }

    @Test
    void getById_ownAttempt_derivesIsCorrectAndCorrectAnswer() {
        StudentAttempt attempt = StudentAttempt.builder()
                .attemptId(TestFixtures.ATTEMPT_ID)
                .testId(TestFixtures.TEST_ID)
                .userId(TestFixtures.USER_ID)
                .startedAt(TestFixtures.CREATED_AT)
                .finishedAt(TestFixtures.CREATED_AT.plusHours(1))
                .build();
        when(attemptRepository.findById(TestFixtures.ATTEMPT_ID)).thenReturn(Optional.of(attempt));
        when(answerRepository.findByAttemptId(TestFixtures.ATTEMPT_ID)).thenReturn(List.of(answer()));
        when(questionRepository.findByTestIdOrderByQuestionOrder(TestFixtures.TEST_ID))
                .thenReturn(List.of(TestFixtures.question()));

        AttemptResponse response = attemptsService.getById(TestFixtures.ATTEMPT_ID, TestFixtures.USER_ID);

        assertThat(response.status()).isEqualTo("graded");
        assertThat(response.items().get(0).isCorrect()).isTrue();
        assertThat(response.items().get(0).score()).isEqualByComparingTo(new BigDecimal("1.00"));
        assertThat(response.items().get(0).correctAnswer()).isEqualTo("4");
        assertThat(response.items().get(0).type()).isEqualTo("single_choice");
    }

    @Test
    void applyGrade_writesScoresAndFinishesAttempt() {
        StudentAttempt attempt = StudentAttempt.builder()
                .attemptId(TestFixtures.ATTEMPT_ID)
                .testId(TestFixtures.TEST_ID)
                .userId(TestFixtures.USER_ID)
                .startedAt(TestFixtures.CREATED_AT)
                .build();
        AttemptAnswer answer = answer();
        when(attemptRepository.findById(TestFixtures.ATTEMPT_ID)).thenReturn(Optional.of(attempt));
        when(answerRepository.findByAttemptIdAndQuestionId(TestFixtures.ATTEMPT_ID, TestFixtures.QUESTION_ID))
                .thenReturn(Optional.of(answer));
        MlGradeAttemptResult result = new MlGradeAttemptResult(
                TestFixtures.TASK_ID.toString(), "ok", TestFixtures.ATTEMPT_ID.toString(),
                TestFixtures.TEST_ID.toString(), 50.0, 3,
                List.of(new MlGradedItem(TestFixtures.QUESTION_ID.toString(), true, 1.0, "Верно", "4", "4")),
                null);

        attemptsService.applyGrade(result);

        assertThat(answer.getScore()).isEqualByComparingTo(new BigDecimal("1.00"));
        assertThat(answer.getFeedback()).isEqualTo("Верно");
        assertThat(attempt.getScorePct()).isEqualByComparingTo(new BigDecimal("50.00"));
        assertThat(attempt.getGrade()).isEqualTo(3);
        assertThat(attempt.getFinishedAt()).isNotNull();
    }

    @Test
    void applyGrade_mlError_leavesAttemptUnchanged() {
        StudentAttempt attempt = StudentAttempt.builder()
                .attemptId(TestFixtures.ATTEMPT_ID)
                .testId(TestFixtures.TEST_ID)
                .userId(TestFixtures.USER_ID)
                .startedAt(TestFixtures.CREATED_AT)
                .build();
        when(attemptRepository.findById(TestFixtures.ATTEMPT_ID)).thenReturn(Optional.of(attempt));
        MlGradeAttemptResult result = new MlGradeAttemptResult(
                TestFixtures.TASK_ID.toString(), "error", TestFixtures.ATTEMPT_ID.toString(),
                TestFixtures.TEST_ID.toString(), null, null, List.of(), "llm unavailable");

        attemptsService.applyGrade(result);

        assertThat(attempt.getFinishedAt()).isNull();
        assertThat(attempt.getScorePct()).isNull();
    }

    private SubmitAttemptRequest submitRequest() {
        return SubmitAttemptRequest.builder()
                .answers(List.of(SubmitAttemptRequest.Answer.builder()
                        .questionId(TestFixtures.QUESTION_ID)
                        .studentAnswer(Map.of("index", 1))
                        .build()))
                .build();
    }

    private AttemptAnswer answer() {
        return AttemptAnswer.builder()
                .answerId(TestFixtures.QUESTION_ID)
                .attemptId(TestFixtures.ATTEMPT_ID)
                .questionId(TestFixtures.QUESTION_ID)
                .studentAnswer(Map.of("index", 1))
                .score(new BigDecimal("1.00"))
                .feedback("Верно")
                .createdAt(TestFixtures.CREATED_AT)
                .build();
    }
}
