import datetime
import json

from storage.case_store import require_case
from tools.docker_manager import docker_run
from utils.validation import validate_case_id, validate_container_path


DEFAULT_PARSERS = "winevt,prefetch,registry"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _run(case_id: str, cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    case = require_case(case_id)
    full_cmd = ["exec", "--user", "root", case["worker_container"], *cmd]
    return docker_run(full_cmd, timeout=timeout)


def build_timeline(
    case_id: str,
    parsers: str = DEFAULT_PARSERS,
    source_path: str | None = None,
    timeout: int = 1800,
) -> dict:
    case_id = validate_case_id(case_id)
    case = require_case(case_id)
    if not case.get("image_path"):
        raise ValueError(f"Case {case_id} is not mounted; call mount_e01 first")

    source_path = source_path or case["evidence_path"]
    source_path = validate_container_path(source_path, ("/cases/", "/mnt/ewf/"))
    storage_path = f"/cases/{case_id}/timelines/{case_id}.plaso"
    rc, _, stderr = _run(case_id, ["mkdir", "-p", f"/cases/{case_id}/timelines"], timeout=10)
    if rc != 0:
        return {"error": stderr[:300], "tool": "mkdir"}

    rc, _, _ = _run(case_id, ["rm", "-f", storage_path], timeout=10)
    cmd = [
        "log2timeline.py",
        "--storage_file",
        storage_path,
        "--parsers",
        parsers,
        "--status_view",
        "none",
        "-q",
        source_path,
    ]
    rc, stdout, stderr = _run(case_id, cmd, timeout=timeout)
    if rc != 0 and "Processing completed" not in stderr:
        return {
            "error": stderr[:800],
            "tool": "log2timeline",
            "stdout": stdout[:800],
            "source_path": source_path,
            "command_args": cmd,
        }

    meta = {
        "storage_path": storage_path,
        "parsers_used": parsers.split(","),
        "source_path": source_path,
        "mounted_image": case["image_path"],
    }
    for line in stderr.splitlines():
        if "Processing time" in line:
            meta["processing_time"] = line.split(":", 1)[-1].strip()
        if "Source type" in line:
            meta["source_type"] = line.split(":", 1)[-1].strip()

    return {
        "collected_at": _now(),
        "worker": "timeline_worker",
        "tool": "log2timeline",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": case["evidence_path"],
        "image": source_path,
        "mounted_image": case["image_path"],
        "filesystem": case.get("filesystem"),
        "offset": case.get("offset"),
        "storage_path": storage_path,
        "meta": meta,
        "command_args": cmd,
    }


def query_timeline(
    case_id: str,
    storage_path: str | None = None,
    max_events: int = 100,
    timeout: int = 300,
) -> dict:
    case_id = validate_case_id(case_id)
    case = require_case(case_id)
    storage_path = storage_path or f"/cases/{case_id}/timelines/{case_id}.plaso"
    storage_path = validate_container_path(storage_path, (f"/cases/{case_id}/",))
    max_events = min(max(int(max_events), 1), 1000)
    output_path = storage_path.replace(".plaso", "_timeline.json")

    _run(case_id, ["rm", "-f", output_path], timeout=10)
    cmd = ["psort.py", "-o", "json", "-w", output_path, storage_path]
    rc, _, stderr = _run(case_id, cmd, timeout=timeout)
    if rc != 0:
        return {"error": stderr[:800], "tool": "psort", "storage_path": storage_path}

    rc, stdout, stderr = _run(case_id, ["cat", output_path], timeout=60)
    if rc != 0:
        return {"error": stderr[:300], "tool": "cat", "output_path": output_path}

    events = []
    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse failed: {exc}", "tool": "psort"}

    iterator = raw.items() if isinstance(raw, dict) else enumerate(raw)
    for key, event in iterator:
        if not isinstance(event, dict):
            continue
        timestamp = ""
        if isinstance(event.get("date_time"), dict) and "timestamp" in event["date_time"]:
            timestamp_ns = event["date_time"]["timestamp"]
            timestamp = datetime.datetime.fromtimestamp(
                timestamp_ns / 1e9,
                datetime.timezone.utc,
            ).isoformat()
        message = event.get("message", "") or event.get("display_name", "")
        events.append(
            {
                "event_id": str(key),
                "event_identifier": str(event.get("event_identifier", "")),
                "data_type": event.get("data_type", ""),
                "filename": event.get("filename", event.get("display_name", "")),
                "timestamp": timestamp,
                "message": message[:500],
                "parser": event.get("parser", ""),
                "source": event.get("source_short", event.get("source", "")),
            }
        )
        if len(events) >= max_events:
            break

    return {
        "collected_at": _now(),
        "worker": "timeline_worker",
        "tool": "psort",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": case["evidence_path"],
        "image": case.get("image_path"),
        "filesystem": case.get("filesystem"),
        "offset": case.get("offset"),
        "storage_path": storage_path,
        "output_path": output_path,
        "event_count": len(events),
        "truncated": len(events) >= max_events,
        "events": events,
        "command_args": cmd,
    }
