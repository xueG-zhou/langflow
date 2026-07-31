package org.langflow.sdk.v1;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import okhttp3.OkHttpClient;
import okhttp3.Response;
import okhttp3.sse.EventSource;
import okhttp3.sse.EventSourceListener;
import okhttp3.sse.EventSources;
import org.langflow.sdk.HttpTransport;
import org.langflow.sdk.LangflowException;
import org.langflow.sdk.v1.model.V1Models.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Flow.Subscriber;
import java.util.concurrent.Flow.Subscription;
import java.util.concurrent.SubmissionPublisher;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Thread-safe client for Langflow API v1. */
public final class LangflowClient implements AutoCloseable {
    private static final Logger LOG = LoggerFactory.getLogger("org.langflow.sdk.sse");
    private static final int MAX_ZIP_ENTRIES = 500;
    private static final long MAX_ENTRY_BYTES = 50L * 1024 * 1024;
    private final HttpTransport http;

    private LangflowClient(Builder builder) {
        this.http = new HttpTransport(builder.baseUrl(), builder.apiKey, builder.connectTimeout,
                builder.readTimeout, builder.writeTimeout, builder.callTimeout, builder.httpClient);
    }

    public static Builder builder(String baseUrl) { return new Builder(baseUrl); }
    public static Builder builder(String host, int port) { return new Builder(host, port); }

    public List<Flow> listFlows() { return listFlows(null, false, false, false, false, 1, 50); }

    public List<Flow> listFlows(UUID folderId, boolean removeExamples, boolean componentsOnly,
                                boolean getAll, boolean headerFlows, int page, int size) {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("folder_id", folderId); params.put("remove_example_flows", removeExamples);
        params.put("components_only", componentsOnly); params.put("get_all", getAll);
        params.put("header_flows", headerFlows); params.put("page", page); params.put("size", size);
        return http.send("GET", "/api/v1/flows/" + HttpTransport.query(params), null, new TypeReference<>() {});
    }

    public Flow getFlow(String flowId) { return http.send("GET", "/api/v1/flows/" + flowId, null, Flow.class); }
    public Flow createFlow(FlowCreate flow) { return http.send("POST", "/api/v1/flows/", flow, Flow.class); }
    public Flow updateFlow(String flowId, FlowUpdate update) { return http.send("PATCH", "/api/v1/flows/" + flowId, update, Flow.class); }
    public UpsertResult upsertFlow(String flowId, FlowCreate flow) {
        var response = http.sendWithStatus("PUT", "/api/v1/flows/" + flowId, flow);
        try {
            return new UpsertResult(http.json.readValue(response.body(), Flow.class), response.statusCode() == 201);
        } catch (IOException e) {
            throw new LangflowException("Invalid Langflow response", e);
        }
    }
    public void deleteFlow(String flowId) { http.send("DELETE", "/api/v1/flows/" + flowId, null, Void.class); }
    public RunResponse runFlow(String idOrEndpoint, RunRequest request) {
        return http.send("POST", "/api/v1/run/" + idOrEndpoint, request, RunResponse.class);
    }
    public RunResponse run(String idOrEndpoint, String inputValue) { return runFlow(idOrEndpoint, new RunRequest(inputValue)); }
    public BackgroundJob runBackground(String idOrEndpoint, String inputValue) {
        return runBackground(idOrEndpoint, new RunRequest(inputValue));
    }
    public BackgroundJob runBackground(String idOrEndpoint, RunRequest request) {
        return new BackgroundJob(http.sendAsync("POST", "/api/v1/run/" + idOrEndpoint, request, RunResponse.class));
    }

    /** Starts an OkHttp SSE connection. Cancelling the subscription closes its EventSource. */
    public java.util.concurrent.Flow.Publisher<StreamChunk> stream(String idOrEndpoint, RunRequest request) {
        var publisher = new SsePublisher();
        var streamingRequest = new RunRequest(request.inputValue(), request.inputType(), request.outputType(), request.tweaks(), true);
        EventSource source = EventSources.createFactory(http.client()).newEventSource(
                http.request("POST", "/api/v1/run/" + idOrEndpoint, streamingRequest, "text/event-stream"),
                new EventSourceListener() {
                    @Override public void onEvent(EventSource source, String id, String type, String data) {
                        try {
                            JsonNode envelope = data == null || data.isBlank() ? http.json.createObjectNode() : http.json.readTree(data);
                            String event = envelope.has("event") ? envelope.path("event").asText() : (type == null ? "message" : type);
                            JsonNode payload = envelope.has("data") ? envelope.get("data") : envelope;
                            LOG.debug("Langflow SSE event received: flow={}, event={}, data={}", idOrEndpoint, event, payload);
                            publisher.submit(new StreamChunk(event, payload));
                        } catch (Exception e) { publisher.closeExceptionally(e); source.cancel(); }
                    }
                    @Override public void onClosed(EventSource source) {
                        LOG.debug("Langflow SSE stream closed: flow={}", idOrEndpoint);
                        publisher.close();
                    }
                    @Override public void onFailure(EventSource source, Throwable t, Response response) {
                        LOG.debug("Langflow SSE stream failed: flow={}, status={}, error={}", idOrEndpoint,
                                response == null ? null : response.code(), t == null ? null : t.toString());
                        publisher.closeExceptionally(t == null ? new LangflowException("SSE connection failed", null) : t);
                    }
                });
        publisher.setSource(source);
        return publisher;
    }

