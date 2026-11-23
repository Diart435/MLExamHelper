package com.examassistant.common.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;

import java.time.Duration;

@Configuration
public class RedisConfig {
    @Bean
    public RedisTemplate<String, String> redisTemplate(RedisConnectionFactory factory){
        RedisTemplate<String, String> redisTemplate = new RedisTemplate<>();
        redisTemplate.setConnectionFactory(factory);
        redisTemplate.setKeySerializer(new StringRedisSerializer());
        redisTemplate.setValueSerializer(new StringRedisSerializer());
        redisTemplate.setHashKeySerializer(new StringRedisSerializer());
        redisTemplate.setHashValueSerializer(new StringRedisSerializer());

        return redisTemplate;
    }

    @Bean
    StreamMessageListenerContainer<String, MapRecord<String, String, String>> listenerContainer(
            RedisConnectionFactory connectionFactory, MlStreamsProperties properties) {

        var options = StreamMessageListenerContainer
                .StreamMessageListenerContainerOptions.builder()
                .pollTimeout(Duration.ofMillis(100))
                // Контейнер стартует не сам: сначала RedisConsumer создаёт
                // consumer-группы на каналах, и только потом подписывается.
                .autoStartup(false)
                .build();

        // Имя consumer'а задаётся при подписке (Consumer.from в RedisConsumer):
        // в этой версии Spring Data Redis у билдера опций такого метода нет.
        return StreamMessageListenerContainer.create(connectionFactory, options);
    }
}
