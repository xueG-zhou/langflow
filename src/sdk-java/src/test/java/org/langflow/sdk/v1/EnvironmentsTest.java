package org.langflow.sdk.v1;

import org.junit.jupiter.api.Test;
import org.langflow.sdk.EnvironmentNotFoundException;

import java.nio.file.Files;

import static org.junit.jupiter.api.Assertions.*;

class EnvironmentsTest {
    @Test void loadsPythonCompatibleTomlAndDefault() throws Exception {
        var file = Files.createTempFile("langflow-environments-", ".toml");
        Files.writeString(file, """
                [environments.staging]
                url = "https://staging.example.com"
                api_key = "test-key"

                [environments.production]
                url = "https://example.com"

                [defaults]
                environment = "staging"
                """);
        var environments = Environments.load(file);
        assertEquals("https://staging.example.com", environments.get("staging").url());
        assertEquals("test-key", Environments.get(null, file).apiKey());
        assertThrows(EnvironmentNotFoundException.class, () -> Environments.get("missing", file));
        Files.deleteIfExists(file);
    }
}
