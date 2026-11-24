package com.examassistant.tests.service;

import com.examassistant.common.exception.AttemptNotFoundException;
import com.examassistant.common.exception.TestNotReadyException;
import com.examassistant.common.util.UuidV5;
import com.examassistant.messaging.GradeTestRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.messaging.StudentAnswerPayload;
import com.examassistant.support.TestFixtures;
import com.examassistant.tests.DTO.SubmitAttemptRequest;
import com.examassistant.tests.TestService;
import com.examassistant.tests.entity.AttemptAnswer;
import com.examassistant.tests.entity.StudentAttempt;
import com.examassistant.tests.enums.TestStatus;
import com.examassistant.tests.repository.AttemptAnswerRepository;
import com.examassistant.tests.repository.QuestionRepository;
import com.examassistant.tests.repository.StudentAttemptRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AttemptsServiceTest {
    @Mock private TestService testService;
    @Mock private QuestionRepository questionRepository;
    @Mock private StudentAttemptRepository attemptRepository;
    @Mock private AttemptAnswerRepository answerRepository;
    @Mock private Producer producer;
    @InjectMocks private AttemptsService service;

    @Test
    void submit_createdTest_persistsAttemptAnswersAndPublishesGradeTask() {
        stubReadyTestAndQuestion();
        SubmitAttemptRequest request = request(StudentAnswerPayload.single(1));

        var response = service.submit(TestFixtures.TEST_ID, request, TestFixtures.USER_ID);

        assertThat(response.attemptId()).isNotNull();
        ArgumentCaptor<StudentAttempt> attemptCaptor = ArgumentCaptor.forClass(StudentAttempt.class);
        verify(attemptRepository).save(attemptCaptor.capture());
        assertThat(attemptCaptor.getValue().getAttemptId()).isEqualTo(response.attemptId());
        assertThat(attemptCaptor.getValue().getUserId()).isEqualTo(TestFixtures.USER_ID);
        assertThat(attemptCaptor.getValue().getFinishedAt()).isNull();

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<AttemptAnswer>> rowsCaptor = ArgumentCaptor.forClass(List.class);
        verify(answerRepository).saveAll(rowsCaptor.capture());
        assertThat(rowsCaptor.getValue()).singleElement().satisfies(answer -> {
            assertThat(answer.getAnswerId()).isEqualTo(UuidV5.create(
                    response.attemptId(), TestFixtures.QUESTION_ID.toString()));
            assertThat(answer.getStudentAnswer()).isEqualTo(java.util.Map.of("index", 1));
            assertThat(answer.getCorrect()).isNull();
            assertThat(answer.getCorrectAnswer()).isNull();
        });

        ArgumentCaptor<GradeTestRedisRequest> taskCaptor = ArgumentCaptor.forClass(GradeTestRedisRequest.class);
        verify(producer).publishGradeTest(taskCaptor.capture());
        assertThat(taskCaptor.getValue().getAttemptId()).isEqualTo(response.attemptId());
        assertThat(taskCaptor.getValue().getTestId()).isEqualTo(TestFixtures.TEST_ID);
        assertThat(taskCaptor.getValue().getAnswers()).hasSize(1);
    }

    @Test
    void submit_questionFromAnotherTest_isRejected() {
        stubReadyTestAndQuestion();
        SubmitAttemptRequest request = request(StudentAnswerPayload.single(1));
        request.getAnswers().get(0).setQuestionId(TestFixtures.OTHER_MATERIAL_ID);

        assertThatThrownBy(() -> service.submit(TestFixtures.TEST_ID, request, TestFixtures.USER_ID))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("does not belong");
        verifyNoInteractions(attemptRepository, answerRepository, producer);
    }

    @Test
    void submit_wrongAnswerShape_isRejected() {
        stubReadyTestAndQuestion();

        assertThatThrownBy(() -> service.submit(TestFixtures.TEST_ID,
                request(StudentAnswerPayload.open("four")), TestFixtures.USER_ID))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("single_choice");
        verifyNoInteractions(attemptRepository, answerRepository, producer);
    }

    @Test
    void submit_indexOutsideOptions_isRejected() {
        stubReadyTestAndQuestion();

        assertThatThrownBy(() -> service.submit(TestFixtures.TEST_ID,
                request(StudentAnswerPayload.single(5)), TestFixtures.USER_ID))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("outside");
    }

    @Test
    void submit_testNotReady_isRejected() {
        var test = TestFixtures.test();
        test.setStatusTest(TestStatus.CREATING);
        when(testService.getById(TestFixtures.TEST_ID, TestFixtures.USER_ID)).thenReturn(test);

        assertThatThrownBy(() -> service.submit(TestFixtures.TEST_ID,
                request(StudentAnswerPayload.single(1)), TestFixtures.USER_ID))
                .isInstanceOf(TestNotReadyException.class);
        verifyNoInteractions(questionRepository, attemptRepository, answerRepository, producer);
    }

    @Test
    void get_owner_returnsProcessingAttempt() {
        when(attemptRepository.findById(TestFixtures.ATTEMPT_ID)).thenReturn(Optional.of(TestFixtures.attempt()));
        when(answerRepository.findByAttemptIdOrderByCreatedAtAsc(TestFixtures.ATTEMPT_ID)).thenReturn(List.of());

        var response = service.get(TestFixtures.ATTEMPT_ID, TestFixtures.USER_ID);

        assertThat(response.status()).isEqualTo("processing");
        assertThat(response.attemptId()).isEqualTo(TestFixtures.ATTEMPT_ID);
    }

    @Test
    void get_finishedAttempt_returnsFinishedStatusAndGrade() {
        StudentAttempt attempt = TestFixtures.attempt();
        attempt.setFinishedAt(OffsetDateTime.now());
        attempt.setGrade(5);
        when(attemptRepository.findById(TestFixtures.ATTEMPT_ID)).thenReturn(Optional.of(attempt));
        when(answerRepository.findByAttemptIdOrderByCreatedAtAsc(TestFixtures.ATTEMPT_ID)).thenReturn(List.of());

        var response = service.get(TestFixtures.ATTEMPT_ID, TestFixtures.USER_ID);

        assertThat(response.status()).isEqualTo("finished");
        assertThat(response.grade()).isEqualTo(5);
    }

    @Test
    void get_otherUsersAttempt_returnsNotFound() {
        when(attemptRepository.findById(TestFixtures.ATTEMPT_ID)).thenReturn(Optional.of(TestFixtures.attempt()));

        assertThatThrownBy(() -> service.get(TestFixtures.ATTEMPT_ID, TestFixtures.OTHER_USER_ID))
                .isInstanceOf(AttemptNotFoundException.class);
        verifyNoInteractions(answerRepository);
    }

    private void stubReadyTestAndQuestion() {
        when(testService.getById(TestFixtures.TEST_ID, TestFixtures.USER_ID)).thenReturn(TestFixtures.test());
        when(questionRepository.findByTestIdOrderByQuestionOrderAsc(TestFixtures.TEST_ID))
                .thenReturn(List.of(TestFixtures.question()));
    }

    private SubmitAttemptRequest request(StudentAnswerPayload answer) {
        return new SubmitAttemptRequest(List.of(
                new SubmitAttemptRequest.Answer(TestFixtures.QUESTION_ID, answer)));
    }
}
