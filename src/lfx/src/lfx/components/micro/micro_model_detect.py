# ruff: noqa: RUF001
"""Micro model detection component.

Detects objects in an input image with a YOLO-style detection model served by
a Triton Inference Server over gRPC. The inference pipeline mirrors the
reference client: letterbox preprocess -> gRPC inference -> confidence filter
-> cxcywh to xyxy -> letterbox inverse -> per-class NMS, returning bounding
boxes in original-image pixel coordinates.

Note: user-facing strings intentionally use CJK punctuation (full-width
commas/parentheses), which trips RUF001; suppressed file-wide above.
"""

import json
import os
from pathlib import Path

from lfx.custom import Component
from lfx.field_typing.range_spec import RangeSpec
from lfx.io import IntInput, MessageTextInput, Output, SliderInput, StrInput, TableInput
from lfx.schema import Data
from lfx.schema.table import EditMode

INPUT_SIZE_DEFAULT = 640
CONF_THRES_DEFAULT = 0.25
IOU_THRES_DEFAULT = 0.45
UNDEFINED_LABEL = "Undefined"


def _letterbox(img, new_shape, cv2, color=(114, 114, 114)):
    h, w = img.shape[:2]
    r = min(new_shape / h, new_shape / w)
    nh, nw = round(h * r), round(w * r)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    top = (new_shape - nh) // 2
    left = (new_shape - nw) // 2
    bottom = new_shape - nh - top
    right = new_shape - nw - left
    out = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return out, r, (left, top)


def _preprocess(img, input_size, cv2, np):
    lb, r, pad = _letterbox(img, input_size, cv2)
    t4 = lb.astype(np.float32) / 255.0
    t4 = t4.transpose(2, 0, 1)[None, ...]  # 1,3,H,W
    return np.ascontiguousarray(t4), r, pad


def _nms(boxes, scores, iou_thr, np):
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.clip(xx2 - xx1, 0, None)
        h = np.clip(yy2 - yy1, 0, None)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][ovr <= iou_thr]
    return keep


def _postprocess(out, r, pad, orig_hw, conf_thres, iou_thres, np):
    pred = out[0]  # 4+C, N
    boxes_cxcywh = pred[:4, :].T
    cls_scores = pred[4:, :].T
    cls_ids = cls_scores.argmax(1)
    confs = cls_scores.max(1)
    mask = confs > conf_thres
    boxes_cxcywh = boxes_cxcywh[mask]
    cls_ids = cls_ids[mask]
    confs = confs[mask]
    if len(confs) == 0:
        return []

    x, y, w, h = boxes_cxcywh[:, 0], boxes_cxcywh[:, 1], boxes_cxcywh[:, 2], boxes_cxcywh[:, 3]
    x1 = x - w / 2
    y1 = y - h / 2
    x2 = x + w / 2
    y2 = y + h / 2
    boxes_xyxy = np.stack([x1, y1, x2, y2], 1)

    pad_l, pad_t = pad
    boxes_xyxy[:, 0] = (boxes_xyxy[:, 0] - pad_l) / r
    boxes_xyxy[:, 2] = (boxes_xyxy[:, 2] - pad_l) / r
    boxes_xyxy[:, 1] = (boxes_xyxy[:, 1] - pad_t) / r
    boxes_xyxy[:, 3] = (boxes_xyxy[:, 3] - pad_t) / r
    oh, ow = orig_hw
    boxes_xyxy[:, [0, 2]] = np.clip(boxes_xyxy[:, [0, 2]], 0, ow)
    boxes_xyxy[:, [1, 3]] = np.clip(boxes_xyxy[:, [1, 3]], 0, oh)

    keep_all = []
    for c in np.unique(cls_ids):
        idx = np.where(cls_ids == c)[0]
        k = _nms(boxes_xyxy[idx], confs[idx], iou_thres, np)
        keep_all.extend(idx[k].tolist())
    keep_all = sorted(keep_all)
    return [(int(cls_ids[i]), float(confs[i]), boxes_xyxy[i].tolist()) for i in keep_all]


