package com.examassistant.messaging.service;

import com.examassistant.common.enums.TestAmountQuestions;
import com.examassistant.common.enums.TestDifficulty;
import com.examassistant.common.exception.TaskNotFoundException;
import com.examassistant.messaging.TaskDTO;
import com.examassistant.messaging.entity.QueryTask;
import com.examassistant.messaging.enums.StatusTask;
import com.examassistant.messaging.repository.TaskRepository;
import com.examassistant.support.TestFixtures;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class TasksServiceTest {

    @Mock
    private TaskRepository taskRepository;

    @InjectMocks
    private TasksService tasksService;

    @Test
    void create_mapsDtoToEntityAndSaves() {
        TaskDTO dto = TestFixtures.taskDto();

        tasksService.create(TestFixtures.TASK_ID, dto);

        ArgumentCaptor<QueryTask> captor = ArgumentCaptor.forClass(QueryTask.class);
        verify(taskRepository).save(captor.capture());
        QueryTask task = captor.getValue();

        assertThat(task.getTaskId()).isEqualTo(TestFixtures.TASK_ID);
        assertThat(task.getTestId()).isEqualTo(TestFixtures.TEST_ID);
        assertThat(task.getCourseId()).isEqualTo(TestFixtures.COURSE_ID);
        assertThat(task.getTitle()).isEqualTo("Math test");
        assertThat(task.getAmountQuestions()).isEqualTo(TestAmountQuestions.MEDIUM);
        assertThat(task.getDifficulty()).isEqualTo(TestDifficulty.MEDIUM);
        assertThat(task.getStatusTask()).isEqualTo(StatusTask.PROCESSING);
        assertThat(task.getCreatedAt()).isNotNull();
        assertThat(task.getFinishedAt()).isNull();
    }

    @Test
    void create_unknownDifficulty_throwsAndDoesNotSave() {
        TaskDTO dto = TestFixtures.taskDto();
        dto.setDifficulty("impossible");

        assertThatThrownBy(() -> tasksService.create(TestFixtures.TASK_ID, dto))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("impossible");

        verifyNoInteractions(taskRepository);
    }

    @Test
    void changeStatus_marksTaskFinished() {
        QueryTask task = TestFixtures.queryTask();
        when(taskRepository.findById(TestFixtures.TASK_ID)).thenReturn(Optional.of(task));

        tasksService.changeStatus(TestFixtures.TASK_ID);

        assertThat(task.getStatusTask()).isEqualTo(StatusTask.FINISHED);
        verify(taskRepository, never()).save(any());
    }

    @Test
    void changeStatus_taskNotFound_throws() {
        when(taskRepository.findById(TestFixtures.TASK_ID)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> tasksService.changeStatus(TestFixtures.TASK_ID))
                .isInstanceOf(TaskNotFoundException.class)
                .hasMessage("task not found");
    }
}
