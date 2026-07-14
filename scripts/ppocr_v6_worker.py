"""Batch PP-OCRv6 worker kept outside the legacy PaddleOCR environment."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from paddleocr import PaddleOCR


def _texts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        result: list[str] = []
        for key in ("rec_texts", "texts", "text"):
            item = value.get(key)
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, list):
                result.extend(str(entry) for entry in item)
        for key in ("res", "result", "ocr_result", "data"):
            result.extend(_texts(value.get(key)))
        return result
    if isinstance(value, (list, tuple)):
        result: list[str] = []
        for item in value:
            result.extend(_texts(item))
        return result
    json_value = getattr(value, "json", None)
    return _texts(json_value) if isinstance(json_value, dict) else []


def main() -> int:
    paths = [Path(raw) for raw in sys.argv[1:]]
    pipeline = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        engine="onnxruntime",
    )
    texts: list[str] = []
    for path in paths:
        values: list[str] = []
        for result in pipeline.predict(str(path)):
            values.extend(_texts(result))
        texts.append("\n".join(dict.fromkeys(item.strip() for item in values if item.strip())))
    print(json.dumps({"texts": texts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
