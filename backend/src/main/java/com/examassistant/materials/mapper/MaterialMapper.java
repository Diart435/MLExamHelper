package com.examassistant.materials.mapper;

import com.examassistant.materials.DTO.MaterialResponse;
import com.examassistant.materials.entity.Material;
import com.examassistant.materials.enums.STATUS_MATERIAL;
import com.examassistant.materials.enums.TYPE_MATERIAL;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.Named;

@Mapper(componentModel = "spring")
public interface MaterialMapper {
    @Mapping(target = "sourceUri", ignore = true)
    @Mapping(target = "typeMaterial", source = "typeMaterial", qualifiedByName = "typeToString")
    @Mapping(target = "statusMaterial", source = "statusMaterial", qualifiedByName = "statusToString")
    MaterialResponse toDTO(Material material);

    @Named("statusToString")
    default String statusToString(STATUS_MATERIAL statusMaterial){
        return statusMaterial.name();
    }

    @Named("typeToString")
    default String typeToString(TYPE_MATERIAL typeMaterial) {
        return typeMaterial.name();
    }
}
