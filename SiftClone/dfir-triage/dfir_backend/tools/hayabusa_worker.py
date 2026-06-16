import csv
import datetime
from io import StringIO

from storage.case_store import require_case
from tools.docker_manager import docker_run
from utils.validation import validate_case_id, validate_container_path


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def scan_hayabusa(
    case_id: str,
    evtx_dir: str,
    timeout: int = 300,
    max_alerts: int = 100,
) -> dict:
    case_id = validate_case_id(case_id)
    case = require_case(case_id)
    evtx_dir = validate_container_path(evtx_dir, ("/cases/",))
    output_path = f"/cases/{case_id}/hayabusa_alerts.csv"
    cmd = [
        "hayabusa",
        "csv-timeline",
        "-d",
        evtx_dir,
        "-o",
        output_path,
        "-q",
        "--no-wizard",
    ]
    rc, stdout, stderr = docker_run(
        ["exec", "--user", "root", case["worker_container"], *cmd],
        timeout=timeout,
    )
    if rc != 0:
        return {"error": stderr[:800] or stdout[:800], "tool": "hayabusa", "command_args": cmd}

    rc, csv_out, cat_err = docker_run(
        ["exec", "--user", "root", case["worker_container"], "cat", output_path],
        timeout=60,
    )
    if rc != 0:
        return {"error": cat_err[:300], "tool": "cat", "output_path": output_path}

    alerts = []
    reader = csv.DictReader(StringIO(csv_out))
    for row in reader:
        alerts.append(row)
        if len(alerts) >= max_alerts:
            break
    return {
        "collected_at": _now(),
        "worker": "hayabusa_worker",
        "tool": "hayabusa",
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "source_evidence_path": case.get("evidence_path"),
        "evtx_dir": evtx_dir,
        "output_path": output_path,
        "alert_count": len(alerts),
        "alerts": alerts,
        "command_args": cmd,
    }
