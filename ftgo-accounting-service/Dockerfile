FROM maven:3.9-eclipse-temurin-17 AS builder

WORKDIR /workspace

COPY pom.xml .
RUN mvn -q -DskipTests dependency:go-offline || true

COPY src ./src
RUN mvn -q -DskipTests package
RUN cp target/*.jar app.jar
RUN java -Djarmode=layertools -jar app.jar extract

FROM eclipse-temurin:17-jre-alpine AS runtime

RUN addgroup -S ftgo && adduser -S ftgo -G ftgo
USER ftgo

WORKDIR /app

COPY --from=builder --chown=ftgo:ftgo /workspace/dependencies/ ./
COPY --from=builder --chown=ftgo:ftgo /workspace/spring-boot-loader/ ./
COPY --from=builder --chown=ftgo:ftgo /workspace/snapshot-dependencies/ ./
COPY --from=builder --chown=ftgo:ftgo /workspace/application/ ./

EXPOSE 8080

ENV JAVA_OPTS="-XX:+UseContainerSupport \
               -XX:MaxRAMPercentage=75.0 \
               -XX:+UseG1GC \
               -Djava.security.egd=file:/dev/./urandom"

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS org.springframework.boot.loader.launch.JarLauncher"]
