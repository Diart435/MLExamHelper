package com.examassistant.materials;

import java.util.UUID;

public interface MaterialService {
    void changeStatus(UUID materialId, String status);
}
