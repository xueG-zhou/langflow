package org.langflow.sdk;

/** Raised when an HTTP request or background wait exceeds its configured timeout. */
public final class TimeoutException extends LangflowException {
    public TimeoutException(String message, Throwable cause) { super(message, cause); }
}
