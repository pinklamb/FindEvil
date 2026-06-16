import datetime
import os
import subprocess
from pathlib import Path

from storage.case_store import require_case
from storage.evidence_store import DATA_ROOT
from tools.docker_manager import docker_run
from utils.validation import extraction_path, validate_case_id, validate_inode


SUSPICIOUS_PATHS = [
    "AppData\\Roaming",
    "ProgramData",
    "Recycle",
    "Windows\\Tasks",
]

SUSPICIOUS_EXTENSIONS = [
    ".exe",
    ".dll",
    ".ps1",
    ".bat",
    ".vbs",
    ".js",
]


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _run(case_id: str, cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    case = require_case(case_id)
    full_cmd = ["exec", "--user", "root", case["worker_container"], *cmd]
    return docker_run(full_cmd, timeout=timeout)


def _get_mount(case_id: str) -> tuple[dict, str, str, str]:
    case = require_case(validate_case_id(case_id))
    if not case.get("image_path"):
        raise ValueError(f"Case {case_id} is not mounted; call mount_e01 first")
    return case, case["image_path"], case["filesystem"], case["offset"]


def _flag_entry(name: str, path: str) -> list[str]:
    flags = []
    for sus in SUSPICIOUS_PATHS:
        if sus.lower() in path.lower():
            flags.append(f"suspicious_path:{sus}")
    for ext in SUSPICIOUS_EXTENSIONS:
        if name.lower().endswith(ext):
            flags.append(f"suspicious_ext:{ext}")
    return flags


def _parse_fls_output(stdout: str, parent_path: str, max_entries: int) -> list[dict]:
    entries = []
    for line in stdout.strip().split("\n")[:max_entries]:
        if not line or "\t" not in line:
            continue
        meta, name = line.split("\t", 1)
        name = name.strip()
        parts = meta.strip().split()
        ftype = parts[0] if parts else ""
        inode = parts[-1].rstrip(":") if len(parts) > 1 else ""
        deleted = "(deleted)" in name
        clean = name.replace(" (deleted)", "")
        full_path = f"{parent_path}/{clean}"
        flags = _flag_entry(clean, full_path)
        entries.append(
            {
                "name": clean,
                "path": full_path,
                "path_depth": len(full_path.split("/")),
                "extension": os.path.splitext(clean)[1].lower(),
                "inode": inode,
                "type": "dir" if ftype.startswith("d") else "file",
                "deleted": deleted,
                "flags": flags,
                "suspicious": len(flags) > 0,
            }
        )
    return entries


def list_directory(case_id: str, inode: str | None = None, max_entries: int = 50) -> dict:
    inode = validate_inode(inode)
    case, image_path, fs_type, offset = _get_mount(case_id)
    max_entries = min(max(int(max_entries), 1), 500)
    cmd = ["fls", "-f", fs_type, "-o", offset, image_path]
    if inode:
        cmd.append(inode)
    rc, stdout, stderr = _run(case_id, cmd, timeout=30)
    if rc != 0 and not stdout:
        return {"error": stderr[:200], "tool": "fls", "inode": inode}
    entries = _parse_fls_output(stdout, inode or "root", max_entries)
    return {
        "collected_at": _now(),
        "worker": "filesystem_worker",
        "tool": "fls",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": case["evidence_path"],
        "image": image_path,
        "filesystem": fs_type,
        "offset": offset,
        "inode": inode or "root",
        "entry_count": len(entries),
        "suspicious_count": sum(1 for e in entries if e["suspicious"]),
        "truncated": len(stdout.strip().split("\n")) > max_entries,
        "entries": entries,
        "command_args": cmd,
    }


def list_temp_files(case_id: str, max_entries: int = 100) -> dict:
    case, image_path, fs_type, offset = _get_mount(case_id)
    max_entries = min(max(int(max_entries), 1), 500)

    rc, stdout, _ = _run(case_id, ["fls", "-f", fs_type, "-o", offset, image_path], timeout=15)
    windows_inode = None
    for line in stdout.split("\n"):
        if "\t" not in line:
            continue
        meta, name = line.split("\t", 1)
        if name.strip().lower() == "windows":
            windows_inode = meta.strip().split()[-1].rstrip(":")
            break
    if not windows_inode:
        return {"error": "Windows directory not found", "tool": "fls"}

    rc, stdout, _ = _run(
        case_id,
        ["fls", "-f", fs_type, "-o", offset, image_path, windows_inode],
        timeout=15,
    )
    temp_inode = None
    for line in stdout.split("\n"):
        if "\t" not in line:
            continue
        meta, name = line.split("\t", 1)
        if name.strip().lower() == "temp":
            temp_inode = meta.strip().split()[-1].rstrip(":")
            break
    if not temp_inode:
        return {"error": "Temp directory not found", "tool": "fls"}

    cmd = ["fls", "-f", fs_type, "-o", offset, image_path, temp_inode]
    rc, stdout, stderr = _run(case_id, cmd, timeout=15)
    if rc != 0 and not stdout:
        return {"error": stderr[:200], "tool": "fls_temp"}
    entries = _parse_fls_output(stdout, "Windows/Temp", max_entries)
    return {
        "collected_at": _now(),
        "worker": "filesystem_worker",
        "tool": "fls_temp",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": case["evidence_path"],
        "image": image_path,
        "filesystem": fs_type,
        "offset": offset,
        "windows_inode": windows_inode,
        "temp_inode": temp_inode,
        "entry_count": len(entries),
        "suspicious_count": sum(1 for e in entries if e["suspicious"]),
        "entries": entries,
        "command_args": cmd,
    }


def extract_file(case_id: str, inode: str, filename: str) -> dict:
    inode = validate_inode(inode)
    if not inode:
        raise ValueError("inode is required")
    case, image_path, fs_type, offset = _get_mount(case_id)
    container_output_path = extraction_path(case_id, filename)
    host_output_path = DATA_ROOT / "evidence" / case_id / "extractions" / Path(filename).name
    host_output_path.parent.mkdir(parents=True, exist_ok=True)

    run = subprocess.run(
        [
            "docker",
            "exec",
            "--user",
            "root",
            case["worker_container"],
            "icat",
            "-f",
            fs_type,
            "-o",
            offset,
            image_path,
            inode,
        ],
        capture_output=True,
        timeout=30,
    )
    if run.returncode != 0:
        return {"error": run.stderr.decode(errors="replace")[:200], "tool": "icat", "inode": inode}

    host_output_path.write_bytes(run.stdout)
    size = host_output_path.stat().st_size
    import hashlib

    output_sha256 = hashlib.sha256(run.stdout).hexdigest()
    return {
        "collected_at": _now(),
        "worker": "filesystem_worker",
        "tool": "icat",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": case["evidence_path"],
        "image": image_path,
        "filesystem": fs_type,
        "offset": offset,
        "inode": inode,
        "output_path": str(host_output_path),
        "container_output_path": container_output_path,
        "output_sha256": output_sha256,
        "file_size": size,
        "success": size > 0,
        "command_args": ["icat", "-f", fs_type, "-o", offset, image_path, inode],
    }
