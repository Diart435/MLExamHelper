package com.examassistant.tests;

import com.examassistant.tests.DTO.QuestionResponse;

import java.util.List;
import java.util.UUID;

public interface QuestionService {
    void create(QuestionDTO questionDTO);
    List<QuestionResponse> getByTestId(UUID testId, UUID userId);
}
