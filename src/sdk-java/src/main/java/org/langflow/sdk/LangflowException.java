package org.langflow.sdk;

/**
 * Base unchecked exception for all failures reported by the Langflow Java SDK.
 *
 * <p>For HTTP failures, {@link #statusCode()} contains the server status and
 * {@link #responseBody()} preserves the original response for diagnostics.
 * Local failures such as connection, timeout, or serialization errors use a
 * status code of {@code 0} and retain the underlying cause.</p>
 */
public class LangflowException extends RuntimeException {
    private final int statusCode;
    private final String responseBody;

    /** Creates an SDK failure that did not originate from an HTTP response. */
    public LangflowException(String message, Throwable cause) {
        super(message, cause);
        this.statusCode = 0;
        this.responseBody = null;
    }

    /** Creates an HTTP failure while preserving its status and raw response body. */
    public LangflowException(int statusCode, String message, String responseBody) {
        super(message);
        this.statusCode = statusCode;
        this.responseBody = responseBody;
    }

    /** Returns the HTTP status, or {@code 0} for local failures. */
    public int statusCode() { return statusCode; }
    /** Returns the unmodified HTTP response body, or {@code null} for local failures. */
    public String responseBody() { return responseBody; }
}
