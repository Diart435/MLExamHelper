package com.examassistant.common.util;

import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class UuidV5Test {
    private static final UUID TEST_ID = UUID.fromString("66666666-6666-6666-6666-666666666666");
    private static final UUID ATTEMPT_ID = UUID.fromString("99999999-9999-9999-9999-999999999999");

    @Test
    void matchesContractVectors() {
        UUID questionOne = UuidV5.create(TEST_ID, "q:1");
        assertThat(questionOne).isEqualTo(UUID.fromString("3ca4bc9c-3865-5f44-9f91-a19b5cfb788f"));
        assertThat(UuidV5.create(TEST_ID, "q:2"))
                .isEqualTo(UUID.fromString("0d53909a-e8e3-5793-8fd1-2b4ebea2be16"));
        assertThat(UuidV5.create(ATTEMPT_ID, questionOne.toString()))
                .isEqualTo(UUID.fromString("3116d980-cdc2-54c8-bddf-f62a03c9f1d2"));
    }

    @Test
    void createsVersionFiveRfcVariantUuid() {
        UUID result = UuidV5.create(TEST_ID, "q:1");
        assertThat(result.version()).isEqualTo(5);
        assertThat(result.variant()).isEqualTo(2);
    }
}
