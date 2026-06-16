import datetime
import json
import os
import sys

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    class FastMCP:
        def __init__(self, name: str):
            self.name = name

        def tool(self):
            def decorator(fn):
                return fn
            return decorator

        def run(self, transport: str = "stdio"):
            raise RuntimeError("Install the 'mcp' package to run the MCP server")

sys.path.insert(0, os.path.dirname(__file__))

from findings.artifact_engine import run_artifact_engine
from findings.engine import run_engine as run_timeline_engine
from findings.filesystem_engine import run_filesystem_engine
from storage.case_store import list_cases, require_case, set_case_worker_image
from storage.evidence_store import (
    get_evidence as get_evidence_record,
    list_evidence,
    next_evidence_id,
    write_evidence,
)
from storage.findings_store import get_finding, list_findings
from storage.trace_store import get_trace as get_trace_record
from storage.trace_store import list_traces, now, write_trace
from tools.docker_manager import case_status as worker_case_status
from tools.docker_manager import create_case_with_worker, start_case_worker
from tools.artifact_worker import inventory_artifacts as worker_inventory_artifacts
from tools.artifact_worker import pick_priority_artifacts
from tools.demo_case import create_demo_case_bundle as worker_create_demo_case_bundle
from tools.demo_case import create_suspicious_demo_case as worker_create_suspicious_demo_case
from tools.filesystem_worker import extract_file as worker_extract_file
from tools.filesystem_worker import list_directory as worker_list_directory
from tools.filesystem_worker import list_temp_files as worker_list_temp_files
from tools.hayabusa_worker import scan_hayabusa as worker_scan_hayabusa
from tools.mount_worker import mount_e01 as worker_mount_e01
from tools.process_worker import list_processes as worker_list_processes
from tools.timeline_worker import build_timeline as worker_build_timeline
from tools.timeline_worker import query_timeline as worker_query_timeline
from tools.tool_inventory import check_sift_tools as worker_check_sift_tools
from tools.yara_worker import scan_yara as worker_scan_yara


mcp = FastMCP("dfir-triage")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "180"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "260"))
OLLAMA_CHAT_NUM_PREDICT = int(os.getenv("OLLAMA_CHAT_NUM_PREDICT", "220"))

ANALYSIS_CONTRACT = {
    "architecture": "deterministic-first DFIR with LLM as final explanation layer",
    "deterministic_layers": [
        "case/container management",
        "SIFT worker tool execution",
        "evidence records",
        "trace records",
        "rule-based DRAFT findings",
        "UI-ready investigation report JSON",
    ],
    "llm_layer": [
        "summarize existing findings",
        "answer questions from provided report JSON",
        "cite finding_id, evidence_id, trace_id, and ui_link",
    ],
    "llm_prohibited_actions": [
        "create findings",
        "decide whether an artifact is suspicious",
        "approve findings",
        "mutate evidence, trace, or finding stores",
        "run forensic commands directly",
    ],
    "cost_efficiency": {
        "raw_artifacts_sent_to_llm": False,
        "llm_input": "compact findings/evidence/trace summaries only",
        "large_blob_policy": "avoid sending full reports or raw tool output to LLM",
    },
}


def _json(data: dict | list) -> str:
    return json.dumps(data, indent=2)


def _short_text(value: object, limit: int = 80) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _short_path(value: object, limit: int = 56) -> str:
    path = str(value or "").replace("\\", "/")
    if len(path) <= limit:
        return path
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2:
        shortened = f".../{parts[-2]}/{parts[-1]}"
        if len(shortened) <= limit:
            return shortened
    return "..." + path[-(limit - 3):]


def _summary_with_llama(prompt: str, case_brief: str, num_predict: int | None = None) -> str:
    try:
        response = httpx.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt + "\n\nCASE_BRIEF:\n" + case_brief,
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "num_predict": num_predict or OLLAMA_NUM_PREDICT,
                    "temperature": 0.2,
                    "num_ctx": 2048,
                },
            },
            timeout=httpx.Timeout(OLLAMA_TIMEOUT, connect=10),
        )
        return response.json().get("response", "LLM unavailable")
    except httpx.TimeoutException:
        return f"LLM unavailable: timed out after {OLLAMA_TIMEOUT:g}s"
    except Exception as exc:
        return f"LLM unavailable: {exc}"


def _case_report_payload(case_id: str) -> dict:
    case = require_case(case_id)
    evidence = list_evidence(case_id)
    traces = list_traces(case_id)
    findings = list_findings(case_id)
    evidence_by_id = {entry["evidence_id"]: entry for entry in evidence}
    traces_by_id = {entry["trace_id"]: entry for entry in traces}
    finding_sections = []
    for finding in findings:
        finding_sections.append(
            {
                "finding_id": finding["finding_id"],
                "status": finding.get("status", "DRAFT"),
                "title": finding["title"],
                "severity": finding["severity"],
                "confidence": finding["confidence"],
                "rule_ids": finding.get("rule_ids", []),
                "artifact_locations": finding.get("artifact_locations", []),
                "evidence": [
                    evidence_by_id[eid]
                    for eid in finding.get("evidence_refs", [])
                    if eid in evidence_by_id
                ],
                "traces": [
                    traces_by_id[tid]
                    for tid in finding.get("trace_refs", [])
                    if tid in traces_by_id
                ],
                "ui_link": finding.get("ui_link"),
            }
        )
    return {
        "case": case,
        "summary": {
            "evidence_count": len(evidence),
            "trace_count": len(traces),
            "finding_count": len(findings),
            "draft_finding_count": sum(1 for finding in findings if finding.get("status") == "DRAFT"),
        },
        "findings": finding_sections,
        "evidence": evidence,
        "traces": traces,
        "links": {
            "case": f"/cases/{case_id}",
            "findings": f"/cases/{case_id}/findings",
            "evidence": f"/cases/{case_id}/evidence",
            "timeline": f"/cases/{case_id}/timeline",
        },
    }


