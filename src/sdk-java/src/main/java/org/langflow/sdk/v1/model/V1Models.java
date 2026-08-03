package org.langflow.sdk.v1.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Request and response types for Langflow API v1.
 */
public final class V1Models {
    private V1Models() {
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    /** Request body for creating a flow; the one-argument constructor supplies server defaults. */
    public record FlowCreate(String name, String description, Map<String, Object> data,
                             @JsonProperty("is_component") Boolean isComponent,
                             @JsonProperty("endpoint_name") String endpointName, List<String> tags,
                             @JsonProperty("folder_id") UUID folderId, String icon,
                             @JsonProperty("icon_bg_color") String iconBgColor, Boolean locked,
                             @JsonProperty("mcp_enabled") Boolean mcpEnabled) {
        public FlowCreate(String name) {
            this(name, null, null, false, null, null, null, null, null, false, false);
        }
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    /** PATCH body for a flow. Null components are omitted to preserve existing values. */
    public record FlowUpdate(String name, String description, Map<String, Object> data,
                             @JsonProperty("endpoint_name") String endpointName, List<String> tags,
                             @JsonProperty("folder_id") UUID folderId, String icon,
                             @JsonProperty("icon_bg_color") String iconBgColor, Boolean locked,
                             @JsonProperty("mcp_enabled") Boolean mcpEnabled) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    /** Flow representation returned by the v1 API. Unknown future fields are ignored. */
    public record Flow(UUID id, String name, String description, Map<String, Object> data,
                       @JsonProperty("is_component") boolean isComponent,
                       @JsonProperty("updated_at") OffsetDateTime updatedAt,
                       @JsonProperty("endpoint_name") String endpointName, List<String> tags,
                       @JsonProperty("folder_id") UUID folderId, @JsonProperty("user_id") UUID userId,
                       String icon, @JsonProperty("icon_bg_color") String iconBgColor, boolean locked,
                       @JsonProperty("mcp_enabled") boolean mcpEnabled, boolean webhook,
                       @JsonProperty("access_type") String accessType) {
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    /** Request body for creating a project/folder and optionally assigning flows. */
    public record ProjectCreate(String name, String description,
                                @JsonProperty("flows_list") List<UUID> flowsList,
                                @JsonProperty("components_list") List<UUID> componentsList) {
        public ProjectCreate(String name) {
            this(name, null, null, null);
        }
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    /** Partial project metadata update. */
    public record ProjectUpdate(String name, String description) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    /** Project/folder summary returned by list and mutation endpoints. */
    public record Project(UUID id, String name, String description, @JsonProperty("parent_id") UUID parentId) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    /** Project detail response with its current flow collection. */
    public record ProjectWithFlows(UUID id, String name, String description,
                                   @JsonProperty("parent_id") UUID parentId, List<Flow> flows) {
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    /** Named input description used by Langflow run metadata. */
    public record RunInput(List<String> components,
                           @JsonProperty("input_value") String inputValue,
                           String type) {
        public RunInput {
            components = components == null ? List.of() : List.copyOf(components);
            inputValue = inputValue == null ? "" : inputValue;
            type = type == null ? "chat" : type;
        }

        public RunInput() { this(List.of(), "", "chat"); }
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    /**
     * Request body for {@code POST /api/v1/run/{id-or-endpoint}}.
     *
     * <p>Tweaks are keyed by component ID and override component parameters for
     * this execution only. The streaming client always forces stream to true.</p>
     */
    public record RunRequest(@JsonProperty("input_value") String inputValue,
                             @JsonProperty("input_type") String inputType,
                             @JsonProperty("output_type") String outputType,
                             Map<String, Object> tweaks, boolean stream) {
        public RunRequest(String inputValue) {
            this(inputValue, "chat", "chat", null, false);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    /** One output block from a v1 run, including component results and artifacts. */
    public record RunOutput(Map<String, Object> results, Map<String, Object> artifacts,
                            List<Map<String, Object>> outputs, @JsonProperty("session_id") String sessionId,
                            Double timedelta) {
        /** Extracts the first standard message text or direct text result. */
        public String firstText() {
            if (outputs == null) return null;
            for (Map<String, Object> component : outputs) {
                Object raw = component.get("results");
                if (!(raw instanceof Map<?, ?> componentResults)) continue;
                Object message = componentResults.get("message");
                if (message instanceof Map<?, ?> msg && msg.get("text") != null) {
                    return msg.get("text").toString();
                }
                if (componentResults.get("text") != null) return componentResults.get("text").toString();
            }
            return null;
        }

        /** Detects component or artifact error markers in this output block. */
        public boolean hasErrors() {
            if (outputs != null && outputs.stream().anyMatch(output -> output.get("error") != null)) return true;
            return artifacts != null && artifacts.get("error") != null;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    /** Complete synchronous v1 execution response plus convenience accessors. */
    public record RunResponse(@JsonProperty("session_id") String sessionId, List<RunOutput> outputs) {
        /** Returns the first text produced by any output block. */
        public String firstTextOutput() {
            if (outputs == null) {
                return null;
            }
            for (RunOutput block : outputs) {
                String text = block.firstText();
                if (text != null) return text;
            }
            return null;
        }

        /** Returns one extracted text value per output block when present. */
        public List<String> allTextOutputs() {
            if (outputs == null) return List.of();
            return outputs.stream().map(RunOutput::firstText).filter(java.util.Objects::nonNull).toList();
        }

        public String getChatOutput() { return firstTextOutput(); }
        public List<RunOutput> getAllOutputs() { return outputs == null ? List.of() : List.copyOf(outputs); }
        public List<String> getTextOutputs() { return allTextOutputs(); }
        public boolean hasErrors() { return outputs != null && outputs.stream().anyMatch(RunOutput::hasErrors); }
        public boolean isCompleted() { return outputs != null && !outputs.isEmpty() && !hasErrors(); }
        public boolean isFailed() { return outputs == null || outputs.isEmpty() || hasErrors(); }
        public boolean isInProgress() { return false; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    /**
     * One v1 streaming event.
     *
     * <p>Known events include token, add_message, end_vertex, end, and error.
     * The raw data node is preserved for forward compatibility.</p>
     */
    public record StreamChunk(String event, JsonNode data) {
        /** Returns incremental token or completed message text when applicable. */
        public String text() {
            if (data == null) {
                return null;
            }
            if ("add_message".equals(event)) {
                return data.path("message").path("text").isMissingNode()
                        ? null : data.path("message").path("text").asText();
            }
            if (!"token".equals(event)) return null;
            JsonNode token = data.get("chunk");
            return token == null || token.isNull() ? null : token.asText();
        }

        public boolean isToken() {
            return "token".equals(event);
        }

        public boolean isEnd() {
            return "end".equals(event);
        }

        public boolean isError() {
            return "error".equals(event);
        }

        /** Parses the embedded full response from an end event, otherwise returns null. */
        public RunResponse finalResponse() {
            if (!isEnd() || data == null || !data.hasNonNull("result")) return null;
            try {
                return new com.fasterxml.jackson.databind.ObjectMapper()
                        .treeToValue(data.get("result"), RunResponse.class);
            } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
                throw new IllegalArgumentException("Invalid final run response", e);
            }
        }
    }

    /** Result of a stable-ID upsert, including whether HTTP 201 created the flow. */
    public record UpsertResult(Flow flow, boolean created) {
    }
}
