package org.langflow.example.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;

@Validated
@ConfigurationProperties(prefix = "langflow")
public record LangflowProperties(
        @NotBlank String baseUrl,
        String apiKey,
        @NotNull @Valid Timeout timeout
) {
    public record Timeout(
            @NotNull Duration connect,
            @NotNull Duration read,
            @NotNull Duration write,
            @NotNull Duration call
    ) {}
}
