
package com.examassistant.auth.DTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class VkUserInfoResponse {

    private VkUser user;

    @Data
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class VkUser {
        @JsonProperty("user_id")    private Long    userId;
        @JsonProperty("first_name") private String  firstName;
        @JsonProperty("last_name")  private String  lastName;
        private String  email;      // может быть null!
        private String  phone;
        private String  avatar;
        private Integer sex;
        private Boolean verified;
        private String  birthday;
    }
}