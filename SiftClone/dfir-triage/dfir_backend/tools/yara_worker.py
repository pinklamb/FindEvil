import datetime

from storage.case_store import require_case
from tools.docker_manager import docker_run
from utils.validation import validate_case_id, validate_container_path


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def scan_yara(
    case_id: str,
    target_path: str | None = None,
    rules_path: str = "/cases/shared-rules/dfir_demo.yar",
    timeout: int = 120,
) -> dict:
    case_id = validate_case_id(case_id)
    case = require_case(case_id)
    target_path = target_path or f"/cases/{case_id}/extractions"
    target_path = validate_container_path(target_path, ("/cases/",))
    rules_path = validate_container_path(rules_path, ("/cases/",))
    cmd = ["yara", "-r", rules_path, target_path]
    rc, stdout, stderr = docker_run(
        ["exec", "--user", "root", case["worker_container"], *cmd],
        timeout=timeout,
    )
    if rc not in (0, 1):
        return {"error": stderr[:500], "tool": "yara", "command_args": cmd}

    matches = []
    for line in stdout.splitlines():
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        matches.append(
            {
                "rule": parts[0],
                "path": parts[1] if len(parts) > 1 else "",
            }
        )
    return {
        "collected_at": _now(),
        "worker": "yara_worker",
        "tool": "yara",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": case.get("evidence_path"),
        "target_path": target_path,
        "rules_path": rules_path,
        "match_count": len(matches),
        "matches": matches,
        "command_args": cmd,
    }
