package org.langflow.sdk;

/** HTTP 401/403 failure indicating missing credentials or insufficient permission. */
public final class AuthException extends LangflowException {
    public AuthException(int status, String message, String body) { super(status, message, body); }
}
