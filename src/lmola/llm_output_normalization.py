from __future__ import annotations

import json
import re
from dataclasses import dataclass

import yaml

THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
ALLOWED_STATUSES = {"ok", "unsupported", "backend_unavailable"}


@dataclass
class NormalizationResult:
    parsed: dict | None
    sanitized_text: str
    json_candidates: list[str]
    thought_block_detected: bool
    thought_block_stripped: bool
    prose_wrapper_detected: bool
    repair_attempted: bool
    repair_successful: bool


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _all_balanced_objects(text: str) -> list[str]:
    out: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(text[start : i + 1])
                start = -1
    return out


def _try_parse(candidate: str) -> dict | None:
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except Exception:
        try:
            obj = yaml.safe_load(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None


def normalize_planner_output(raw: str) -> NormalizationResult:
    stripped = raw.strip()
    thought_block_detected = bool(THINK_RE.search(stripped))
    sanitized = THINK_RE.sub("", stripped).strip()
    thought_block_stripped = sanitized != stripped
    candidates: list[str] = [stripped]
    if sanitized and sanitized != stripped:
        candidates.append(sanitized)
    for m in FENCE_RE.finditer(stripped):
        candidates.append(m.group(1).strip())
    for bal in _all_balanced_objects(sanitized or stripped):
        candidates.append(bal.strip())
    uniq: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        if c and c not in seen:
            uniq.append(c)
            seen.add(c)
    parsed = None
    repair_attempted = False
    repair_successful = False
    parsed_candidates = [(_try_parse(c), c) for c in uniq]
    best_score = -1
    for obj, _c in parsed_candidates:
        if not isinstance(obj, dict):
            continue
        status = str(obj.get("status", "")).strip().lower()
        workflow_id = obj.get("workflow_id")
        score = 0
        if "status" in obj:
            score += 3
        if "workflow_id" in obj or status in {"unsupported", "backend_unavailable"}:
            score += 2
        if status in ALLOWED_STATUSES | {"completed", "success", "done", "pending", "running", "error", "unavailable"}:
            score += 2
        if workflow_id is None or isinstance(workflow_id, str):
            score += 1
        if status in {"ok", "completed", "success", "done"} and isinstance(obj.get("input"), dict):
            score += 1
        if score > best_score:
            best_score = score
            parsed = obj
    if parsed is None:
        for obj, _c in parsed_candidates:
            if obj is not None:
                parsed = obj
                break
    bal = _first_balanced_object(sanitized or stripped)
    if parsed is None and bal:
        repair_attempted = True
        parsed = _try_parse(bal.replace("\n", " "))
        repair_successful = parsed is not None
    prose_wrapper_detected = bool(parsed is not None and uniq and uniq[0].strip() != (sanitized or stripped))
    return NormalizationResult(parsed, sanitized or stripped, uniq, thought_block_detected, thought_block_stripped, prose_wrapper_detected, repair_attempted, repair_successful)
