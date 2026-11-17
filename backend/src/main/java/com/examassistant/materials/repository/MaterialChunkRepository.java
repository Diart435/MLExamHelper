package com.examassistant.materials.repository;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

/**
 * Проверка существования чанка в material_chunks.
 *
 * Таблицу material_chunks наполняет ML (PgVectorStore), сущности на неё в
 * backend нет: вектор — это не то, с чем работает JPA. Нужен только факт
 * существования: source_chunk_id — внешний ключ, и несуществующий чанк должен
 * превращаться в NULL, а не ронять вставку вопроса.
 */
@Repository
@RequiredArgsConstructor
public class MaterialChunkRepository {

    private final JdbcTemplate jdbcTemplate;

    public boolean existsById(UUID chunkId) {
        List<Integer> found = jdbcTemplate.query(
                "SELECT 1 FROM material_chunks WHERE chunk_id = ?",
                (rs, rowNum) -> rs.getInt(1),
                chunkId);
        return !found.isEmpty();
    }
}