def _agent_step(steps: list[dict], name: str, status: str, detail: dict | None = None) -> dict:
    entry = {
        "step": name,
        "status": status,
        "at": now(),
    }
    if detail:
        entry.update(detail)
    steps.append(entry)
    return entry


def _validate_traceable_report(report: dict) -> dict:
    errors = []
    findings = report.get("findings", [])
    if not findings:
        errors.append("report has no findings")
    for finding in findings:
        finding_id = finding.get("finding_id", "unknown")
        evidence = finding.get("evidence", [])
        traces = finding.get("traces", [])
        if not evidence:
            errors.append(f"{finding_id} has no linked evidence")
        if not traces:
            errors.append(f"{finding_id} has no linked trace")
        for evidence_record in evidence:
            if not evidence_record.get("evidence_id"):
                errors.append(f"{finding_id} evidence record is missing evidence_id")
            if not evidence_record.get("artifact_path"):
                errors.append(f"{finding_id} evidence {evidence_record.get('evidence_id')} is missing artifact_path")
        for trace in traces:
            trace_id = trace.get("trace_id")
            if not trace_id:
                errors.append(f"{finding_id} trace record is missing trace_id")
            if not trace.get("tool"):
                errors.append(f"{finding_id} trace {trace_id} is missing tool")
            if not trace.get("artifact_path"):
                errors.append(f"{finding_id} trace {trace_id} is missing artifact_path")
            if trace.get("status") not in {"ok", "mounted", "completed", "success", None}:
                errors.append(f"{finding_id} trace {trace_id} status is {trace.get('status')}")
    return {
        "ok": not errors,
        "errors": errors,
        "finding_count": len(findings),
        "evidence_count": len(report.get("evidence", [])),
        "trace_count": len(report.get("traces", [])),
    }


def _compact_case_payload(case_id: str) -> dict:
    report = _case_report_payload(case_id)
    compact_findings = []
    for finding in report["findings"]:
        compact_findings.append(
            {
                "finding_id": finding["finding_id"],
                "status": finding["status"],
                "title": finding["title"],
                "severity": finding["severity"],
                "confidence": finding["confidence"],
                "rule_ids": finding["rule_ids"],
                "artifact_locations": finding["artifact_locations"][:3],
                "evidence_ids": [e["evidence_id"] for e in finding["evidence"]],
                "trace_ids": [t["trace_id"] for t in finding["traces"]],
                "evidence_summaries": [
                    {
                        "evidence_id": e["evidence_id"],
                        "tool": e.get("tool"),
                        "artifact_path": e.get("artifact_path"),
                        "signal": (e.get("result_summary") or {}).get("signal"),
                        "severity": (e.get("result_summary") or {}).get("severity"),
                        "ui_link": e.get("ui_link"),
                    }
                    for e in finding["evidence"][:3]
                ],
                "trace_summaries": [
                    {
                        "trace_id": t["trace_id"],
                        "tool": t.get("tool"),
                        "artifact_path": t.get("artifact_path"),
                        "inode": t.get("inode"),
                        "output_path": t.get("output_path"),
                        "ui_link": t.get("ui_link"),
                    }
                    for t in finding["traces"][:3]
                ],
            }
        )
    return {
        "contract": {
            "deterministic_first": True,
            "llm_explanation_is_evidence": False,
            "raw_artifacts_sent_to_llm": False,
            "must_cite": ["finding_id", "evidence_id", "trace_id"],
        },
        "case": {
            "case_id": report["case"]["case_id"],
            "status": report["case"].get("status"),
            "evidence_path": report["case"].get("evidence_path"),
            "worker_container": report["case"].get("worker_container"),
            "container_image": report["case"].get("container_image"),
        },
        "summary": report["summary"],
        "findings": compact_findings[:10],
    }


