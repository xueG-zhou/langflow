package org.langflow.sdk;

/** Raised when the SDK cannot establish or maintain a connection to Langflow. */
public final class ConnectionException extends LangflowException {
    public ConnectionException(String message, Throwable cause) { super(message, cause); }
}
