package org.langflow.sdk;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import okhttp3.HttpUrl;
import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

import java.io.IOException;
import java.io.InterruptedIOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.CompletableFuture;

/**
 * Shared OkHttp/Jackson transport used by the versioned clients.
 *
 * <p>This class centralizes URL resolution, API-key propagation, JSON
 * serialization, timeout configuration, debug logging, and conversion of HTTP
 * status codes into typed SDK exceptions. Applications normally interact with
 * the v1 or v2 client instead of constructing this class directly.</p>
 */
public final class HttpTransport {
    static final MediaType JSON = MediaType.get("application/json; charset=utf-8");
    static final MediaType OCTET_STREAM = MediaType.get("application/octet-stream");
    public final ObjectMapper json = new ObjectMapper().registerModule(new JavaTimeModule());
    private final HttpUrl baseUrl;
    private final String apiKey;
    private final OkHttpClient client;

    /**
     * Creates a transport with independent OkHttp timeout controls.
     *
     * @param baseUrl Langflow service root, for example {@code http://localhost:7860}
     * @param apiKey optional value sent in the {@code x-api-key} header
     * @param client optional application-provided OkHttp client; it is cloned before use
     */
    public HttpTransport(String baseUrl, String apiKey, Duration connectTimeout, Duration readTimeout,
                         Duration writeTimeout, Duration callTimeout, OkHttpClient client) {
        this.baseUrl = HttpUrl.get(baseUrl.replaceAll("/+$", "") + "/");
        this.apiKey = apiKey;
        this.client = (client == null ? new OkHttpClient() : client).newBuilder()
                .addInterceptor(new DebugLoggingInterceptor())
                .connectTimeout(connectTimeout.toMillis(), TimeUnit.MILLISECONDS)
                .readTimeout(readTimeout.toMillis(), TimeUnit.MILLISECONDS)
                .writeTimeout(writeTimeout.toMillis(), TimeUnit.MILLISECONDS)
                .callTimeout(callTimeout.toMillis(), TimeUnit.MILLISECONDS)
                .build();
    }

    /** Returns the configured OkHttp client used for normal and SSE calls. */
    public OkHttpClient client() { return client; }

    /**
     * Builds an authenticated request without executing it.
     *
     * <p>Used by the SSE clients because OkHttp's EventSource API owns request
     * execution. Non-null bodies are JSON encoded.</p>
     */
    public Request request(String method, String path, Object body, String accept) {
        try {
            RequestBody requestBody = body == null ? null : RequestBody.create(json.writeValueAsBytes(body), JSON);
            var builder = new Request.Builder().url(resolve(path)).header("Accept", accept);
            if (requestBody != null) builder.header("Content-Type", "application/json");
            if (apiKey != null && !apiKey.isBlank()) builder.header("x-api-key", apiKey);
            return builder.method(method, requestBody).build();
        } catch (Exception e) {
            throw new LangflowException("Unable to build Langflow request", e);
        }
    }

    /** Executes a JSON request and deserializes a concrete response type. */
    public <T> T send(String method, String path, Object body, Class<T> type) {
        String response = execute(method, path, body).body();
        if (type == Void.class || response.isBlank()) return null;
        try { return json.readValue(response, type); }
        catch (Exception e) { throw new LangflowException("Invalid Langflow response", e); }
    }

    /**
     * Executes a JSON request asynchronously.
     *
     * <p>Cancelling the returned future also cancels the underlying OkHttp
     * call, rather than only changing the future's state.</p>
     */
    public <T> CompletableFuture<T> sendAsync(String method, String path, Object body, Class<T> type) {
        Call call = client.newCall(request(method, path, body, "application/json"));
        var future = new CallFuture<T>(call);
        call.enqueue(new Callback() {
            @Override public void onFailure(Call ignored, IOException error) {
                if (!future.isCancelled()) future.completeExceptionally(ioError(error));
            }

            @Override public void onResponse(Call ignored, Response response) {
                try (response) {
                    String text = response.body() == null ? "" : response.body().string();
                    if (!response.isSuccessful()) {
                        future.completeExceptionally(httpError(response.code(), text));
                    } else if (type == Void.class || text.isBlank()) {
                        future.complete(null);
                    } else {
                        future.complete(json.readValue(text, type));
                    }
                } catch (Exception error) {
                    future.completeExceptionally(error instanceof LangflowException
                            ? error : new LangflowException("Invalid Langflow response", error));
                }
            }
        });
        return future;
    }

