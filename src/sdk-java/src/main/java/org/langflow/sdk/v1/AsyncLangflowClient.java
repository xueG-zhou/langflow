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
 * all request and file helpers are dispatched on the configured executor.
 * Create one instance per application and close it during shutdown.</p>
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

    /** Creates an async-client builder for a complete Langflow base URL. */
    public static Builder builder(String baseUrl) { return new Builder(baseUrl); }

    /** Asynchronously lists flows using default pagination. */
    public CompletableFuture<List<Flow>> listFlows() { return async(delegate::listFlows); }
    /** Asynchronously fetches a flow by ID. */
    public CompletableFuture<Flow> getFlow(String id) { return async(() -> delegate.getFlow(id)); }
    /** Asynchronously creates a flow. */
    public CompletableFuture<Flow> createFlow(FlowCreate flow) { return async(() -> delegate.createFlow(flow)); }
    /** Asynchronously applies a partial flow update. */
    public CompletableFuture<Flow> updateFlow(String id, FlowUpdate update) {
        return async(() -> delegate.updateFlow(id, update));
    }
    /** Asynchronously creates or updates a stable-ID flow. */
    public CompletableFuture<UpsertResult> upsertFlow(String id, FlowCreate flow) {
        return async(() -> delegate.upsertFlow(id, flow));
    }
    /** Asynchronously deletes a flow. */
    public CompletableFuture<Void> deleteFlow(String id) { return async(() -> { delegate.deleteFlow(id); return null; }); }
    /** Runs a flow through OkHttp's native async API; cancellation cancels the call. */
    public CompletableFuture<RunResponse> runFlow(String id, RunRequest request) {
        return delegate.runBackground(id, request).future();
    }
    /** Convenience asynchronous run using chat defaults. */
    public CompletableFuture<RunResponse> run(String id, String inputValue) {
        return delegate.runBackground(id, inputValue).future();
    }
    /** Returns a cancellable job handle for a v1 run. */
    public BackgroundJob runBackground(String id, String inputValue) {
        return delegate.runBackground(id, inputValue);
    }
    /** Opens a reactive SSE stream; cancellation closes the network stream. */
    public java.util.concurrent.Flow.Publisher<StreamChunk> stream(String id, RunRequest request) {
        return delegate.stream(id, request);
    }
    /** Asynchronously lists projects visible to the API key. */
    public CompletableFuture<List<Project>> listProjects() { return async(delegate::listProjects); }
    /** Asynchronously fetches a project and its flows. */
    public CompletableFuture<ProjectWithFlows> getProject(String id) { return async(() -> delegate.getProject(id)); }
    /** Asynchronously creates a project. */
    public CompletableFuture<Project> createProject(ProjectCreate project) {
        return async(() -> delegate.createProject(project));
    }
    /** Asynchronously updates project metadata. */
    public CompletableFuture<Project> updateProject(String id, ProjectUpdate update) {
        return async(() -> delegate.updateProject(id, update));
    }
    /** Asynchronously deletes a project. */
    public CompletableFuture<Void> deleteProject(String id) {
        return async(() -> { delegate.deleteProject(id); return null; });
    }
    /** Asynchronously downloads and safely extracts a project archive. */
    public CompletableFuture<Map<String, byte[]>> downloadProject(String id) {
        return async(() -> delegate.downloadProject(id));
    }
    /** Asynchronously uploads a project archive. */
    public CompletableFuture<List<Flow>> uploadProject(byte[] zip) {
        return async(() -> delegate.uploadProject(zip));
    }
    /** Asynchronously pushes a local flow file. */
    public CompletableFuture<UpsertResult> push(Path path) { return async(() -> delegate.push(path)); }
    /** Asynchronously pulls, normalizes, and optionally writes a flow. */
    public CompletableFuture<com.fasterxml.jackson.databind.JsonNode> pull(String id, Path output) {
        return async(() -> delegate.pull(id, output));
    }
    /** Asynchronously pushes every JSON flow file in a directory. */
    public CompletableFuture<List<UpsertResult>> pushProject(Path directory) {
        return async(() -> delegate.pushProject(directory));
    }
    /** Asynchronously downloads and writes every flow in a project. */
    public CompletableFuture<Map<String, Path>> pullProject(String id, Path outputDirectory) {
        return async(() -> delegate.pullProject(id, outputDirectory));
    }

    private <T> CompletableFuture<T> async(Supplier<T> operation) {
        return CompletableFuture.supplyAsync(operation, executor);
    }

    /** Cancels calls owned by the delegated synchronous client. */
    @Override public void close() { delegate.close(); }

    /** Fluent async-client configuration, including the executor for blocking file helpers. */
    public static final class Builder {
        private final String baseUrl;
        private String apiKey;
        private java.time.Duration connectTimeout = java.time.Duration.ofSeconds(10);
        private java.time.Duration readTimeout = java.time.Duration.ofSeconds(60);
        private java.time.Duration writeTimeout = java.time.Duration.ofSeconds(60);
        private java.time.Duration callTimeout = java.time.Duration.ofSeconds(60);
        private Executor executor = ForkJoinPool.commonPool();
        private Builder(String baseUrl) { this.baseUrl = baseUrl; }
        /** Sets the optional x-api-key credential. */
        public Builder apiKey(String value) { this.apiKey = value; return this; }
        /** Applies one duration to all four HTTP timeout categories. */
        public Builder timeout(java.time.Duration value) {
            connectTimeout = value; readTimeout = value; writeTimeout = value; callTimeout = value;
            return this;
        }
        /** Sets the TCP connection timeout. */
        public Builder connectTimeout(java.time.Duration value) { connectTimeout = value; return this; }
        /** Sets the response read timeout. */
        public Builder readTimeout(java.time.Duration value) { readTimeout = value; return this; }
        /** Sets the request-body write timeout. */
        public Builder writeTimeout(java.time.Duration value) { writeTimeout = value; return this; }
        /** Sets the whole-call timeout. */
        public Builder callTimeout(java.time.Duration value) { callTimeout = value; return this; }
        /** Selects the executor used by CRUD and local file operations. */
        public Builder executor(Executor value) { this.executor = value; return this; }
        /** Creates the async facade and its underlying reusable HTTP client. */
        public AsyncLangflowClient build() { return new AsyncLangflowClient(this); }
    }
}
