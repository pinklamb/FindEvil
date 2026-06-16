import json
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from .tools.evidence_files import (
        auto_case_id_from_evidence,
        evidence_file_metadata,
        list_evidence_files,
        uploaded_evidence_target,
    )
except ImportError:
    from tools.evidence_files import (
        auto_case_id_from_evidence,
        evidence_file_metadata,
        list_evidence_files,
        uploaded_evidence_target,
    )

try:
    from .server import (
        agent_run_case,
        answer_case_question,
        case_status,
        check_llm_status,
        check_sift_tools,
        create_case,
        create_suspicious_demo_bundle,
        create_suspicious_test_case,
        generate_investigation_report,
        generate_llm_investigative_report,
        get_analysis_contract,
        get_evidence,
        get_finding_trace,
        get_llm_case_brief,
        get_trace,
        investigate_case,
        list_all_cases,
        mount_e01,
        start_worker,
    )
except ImportError:
    from server import (
        agent_run_case,
        answer_case_question,
        case_status,
        check_llm_status,
        check_sift_tools,
        create_case,
        create_suspicious_demo_bundle,
        create_suspicious_test_case,
        generate_investigation_report,
        generate_llm_investigative_report,
        get_analysis_contract,
        get_evidence,
        get_finding_trace,
        get_llm_case_brief,
        get_trace,
        investigate_case,
        list_all_cases,
        mount_e01,
        start_worker,
    )


app = FastAPI(
    title="Traceable DFIR Backend",
    version="0.1.0",
    description="Deterministic DFIR API with evidence, trace, finding, and LLM-summary endpoints.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateCaseRequest(BaseModel):
    case_id: str
    evidence_path: str


class CreateDemoRequest(BaseModel):
    case_id: str = "CASE-FRONTEND-001"
    reset: bool = True


class CreateDemoBundleRequest(BaseModel):
    reset: bool = True


class MountRequest(BaseModel):
    evidence_path: str


class CreateCaseFromEvidenceRequest(BaseModel):
    evidence_path: str
    case_id: str | None = None


class ChatRequest(BaseModel):
    question: str


def _parse(raw: str) -> Any:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Backend returned invalid JSON: {exc}") from exc
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=400, detail=data)
    return data


def _call_backend(fn, *args, **kwargs) -> Any:
    try:
        return _parse(fn(*args, **kwargs))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc), "backend_function": fn.__name__}) from exc


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "traceable-dfir-backend",
        "llm": _call_backend(check_llm_status),
        "analysis_contract": _call_backend(get_analysis_contract),
    }


@app.get("/api/contract")
def analysis_contract() -> dict:
    return _call_backend(get_analysis_contract)


@app.get("/api/cases")
def cases() -> dict:
    return _call_backend(list_all_cases)


@app.get("/api/evidence-files")
def evidence_files() -> dict:
    try:
        return list_evidence_files()
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc


@app.post("/api/evidence-files")
async def upload_evidence_file(file: UploadFile = File(...)) -> dict:
    target = None
    try:
        target = uploaded_evidence_target(file.filename or "evidence")
        with open(target, "wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        return evidence_file_metadata(target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    except Exception as exc:
        if target is not None and target.exists():
            target.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc


@app.post("/api/cases")
def create_case_endpoint(request: CreateCaseRequest) -> dict:
    return _call_backend(create_case, request.case_id, request.evidence_path)


@app.post("/api/cases/from-evidence")
def create_case_from_evidence(request: CreateCaseFromEvidenceRequest) -> dict:
    case_id = request.case_id or auto_case_id_from_evidence(request.evidence_path)
    return _call_backend(create_case, case_id, request.evidence_path)


@app.post("/api/cases/demo")
def create_demo_case(request: CreateDemoRequest) -> dict:
    return _call_backend(create_suspicious_test_case, request.case_id, request.reset)


@app.post("/api/cases/demo-bundle")
def create_demo_bundle(request: CreateDemoBundleRequest) -> dict:
    return _call_backend(create_suspicious_demo_bundle, request.reset)


@app.get("/api/cases/{case_id}/status")
def case_status_endpoint(case_id: str) -> dict:
    return _call_backend(case_status, case_id)


@app.post("/api/cases/{case_id}/start")
def start_case_worker(case_id: str) -> dict:
    return _call_backend(start_worker, case_id)


@app.post("/api/cases/{case_id}/mount")
def mount_case(case_id: str, request: MountRequest) -> dict:
    return _call_backend(mount_e01, case_id, request.evidence_path)


@app.post("/api/cases/{case_id}/investigate")
def investigate_case_endpoint(case_id: str) -> dict:
    return _call_backend(investigate_case, case_id)


@app.post("/api/cases/{case_id}/agent-run")
def agent_run_case_endpoint(case_id: str) -> dict:
    return _call_backend(agent_run_case, case_id)


@app.get("/api/cases/{case_id}/tools")
def case_tools(case_id: str) -> dict:
    return _call_backend(check_sift_tools, case_id)


@app.get("/api/cases/{case_id}/report")
def case_report(case_id: str) -> dict:
    return _call_backend(generate_investigation_report, case_id)


@app.post("/api/cases/{case_id}/llm-report")
def llm_report(case_id: str) -> dict:
    return _call_backend(generate_llm_investigative_report, case_id)


@app.get("/api/cases/{case_id}/llm-brief")
def llm_brief(case_id: str) -> dict:
    return _call_backend(get_llm_case_brief, case_id)


@app.post("/api/cases/{case_id}/chat")
def chat(case_id: str, request: ChatRequest) -> dict:
    return _call_backend(answer_case_question, case_id, request.question)


@app.get("/api/cases/{case_id}/evidence/{evidence_id}")
def evidence(case_id: str, evidence_id: str) -> dict:
    return _call_backend(get_evidence, case_id, evidence_id)


@app.get("/api/cases/{case_id}/traces/{trace_id}")
def trace(case_id: str, trace_id: str) -> dict:
    return _call_backend(get_trace, case_id, trace_id)


@app.get("/api/cases/{case_id}/findings/{finding_id}/trace")
def finding_trace(case_id: str, finding_id: str) -> dict:
    return _call_backend(get_finding_trace, case_id, finding_id)
