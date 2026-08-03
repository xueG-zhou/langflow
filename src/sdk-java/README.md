# Langflow Java SDK

基于 JDK 21、OkHttp 4 和 Jackson 的 Langflow Java SDK。当前版本与 Python SDK
`0.3.0` 对齐，v1 与 v2 使用独立目录和包，避免接口模型混用。

## Spring Boot 集成

SDK 保持框架无关，不引入 Spring Boot 依赖。在应用自己的配置类中注册需要的客户端：

```yaml
langflow:
  base-url: ${LANGFLOW_BASE_URL:http://localhost:7860}
  api-key: ${LANGFLOW_API_KEY:}
  timeout:
    connect: 10s
    read: 60s
    write: 60s
    call: 90s
```

```java
@Configuration
public class LangflowConfiguration {
    @Bean(destroyMethod = "close")
    LangflowClient langflowClient(
            @Value("${langflow.base-url}") String baseUrl,
            @Value("${langflow.api-key:}") String apiKey) {
        return LangflowClient.builder(baseUrl)
            .apiKey(apiKey)
            .build();
    }
```

之后可通过构造器注入使用。完整 v1、异步 v1 和 v2 配置参见 `src/sdk-java-springboot-demo`。

## 构建

```bash
cd src/sdk-java
mvn test
```

## v1

```java
import org.langflow.sdk.v1.LangflowClient;

try (var client = LangflowClient.builder("http://localhost:7860")
        .apiKey(System.getenv("LANGFLOW_API_KEY"))
        .build()) {
    var response = client.run("my-flow", "你好");
    System.out.println(response.firstTextOutput());
}
```

URL、端口、API Key 和超时均可配置：

```java
var client = LangflowClient.builder("localhost", 7860)
    .scheme("http")
    .apiKey(System.getenv("LANGFLOW_API_KEY"))
    .connectTimeout(Duration.ofSeconds(10))
    .readTimeout(Duration.ofSeconds(60))
    .writeTimeout(Duration.ofSeconds(60))
    .callTimeout(Duration.ofSeconds(90))
    .build();
```

`.timeout(Duration)` 可一次设置全部四类超时；`builder("https://host:port")` 仍然可用。v1 和 v2 Builder 提供相同的配置接口。

## DEBUG 请求日志（Spring Boot）

SDK 会在 DEBUG 级别记录请求 URL、请求参数、响应参数、HTTP 状态码和耗时。API Key、Authorization 以及常见密码/Token 字段会脱敏。

```yaml
logging:
  level:
    org.langflow.sdk.http: DEBUG
    org.langflow.sdk.sse: DEBUG
```

普通响应日志最大记录 1 MB，超过部分会标记为 `<truncated>`。SSE 响应不会被预读取，而是通过 `org.langflow.sdk.sse` 逐事件记录。

SSE 基于 `okhttp-sse`，返回 JDK `Flow.Publisher`：

```java
client.stream("my-flow", new RunRequest("你好")).subscribe(subscriber);
```

v1 当前包含 Flow CRUD、运行与 SSE、后台运行、Project CRUD 与 ZIP 导入导出，以及
适合 Git 管理的 flow push/pull 文件工具；模型位于 `org.langflow.sdk.v1.model`。

```java
var pushed = client.push(Path.of("flows/my-flow.json"));
var normalized = client.pull(pushed.flow().id().toString(), Path.of("flows/my-flow.json"));

var job = client.runBackground("my-flow", "你好");
var response = job.waitForCompletion(Duration.ofSeconds(60));
```

`FlowSerialization.normalizeFlow(...)` 会移除实例相关字段、清空密码字段、移除节点拖拽状态并递归排序 key，
与 Python SDK 的默认规范化行为一致。

需要控制 Python SDK 中的各项规范化开关时：

```java
var options = new FlowSerialization.Options(
    true,  // stripVolatile
    true,  // stripSecrets
    true,  // sortKeys
    true,  // codeAsLines
    true   // stripNodeVolatile
);
var normalized = FlowSerialization.normalizeFlow(raw, options);
```

异步客户端返回 `CompletableFuture`：

```java
try (var async = AsyncLangflowClient.builder("http://localhost:7860")
        .apiKey(System.getenv("LANGFLOW_API_KEY"))
        .build()) {
    async.run(flowId, "你好").thenAccept(response -> System.out.println(response.getChatOutput()));
}
```

Python SDK 使用的 `langflow-environments.toml` 可直接复用：

```java
try (var client = Environments.client("staging")) {
    client.listFlows();
}
```

## v2

```java
import org.langflow.sdk.v2.LangflowClient;
import org.langflow.sdk.v2.model.V2Models.WorkflowRequest;

try (var client = LangflowClient.builder("http://localhost:7860")
        .apiKey(System.getenv("LANGFLOW_API_KEY"))
        .build()) {
    var result = client.execute(WorkflowRequest.synchronous(
        "67ccd2be-17f0-8190-81ff-3bb2cf6508e6", "你好"));
}
```

v2 使用当前原生 Workflow API 请求模型，支持 `sync`、`stream`、`background` 三种 mode，
以及 `input_value`、`tweaks`、`session_id`、`stream_protocol`、局部运行和幂等后台提交。
此外支持任务状态与停止、SSE 后台事件重连、HITL pending 查询及 resume：

```java
var job = (WorkflowJob) client.execute(WorkflowRequest.background(flowId, "处理这份文件"));
client.events(job.jobId(), lastEventId).subscribe(subscriber);

var pending = client.pending(flowId);
client.resume(job.jobId(), new WorkflowResumeRequest(
    pending.getFirst().requestId(), Map.of("action_id", "approve")));
```

模型位于 `org.langflow.sdk.v2.model`。
