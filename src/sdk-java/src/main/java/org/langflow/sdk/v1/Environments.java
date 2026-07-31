package org.langflow.sdk.v1;

import org.langflow.sdk.EnvironmentConfigException;
import org.langflow.sdk.EnvironmentNotFoundException;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Loader for named {@code langflow-environments.toml} configurations.
 *
 * <p>Lookup order matches the Python SDK: explicit path, the
 * {@value #FILE_ENV} environment variable, the working directory, then the
 * user configuration directory. API keys may be read indirectly with
 * {@code api_key_env} to avoid storing credentials in source control.</p>
 */
public final class Environments {
    /** Name of the environment variable that can point to the TOML file. */
    public static final String FILE_ENV = "LANGFLOW_ENVIRONMENTS_FILE";
    private Environments() {}

    /** One resolved environment; {@link #toString()} masks the API key. */
    public record EnvironmentConfig(String name, String url, String apiKey) {
        @Override public String toString() {
            String masked = apiKey == null ? null : apiKey.substring(0, Math.min(4, apiKey.length())) + "...";
            return "EnvironmentConfig[name=" + name + ", url=" + url + ", apiKey=" + masked + "]";
        }
    }

    /** Loads every environment from the first configuration file found. */
    public static Map<String, EnvironmentConfig> load() { return load(null); }

    /** Loads every environment, giving an explicit file highest priority. */
    public static Map<String, EnvironmentConfig> load(Path explicitFile) {
        Path file = findFile(explicitFile);
        Parsed parsed = parse(file);
        Map<String, EnvironmentConfig> result = new LinkedHashMap<>();
        parsed.environments.forEach((name, values) -> {
            String url = values.get("url");
            if (url == null || url.isBlank()) {
                throw new EnvironmentConfigException(
                        "Environment '" + name + "' in " + file + " is missing the required 'url' field", null);
            }
            String apiKey = null;
            String apiKeyEnv = values.get("api_key_env");
            if (apiKeyEnv != null) apiKey = System.getenv(apiKeyEnv);
            else if (values.containsKey("api_key")) apiKey = values.get("api_key");
            result.put(name, new EnvironmentConfig(name, url, apiKey));
        });
        return Map.copyOf(result);
    }

    /** Resolves a named environment from the standard configuration lookup. */
    public static EnvironmentConfig get(String name) { return get(name, null); }

    /** Resolves a named environment, or the configured default when name is null. */
    public static EnvironmentConfig get(String name, Path explicitFile) {
        Path file = findFile(explicitFile);
        Parsed parsed = parse(file);
        String resolved = name == null ? parsed.defaultEnvironment : name;
        if (resolved == null || resolved.isBlank()) {
            throw new EnvironmentConfigException(
                    "No environment name given and no [defaults] environment set in " + file, null);
        }
        EnvironmentConfig config = load(file).get(resolved);
        if (config == null) throw new EnvironmentNotFoundException(resolved);
        return config;
    }

    /** Creates a v1 client for a named environment with a 60-second timeout. */
    public static LangflowClient client(String name) { return client(name, null, Duration.ofSeconds(60)); }

    /** Creates a v1 client using an environment and explicit timeout. */
    public static LangflowClient client(String name, Path file, Duration timeout) {
        EnvironmentConfig config = get(name, file);
        return LangflowClient.builder(config.url()).apiKey(config.apiKey()).timeout(timeout).build();
    }

    private static Path findFile(Path explicitFile) {
        String fromEnvironment = System.getenv(FILE_ENV);
        List<Path> candidates = List.of(
                explicitFile == null ? Path.of("__not_configured__") : explicitFile,
                fromEnvironment == null || fromEnvironment.isBlank() ? Path.of("__not_configured__") : Path.of(fromEnvironment),
                Path.of("langflow-environments.toml"),
                Path.of(System.getProperty("user.home"), ".config", "langflow", "environments.toml"));
        return candidates.stream().filter(Files::exists).findFirst().orElseThrow(() ->
                new EnvironmentConfigException(
                        "No langflow-environments.toml found; set " + FILE_ENV + " or pass an explicit path", null));
    }

    private static Parsed parse(Path file) {
        try {
            Map<String, Map<String, String>> environments = new LinkedHashMap<>();
            Map<String, String> current = null;
            String defaultEnvironment = null;
            boolean defaults = false;
            for (String original : Files.readAllLines(file)) {
                String line = stripComment(original).trim();
                if (line.isEmpty()) continue;
                if (line.startsWith("[") && line.endsWith("]")) {
                    String section = line.substring(1, line.length() - 1).trim();
                    defaults = "defaults".equals(section);
                    current = section.startsWith("environments.")
                            ? environments.computeIfAbsent(section.substring("environments.".length()), ignored -> new LinkedHashMap<>())
                            : null;
                    continue;
                }
                int separator = line.indexOf('=');
                if (separator < 1) throw new IllegalArgumentException("Invalid TOML assignment: " + original);
                String key = line.substring(0, separator).trim();
                String value = unquote(line.substring(separator + 1).trim());
                if (defaults && "environment".equals(key)) defaultEnvironment = value;
                else if (current != null) current.put(key, value);
            }
            return new Parsed(environments, defaultEnvironment);
        } catch (IOException | IllegalArgumentException error) {
            throw new EnvironmentConfigException("Cannot parse environments file " + file + ": " + error.getMessage(), error);
        }
    }

    private static String stripComment(String line) {
        boolean single = false;
        boolean doubled = false;
        for (int i = 0; i < line.length(); i++) {
            char character = line.charAt(i);
            if (character == '\'' && !doubled) single = !single;
            else if (character == '"' && !single && (i == 0 || line.charAt(i - 1) != '\\')) doubled = !doubled;
            else if (character == '#' && !single && !doubled) return line.substring(0, i);
        }
        return line;
    }

    private static String unquote(String value) {
        if (value.length() >= 2
                && ((value.startsWith("\"") && value.endsWith("\""))
                || (value.startsWith("'") && value.endsWith("'")))) {
            return value.substring(1, value.length() - 1);
        }
        throw new IllegalArgumentException("Expected quoted string value");
    }

    private record Parsed(Map<String, Map<String, String>> environments, String defaultEnvironment) {}
}
