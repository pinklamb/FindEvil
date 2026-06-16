import os
import re
from pathlib import Path, PurePosixPath


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("DFIR_DATA_ROOT", PROJECT_ROOT))
EVIDENCE_ROOT = DATA_ROOT / "evidence"
CASES_CONTAINER_PATH = os.getenv("CASES_CONTAINER_PATH", "/cases")

ACCEPTED_EVIDENCE_EXTENSIONS = {
    ".e01",
    ".ex01",
}


def _safe_filename(name: str) -> str:
    basename = Path(name).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    if not safe:
        raise ValueError("filename must include a safe basename")
    return safe


def is_accepted_evidence_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in ACCEPTED_EVIDENCE_EXTENSIONS


def evidence_container_path(host_path: Path) -> str:
    resolved = host_path.resolve()
    root = EVIDENCE_ROOT.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("evidence file must be under evidence/")
    relative = resolved.relative_to(root).as_posix()
    if ".." in PurePosixPath(relative).parts:
        raise ValueError("path traversal is not allowed")
    return f"{CASES_CONTAINER_PATH.rstrip('/')}/{relative}"


def list_evidence_files() -> dict:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    files = []
    for path in EVIDENCE_ROOT.rglob("*"):
        if not path.is_file() or not is_accepted_evidence_file(path):
            continue
        relative = path.relative_to(EVIDENCE_ROOT).as_posix()
        files.append(
            {
                "name": path.name,
                "relative_path": relative,
                "container_path": evidence_container_path(path),
                "size_bytes": path.stat().st_size,
                "extension": path.suffix.lower(),
                "accepted": True,
            }
        )
    return {
        "evidence_root": str(EVIDENCE_ROOT),
        "container_root": CASES_CONTAINER_PATH,
        "accepted_extensions": sorted(ACCEPTED_EVIDENCE_EXTENSIONS),
        "files": sorted(files, key=lambda item: item["relative_path"].lower()),
    }


def save_uploaded_evidence(filename: str, content: bytes) -> dict:
    target = uploaded_evidence_target(filename)
    target.write_bytes(content)
    return evidence_file_metadata(target)


def uploaded_evidence_target(filename: str) -> Path:
    safe = _safe_filename(filename)
    if not is_accepted_evidence_file(safe):
        raise ValueError(
            "unsupported evidence file type; accepted extensions: "
            + ", ".join(sorted(ACCEPTED_EVIDENCE_EXTENSIONS))
        )
    upload_dir = EVIDENCE_ROOT / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / safe


def evidence_file_metadata(target: Path) -> dict:
    return {
        "name": target.name,
        "relative_path": target.relative_to(EVIDENCE_ROOT).as_posix(),
        "container_path": evidence_container_path(target),
        "size_bytes": target.stat().st_size,
        "extension": target.suffix.lower(),
        "accepted": True,
    }


def auto_case_id_from_evidence(container_path: str) -> str:
    stem = Path(container_path).stem.upper()
    safe = re.sub(r"[^A-Z0-9]+", "-", stem).strip("-")
    safe = safe[:32] or "EVIDENCE"
    return f"CASE-{safe}-001"
