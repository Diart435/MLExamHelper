package com.examassistant.common;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

/**
 * Детерминированный UUID по паре (namespace, name).
 *
 * Нужен там, где backend может получить одно и то же событие дважды: доставка
 * в Redis Streams — «хотя бы один раз», поэтому вопросы теста должны иметь
 * один и тот же id при повторной обработке результата, иначе в test_questions
 * появятся дубли.
 */
public final class DeterministicUuid {

    private DeterministicUuid() {
    }

    public static UUID of(UUID namespace, String name) {
        String key = namespace + ":" + name;
        return UUID.nameUUIDFromBytes(key.getBytes(StandardCharsets.UTF_8));
    }
}
