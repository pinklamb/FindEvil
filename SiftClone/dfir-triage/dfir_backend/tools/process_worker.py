import datetime

from storage.case_store import require_case
from tools.docker_manager import docker_run
from utils.validation import validate_case_id


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def list_processes(case_id: str, max_processes: int = 50) -> dict:
    case_id = validate_case_id(case_id)
    case = require_case(case_id)
    max_processes = min(max(int(max_processes), 1), 200)
    cmd = ["ps", "aux", "--sort=-%cpu"]
    rc, stdout, stderr = docker_run(
        ["exec", case["worker_container"], *cmd],
        timeout=30,
    )
    if rc != 0:
        return {"error": stderr[:300], "tool": "ps"}

    processes = []
    for line in stdout.strip().splitlines()[1 : max_processes + 1]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        command = parts[10]
        flags = []
        for marker in ["/tmp/", "/dev/shm/", "bash -i", " nc ", "powershell"]:
            if marker.lower() in command.lower():
                flags.append(f"suspicious_command:{marker.strip()}")
        processes.append(
            {
                "user": parts[0],
                "pid": parts[1],
                "cpu_pct": parts[2],
                "mem_pct": parts[3],
                "command": command[:300],
                "flags": flags,
                "suspicious": bool(flags),
            }
        )
    return {
        "collected_at": _now(),
        "worker": "process_worker",
        "tool": "ps",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": "live_worker_container",
        "process_count": len(processes),
        "suspicious_count": sum(1 for p in processes if p["suspicious"]),
        "processes": processes,
        "command_args": cmd,
    }
