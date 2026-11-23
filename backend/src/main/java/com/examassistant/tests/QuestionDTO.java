package com.examassistant.tests;

import com.examassistant.tests.enums.QuestionType;
import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;
import java.util.UUID;

@Data
@AllArgsConstructor
public class QuestionDTO {
    private UUID testId;

    private QuestionType typeQuestion;

    private String textQuestion;

    private List<String> options;

    // Опорные пункты вопроса — плоский список строк (контракт v4.1).
    private List<String> keyPoints;

    private UUID sourceChunkId;
}
