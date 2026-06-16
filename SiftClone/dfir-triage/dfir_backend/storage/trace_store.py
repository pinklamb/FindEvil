import datetime
import json
import os
from pathlib import Path

from storage.case_store import add_trace
from storage.ids import next_id
from utils.validation import validate_case_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("DFIR_DATA_ROOT", PROJECT_ROOT))


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _store_path(case_id: str) -> Path:
    case_id = validate_case_id(case_id)
    return DATA_ROOT / "evidence" / case_id / "trace_store.jsonl"


def _ensure_store(case_id: str) -> Path:
    path = _store_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    return path


def list_traces(case_id: str) -> list[dict]:
    path = _ensure_store(case_id)
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def next_trace_id(case_id: str) -> str:
    return next_id(list_traces(case_id), "trace_id", "TR", case_id)


def write_trace(case_id: str, **fields) -> dict:
    validate_case_id(case_id)
    path = _ensure_store(case_id)
    trace_id = fields.get("trace_id") or next_trace_id(case_id)
    entry = {
        "trace_id": trace_id,
        "case_id": case_id,
        "evidence_id": fields.get("evidence_id"),
        "tool": fields.get("tool"),
        "worker_container": fields.get("worker_container"),
        "container_image": fields.get("container_image"),
        "source_evidence_path": fields.get("source_evidence_path"),
        "source_sha256": fields.get("source_sha256"),
        "filesystem": fields.get("filesystem"),
        "offset": fields.get("offset"),
        "artifact_path": fields.get("artifact_path"),
        "inode": fields.get("inode"),
        "output_path": fields.get("output_path"),
        "output_sha256": fields.get("output_sha256"),
        "command_args": fields.get("command_args", []),
        "started_at": fields.get("started_at"),
        "completed_at": fields.get("completed_at") or now(),
        "status": fields.get("status", "ok"),
        "summary": fields.get("summary", {}),
        "ui_link": f"/cases/{case_id}/artifacts/{trace_id}",
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    add_trace(case_id, trace_id)
    return entry


def get_trace(case_id: str, trace_id: str) -> dict | None:
    for entry in list_traces(case_id):
        if entry.get("trace_id") == trace_id:
            return entry
    return None
