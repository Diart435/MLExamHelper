package com.examassistant.common.exception;

public class CourseForbiddenException extends RuntimeException{
    public CourseForbiddenException(String message){
        super(message);
    }
}
