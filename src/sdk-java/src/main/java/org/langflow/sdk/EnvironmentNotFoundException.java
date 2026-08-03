package org.langflow.sdk;

/** Raised when a requested named Langflow environment is not configured. */
public final class EnvironmentNotFoundException extends LangflowException {
    public EnvironmentNotFoundException(String name) {
        super("Langflow environment '" + name + "' was not found", null);
    }
}
