"""Pure helpers for evidence-first Map-Reduce-Verify analysis."""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any


class JsonPayloadError(ValueError):
    """Raised when a model response does not contain the expected JSON value."""


def split_transcript(text: str, *, max_chars: int = 6000) -> list[str]:
    """Split a transcript at paragraph/sentence boundaries without dropping text."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    def flush() -> None:
        nonlocal current, current_size
        if current:
            chunks.append("\n\n".join(current))
            current = []
            current_size = 0

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            flush()
            sentences = [part.strip() for part in re.split(r"(?<=[。！？.!?])\s*", paragraph) if part.strip()]
            fragment = ""
            for sentence in sentences:
                if fragment and len(fragment) + 1 + len(sentence) > max_chars:
                    chunks.append(fragment)
                    fragment = sentence
                elif not fragment and len(sentence) > max_chars:
                    for start in range(0, len(sentence), max_chars):
                        chunks.append(sentence[start:start + max_chars])
                else:
                    fragment = f"{fragment} {sentence}".strip()
            if fragment:
                chunks.append(fragment)
            continue

        separator = 2 if current else 0
        if current and current_size + separator + len(paragraph) > max_chars:
            flush()
        current.append(paragraph)
        current_size += separator + len(paragraph)
    flush()
    return chunks


def parse_json_payload(raw: str, expected_type: type) -> Any:
    """Extract the first valid JSON object/array from a model response."""
    decoder = json.JSONDecoder()
    text = (raw or "").strip().replace("```json", "").replace("```", "")
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, expected_type):
            return value
    raise JsonPayloadError(f"未找到 {expected_type.__name__} JSON")


def _normalize_evidence(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def verify_analysis_payload(payload: dict[str, Any], transcript: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep only list items whose evidence quote is present in the source."""
    verified = deepcopy(payload)
    source = _normalize_evidence(transcript)
    report: dict[str, Any] = {"verified": {}, "rejected": {}}

    for field in ("highlights", "glossary", "chapters", "flashcards", "deep_questions"):
        items = payload.get(field, []) or []
        kept: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            evidence = _normalize_evidence(str(item.get("evidence", "")))
            if evidence and evidence in source:
                kept.append(item)
            else:
                rejected.append(item)
        verified[field] = kept
        report["verified"][field] = len(kept)
        report["rejected"][field] = len(rejected)
    return verified, report
