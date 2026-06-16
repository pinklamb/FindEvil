import datetime
import os

from storage.case_store import require_case
from tools.docker_manager import docker_run
from utils.validation import validate_case_id


ARTIFACT_RULES = [
    ("event_log", ("windows/system32/winevt/logs/", ".evtx")),
    ("prefetch", ("windows/prefetch/", ".pf")),
    ("registry_hive", ("windows/system32/config/", "")),
    ("amcache", ("appcompat/programs/amcache.hve", "")),
    ("scheduled_task", ("windows/system32/tasks/", "")),
    ("powershell_history", ("psreadline/consolehost_history.txt", "")),
    ("lnk", (".lnk", "")),
    ("jump_list", ("automaticdestinations", ".automaticdestinations-ms")),
    ("recycle_bin", ("$recycle.bin", "")),
    ("browser_history", ("users/", "history")),
]

REGISTRY_HIVE_NAMES = {"sam", "security", "software", "system", "default"}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _run(case_id: str, cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    case = require_case(case_id)
    return docker_run(["exec", "--user", "root", case["worker_container"], *cmd], timeout=timeout)


def _get_mount(case_id: str) -> tuple[dict, str, str, str]:
    case = require_case(validate_case_id(case_id))
    if not case.get("image_path"):
        raise ValueError(f"Case {case_id} is not mounted; call mount_e01 first")
    return case, case["image_path"], case["filesystem"], case["offset"]


def _parse_fls_recursive(stdout: str, max_entries: int) -> list[dict]:
    artifacts = []
    for line in stdout.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        path = path.strip()
        parts = meta.strip().split()
        if not parts:
            continue
        inode = parts[-1].rstrip(":")
        ftype = parts[0]
        deleted = "(deleted)" in path
        clean_path = path.replace(" (deleted)", "")
        name = clean_path.rsplit("/", 1)[-1]
        lower_path = clean_path.lower().replace("\\", "/")
        lower_name = name.lower()

        categories = []
        for category, (needle, suffix) in ARTIFACT_RULES:
            if needle and needle not in lower_path:
                continue
            if suffix and not lower_path.endswith(suffix):
                continue
            categories.append(category)
        if lower_path.startswith("windows/system32/config/") and lower_name in REGISTRY_HIVE_NAMES:
            categories.append("registry_hive")

        if not categories:
            continue

        artifacts.append(
            {
                "name": name,
                "path": clean_path,
                "inode": inode,
                "type": "dir" if ftype.startswith("d") else "file",
                "deleted": deleted,
                "extension": os.path.splitext(name)[1].lower(),
                "categories": sorted(set(categories)),
                "ui_hint": "extractable" if not ftype.startswith("d") else "browseable",
            }
        )
        if len(artifacts) >= max_entries:
            break
    return artifacts


def inventory_artifacts(case_id: str, max_entries: int = 500) -> dict:
    case, image_path, fs_type, offset = _get_mount(case_id)
    max_entries = min(max(int(max_entries), 1), 5000)
    cmd = ["fls", "-r", "-p", "-f", fs_type, "-o", offset, image_path]
    rc, stdout, stderr = _run(case_id, cmd, timeout=300)
    if rc != 0 and not stdout:
        return {"error": stderr[:500], "tool": "fls_recursive"}
    artifacts = _parse_fls_recursive(stdout, max_entries)
    category_counts = {}
    for artifact in artifacts:
        for category in artifact["categories"]:
            category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "collected_at": _now(),
        "worker": "artifact_worker",
        "tool": "inventory_artifacts",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": case["evidence_path"],
        "image": image_path,
        "filesystem": fs_type,
        "offset": offset,
        "artifact_count": len(artifacts),
        "category_counts": category_counts,
        "artifacts": artifacts,
        "command_args": cmd,
    }


def pick_priority_artifacts(artifacts: list[dict], limit: int = 25) -> list[dict]:
    priority = {
        "event_log": 10,
        "amcache": 9,
        "registry_hive": 8,
        "scheduled_task": 7,
        "powershell_history": 7,
        "prefetch": 6,
        "browser_history": 5,
        "jump_list": 4,
        "lnk": 3,
        "recycle_bin": 2,
    }

    def score(artifact: dict) -> tuple[int, str]:
        best = max((priority.get(c, 0) for c in artifact.get("categories", [])), default=0)
        return (-best, artifact.get("path", ""))

    files = [a for a in artifacts if a.get("type") == "file"]
    return sorted(files, key=score)[: max(1, min(int(limit), 100))]