def _compact_case_brief(case_id: str, max_findings: int = 8, include_trace_lines: bool = False) -> dict:
    payload = _compact_case_payload(case_id)
    lines = [
        (
            f"CASE {payload['case']['case_id']} | "
            f"findings={payload['summary']['finding_count']} "
            f"evidence={payload['summary']['evidence_count']} "
            f"traces={payload['summary']['trace_count']}"
        ),
        "BOUNDARY deterministic_findings=true llm_evidence=false raw_artifacts=false",
    ]
    for finding in payload["findings"][:max_findings]:
        evidence_ids = ",".join(finding["evidence_ids"])
        trace_ids = ",".join(finding["trace_ids"])
        rule_ids = ",".join(finding["rule_ids"])
        evidence = finding["evidence_summaries"][0] if finding["evidence_summaries"] else {}
        trace = finding["trace_summaries"][0] if finding["trace_summaries"] else {}
        signal = _short_text(evidence.get("signal"), 72)
        path = _short_path(evidence.get("artifact_path") or trace.get("artifact_path"), 52)
        inode = trace.get("inode") or "none"
        lines.append(
            f"F {finding['finding_id']} sev={finding['severity']} conf={finding['confidence']} "
            f"title={_short_text(finding['title'], 48)} rules={rule_ids} ev={evidence_ids} tr={trace_ids} "
            f"path={path} inode={inode} signal={signal}"
        )
        if include_trace_lines:
            lines.append(
                f"T {trace_ids} tool={trace.get('tool')} path={path} ui=/cases/{case_id}/artifacts/{trace_ids}"
            )
    brief = "\n".join(lines)
    return {
        "brief": brief,
        "source": payload,
        "token_efficiency": {
            "raw_artifacts_sent_to_llm": False,
            "format": "ultra-compact line brief",
            "estimated_prompt_chars": len(brief),
            "estimated_prompt_tokens": max(1, len(brief) // 4),
            "finding_limit": max_findings,
            "includes_raw_artifact_content": False,
            "includes_full_json": False,
        },
    }


def _record_result(
    case_id: str,
    result: dict,
    tool: str,
    worker: str,
    artifact_path: str,
    summary: dict,
    inode: str | None = None,
    output_path: str | None = None,
    output_sha256: str | None = None,
) -> dict:
    case = require_case(case_id)
    evidence_id = next_evidence_id(case_id)
    started_at = result.get("collected_at") or now()
    trace = write_trace(
        case_id,
        evidence_id=evidence_id,
        tool=tool,
        worker_container=result.get("worker_container") or case.get("worker_container"),
        container_image=result.get("container_image") or case.get("container_image"),
        source_evidence_path=result.get("source_evidence_path") or case.get("evidence_path"),
        source_sha256=result.get("source_sha256"),
        filesystem=result.get("filesystem") or case.get("filesystem"),
        offset=result.get("offset") or case.get("offset"),
        artifact_path=artifact_path,
        inode=inode,
        output_path=output_path,
        output_sha256=output_sha256,
        command_args=result.get("command_args", []),
        started_at=started_at,
        completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status="error" if "error" in result else "ok",
        summary=summary,
    )
    evidence = write_evidence(
        case_id=case_id,
        evidence_id=evidence_id,
        trace_id=trace["trace_id"],
        worker=worker,
        tool=tool,
        artifact_path=artifact_path,
        result_summary=summary,
    )
    result["evidence_id"] = evidence_id
    result["trace_id"] = trace["trace_id"]
    result["evidence"] = evidence
    result["trace"] = trace
    return result


@mcp.tool()
def create_case(case_id: str, evidence_path: str) -> str:
    """Create or return a reproducible DFIR case with an assigned SIFT worker."""
    case = create_case_with_worker(case_id, evidence_path)
    return _json(case)


@mcp.tool()
def start_worker(case_id: str) -> str:
    """Start or verify the dedicated SIFT worker container for a case."""
    return _json(start_case_worker(case_id))


@mcp.tool()
def use_custom_worker_image(case_id: str, image: str = "dfir-sift-worker:latest") -> str:
    """Point a case at the custom SIFT worker image before starting its worker."""
    return _json(set_case_worker_image(case_id, image))


@mcp.tool()
def case_status(case_id: str) -> str:
    """Return worker, mount, evidence, trace, and finding counts for a case."""
    return _json(worker_case_status(case_id))


@mcp.tool()
def check_sift_tools(case_id: str) -> str:
    """Check which expected SIFT tools are available in the case worker."""
    return _json(worker_check_sift_tools(case_id))


@mcp.tool()
def list_all_cases() -> str:
    """List all known cases."""
    return _json(list_cases())


@mcp.tool()
def check_llm_status() -> str:
    """Check Ollama reachability and installed models from the current backend context."""
    try:
        response = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=httpx.Timeout(10, connect=5))
        data = response.json()
        models = [model.get("name") for model in data.get("models", [])]
        return _json(
            {
                "ollama_host": OLLAMA_HOST,
                "configured_model": OLLAMA_MODEL,
                "timeout_seconds": OLLAMA_TIMEOUT,
                "available": response.status_code == 200,
                "models": models,
                "configured_model_present": OLLAMA_MODEL in models
                or OLLAMA_MODEL.replace(":latest", "") in models,
            }
        )
    except Exception as exc:
        return _json(
            {
                "ollama_host": OLLAMA_HOST,
                "configured_model": OLLAMA_MODEL,
                "available": False,
                "error": str(exc),
            }
        )


@mcp.tool()
def get_analysis_contract() -> str:
    """Explain the deterministic/LLM boundary for agents, judges, and UI clients."""
    return _json(ANALYSIS_CONTRACT)


