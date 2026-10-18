package com.examassistant.courses.service;

import com.examassistant.common.exception.CourseForbiddenException;
import com.examassistant.courses.CourseDTO;
import com.examassistant.courses.CourseService;
import com.examassistant.courses.DTO.CourseFilter;
import com.examassistant.courses.DTO.CreateCourseRequest;
import com.examassistant.courses.DTO.UpdateCourseRequest;
import com.examassistant.common.exception.CourseNotFoundException;
import com.examassistant.courses.entity.Course;
import com.examassistant.courses.mapper.CourseMapper;
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
public class CoursesService implements CourseService {

    private final CourseRepository courseRepository;
    private final CourseMapper courseMapper;

    @Transactional
    public Course create(@Valid CreateCourseRequest request, UUID id) {
        if (courseRepository.existsByOwnerIdAndTitle(id, request.getTitle())) {
            throw new IllegalArgumentException("Course with this title already exists for this user");
        }

        Course course = Course.builder()
                .title(request.getTitle())
                .courseDescription(request.getCourseDescription())
                .ownerId(id)
                .createdAt(OffsetDateTime.now())
                .updatedAt(OffsetDateTime.now())
                .build();

        return courseRepository.save(course);
    }

    @Transactional(readOnly = true)
    public Course getById(UUID id, UUID userId) {
        return courseRepository.findById(id)
                .orElseThrow(() -> new CourseNotFoundException(id.toString()));
    }

    @Transactional(readOnly = true)
    public Page<Course> search(CourseFilter filter, Pageable pageable, UUID userId) {
        UUID ownerId = filter != null ? userId : null;
        String title = filter != null ? filter.getTitle() : null;
        String description = filter != null ? filter.getCourseDescription() : null;

        return courseRepository.findByFilter(ownerId, title, description, pageable);
    }

    @Transactional
    public Course update(UUID id, @Valid UpdateCourseRequest request, UUID userId) {
        Course course = courseRepository.findById(id)
                .orElseThrow(() -> new CourseNotFoundException(id.toString()));
        if(!course.getOwnerId().equals(userId)){
            throw new CourseForbiddenException("This course is not yours");
        }

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
        course.setOwnerId(userId);
        course.setUpdatedAt(OffsetDateTime.now());

        return courseRepository.save(course);
    }

    @Transactional
    public void delete(UUID id, UUID userId) {
        Course course = courseRepository.findById(id)
                .orElseThrow(() -> new CourseNotFoundException(id.toString()));
        if(!course.getOwnerId().equals(userId)){
            throw new CourseForbiddenException("This course is not yours");
        }
        courseRepository.deleteById(id);
    }

    @Override
    public CourseDTO getDTOById(UUID id, UUID userId) {
        return courseMapper.toDTO(getById(id, userId));
    }
}