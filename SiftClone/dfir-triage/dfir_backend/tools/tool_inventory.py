from storage.case_store import require_case
from tools.docker_manager import docker_run
from utils.validation import validate_case_id


DEFAULT_TOOLS = [
    "ewfmount",
    "mmls",
    "fsstat",
    "fls",
    "icat",
    "sha256sum",
    "yara",
    "hayabusa",
    "log2timeline.py",
    "psort.py",
]


def check_sift_tools(case_id: str, tools: list[str] | None = None) -> dict:
    case_id = validate_case_id(case_id)
    case = require_case(case_id)
    tools = tools or DEFAULT_TOOLS
    results = {}
    for tool in tools:
        rc, stdout, stderr = docker_run(
            ["exec", "--user", "root", case["worker_container"], "which", tool],
            timeout=10,
        )
        results[tool] = {
            "available": rc == 0,
            "path": stdout.strip() if rc == 0 else None,
            "error": stderr.strip()[:200] if rc != 0 else None,
        }
    return {
        "case_id": case_id,
        "worker_container": case["worker_container"],
        "container_image": case["container_image"],
        "tools": results,
    }
