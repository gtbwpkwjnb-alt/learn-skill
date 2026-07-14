"""OCR provider selection: PaddleOCR first, Tesseract only as a safe fallback."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Optional


def _load_skill_env() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_skill_env()


@dataclass
class OcrProvider:
    name: str
    read: Callable[[Path], str]
    fallback_reason: str = ""
    read_many: Optional[Callable[[list[Path]], list[str]]] = None


def _ppocr_python() -> Optional[Path]:
    configured = os.environ.get("LEARN_PPOCR_PYTHON", "")
    candidate = Path(configured) if configured else Path(__file__).resolve().parent.parent / ".venv-ppocr" / "Scripts" / "python.exe"
    return candidate if candidate.is_file() else None


def ppocr_v6_available() -> bool:
    return _ppocr_python() is not None


def paddleocr_installed() -> bool:
    return importlib.util.find_spec("paddleocr") is not None


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None and importlib.util.find_spec("pytesseract") is not None


def _dedupe(lines: list[str]) -> str:
    seen: set[str] = set()
    kept: list[str] = []
    for line in lines:
        text = str(line).strip()
        if text and text not in seen:
            seen.add(text)
            kept.append(text)
    return "\n".join(kept)


def _paddle_texts(value: Any) -> list[str]:
    """Accept both PaddleOCR 2.x tuples and 3.x result dictionaries."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        lines: list[str] = []
        for key in ("rec_texts", "texts", "text"):
            text = value.get(key)
            if isinstance(text, str):
                lines.append(text)
            elif isinstance(text, list):
                lines.extend(str(item) for item in text)
        for key in ("res", "result", "ocr_result", "data"):
            lines.extend(_paddle_texts(value.get(key)))
        return lines
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        return [value[0]]
    if isinstance(value, (list, tuple)):
        lines: list[str] = []
        for item in value:
            lines.extend(_paddle_texts(item))
        return lines
    json_value = getattr(value, "json", None)
    if isinstance(json_value, dict):
        return _paddle_texts(json_value)
    return []


def _build_paddle_reader(factory: Optional[Callable[[], Any]] = None) -> Callable[[Path], str]:
    if factory is None:
        from paddleocr import PaddleOCR

        factory = lambda: PaddleOCR(lang="ch")
    engine = factory()

    def read(image_path: Path) -> str:
        if hasattr(engine, "predict"):
            result = engine.predict(str(image_path))
        else:
            result = engine.ocr(str(image_path), cls=True)
        return _dedupe(_paddle_texts(result))

    return read


def _build_tesseract_reader() -> Callable[[Path], str]:
    import pytesseract
    from PIL import Image

    def read(image_path: Path) -> str:
        return pytesseract.image_to_string(Image.open(str(image_path)), lang="chi_sim+eng").strip()

    return read


def _build_ppocr_v6_reader() -> OcrProvider:
    python = _ppocr_python()
    if python is None:
        raise RuntimeError("PP-OCRv6 isolated environment is not installed")
    worker = Path(__file__).resolve().parent / "ppocr_v6_worker.py"

    def read_many(paths: list[Path]) -> list[str]:
        result = subprocess.run(
            [str(python), str(worker), *[str(path) for path in paths]],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "PP-OCRv6 worker failed")
        payload = json.loads(result.stdout)
        return [str(item).strip() for item in payload.get("texts", [])]

    return OcrProvider("ppocr-v6", lambda path: read_many([path])[0], read_many=read_many)


def select_ocr_provider(
    *,
    paddle_factory: Optional[Callable[[], Any]] = None,
    tesseract_factory: Optional[Callable[[], Callable[[Path], str]]] = None,
) -> Optional[OcrProvider]:
    """Return the strongest usable local provider; never changes dependencies."""
    if ppocr_v6_available() and paddle_factory is None:
        try:
            return _build_ppocr_v6_reader()
        except Exception as error:
            paddle_error = f"PP-OCRv6 初始化失败: {error}"
    else:
        paddle_error = ""
    if paddleocr_installed() or paddle_factory is not None:
        try:
            return OcrProvider("paddleocr", _build_paddle_reader(paddle_factory))
        except Exception as error:
            paddle_error = f"PaddleOCR 初始化失败: {error}"
    if tesseract_available() or tesseract_factory is not None:
        try:
            reader = tesseract_factory() if tesseract_factory else _build_tesseract_reader()
            return OcrProvider("tesseract", reader, fallback_reason=paddle_error)
        except Exception as error:
            paddle_error = f"{paddle_error}; Tesseract 初始化失败: {error}".strip("; ")
    return None
