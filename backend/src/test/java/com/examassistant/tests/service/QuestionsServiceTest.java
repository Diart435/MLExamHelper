package com.examassistant.tests.service;

import com.examassistant.support.TestFixtures;
import com.examassistant.tests.DTO.QuestionResponse;
import com.examassistant.tests.QuestionDTO;
import com.examassistant.tests.TestService;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.enums.QuestionType;
import com.examassistant.tests.repository.QuestionRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.OffsetDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class QuestionsServiceTest {

    @Mock
    private QuestionRepository questionRepository;
    @Mock
    private TestService testService;

    @InjectMocks
    private QuestionsService questionsService;

    @Test
    void create_mapsAllFieldsAndSaves() {
        QuestionDTO dto = TestFixtures.questionDto();
        OffsetDateTime before = OffsetDateTime.now().minusSeconds(1);

        questionsService.create(dto);

        ArgumentCaptor<Question> captor = ArgumentCaptor.forClass(Question.class);
        verify(questionRepository).save(captor.capture());
        Question question = captor.getValue();

        assertThat(question.getTestId()).isEqualTo(TestFixtures.TEST_ID);
        assertThat(question.getTypeQuestion()).isEqualTo(QuestionType.SINGLE_CHOICE);
        assertThat(question.getTextQuestion()).isEqualTo("What is 2+2?");
        assertThat(question.getOptions()).containsExactly("3", "4");
        // key_points — плоский список строк (контракт v4.1).
        assertThat(question.getKeyPoints()).containsExactly("4");
        assertThat(question.getSourceChunkId()).isEqualTo(TestFixtures.SOURCE_CHUNK_ID);
        assertThat(question.getCreatedAt()).isAfter(before);
    }

    @Test
    void create_optionalFieldsNull_savesQuestionWithoutThem() {
        QuestionDTO dto = new QuestionDTO(
                TestFixtures.TEST_ID,
                QuestionType.OPEN_ANSWER,
                "Explain the solution",
                null,
                null,
                null
        );

        questionsService.create(dto);

        ArgumentCaptor<Question> captor = ArgumentCaptor.forClass(Question.class);
        verify(questionRepository).save(captor.capture());
        Question question = captor.getValue();

        assertThat(question.getTypeQuestion()).isEqualTo(QuestionType.OPEN_ANSWER);
        assertThat(question.getTextQuestion()).isEqualTo("Explain the solution");
        assertThat(question.getOptions()).isNull();
        assertThat(question.getKeyPoints()).isNull();
        assertThat(question.getSourceChunkId()).isNull();
        assertThat(question.getCreatedAt()).isNotNull();
    }

    @Test
    void getByTestId_mapsAllFieldsAndChecksAccess() {
        when(questionRepository.findByTestIdOrderByQuestionOrderAsc(TestFixtures.TEST_ID))
                .thenReturn(List.of(TestFixtures.question()));

        List<QuestionResponse> result =
                questionsService.getByTestId(TestFixtures.TEST_ID, TestFixtures.USER_ID);

        assertThat(result).hasSize(1);
        QuestionResponse response = result.get(0);
        assertThat(response.questionId()).isEqualTo(TestFixtures.QUESTION_ID);
        assertThat(response.questionOrder()).isEqualTo(1);
        // type — строковое значение enum QuestionType.
        assertThat(response.type()).isEqualTo(QuestionType.SINGLE_CHOICE.getValue());
        assertThat(response.text()).isEqualTo("What is 2+2?");
        assertThat(response.options()).containsExactly("3", "4");

        // Права на тест проверяются тем же механизмом, что и в TestsService.getById.
        verify(testService).getById(TestFixtures.TEST_ID, TestFixtures.USER_ID);
    }

    @Test
    void getByTestId_keepsOrderAndCountOfQuestions() {
        Question first = TestFixtures.question();
        Question second = TestFixtures.question();
        second.setQuestionId(TestFixtures.OTHER_MATERIAL_ID);
        second.setQuestionOrder(2);
        second.setTypeQuestion(QuestionType.MULTI_CHOICE);
        second.setTextQuestion("Select all correct answers");
        second.setOptions(List.of("a", "b", "c"));
        Question third = TestFixtures.question();
        third.setQuestionId(TestFixtures.OTHER_USER_ID);
        third.setQuestionOrder(3);
        third.setTypeQuestion(QuestionType.OPEN_ANSWER);
        third.setTextQuestion("Explain the solution");
        third.setOptions(null);

        when(questionRepository.findByTestIdOrderByQuestionOrderAsc(TestFixtures.TEST_ID))
                .thenReturn(List.of(first, second, third));

        List<QuestionResponse> result =
                questionsService.getByTestId(TestFixtures.TEST_ID, TestFixtures.USER_ID);

        assertThat(result).hasSize(3);
        assertThat(result)
                .extracting(QuestionResponse::questionOrder)
                .containsExactly(1, 2, 3);
        assertThat(result)
                .extracting(QuestionResponse::type)
                .containsExactly("single_choice", "multi_choice", "open_answer");
        // options может быть null — отдаём как есть.
        assertThat(result.get(2).options()).isNull();
    }

    @Test
    void getByTestId_noQuestions_returnsEmptyList() {
        when(questionRepository.findByTestIdOrderByQuestionOrderAsc(TestFixtures.TEST_ID))
                .thenReturn(List.of());

        List<QuestionResponse> result =
                questionsService.getByTestId(TestFixtures.TEST_ID, TestFixtures.USER_ID);

        assertThat(result).isEmpty();
        verify(testService).getById(TestFixtures.TEST_ID, TestFixtures.USER_ID);
    }
}
