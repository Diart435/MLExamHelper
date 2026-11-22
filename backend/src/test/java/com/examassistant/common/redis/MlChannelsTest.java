package com.examassistant.common.redis;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class MlChannelsTest {
    @Test
    void buildsAllContractChannels() {
        assertThat(MlChannels.taskChannel(MlChannels.INGEST)).isEqualTo("ingest:be-to-ml");
        assertThat(MlChannels.taskChannel(MlChannels.CREATE_TEST)).isEqualTo("create-test:be-to-ml");
        assertThat(MlChannels.taskChannel(MlChannels.GRADE_TEST)).isEqualTo("grade-test:be-to-ml");
        assertThat(MlChannels.resultChannels()).containsExactly(
                "ingest:ml-to-be", "create-test:ml-to-be", "grade-test:ml-to-be");
    }
}