    /** Executes a JSON request whose response contains generic collection types. */
    public <T> T send(String method, String path, Object body, TypeReference<T> type) {
        try { return json.readValue(execute(method, path, body).body(), type); }
        catch (LangflowException e) { throw e; }
        catch (Exception e) { throw new LangflowException("Invalid Langflow response", e); }
    }

    /** Executes a request and exposes both the HTTP status and raw body. */
    public ResponseData sendWithStatus(String method, String path, Object body) {
        return execute(method, path, body);
    }

    /** Downloads an opaque binary response, used for project ZIP exports. */
    public byte[] download(String path) {
        try (Response response = client.newCall(request("GET", path, null, "application/octet-stream")).execute()) {
            byte[] bytes = response.body() == null ? new byte[0] : response.body().bytes();
            if (!response.isSuccessful()) {
                throw httpError(response.code(), new String(bytes, StandardCharsets.UTF_8));
            }
            return bytes;
        } catch (LangflowException e) {
            throw e;
        } catch (IOException e) {
            throw ioError(e);
        }
    }

    /** Uploads an {@code application/octet-stream} payload and parses its JSON response. */
    public <T> T upload(String path, byte[] bytes, TypeReference<T> type) {
        RequestBody body = RequestBody.create(bytes, OCTET_STREAM);
        var builder = new Request.Builder().url(resolve(path)).header("Accept", "application/json")
                .header("Content-Type", "application/octet-stream").post(body);
        if (apiKey != null && !apiKey.isBlank()) builder.header("x-api-key", apiKey);
        try (Response response = client.newCall(builder.build()).execute()) {
            String text = response.body() == null ? "" : response.body().string();
            if (!response.isSuccessful()) throw httpError(response.code(), text);
            return json.readValue(text, type);
        } catch (LangflowException e) {
            throw e;
        } catch (IOException e) {
            throw ioError(e);
        }
    }

    private ResponseData execute(String method, String path, Object body) {
        try (Response response = client.newCall(request(method, path, body, "application/json")).execute()) {
            String text = response.body() == null ? "" : response.body().string();
            if (!response.isSuccessful()) throw httpError(response.code(), text);
            return new ResponseData(response.code(), text);
        } catch (LangflowException e) { throw e; }
        catch (IOException e) { throw ioError(e); }
    }

    /** Immutable successful HTTP response used when status codes carry semantics such as 201. */
    public record ResponseData(int statusCode, String body) {}

    private LangflowException ioError(IOException error) {
        if (error instanceof java.net.SocketTimeoutException
                || error instanceof InterruptedIOException && !Thread.currentThread().isInterrupted()) {
            return new TimeoutException("Request to Langflow at " + baseUrl + " timed out", error);
        }
        return new ConnectionException("Could not connect to Langflow at " + baseUrl, error);
    }

    private static final class CallFuture<T> extends CompletableFuture<T> {
        private final Call call;
        private CallFuture(Call call) { this.call = call; }
        @Override public boolean cancel(boolean mayInterruptIfRunning) {
            call.cancel();
            return super.cancel(mayInterruptIfRunning);
        }
    }

    private HttpUrl resolve(String path) {
        HttpUrl resolved = baseUrl.resolve(path.replaceFirst("^/", ""));
        if (resolved == null) throw new IllegalArgumentException("Invalid API path: " + path);
        return resolved;
    }

    /**
     * Encodes non-null values as URL query parameters.
     *
     * @param params insertion-ordered parameters when deterministic output is desired
     */
    public static String query(Map<String, ?> params) {
        var builder = new StringBuilder();
        params.forEach((key, value) -> {
            if (value == null) return;
            builder.append(builder.isEmpty() ? '?' : '&')
                    .append(URLEncoder.encode(key, StandardCharsets.UTF_8))
                    .append('=')
                    .append(URLEncoder.encode(value.toString(), StandardCharsets.UTF_8));
        });
        return builder.toString();
    }

    private LangflowException httpError(int status, String body) {
        String message = body;
        try {
            JsonNode detail = json.readTree(body).get("detail");
            if (detail != null) message = detail.isTextual() ? detail.asText() : detail.toString();
        } catch (Exception ignored) { }
        if (status == 401 || status == 403) return new AuthException(status, message, body);
        if (status == 404) return new NotFoundException(status, message, body);
        if (status == 400 || status == 422) return new ValidationException(status, message, body);
        return new LangflowException(status, message, body);
    }
}
