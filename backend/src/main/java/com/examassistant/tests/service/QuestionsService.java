package com.examassistant.tests.service;

import com.examassistant.tests.repository.QuestionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class QuestionsService {
    private final QuestionRepository questionRepository;

    @Transactional
    public void create(){
        //TODO: сделать сохранение вопросов
    }
}
