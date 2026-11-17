package com.examassistant.tests.service;

import com.examassistant.common.DeterministicUuid;
import com.examassistant.materials.repository.MaterialChunkRepository;
import com.examassistant.ml.payload.MlQuestionData;
import com.examassistant.tests.QuestionService;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.enums.QuestionType;
import com.examassistant.tests.repository.QuestionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class QuestionsService implements QuestionService {
    private final QuestionRepository questionRepository;
    private final MaterialChunkRepository materialChunkRepository;

    /**
     * Сохранить вопросы теста, сгенерированные ML.
     *
     * id вопроса детерминированный (uuid5 от test_id и порядкового номера):
     * доставка в Redis Streams — «хотя бы один раз», повторная обработка
     * результата не должна плодить дубли вопросов.
     *
     * source_chunk_id — внешний ключ на material_chunks. Чанка может не быть
     * в БД (in-memory vector store), тогда пишем NULL, а не роняем вставку.
     */
    @Transactional
    @Override
    public void saveFromMl(UUID testId, List<MlQuestionData> questions) {
        if (questions == null || questions.isEmpty()) {
            throw new IllegalArgumentException("ML вернул тест без вопросов");
        }
        OffsetDateTime now = OffsetDateTime.now();
        List<Question> entities = new ArrayList<>(questions.size());
        for (int i = 0; i < questions.size(); i++) {
            MlQuestionData ml = questions.get(i);
            Question question = new Question();
            question.setQuestionId(DeterministicUuid.of(testId, "q:" + i));
            question.setTestId(testId);
            question.setQuestionOrder(i);
            question.setTypeQuestion(QuestionType.fromValue(ml.type()));
            question.setTextQuestion(ml.text());
            question.setOptions(ml.options() == null ? List.of() : new ArrayList<>(ml.options()));
            question.setAnswerKey(ml.answerKey() == null ? Map.of() : new LinkedHashMap<>(ml.answerKey()));
            question.setKeyPoints(ml.keyPoints() == null ? List.of() : new ArrayList<>(ml.keyPoints()));
            question.setSourceChunkId(resolveChunkId(ml.sourceChunkId()));
            question.setCreatedAt(now);
            entities.add(question);
        }
        questionRepository.saveAll(entities);
    }

    private UUID resolveChunkId(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        UUID chunkId;
        try {
            chunkId = UUID.fromString(raw);
        } catch (IllegalArgumentException e) {
            return null;
        }
        return materialChunkRepository.existsById(chunkId) ? chunkId : null;
    }
}
