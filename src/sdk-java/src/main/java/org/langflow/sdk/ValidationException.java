package org.langflow.sdk;

/** HTTP 400/422 failure caused by an invalid SDK request or API payload. */
public final class ValidationException extends LangflowException {
    public ValidationException(int status, String message, String body) { super(status, message, body); }
}
