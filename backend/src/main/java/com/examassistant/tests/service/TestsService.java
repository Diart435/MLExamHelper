package com.examassistant.tests.service;

import com.examassistant.tests.DTO.CreateTestRequest;
import com.examassistant.tests.DTO.TestFilter;
import com.examassistant.tests.DTO.TestsResponse;
import com.examassistant.tests.TestDTO;
import com.examassistant.tests.TestService; // если создавал интерфейс
import com.examassistant.tests.entity.Test;
import com.examassistant.tests.enums.TestDifficulty;
import com.examassistant.tests.enums.TestStatus;
import com.examassistant.common.exception.TestNotFoundException;
import com.examassistant.tests.mapper.TestMapper;
import com.examassistant.tests.repository.TestRepository;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class TestsService implements TestService {

    private final TestRepository testRepository;
    private final TestMapper testMapper;

    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
            "testId", "title", "statusTest", "difficulty", "courseId", "createdAt"
    );

    @Transactional
    public TestsResponse create(@Valid CreateTestRequest request) {
        Test test = Test.builder()
                .courseId(request.getCourseId())
                .title(request.getTitle())
                .statusTest(TestStatus.CREATED)
                .difficulty(request.getDifficulty() != null ? request.getDifficulty() : TestDifficulty.MEDIUM)
                .createdAt(OffsetDateTime.now())
                .build();

        Test savedTest = testRepository.save(test);
        return testMapper.toResponse(savedTest);
    }

    @Transactional(readOnly = true)
    public Test getById(UUID id, UUID courseId) {
        Test test = testRepository.findById(id)
                .orElseThrow(() -> new TestNotFoundException("Test not found with id: " + id));

        if (!test.getCourseId().equals(courseId)) {
            throw new IllegalArgumentException("Test does not belong to the specified course");
        }
        return test;
    }

    @Transactional(readOnly = true)
    public Page<TestsResponse> search(TestFilter filter, Pageable pageable) {
        for (Sort.Order order : pageable.getSort()) {
            if (!ALLOWED_SORT_FIELDS.contains(order.getProperty())) {
                throw new IllegalArgumentException("Invalid sort parameter. Field '" + order.getProperty() + "' not found in entity Test");
            }
        }

        UUID courseId = filter != null ? filter.getCourseId() : null;
        TestStatus statusTest = filter != null ? filter.getStatusTest() : null;

        return testRepository.findByFilter(courseId, statusTest, pageable)
                .map(testMapper::toResponse);
    }

    @Transactional
    public void delete(UUID id) {
        if (!testRepository.existsById(id)) {
            throw new TestNotFoundException("Test not found with id: " + id);
        }
        testRepository.deleteById(id);
    }

    @Override
    public TestDTO getDTOById(UUID id, UUID courseId) {
        return testMapper.toDTO(getById(id, courseId));
    }
}