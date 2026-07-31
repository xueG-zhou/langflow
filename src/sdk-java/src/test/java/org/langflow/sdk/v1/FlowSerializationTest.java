package org.langflow.sdk.v1;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FlowSerializationTest {
    private final ObjectMapper json = new ObjectMapper();

    @Test void defaultOptionsMatchPythonNormalization() throws Exception {
        var source = json.readTree("""
                {"updated_at":"now","data":{"nodes":[{"selected":true,"data":{"node":{"template":{
                  "secret":{"password":true,"value":"key"},
                  "code":{"type":"code","value":"line1\\nline2"}
                }}}}]}}
                """);
        var result = FlowSerialization.normalizeFlow(source);
        assertFalse(result.has("updated_at"));
        assertFalse(result.path("data").path("nodes").get(0).has("selected"));
        assertEquals("", result.at("/data/nodes/0/data/node/template/secret/value").asText());
        assertTrue(result.at("/data/nodes/0/data/node/template/code/value").isTextual());
    }

    @Test void supportsPythonSerializationOptionsAndCodeLines() throws Exception {
        var source = json.readTree("""
                {"updated_at":"now","data":{"nodes":[{"selected":true,"data":{"node":{"template":{
                  "secret":{"password":true,"value":"key"},
                  "code":{"type":"code","value":"line1\\nline2"}
                }}}}]}}
                """);
        var options = new FlowSerialization.Options(false, false, false, true, false);
        var result = FlowSerialization.normalizeFlow(source, options);
        assertEquals("now", result.path("updated_at").asText());
        assertTrue(result.path("data").path("nodes").get(0).path("selected").asBoolean());
        assertEquals("key", result.at("/data/nodes/0/data/node/template/secret/value").asText());
        assertEquals(2, result.at("/data/nodes/0/data/node/template/code/value").size());
    }
}
