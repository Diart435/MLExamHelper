package com.examassistant.tests;

import com.examassistant.ml.payload.MlQuestionData;

import java.util.List;
import java.util.UUID;

public interface QuestionService {
    void saveFromMl(UUID testId, List<MlQuestionData> questions);
}
