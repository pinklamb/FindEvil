import datetime
import json
import os
import shutil
from pathlib import Path

from utils.validation import validate_case_id, worker_name_for_case


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("DFIR_DATA_ROOT", PROJECT_ROOT))
STORE_PATH = DATA_ROOT / "storage" / "case_store.json"
DEFAULT_WORKER_IMAGE = os.getenv("SIFT_WORKER_IMAGE", "dfir-sift-worker:latest")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _ensure_store() -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        STORE_PATH.write_text("{}", encoding="utf-8")


def _load_cases() -> dict:
    _ensure_store()
    with open(STORE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_cases(cases: dict) -> None:
    _ensure_store()
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)


def create_case(
    case_id: str,
    evidence_path: str,
    worker_container: str | None = None,
    container_image: str | None = None,
) -> dict:
    case_id = validate_case_id(case_id)
    cases = _load_cases()
    if case_id in cases:
        case = cases[case_id]
        case.setdefault("case_dir", f"/cases/{case_id}")
        case.setdefault("extractions_dir", f"/cases/{case_id}/extractions")
        case.setdefault("worker_container", worker_container or worker_name_for_case(case_id))
        case.setdefault("container_image", container_image or DEFAULT_WORKER_IMAGE)
        case.setdefault("trace_ids", [])
        case.setdefault("finding_ids", [])
        case.setdefault("evidence_ids", [])
        case.setdefault("image_path", None)
        case.setdefault("filesystem", None)
        case.setdefault("offset", None)
        case["updated_at"] = _now()
        _save_cases(cases)
        return cases[case_id]

    case_dir = f"/cases/{case_id}"
    case = {
        "case_id": case_id,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "created",
        "evidence_path": evidence_path,
        "case_dir": case_dir,
        "extractions_dir": f"{case_dir}/extractions",
        "worker_container": worker_container or worker_name_for_case(case_id),
        "container_image": container_image or DEFAULT_WORKER_IMAGE,
        "image_path": None,
        "filesystem": None,
        "offset": None,
        "finding_ids": [],
        "evidence_ids": [],
        "trace_ids": [],
    }
    cases[case_id] = case
    _save_cases(cases)
    return case


def update_case(case_id: str, **updates) -> dict:
    case_id = validate_case_id(case_id)
    cases = _load_cases()
    if case_id not in cases:
        raise ValueError(f"Case not found: {case_id}")
    cases[case_id].update(updates)
    cases[case_id]["updated_at"] = _now()
    _save_cases(cases)
    return cases[case_id]


def set_case_worker_image(case_id: str, container_image: str = DEFAULT_WORKER_IMAGE) -> dict:
    return update_case(case_id, container_image=container_image)


def update_mount_info(case_id: str, image_path: str, filesystem: str, offset: str) -> dict:
    return update_case(
        case_id,
        image_path=image_path,
        filesystem=filesystem,
        offset=offset,
        status="mounted",
    )


def _append_unique(case_id: str, key: str, value: str) -> dict:
    case_id = validate_case_id(case_id)
    cases = _load_cases()
    if case_id not in cases:
        raise ValueError(f"Case not found: {case_id}")
    cases[case_id].setdefault(key, [])
    if value not in cases[case_id][key]:
        cases[case_id][key].append(value)
    cases[case_id]["updated_at"] = _now()
    _save_cases(cases)
    return cases[case_id]


def add_finding(case_id: str, finding_id: str) -> dict:
    return _append_unique(case_id, "finding_ids", finding_id)


def add_evidence(case_id: str, evidence_id: str) -> dict:
    return _append_unique(case_id, "evidence_ids", evidence_id)


def add_trace(case_id: str, trace_id: str) -> dict:
    return _append_unique(case_id, "trace_ids", trace_id)


def get_case(case_id: str) -> dict | None:
    case_id = validate_case_id(case_id)
    return _load_cases().get(case_id)


def require_case(case_id: str) -> dict:
    case = get_case(case_id)
    if not case:
        raise ValueError(f"Case not found: {case_id}")
    return case


def list_cases() -> dict:
    return _load_cases()


def delete_case(case_id: str, remove_case_data: bool = True) -> dict:
    case_id = validate_case_id(case_id)
    cases = _load_cases()
    removed = cases.pop(case_id, None)
    _save_cases(cases)
    data_path = DATA_ROOT / "evidence" / case_id
    if remove_case_data and data_path.exists():
        shutil.rmtree(data_path)
    return {"case_id": case_id, "removed": removed is not None, "data_path_removed": remove_case_data}