class MicroModelDetectComponent(Component):
    display_name = "微模型目标检测"
    description = (
        "通过 gRPC 调用 Triton Server 上的微模型（YOLO 检测模型）对输入图片进行目标检测，"
        "输出包含分类、置信度与坐标框（原图像素坐标）的 JSON（Detect objects in an image "
        "with a YOLO model served by Triton over gRPC）."
    )
    icon = "crosshair"
    name = "MicroModelDetect"

    inputs = [
        MessageTextInput(
            name="image_path",
            display_name="Image Path",
            info="待检测图片的完整路径（建议使用正斜杠以避免反斜杠转义）。",
            required=True,
        ),
        StrInput(
            name="model_variable",
            display_name="Model Config Variable",
            info=(
                "保存模型配置的全局变量名（勾选 Load from DB 后从全局变量解析）。"
                "变量值为 JSON 字符串，需包含 grpc_url 和 model，例如："
                '{"server_id":"...","base_url":"http://localhost:8000",'
                '"grpc_url":"localhost:8001","model":"hand_detect"}'
            ),
            # Field name must NOT contain "config" or "kwargs": loading.convert_kwargs()
            # treats any such string field as JSON and drops it when parsing fails.
            # load_from_db=True lets the framework resolve the global variable value
            # for us, so the component just parses the resolved JSON.
            load_from_db=True,
            required=True,
        ),
        IntInput(
            name="input_size",
            display_name="Input Size",
            info="模型输入边长（像素），需与模型训练/导出尺寸一致。",
            value=INPUT_SIZE_DEFAULT,
            required=False,
        ),
        SliderInput(
            name="conf_thres",
            display_name="Conf Threshold",
            info="置信度阈值（0-1），低于此值的检测结果被过滤。",
            value=CONF_THRES_DEFAULT,
            range_spec=RangeSpec(min=0, max=1, step=0.01),
            required=False,
        ),
        SliderInput(
            name="iou_thres",
            display_name="IOU Threshold",
            info="NMS 的 IOU 阈值（0-1），高于此值的重叠框被抑制。",
            value=IOU_THRES_DEFAULT,
            range_spec=RangeSpec(min=0, max=1, step=0.01),
            required=False,
        ),
        TableInput(
            name="label_mapping",
            display_name="Label Mapping",
            info="分类 ID 与分类名称的映射表（可选）。未配置的分类输出 Undefined。",
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
        )
    ]

    outputs = [
        Output(display_name="Detections", name="result", method="detect", types=["Data"]),
    ]

    async def detect(self) -> Data:
        """Run object detection on the input image and return a Data object with the detections list."""
        path = self._resolve_image_path()
        config = await self._get_model_config()
        id_to_name = self._parse_label_mapping()
        input_size = int(self.input_size)
        conf_thres = float(self.conf_thres)
        iou_thres = float(self.iou_thres)

        try:
            import cv2
            import numpy as np
            import tritonclient.grpc as grpcclient
            from PIL import Image
        except ImportError as e:
            msg = (
                "Micro model detection requires extra dependencies. "
                'Install them with: pip install numpy opencv-python pillow "tritonclient[grpc]"'
            )
            raise ImportError(msg) from e

        pil = Image.open(path).convert("RGB")
        img = np.array(pil)  # HWC RGB
        orig_hw = img.shape[:2]
        tensor, r, pad = _preprocess(img, input_size, cv2, np)

        grpc_url = config["grpc_url"]
        model_name = config["model"]
        client = grpcclient.InferenceServerClient(url=grpc_url)
        try:
            if not (client.is_server_ready() and client.is_model_ready(model_name)):
                msg = f"Triton server at '{grpc_url}' or model '{model_name}' is not ready."
                raise RuntimeError(msg)

            inp = grpcclient.InferInput("images", [1, 3, input_size, input_size], "FP32")
            inp.set_data_from_numpy(tensor)
            result = client.infer(
                model_name=model_name,
                inputs=[inp],
                outputs=[grpcclient.InferRequestedOutput("output0")],
            )
            out = result.as_numpy("output0")
        except RuntimeError:
            raise
        except Exception as e:
            msg = f"Failed to run inference on Triton server at '{grpc_url}' (model '{model_name}'): {e}"
            raise RuntimeError(msg) from e
        finally:
            client.close()

        dets = _postprocess(out, r, pad, orig_hw, conf_thres, iou_thres, np)
        detections = [
            {
                "class_id": cid,
                "name": id_to_name.get(cid, UNDEFINED_LABEL),
                "confidence": conf,
                "box": {
                    "x1": round(box[0]),
                    "y1": round(box[1]),
                    "x2": round(box[2]),
                    "y2": round(box[3]),
                },
            }
            for cid, conf, box in dets
        ]

        self.status = f"detections={len(detections)} image={path}"
        return Data(data={"detections": detections})

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

    def _resolve_image_path(self) -> Path:
        """Resolve and validate the image path, tolerating Windows backslash paths and surrounding quotes."""
        raw_path = os.path.expandvars(str(self.image_path or "").strip().strip("\"'"))
        if not raw_path:
            msg = "Image path is empty."
            raise ValueError(msg)

        path = Path(raw_path).expanduser()
        if not path.is_file():
            msg = f"Image file not found: '{path}'. Check that the path points to an existing image file."
            raise ValueError(msg)
        return path

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
