package org.langflow.sdk.v1;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.langflow.sdk.LangflowException;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.Set;
import java.util.TreeMap;

/** Git-friendly flow normalization equivalent to the Python SDK serialization helpers. */
public final class FlowSerialization {
    private static final Set<String> VOLATILE_TOP_LEVEL =
            Set.of("updated_at", "created_at", "user_id", "folder_id", "access_type", "gradient");
    private static final Set<String> VOLATILE_NODE = Set.of("positionAbsolute", "dragging", "selected");
    private static final ObjectMapper JSON = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

    private FlowSerialization() {}

    public static ObjectNode normalizeFlow(JsonNode flow) {
        return normalizeFlow(flow, Options.defaults());
    }

    public static ObjectNode normalizeFlow(JsonNode flow, Options options) {
        if (flow == null || !flow.isObject()) throw new IllegalArgumentException("Flow must be a JSON object");
        if (options == null) throw new IllegalArgumentException("options is required");
        ObjectNode result = ((ObjectNode) flow).deepCopy();
        if (options.stripVolatile()) VOLATILE_TOP_LEVEL.forEach(result::remove);
        JsonNode nodes = result.path("data").path("nodes");
        if (nodes.isArray()) {
            for (JsonNode rawNode : nodes) {
                if (!(rawNode instanceof ObjectNode node)) continue;
                if (options.stripNodeVolatile()) VOLATILE_NODE.forEach(node::remove);
                JsonNode template = node.path("data").path("node").path("template");
                if (!template.isObject()) continue;
                for (Iterator<JsonNode> fields = template.elements(); fields.hasNext();) {
                    JsonNode field = fields.next();
                    if (field instanceof ObjectNode object) {
                        if (options.stripSecrets()
                                && (object.path("password").asBoolean() || object.path("load_from_db").asBoolean())) {
                            object.put("value", "");
                        }
                        if (options.codeAsLines() && "code".equals(object.path("type").asText())
                                && object.path("value").isTextual()) {
                            ArrayNode lines = JSON.createArrayNode();
                            String value = object.path("value").asText();
                            for (String line : value.split("\\n", -1)) lines.add(line);
                            object.set("value", lines);
                        }
                    }
                }
            }
        }
        return options.sortKeys() ? (ObjectNode) sortRecursively(result) : result;
    }

    public static ObjectNode normalizeFlowFile(Path path) {
        return normalizeFlowFile(path, Options.defaults());
    }

    public static ObjectNode normalizeFlowFile(Path path, Options options) {
        try {
            return normalizeFlow(JSON.readTree(path.toFile()), options);
        } catch (IOException e) {
            throw new LangflowException("Unable to read flow file " + path, e);
        }
    }

    public static String flowToJson(JsonNode flow) {
        try {
            return JSON.writeValueAsString(flow) + "\n";
        } catch (IOException e) {
            throw new LangflowException("Unable to serialize flow", e);
        }
    }

    public static void write(JsonNode flow, Path output) {
        try {
            Path parent = output.toAbsolutePath().getParent();
            if (parent != null) Files.createDirectories(parent);
            Files.writeString(output, flowToJson(flow));
        } catch (IOException e) {
            throw new LangflowException("Unable to write flow file " + output, e);
        }
    }

    private static JsonNode sortRecursively(JsonNode node) {
        if (node.isObject()) {
            ObjectNode sorted = JSON.createObjectNode();
            var fields = new TreeMap<String, JsonNode>();
            node.fields().forEachRemaining(entry -> fields.put(entry.getKey(), entry.getValue()));
            fields.forEach((key, value) -> sorted.set(key, sortRecursively(value)));
            return sorted;
        }
        if (node.isArray()) {
            ArrayNode array = JSON.createArrayNode();
            node.forEach(value -> array.add(sortRecursively(value)));
            return array;
        }
        return node.deepCopy();
    }

    /** Options matching Python SDK normalize_flow keyword arguments. */
    public record Options(
            boolean stripVolatile,
            boolean stripSecrets,
            boolean sortKeys,
            boolean codeAsLines,
            boolean stripNodeVolatile) {
        public static Options defaults() { return new Options(true, true, true, false, true); }
    }
}
