package com.examassistant.tests.service;

import com.examassistant.common.enums.TestAmountQuestions;
import com.examassistant.common.enums.TestDifficulty;
import com.examassistant.common.exception.CourseForbiddenException;
import com.examassistant.common.exception.TestNotFoundException;
import com.examassistant.courses.CourseService;
import com.examassistant.messaging.CreateTestRedisRequest;
import com.examassistant.messaging.Producer;
import com.examassistant.support.TestFixtures;
import com.examassistant.tests.DTO.CreateTestRequest;
import com.examassistant.tests.DTO.TestFilter;
import com.examassistant.tests.TestDTO;
import com.examassistant.tests.entity.MaterialsTest;
import com.examassistant.tests.enums.TestStatus;
import com.examassistant.tests.mapper.TestMapper;
import com.examassistant.tests.repository.MaterialsTestRepository;
import com.examassistant.tests.repository.TestRepository;
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

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class TestsServiceTest {

    @Mock
    private TestRepository testRepository;
    @Mock
    private CourseService courseService;
    @Mock
    private TestMapper testMapper;
    @Mock
    private Producer redisProducer;
    @Mock
    private MaterialsTestRepository materialsTestRepository;

    @InjectMocks
    private TestsService testsService;

    @Test
    void create_savesTestLinksAndPublishesTask() {
        CreateTestRequest request = TestFixtures.createTestRequest();
        stubCourseAccess();
        stubSaveAssignsId();

        com.examassistant.tests.entity.Test result =
                testsService.create(request, TestFixtures.USER_ID);

        assertThat(result.getTestId()).isEqualTo(TestFixtures.TEST_ID);
        assertThat(result.getCourseId()).isEqualTo(TestFixtures.COURSE_ID);
        assertThat(result.getTitle()).isEqualTo("Math test");
        assertThat(result.getAmountQuestions()).isEqualTo(TestAmountQuestions.MEDIUM);
        assertThat(result.getStatusTest()).isEqualTo(TestStatus.CREATED);
        assertThat(result.getDifficulty()).isEqualTo(TestDifficulty.MEDIUM);
        assertThat(result.getCreatedAt()).isNotNull();

        verify(courseService).getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<MaterialsTest>> linksCaptor = ArgumentCaptor.forClass(List.class);
        verify(materialsTestRepository).saveAll(linksCaptor.capture());
        assertThat(linksCaptor.getValue()).hasSize(1);
        MaterialsTest link = linksCaptor.getValue().get(0);
        assertThat(link.getId().getTestId()).isEqualTo(TestFixtures.TEST_ID);
        assertThat(link.getId().getMaterialId()).isEqualTo(TestFixtures.MATERIAL_ID);

        ArgumentCaptor<CreateTestRedisRequest> redisCaptor =
                ArgumentCaptor.forClass(CreateTestRedisRequest.class);
        verify(redisProducer).publishCreateTest(redisCaptor.capture());
        CreateTestRedisRequest published = redisCaptor.getValue();
        assertThat(published.getTaskId()).isNotNull();
        assertThat(published.getTestId()).isEqualTo(TestFixtures.TEST_ID);
        assertThat(published.getMaterialIds()).containsExactly(TestFixtures.MATERIAL_ID);
        assertThat(published.getTitle()).isEqualTo("Math test");
        assertThat(published.getAmountQuestions()).isEqualTo(TestAmountQuestions.MEDIUM);
        assertThat(published.getDifficulty()).isEqualTo("medium");
        assertThat(published.getCourseId()).isEqualTo(TestFixtures.COURSE_ID);
    }

    @Test
    void create_nullDifficulty_defaultsToMedium() {
        CreateTestRequest request = TestFixtures.createTestRequest();
        request.setDifficulty(null);
        stubCourseAccess();
        stubSaveAssignsId();

        com.examassistant.tests.entity.Test result =
                testsService.create(request, TestFixtures.USER_ID);

        assertThat(result.getDifficulty()).isEqualTo(TestDifficulty.MEDIUM);

        ArgumentCaptor<CreateTestRedisRequest> captor =
                ArgumentCaptor.forClass(CreateTestRedisRequest.class);
        verify(redisProducer).publishCreateTest(captor.capture());
        assertThat(captor.getValue().getDifficulty()).isEqualTo("medium");
    }

    @Test
    void getById_found_checksCourseAccessAndReturnsTest() {
        com.examassistant.tests.entity.Test test = TestFixtures.test();
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));
        stubCourseAccess();

        com.examassistant.tests.entity.Test result =
                testsService.getById(TestFixtures.TEST_ID, TestFixtures.USER_ID);

        assertThat(result).isSameAs(test);
        verify(courseService).getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID);
    }

    @Test
    void getById_notFound_throws() {
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> testsService.getById(TestFixtures.TEST_ID, TestFixtures.USER_ID))
                .isInstanceOf(TestNotFoundException.class)
                .hasMessage(TestFixtures.TEST_ID.toString());

        verifyNoInteractions(courseService);
    }

    @Test
    void getById_courseAccessDenied_propagatesException() {
        com.examassistant.tests.entity.Test test = TestFixtures.test();
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));
        when(courseService.getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID))
                .thenThrow(new CourseForbiddenException("This course is not yours"));

        assertThatThrownBy(() -> testsService.getById(TestFixtures.TEST_ID, TestFixtures.USER_ID))
                .isInstanceOf(CourseForbiddenException.class)
                .hasMessage("This course is not yours");
    }

    @Test
    void getDTOById_delegatesToMapper() {
        com.examassistant.tests.entity.Test test = TestFixtures.test();
        TestDTO dto = new TestDTO(
                TestFixtures.TEST_ID,
                TestFixtures.COURSE_ID,
                "Math test",
                TestAmountQuestions.MEDIUM,
                TestFixtures.CREATED_AT,
                TestStatus.CREATED,
                TestDifficulty.MEDIUM
        );
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));
        stubCourseAccess();
        when(testMapper.toDTO(test)).thenReturn(dto);

        TestDTO result = testsService.getDTOById(TestFixtures.TEST_ID, TestFixtures.USER_ID);

        assertThat(result).isSameAs(dto);
        verify(testMapper).toDTO(test);
    }

    @Test
    void search_invalidSortField_throwsWithoutRepositoryCall() {
        Pageable pageable = PageRequest.of(0, 10, Sort.by("unknown"));

        assertThatThrownBy(() -> testsService.search(new TestFilter(), pageable, TestFixtures.USER_ID))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("unknown");

        verifyNoInteractions(testRepository, courseService);
    }

    @Test
    void search_byCourse_checksAccessAndUsesCourseQuery() {
        TestFilter filter = new TestFilter();
        filter.setCourseId(TestFixtures.COURSE_ID);
        filter.setStatusTest(TestStatus.CREATED);
        Pageable pageable = PageRequest.of(0, 10);
        Page<com.examassistant.tests.entity.Test> page =
                new PageImpl<>(List.of(TestFixtures.test()));
        stubCourseAccess();
        when(testRepository.findByCourseIdAndStatusTest(
                TestFixtures.COURSE_ID, TestStatus.CREATED, pageable)).thenReturn(page);

        Page<com.examassistant.tests.entity.Test> result =
                testsService.search(filter, pageable, TestFixtures.USER_ID);

        assertThat(result).isSameAs(page);
        verify(courseService).getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID);
        verify(testRepository).findByCourseIdAndStatusTest(
                TestFixtures.COURSE_ID, TestStatus.CREATED, pageable);
    }

    @Test
    void search_nullFilter_usesOwnerQuery() {
        Pageable pageable = PageRequest.of(0, 10);
        Page<com.examassistant.tests.entity.Test> page =
                new PageImpl<>(List.of(TestFixtures.test()));
        when(testRepository.findByCourseOwnerId(TestFixtures.USER_ID, null, pageable))
                .thenReturn(page);

        Page<com.examassistant.tests.entity.Test> result =
                testsService.search(null, pageable, TestFixtures.USER_ID);

        assertThat(result).isSameAs(page);
        verify(testRepository).findByCourseOwnerId(TestFixtures.USER_ID, null, pageable);
        verifyNoInteractions(courseService);
    }

    @Test
    void search_statusOnly_usesOwnerQueryWithStatus() {
        TestFilter filter = new TestFilter();
        filter.setStatusTest(TestStatus.CREATED);
        Pageable pageable = PageRequest.of(0, 10);
        Page<com.examassistant.tests.entity.Test> page =
                new PageImpl<>(List.of(TestFixtures.test()));
        when(testRepository.findByCourseOwnerId(
                TestFixtures.USER_ID, TestStatus.CREATED, pageable)).thenReturn(page);

        Page<com.examassistant.tests.entity.Test> result =
                testsService.search(filter, pageable, TestFixtures.USER_ID);

        assertThat(result).isSameAs(page);
        verify(testRepository).findByCourseOwnerId(
                TestFixtures.USER_ID, TestStatus.CREATED, pageable);
        verifyNoInteractions(courseService);
    }

    @Test
    void delete_found_checksAccessAndDeletes() {
        com.examassistant.tests.entity.Test test = TestFixtures.test();
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.of(test));
        stubCourseAccess();

        testsService.delete(TestFixtures.TEST_ID, TestFixtures.USER_ID);

        verify(courseService).getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID);
        verify(testRepository).delete(test);
    }

    @Test
    void delete_notFound_throwsAndDoesNotDelete() {
        when(testRepository.findById(TestFixtures.TEST_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> testsService.delete(TestFixtures.TEST_ID, TestFixtures.USER_ID))
                .isInstanceOf(TestNotFoundException.class)
                .hasMessage(TestFixtures.TEST_ID.toString());

        verify(testRepository, never()).delete(any());
        verifyNoInteractions(courseService);
    }

    @Test
    void saveMaterialsTest_mapsEveryMaterialToLink() {
        testsService.saveMaterialsTest(
                TestFixtures.TEST_ID,
                List.of(TestFixtures.MATERIAL_ID, TestFixtures.OTHER_MATERIAL_ID)
        );

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<MaterialsTest>> captor = ArgumentCaptor.forClass(List.class);
        verify(materialsTestRepository).saveAll(captor.capture());

        assertThat(captor.getValue()).hasSize(2);
        assertThat(captor.getValue())
                .extracting(link -> link.getId().getTestId())
                .containsOnly(TestFixtures.TEST_ID);
        assertThat(captor.getValue())
                .extracting(link -> link.getId().getMaterialId())
                .containsExactly(TestFixtures.MATERIAL_ID, TestFixtures.OTHER_MATERIAL_ID);
    }

    private void stubCourseAccess() {
        when(courseService.getDTOById(TestFixtures.COURSE_ID, TestFixtures.USER_ID))
                .thenReturn(TestFixtures.courseDto(TestFixtures.COURSE_ID, TestFixtures.USER_ID));
    }

    private void stubSaveAssignsId() {
        when(testRepository.save(any(com.examassistant.tests.entity.Test.class)))
                .thenAnswer(invocation -> {
                    com.examassistant.tests.entity.Test test = invocation.getArgument(0);
                    test.setTestId(TestFixtures.TEST_ID);
                    return test;
                });
    }
}
