package com.examassistant.tests;

import java.util.UUID;

public interface TestService {
    TestDTO getDTOById(UUID id, UUID courseId);
}