"""BERT text classification component backed by a Triton Inference Server gRPC model.

Faithful Python port of ``BertClassifier.java`` + ``BertTokenizer.java`` semantics:

- Greedy longest-match BERT tokenizer (NOT HuggingFace WordPiece).
- Long text: tokenize -> sliding window (effective_window = MAX_LEN-2 = 510,
  STRIDE = 200) -> rebuild each window text -> re-tokenize -> encode -> infer
  -> argmax -> majority vote across segments.
- Inputs:  input_ids[1,MAX_LEN] int64, attention_mask[1,MAX_LEN] int64.
- Output:  logits[1,N] fp32 -> argmax -> class id.

Component inputs (4 total):
    1. input_text   - the text to classify.
    2. model_config - name of a global variable whose value is a JSON object
       (as registered by the "Add Models to Global Variables" feature):
        {
          "server_id":   "96370f7e-35f4-4810-8bb8-7892666ae048",  # registered server id
          "base_url":    "http://localhost:8000",   # Triton HTTP URL
          "grpc_url":    "localhost:8001",          # Triton gRPC URL (host:rpc_port)
          "model":       "9636"                     # model name (also accepts "model_name")
        }
       Optional keys (defaults shown):
          "model_version": "",    # "" = latest
          "max_len":      512,     # BERT max sequence length
          "stride":       200,     # sliding-window stride
          "class_labels": [...]    # positional label fallback per class id
    3. vocab_path            - absolute path to the BERT vocab.txt.
    4. class_label_mapping   - optional {class_id: label} map. When provided,
       the component emits the mapped label directly. Behavior:
          - mapping configured + id present  -> mapped label
          - mapping configured + id missing -> "undefined"
          - mapping empty                   -> the raw class id (string)
"""

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.inputs.inputs import MessageTextInput, MultilineInput, NestedDictInput
from lfx.io import Output
from lfx.schema.data import Data
from lfx.schema.message import Message

# Constants — keep in sync with BertClassifier.java
EFFECTIVE_WINDOW_OFFSET = 2  # room for [CLS] ... [SEP]
DEFAULT_MAX_LEN = 512
DEFAULT_STRIDE = 200


class BertTokenizer:
    """Greedy longest-match tokenizer matching the Java implementation 1:1."""

    def __init__(self, vocab_path: str, max_len: int = DEFAULT_MAX_LEN) -> None:
        with Path(vocab_path).open(encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f]
        # Java does `lines.get(i).trim()` — strip trailing \r for CRLF files.
        self.vocab: dict[str, int] = {tok: i for i, tok in enumerate(line.strip() for line in lines)}
        self.unk_token_id = self.vocab.get("[UNK]", 100)
        self.pad_token_id = self.vocab["[PAD]"]
        self.max_len = max_len

    def tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            if text[i] == " ":
                i += 1
                continue
            max_len = 0
            token = "[UNK]"  # noqa: S105 - not a password, BERT special token
            # extend greedily while the (lowercased) substring is in vocab
            while i + max_len < n:
                substr = text[i : i + max_len + 1].lower()
                if substr in self.vocab:
                    token = substr
                    max_len += 1
                else:
                    break
            tokens.append(token if max_len > 0 else "[UNK]")
            # Java: i += maxLen > 0 ? (maxLen - 1) : 0;  then loop does i++
            i += (max_len - 1) if max_len > 0 else 0
            i += 1  # the for-loop increment in Java
        return tokens

    @staticmethod
    def rebuild_text(tokens: list[str]) -> str:
        # Java: String.join(" ", tokens)
        return " ".join(tokens)

    def encode(self, text: str) -> tuple[Any, Any]:
        """Return (input_ids[1,MAX_LEN] int64, attention_mask[1,MAX_LEN] int64)."""
        import numpy as np

        tokens: list[str] = ["[CLS]"]
        tokens.extend(self.tokenize(text))
        tokens.append("[SEP]")

        input_ids = np.full((1, self.max_len), self.pad_token_id, dtype=np.int64)
        attention_mask = np.zeros((1, self.max_len), dtype=np.int64)

        length = min(len(tokens), self.max_len)
        input_ids[0, :length] = [self.vocab.get(t, self.unk_token_id) for t in tokens[:length]]
        attention_mask[0, :length] = 1
        return input_ids, attention_mask


