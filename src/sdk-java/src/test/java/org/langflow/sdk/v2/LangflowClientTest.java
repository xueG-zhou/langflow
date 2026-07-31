package org.langflow.sdk.v2;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.langflow.sdk.v2.model.V2Models.WorkflowJob;
import org.langflow.sdk.v2.model.V2Models.WorkflowRequest;
import org.langflow.sdk.v2.model.V2Models.WorkflowMode;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class LangflowClientTest {
    MockWebServer server;
    LangflowClient client;
    @BeforeEach void setUp() throws Exception {
        server = new MockWebServer(); server.start();
        client = LangflowClient.builder(server.url("/").toString()).apiKey("secret").build();
    }
    @AfterEach void tearDown() throws Exception { client.close(); server.shutdown(); }

    @Test void executesBackgroundWorkflow() throws Exception {
        server.enqueue(new MockResponse().setHeader("Content-Type", "application/json").setBody("""
                {"object":"job","job_id":"9ef96787-c34f-4e63-81c5-1979f2142b2f","flow_id":"demo","status":"queued"}
                """));
        var result = client.execute(WorkflowRequest.background(
                "67ccd2be-17f0-8190-81ff-3bb2cf6508e6", "hi"));
        assertInstanceOf(WorkflowJob.class, result);
        assertEquals("/api/v2/workflows", server.takeRequest().getPath());
    }

    @Test void serializesNativeV2RequestShape() throws Exception {
        server.enqueue(new MockResponse().setHeader("Content-Type", "application/json").setBody("""
                {"object":"response","flow_id":"67ccd2be-17f0-8190-81ff-3bb2cf6508e6",
                 "status":"completed","output":{"reason":"single","text":"hello","source":"ChatOutput-1"}}
                """));
        var request = new WorkflowRequest(
                "67ccd2be-17f0-8190-81ff-3bb2cf6508e6", "hi", Map.of("ChatInput-1", Map.of("input_value", "hi")),
                "session-1", WorkflowMode.sync, "langflow", null, null, null, null,
                java.util.List.of("ChatOutput-1"), Map.of("ENV", "test"), null);
        var result = client.execute(request);
        var wire = server.takeRequest().getBody().readUtf8();
        assertTrue(wire.contains("\"mode\":\"sync\""));
        assertTrue(wire.contains("\"input_value\":\"hi\""));
        assertTrue(wire.contains("\"output_ids\":[\"ChatOutput-1\"]"));
        assertEquals("hello", ((org.langflow.sdk.v2.model.V2Models.WorkflowResponse) result).textOutput());
    }

    @Test void rejectsStreamingRequestOnJsonExecute() {
        assertThrows(IllegalArgumentException.class, () -> client.execute(WorkflowRequest.streaming(
                "67ccd2be-17f0-8190-81ff-3bb2cf6508e6", "hi")));
    }

    @Test void resumesSuspendedWorkflow() throws Exception {
        server.enqueue(new MockResponse().setHeader("Content-Type", "application/json").setBody("""
                {"job_id":"9ef96787-c34f-4e63-81c5-1979f2142b2f","status":"queued","message":"resumed"}
                """));
        var response = client.resume("9ef96787-c34f-4e63-81c5-1979f2142b2f",
                new org.langflow.sdk.v2.model.V2Models.WorkflowResumeRequest(
                        "node-1:run-1", Map.of("action_id", "approve")));
        assertEquals("queued", response.status());
        assertEquals("/api/v2/workflows/9ef96787-c34f-4e63-81c5-1979f2142b2f/resume",
                server.takeRequest().getPath());
    }
}
