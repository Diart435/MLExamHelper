package com.examassistant.messaging;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Задача на проверку попытки (канал ml-tasks:grade_attempt).
 *
 * answers — список готовых к отправке ML элементов:
 * {"question_id": "<uuid>", "student_answer": {"index"|"indexes"|"text"}}
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class GradeAttemptRedisRequest {
    private UUID taskId;
    private UUID attemptId;
    private UUID testId;
    private UUID userId;
    private List<Map<String, Object>> answers;
}
