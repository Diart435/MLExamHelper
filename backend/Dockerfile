FROM maven:3.9.9-eclipse-temurin-21 AS builder

WORKDIR /build

COPY . .

RUN --mount=type=cache,target=/root/.m2,sharing=locked \
    mvn clean package -Pprod


FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

COPY --from=builder /build/backend/target/*.jar /app/app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]