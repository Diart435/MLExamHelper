package com.examassistant.tests.service;

import com.examassistant.tests.QuestionDTO;
import com.examassistant.tests.QuestionService;
import com.examassistant.tests.entity.Question;
import com.examassistant.tests.repository.QuestionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;

@Service
@RequiredArgsConstructor
public class QuestionsService implements QuestionService {
    private final QuestionRepository questionRepository;

    @Transactional
    @Override
    public void create(QuestionDTO questionDTO){
        Question question = new Question();
        question.setTestId(questionDTO.getTestId());
        question.setTextQuestion(questionDTO.getTextQuestion());
        question.setTypeQuestion(questionDTO.getTypeQuestion());
        question.setOptions(questionDTO.getOptions());
        question.setAnswerKey(questionDTO.getAnswerKey());
        question.setKeyPoints(questionDTO.getKeyPoints());
        question.setSourceChunkId(questionDTO.getSourceChunkId());
        question.setCreatedAt(OffsetDateTime.now());
        questionRepository.save(question);
    }
}
