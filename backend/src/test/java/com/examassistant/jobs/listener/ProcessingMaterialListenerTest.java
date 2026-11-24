package com.examassistant.jobs.listener;

import com.examassistant.jobs.service.MlResultAckSupport;
import com.examassistant.materials.MaterialService;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.connection.stream.MapRecord;
import tools.jackson.databind.ObjectMapper;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProcessingMaterialListenerTest {

    private static final String READY_PAYLOAD =
            "{\"material_id\":\"" + TestFixtures.MATERIAL_ID + "\",\"status\":\"ready\"}";
    private static final String ERROR_PAYLOAD =
            "{\"material_id\":\"" + TestFixtures.MATERIAL_ID + "\",\"status\":\"error\",\"error\":\"boom\"}";

    @Mock
    private MaterialService materialService;
    @Mock
    private MlResultAckSupport ackSupport;

    private ProcessingMaterialListener listener;

    @BeforeEach
    void setUp() {
        listener = new ProcessingMaterialListener(materialService, new ObjectMapper(), ackSupport);
    }

    @Test
    void ready_changesStatusAndAcknowledges() {
        var message = message(READY_PAYLOAD);

        listener.onMessage(message);

        verify(materialService).changeStatus(TestFixtures.MATERIAL_ID, "ready");
        verify(ackSupport).ack(message);
    }

    @Test
    void error_changesStatusAndAcknowledges() {
        var message = message(ERROR_PAYLOAD);

        listener.onMessage(message);

        verify(materialService).changeStatus(TestFixtures.MATERIAL_ID, "error");
        verify(ackSupport).ack(message);
    }

    @Test
    void malformedJson_isPoisonAndAcknowledged() {
        var message = message("{");

        listener.onMessage(message);

        verify(ackSupport).ackPoison(any(), any(RuntimeException.class));
        verifyNoInteractions(materialService);
    }

    @Test
    void databaseFailure_isNotAcknowledged() {
        var message = message(READY_PAYLOAD);
        doThrow(new IllegalStateException("database down")).when(materialService).changeStatus(any(), any());

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
