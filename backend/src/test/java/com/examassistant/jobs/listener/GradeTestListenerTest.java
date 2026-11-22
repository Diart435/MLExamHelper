package com.examassistant.jobs.listener;

import com.examassistant.jobs.DTO.GradeTestResultMessage;
import com.examassistant.jobs.service.GradeTestResultService;
import com.examassistant.jobs.service.MlResultAckSupport;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.connection.stream.MapRecord;
import tools.jackson.databind.ObjectMapper;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class GradeTestListenerTest {
    @Mock private GradeTestResultService resultService;
    @Mock private MlResultAckSupport ackSupport;
    private GradeTestListener listener;

    @BeforeEach
    void setUp() {
        listener = new GradeTestListener(resultService, new ObjectMapper(), ackSupport);
    }

    @Test
    void successWithoutStatus_appliesGradeAndAcknowledges() {
        var message = message("{\"task_id\":\"" + TestFixtures.TASK_ID + "\",\"attempt_id\":\""
                + TestFixtures.ATTEMPT_ID + "\",\"test_id\":\"" + TestFixtures.TEST_ID
                + "\",\"score_pct\":83.3,\"grade\":4,\"items\":[]}");

        listener.onMessage(message);

        ArgumentCaptor<GradeTestResultMessage> captor = ArgumentCaptor.forClass(GradeTestResultMessage.class);
        verify(resultService).apply(captor.capture());
        assertThat(captor.getValue().getAttemptId()).isEqualTo(TestFixtures.ATTEMPT_ID);
        verify(ackSupport).ack(message);
    }

    @Test
    void error_doesNotTouchAttemptAndAcknowledges() {
        var message = message("{\"task_id\":\"" + TestFixtures.TASK_ID + "\",\"error\":\"grading failed\"}");

        listener.onMessage(message);

        verifyNoInteractions(resultService);
        verify(ackSupport).ack(message);
    }

    @Test
    void malformedJson_isPoisonAndAcknowledged() {
        var message = message("{");

        listener.onMessage(message);

        verify(ackSupport).ackPoison(any(), any(RuntimeException.class));
        verifyNoInteractions(resultService);
    }

    @Test
    void databaseFailure_isNotAcknowledged() {
        var message = message("{\"task_id\":\"" + TestFixtures.TASK_ID + "\",\"attempt_id\":\""
                + TestFixtures.ATTEMPT_ID + "\"}");
        doThrow(new IllegalStateException("database down")).when(resultService).apply(any());

        listener.onMessage(message);

        verify(ackSupport, org.mockito.Mockito.never()).ack(any());
        verify(ackSupport, org.mockito.Mockito.never()).ackPoison(any(), any());
    }

    @SuppressWarnings("unchecked")
    private MapRecord<String, String, String> message(String payload) {
        MapRecord<String, String, String> message = mock(MapRecord.class);
        when(ackSupport.payload(message)).thenReturn(payload);
        return message;
    }
}
