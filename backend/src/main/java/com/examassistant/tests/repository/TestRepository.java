package com.examassistant.tests.repository;

import com.examassistant.tests.entity.Test;
import com.examassistant.tests.enums.TestStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface TestRepository extends JpaRepository<Test, UUID> {

    @Query("SELECT t FROM Test t WHERE " +
            "(:courseId IS NULL OR t.courseId = :courseId) AND " +
            "(:statusTest IS NULL OR t.statusTest = :statusTest)")
    Page<Test> findByFilter(
            @Param("courseId") UUID courseId,
            @Param("statusTest") TestStatus statusTest,
            Pageable pageable
    );
}