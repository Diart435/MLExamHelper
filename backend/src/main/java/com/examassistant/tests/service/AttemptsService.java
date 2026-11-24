package com.examassistant.tests.service;

import com.examassistant.common.exception.AttemptNotFoundException;
import com.examassistant.common.exception.TestNotReadyException;
import com.examassistant.common.util.UuidV5;
import com.examassistant.messaging.GradeTestRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.messaging.StudentAnswerPayload;
import com.examassistant.tests.DTO.AttemptAnswerResponse;
import com.examassistant.tests.DTO.AttemptResponse;
import com.examassistant.tests.DTO.SubmitAttemptRequest;
import com.examassistant.tests.DTO.SubmitAttemptResponse;
import com.examassistant.tests.TestService;
import com.examassistant.tests.entity.AttemptAnswer;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.entity.StudentAttempt;
import com.examassistant.tests.entity.Test;
import com.examassistant.tests.enums.TestStatus;
import com.examassistant.tests.repository.AttemptAnswerRepository;
import com.examassistant.tests.repository.QuestionRepository;
import com.examassistant.tests.repository.StudentAttemptRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class AttemptsService {
    private final TestService testService;
    private final QuestionRepository questionRepository;
    private final StudentAttemptRepository attemptRepository;
    private final AttemptAnswerRepository answerRepository;
    private final Producer producer;

    @Transactional
    public SubmitAttemptResponse submit(UUID testId, SubmitAttemptRequest request, UUID userId) {
        Test test = testService.getById(testId, userId);
        if (test.getStatusTest() != TestStatus.CREATED) {
            throw new TestNotReadyException(testId);
        }

        Map<UUID, Question> questions = questionRepository.findByTestIdOrderByQuestionOrderAsc(testId).stream()
                .collect(Collectors.toMap(Question::getQuestionId, Function.identity()));
        List<SubmitAttemptRequest.Answer> answers = request.getAnswers() == null ? List.of() : request.getAnswers();
        validateAnswers(answers, questions);

        UUID attemptId = UUID.randomUUID();
        OffsetDateTime now = OffsetDateTime.now();
        attemptRepository.save(StudentAttempt.builder()
                .attemptId(attemptId)
                .testId(testId)
                .userId(userId)
                .startedAt(now)
                .build());

        List<AttemptAnswer> answerRows = answers.stream()
                .map(answer -> AttemptAnswer.builder()
                        .answerId(UuidV5.create(attemptId, answer.getQuestionId().toString()))
                        .attemptId(attemptId)
                        .questionId(answer.getQuestionId())
                        .studentAnswer(answer.getStudentAnswer().toMap())
                        .createdAt(now)
                        .build())
                .toList();
        answerRepository.saveAll(answerRows);

        producer.publishGradeTest(new GradeTestRedisRequest(
                UUID.randomUUID(),
                attemptId,
                testId,
                answers.stream()
                        .map(answer -> new GradeTestRedisRequest.Answer(answer.getQuestionId(), answer.getStudentAnswer()))
                        .toList()
        ));
        return new SubmitAttemptResponse(attemptId);
    }

    @Transactional(readOnly = true)
    public AttemptResponse get(UUID attemptId, UUID userId) {
        StudentAttempt attempt = attemptRepository.findById(attemptId)
                .filter(item -> item.getUserId().equals(userId))
                .orElseThrow(() -> new AttemptNotFoundException(attemptId));
        List<AttemptAnswerResponse> answers = answerRepository.findByAttemptIdOrderByCreatedAtAsc(attemptId).stream()
                .map(answer -> new AttemptAnswerResponse(
                        answer.getAnswerId(),
                        answer.getQuestionId(),
                        answer.getStudentAnswer(),
                        answer.getCorrect(),
                        answer.getCorrectAnswer(),
                        answer.getScore(),
                        answer.getFeedback()
                ))
                .toList();
        return new AttemptResponse(
                attempt.getAttemptId(),
                attempt.getTestId(),
                attempt.getFinishedAt() == null ? "processing" : "finished",
                attempt.getStartedAt(),
                attempt.getFinishedAt(),
                attempt.getScorePct(),
                attempt.getGrade(),
                answers
        );
    }

    private void validateAnswers(List<SubmitAttemptRequest.Answer> answers, Map<UUID, Question> questions) {
        Set<UUID> answeredQuestions = new HashSet<>();
        for (SubmitAttemptRequest.Answer answer : answers) {
            if (answer == null || answer.getQuestionId() == null || answer.getStudentAnswer() == null) {
                throw new IllegalArgumentException("Each answer requires question_id and student_answer");
            }
            Question question = questions.get(answer.getQuestionId());
            if (question == null) {
                throw new IllegalArgumentException("Question does not belong to the test: " + answer.getQuestionId());
            }
            if (!answeredQuestions.add(answer.getQuestionId())) {
                throw new IllegalArgumentException("Question answered more than once: " + answer.getQuestionId());
            }
            validateAnswerShape(question, answer.getStudentAnswer());
        }
    }

    private void validateAnswerShape(Question question, StudentAnswerPayload answer) {
        answer.toMap();
        switch (question.getTypeQuestion()) {
            case SINGLE_CHOICE -> {
                if (answer.getIndex() == null) {
                    throw new IllegalArgumentException("single_choice answer requires index");
                }
                validateIndex(answer.getIndex(), question);
            }
            case MULTI_CHOICE -> {
                if (answer.getIndexes() == null) {
                    throw new IllegalArgumentException("multi_choice answer requires indexes");
                }
                if (answer.getIndexes().stream().anyMatch(index -> index == null)) {
                    throw new IllegalArgumentException("indexes must not contain null");
                }
                if (answer.getIndexes().size() != new HashSet<>(answer.getIndexes()).size()) {
                    throw new IllegalArgumentException("indexes must not contain duplicates");
                }
                answer.getIndexes().forEach(index -> validateIndex(index, question));
            }
            case OPEN_ANSWER -> {
                if (answer.getText() == null) {
                    throw new IllegalArgumentException("open_answer answer requires text");
                }
            }
        }
    }

    private void validateIndex(Integer index, Question question) {
        int optionCount = question.getOptions() == null ? 0 : question.getOptions().size();
        if (index < 0 || index >= optionCount) {
            throw new IllegalArgumentException("Answer index is outside the options range");
        }
    }
}
