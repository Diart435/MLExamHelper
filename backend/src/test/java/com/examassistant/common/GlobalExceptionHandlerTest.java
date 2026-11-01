package com.examassistant.common;

import com.examassistant.common.DTO.ApiError;
import com.examassistant.common.exception.CourseForbiddenException;
import com.examassistant.common.exception.CourseNotFoundException;
import com.examassistant.common.exception.FileForbiddenException;
import com.examassistant.common.exception.FileNotFoundException;
import com.examassistant.common.exception.FileUploadException;
import com.examassistant.common.exception.InvalidCredentialsException;
import com.examassistant.common.exception.InvalidTokenException;
import com.examassistant.common.exception.UserAlreadyExistException;
import com.examassistant.common.exception.UserNotFoundException;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import org.junit.jupiter.api.Test;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.context.request.ServletWebRequest;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;

import java.lang.reflect.Method;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class GlobalExceptionHandlerTest {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @Test
    void illegalArgument_returns400() {
        ResponseEntity<ApiError> response = handler.handleBadRequest(
                new IllegalArgumentException("bad request"), request("/api/test"));

        assertApiError(response, HttpStatus.BAD_REQUEST, "bad request", "/api/test");
    }

    @Test
    void fileUploadException_returns400() {
        ResponseEntity<ApiError> response = handler.handleFileUploadException(
                new FileUploadException("File is empty"), request("/api/materials/upload"));

        assertApiError(response, HttpStatus.BAD_REQUEST, "File is empty", "/api/materials/upload");
    }

    @Test
    void validationException_returns400WithJoinedMessages() throws Exception {
        BeanPropertyBindingResult bindingResult =
                new BeanPropertyBindingResult(new Object(), "request");
        bindingResult.addError(new FieldError("request", "email", "Email is required"));
        bindingResult.addError(new FieldError("request", "password", "Password is required"));
        Method method = GlobalExceptionHandlerTest.class.getDeclaredMethod("dummy", String.class);
        MethodArgumentNotValidException exception =
                new MethodArgumentNotValidException(new MethodParameter(method, 0), bindingResult);

        ResponseEntity<ApiError> response = handler.handleValidation(
                exception, request("/api/auth/register"));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getMessage())
                .contains("Email is required", "Password is required");
        assertThat(response.getBody().getPath()).isEqualTo("/api/auth/register");
    }

    @Test
    void typeMismatch_returns400WithUuidMessage() throws Exception {
        Method method = GlobalExceptionHandlerTest.class.getDeclaredMethod("dummy", UUID.class);
        MethodArgumentTypeMismatchException exception = new MethodArgumentTypeMismatchException(
                "bad-id",
                UUID.class,
                "id",
                new MethodParameter(method, 0),
                new IllegalArgumentException("bad-id")
        );

        ResponseEntity<ApiError> response = handler.handleTypeMismatch(
                exception, request("/api/courses/bad-id"));

        assertApiError(response, HttpStatus.BAD_REQUEST,
                "Invalid ID format. Must be a UUID", "/api/courses/bad-id");
    }

    @Test
    void missingParameter_returns400WithParameterName() {
        ResponseEntity<ApiError> response = handler.handleMissingParam(
                new MissingServletRequestParameterException("courseId", "UUID"),
                request("/api/materials"));

        assertApiError(response, HttpStatus.BAD_REQUEST,
                "Required parameter 'courseId' is missing", "/api/materials");
    }

    @Test
    void missingMultipartPart_returns400() {
        ResponseEntity<ApiError> response = handler.handleMissingPart(
                new MissingServletRequestPartException("file"),
                request("/api/materials/upload"));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getMessage()).contains("file");
    }

    @Test
    void userAlreadyExists_returns409() {
        ResponseEntity<ApiError> response = handler.handleConflict(
                new UserAlreadyExistException("User already exists"), request("/api/auth/register"));

        assertApiError(response, HttpStatus.CONFLICT,
                "User already exists", "/api/auth/register");
    }

    @Test
    void fileForbidden_returns403() {
        ResponseEntity<ApiError> response = handler.handleForbidden(
                new FileForbiddenException("This file is not yours"), request("/api/materials/1"));

        assertApiError(response, HttpStatus.FORBIDDEN,
                "This file is not yours", "/api/materials/1");
    }

    @Test
    void courseForbidden_returns403() {
        ResponseEntity<ApiError> response = handler.handleForbidden(
                new CourseForbiddenException("This course is not yours"), request("/api/courses/1"));

        assertApiError(response, HttpStatus.FORBIDDEN,
                "This course is not yours", "/api/courses/1");
    }

    @Test
    void userNotFound_returns404() {
        ResponseEntity<ApiError> response = handler.handleNotFound(
                new UserNotFoundException("User not found"), request("/api/user/me"));

        assertApiError(response, HttpStatus.NOT_FOUND, "User not found", "/api/user/me");
    }

    @Test
    void fileNotFound_returns404() {
        ResponseEntity<ApiError> response = handler.handleNotFound(
                new FileNotFoundException("Invalid file id"), request("/api/materials/1"));

        assertApiError(response, HttpStatus.NOT_FOUND, "Invalid file id", "/api/materials/1");
    }

    @Test
    void courseNotFound_returns404() {
        ResponseEntity<ApiError> response = handler.handleCourseNotFound(
                new CourseNotFoundException("Course not found"), request("/api/courses/1"));

        assertApiError(response, HttpStatus.NOT_FOUND, "Course not found", "/api/courses/1");
    }

    @Test
    void invalidToken_returns401() {
        ResponseEntity<ApiError> response = handler.handleInvalidToken(
                new InvalidTokenException("Token is invalid"), request("/api/auth/refresh"));

        assertApiError(response, HttpStatus.UNAUTHORIZED,
                "Token is invalid", "/api/auth/refresh");
    }

    @Test
    void invalidCredentials_returns401() {
        ResponseEntity<ApiError> response = handler.handleInvalidToken(
                new InvalidCredentialsException("Password is incorrect"), request("/api/auth/login"));

        assertApiError(response, HttpStatus.UNAUTHORIZED,
                "Password is incorrect", "/api/auth/login");
    }

    @Test
    void genericException_returns500() {
        ResponseEntity<ApiError> response = handler.handleGeneric(
                new RuntimeException("boom"), request("/api/test"));

        assertApiError(response, HttpStatus.INTERNAL_SERVER_ERROR, "boom", "/api/test");
    }

    @Test
    void constraintViolation_returns400WithJoinedMessages() {
        Validator validator = Validation.buildDefaultValidatorFactory().getValidator();
        Set<ConstraintViolation<ValidatedPayload>> violations =
                validator.validate(new ValidatedPayload());
        ConstraintViolationException exception = new ConstraintViolationException(violations);

        ResponseEntity<ApiError> response = handler.handleConstraintViolation(
                exception, request("/api/test"));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getMessage()).contains("name required");
    }

    private WebRequest request(String path) {
        return new ServletWebRequest(new MockHttpServletRequest("GET", path));
    }

    private void assertApiError(
            ResponseEntity<ApiError> response,
            HttpStatus status,
            String message,
            String path
    ) {
        assertThat(response.getStatusCode()).isEqualTo(status);
        ApiError body = response.getBody();
        assertThat(body).isNotNull();
        assertThat(body.getTimestamp()).isNotNull();
        assertThat(body.getStatus()).isEqualTo(status.value());
        assertThat(body.getError()).isEqualTo(status.getReasonPhrase());
        assertThat(body.getMessage()).isEqualTo(message);
        assertThat(body.getPath()).isEqualTo(path);
    }

    @SuppressWarnings("unused")
    private void dummy(UUID id) {
    }

    @SuppressWarnings("unused")
    private void dummy(String value) {
    }

    private static class ValidatedPayload {
        @NotBlank(message = "name required")
        private String name;
    }
}