class TritonBertClassifierComponent(Component):
    display_name = "Triton BERT Classifier"
    description = (
        "Classify text using a BERT model served by NVIDIA Triton Inference Server via gRPC. "
        "Model connection settings come from a JSON global variable (model_config)."
    )
    documentation: str = "https://docs.langflow.org/"
    icon = "brain-circuit"
    name = "TritonBertClassifier"

    inputs = [
        MultilineInput(
            name="input_text",
            display_name="Input Text",
            info="The text to classify.",
            tool_mode=True,
        ),
        MessageTextInput(
            name="model_config",
            display_name="Model Config",
            info=(
                "Pick a global variable whose value is the model JSON config, "
                'or paste the JSON directly. Expected keys: "server_id", '
                '"base_url" (http), "grpc_url" (gRPC), "model" (also accepts '
                '"model_name"); optional "model_version", "max_len", '
                '"stride", "class_labels".'
            ),
            load_from_db=True,
            refresh_button=True,
        ),
        MessageTextInput(
            name="vocab_path",
            display_name="Vocab Path",
            info="Absolute path to the BERT vocab.txt used to tokenize input text.",
        ),
        NestedDictInput(
            name="class_label_mapping",
            display_name="Class Label Mapping",
            info=(
                "Optional {class_id: label} map. When configured, the component "
                "outputs the mapped label directly. Ids missing from the map "
                'yield "undefined"; an empty map falls back to the raw class id.'
            ),
            value={},
            required=False,
        ),
    ]

    outputs = [
        Output(display_name="Classification", name="classification", method="classify"),
        Output(display_name="Result Data", name="result_data", type_=Data, method="get_result_data"),
    ]

    # -- shared prediction (computed once and cached on the instance) ----------
    _cached_prediction: dict[str, Any] | None = None

    def _parse_model_config(self) -> dict[str, Any]:
        """Resolve model_config (global variable name or JSON string) into a dict.

        Accepts, in order:
        1. A dict (already resolved by the framework's ``load_from_db`` path).
        2. A JSON object string (pasted directly).
        3. A bare global variable name — resolved here as a fallback when the
           framework's ``load_from_db`` resolution did not replace the field
           value with the variable's content. Looks up the variable via the
           variable service (DB / request-scoped / env) and parses the result.
        """
        raw = self.model_config
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            msg = f"Unsupported model_config type: {type(raw).__name__}"
            raise TypeError(msg)

        text = raw.strip()
        if not text:
            msg = "Model config is empty. Pick a global variable or paste a JSON object."
            raise ValueError(msg)

        # Direct JSON paste.
        if text.startswith("{"):
            return self._parse_json_config(text)

        # Bare variable name — resolve it ourselves so the component works even
        # when the framework's load_from_db resolution doesn't kick in.
        resolved = self._resolve_global_variable(text)
        if resolved is None:
            msg = (
                f"Could not resolve global variable '{text}'. "
                "Pick a global variable via the dropdown, create one with this "
                "name containing the JSON config, or paste the JSON directly."
            )
            raise ValueError(msg)
        if isinstance(resolved, dict):
            return resolved
        if not isinstance(resolved, str):
            msg = f"Global variable '{text}' resolved to {type(resolved).__name__}, expected a JSON object string."
            raise TypeError(msg)
        resolved = resolved.strip()
        if not resolved.startswith("{"):
            msg = f"Global variable '{text}' does not contain a JSON object. Got: {resolved[:80]!r}..."
            raise ValueError(msg)
        return self._parse_json_config(resolved)

    def _resolve_global_variable(self, name: str) -> str | dict | None:
        """Resolve a global variable name to its value.

        Resolution order (first match wins), mirroring the credentials helper:
        1. Variable service (DB for the current user when available, then
           request-scoped variables, then environment variables).
        2. Active request variables (sync ContextVar lookup).
        3. ``os.environ`` (unless the request disabled env fallback).
        """
        from uuid import UUID

        from lfx.services.deps import get_variable_service, session_scope
        from lfx.services.variable.request_scope import (
            get_active_request_variables,
            is_env_fallback_disabled,
        )
        from lfx.utils.async_helpers import run_until_complete

        user_id = self.user_id
        has_user = user_id is not None and not (isinstance(user_id, str) and user_id == "None")

        if has_user:

            async def _get() -> str | None:
                async with session_scope() as session:
                    vs = get_variable_service()
                    if vs is None:
                        return None
                    uid = UUID(user_id) if isinstance(user_id, str) else user_id
                    try:
                        return await vs.get_variable(
                            user_id=uid,
                            name=name,
                            field="model_config",
                            session=session,
                        )
                    except (ValueError, TypeError):
                        return None

            value = run_until_complete(_get())
            if value:
                return value

        # Sync fallbacks for the no-user / lfx run / lfx serve path.
        request_vars = get_active_request_variables()
        if request_vars and name in request_vars:
            return request_vars[name]

        if not is_env_fallback_disabled():
            env_value = os.environ.get(name)
            if env_value and env_value.strip():
                return env_value.strip()
        return None

    @staticmethod
    def _parse_json_config(text: str) -> dict[str, Any]:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            msg = f"Model config is not valid JSON: {e}"
            raise ValueError(msg) from e
        if not isinstance(parsed, dict):
            msg = "Model config JSON must be a JSON object."
            raise TypeError(msg)
        return parsed

    def _predict(self) -> dict[str, Any]:
        if self._cached_prediction is not None:
            return self._cached_prediction

        text = (self.input_text or "").strip()
        if not text:
            error = "Input text is empty."
            self.status = error
            self._cached_prediction = {"error": error, "text_summary": error, "data": {"error": error}}
            return self._cached_prediction

        try:
            config = self._parse_model_config()
        except (ValueError, TypeError) as e:
            error = f"Invalid model config: {e}"
            self.status = error
            self._cached_prediction = {"error": error, "text_summary": error, "data": {"error": error}}
            return self._cached_prediction

        grpc_url = config.get("grpc_url") or config.get("rpc_url")
        model_name = config.get("model_name") or config.get("model")
        model_version = config.get("model_version") or ""
        max_len = int(config.get("max_len") or DEFAULT_MAX_LEN)
        stride = int(config.get("stride") or DEFAULT_STRIDE)
        class_labels = config.get("class_labels") or []
        effective_window = max_len - EFFECTIVE_WINDOW_OFFSET

        if not grpc_url:
            error = 'Model config JSON is missing the "grpc_url" field (e.g. "localhost:8001").'
            self.status = error
            self._cached_prediction = {"error": error, "text_summary": error, "data": {"error": error}}
            return self._cached_prediction
        if not model_name:
            error = 'Model config JSON is missing the "model_name" (or "model") field.'
            self.status = error
            self._cached_prediction = {"error": error, "text_summary": error, "data": {"error": error}}
            return self._cached_prediction

        try:
            import tritonclient.grpc as grpcclient  # type: ignore[import-not-found]
        except ImportError as e:
            msg = (
                "Could not import 'tritonclient'. Install it with: pip install tritonclient[all] "
                "(or pip install tritonclient)."
            )
            raise ImportError(msg) from e

        tokenizer = BertTokenizer(self.vocab_path, max_len=max_len)
        client = grpcclient.InferenceServerClient(url=grpc_url, verbose=False)

        # Health checks
        if not client.is_server_live():
            error = f"Triton server at {grpc_url} is not live."
            self.status = error
            self._cached_prediction = {"error": error, "text_summary": error, "data": {"error": error}}
            return self._cached_prediction
        if not client.is_server_ready():
            error = f"Triton server at {grpc_url} is not ready."
            self.status = error
            self._cached_prediction = {"error": error, "text_summary": error, "data": {"error": error}}
            return self._cached_prediction
        if not client.is_model_ready(model_name, model_version):
            error = f"Model '{model_name}' is not ready. Check Triton logs and the model config.pbtxt."
            self.status = error
            self._cached_prediction = {"error": error, "text_summary": error, "data": {"error": error}}
            return self._cached_prediction

        segments = self._segment_text(tokenizer, text, effective_window, stride)
        if not segments:
            segments = [text]

        import numpy as np

        predictions: list[int] = []
        segment_details: list[dict[str, Any]] = []
        for idx, seg in enumerate(segments):
            input_ids, attention_mask = tokenizer.encode(seg)
            logits = self._infer_segment(client, input_ids, attention_mask, max_len, model_name, model_version)
            pred = int(np.argmax(logits[0]))
            predictions.append(pred)
            probs = self._softmax(logits[0])
            segment_details.append(
                {
                    "segment_index": idx,
                    "segment_text": seg,
                    "prediction": pred,
                    "logits": logits[0].tolist(),
                    "probabilities": probs.tolist(),
                }
            )
            self.log(
                f"seg#{idx:02d} len={len(seg)} pred={pred} "
                f"logits={np.array2string(logits[0], precision=4)} "
                f"probs={np.array2string(probs, precision=4)}"
            )

        final = self._majority_vote(predictions)
        label_mapping = self.class_label_mapping or {}
        label = self._label_for_class(final, class_labels=class_labels, label_mapping=label_mapping)

        n_tokens = len(tokenizer.tokenize(text))
        summary = f"Class: {label} (id={final}) | segments={len(predictions)} | tokens~{n_tokens}"
        self.status = summary

        result_data = {
            "final_class_id": final,
            "final_class_label": label,
            "text": text,
            "model_name": model_name,
            "grpc_url": grpc_url,
            "num_segments": len(predictions),
            "per_segment_class_ids": predictions,
            "segments": segment_details,
        }
        self._cached_prediction = {
            "text_summary": summary,
            "label": label,
            "final_class_id": final,
            "data": result_data,
        }
        return self._cached_prediction

    # -- output methods --------------------------------------------------------
    def classify(self) -> Message:
        result = self._predict()
        return Message(text=result["text_summary"])

    def get_result_data(self) -> Data:
        result = self._predict()
        return Data(data=result["data"])

    def build(self):
        """Return the main classification function for use as a tool."""
        return self.classify

    # -- inference helpers (ports of TritonBertClient) -------------------------
    def _infer_segment(self, client, input_ids, attention_mask, max_len, model_name, model_version) -> Any:
        import tritonclient.grpc as grpcclient  # type: ignore[import-not-found]

        in_ids = grpcclient.InferInput("input_ids", [1, max_len], "INT64")
        in_ids.set_data_from_numpy(input_ids)
        in_mask = grpcclient.InferInput("attention_mask", [1, max_len], "INT64")
        in_mask.set_data_from_numpy(attention_mask)
        out = grpcclient.InferRequestedOutput("logits")
        result = client.infer(
            model_name=model_name,
            model_version=model_version,
            inputs=[in_ids, in_mask],
            outputs=[out],
        )
        return result.as_numpy("logits")

    @staticmethod
    def _segment_text(
        tokenizer: BertTokenizer,
        text: str,
        effective_window: int,
        stride: int,
    ) -> list[str]:
        # Java BertClassifier.segmentText
        tokens = tokenizer.tokenize(text)
        segments: list[str] = []
        start = 0
        while start < len(tokens):
            end = min(start + effective_window, len(tokens))
            window_tokens = tokens[start:end]
            segments.append(tokenizer.rebuild_text(window_tokens))
            if end == len(tokens):
                break
            start += stride
        return segments

    @staticmethod
    def _majority_vote(preds: list[int]) -> int:
        # Java: max by count; ties broken by Collections.max (natural order -> smallest id)
        counts = Counter(preds)
        best_count = max(counts.values())
        candidates = [k for k, c in counts.items() if c == best_count]
        return min(candidates)

    @staticmethod
    def _softmax(x) -> Any:
        import numpy as np

        x = x.astype(np.float64)
        e = np.exp(x - np.max(x))
        return e / e.sum()

    @staticmethod
    def _label_for_class(
        class_id: int,
        class_labels: list[str] | None = None,
        label_mapping: dict | None = None,
    ) -> str:
        """Resolve a class id to a human-readable label.

        Resolution order:
        1. ``label_mapping`` (the component's Class Label Mapping input) — when
           non-empty, it is authoritative: a hit returns the mapped label and a
           miss returns ``"undefined"`` (per the component spec).
        2. ``class_labels`` — positional fallback from the model config JSON
           (index ``class_id`` into the list). Backward compatible.
        3. Raw id as a string when neither source is configured.
        """
        if label_mapping:
            # NestedDictInput keys arrive as strings (JSON object keys). Try
            # string first, then int, so users can type either form.
            for key in (str(class_id), class_id):
                if key in label_mapping:
                    return str(label_mapping[key])
            return "undefined"
        if class_labels and 0 <= class_id < len(class_labels):
            return class_labels[class_id]
        return str(class_id)
