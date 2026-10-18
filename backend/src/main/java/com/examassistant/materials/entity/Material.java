package com.examassistant.materials.entity;

import com.examassistant.materials.enums.STATUS_MATERIAL;
import com.examassistant.materials.enums.TYPE_MATERIAL;
import jakarta.persistence.*;
import lombok.*;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "materials")
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Material {
    @Id
    @Column(name = "material_id", nullable = false, updatable = false)
    private UUID materialId;

    @Column(name = "course_id", nullable = false)
    private UUID courseId;

    @Column(name = "type_material", nullable = false)
    @Enumerated(value = EnumType.STRING)
    private TYPE_MATERIAL typeMaterial;

    @Column(name = "title", nullable = false)
    private String title;

    @Column(name = "source_uri", nullable = false)
    private String sourceUri;

    @Column(name = "status_material", nullable = false)
    @Enumerated(value = EnumType.STRING)
    private STATUS_MATERIAL statusMaterial;

    @Column(name = "material_size", nullable = false)
    private long materialSize;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;
}
