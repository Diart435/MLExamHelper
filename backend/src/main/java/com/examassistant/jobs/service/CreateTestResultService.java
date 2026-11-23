package com.examassistant.jobs.service;

import com.examassistant.common.util.UuidV5;
import com.examassistant.jobs.DTO.CreateTestResultMessage;
import com.examassistant.jobs.DTO.QuestionDataMessage;
import com.examassistant.messaging.TaskService;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.entity.Test;
import com.examassistant.tests.enums.QuestionType;
import com.examassistant.tests.enums.TestStatus;
import com.examassistant.tests.repository.QuestionRepository;
import com.examassistant.tests.repository.TestRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class CreateTestResultService {
    private final TestRepository testRepository;
    private final QuestionRepository questionRepository;
    private final TaskService taskService;
    private final JdbcTemplate jdbcTemplate;

    @Transactional
    public void apply(CreateTestResultMessage message) {
        if (message.getTestId() == null) {
            throw new InvalidResultException("test_id is required for a successful result");
        }
        Test test = testRepository.findByIdForUpdate(message.getTestId())
                .orElseThrow(() -> new InvalidResultException("Test not found: " + message.getTestId()));
        if (test.getStatusTest() != TestStatus.CREATING) {
            return;
        }

        try {
            List<Question> questions = mapQuestions(test.getTestId(), message);
            questionRepository.saveAll(questions);
            // Контракт v4.1: размер теста выбирает ML — backend пишет фактическое
            // число вопросов вместо запрошенного bucket'а.
            test.setAmountQuestions(String.valueOf(questions.size()));
            test.setStatusTest(TestStatus.CREATED);
            changeTaskStatus(message.getTaskId(), StatusTask.FINISHED);
        } catch (InvalidResultException e) {
            log.warn("Invalid create-test result for test {}: {}", test.getTestId(), e.getMessage());
            markError(test, message.getTaskId());
        }
    }

    @Transactional
    public void applyError(CreateTestResultMessage message) {
        if (message.getTestId() != null) {
            testRepository.findByIdForUpdate(message.getTestId())
                    .filter(test -> test.getStatusTest() == TestStatus.CREATING)
                    .ifPresent(test -> markError(test, message.getTaskId()));
            return;
        }
        changeTaskStatus(message.getTaskId(), StatusTask.ERROR);
    }

    private List<Question> mapQuestions(UUID testId, CreateTestResultMessage message) {
        if (message.getTest() == null || message.getTest().getQuestions() == null
                || message.getTest().getQuestions().isEmpty()) {
            throw new InvalidResultException("test.questions must not be empty");
        }

        List<QuestionDataMessage> source = message.getTest().getQuestions();
        Set<Integer> orders = new HashSet<>();
        List<Question> questions = new ArrayList<>(source.size());
        for (QuestionDataMessage item : source) {
            QuestionType type = validateQuestion(item, source.size());
            if (!orders.add(item.getId())) {
                throw new InvalidResultException("Question ids must be unique and continuous");
            }
            UUID sourceChunkId = item.getSourceChunkId();
            if (sourceChunkId != null && !chunkExists(sourceChunkId)) {
                sourceChunkId = null;
            }
            questions.add(Question.builder()
                    .questionId(UuidV5.create(testId, "q:" + item.getId()))
                    .testId(testId)
                    .typeQuestion(type)
                    .textQuestion(item.getText())
                    .options(item.getOptions() == null ? null : List.copyOf(item.getOptions()))
                    // key_points — плоский список строк: критерии для open_answer.
                    .keyPoints(item.getKeyPoints() == null ? null : List.copyOf(item.getKeyPoints()))
                    .answerKey(new LinkedHashMap<>(item.getAnswerKey()))
                    .sourceChunkId(sourceChunkId)
                    .questionOrder(item.getId())
                    .createdAt(OffsetDateTime.now())
                    .build());
        }
        for (int order = 1; order <= source.size(); order++) {
            if (!orders.contains(order)) {
                throw new InvalidResultException("Question ids must be continuous from 1 to " + source.size());
            }
        }
        return questions;
    }

    private QuestionType validateQuestion(QuestionDataMessage item, int questionCount) {
        if (item == null || item.getId() == null || item.getId() < 1 || item.getId() > questionCount) {
            throw new InvalidResultException("Question id is outside the range 1.." + questionCount);
        }
        if (item.getText() == null || item.getText().isBlank()) {
            throw new InvalidResultException("Question text must not be blank");
        }
        QuestionType type;
        try {
            type = QuestionType.fromValue(item.getType());
        } catch (RuntimeException e) {
            throw new InvalidResultException("Unknown question type: " + item.getType());
        }
        if (item.getAnswerKey() == null) {
            throw new InvalidResultException("answer_key is required");
        }

        switch (type) {
            case SINGLE_CHOICE -> validateSingleChoice(item);
            case MULTI_CHOICE -> validateMultiChoice(item);
            case OPEN_ANSWER -> {
                return type;
            }
        }
        return type;
    }

    private void validateSingleChoice(QuestionDataMessage item) {
        validateOptions(item);
        validateIndex(item.getAnswerKey().get("correct_index"), item.getOptions().size(), "correct_index");
    }

    private void validateMultiChoice(QuestionDataMessage item) {
        validateOptions(item);
        if (!(item.getAnswerKey().get("correct_indexes") instanceof List<?> indexes) || indexes.isEmpty()) {
            throw new InvalidResultException("answer_key.correct_indexes must be a non-empty array");
        }
        Set<Integer> uniqueIndexes = new HashSet<>();
        for (Object value : indexes) {
            int index = validateIndex(value, item.getOptions().size(), "correct_indexes");
            if (!uniqueIndexes.add(index)) {
                throw new InvalidResultException("answer_key.correct_indexes must not contain duplicates");
            }
        }
    }

    private void validateOptions(QuestionDataMessage item) {
        if (item.getOptions() == null || item.getOptions().size() < 2) {
            throw new InvalidResultException("Closed question must have at least two options");
        }
    }

    private int validateIndex(Object value, int optionCount, String field) {
        if (!(value instanceof Number number) || number.doubleValue() % 1 != 0) {
            throw new InvalidResultException("answer_key." + field + " must contain integer indexes");
        }
        int index = number.intValue();
        if (index < 0 || index >= optionCount) {
            throw new InvalidResultException("answer_key." + field + " is outside the options range");
        }
        return index;
    }

    private boolean chunkExists(UUID chunkId) {
        Boolean exists = jdbcTemplate.queryForObject(
                "SELECT EXISTS (SELECT 1 FROM material_chunks WHERE chunk_id = ?)",
                Boolean.class,
                chunkId
        );
        return Boolean.TRUE.equals(exists);
    }

    private void markError(Test test, UUID taskId) {
        test.setStatusTest(TestStatus.ERROR);
        changeTaskStatus(taskId, StatusTask.ERROR);
    }

    private void changeTaskStatus(UUID taskId, StatusTask status) {
        if (taskId != null) {
            taskService.changeStatus(taskId, status);
        }
    }

    private static class InvalidResultException extends RuntimeException {
        private InvalidResultException(String message) {
            super(message);
        }
    }
}
