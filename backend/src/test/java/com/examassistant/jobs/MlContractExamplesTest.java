package com.examassistant.jobs;

import com.examassistant.jobs.DTO.CreateTestResultMessage;
import com.examassistant.jobs.DTO.GradeItemMessage;
import com.examassistant.jobs.DTO.GradeTestResultMessage;
import com.examassistant.jobs.DTO.IngestResultMessage;
import com.examassistant.jobs.DTO.QuestionDataMessage;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Контракт ML ↔ backend: канонические примеры payload'ов из
 * `ml/docs/contracts/examples/` должны разбираться DTO'ами backend'а без потерь.
 *
 * Примеры — источник правды на стороне ML (их генерирует `app/contracts.py`,
 * актуальность следит `ml/tests/test_contract_schema.py`). Тест ловит рассинхрон:
 * ML прислал `correct_answer` строкой, а backend ждёт объект, — вердикт молча
 * потерялся бы, и никакой unit-тест на стороне backend'а это не показал бы.
 *
 * Каталог с примерами можно переопределить системным свойством
 * `ml.contracts.examples.dir`; если его нет — тест пропускается, чтобы сборка
 * backend'а не зависела от наличия папки `ml/`.
 */
class MlContractExamplesTest {

    private static final Path EXAMPLES_DIR = Path.of(
            System.getProperty("ml.contracts.examples.dir", "../ml/docs/contracts/examples"));

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void ingestResult_isParsed() {
        String payload = readExample("ingest-ml-to-be.json");
        IngestResultMessage message = mapper.readValue(payload, IngestResultMessage.class);

        assertThat(message.getMaterialId()).isNotNull();
        assertThat(message.getStatus()).isEqualTo("ready");
        assertThat(message.getError()).isNull();
    }

    @Test
    void createTestResult_isParsedWithNestedAnswerKeyAndKeyPoints() {
        String payload = readExample("create-test-ml-to-be.json");
        CreateTestResultMessage message = mapper.readValue(payload, CreateTestResultMessage.class);

        assertThat(message.getStatus()).isEqualTo("ok");
        assertThat(message.getTaskId()).isNotNull();
        assertThat(message.getTestId()).isNotNull();
        assertThat(message.getTest()).isNotNull();
        List<QuestionDataMessage> questions = message.getTest().getQuestions();
        assertThat(questions).isNotEmpty();

        for (QuestionDataMessage question : questions) {
            assertThat(question.getId()).isNotNull();
            assertThat(question.getType()).isIn("single_choice", "multi_choice", "open_answer");
            assertThat(question.getText()).isNotBlank();
            assertThat(question.getAnswerKey()).isNotEmpty();
            // `key_points` — плоский список строк, а не объект: иначе Hibernate
            // не сможет положить его в jsonb-колонку, а ML потеряет критерии
            // для open_answer.
            assertThat(question.getKeyPoints()).isNotNull();
        }

        QuestionDataMessage open = questions.stream()
                .filter(question -> "open_answer".equals(question.getType()))
                .findFirst()
                .orElseThrow();
        assertThat(open.getOptions()).isNullOrEmpty();
        assertThat(open.getKeyPoints()).isNotEmpty();
        assertThat(open.getAnswerKey()).containsKey("reference_answer");
    }

    @Test
    void gradeTestResult_hasNoStatusFieldAndObjectsInsteadOfStrings() {
        String payload = readExample("grade-test-ml-to-be.json");

        // Контракт v4.1: в grade-ответе поля `status` нет — признак ошибки
        // это наличие ключа `error`. Если backend начнёт ждать `status`, вердикт
        // будет отвергнут как ошибка.
        JsonNode root = mapper.readTree(payload);
        assertThat(root.has("status")).isFalse();

        GradeTestResultMessage message = mapper.readValue(payload, GradeTestResultMessage.class);
        assertThat(message.getScorePct()).isNotNull();
        assertThat(message.getGrade()).isNotNull();
        assertThat(message.getItems()).isNotEmpty();

        for (GradeItemMessage item : message.getItems()) {
            assertThat(item.getQuestionId()).isNotNull();
            assertThat(item.getCorrect()).isNotNull();
            assertThat(item.getScore()).isNotNull();
            // Эталон — объект той же формы, что `answer_key` вопроса. Строкой
            // его быть не может: backend читает поле в Map<String, Object>.
            assertThat(item.getCorrectAnswer()).isInstanceOf(Map.class);
            assertThat(item.getCorrectAnswer()).isNotEmpty();
        }
    }

    private String readExample(String fileName) {
        Assumptions.assumeTrue(Files.isDirectory(EXAMPLES_DIR),
                "каталог с примерами контракта не найден: " + EXAMPLES_DIR.toAbsolutePath());
        Path path = EXAMPLES_DIR.resolve(fileName);
        Assumptions.assumeTrue(Files.exists(path), "нет примера: " + path.toAbsolutePath());
        try {
            return Files.readString(path);
        } catch (java.io.IOException e) {
            throw new IllegalStateException("не прочитан пример контракта: " + path, e);
        }
    }
}
