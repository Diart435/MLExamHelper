package com.examassistant.courses.repository;

import com.examassistant.courses.entity.Course;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface CourseRepository extends JpaRepository<Course, UUID>, JpaSpecificationExecutor<Course> {

    @Query("SELECT COUNT(c) > 0 FROM Course c WHERE c.ownerId = :ownerId AND c.title = :title")
    boolean existsByOwnerIdAndTitle(@Param("ownerId") UUID ownerId, @Param("title") String title);

    @Query("SELECT c FROM Course c WHERE " +
            "(:ownerId IS NULL OR c.ownerId = :ownerId) AND " +
            "(:title IS NULL OR LOWER(c.title) LIKE LOWER(CONCAT('%', :title, '%'))) AND " +
            "(:courseDescription IS NULL OR LOWER(c.courseDescription) LIKE LOWER(CONCAT('%', :courseDescription, '%')))")
    Page<Course> findByFilter(
            @Param("ownerId") UUID ownerId,
            @Param("title") String title,
            @Param("courseDescription") String courseDescription,
            Pageable pageable
    );
}