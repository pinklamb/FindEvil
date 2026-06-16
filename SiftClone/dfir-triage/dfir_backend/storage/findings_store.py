import datetime
import json
import os
from pathlib import Path

from storage.case_store import add_finding
from storage.ids import next_id
from utils.validation import validate_case_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("DFIR_DATA_ROOT", PROJECT_ROOT))


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _store_path(case_id: str) -> Path:
    case_id = validate_case_id(case_id)
    return DATA_ROOT / "evidence" / case_id / "findings_store.jsonl"


def _ensure_store(case_id: str) -> Path:
    path = _store_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    return path


def list_findings(case_id: str, severity: str | None = None) -> list[dict]:
    path = _ensure_store(case_id)
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if severity is None or entry.get("severity") == severity:
                entries.append(entry)
    return entries


def next_finding_id(case_id: str) -> str:
    return next_id(list_findings(case_id), "finding_id", "FIN", case_id)


def write_finding(
    case_id: str,
    finding_id: str,
    title: str,
    severity: str,
    evidence_refs: list[str],
    rule_ids: list[str],
    confidence: float,
    trace_refs: list[str] | None = None,
    artifact_locations: list[dict] | None = None,
    llm_explanation: str = "",
) -> dict:
    validate_case_id(case_id)
    if not evidence_refs:
        raise ValueError("Finding requires at least one evidence_ref")
    trace_refs = trace_refs or []
    artifact_locations = artifact_locations or []
    path = _ensure_store(case_id)
    entry = {
        "case_id": case_id,
        "finding_id": finding_id,
        "status": "DRAFT",
        "created_at": _now(),
        "title": title,
        "severity": severity,
        "evidence_refs": evidence_refs,
        "trace_refs": trace_refs,
        "artifact_locations": artifact_locations,
        "rule_ids": rule_ids,
        "confidence": confidence,
        "llm_explanation": llm_explanation,
        "llm_explanation_is_evidence": False,
        "ui_link": f"/cases/{case_id}/findings/{finding_id}/trace",
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    add_finding(case_id, finding_id)
    return entry


def get_finding(case_id: str, finding_id: str) -> dict | None:
    for entry in list_findings(case_id):
        if entry.get("finding_id") == finding_id:
            return entry
    return None
