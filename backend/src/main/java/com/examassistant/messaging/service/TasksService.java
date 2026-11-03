package com.examassistant.messaging.service;

import com.examassistant.common.exception.TaskNotFoundException;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.TaskService;
import com.examassistant.messaging.entity.QueryTask;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.messaging.repository.TaskRepository;
import com.examassistant.tests.TestDifficulty;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class TasksService implements TaskService {
    private final TaskRepository taskRepository;

    @Transactional
    public void create(UUID taskId, TaskDTO taskDTO){
        QueryTask task = new QueryTask(taskId,
                taskDTO.getTestId(),
                taskDTO.getTitle(),
                taskDTO.getNumQuestions(),
                TestDifficulty.fromValue(taskDTO.getDifficulty()),
                taskDTO.getCourseId(), OffsetDateTime.now(),
                null,
                taskDTO.getStatusTask());
        taskRepository.save(task);
    }

    @Transactional
    public void changeStatus(UUID taskId){
        QueryTask task = taskRepository.findById(taskId).orElseThrow(() -> new TaskNotFoundException("task not found"));
        task.setStatusTask(StatusTask.FINISHED);
    }
}