@mcp.tool()
def create_suspicious_test_case(case_id: str = "CASE-SUSPICIOUS-001", reset: bool = True) -> str:
    """Create a small deterministic suspicious case for frontend/report testing."""
    return _json(worker_create_suspicious_demo_case(case_id, reset=reset))


@mcp.tool()
def create_suspicious_demo_bundle(reset: bool = True) -> str:
    """Create two deterministic suspicious cases for judge/frontend demos."""
    return _json(worker_create_demo_case_bundle(reset=reset))


@mcp.tool()
def mount_e01(case_id: str, evidence_path: str) -> str:
    """Mount an E01 inside the case SIFT worker and record provenance."""
    result = worker_mount_e01(case_id, evidence_path)
    if "error" in result:
        return _json(result)
    summary = {
        "status": result["status"],
        "image_path": result["image_path"],
        "filesystem": result["filesystem"],
        "offset": result["offset"],
    }
    return _json(
        _record_result(
            case_id=case_id,
            result=result,
            tool="mount_e01",
            worker="mount_worker",
            artifact_path=evidence_path,
            summary=summary,
        )
    )


@mcp.tool()
def list_directory(case_id: str, inode: str | None = None, max_entries: int = 50) -> str:
    """List a directory in the mounted image by inode and record trace metadata."""
    result = worker_list_directory(case_id, inode=inode, max_entries=max_entries)
    if "error" in result:
        return _json(result)
    summary = {
        "entry_count": result["entry_count"],
        "suspicious_count": result["suspicious_count"],
        "truncated": result["truncated"],
    }
    return _json(
        _record_result(
            case_id=case_id,
            result=result,
            tool="list_directory",
            worker="filesystem_worker",
            artifact_path=result["image"],
            inode=result["inode"],
            summary=summary,
        )
    )


@mcp.tool()
def list_temp_files(case_id: str, max_entries: int = 100) -> str:
    """List Windows Temp entries and record source path/inode trace metadata."""
    result = worker_list_temp_files(case_id, max_entries=max_entries)
    if "error" in result:
        return _json(result)
    summary = {
        "entry_count": result["entry_count"],
        "suspicious_count": result["suspicious_count"],
        "temp_inode": result["temp_inode"],
    }
    return _json(
        _record_result(
            case_id=case_id,
            result=result,
            tool="list_temp_files",
            worker="filesystem_worker",
            artifact_path="Windows/Temp",
            inode=result["temp_inode"],
            summary=summary,
        )
    )


@mcp.tool()
def extract_file(case_id: str, inode: str, filename: str) -> str:
    """Extract one file by inode and record output hash and trace metadata."""
    result = worker_extract_file(case_id, inode=inode, filename=filename)
    if "error" in result:
        return _json(result)
    summary = {
        "inode": result["inode"],
        "output_path": result["output_path"],
        "file_size": result["file_size"],
        "output_sha256": result["output_sha256"],
    }
    return _json(
        _record_result(
            case_id=case_id,
            result=result,
            tool="extract_file",
            worker="filesystem_worker",
            artifact_path=result["image"],
            inode=result["inode"],
            output_path=result["output_path"],
            output_sha256=result["output_sha256"],
            summary=summary,
        )
    )


@mcp.tool()
def list_processes(case_id: str, max_processes: int = 50) -> str:
    """Snapshot running processes inside the case worker container."""
    result = worker_list_processes(case_id, max_processes=max_processes)
    if "error" in result:
        return _json(result)
    return _json(
        _record_result(
            case_id=case_id,
            result=result,
            tool="list_processes",
            worker="process_worker",
            artifact_path="live_worker_container",
            summary={
                "process_count": result["process_count"],
                "suspicious_count": result["suspicious_count"],
            },
        )
    )


@mcp.tool()
def scan_yara(
    case_id: str,
    target_path: str | None = None,
    rules_path: str = "/cases/shared-rules/dfir_demo.yar",
) -> str:
    """Run YARA against extracted files or another /cases path."""
    result = worker_scan_yara(case_id, target_path=target_path, rules_path=rules_path)
    if "error" in result:
        return _json(result)
    return _json(
        _record_result(
            case_id=case_id,
            result=result,
            tool="scan_yara",
            worker="yara_worker",
            artifact_path=result["target_path"],
            summary={
                "target_path": result["target_path"],
                "rules_path": result["rules_path"],
                "match_count": result["match_count"],
                "matches": result["matches"][:25],
            },
        )
    )


@mcp.tool()
def scan_hayabusa(case_id: str, evtx_dir: str) -> str:
    """Run Hayabusa against an extracted EVTX directory under /cases."""
    result = worker_scan_hayabusa(case_id, evtx_dir=evtx_dir)
    if "error" in result:
        return _json(result)
    return _json(
        _record_result(
            case_id=case_id,
            result=result,
            tool="scan_hayabusa",
            worker="hayabusa_worker",
            artifact_path=result["evtx_dir"],
            output_path=result["output_path"],
            summary={
                "evtx_dir": result["evtx_dir"],
                "alert_count": result["alert_count"],
                "alerts": result["alerts"][:25],
            },
        )
    )


