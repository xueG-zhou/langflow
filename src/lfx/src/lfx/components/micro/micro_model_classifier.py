# ruff: noqa: RUF001
"""Micro model classifier component.

Classifies input text with a BERT-style classification model served by a
Triton Inference Server over gRPC. The inference pipeline mirrors the
reference client: greedy longest-match tokenization -> sliding-window
segmentation (window=510, stride=200) -> per-segment inference -> argmax ->
majority vote (ties resolve to the smallest class id).

Note: user-facing strings intentionally use CJK punctuation (full-width
commas/parentheses), which trips RUF001; suppressed file-wide above.
"""

import json
import os
from collections import Counter
from pathlib import Path

from lfx.custom import Component
from lfx.io import DropdownInput, MessageTextInput, Output, StrInput, TableInput
from lfx.schema.message import Message
from lfx.schema.table import EditMode

MAX_LEN = 512
STRIDE = 200
WINDOW = MAX_LEN - 2  # 510, room for [CLS] ... [SEP]

OUTPUT_CLASS_NAME = "Class Name"
OUTPUT_CLASS_ID = "Class ID"
UNDEFINED_LABEL = "Undefined"


def _load_vocab(path: Path) -> dict[str, int]:
    with path.open(encoding="utf-8") as f:
        return {tok: i for i, tok in enumerate(line.strip() for line in f)}


def _tokenize(text: str, vocab: dict[str, int]) -> list[str]:
    """Greedy longest-match tokenization (port of BertTokenizer.java)."""
    tokens, i = [], 0
    while i < len(text):
        if text[i] == " ":
            i += 1
            continue
        n, token = 0, "[UNK]"
        while i + n < len(text) and text[i : i + n + 1].lower() in vocab:
            n += 1
            token = text[i : i + n].lower()
        tokens.append(token)
        i += max(n, 1)
    return tokens


def _segment(text: str, vocab: dict[str, int]) -> list[str]:
    """Sliding-window segmentation (port of BertClassifier.segmentText)."""
    tokens = _tokenize(text, vocab)
    segments, start = [], 0
    while start < len(tokens):
        end = min(start + WINDOW, len(tokens))
        segments.append(" ".join(tokens[start:end]))
        if end == len(tokens):
            break
        start += STRIDE
    return segments or [text]


def _encode(text: str, vocab: dict[str, int], np) -> tuple:
    """Return (input_ids[1,512] int64, attention_mask[1,512] int64)."""
    unk, pad = vocab.get("[UNK]", 100), vocab.get("[PAD]", 0)
    ids = [vocab.get(t, unk) for t in ["[CLS]", *_tokenize(text, vocab), "[SEP]"]]
    ids = ids[:MAX_LEN]
    mask = [1] * len(ids) + [0] * (MAX_LEN - len(ids))
    ids += [pad] * (MAX_LEN - len(ids))
    return np.array([ids], dtype=np.int64), np.array([mask], dtype=np.int64)


