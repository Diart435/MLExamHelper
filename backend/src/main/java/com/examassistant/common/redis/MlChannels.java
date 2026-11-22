package com.examassistant.common.redis;

import java.util.List;

public final class MlChannels {
    public static final String INGEST = "ingest";
    public static final String CREATE_TEST = "create-test";
    public static final String GRADE_TEST = "grade-test";
    public static final String BE_TO_ML = "be-to-ml";
    public static final String ML_TO_BE = "ml-to-be";

    private MlChannels() {
    }

    public static String taskChannel(String slug) {
        return slug + ":" + BE_TO_ML;
    }

    public static String resultChannel(String slug) {
        return slug + ":" + ML_TO_BE;
    }

    public static List<String> resultChannels() {
        return List.of(resultChannel(INGEST), resultChannel(CREATE_TEST), resultChannel(GRADE_TEST));
    }
}
