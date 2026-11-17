package com.examassistant.messaging;

import java.util.UUID;

public interface TaskService {
    void changeStatus(UUID taskId);
}
