package com.examassistant.jobs.service;

import com.examassistant.common.config.MlStreamsProperties;
import com.examassistant.common.redis.MlChannels;
import com.examassistant.jobs.listener.CreateTestListener;
import com.examassistant.jobs.listener.GradeTestListener;
import com.examassistant.jobs.listener.ProcessingMaterialListener;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Range;
import org.springframework.data.redis.RedisSystemException;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.PendingMessage;
import org.springframework.data.redis.connection.stream.PendingMessages;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RedisConsumerTest {
    @Mock private StreamMessageListenerContainer<String, MapRecord<String, String, String>> container;
    @Mock private StringRedisTemplate redisTemplate;
    @Mock private ProcessingMaterialListener ingestListener;
    @Mock private CreateTestListener createTestListener;
    @Mock private GradeTestListener gradeTestListener;
    @Mock private StreamOperations<String, String, String> streams;
    private MlStreamsProperties properties;
    private RedisConsumer consumer;

    @BeforeEach
    void setUp() {
        properties = new MlStreamsProperties();
        properties.setConsumerGroup("ml-backend");
        properties.setConsumerName("backend-test");
        properties.setReclaimIdle(Duration.ofSeconds(30));
        properties.setReclaimMaxAttempts(5);
        consumer = new RedisConsumer(container, redisTemplate, ingestListener, createTestListener,
                gradeTestListener, properties);
        lenient().when(redisTemplate.<String, String>opsForStream()).thenReturn(streams);
    }

    @Test
    void start_createsAllGroupsAndSubscribesWithoutAutoAck() {
        consumer.start();

        verify(redisTemplate, times(3)).execute(any(RedisCallback.class));
        verify(container, times(3)).receive(any(Consumer.class), any(StreamOffset.class), any(StreamListener.class));
        verify(container).start();
        assertThatRunning();
    }

    /**
     * Группа создаётся сырой командой {@code XGROUP CREATE <channel> <group> 0-0 MKSTREAM}:
     * идентификатор {@code >} из ReadOffset.lastConsumed() Redis не принимает,
     * а MKSTREAM нужен, чтобы канал создавался на лету.
     */
    @Test
    void start_createsGroupsWithMkstreamAndZeroOffset() throws Exception {
        List<RedisCallback<Object>> callbacks = new ArrayList<>();
        when(redisTemplate.execute(any(RedisCallback.class))).thenAnswer(invocation -> {
            RedisCallback<Object> callback = invocation.getArgument(0);
            callbacks.add(callback);
            return "OK";
        });

        consumer.start();

        assertThat(callbacks).hasSize(MlChannels.resultChannels().size());
        for (int i = 0; i < callbacks.size(); i++) {
            RedisConnection connection = mock(RedisConnection.class);
            when(connection.execute(eq("XGROUP"), any(byte[][].class))).thenReturn("OK");
            callbacks.get(i).doInRedis(connection);

            ArgumentCaptor<byte[][]> args = ArgumentCaptor.forClass(byte[][].class);
            verify(connection).execute(eq("XGROUP"), args.capture());
            List<String> command = Arrays.stream(args.getValue()).map(String::new).toList();
            assertThat(command).containsExactly("CREATE", MlChannels.resultChannels().get(i),
                    "ml-backend", "0-0", "MKSTREAM");
        }
    }

    /** BUSYGROUP — группа уже есть (перезапуск backend'а), это штатная ситуация. */
    @Test
    void start_toleratesBusyGroup() {
        when(redisTemplate.execute(any(RedisCallback.class))).thenThrow(
                new RedisSystemException("Error in execution",
                        new RuntimeException("BUSYGROUP Consumer Group name already exists")));

        consumer.start();

        verify(container, times(3)).receive(any(Consumer.class), any(StreamOffset.class), any(StreamListener.class));
        assertThatRunning();
    }

    /** Прочие ошибки транспорта не должны ронять приложение, но обязаны быть видны в логе. */
    @Test
    void start_survivesTransportFailure() {
        when(redisTemplate.execute(any(RedisCallback.class))).thenThrow(
                new RedisSystemException("Error in execution",
                        new RuntimeException("NOGROUP No such key 'ingest:ml-to-be'")));

        consumer.start();

        verify(container, times(3)).receive(any(Consumer.class), any(StreamOffset.class), any(StreamListener.class));
        assertThatRunning();
    }

    @Test
    void reclaim_claimsPendingAndRoutesToChannelListener() {
        consumer.start();
        clearInvocations(streams, gradeTestListener);
        RecordId id = RecordId.of("1-0");
        PendingMessages pending = pending(pendingMessage(id, 2));
        PendingMessages empty = emptyPending();
        when(streams.pending(anyString(), eq("ml-backend"), any(Range.class), eq(50L), eq(Duration.ofSeconds(30))))
                .thenReturn(empty);
        when(streams.pending(eq("grade-test:ml-to-be"), eq("ml-backend"), any(Range.class), eq(50L),
                eq(Duration.ofSeconds(30)))).thenReturn(pending);
        MapRecord<String, String, String> message = mock(MapRecord.class);
        when(streams.claim(eq("grade-test:ml-to-be"), eq("ml-backend"), eq("backend-test"),
                eq(Duration.ofSeconds(30)), eq(id))).thenReturn(List.of(message));

        consumer.reclaimPending();

        verify(gradeTestListener).onMessage(message);
    }

    @Test
    void reclaim_poisonMessageIsAcknowledgedAndNotClaimed() {
        consumer.start();
        clearInvocations(streams);
        RecordId id = RecordId.of("2-0");
        PendingMessages pending = pending(pendingMessage(id, 5));
        PendingMessages empty = emptyPending();
        when(streams.pending(anyString(), eq("ml-backend"), any(Range.class), eq(50L), eq(Duration.ofSeconds(30))))
                .thenReturn(empty);
        when(streams.pending(eq("ingest:ml-to-be"), eq("ml-backend"), any(Range.class), eq(50L),
                eq(Duration.ofSeconds(30)))).thenReturn(pending);

        consumer.reclaimPending();

        verify(streams).acknowledge(eq("ingest:ml-to-be"), eq("ml-backend"), eq(id));
        verify(streams).delete(eq("ingest:ml-to-be"), eq(id));
        verify(streams, never()).claim(anyString(), anyString(), anyString(), any(), any(RecordId.class));
    }

    private PendingMessage pendingMessage(RecordId id, long deliveries) {
        PendingMessage message = mock(PendingMessage.class);
        lenient().when(message.getId()).thenReturn(id);
        lenient().when(message.getTotalDeliveryCount()).thenReturn(deliveries);
        return message;
    }

    private PendingMessages pending(PendingMessage message) {
        PendingMessages pending = mock(PendingMessages.class);
        when(pending.iterator()).thenReturn(List.of(message).iterator());
        return pending;
    }

    private PendingMessages emptyPending() {
        PendingMessages pending = mock(PendingMessages.class);
        lenient().when(pending.iterator()).thenReturn(List.<PendingMessage>of().iterator());
        return pending;
    }

    private void assertThatRunning() {
        org.assertj.core.api.Assertions.assertThat(consumer.isRunning()).isTrue();
        org.assertj.core.api.Assertions.assertThat(consumer.getPhase())
                .isEqualTo(org.springframework.context.SmartLifecycle.DEFAULT_PHASE - 10);
    }
}
