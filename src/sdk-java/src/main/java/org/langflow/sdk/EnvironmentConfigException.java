package org.langflow.sdk;

/** Raised when a Langflow environments TOML file is missing or malformed. */
public final class EnvironmentConfigException extends LangflowException {
    public EnvironmentConfigException(String message, Throwable cause) { super(message, cause); }
}
