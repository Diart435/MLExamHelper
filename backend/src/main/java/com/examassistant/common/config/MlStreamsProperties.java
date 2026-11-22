package com.examassistant.common.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Data
@Component
@ConfigurationProperties(prefix = "ml.streams")
public class MlStreamsProperties {
    private String consumerGroup = "ml-backend";
    private String consumerName = "backend-1";
    private Duration reclaimIdle = Duration.ofSeconds(30);
    private long reclaimIntervalMs = 60_000;
    private int reclaimMaxAttempts = 5;
}
