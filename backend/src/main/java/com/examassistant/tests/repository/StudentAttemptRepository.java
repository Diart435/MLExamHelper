package com.examassistant.tests.repository;

import com.examassistant.tests.entity.StudentAttempt;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.UUID;

public interface StudentAttemptRepository extends JpaRepository<StudentAttempt, UUID> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT a FROM StudentAttempt a WHERE a.attemptId = :attemptId")
    Optional<StudentAttempt> findByIdForUpdate(@Param("attemptId") UUID attemptId);
}
