package com.examassistant.tests.service;

import com.examassistant.common.exception.CourseForbiddenException;
import com.examassistant.common.exception.CourseNotFoundException;
import com.examassistant.common.exception.TestNotFoundException;
import com.examassistant.courses.entity.Course;
import com.examassistant.courses.repository.CourseRepository;
import com.examassistant.tests.TestDTO;
import com.examassistant.tests.TestService;
import com.examassistant.tests.DTO.CreateTestRequest;
import com.examassistant.tests.DTO.TestFilter;
import com.examassistant.tests.entity.Test;
import com.examassistant.tests.enums.TestDifficulty;
import com.examassistant.tests.enums.TestStatus;
import com.examassistant.tests.mapper.TestMapper;
import com.examassistant.tests.repository.TestRepository;
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
    private final CourseRepository courseRepository;
    private final TestMapper testMapper;

    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
            "testId", "title", "statusTest", "difficulty", "courseId", "createdAt"
    );

    @Transactional
    public Test create(CreateTestRequest request, UUID userId) {
        Course course = courseRepository.findById(request.getCourseId())
                .orElseThrow(() -> new CourseNotFoundException(request.getCourseId().toString()));

        if (!course.getOwnerId().equals(userId)) {
            throw new CourseForbiddenException("You cannot create a test for a course that is not yours");
        }

        Test test = Test.builder()
                .courseId(request.getCourseId())
                .title(request.getTitle())
                .statusTest(TestStatus.CREATED)
                .difficulty(request.getDifficulty() != null ? request.getDifficulty() : TestDifficulty.MEDIUM)
                .createdAt(OffsetDateTime.now())
                .build();

        return testRepository.save(test);
    }

    @Override
    @Transactional(readOnly = true)
    public Test getById(UUID id, UUID userId) {
        Test test = testRepository.findById(id)
                .orElseThrow(() -> new TestNotFoundException(id.toString()));

        Course course = courseRepository.findById(test.getCourseId())
                .orElseThrow(() -> new CourseNotFoundException(test.getCourseId().toString()));

        if (!course.getOwnerId().equals(userId)) {
            throw new CourseForbiddenException("This test does not belong to your course");
        }

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
            Course course = courseRepository.findById(courseId)
                    .orElseThrow(() -> new CourseNotFoundException(courseId.toString()));
            if (!course.getOwnerId().equals(userId)) {
                throw new CourseForbiddenException("This course does not belong to you");
            }
            return testRepository.findByCourseIdAndStatusTest(courseId, statusTest, pageable);
        } else {
            return testRepository.findByCourseOwnerId(userId, statusTest, pageable);
        }
    }

    @Transactional
    public void delete(UUID id, UUID userId) {
        Test test = testRepository.findById(id)
                .orElseThrow(() -> new TestNotFoundException(id.toString()));

        Course course = courseRepository.findById(test.getCourseId())
                .orElseThrow(() -> new CourseNotFoundException(test.getCourseId().toString()));

        if (!course.getOwnerId().equals(userId)) {
            throw new CourseForbiddenException("You cannot delete a test from a course that is not yours");
        }

        testRepository.delete(test);
    }
}