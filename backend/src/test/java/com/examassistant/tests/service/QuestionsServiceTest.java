package com.examassistant.tests.service;

import com.examassistant.materials.repository.MaterialChunkRepository;
import com.examassistant.support.TestFixtures;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.enums.QuestionType;
import com.examassistant.tests.repository.QuestionRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class QuestionsServiceTest {

    @Mock
    private QuestionRepository questionRepository;
    @Mock
    private MaterialChunkRepository materialChunkRepository;

    @InjectMocks
    private QuestionsService questionsService;

    @Test
    void saveFromMl_mapsAllFieldsAndSaves() {
        when(materialChunkRepository.existsById(TestFixtures.SOURCE_CHUNK_ID)).thenReturn(true);

        questionsService.saveFromMl(TestFixtures.TEST_ID, List.of(TestFixtures.mlQuestionData()));

        Question question = savedQuestions().get(0);
        assertThat(question.getTestId()).isEqualTo(TestFixtures.TEST_ID);
        assertThat(question.getTypeQuestion()).isEqualTo(QuestionType.SINGLE_CHOICE);
        assertThat(question.getTextQuestion()).isEqualTo("What is 2+2?");
        assertThat(question.getOptions()).containsExactly("3", "4");
        assertThat(question.getAnswerKey()).containsEntry("correct_index", 1);
        assertThat(question.getKeyPoints()).isEmpty();
        assertThat(question.getSourceChunkId()).isEqualTo(TestFixtures.SOURCE_CHUNK_ID);
        assertThat(question.getQuestionOrder()).isZero();
        assertThat(question.getCreatedAt()).isNotNull();
    }

    @Test
    void saveFromMl_sameTestTwice_keepsQuestionIdStable() {
        when(materialChunkRepository.existsById(any())).thenReturn(true);

        questionsService.saveFromMl(TestFixtures.TEST_ID, List.of(TestFixtures.mlQuestionData()));
        questionsService.saveFromMl(TestFixtures.TEST_ID, List.of(TestFixtures.mlQuestionData()));

        ArgumentCaptor<List<Question>> captor = ArgumentCaptor.forClass(List.class);
        verify(questionRepository, times(2)).saveAll(captor.capture());

        assertThat(captor.getAllValues().get(0).get(0).getQuestionId())
                .isEqualTo(captor.getAllValues().get(1).get(0).getQuestionId());
    }

    @Test
    void saveFromMl_unknownChunk_savesNullChunkId() {
        when(materialChunkRepository.existsById(TestFixtures.SOURCE_CHUNK_ID)).thenReturn(false);

        questionsService.saveFromMl(TestFixtures.TEST_ID, List.of(TestFixtures.mlQuestionData()));

        assertThat(savedQuestions().get(0).getSourceChunkId()).isNull();
    }

    @Test
    void saveFromMl_noQuestions_throwsAndDoesNotSave() {
        assertThatThrownBy(() -> questionsService.saveFromMl(TestFixtures.TEST_ID, List.of()))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(questionRepository);
    }

    @SuppressWarnings("unchecked")
    private List<Question> savedQuestions() {
        ArgumentCaptor<List<Question>> captor = ArgumentCaptor.forClass(List.class);
        verify(questionRepository).saveAll(captor.capture());
        return captor.getValue();
    }
}
