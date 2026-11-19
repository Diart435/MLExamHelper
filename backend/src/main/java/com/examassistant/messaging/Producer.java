package com.examassistant.messaging;

import org.springframework.data.redis.connection.stream.RecordId;

public interface Producer {
    RecordId publishCreateTest(CreateTestRedisRequest test);
    RecordId publishMaterialProcess(ProcessMaterialRedisRequest material);
}
