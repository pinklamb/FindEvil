import datetime
import os
import re
import subprocess

from storage.case_store import create_case, require_case, update_mount_info
from tools.docker_manager import docker_run
from utils.validation import validate_case_id, validate_container_path


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _run(case_id: str, cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    case = require_case(case_id)
    full_cmd = ["exec", "--user", "root", case["worker_container"], *cmd]
    return docker_run(full_cmd, timeout=timeout)


SOURCE_HASH_TIMEOUT = int(os.getenv("SOURCE_HASH_TIMEOUT", "10"))
HASH_SOURCE_ON_MOUNT = os.getenv("HASH_SOURCE_ON_MOUNT", "false").lower() == "true"


def _sha256_in_worker(case_id: str, path: str) -> str | None:
    rc, stdout, _ = _run(case_id, ["sha256sum", path], timeout=SOURCE_HASH_TIMEOUT)
    if rc != 0 or not stdout.strip():
        return None
    return stdout.split()[0]


def mount_e01(case_id: str, e01_path: str) -> dict:
    case_id = validate_case_id(case_id)
    e01_path = validate_container_path(e01_path, ("/cases/",))
    case = create_case(case_id=case_id, evidence_path=e01_path)

    mount_dir = f"/mnt/ewf/{case_id}"
    image_path = f"{mount_dir}/ewf1"

    rc, _, err = _run(case_id, ["mkdir", "-p", mount_dir])
    if rc != 0:
        return {"error": f"mkdir failed: {err[:200]}", "tool": "mkdir"}

    rc, stdout, _ = _run(case_id, ["ls", mount_dir])
    already_mounted = "ewf1" in stdout
    if not already_mounted:
        rc, _, stderr = _run(case_id, ["ewfmount", e01_path, mount_dir], timeout=120)
        if rc != 0 and "not empty" not in stderr and "already" not in stderr.lower():
            return {"error": stderr[:300], "tool": "ewfmount"}

    rc, stdout, _ = _run(case_id, ["ls", mount_dir])
    if "ewf1" not in stdout:
        return {"error": f"ewf1 not found in {mount_dir} after mount", "tool": "ewfmount"}

    rc, stdout, _ = _run(case_id, ["mmls", image_path])
    offset = "0"
    if rc == 0:
        for line in stdout.splitlines():
            if "NTFS" in line or "Basic data partition" in line:
                parts = line.split()
                if len(parts) >= 3:
                    offset = parts[2]
                    break

    rc, stdout, _ = _run(case_id, ["fsstat", "-o", offset, image_path])
    filesystem = "ntfs"
    if rc == 0:
        fs_match = re.search(r"File System Type:\s*(.+)", stdout)
        if fs_match:
            filesystem = fs_match.group(1).strip().lower()

    update_mount_info(case_id, image_path=image_path, filesystem=filesystem, offset=offset)
    source_sha256 = None
    if HASH_SOURCE_ON_MOUNT:
        try:
            source_sha256 = _sha256_in_worker(case_id, e01_path)
        except subprocess.TimeoutExpired:
            source_sha256 = None

    return {
        "collected_at": _now(),
        "worker": "mount_worker",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": e01_path,
        "source_sha256": source_sha256,
        "source_sha256_status": "not_requested" if source_sha256 is None else "complete",
        "image_path": image_path,
        "filesystem": filesystem,
        "offset": offset,
        "status": "mounted",
        "command_args": [
            "ewfmount",
            e01_path,
            mount_dir,
            "mmls",
            image_path,
            "fsstat",
            "-o",
            offset,
            image_path,
        ],
    }
