import re
from pathlib import PurePosixPath


CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
INODE_RE = re.compile(r"^[0-9-]+$")


def validate_case_id(case_id: str) -> str:
    if not isinstance(case_id, str) or not CASE_ID_RE.match(case_id):
        raise ValueError(
            "case_id must start with a letter or number and contain only "
            "letters, numbers, underscore, or hyphen"
        )
    return case_id


def worker_name_for_case(case_id: str) -> str:
    safe = validate_case_id(case_id).lower().replace("_", "-")
    return f"sift-worker-{safe}"


def validate_inode(inode: str | None) -> str | None:
    if inode is None or inode == "":
        return None
    if not INODE_RE.match(str(inode)):
        raise ValueError("inode must contain only digits and hyphens")
    return str(inode)


def validate_container_path(path: str, allowed_prefixes: tuple[str, ...]) -> str:
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("path must be an absolute container path")
    normalized = str(PurePosixPath(path))
    if ".." in PurePosixPath(path).parts:
        raise ValueError("path traversal is not allowed")
    if not any(normalized == p.rstrip("/") or normalized.startswith(p) for p in allowed_prefixes):
        raise ValueError(f"path must be under one of: {', '.join(allowed_prefixes)}")
    return normalized


def extraction_path(case_id: str, filename: str) -> str:
    validate_case_id(case_id)
    name = PurePosixPath(filename).name
    if not name or name in {".", ".."}:
        raise ValueError("filename must include a safe basename")
    if ".." in PurePosixPath(filename).parts:
        raise ValueError("filename path traversal is not allowed")
    return f"/cases/{case_id}/extractions/{name}"
