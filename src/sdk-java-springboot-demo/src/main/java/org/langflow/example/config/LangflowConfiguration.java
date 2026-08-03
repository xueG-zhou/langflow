package org.langflow.example.config;

import org.langflow.sdk.v1.AsyncLangflowClient;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(LangflowProperties.class)
public class LangflowConfiguration {
    @Bean(destroyMethod = "close")
    org.langflow.sdk.v1.LangflowClient langflowV1Client(LangflowProperties properties) {
        var timeout = properties.timeout();
        return org.langflow.sdk.v1.LangflowClient.builder(properties.baseUrl())
                .apiKey(properties.apiKey())
                .connectTimeout(timeout.connect()).readTimeout(timeout.read())
                .writeTimeout(timeout.write()).callTimeout(timeout.call()).build();
    }

    @Bean(destroyMethod = "close")
    AsyncLangflowClient asyncLangflowV1Client(LangflowProperties properties) {
        var timeout = properties.timeout();
        return AsyncLangflowClient.builder(properties.baseUrl())
                .apiKey(properties.apiKey())
                .connectTimeout(timeout.connect()).readTimeout(timeout.read())
                .writeTimeout(timeout.write()).callTimeout(timeout.call()).build();
    }

    @Bean(destroyMethod = "close")
    org.langflow.sdk.v2.LangflowClient langflowV2Client(LangflowProperties properties) {
        var timeout = properties.timeout();
        return org.langflow.sdk.v2.LangflowClient.builder(properties.baseUrl())
                .apiKey(properties.apiKey())
                .connectTimeout(timeout.connect()).readTimeout(timeout.read())
                .writeTimeout(timeout.write()).callTimeout(timeout.call()).build();
    }
}