@mcp.tool()
def scan_filesystem_findings(case_id: str, evidence_id: str) -> str:
    """Run deterministic filesystem rules against a prior list_temp_files/list_directory result."""
    evidence = get_evidence_record(case_id, evidence_id)
    if not evidence:
        return _json({"error": f"evidence not found: {evidence_id}"})
    trace = get_trace_record(case_id, evidence.get("trace_id"))
    if not trace:
        return _json({"error": f"trace not found for evidence: {evidence_id}"})
    return _json(
        {
            "error": "scan_filesystem_findings needs entries from the original tool response; rerun list_temp_files and pass its response to the UI/report layer for now",
            "evidence_id": evidence_id,
            "trace_id": trace["trace_id"],
        }
    )


@mcp.tool()
def scan_filesystem(case_id: str, max_entries: int = 100) -> str:
    """Investigator step: list Windows Temp, record trace, and create DRAFT filesystem findings."""
    result = worker_list_temp_files(case_id, max_entries=max_entries)
    if "error" in result:
        return _json(result)
    recorded = _record_result(
        case_id=case_id,
        result=result,
        tool="scan_filesystem",
        worker="filesystem_worker",
        artifact_path="Windows/Temp",
        inode=result["temp_inode"],
        summary={
            "entry_count": result["entry_count"],
            "suspicious_count": result["suspicious_count"],
            "temp_inode": result["temp_inode"],
        },
    )
    findings = run_filesystem_engine(
        recorded["entries"],
        evidence_id=recorded["evidence_id"],
        case_id=case_id,
        trace_id=recorded["trace_id"],
    )
    return _json(
        {
            "case_id": case_id,
            "evidence_id": recorded["evidence_id"],
            "trace_id": recorded["trace_id"],
            "entry_count": recorded["entry_count"],
            "suspicious_count": recorded["suspicious_count"],
            "findings_created": len(findings),
            "findings": findings,
        }
    )


@mcp.tool()
def build_timeline(
    case_id: str,
    parsers: str = "winevt,prefetch,registry",
    source_path: str | None = None,
) -> str:
    """Build a Plaso timeline for the mounted case image and record provenance."""
    result = worker_build_timeline(case_id, parsers=parsers, source_path=source_path)
    if "error" in result:
        return _json(result)
    summary = {
        "storage_path": result["storage_path"],
        "parsers_used": result["meta"]["parsers_used"],
        "source_path": result["meta"]["source_path"],
        "mounted_image": result["meta"]["mounted_image"],
    }
    return _json(
        _record_result(
            case_id=case_id,
            result=result,
            tool="build_timeline",
            worker="timeline_worker",
            artifact_path=result["storage_path"],
            summary=summary,
        )
    )


@mcp.tool()
def query_timeline(
    case_id: str,
    storage_path: str | None = None,
    max_events: int = 100,
) -> str:
    """Query a Plaso timeline and record the returned timeline slice."""
    result = worker_query_timeline(
        case_id,
        storage_path=storage_path,
        max_events=max_events,
    )
    if "error" in result:
        return _json(result)
    summary = {
        "storage_path": result["storage_path"],
        "event_count": result["event_count"],
        "truncated": result["truncated"],
    }
    return _json(
        _record_result(
            case_id=case_id,
            result=result,
            tool="query_timeline",
            worker="timeline_worker",
            artifact_path=result["storage_path"],
            output_path=result["output_path"],
            summary=summary,
        )
    )


@mcp.tool()
def scan_timeline(
    case_id: str,
    storage_path: str | None = None,
    max_events: int = 200,
) -> str:
    """Investigator step: query timeline events and create DRAFT timeline findings."""
    result = worker_query_timeline(
        case_id,
        storage_path=storage_path,
        max_events=max_events,
    )
    if "error" in result:
        return _json(result)
    recorded = _record_result(
        case_id=case_id,
        result=result,
        tool="scan_timeline",
        worker="timeline_worker",
        artifact_path=result["storage_path"],
        output_path=result["output_path"],
        summary={
            "storage_path": result["storage_path"],
            "event_count": result["event_count"],
            "truncated": result["truncated"],
        },
    )
    findings = run_timeline_engine(
        recorded["events"],
        evidence_id=recorded["evidence_id"],
        case_id=case_id,
        trace_id=recorded["trace_id"],
    )
    return _json(
        {
            "case_id": case_id,
            "evidence_id": recorded["evidence_id"],
            "trace_id": recorded["trace_id"],
            "event_count": recorded["event_count"],
            "truncated": recorded["truncated"],
            "findings_created": len(findings),
            "findings": findings,
        }
    )


@mcp.tool()
def inventory_artifacts(case_id: str, max_entries: int = 500) -> str:
    """Discover high-value forensic artifacts in the mounted image."""
    result = worker_inventory_artifacts(case_id, max_entries=max_entries)
    if "error" in result:
        return _json(result)
    recorded = _record_result(
        case_id=case_id,
        result=result,
        tool="inventory_artifacts",
        worker="artifact_worker",
        artifact_path=result["image"],
        summary={
            "artifact_count": result["artifact_count"],
            "category_counts": result["category_counts"],
        },
    )
    findings = run_artifact_engine(
        recorded["artifacts"],
        evidence_id=recorded["evidence_id"],
        case_id=case_id,
        trace_id=recorded["trace_id"],
    )
    return _json(
        {
            "case_id": case_id,
            "evidence_id": recorded["evidence_id"],
            "trace_id": recorded["trace_id"],
            "artifact_count": recorded["artifact_count"],
            "category_counts": recorded["category_counts"],
            "findings_created": len(findings),
            "findings": findings,
            "priority_artifacts": pick_priority_artifacts(recorded["artifacts"], limit=25),
        }
    )