class MicroModelClassifierComponent(Component):
    display_name = "微模型分类"
    description = (
        "通过 gRPC 调用 Triton Server 上的微模型（BERT 分类模型）对输入文本进行分类，"
        "输出分类 ID 或映射后的分类名称（Classify text with a BERT model served by Triton over gRPC）."
    )
    icon = "microscope"
    name = "MicroModelClassifier"

    inputs = [
        MessageTextInput(
            name="input_text",
            display_name="Input Text",
            info="待进行分类计算的字符串。",
            required=True,
        ),
        StrInput(
            name="vocab_path",
            display_name="Vocab Path",
            info=(
                "vocab.txt 文件的完整路径。"
                "请使用正斜杠（例如 D:/userdata/models/9636/vocab.txt），"
                "避免使用反斜杠：框架会对字符串字段做转义处理，"
                "路径中的 \\n（如 \\newtouch）会被当作换行符而损坏路径。"
            ),
            required=True,
        ),
        StrInput(
            name="model_variable",
            display_name="Model Config Variable",
            info=(
                "保存模型配置的全局变量名（勾选 Load from DB 后从全局变量解析）。"
                "变量值为 JSON 字符串，需包含 grpc_url 和 model，例如："
                '{"server_id":"96370f7e-35f4-4810-8bb8-7892666ae048","base_url":"http://localhost:8000",'
                '"grpc_url":"localhost:8001","model":"9636"}'
            ),
            # Field name must NOT contain "config" or "kwargs": loading.convert_kwargs()
            # treats any such string field as JSON and drops it when parsing fails.
            # load_from_db=True lets the framework resolve the global variable value
            # for us, so the component just parses the resolved JSON.
            load_from_db=True,
            required=True,
        ),
        DropdownInput(
            name="output_type",
            display_name="Output Type",
            info=(
                f"选择输出分类 ID 还是分类名称。选择分类名称时，若分类 ID 未在映射表中配置，输出 {UNDEFINED_LABEL}。"
            ),
            options=[OUTPUT_CLASS_NAME, OUTPUT_CLASS_ID],
            value=OUTPUT_CLASS_NAME,
        ),
        TableInput(
            name="label_mapping",
            display_name="Label Mapping",
            info="分类 ID 与分类名称的映射表（可选）。仅当输出类型为分类名称时使用。",
            table_schema=[
                {
                    "name": "class_id",
                    "display_name": "Class ID",
                    "type": "str",
                    "description": "模型输出的分类 ID（整数，如 0、1、2 ...）",
                    "edit_mode": EditMode.INLINE,
                },
                {
                    "name": "class_name",
                    "display_name": "Class Name",
                    "type": "str",
                    "description": "分类 ID 对应的分类名称",
                    "edit_mode": EditMode.INLINE,
                },
            ],
            value=[],
            required=False,
        ),
    ]

    outputs = [
        Output(display_name="Classification", name="result", method="classify"),
    ]

    async def classify(self) -> Message:
        """Classify the input text and return the class id or mapped class name."""
        text = str(self.input_text or "").strip()
        if not text:
            msg = "Input text is empty."
            raise ValueError(msg)

        config = await self._get_model_config()
        vocab = self._read_vocab()
        id_to_name = self._parse_label_mapping()

        try:
            import numpy as np
            import tritonclient.grpc as grpcclient
        except ImportError as e:
            msg = (
                "Micro model classification requires extra dependencies. "
                "Install them with: pip install numpy tritonclient[grpc]"
            )
            raise ImportError(msg) from e

        grpc_url = config["grpc_url"]
        model_name = config["model"]
        client = grpcclient.InferenceServerClient(url=grpc_url)
        try:
            if not (client.is_server_ready() and client.is_model_ready(model_name)):
                msg = f"Triton server at '{grpc_url}' or model '{model_name}' is not ready."
                raise RuntimeError(msg)

            segments = _segment(text, vocab)
            preds = []
            for seg in segments:
                input_ids, attention_mask = _encode(seg, vocab, np)
                inputs = [
                    grpcclient.InferInput("input_ids", [1, MAX_LEN], "INT64"),
                    grpcclient.InferInput("attention_mask", [1, MAX_LEN], "INT64"),
                ]
                inputs[0].set_data_from_numpy(input_ids)
                inputs[1].set_data_from_numpy(attention_mask)
                result = client.infer(
                    model_name=model_name,
                    inputs=inputs,
                    outputs=[grpcclient.InferRequestedOutput("logits")],
                )
                preds.append(int(np.argmax(result.as_numpy("logits"))))
        except RuntimeError:
            raise
        except Exception as e:
            msg = f"Failed to run inference on Triton server at '{grpc_url}' (model '{model_name}'): {e}"
            raise RuntimeError(msg) from e
        finally:
            client.close()

        # Majority vote; ties -> smallest class id (same as the reference client)
        counts = Counter(preds)
        best = max(counts.values())
        final_id = min(k for k, c in counts.items() if c == best)

        if self.output_type == OUTPUT_CLASS_NAME:
            result_text = id_to_name.get(final_id, UNDEFINED_LABEL)
        else:
            result_text = str(final_id)

        self.status = f"segments={len(preds)} preds={preds} final_id={final_id} result={result_text}"
        return Message(text=result_text)

    async def _get_model_config(self) -> dict:
        """Parse the model config JSON resolved from the named global variable.

        With ``load_from_db=True`` on the ``model_variable`` input, the framework's
        ``update_params_with_load_from_db_fields`` resolves the global variable
        (by the name the user picked) into its value *before* this method runs, so
        ``self.model_variable`` already holds the variable's raw value. We just need
        to unwrap it and parse the JSON.
        """
        raw = self.model_variable

        # SecretStr-typed global variables wrap their value; unwrap it.
        if hasattr(raw, "get_secret_value"):
            raw = raw.get_secret_value()

        if not raw or not str(raw).strip():
            msg = (
                "Model config global variable is empty or not found. "
                "Check the 'Model Config Variable' field and that the global variable exists."
            )
            raise ValueError(msg)

        try:
            config = json.loads(str(raw))
        except json.JSONDecodeError as e:
            msg = f"Model config global variable is not a valid JSON string: {e}"
            raise ValueError(msg) from e

        if not isinstance(config, dict):
            msg = "Model config global variable must be a JSON object."
            raise TypeError(msg)

        grpc_url = str(config.get("grpc_url") or "").strip()
        model = str(config.get("model") or "").strip()
        if not grpc_url or not model:
            msg = "Model config global variable must contain non-empty 'grpc_url' and 'model' fields."
            raise ValueError(msg)

        # The gRPC client expects host:port without a URL scheme
        for prefix in ("grpc://", "http://", "https://"):
            if grpc_url.startswith(prefix):
                grpc_url = grpc_url[len(prefix) :]
                break
        return {"grpc_url": grpc_url.rstrip("/"), "model": model}

    def _read_vocab(self) -> dict[str, int]:
        """Load vocab.txt, tolerating Windows backslash paths and surrounding quotes."""
        raw_path = os.path.expandvars(str(self.vocab_path or "").strip().strip("\"'"))
        if not raw_path:
            msg = "Vocab path is empty."
            raise ValueError(msg)

        path = Path(raw_path).expanduser()
        if not path.is_file():
            msg = f"Vocab file not found: '{path}'. Check that the path points to an existing vocab.txt file."
            raise ValueError(msg)

        try:
            return _load_vocab(path)
        except (OSError, UnicodeError) as e:
            msg = f"Failed to read vocab file '{path}': {e}"
            raise ValueError(msg) from e

    def _parse_label_mapping(self) -> dict[int, str]:
        """Build the {class_id: class_name} mapping from the table input, skipping invalid rows."""
        mapping: dict[int, str] = {}
        for row in self.label_mapping or []:
            if not isinstance(row, dict):
                continue
            class_name = str(row.get("class_name") or "").strip()
            try:
                class_id = int(str(row.get("class_id")).strip())
            except (TypeError, ValueError):
                continue
            if class_name:
                mapping[class_id] = class_name
        return mapping
