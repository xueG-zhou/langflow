package org.langflow.sdk;

/** HTTP 404 failure for an unknown or deliberately hidden Langflow resource. */
public final class NotFoundException extends LangflowException {
    public NotFoundException(int status, String message, String body) { super(status, message, body); }
}