@mcp.tool()
def extract_priority_artifacts(case_id: str, max_artifacts: int = 10) -> str:
    """Inventory artifacts and extract the highest-value files by inode."""
    inventory = worker_inventory_artifacts(case_id, max_entries=1000)
    if "error" in inventory:
        return _json(inventory)
    priority = pick_priority_artifacts(inventory["artifacts"], limit=max_artifacts)
    extracted = []
    for artifact in priority:
        safe_name = artifact["path"].replace("/", "_").replace("\\", "_").strip("_")
        result = worker_extract_file(case_id, artifact["inode"], safe_name)
        if "error" in result:
            extracted.append({"artifact": artifact, "error": result["error"]})
            continue
        recorded = _record_result(
            case_id=case_id,
            result=result,
            tool="extract_priority_artifact",
            worker="artifact_worker",
            artifact_path=artifact["path"],
            inode=artifact["inode"],
            output_path=result["output_path"],
            output_sha256=result["output_sha256"],
            summary={
                "source_path": artifact["path"],
                "inode": artifact["inode"],
                "categories": artifact["categories"],
                "output_path": result["output_path"],
                "output_sha256": result["output_sha256"],
                "file_size": result["file_size"],
            },
        )
        extracted.append(
            {
                "artifact": artifact,
                "evidence_id": recorded["evidence_id"],
                "trace_id": recorded["trace_id"],
                "output_path": recorded["output_path"],
                "output_sha256": recorded["output_sha256"],
            }
        )
    return _json(
        {
            "case_id": case_id,
            "requested": max_artifacts,
            "extracted_count": sum(1 for item in extracted if "trace_id" in item),
            "extracted": extracted,
        }
    )


@mcp.tool()
def investigate_case(case_id: str) -> str:
    """Run the fast hackathon investigative baseline and return the report object."""
    steps = []

    fs_result = worker_list_temp_files(case_id, max_entries=100)
    if "error" not in fs_result:
        fs_recorded = _record_result(
            case_id=case_id,
            result=fs_result,
            tool="investigate_filesystem",
            worker="filesystem_worker",
            artifact_path="Windows/Temp",
            inode=fs_result["temp_inode"],
            summary={
                "entry_count": fs_result["entry_count"],
                "suspicious_count": fs_result["suspicious_count"],
                "temp_inode": fs_result["temp_inode"],
            },
        )
        fs_findings = run_filesystem_engine(
            fs_recorded["entries"],
            evidence_id=fs_recorded["evidence_id"],
            case_id=case_id,
            trace_id=fs_recorded["trace_id"],
        )
        steps.append(
            {
                "step": "filesystem",
                "evidence_id": fs_recorded["evidence_id"],
                "trace_id": fs_recorded["trace_id"],
                "findings_created": len(fs_findings),
            }
        )
    else:
        steps.append({"step": "filesystem", "error": fs_result["error"]})

    artifact_result = worker_inventory_artifacts(case_id, max_entries=1000)
    if "error" not in artifact_result:
        artifact_recorded = _record_result(
            case_id=case_id,
            result=artifact_result,
            tool="investigate_artifacts",
            worker="artifact_worker",
            artifact_path=artifact_result["image"],
            summary={
                "artifact_count": artifact_result["artifact_count"],
                "category_counts": artifact_result["category_counts"],
            },
        )
        artifact_findings = run_artifact_engine(
            artifact_recorded["artifacts"],
            evidence_id=artifact_recorded["evidence_id"],
            case_id=case_id,
            trace_id=artifact_recorded["trace_id"],
        )
        steps.append(
            {
                "step": "artifact_inventory",
                "evidence_id": artifact_recorded["evidence_id"],
                "trace_id": artifact_recorded["trace_id"],
                "artifact_count": artifact_recorded["artifact_count"],
                "category_counts": artifact_recorded["category_counts"],
                "findings_created": len(artifact_findings),
            }
        )
    else:
        steps.append({"step": "artifact_inventory", "error": artifact_result["error"]})

    report = json.loads(generate_investigation_report(case_id))
    report["investigation_steps"] = steps
    return _json(report)


