package com.examassistant.messaging;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Data
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class StudentAnswerPayload {
    private Integer index;
    private List<Integer> indexes;
    private String text;

    public static StudentAnswerPayload single(int index) {
        return new StudentAnswerPayload(index, null, null);
    }

    public static StudentAnswerPayload multiple(List<Integer> indexes) {
        return new StudentAnswerPayload(null, indexes, null);
    }

    public static StudentAnswerPayload open(String text) {
        return new StudentAnswerPayload(null, null, text);
    }

    public Map<String, Object> toMap() {
        int variants = (index == null ? 0 : 1) + (indexes == null ? 0 : 1) + (text == null ? 0 : 1);
        if (variants != 1) {
            throw new IllegalArgumentException("Student answer must contain exactly one of index, indexes or text");
        }
        Map<String, Object> answer = new LinkedHashMap<>();
        if (index != null) {
            answer.put("index", index);
        } else if (indexes != null) {
            answer.put("indexes", List.copyOf(indexes));
        } else {
            answer.put("text", text);
        }
        return answer;
    }
}
