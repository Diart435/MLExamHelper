package com.examassistant.tests.service;

import com.examassistant.common.exception.AttemptForbiddenException;
import com.examassistant.common.exception.AttemptNotFoundException;
import com.examassistant.common.exception.CourseForbiddenException;
import com.examassistant.common.exception.TestNotFoundException;
import com.examassistant.courses.CourseService;
import com.examassistant.messaging.GradeAttemptRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.ml.payload.MlGradeAttemptResult;
import com.examassistant.ml.payload.MlGradedItem;
import com.examassistant.tests.AttemptService;
import com.examassistant.tests.DTO.AttemptResponse;
import com.examassistant.tests.DTO.SubmitAttemptRequest;
import com.examassistant.tests.entity.AttemptAnswer;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.entity.StudentAttempt;
import com.examassistant.tests.entity.Test;
import com.examassistant.tests.enums.TestStatus;
import com.examassistant.tests.repository.AttemptAnswerRepository;
import com.examassistant.tests.repository.QuestionRepository;
import com.examassistant.tests.repository.StudentAttemptRepository;
import com.examassistant.tests.repository.TestRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Попытки прохождения теста.
 *
 * Сдача: backend сохраняет попытку и ответы, публикует задачу проверки в ML и
 * отвечает 202 — проверка асинхронная. Результат приходит в ml-results:grade_attempt
 * и дописывается в ту же попытку (applyGrade).
 *
 * is_correct и correct_answer в БД не хранятся (в схеме заказчика таких
 * колонок нет): первый выводится из score с порогом 0.5, второй — из
 * answer_key вопроса.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AttemptsService implements AttemptService {

    private static final BigDecimal CORRECT_THRESHOLD = new BigDecimal("0.5");

    private final StudentAttemptRepository attemptRepository;
    private final AttemptAnswerRepository answerRepository;
    private final QuestionRepository questionRepository;
    private final TestRepository testRepository;
    private final CourseService courseService;
    private final Producer redisProducer;

    @Transactional
    @Override
    public AttemptResponse submit(UUID testId, SubmitAttemptRequest request, UUID userId) {
        Test test = testRepository.findById(testId)
                .orElseThrow(() -> new TestNotFoundException(testId.toString()));
        if (test.getStatusTest() != TestStatus.READY) {
            throw new IllegalArgumentException("Test is not ready to be taken");
        }

        Map<UUID, Question> questions = new LinkedHashMap<>();
        for (Question question : questionRepository.findByTestIdOrderByQuestionOrder(testId)) {
            questions.put(question.getQuestionId(), question);
        }

        UUID attemptId = UUID.randomUUID();
        OffsetDateTime now = OffsetDateTime.now();
        StudentAttempt attempt = attemptRepository.save(StudentAttempt.builder()
                .attemptId(attemptId)
                .testId(testId)
                .userId(userId)
                .startedAt(now)
                .build());

        List<AttemptAnswer> answers = new ArrayList<>();
        for (SubmitAttemptRequest.Answer answer : request.getAnswers()) {
            if (!questions.containsKey(answer.getQuestionId())) {
                throw new IllegalArgumentException(
                        "Answer references question " + answer.getQuestionId() + " from another test");
            }
            answers.add(AttemptAnswer.builder()
                    .answerId(UUID.randomUUID())
                    .attemptId(attemptId)
                    .questionId(answer.getQuestionId())
                    .studentAnswer(new LinkedHashMap<>(answer.getStudentAnswer()))
                    .createdAt(now)
                    .build());
        }
        answerRepository.saveAll(answers);

        redisProducer.publishGradeAttempt(new GradeAttemptRedisRequest(
                UUID.randomUUID(),
                attemptId,
                testId,
                userId,
                answers.stream()
                        .map(answer -> Map.<String, Object>of(
                                "question_id", answer.getQuestionId().toString(),
                                "student_answer", answer.getStudentAnswer()))
                        .toList()));

        return buildResponse(attempt, questions, answers);
    }

    @Transactional(readOnly = true)
    @Override
    public AttemptResponse getById(UUID attemptId, UUID userId) {
        StudentAttempt attempt = attemptRepository.findById(attemptId)
                .orElseThrow(() -> new AttemptNotFoundException(attemptId.toString()));

        if (!attempt.getUserId().equals(userId) && !isCourseOwner(attempt.getTestId(), userId)) {
            throw new AttemptForbiddenException("This attempt is not yours");
        }

        List<AttemptAnswer> answers = answerRepository.findByAttemptId(attemptId);
        Map<UUID, Question> questions = new LinkedHashMap<>();
        for (Question question : questionRepository.findByTestIdOrderByQuestionOrder(attempt.getTestId())) {
            questions.put(question.getQuestionId(), question);
        }
        return buildResponse(attempt, questions, answers);
    }

    /**
     * Результат проверки от ML: дробные баллы и фидбэк по вопросам плюс итог.
     *
     * При status="error" попытка остаётся непроверенной — student_attempts не
     * меняется, ошибка попадает в лог.
     */
    @Transactional
    @Override
    public void applyGrade(MlGradeAttemptResult result) {
        if (result.attemptId() == null) {
            log.warn("ML вернул результат проверки без attempt_id: {}", result);
            return;
        }
        UUID attemptId = UUID.fromString(result.attemptId());
        StudentAttempt attempt = attemptRepository.findById(attemptId).orElse(null);
        if (attempt == null) {
            log.warn("ML вернул результат для несуществующей попытки {}", attemptId);
            return;
        }
        if (!result.isOk()) {
            log.error("ML не смог проверить попытку {}: {}", attemptId, result.error());
            return;
        }

        for (MlGradedItem item : result.items() == null ? List.<MlGradedItem>of() : result.items()) {
            if (item.questionId() == null) {
                continue;
            }
            UUID questionId = UUID.fromString(item.questionId());
            answerRepository.findByAttemptIdAndQuestionId(attemptId, questionId).ifPresent(answer -> {
                answer.setScore(item.score() == null ? null : score(item.score()));
                answer.setFeedback(item.feedback());
            });
        }

        attempt.setFinishedAt(OffsetDateTime.now());
        attempt.setScorePct(result.scorePct() == null ? null : score(result.scorePct()));
        attempt.setGrade(result.grade());
    }

    private boolean isCourseOwner(UUID testId, UUID userId) {
        Test test = testRepository.findById(testId).orElse(null);
        if (test == null) {
            return false;
        }
        try {
            courseService.getDTOById(test.getCourseId(), userId);
            return true;
        } catch (CourseForbiddenException e) {
            return false;
        }
    }

    private AttemptResponse buildResponse(StudentAttempt attempt,
                                          Map<UUID, Question> questions,
                                          List<AttemptAnswer> answers) {
        List<AttemptResponse.Item> items = new ArrayList<>();
        for (AttemptAnswer answer : answers) {
            Question question = questions.get(answer.getQuestionId());
            items.add(new AttemptResponse.Item(
                    answer.getQuestionId(),
                    question == null ? null : question.getTypeQuestion().getValue(),
                    question == null ? null : question.getTextQuestion(),
                    answer.getStudentAnswer(),
                    isCorrect(answer.getScore()),
                    answer.getScore(),
                    answer.getFeedback(),
                    question == null ? null : correctAnswer(question)));
        }

        return new AttemptResponse(
                attempt.getAttemptId(),
                attempt.getTestId(),
                attempt.getUserId(),
                attempt.getFinishedAt() == null ? "processing" : "graded",
                attempt.getStartedAt(),
                attempt.getFinishedAt(),
                attempt.getScorePct(),
                attempt.getGrade(),
                items);
    }

    private Boolean isCorrect(BigDecimal score) {
        if (score == null) {
            return null;
        }
        return score.compareTo(CORRECT_THRESHOLD) >= 0;
    }

    /**
     * Текст правильного ответа из answer_key вопроса: single_choice — вариант
     * под correct_index, multi_choice — варианты под correct_indexes,
     * open_answer — reference_answer.
     */
    private String correctAnswer(Question question) {
        Map<String, Object> answerKey = question.getAnswerKey();
        if (answerKey == null || answerKey.isEmpty()) {
            return null;
        }
        List<String> options = question.getOptions();

        Integer correctIndex = asInt(answerKey.get("correct_index"));
        if (correctIndex != null) {
            return optionAt(options, correctIndex);
        }

        if (answerKey.get("correct_indexes") instanceof List<?> indexes) {
            List<String> texts = new ArrayList<>();
            for (Object index : indexes) {
                Integer position = asInt(index);
                String text = position == null ? null : optionAt(options, position);
                if (text != null) {
                    texts.add(text);
                }
            }
            return texts.isEmpty() ? null : String.join(", ", texts);
        }

        Object reference = answerKey.get("reference_answer");
        return reference == null ? null : reference.toString();
    }

    private String optionAt(List<String> options, int index) {
        if (options == null || index < 0 || index >= options.size()) {
            return null;
        }
        return options.get(index);
    }

    private Integer asInt(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value instanceof String text) {
            try {
                return Integer.valueOf(text.trim());
            } catch (NumberFormatException e) {
                return null;
            }
        }
        return null;
    }

    private BigDecimal score(double value) {
        return BigDecimal.valueOf(value).setScale(2, RoundingMode.HALF_UP);
    }
}