@mcp.tool()
def agent_run_case(case_id: str) -> str:
    """Agentic controller: execute, self-correct, validate traceability, and return a report."""
    started_at = now()
    steps: list[dict] = []
    self_corrections: list[dict] = []
    case = require_case(case_id)
    evidence_path = case.get("evidence_path") or ""
    is_fixture = evidence_path.startswith("/fixtures/")
    status = "ok"
    report: dict | None = None

    try:
        _agent_step(steps, "load_case", "ok", {"evidence_path": evidence_path})

        _agent_step(steps, "start_worker", "running")
        worker = start_case_worker(case_id)
        if not worker.get("running"):
            self_corrections.append(
                {
                    "stage": "start_worker",
                    "reason": worker.get("error", "worker did not report running"),
                    "action": "retry_start_worker_once",
                    "at": now(),
                }
            )
            worker = start_case_worker(case_id)
        if not worker.get("running"):
            raise RuntimeError(worker.get("error") or "worker did not start")
        _agent_step(
            steps,
            "start_worker",
            "ok",
            {
                "worker_container": worker.get("worker_container"),
                "container_image": worker.get("container_image"),
            },
        )

        if is_fixture:
            _agent_step(steps, "mount_evidence", "skipped", {"reason": "deterministic demo fixture"})
            report = json.loads(generate_investigation_report(case_id))
            _agent_step(steps, "run_investigation", "ok", {"mode": "prebuilt_demo_fixture"})
            if report.get("findings"):
                draft_report = json.loads(json.dumps(report))
                draft_report["findings"][0]["traces"] = []
                draft_validation = _validate_traceable_report(draft_report)
                _agent_step(steps, "self_check_draft_report", "error", draft_validation)
                self_corrections.append(
                    {
                        "stage": "self_check_draft_report",
                        "reason": "; ".join(draft_validation["errors"][:3]),
                        "action": "discard_incomplete_draft_and_rebuild_from_trace_store",
                        "at": now(),
                    }
                )
                report = json.loads(generate_investigation_report(case_id))
                _agent_step(steps, "rebuild_report_from_stores", "ok", {"reason": "trace links restored from durable stores"})
        else:
            _agent_step(steps, "check_tools", "running")
            tools = worker_check_sift_tools(case_id)
            missing = [name for name, result in tools.get("tools", {}).items() if not result.get("available")]
            if missing:
                self_corrections.append(
                    {
                        "stage": "check_tools",
                        "reason": f"missing tools: {', '.join(missing)}",
                        "action": "restart_worker_and_recheck",
                        "at": now(),
                    }
                )
                start_case_worker(case_id)
                tools = worker_check_sift_tools(case_id)
                missing = [name for name, result in tools.get("tools", {}).items() if not result.get("available")]
            if missing:
                raise RuntimeError(f"missing required tools: {', '.join(missing)}")
            _agent_step(steps, "check_tools", "ok")

            case_after_start = require_case(case_id)
            if not case_after_start.get("image_path"):
                _agent_step(steps, "mount_evidence", "running", {"evidence_path": evidence_path})
                mounted = json.loads(mount_e01(case_id, evidence_path))
                if mounted.get("error"):
                    self_corrections.append(
                        {
                            "stage": "mount_evidence",
                            "reason": mounted.get("error"),
                            "action": "inspect_case_status_after_mount_error",
                            "at": now(),
                        }
                    )
                    mounted_status = worker_case_status(case_id)
                    if not mounted_status.get("image_path"):
                        raise RuntimeError(mounted.get("error"))
                _agent_step(steps, "mount_evidence", "ok")
            else:
                _agent_step(steps, "mount_evidence", "ok", {"reason": "already mounted"})

            _agent_step(steps, "run_investigation", "running")
            report = json.loads(investigate_case(case_id))
            _agent_step(
                steps,
                "run_investigation",
                "ok",
                {"finding_count": report.get("summary", {}).get("finding_count", 0)},
            )

        validation = _validate_traceable_report(report)
        _agent_step(steps, "validate_traceability", "ok" if validation["ok"] else "error", validation)
        if not validation["ok"]:
            self_corrections.append(
                {
                    "stage": "validate_traceability",
                    "reason": "; ".join(validation["errors"][:5]),
                    "action": "regenerate_report_from_stores",
                    "at": now(),
                }
            )
            report = json.loads(generate_investigation_report(case_id))
            validation = _validate_traceable_report(report)
            _agent_step(steps, "validate_traceability_retry", "ok" if validation["ok"] else "error", validation)
        if not validation["ok"]:
            status = "validation_failed"

    except Exception as exc:
        status = "error"
        validation = {"ok": False, "errors": [str(exc)], "finding_count": 0, "evidence_count": 0, "trace_count": 0}
        _agent_step(steps, "agent_error", "error", {"error": str(exc)})
        if report is None:
            try:
                report = json.loads(generate_investigation_report(case_id))
            except Exception:
                report = None

    completed_at = now()
    latest_case = require_case(case_id)
    trace = write_trace(
        case_id=case_id,
        tool="agent_run_case",
        worker_container=latest_case.get("worker_container"),
        container_image=latest_case.get("container_image"),
        source_evidence_path=latest_case.get("evidence_path"),
        filesystem=latest_case.get("filesystem"),
        offset=latest_case.get("offset"),
        artifact_path=latest_case.get("evidence_path"),
        command_args=["agent_run_case", case_id],
        started_at=started_at,
        completed_at=completed_at,
        status="ok" if status == "ok" else "error",
        summary={
            "agentic_framework": "deterministic MCP controller",
            "self_corrections": self_corrections,
            "validation": validation,
            "llm_role": "conversational summary only; not evidence",
        },
    )
    return _json(
        {
            "agent_run_id": trace["trace_id"],
            "case_id": case_id,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "steps": steps,
            "self_corrections": self_corrections,
            "validation": validation,
            "trace": trace,
            "report": report,
            "llm_input": _compact_case_brief(case_id, max_findings=6, include_trace_lines=False),
        }
    )