    public List<Project> listProjects() { return http.send("GET", "/api/v1/projects/", null, new TypeReference<>() {}); }
    public ProjectWithFlows getProject(String id) { return http.send("GET", "/api/v1/projects/" + id, null, ProjectWithFlows.class); }
    public Project createProject(ProjectCreate project) { return http.send("POST", "/api/v1/projects/", project, Project.class); }
    public Project updateProject(String id, ProjectUpdate update) { return http.send("PATCH", "/api/v1/projects/" + id, update, Project.class); }
    public void deleteProject(String id) { http.send("DELETE", "/api/v1/projects/" + id, null, Void.class); }

    public Map<String, byte[]> downloadProject(String id) {
        return extractProjectArchive(http.download("/api/v1/projects/download/" + id));
    }

    public List<Flow> uploadProject(byte[] zipBytes) {
        return http.upload("/api/v1/projects/upload/", zipBytes, new TypeReference<>() {});
    }

    public UpsertResult push(Path path) {
        try {
            JsonNode raw = http.json.readTree(path.toFile());
            JsonNode id = raw.get("id");
            if (id == null || id.asText().isBlank()) {
                throw new IllegalArgumentException("Flow file '" + path + "' does not contain an 'id' field; cannot upsert");
            }
            var payload = (com.fasterxml.jackson.databind.node.ObjectNode) raw.deepCopy();
            payload.remove("id");
            return upsertFlow(id.asText(), http.json.treeToValue(payload, FlowCreate.class));
        } catch (IOException e) {
            throw new LangflowException("Unable to read flow file " + path, e);
        }
    }

    public JsonNode pull(String flowId) { return pull(flowId, null); }

    public JsonNode pull(String flowId, Path output) {
        JsonNode normalized = FlowSerialization.normalizeFlow(http.json.valueToTree(getFlow(flowId)));
        if (output != null) FlowSerialization.write(normalized, output);
        return normalized;
    }

    public List<UpsertResult> pushProject(Path directory) {
        try (var paths = Files.list(directory)) {
            return paths.filter(path -> path.getFileName().toString().endsWith(".json"))
                    .sorted(Comparator.comparing(Path::toString)).map(this::push).toList();
        } catch (IOException e) {
            throw new LangflowException("Unable to list project directory " + directory, e);
        }
    }

    public Map<String, Path> pullProject(String projectId, Path outputDirectory) {
        try {
            Files.createDirectories(outputDirectory);
            Map<String, Path> written = new LinkedHashMap<>();
            for (Map.Entry<String, byte[]> entry : downloadProject(projectId).entrySet()) {
                JsonNode normalized = FlowSerialization.normalizeFlow(http.json.readTree(entry.getValue()));
                String name = normalized.path("name").asText(stripJsonSuffix(entry.getKey()));
                Path destination = outputDirectory.resolve(name + ".json");
                FlowSerialization.write(normalized, destination);
                written.put(name, destination);
            }
            return written;
        } catch (IOException e) {
            throw new LangflowException("Unable to extract project " + projectId, e);
        }
    }

    private Map<String, byte[]> extractProjectArchive(byte[] archive) {
        Map<String, byte[]> files = new LinkedHashMap<>();
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(archive))) {
            ZipEntry entry;
            int count = 0;
            while ((entry = zip.getNextEntry()) != null) {
                if (++count > MAX_ZIP_ENTRIES) {
                    throw new IllegalArgumentException("ZIP contains more than " + MAX_ZIP_ENTRIES + " entries");
                }
                if (entry.isDirectory() || entry.getSize() > MAX_ENTRY_BYTES) continue;
                byte[] bytes = zip.readNBytes((int) MAX_ENTRY_BYTES + 1);
                if (bytes.length <= MAX_ENTRY_BYTES) files.put(entry.getName(), bytes);
            }
            return files;
        } catch (IOException e) {
            throw new LangflowException("Invalid project ZIP archive", e);
        }
    }

    private static String stripJsonSuffix(String filename) {
        String leaf = Path.of(filename).getFileName().toString();
        return leaf.endsWith(".json") ? leaf.substring(0, leaf.length() - 5) : leaf;
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

    private static final class SsePublisher extends SubmissionPublisher<StreamChunk> {
        private volatile EventSource source;
        private volatile boolean cancelled;
        private void setSource(EventSource value) {
            source = value;
            if (cancelled) value.cancel();
        }
        @Override public void subscribe(Subscriber<? super StreamChunk> subscriber) {
            super.subscribe(new Subscriber<>() {
                @Override public void onSubscribe(Subscription subscription) {
                    subscriber.onSubscribe(new Subscription() {
                        @Override public void request(long count) { subscription.request(count); }
                        @Override public void cancel() {
                            subscription.cancel();
                            cancelled = true;
                            EventSource current = source;
                            if (current != null) current.cancel();
                        }
                    });
                }
                @Override public void onNext(StreamChunk item) { subscriber.onNext(item); }
                @Override public void onError(Throwable throwable) { subscriber.onError(throwable); }
                @Override public void onComplete() { subscriber.onComplete(); }
            });
        }
    }
}
