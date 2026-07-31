package org.langflow.sdk.v2;

import com.fasterxml.jackson.databind.JsonNode;
import okhttp3.OkHttpClient;
import okhttp3.Response;
import okhttp3.sse.EventSource;
import okhttp3.sse.EventSourceListener;
import okhttp3.sse.EventSources;
import org.langflow.sdk.HttpTransport;
import org.langflow.sdk.LangflowException;
import org.langflow.sdk.v2.model.V2Models.*;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.SubmissionPublisher;

/** Thread-safe client for the native /api/v2/workflows API. */
public final class LangflowClient implements AutoCloseable {
    private final HttpTransport http;
    private LangflowClient(Builder builder) {
        this.http = new HttpTransport(builder.baseUrl(), builder.apiKey, builder.connectTimeout,
                builder.readTimeout, builder.writeTimeout, builder.callTimeout, builder.httpClient);
    }

    public static Builder builder(String baseUrl) { return new Builder(baseUrl); }
    public static Builder builder(String host, int port) { return new Builder(host, port); }

    public WorkflowResult execute(WorkflowRequest request) {
        if (request.mode() == WorkflowMode.stream) {
            throw new IllegalArgumentException("Use stream(request) when mode is stream");
        }
        JsonNode node = http.send("POST", "/api/v2/workflows", request, JsonNode.class);
        return convert(node);
    }

    public java.util.concurrent.Flow.Publisher<StreamEvent> stream(WorkflowRequest request) {
        if (request.mode() != WorkflowMode.stream) {
            throw new IllegalArgumentException("Workflow request mode must be stream");
        }
        return openStream("/api/v2/workflows", request, null);
    }

    public java.util.concurrent.Flow.Publisher<StreamEvent> streamPublic(PublicWorkflowRequest request) {
        return openStream("/api/v2/workflows/public", request, null);
    }

    public WorkflowResult status(String jobId) {
        JsonNode node = http.send("GET", "/api/v2/workflows" + HttpTransport.query(Map.of("job_id", jobId)), null, JsonNode.class);
        return convert(node);
    }

    public WorkflowStopResponse stop(String jobId) {
        return http.send("POST", "/api/v2/workflows/stop", new WorkflowStopRequest(jobId), WorkflowStopResponse.class);
    }

    public List<PendingWorkflow> pending(String flowId) {
        return http.send("GET", "/api/v2/workflows/pending" + HttpTransport.query(Map.of("flow_id", flowId)),
                null, new com.fasterxml.jackson.core.type.TypeReference<>() {});
    }

    public WorkflowResumeResponse resume(String jobId, WorkflowResumeRequest request) {
        return http.send("POST", "/api/v2/workflows/" + jobId + "/resume", request, WorkflowResumeResponse.class);
    }

    public java.util.concurrent.Flow.Publisher<StreamEvent> events(String jobId) {
        return events(jobId, null);
    }

    public java.util.concurrent.Flow.Publisher<StreamEvent> events(String jobId, String lastEventId) {
        return openStream("/api/v2/workflows/" + jobId + "/events", null, lastEventId);
    }

    private java.util.concurrent.Flow.Publisher<StreamEvent> openStream(
            String path, Object body, String lastEventId) {
        var publisher = new SsePublisher();
        var requestBuilder = http.request(body == null ? "GET" : "POST", path, body, "text/event-stream").newBuilder();
        if (lastEventId != null && !lastEventId.isBlank()) requestBuilder.header("Last-Event-ID", lastEventId);
        EventSource source = EventSources.createFactory(http.client()).newEventSource(
                requestBuilder.build(),
                new EventSourceListener() {
                    @Override public void onEvent(EventSource source, String id, String type, String data) {
                        try {
                            JsonNode payload = data == null || data.isBlank()
                                    ? http.json.createObjectNode() : http.json.readTree(data);
                            publisher.submit(new StreamEvent(id, type == null ? "message" : type, payload));
                        } catch (Exception e) {
                            publisher.closeExceptionally(e);
                            source.cancel();
                        }
                    }

                    @Override public void onClosed(EventSource source) { publisher.close(); }

                    @Override public void onFailure(EventSource source, Throwable t, Response response) {
                        publisher.closeExceptionally(t == null
                                ? new LangflowException("V2 SSE connection failed", null) : t);
                    }
                });
        publisher.source = source;
        return publisher;
    }

    private WorkflowResult convert(JsonNode node) {
        try {
            return "job".equals(node.path("object").asText())
                    ? http.json.treeToValue(node, WorkflowJob.class)
                    : http.json.treeToValue(node, WorkflowResponse.class);
        } catch (Exception e) { throw new LangflowException("Invalid v2 workflow response", e); }
    }

    private static final class SsePublisher extends SubmissionPublisher<StreamEvent> {
        private volatile EventSource source;
        void cancelSource() { if (source != null) source.cancel(); }
    }

    @Override public void close() { http.client().dispatcher().cancelAll(); }

    public static final class Builder {
        private String baseUrl;
        private String scheme = "http";
        private String host;
        private Integer port;
        private String apiKey;
        private Duration connectTimeout = Duration.ofSeconds(10);
        private Duration readTimeout = Duration.ofSeconds(60);
        private Duration writeTimeout = Duration.ofSeconds(60);
        private Duration callTimeout = Duration.ofSeconds(60);
        private OkHttpClient httpClient;
        private Builder(String baseUrl) { this.baseUrl = baseUrl; }
        private Builder(String host, int port) { this.host = host; this.port = validatePort(port); }
        public Builder scheme(String value) { this.scheme = requireText(value, "scheme"); return this; }
        public Builder host(String value) { this.host = requireText(value, "host"); this.baseUrl = null; return this; }
        public Builder port(int value) { this.port = validatePort(value); this.baseUrl = null; return this; }
        public Builder apiKey(String value) { this.apiKey = value; return this; }
        public Builder timeout(Duration value) {
            Duration timeout = requirePositive(value, "timeout");
            this.connectTimeout = timeout; this.readTimeout = timeout;
            this.writeTimeout = timeout; this.callTimeout = timeout;
            return this;
        }
        public Builder connectTimeout(Duration value) { this.connectTimeout = requirePositive(value, "connectTimeout"); return this; }
        public Builder readTimeout(Duration value) { this.readTimeout = requirePositive(value, "readTimeout"); return this; }
        public Builder writeTimeout(Duration value) { this.writeTimeout = requirePositive(value, "writeTimeout"); return this; }
        public Builder callTimeout(Duration value) { this.callTimeout = requirePositive(value, "callTimeout"); return this; }
        public Builder httpClient(OkHttpClient value) { this.httpClient = value; return this; }
        public LangflowClient build() { return new LangflowClient(this); }
        private String baseUrl() {
            if (baseUrl != null && !baseUrl.isBlank()) return baseUrl;
            if (host == null || port == null) throw new IllegalStateException("baseUrl or host and port are required");
            return scheme + "://" + host + ":" + port;
        }
        private static int validatePort(int value) {
            if (value < 1 || value > 65535) throw new IllegalArgumentException("port must be between 1 and 65535");
            return value;
        }
        private static String requireText(String value, String name) {
            if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
            return value;
        }
        private static Duration requirePositive(Duration value, String name) {
            if (value == null || value.isZero() || value.isNegative())
                throw new IllegalArgumentException(name + " must be positive");
            return value;
        }
    }
}
