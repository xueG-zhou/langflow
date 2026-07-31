package org.langflow.example.web;

import org.langflow.sdk.v2.LangflowClient;
import org.langflow.sdk.v2.model.V2Models.WorkflowRequest;
import org.langflow.sdk.v2.model.V2Models.WorkflowResult;
import org.langflow.sdk.v2.model.V2Models.WorkflowMode;
import org.langflow.sdk.v2.model.V2Models.WorkflowStopResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/demo/v2")
public class V2Controller {
    private final LangflowClient client;
    public V2Controller(LangflowClient client) { this.client = client; }

    @PostMapping("/run")
    public WorkflowResult run(@RequestBody V2RunRequest body) {
        return client.execute(new WorkflowRequest(
                body.flowId(), body.inputValue(), body.tweaks(), body.sessionId(),
                body.background() ? WorkflowMode.background : WorkflowMode.sync,
                "langflow", null, body.files(), null, null, body.outputIds(),
                body.globals(), body.idempotencyKey()));
    }

    @GetMapping("/status")
    public WorkflowResult status(@RequestParam String jobId) { return client.status(jobId); }

    @PostMapping("/stop")
    public WorkflowStopResponse stop(@RequestBody StopRequest body) { return client.stop(body.jobId()); }

    public record V2RunRequest(String flowId, String inputValue, boolean background,
                               Map<String, Object> tweaks, String sessionId, java.util.List<String> files,
                               java.util.List<String> outputIds, Map<String, String> globals,
                               String idempotencyKey) {}
    public record StopRequest(String jobId) {}
}
