package com.examassistant.ml;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Имена каналов Redis Streams для обмена с ML.
 *
 * Контракт: один тип задачи — один канал. Тип задаёт ИМЯ КАНАЛА, а не поле в
 * payload, поэтому сообщение нельзя прочитать не тем обработчиком.
 *
 *   ml-tasks:ingest        ml-results:ingest
 *   ml-tasks:create_test   ml-results:create_test
 *   ml-tasks:grade_attempt ml-results:grade_attempt
 *
 * Backend читает каналы результатов своей consumer-группой и подтверждает
 * сообщения в том же канале, откуда их получил.
 */
@Component
public class MlChannels {

    public static final String INGEST = "ingest";
    public static final String CREATE_TEST = "create_test";
    public static final String GRADE_ATTEMPT = "grade_attempt";

    private final String tasksPrefix;
    private final String resultsPrefix;
    private final String consumerGroup;
    private final String consumerName;

    public MlChannels(
            @Value("${ml.streams.tasks-prefix:ml-tasks}") String tasksPrefix,
            @Value("${ml.streams.results-prefix:ml-results}") String resultsPrefix,
            @Value("${ml.streams.consumer-group:ml-backend}") String consumerGroup,
            @Value("${ml.streams.consumer-name:backend-1}") String consumerName) {
        this.tasksPrefix = tasksPrefix;
        this.resultsPrefix = resultsPrefix;
        this.consumerGroup = consumerGroup;
        this.consumerName = consumerName;
    }

    public String taskChannel(String taskType) {
        return tasksPrefix + ":" + taskType;
    }

    public String resultChannel(String taskType) {
        return resultsPrefix + ":" + taskType;
    }

    /**
     * Имя канала → тип задачи: "ml-results:create_test" → "create_test".
     */
    public String typeFromChannel(String channel) {
        int colon = channel.lastIndexOf(':');
        return colon < 0 ? "" : channel.substring(colon + 1);
    }

    public String consumerGroup() {
        return consumerGroup;
    }

    public String consumerName() {
        return consumerName;
    }
}