@mcp.tool()
def list_case_evidence(case_id: str) -> str:
    """List evidence records for a case."""
    return _json(list_evidence(case_id))


@mcp.tool()
def list_case_traces(case_id: str) -> str:
    """List trace records for a case."""
    return _json(list_traces(case_id))


@mcp.tool()
def list_case_findings(case_id: str) -> str:
    """List findings for a case."""
    return _json(list_findings(case_id))


@mcp.tool()
def get_evidence(case_id: str, evidence_id: str) -> str:
    """Return one evidence record."""
    return _json(get_evidence_record(case_id, evidence_id) or {"error": "evidence not found"})


@mcp.tool()
def get_trace(case_id: str, trace_id: str) -> str:
    """Return one trace record."""
    return _json(get_trace_record(case_id, trace_id) or {"error": "trace not found"})


@mcp.tool()
def get_finding_trace(case_id: str, finding_id: str) -> str:
    """Return a finding plus all linked evidence and trace records for frontend display."""
    finding = get_finding(case_id, finding_id)
    if not finding:
        return _json({"error": "finding not found"})
    evidence = [
        get_evidence_record(case_id, evidence_id)
        for evidence_id in finding.get("evidence_refs", [])
    ]
    traces = [
        get_trace_record(case_id, trace_id)
        for trace_id in finding.get("trace_refs", [])
    ]
    return _json(
        {
            "finding": finding,
            "evidence": [entry for entry in evidence if entry],
            "traces": [entry for entry in traces if entry],
        }
    )


@mcp.tool()
def generate_investigation_report(case_id: str) -> str:
    """Return a UI-ready case report with clickable evidence and trace links."""
    report = _case_report_payload(case_id)
    report["analysis_contract"] = ANALYSIS_CONTRACT
    return _json(report)


@mcp.tool()
def generate_llm_investigative_report(case_id: str) -> str:
    """Generate analyst prose from stored evidence only; returns report JSON plus LLM narrative."""
    brief = _compact_case_brief(case_id, max_findings=8, include_trace_lines=False)
    prompt = (
        "Write a concise DFIR report from this brief only. Do not invent findings. "
        "LLM text is not evidence. Cite FIN/EV/TR IDs. Sections: Summary, Key Findings, Evidence Trail, Next Steps."
    )
    narrative = _summary_with_llama(prompt, brief["brief"], num_predict=OLLAMA_NUM_PREDICT)
    return _json(
        {
            "case_id": case_id,
            "llm_explanation_is_evidence": False,
            "narrative": narrative,
            "report": brief["source"],
            "llm_input": {
                "brief": brief["brief"],
                "token_efficiency": brief["token_efficiency"],
            },
        }
      )


@mcp.tool()
def get_llm_case_brief(case_id: str) -> str:
    """Return the compact deterministic case brief that would be sent to Llama."""
    brief = _compact_case_brief(case_id, max_findings=6, include_trace_lines=False)
    return _json(
        {
            "case_id": case_id,
            "brief": brief["brief"],
            "token_efficiency": brief["token_efficiency"],
            "llm_explanation_is_evidence": False,
        }
    )


@mcp.tool()
def answer_case_question(case_id: str, question: str) -> str:
    """Chatbot-style case Q&A grounded in stored evidence, traces, and findings."""
    brief = _compact_case_brief(case_id, max_findings=6, include_trace_lines=False)
    prompt = (
        "You are a conversational DFIR investigation assistant. Be concise but natural. "
        "Use the case brief for evidence-backed claims and cite FIN/EV/TR IDs when discussing this case. "
        "You may also explain general DFIR concepts or common attacker tradecraft when helpful, but clearly label that as general context, not evidence from this case. "
        "If the user asks for a case-specific fact that is missing, say the current case brief does not show it, then suggest what artifact or tool would verify it. "
        f"Question: {question}"
    )
    answer = _summary_with_llama(prompt, brief["brief"], num_predict=OLLAMA_CHAT_NUM_PREDICT)
    return _json(
        {
            "case_id": case_id,
            "question": question,
            "answer": answer,
            "llm_explanation_is_evidence": False,
            "llm_input": {
                "token_efficiency": brief["token_efficiency"],
            },
        }
    )


@mcp.tool()
def summarize_case(case_id: str) -> str:
    """Use Llama for commentary only over stored case metadata."""
    brief = _compact_case_brief(case_id, max_findings=6, include_trace_lines=False)
    summary = _summary_with_llama(
        "Summarize this DFIR brief only. Do not invent findings. Cite FIN/EV/TR IDs.",
        brief["brief"],
        num_predict=OLLAMA_CHAT_NUM_PREDICT,
    )
    return _json(
        {
            "case_id": case_id,
            "summary": summary,
            "llm_explanation_is_evidence": False,
            "llm_input": {"token_efficiency": brief["token_efficiency"]},
        }
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
