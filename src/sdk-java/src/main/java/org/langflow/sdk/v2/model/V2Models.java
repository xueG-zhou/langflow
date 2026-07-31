package org.langflow.sdk.v2.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.List;
import java.util.Map;

/** Request and response types for the native Langflow v2 Workflow API. */
public final class V2Models {
    private V2Models() {}

    public enum JobStatus {queued, in_progress, completed, failed, cancelled, timed_out, suspended}
    public enum WorkflowMode {sync, stream, background}
    public enum OutputReason {single, multiple, none, non_string, failed}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record WorkflowRequest(
            @JsonProperty("flow_id") String flowId,
            @JsonProperty("input_value") String inputValue,
            Map<String, Object> tweaks,
            @JsonProperty("session_id") String sessionId,
            WorkflowMode mode,
            @JsonProperty("stream_protocol") String streamProtocol,
            Map<String, Object> data,
            List<String> files,
            @JsonProperty("start_component_id") String startComponentId,
            @JsonProperty("stop_component_id") String stopComponentId,
            @JsonProperty("output_ids") List<String> outputIds,
            Map<String, String> globals,
            @JsonProperty("idempotency_key") String idempotencyKey) {
        public WorkflowRequest {
            if (flowId == null || flowId.isBlank()) throw new IllegalArgumentException("flowId is required");
            if (idempotencyKey != null && idempotencyKey.length() > 255) {
                throw new IllegalArgumentException("idempotencyKey must not exceed 255 characters");
            }
            inputValue = inputValue == null ? "" : inputValue;
            tweaks = tweaks == null ? Map.of() : Map.copyOf(tweaks);
            mode = mode == null ? WorkflowMode.sync : mode;
            streamProtocol = streamProtocol == null ? "langflow" : streamProtocol;
            globals = globals == null ? Map.of() : Map.copyOf(globals);
        }

        public static WorkflowRequest synchronous(String flowId, String inputValue) {
            return create(flowId, inputValue, WorkflowMode.sync);
        }

        public static WorkflowRequest background(String flowId, String inputValue) {
            return create(flowId, inputValue, WorkflowMode.background);
        }

        public static WorkflowRequest streaming(String flowId, String inputValue) {
            return create(flowId, inputValue, WorkflowMode.stream);
        }

        private static WorkflowRequest create(String flowId, String inputValue, WorkflowMode mode) {
            return new WorkflowRequest(flowId, inputValue, Map.of(), null, mode, "langflow",
                    null, null, null, null, null, Map.of(), null);
        }
    }

    /** Restricted request body accepted by the unauthenticated public-flow streaming endpoint. */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record PublicWorkflowRequest(
            @JsonProperty("flow_id") String flowId,
            @JsonProperty("input_value") String inputValue,
            @JsonProperty("session_id") String sessionId,
            WorkflowMode mode,
            @JsonProperty("stream_protocol") String streamProtocol,
            List<String> files,
            @JsonProperty("start_component_id") String startComponentId,
            @JsonProperty("stop_component_id") String stopComponentId) {
        public PublicWorkflowRequest {
            if (flowId == null || flowId.isBlank()) throw new IllegalArgumentException("flowId is required");
            if (mode != null && mode != WorkflowMode.stream) {
                throw new IllegalArgumentException("Public workflows only support stream mode");
            }
            inputValue = inputValue == null ? "" : inputValue;
            mode = WorkflowMode.stream;
            streamProtocol = streamProtocol == null ? "langflow" : streamProtocol;
        }

        public PublicWorkflowRequest(String flowId, String inputValue) {
            this(flowId, inputValue, null, WorkflowMode.stream, "langflow", null, null, null);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ErrorDetail(String error, String code, Map<String, Object> details) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ComponentOutput(
            String type,
            JobStatus status,
            @JsonProperty("display_name") String displayName,
            JsonNode content,
            Map<String, Object> metadata) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record WorkflowOutput(OutputReason reason, String text, String source) {}

    public sealed interface WorkflowResult permits WorkflowResponse, WorkflowJob {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record WorkflowResponse(
            @JsonProperty("flow_id") String flowId,
            @JsonProperty("session_id") String sessionId,
            @JsonProperty("job_id") String jobId,
            String object,
            @JsonProperty("created_timestamp") String createdTimestamp,
            JobStatus status,
            WorkflowOutput output,
            List<ErrorDetail> errors,
            Map<String, Object> inputs,
            Map<String, String> globals,
            Map<String, ComponentOutput> outputs,
            @JsonProperty("human_request") Map<String, Object> humanRequest) implements WorkflowResult {
        public boolean hasErrors() { return errors != null && !errors.isEmpty(); }
        public boolean isCompleted() { return status == JobStatus.completed; }
        public boolean isFailed() {
            return status == JobStatus.failed || status == JobStatus.cancelled || status == JobStatus.timed_out;
        }
        public boolean isInProgress() {
            return status == JobStatus.queued || status == JobStatus.in_progress;
        }
        public boolean isSuspended() { return status == JobStatus.suspended; }
        public String textOutput() { return output == null ? null : output.text(); }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record WorkflowJob(
            @JsonProperty("job_id") String jobId,
            @JsonProperty("flow_id") String flowId,
            String object,
            @JsonProperty("created_timestamp") String createdTimestamp,
            JobStatus status,
            Map<String, String> links,
            List<ErrorDetail> errors,
            Map<String, String> globals) implements WorkflowResult {
        public boolean isTerminal() {
            return status == JobStatus.completed || status == JobStatus.failed
                    || status == JobStatus.cancelled || status == JobStatus.timed_out;
        }
        public boolean isSuspended() { return status == JobStatus.suspended; }
    }

    public record WorkflowStopRequest(@JsonProperty("job_id") String jobId) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record WorkflowStopResponse(@JsonProperty("job_id") String jobId, String message) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record WorkflowResumeRequest(
            @JsonProperty("request_id") String requestId,
            Map<String, Object> decision) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record WorkflowResumeResponse(
            @JsonProperty("job_id") String jobId,
            String status,
            String message) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record PendingWorkflow(
            @JsonProperty("job_id") String jobId,
            @JsonProperty("flow_id") String flowId,
            @JsonProperty("session_id") String sessionId,
            @JsonProperty("created_at") String createdAt,
            @JsonProperty("request_id") String requestId,
            String kind,
            String prompt,
            List<Map<String, Object>> options,
            @JsonProperty("allowed_decisions") List<String> allowedDecisions) {}

    /** Generic SSE frame for both initial streaming runs and background event reattachment. */
    public record StreamEvent(String id, String event, JsonNode data) {}
}
