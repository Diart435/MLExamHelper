package com.examassistant.tests;

import com.examassistant.tests.DTO.CreateTestRequest;
import com.examassistant.tests.DTO.TestFilter;
import com.examassistant.tests.entity.Test;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.UUID;

public interface TestService {
    Test create(CreateTestRequest request, UUID userId);
    Test getById(UUID id, UUID userId);
    TestDTO getDTOById(UUID id, UUID userId);
    Page<Test> search(TestFilter filter, Pageable pageable, UUID userId);
    void delete(UUID id, UUID userId);
}