package org.langflow.sdk.v1;

import org.langflow.sdk.v1.model.V1Models.*;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ForkJoinPool;
import java.util.function.Supplier;

/**
 * CompletableFuture facade mirroring the Python AsyncLangflowClient surface.
 *
 * <p>Streaming remains a reactive {@link java.util.concurrent.Flow.Publisher};
 * all request and file helpers are dispatched on the configured executor.</p>
 */
public final class AsyncLangflowClient implements AutoCloseable {
    private final LangflowClient delegate;
    private final Executor executor;

    private AsyncLangflowClient(Builder builder) {
        var sync = LangflowClient.builder(builder.baseUrl).apiKey(builder.apiKey)
                .connectTimeout(builder.connectTimeout).readTimeout(builder.readTimeout)
                .writeTimeout(builder.writeTimeout).callTimeout(builder.callTimeout);
        this.delegate = sync.build();
        this.executor = builder.executor;
    }

    public static Builder builder(String baseUrl) { return new Builder(baseUrl); }

    public CompletableFuture<List<Flow>> listFlows() { return async(delegate::listFlows); }
    public CompletableFuture<Flow> getFlow(String id) { return async(() -> delegate.getFlow(id)); }
    public CompletableFuture<Flow> createFlow(FlowCreate flow) { return async(() -> delegate.createFlow(flow)); }
    public CompletableFuture<Flow> updateFlow(String id, FlowUpdate update) {
        return async(() -> delegate.updateFlow(id, update));
    }
    public CompletableFuture<UpsertResult> upsertFlow(String id, FlowCreate flow) {
        return async(() -> delegate.upsertFlow(id, flow));
    }
    public CompletableFuture<Void> deleteFlow(String id) { return async(() -> { delegate.deleteFlow(id); return null; }); }
    public CompletableFuture<RunResponse> runFlow(String id, RunRequest request) {
        return delegate.runBackground(id, request).future();
    }
    public CompletableFuture<RunResponse> run(String id, String inputValue) {
        return delegate.runBackground(id, inputValue).future();
    }
    public BackgroundJob runBackground(String id, String inputValue) {
        return delegate.runBackground(id, inputValue);
    }
    public java.util.concurrent.Flow.Publisher<StreamChunk> stream(String id, RunRequest request) {
        return delegate.stream(id, request);
    }
    public CompletableFuture<List<Project>> listProjects() { return async(delegate::listProjects); }
    public CompletableFuture<ProjectWithFlows> getProject(String id) { return async(() -> delegate.getProject(id)); }
    public CompletableFuture<Project> createProject(ProjectCreate project) {
        return async(() -> delegate.createProject(project));
    }
    public CompletableFuture<Project> updateProject(String id, ProjectUpdate update) {
        return async(() -> delegate.updateProject(id, update));
    }
    public CompletableFuture<Void> deleteProject(String id) {
        return async(() -> { delegate.deleteProject(id); return null; });
    }
    public CompletableFuture<Map<String, byte[]>> downloadProject(String id) {
        return async(() -> delegate.downloadProject(id));
    }
    public CompletableFuture<List<Flow>> uploadProject(byte[] zip) {
        return async(() -> delegate.uploadProject(zip));
    }
    public CompletableFuture<UpsertResult> push(Path path) { return async(() -> delegate.push(path)); }
    public CompletableFuture<com.fasterxml.jackson.databind.JsonNode> pull(String id, Path output) {
        return async(() -> delegate.pull(id, output));
    }
    public CompletableFuture<List<UpsertResult>> pushProject(Path directory) {
        return async(() -> delegate.pushProject(directory));
    }
    public CompletableFuture<Map<String, Path>> pullProject(String id, Path outputDirectory) {
        return async(() -> delegate.pullProject(id, outputDirectory));
    }

    private <T> CompletableFuture<T> async(Supplier<T> operation) {
        return CompletableFuture.supplyAsync(operation, executor);
    }

    @Override public void close() { delegate.close(); }

    public static final class Builder {
        private final String baseUrl;
        private String apiKey;
        private java.time.Duration connectTimeout = java.time.Duration.ofSeconds(10);
        private java.time.Duration readTimeout = java.time.Duration.ofSeconds(60);
        private java.time.Duration writeTimeout = java.time.Duration.ofSeconds(60);
        private java.time.Duration callTimeout = java.time.Duration.ofSeconds(60);
        private Executor executor = ForkJoinPool.commonPool();
        private Builder(String baseUrl) { this.baseUrl = baseUrl; }
        public Builder apiKey(String value) { this.apiKey = value; return this; }
        public Builder timeout(java.time.Duration value) {
            connectTimeout = value; readTimeout = value; writeTimeout = value; callTimeout = value;
            return this;
        }
        public Builder connectTimeout(java.time.Duration value) { connectTimeout = value; return this; }
        public Builder readTimeout(java.time.Duration value) { readTimeout = value; return this; }
        public Builder writeTimeout(java.time.Duration value) { writeTimeout = value; return this; }
        public Builder callTimeout(java.time.Duration value) { callTimeout = value; return this; }
        public Builder executor(Executor value) { this.executor = value; return this; }
        public AsyncLangflowClient build() { return new AsyncLangflowClient(this); }
    }
}
