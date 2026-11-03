package com.examassistant.courses.service;

import com.examassistant.common.exception.CourseForbiddenException;
import com.examassistant.common.exception.CourseNotFoundException;
import com.examassistant.courses.CourseDTO;
import com.examassistant.courses.DTO.CourseFilter;
import com.examassistant.courses.DTO.CreateCourseRequest;
import com.examassistant.courses.DTO.UpdateCourseRequest;
import com.examassistant.courses.entity.Course;
import com.examassistant.courses.mapper.CourseMapper;
import com.examassistant.courses.repository.CourseRepository;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CoursesServiceTest {

    @Mock
    private CourseRepository courseRepository;
    @Mock
    private CourseMapper courseMapper;

    @InjectMocks
    private CoursesService coursesService;

    @Test
    void create_newCourse_savesWithOwnerAndTimestamps() {
        CreateCourseRequest request = new CreateCourseRequest("Math", "Course description");
        when(courseRepository.existsByOwnerIdAndTitle(TestFixtures.USER_ID, "Math")).thenReturn(false);
        when(courseRepository.save(any(Course.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        OffsetDateTime before = OffsetDateTime.now().minusSeconds(1);
        Course result = coursesService.create(request, TestFixtures.USER_ID);

        assertThat(result.getTitle()).isEqualTo("Math");
        assertThat(result.getCourseDescription()).isEqualTo("Course description");
        assertThat(result.getOwnerId()).isEqualTo(TestFixtures.USER_ID);
        assertThat(result.getCreatedAt()).isAfter(before);
        assertThat(result.getUpdatedAt()).isAfter(before);

        ArgumentCaptor<Course> captor = ArgumentCaptor.forClass(Course.class);
        verify(courseRepository).save(captor.capture());
        assertThat(captor.getValue().getTitle()).isEqualTo("Math");
    }

    @Test
    void create_duplicateTitle_throwsAndDoesNotSave() {
        CreateCourseRequest request = new CreateCourseRequest("Math", "Course description");
        when(courseRepository.existsByOwnerIdAndTitle(TestFixtures.USER_ID, "Math")).thenReturn(true);

        assertThatThrownBy(() -> coursesService.create(request, TestFixtures.USER_ID))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Course with this title already exists for this user");

        verify(courseRepository, never()).save(any(Course.class));
    }

    @Test
    void getById_found_returnsCourse() {
        Course course = TestFixtures.course();
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.of(course));

        Course result = coursesService.getById(TestFixtures.COURSE_ID, TestFixtures.USER_ID);

        assertThat(result).isSameAs(course);
    }

    @Test
    void getById_notFound_throws() {
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> coursesService.getById(TestFixtures.COURSE_ID, TestFixtures.USER_ID))
                .isInstanceOf(CourseNotFoundException.class)
                .hasMessage(TestFixtures.COURSE_ID.toString());
    }

    @Test
    void search_nullFilter_returnsCoursesByOwner() {
        Pageable pageable = PageRequest.of(0, 10, Sort.by("title"));
        Page<Course> page = new PageImpl<>(List.of(TestFixtures.course()), pageable, 1);
        when(courseRepository.findByOwnerId(TestFixtures.USER_ID, pageable)).thenReturn(page);

        Page<Course> result = coursesService.search(null, pageable, TestFixtures.USER_ID);

        assertThat(result).isSameAs(page);
        verify(courseRepository).findByOwnerId(TestFixtures.USER_ID, pageable);
    }

    @Test
    void search_blankTitle_returnsCoursesByOwner() {
        Pageable pageable = PageRequest.of(0, 10);
        Page<Course> page = new PageImpl<>(List.of(TestFixtures.course()), pageable, 1);
        CourseFilter filter = new CourseFilter();
        filter.setTitle("   ");
        when(courseRepository.findByOwnerId(TestFixtures.USER_ID, pageable)).thenReturn(page);

        Page<Course> result = coursesService.search(filter, pageable, TestFixtures.USER_ID);

        assertThat(result).isSameAs(page);
        verify(courseRepository).findByOwnerId(TestFixtures.USER_ID, pageable);
    }

    @Test
    void search_titleIsTrimmedAndUsesContainingQuery() {
        Pageable pageable = PageRequest.of(0, 10);
        Page<Course> page = new PageImpl<>(List.of(TestFixtures.course()), pageable, 1);
        CourseFilter filter = new CourseFilter();
        filter.setTitle("  math  ");
        when(courseRepository.findByOwnerIdAndTitleContainingIgnoreCase(
                TestFixtures.USER_ID, "math", pageable)).thenReturn(page);

        Page<Course> result = coursesService.search(filter, pageable, TestFixtures.USER_ID);

        assertThat(result).isSameAs(page);
        verify(courseRepository).findByOwnerIdAndTitleContainingIgnoreCase(
                TestFixtures.USER_ID, "math", pageable);
    }

    @Test
    void search_invalidSortField_throws() {
        Pageable pageable = PageRequest.of(0, 10, Sort.by("unknownField"));

        assertThatThrownBy(() -> coursesService.search(null, pageable, TestFixtures.USER_ID))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("unknownField");

        verifyNoInteractions(courseRepository);
    }

    @Test
    void search_allowedSortFields_doNotThrow() {
        Pageable pageable = PageRequest.of(0, 10, Sort.by("title", "createdAt"));
        Page<Course> page = new PageImpl<>(List.of(TestFixtures.course()), pageable, 1);
        when(courseRepository.findByOwnerId(TestFixtures.USER_ID, pageable)).thenReturn(page);

        assertThat(coursesService.search(null, pageable, TestFixtures.USER_ID)).isSameAs(page);
    }

    @Test
    void update_success_updatesFieldsAndTimestamp() {
        Course course = TestFixtures.course();
        course.setUpdatedAt(OffsetDateTime.now().minusDays(1));
        UpdateCourseRequest request = new UpdateCourseRequest("New title", "New description");
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.of(course));
        when(courseRepository.existsByOwnerIdAndTitle(TestFixtures.USER_ID, "New title")).thenReturn(false);
        when(courseRepository.save(any(Course.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        OffsetDateTime before = OffsetDateTime.now().minusSeconds(1);
        Course result = coursesService.update(TestFixtures.COURSE_ID, request, TestFixtures.USER_ID);

        assertThat(result.getTitle()).isEqualTo("New title");
        assertThat(result.getCourseDescription()).isEqualTo("New description");
        assertThat(result.getOwnerId()).isEqualTo(TestFixtures.USER_ID);
        assertThat(result.getUpdatedAt()).isAfter(before);
        verify(courseRepository).save(course);
    }

    @Test
    void update_sameTitle_doesNotCheckDuplicates() {
        Course course = TestFixtures.course();
        UpdateCourseRequest request = new UpdateCourseRequest("Math", null);
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.of(course));
        when(courseRepository.save(any(Course.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        coursesService.update(TestFixtures.COURSE_ID, request, TestFixtures.USER_ID);

        verify(courseRepository, never()).existsByOwnerIdAndTitle(any(), anyString());
        assertThat(course.getTitle()).isEqualTo("Math");
        assertThat(course.getCourseDescription()).isEqualTo("Course description");
    }

    @Test
    void update_nullTitleAndDescription_keepsExistingValues() {
        Course course = TestFixtures.course();
        UpdateCourseRequest request = new UpdateCourseRequest(null, null);
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.of(course));
        when(courseRepository.save(any(Course.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        coursesService.update(TestFixtures.COURSE_ID, request, TestFixtures.USER_ID);

        assertThat(course.getTitle()).isEqualTo("Math");
        assertThat(course.getCourseDescription()).isEqualTo("Course description");
        verify(courseRepository, never()).existsByOwnerIdAndTitle(any(), anyString());
    }

    @Test
    void update_notFound_throws() {
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> coursesService.update(
                TestFixtures.COURSE_ID, new UpdateCourseRequest("New", "New"), TestFixtures.USER_ID))
                .isInstanceOf(CourseNotFoundException.class);
    }

    @Test
    void update_notOwner_throwsAndDoesNotSave() {
        Course course = TestFixtures.course(TestFixtures.COURSE_ID, TestFixtures.OTHER_USER_ID, "Math");
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.of(course));

        assertThatThrownBy(() -> coursesService.update(
                TestFixtures.COURSE_ID, new UpdateCourseRequest("New", "New"), TestFixtures.USER_ID))
                .isInstanceOf(CourseForbiddenException.class)
                .hasMessage("This course is not yours");

        verify(courseRepository, never()).save(any(Course.class));
        verify(courseRepository, never()).existsByOwnerIdAndTitle(any(), anyString());
    }

    @Test
    void update_duplicateTitle_throwsAndKeepsOldValues() {
        Course course = TestFixtures.course();
        UpdateCourseRequest request = new UpdateCourseRequest("New title", "New description");
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.of(course));
        when(courseRepository.existsByOwnerIdAndTitle(TestFixtures.USER_ID, "New title")).thenReturn(true);

        assertThatThrownBy(() -> coursesService.update(
                TestFixtures.COURSE_ID, request, TestFixtures.USER_ID))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Course with this title already exists for this user");

        assertThat(course.getTitle()).isEqualTo("Math");
        assertThat(course.getCourseDescription()).isEqualTo("Course description");
        verify(courseRepository, never()).save(any(Course.class));
    }

    @Test
    void delete_success_deletesCourse() {
        when(courseRepository.findById(TestFixtures.COURSE_ID))
                .thenReturn(Optional.of(TestFixtures.course()));

        coursesService.delete(TestFixtures.COURSE_ID, TestFixtures.USER_ID);

        verify(courseRepository).deleteById(TestFixtures.COURSE_ID);
    }

    @Test
    void delete_notFound_throws() {
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> coursesService.delete(TestFixtures.COURSE_ID, TestFixtures.USER_ID))
                .isInstanceOf(CourseNotFoundException.class);

        verify(courseRepository, never()).deleteById(any());
    }

    @Test
    void delete_notOwner_throwsAndDoesNotDelete() {
        Course course = TestFixtures.course(TestFixtures.COURSE_ID, TestFixtures.OTHER_USER_ID, "Math");
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.of(course));

        assertThatThrownBy(() -> coursesService.delete(TestFixtures.COURSE_ID, TestFixtures.USER_ID))
                .isInstanceOf(CourseForbiddenException.class)
                .hasMessage("This course is not yours");

        verify(courseRepository, never()).deleteById(any());
    }

    @Test
    void getDTOById_mapsCourse() {
        Course course = TestFixtures.course();
        CourseDTO dto = TestFixtures.courseDto(TestFixtures.COURSE_ID, TestFixtures.USER_ID);
        when(courseRepository.findById(TestFixtures.COURSE_ID)).thenReturn(Optional.of(course));
        when(courseMapper.toDTO(course)).thenReturn(dto);

        CourseDTO result = coursesService.getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID);

        assertThat(result).isSameAs(dto);
        verify(courseMapper).toDTO(course);
    }
}
