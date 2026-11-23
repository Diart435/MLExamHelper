package com.examassistant.jobs.listener;

import com.examassistant.jobs.DTO.CreateTestResultMessage;
import com.examassistant.jobs.service.CreateTestResultService;
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

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CreateTestListenerTest {

    private static final String OK_PAYLOAD =
            "{\"task_id\":\"" + TestFixtures.TASK_ID + "\",\"status\":\"ok\",\"test_id\":\""
                    + TestFixtures.TEST_ID + "\",\"test\":{\"title\":\"Math test\",\"questions\":[]}}";
    private static final String ERROR_PAYLOAD =
            "{\"task_id\":\"" + TestFixtures.TASK_ID + "\",\"status\":\"error\",\"test_id\":\""
                    + TestFixtures.TEST_ID + "\",\"error\":\"generation failed\"}";

    @Mock
    private CreateTestResultService resultService;
    @Mock
    private MlResultAckSupport ackSupport;

    private CreateTestListener listener;

    @BeforeEach
    void setUp() {
        listener = new CreateTestListener(resultService, new ObjectMapper(), ackSupport);
    }

    @Test
    void success_appliesResultAndAcknowledges() {
        var message = message(OK_PAYLOAD);

        listener.onMessage(message);

        ArgumentCaptor<CreateTestResultMessage> captor = ArgumentCaptor.forClass(CreateTestResultMessage.class);
        verify(resultService).apply(captor.capture());
        assertThat(captor.getValue().getTaskId()).isEqualTo(TestFixtures.TASK_ID);
        assertThat(captor.getValue().getTestId()).isEqualTo(TestFixtures.TEST_ID);
        verify(ackSupport).ack(message);
    }

    @Test
    void error_appliesErrorAndAcknowledges() {
        var message = message(ERROR_PAYLOAD);

        listener.onMessage(message);

        verify(resultService).applyError(any());
        verify(resultService, org.mockito.Mockito.never()).apply(any());
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
        var message = message(OK_PAYLOAD);
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
