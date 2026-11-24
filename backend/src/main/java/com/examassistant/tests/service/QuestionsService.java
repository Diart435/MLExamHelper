package com.examassistant.tests.service;

import com.examassistant.tests.DTO.QuestionResponse;
import com.examassistant.tests.QuestionDTO;
import com.examassistant.tests.QuestionService;
import com.examassistant.tests.TestService;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.repository.QuestionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class QuestionsService implements QuestionService {
    private final QuestionRepository questionRepository;
    private final TestService testService;

    @Transactional
    @Override
    public void create(QuestionDTO questionDTO){
        Question question = new Question();
        question.setQuestionId(UUID.randomUUID());
        question.setTestId(questionDTO.getTestId());
        question.setTextQuestion(questionDTO.getTextQuestion());
        question.setTypeQuestion(questionDTO.getTypeQuestion());
        question.setOptions(questionDTO.getOptions());
        question.setKeyPoints(questionDTO.getKeyPoints());
        question.setSourceChunkId(questionDTO.getSourceChunkId());
        question.setCreatedAt(OffsetDateTime.now());
        questionRepository.save(question);
    }

    @Transactional(readOnly = true)
    @Override
    public List<QuestionResponse> getByTestId(UUID testId, UUID userId) {
        testService.getById(testId, userId);

        return questionRepository.findByTestIdOrderByQuestionOrderAsc(testId).stream()
                .map(question -> new QuestionResponse(
                        question.getQuestionId(),
                        question.getQuestionOrder(),
                        question.getTypeQuestion().getValue(),
                        question.getTextQuestion(),
                        question.getOptions()
                ))
                .toList();
    }
}
