package com.examassistant.tests;

import com.examassistant.ml.payload.MlGradeAttemptResult;
import com.examassistant.tests.DTO.AttemptResponse;
import com.examassistant.tests.DTO.SubmitAttemptRequest;

import java.util.UUID;

public interface AttemptService {
    AttemptResponse submit(UUID testId, SubmitAttemptRequest request, UUID userId);

    AttemptResponse getById(UUID attemptId, UUID userId);

    void applyGrade(MlGradeAttemptResult result);
}
