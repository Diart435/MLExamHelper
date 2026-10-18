package com.examassistant.courses.service;

import com.examassistant.courses.DTO.CourseFilter;
import com.examassistant.courses.DTO.CoursesResponse;
import com.examassistant.courses.DTO.CreateCourseRequest;
import com.examassistant.courses.DTO.UpdateCourseRequest;
import com.examassistant.common.exception.CourseNotFoundException;
import com.examassistant.courses.entity.Course;
import com.examassistant.common.mapper.CourseMapper;
import com.examassistant.courses.repository.CourseRepository;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class CoursesService {

    private final CourseRepository courseRepository;
    private final CourseMapper courseMapper;

    @Transactional
    public CoursesResponse create(@Valid CreateCourseRequest request) {
        if (courseRepository.existsByOwnerIdAndTitle(request.getUserId(), request.getTitle())) {
            throw new IllegalArgumentException("Course with this title already exists for this user");
        }

        Course course = Course.builder()
                .title(request.getTitle())
                .courseDescription(request.getCourseDescription())
                .ownerId(request.getUserId())
                .createdAt(OffsetDateTime.now())
                .updatedAt(OffsetDateTime.now())
                .build();

        Course savedCourse = courseRepository.save(course);
        return courseMapper.toResponse(savedCourse);
    }

    @Transactional(readOnly = true)
    public CoursesResponse getById(UUID id) {
        Course course = courseRepository.findById(id)
                .orElseThrow(() -> new CourseNotFoundException(id.toString()));
        return courseMapper.toResponse(course);
    }

    @Transactional(readOnly = true)
    public Page<CoursesResponse> search(CourseFilter filter, Pageable pageable) {
        UUID ownerId = filter != null ? filter.getUserId() : null;
        String title = filter != null ? filter.getTitle() : null;
        String description = filter != null ? filter.getCourseDescription() : null;

        return courseRepository.findByFilter(ownerId, title, description, pageable)
                .map(courseMapper::toResponse);
    }

    @Transactional
    public CoursesResponse update(UUID id, @Valid UpdateCourseRequest request) {
        Course course = courseRepository.findById(id)
                .orElseThrow(() -> new CourseNotFoundException(id.toString()));

        if (request.getTitle() != null && !request.getTitle().equals(course.getTitle())) {
            if (courseRepository.existsByOwnerIdAndTitle(course.getOwnerId(), request.getTitle())) {
                throw new IllegalArgumentException("Course with this title already exists for this user");
            }
        }

        if (request.getTitle() != null) {
            course.setTitle(request.getTitle());
        }
        if (request.getCourseDescription() != null) {
            course.setCourseDescription(request.getCourseDescription());
        }
        if (request.getUserId() != null) {
            course.setOwnerId(request.getUserId());
        }
        course.setUpdatedAt(OffsetDateTime.now());

        Course updatedCourse = courseRepository.save(course);
        return courseMapper.toResponse(updatedCourse);
    }

    @Transactional
    public void delete(UUID id) {
        if (!courseRepository.existsById(id)) {
            throw new CourseNotFoundException(id.toString());
        }
        courseRepository.deleteById(id);
    }
}