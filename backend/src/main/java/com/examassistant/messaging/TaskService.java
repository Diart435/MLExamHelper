package com.examassistant.messaging;

import com.examassistant.messaging.enums.StatusTask;

import java.util.UUID;

public interface TaskService {
    void changeStatus(UUID taskId);

    void changeStatus(UUID taskId, StatusTask status);
}
