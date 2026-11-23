package com.examassistant.jobs.service;

import com.examassistant.common.util.UuidV5;
import com.examassistant.jobs.DTO.CreateTestResultMessage;
import com.examassistant.jobs.DTO.QuestionDataMessage;
import com.examassistant.jobs.DTO.TestDataMessage;
import com.examassistant.messaging.TaskService;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.support.TestFixtures;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.enums.QuestionType;
import com.examassistant.tests.enums.TestStatus;
import com.examassistant.tests.repository.QuestionRepository;
import com.examassistant.tests.repository.TestRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CreateTestResultServiceTest {
    @Mock private TestRepository testRepository;
    @Mock private QuestionRepository questionRepository;
    @Mock private TaskService taskService;
    @Mock private JdbcTemplate jdbcTemplate;
    @InjectMocks private CreateTestResultService service;

    @Test
    void apply_savesDeterministicIdsOrdersAndNestedAnswerKeys() {
        var test = creatingTest();
        when(testRepository.findByIdForUpdate(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));

        service.apply(successMessage(question(1), question(2)));

        List<Question> saved = savedQuestions();
        assertThat(saved).extracting(Question::getQuestionId).containsExactly(
                UuidV5.create(TestFixtures.TEST_ID, "q:1"), UuidV5.create(TestFixtures.TEST_ID, "q:2"));
        assertThat(saved).extracting(Question::getQuestionOrder).containsExactly(1, 2);
        assertThat(saved).extracting(Question::getAnswerKey)
                .containsExactly(Map.of("correct_index", 0), Map.of("correct_index", 0));
        assertThat(test.getStatusTest()).isEqualTo(TestStatus.CREATED);
        verify(taskService).changeStatus(TestFixtures.TASK_ID, StatusTask.FINISHED);
    }

    @Test
    void apply_savesSingleMultiAndOpenQuestionForms() {
        var test = creatingTest();
        when(testRepository.findByIdForUpdate(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));
        QuestionDataMessage multi = question(2);
        multi.setType("multi_choice");
        multi.setAnswerKey(Map.of("correct_indexes", List.of(0, 1)));
        // open_answer по контракту v4.1: answer_key = эталон, key_points — отдельное поле.
        QuestionDataMessage open = question(3);
        open.setType("open_answer");
        open.setOptions(null);
        open.setAnswerKey(Map.of("reference_answer", "A transaction is a unit of work",
                "explanation", "Name the unit of work"));
        open.setKeyPoints(List.of("definition", "example"));

        service.apply(successMessage(question(1), multi, open));

        List<Question> saved = savedQuestions();
        assertThat(saved).extracting(Question::getTypeQuestion).containsExactly(
                QuestionType.SINGLE_CHOICE, QuestionType.MULTI_CHOICE, QuestionType.OPEN_ANSWER);
        assertThat(saved.get(1).getAnswerKey()).isEqualTo(Map.of("correct_indexes", List.of(0, 1)));
        assertThat(saved.get(2).getOptions()).isNull();
        assertThat(saved.get(2).getAnswerKey()).isEqualTo(Map.of(
                "reference_answer", "A transaction is a unit of work",
                "explanation", "Name the unit of work"));
        // Опорные пункты ML присылает отдельным полем key_points.
        assertThat(saved.get(2).getKeyPoints()).containsExactly("definition", "example");
    }

    @Test
    void apply_writesActualQuestionCountIntoAmountQuestions() {
        var test = creatingTest();
        when(testRepository.findByIdForUpdate(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));

        service.apply(successMessage(question(1), question(2)));

        // Размер теста выбирает ML — backend пишет фактическое число вопросов.
        assertThat(test.getAmountQuestions()).isEqualTo("2");
    }

    @Test
    void apply_repeatedResultAfterCreated_doesNotCreateDuplicates() {
        var test = TestFixtures.test();
        when(testRepository.findByIdForUpdate(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));

        service.apply(successMessage(question(1)));

        verifyNoInteractions(questionRepository, taskService, jdbcTemplate);
    }

    @Test
    void apply_invalidQuestion_marksTestAndTaskError() {
        var test = creatingTest();
        QuestionDataMessage invalid = question(2);
        when(testRepository.findByIdForUpdate(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));

        service.apply(successMessage(invalid));

        assertThat(test.getStatusTest()).isEqualTo(TestStatus.ERROR);
        verify(taskService).changeStatus(TestFixtures.TASK_ID, StatusTask.ERROR);
        verifyNoInteractions(questionRepository);
    }

    @Test
    void apply_missingNestedAnswerKey_marksTestAndTaskError() {
        var test = creatingTest();
        QuestionDataMessage invalid = question(1);
        invalid.setAnswerKey(null);
        when(testRepository.findByIdForUpdate(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));

        service.apply(successMessage(invalid));

        assertThat(test.getStatusTest()).isEqualTo(TestStatus.ERROR);
        verify(taskService).changeStatus(TestFixtures.TASK_ID, StatusTask.ERROR);
        verifyNoInteractions(questionRepository);
    }

    @Test
    void apply_unknownSourceChunk_storesNull() {
        var test = creatingTest();
        QuestionDataMessage question = question(1);
        question.setSourceChunkId(TestFixtures.SOURCE_CHUNK_ID);
        when(testRepository.findByIdForUpdate(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));
        when(jdbcTemplate.queryForObject(anyString(), eq(Boolean.class), eq(TestFixtures.SOURCE_CHUNK_ID)))
                .thenReturn(false);

        service.apply(successMessage(question));

        assertThat(savedQuestions().get(0).getSourceChunkId()).isNull();
    }

    @Test
    void applyError_withoutTestId_marksOnlyTaskError() {
        CreateTestResultMessage message = new CreateTestResultMessage();
        message.setTaskId(TestFixtures.TASK_ID);
        message.setStatus("error");
        message.setError("failed");

        service.applyError(message);

        verify(taskService).changeStatus(TestFixtures.TASK_ID, StatusTask.ERROR);
        verifyNoInteractions(testRepository, questionRepository);
    }

    private com.examassistant.tests.entity.Test creatingTest() {
        var test = TestFixtures.test();
        test.setStatusTest(TestStatus.CREATING);
        // Пока тест готовит ML, в колонке 0 — фактическое число пишется
        // по ответу ML.
        test.setAmountQuestions("0");
        return test;
    }

    private CreateTestResultMessage successMessage(QuestionDataMessage... questions) {
        CreateTestResultMessage message = new CreateTestResultMessage();
        message.setTaskId(TestFixtures.TASK_ID);
        message.setTestId(TestFixtures.TEST_ID);
        message.setStatus("ok");
        TestDataMessage data = new TestDataMessage();
        data.setTitle("Math test");
        data.setQuestions(List.of(questions));
        message.setTest(data);
        return message;
    }

    private QuestionDataMessage question(int id) {
        QuestionDataMessage question = new QuestionDataMessage();
        question.setId(id);
        question.setType("single_choice");
        question.setText("Question " + id);
        question.setOptions(List.of("A", "B"));
        question.setAnswerKey(Map.of("correct_index", 0));
        return question;
    }

    @SuppressWarnings("unchecked")
    private List<Question> savedQuestions() {
        ArgumentCaptor<List<Question>> captor = ArgumentCaptor.forClass(List.class);
        verify(questionRepository).saveAll(captor.capture());
        return captor.getValue();
    }
}
