import os
import subprocess
from pathlib import Path

from storage.case_store import create_case, require_case, update_case
from utils.validation import validate_case_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES_HOST_PATH = os.getenv("CASES_HOST_PATH", str(PROJECT_ROOT / "evidence"))
CASES_CONTAINER_PATH = os.getenv("CASES_CONTAINER_PATH", "/cases")


def docker_run(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        run = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return run.returncode, run.stdout, run.stderr
    except FileNotFoundError:
        return 127, "", "docker executable not found"
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "docker command timed out"


def container_exists(container_name: str) -> bool:
    rc, _, _ = docker_run(["inspect", container_name], timeout=10)
    return rc == 0


def container_running(container_name: str) -> bool:
    rc, stdout, _ = docker_run(
        ["inspect", "-f", "{{.State.Running}}", container_name],
        timeout=10,
    )
    return rc == 0 and stdout.strip().lower() == "true"


def start_case_worker(case_id: str) -> dict:
    case = require_case(validate_case_id(case_id))
    name = case["worker_container"]
    image = case["container_image"]
    docker_available, _, docker_error = docker_run(["version", "--format", "{{.Server.Version}}"], timeout=10)
    if docker_available != 0:
        return {
            "case_id": case_id,
            "worker_container": name,
            "container_image": image,
            "running": False,
            "error": docker_error[:500] or "Docker is not available to the backend container",
            "stage": "docker_unavailable",
        }

    if container_running(name):
        update_case(case_id, status=case.get("status", "worker_running"))
        return {
            "case_id": case_id,
            "worker_container": name,
            "container_image": image,
            "running": True,
            "stage": "already_running",
        }

    if container_exists(name):
        rc, _, stderr = docker_run(["start", name], timeout=30)
        if rc != 0:
            return {
                "case_id": case_id,
                "worker_container": name,
                "container_image": image,
                "running": False,
                "error": stderr[:500],
                "stage": "start_existing_failed",
            }
        update_case(case_id, status="worker_running")
        return {
            "case_id": case_id,
            "worker_container": name,
            "container_image": image,
            "running": True,
            "stage": "started_existing",
        }

    rc, _, stderr = docker_run(
        [
            "run",
            "-d",
            "--name",
            name,
            "--privileged",
            "--cap-add",
            "SYS_ADMIN",
            "--cap-add",
            "MKNOD",
            "--device",
            "/dev/fuse",
            "-v",
            f"{CASES_HOST_PATH}:{CASES_CONTAINER_PATH}",
            "-it",
            image,
        ],
        timeout=60,
    )
    if rc != 0:
        return {
            "case_id": case_id,
            "worker_container": name,
            "container_image": image,
            "running": False,
            "error": stderr[:500],
            "stage": "create_worker_failed",
        }
    update_case(case_id, status="worker_running")
    return {
        "case_id": case_id,
        "worker_container": name,
        "container_image": image,
        "running": True,
        "stage": "created_worker",
    }


def create_case_with_worker(case_id: str, evidence_path: str) -> dict:
    return create_case(case_id=case_id, evidence_path=evidence_path)


def case_status(case_id: str) -> dict:
    case = require_case(validate_case_id(case_id))
    rc, stdout, stderr = docker_run(
        ["inspect", "-f", "{{.State.Running}}", case["worker_container"]],
        timeout=10,
    )
    running = rc == 0 and stdout.strip().lower() == "true"
    return {
        "case_id": case_id,
        "status": case.get("status"),
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "uses_custom_worker_image": case["container_image"].startswith("dfir-sift-worker"),
        "worker_running": running,
        "docker_available": rc != 127,
        "docker_status_error": stderr if rc not in (0, 1) else None,
        "evidence_path": case.get("evidence_path"),
        "image_path": case.get("image_path"),
        "filesystem": case.get("filesystem"),
        "offset": case.get("offset"),
        "evidence_count": len(case.get("evidence_ids", [])),
        "trace_count": len(case.get("trace_ids", [])),
        "finding_count": len(case.get("finding_ids", [])),
    }
