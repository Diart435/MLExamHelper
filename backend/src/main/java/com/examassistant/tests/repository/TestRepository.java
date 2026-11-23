package com.examassistant.tests.repository;

import com.examassistant.tests.entity.Test;
import com.examassistant.tests.enums.TestStatus;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface TestRepository extends JpaRepository<Test, UUID> {

    // Блокировка строки теста: результат из ML применяется ровно один раз.
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT t FROM Test t WHERE t.testId = :testId")
    Optional<Test> findByIdForUpdate(@Param("testId") UUID testId);

    @Query("SELECT t FROM Test t WHERE (:courseId IS NULL OR t.courseId = :courseId) AND (:statusTest IS NULL OR t.statusTest = :statusTest)")
    Page<Test> findByCourseIdAndStatusTest(@Param("courseId") UUID courseId, @Param("statusTest") TestStatus statusTest, Pageable pageable);

    @Query("SELECT t FROM Test t JOIN Course c ON t.courseId = c.courseId WHERE c.ownerId = :userId AND (:statusTest IS NULL OR t.statusTest = :statusTest)")
    Page<Test> findByCourseOwnerId(@Param("userId") UUID userId, @Param("statusTest") TestStatus statusTest, Pageable pageable);
}