package com.examassistant.tests.entity;

import com.examassistant.tests.enums.QuestionType;
import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Entity
@NoArgsConstructor
@Setter
@Getter
@Builder
@AllArgsConstructor
@Table(name = "test_questions")
public class Question {
    @Id
    @Column(name = "question_id")
    private UUID questionId;

    @Column(name = "test_id", nullable = false)
    private UUID testId;

    /**
     * Порядок вопроса в тесте (порядок генерации ML). В схеме заказчика такой
     * колонки нет, но без неё вопросы выдаются в случайном порядке (ORDER BY
     * question_id — это порядок случайных UUID).
     */
    @Column(name = "question_order", nullable = false)
    private int questionOrder;

    @Enumerated(EnumType.STRING)
    @Column(name = "type_question", nullable = false)
    private QuestionType typeQuestion;

    @Column(name = "text_question", nullable = false)
    private String textQuestion;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", name = "options")
    private List<String> options;

    /**
     * Эталон правильного ответа as-is из ответа ML:
     * single_choice → {correct_index, explanation}, multi_choice → {correct_indexes[], explanation},
     * open_answer → {reference_answer, explanation}.
     */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", name = "answer_key")
    private Map<String, Object> answerKey;

    /**
     * Опорные пункты для open_answer (плоский список строк), у закрытых типов — пустой список.
     */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", name = "key_points")
    private List<String> keyPoints;

    @Column(name = "source_chunk_id")
    private UUID sourceChunkId;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;
}
