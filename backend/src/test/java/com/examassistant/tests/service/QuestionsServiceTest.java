package com.examassistant.tests.service;

import com.examassistant.support.TestFixtures;
import com.examassistant.tests.QuestionDTO;
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
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class QuestionsServiceTest {

    @Mock
    private QuestionRepository questionRepository;

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
        assertThat(question.getKeyPoints()).isEqualTo(Map.of("correct", List.of("4")));
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
}
