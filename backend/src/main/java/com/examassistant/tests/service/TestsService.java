package com.examassistant.tests.service;

import com.examassistant.common.exception.TestNotFoundException;
import com.examassistant.courses.CourseDTO;
import com.examassistant.courses.CourseService;
import com.examassistant.messaging.CreateTestRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.tests.TestDTO;
import com.examassistant.tests.TestService;
import com.examassistant.tests.DTO.CreateTestRequest;
import com.examassistant.tests.DTO.TestFilter;
import com.examassistant.tests.entity.MaterialsTest;
import com.examassistant.tests.entity.MaterialsTestId;
import com.examassistant.tests.entity.Test;
import com.examassistant.common.enums.TestDifficulty;
import com.examassistant.tests.enums.TestStatus;
import com.examassistant.tests.mapper.TestMapper;
import com.examassistant.tests.repository.MaterialsTestRepository;
import com.examassistant.tests.repository.TestRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class TestsService implements TestService {

    private final TestRepository testRepository;
    private final CourseService courseService;
    private final TestMapper testMapper;
    private final Producer redisProducer;
    private final MaterialsTestRepository materialsTestRepository;

    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
            "testId", "title", "statusTest", "difficulty", "courseId", "createdAt"
    );

    @Transactional
    public Test create(CreateTestRequest request, UUID userId) {
        CourseDTO course = courseService.getDTOById(request.getCourseId(), userId);

        Test test = Test.builder()
                .courseId(request.getCourseId())
                .title(request.getTitle())
                .amountQuestions(request.getAmountQuestions())
                .statusTest(TestStatus.CREATED)
                .difficulty(request.getDifficulty() == null ? TestDifficulty.MEDIUM : request.getDifficulty())
                .createdAt(OffsetDateTime.now())
                .build();

        Test saved = testRepository.save(test);
        saveMaterialsTest(saved.getTestId(), request.getMaterialIds());
        sendTestTask(saved, request.getMaterialIds());
        return saved;
    }

    @Override
    @Transactional(readOnly = true)
    public Test getById(UUID id, UUID userId) {
        Test test = testRepository.findById(id)
                .orElseThrow(() -> new TestNotFoundException(id.toString()));

        CourseDTO course = courseService.getDTOById(test.getCourseId(), userId);

        return test;
    }

    @Override
    @Transactional(readOnly = true)
    public TestDTO getDTOById(UUID id, UUID userId) {
        return testMapper.toDTO(getById(id, userId));
    }

    @Transactional(readOnly = true)
    public Page<Test> search(TestFilter filter, Pageable pageable, UUID userId) {
        for (Sort.Order order : pageable.getSort()) {
            if (!ALLOWED_SORT_FIELDS.contains(order.getProperty())) {
                throw new IllegalArgumentException("Invalid sort parameter. Field '" + order.getProperty() + "' not found in entity Test");
            }
        }

        UUID courseId = filter != null ? filter.getCourseId() : null;
        TestStatus statusTest = filter != null ? filter.getStatusTest() : null;

        if (courseId != null) {
            CourseDTO course = courseService.getDTOById(courseId, userId);
            return testRepository.findByCourseIdAndStatusTest(courseId, statusTest, pageable);
        } else {
            return testRepository.findByCourseOwnerId(userId, statusTest, pageable);
        }
    }

    @Transactional
    public void delete(UUID id, UUID userId) {
        Test test = testRepository.findById(id)
                .orElseThrow(() -> new TestNotFoundException(id.toString()));

        CourseDTO course = courseService.getDTOById(test.getCourseId(), userId);

        testRepository.delete(test);
    }

    public void sendTestTask(Test test, List<UUID> materialIds){
        UUID taskId = UUID.randomUUID();
        CreateTestRedisRequest createTest = new CreateTestRedisRequest(
                taskId,
                test.getTestId(),
                materialIds,
                test.getTitle(),
                test.getAmountQuestions(),
                test.getDifficulty().getValue(),
                test.getCourseId()
        );
        redisProducer.publishCreateTest(createTest);
    }

    @Transactional
    public void saveMaterialsTest(UUID testId, List<UUID> materialIds){
        List<MaterialsTest> links = materialIds.stream()
                .map(matId -> new MaterialsTest(new MaterialsTestId(testId, matId)))
                .toList();

        materialsTestRepository.saveAll(links);
    }
}