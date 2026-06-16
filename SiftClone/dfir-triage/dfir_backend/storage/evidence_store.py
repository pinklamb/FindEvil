import datetime
import json
import os
from pathlib import Path

from storage.case_store import add_evidence
from storage.ids import next_id
from utils.validation import validate_case_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("DFIR_DATA_ROOT", PROJECT_ROOT))


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _store_path(case_id: str) -> Path:
    case_id = validate_case_id(case_id)
    return DATA_ROOT / "evidence" / case_id / "evidence_store.jsonl"


def _ensure_store(case_id: str) -> Path:
    path = _store_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    return path


def list_evidence(case_id: str, worker: str | None = None) -> list[dict]:
    path = _ensure_store(case_id)
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if worker is None or entry.get("worker") == worker:
                entries.append(entry)
    return entries


def next_evidence_id(case_id: str) -> str:
    return next_id(list_evidence(case_id), "evidence_id", "EV", case_id)


def write_evidence(
    case_id: str,
    evidence_id: str,
    worker: str,
    tool: str,
    artifact_path: str,
    result_summary: dict,
    trace_id: str | None = None,
) -> dict:
    validate_case_id(case_id)
    path = _ensure_store(case_id)
    entry = {
        "case_id": case_id,
        "evidence_id": evidence_id,
        "trace_id": trace_id,
        "collected_at": _now(),
        "worker": worker,
        "tool": tool,
        "artifact_path": artifact_path,
        "result_summary": result_summary,
        "ui_link": f"/cases/{case_id}/evidence/{evidence_id}",
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    add_evidence(case_id, evidence_id)
    return entry


def get_evidence(case_id: str, evidence_id: str) -> dict | None:
    for entry in list_evidence(case_id):
        if entry.get("evidence_id") == evidence_id:
            return entry
    return None
