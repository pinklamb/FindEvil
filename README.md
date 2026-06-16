# Traceable DFIR Investigator

**Detectable hallucinations for agentic forensic analysis.**

Traceable DFIR Investigator is a reproducible, Docker-first forensic investigation platform built for the SANS FindEvil / Protocol SIFT hackathon. It exposes SIFT-backed forensic workflows through a real Model Context Protocol (MCP) server, while also providing a FastAPI backend and React dashboard for judge-friendly review.

The project changes the trust boundary:

```text
SIFT tools are the source of truth.
LLMs and agents can orchestrate or explain.
They cannot create evidence-backed findings unless tool output supports them.
```

## The Problem

Agentic DFIR systems are powerful, but they can accidentally make the LLM the source of truth. If Claude or another agent summarizes a case and hallucinates a finding, there may be no built-in way to detect that the claim is unsupported.

In forensics, that is a serious failure mode:

- prompt instructions are not evidence controls;
- an agent can misread tool output or invent a plausible claim;
- judges and analysts need to know which exact tool output supports each finding;
- evidence integrity should not depend on model behavior.


## Why This Matters in Forensics

Incident responders stake their reputation on findings. A claim that doesn't 
check out can:
- Torpedo a prosecution
- Waste days of investigation time
- Create liability for the organization

In automated systems, hallucinations are especially dangerous because they're 
confident and plausible. An LLM can confidently invent a finding that sounds 
forensically sound but has no evidence.

This project makes hallucinations detectable: if a claim doesn't trace to 
tool output, it's commentary, not evidence.

## The Solution

This project makes deterministic SIFT tool execution the source of truth.

- Findings come from deterministic tool output, not LLM generation.
- Every finding must trace back to `evidence_id -> trace_id -> tool output`.
- Claude, a human, or any MCP-capable agent can orchestrate tool calls.
- The controller validates findings before returning the final report.
- If a proposed finding does not trace to tool output, it is rejected or rebuilt from durable records.
- The dashboard shows the audit trail for every claim.

The LLM is useful, but it is deliberately outside the evidence boundary. It can explain validated findings, answer questions from a compact case brief, and help an analyst navigate the case. It does not decide what is true.

## Core Contract

```text
MCP client / Claude / Browser UI
  -> agent_run_case
  -> deterministic SIFT-backed tools in Docker
  -> trace records from tool output
  -> findings generated from traces
  -> validated investigation report
  -> optional compact LLM explanation
```

The important property is that hallucinations become detectable. If an agent says, "this host had suspicious persistence," the system can ask: which finding, which evidence record, which trace record, and which tool output support that claim?

## What Is Implemented

Implemented now:

- Real MCP stdio server in `SiftClone/dfir-triage/dfir_backend/server.py`.
- FastAPI wrapper over the same deterministic backend functions.
- React/Vite dashboard for reviewing cases, findings, evidence, traces, and reports.
- Docker Compose stack with backend, Ollama, and a custom SIFT worker image.
- One SIFT worker container per case.
- Durable evidence, trace, and finding stores.
- `agent_run_case` controller with traceability validation.
- Built-in demo cases that do not require a large forensic image.
- Simulated self-correction demo: the controller detects an intentionally incomplete draft report, discards it, rebuilds from stored traces, and validates the final report.

Architecture-ready / intended extension:

- A live Claude or other MCP agent can orchestrate the same tool surface.
- If the agent proposes an unsupported claim, the system can force it back to deterministic traces: call another MCP tool, produce a new trace record, validate again, or retract the claim.

## Architecture

```text
                 MCP stdio                         HTTP
        Claude / MCP Inspector / Agent       Browser Dashboard
                    |                               |
                    v                               v
        dfir_backend/server.py              dfir_backend/api.py
        Real MCP tool server                 FastAPI wrapper
                    |                               |
                    +---------------+---------------+
                                    |
                                    v
                       Deterministic Controller
                           agent_run_case
                                    |
                    +---------------+---------------+
                    |                               |
                    v                               v
          Docker SIFT worker per case       Durable local stores
          sift-worker-<case-id>             evidence / traces / findings
                    |                               |
                    v                               v
             SIFT tool output          Validated investigation report
                                    |
                                    v
                         Optional LLM explanation
```

The HTTP API and MCP server share the same backend functions. `api.py` imports from `server.py`, so UI actions and MCP tool calls exercise the same deterministic controller.

## Evidence Integrity Guardrails

The project uses architectural guardrails rather than relying on prompts like "please do not modify evidence."

- Original evidence stays on the host filesystem.
- The backend creates case-specific worker containers.
- Evidence is mounted into the worker under `/cases`.
- SIFT tools execute inside the worker boundary.
- Tool output is recorded as trace records.
- Findings must link back to those trace records.

That means the audit trail is structural:

```text
finding
  -> evidence_id
  -> trace_id
  -> tool_name
  -> artifact_path
  -> tool output / summary
```

## Self-Correction Model

The self-correction idea is not "ask the model to be careful." It is validation against deterministic records.

When an agent or report proposes a finding:

1. The system checks whether the finding links to evidence and trace records.
2. The trace record points to the tool, command arguments, container, artifact path, and output summary.
3. If the links are missing or invalid, the claim is not accepted as evidence-backed.
4. The agent can investigate further by calling another MCP tool.
5. New tool output becomes a new trace record.
6. The process repeats until the claim is validated or rejected.

Current demo status:

- The built-in demo simulates this by intentionally creating a draft report with a missing trace link.
- `agent_run_case` detects the invalid draft, logs the correction in `self_corrections`, discards the draft, rebuilds from durable stores, and validates the final report.
- Real non-fixture runs also validate traceability and regenerate reports from stores if validation fails.

The goal is that any connected tool or agent can be challenged with: "show me the trace." If it cannot, the claim is commentary, not evidence.

## Repository Layout

```text
.
  README.md
  DatasetDocumentation.md
  HackathonOverview.md
  SiftClone/dfir-triage/
    docker-compose.yml
    dfir_backend/
      server.py          MCP server and core tool definitions
      api.py             FastAPI HTTP wrapper
      findings/          deterministic finding engines
      storage/           case, evidence, trace, and finding stores
      tools/             Docker/SIFT worker wrappers
    frontend/
      React + Vite dashboard
    sift_worker/
      Dockerfile         custom SIFT worker image
    scripts/
      start-all.ps1
      start-all.sh
      clean-generated.ps1
      clean-generated.sh
```

## Recommended Recreation

The primary judge recreation path is local Docker Compose.

Runtime services:

- Backend API: `http://localhost:8000`
- React/Vite dashboard: `http://localhost:5174`
- Ollama service: `http://localhost:11434`
- MCP stdio server: `SiftClone/dfir-triage/dfir_backend/server.py`
- SIFT worker image: `dfir-sift-worker:latest`
- Per-case workers: `sift-worker-<case-id>`

Recommended flow:

1. Clone the repository.
2. Enter `SiftClone/dfir-triage`.
3. Start the Docker Compose demo.
4. Open the dashboard.
5. Load demo cases.
6. Run a case.
7. Click findings to inspect evidence and trace records.
8. Optionally connect an MCP client and call the same tools directly.

## Requirements

For the full local workflow:

- Docker Desktop or Docker Engine with Linux containers
- Docker Compose v2
- Node.js 20+
- npm
- Python 3.12+
- Several GB of free disk space for images and containers

Optional:

- An Ollama model already pulled, such as `llama3.2:latest`
- SANS SIFT Workstation or another Linux Docker host

The full worker orchestration requires access to a Docker daemon. In Docker Compose, the backend container mounts `/var/run/docker.sock` so it can create per-case worker containers.

## Quick Start

From the repository root:

```bash
cd SiftClone/dfir-triage
```

Linux/macOS/Git Bash:

```bash
./scripts/start-all.sh
```

PowerShell:

```powershell
.\scripts\start-all.ps1
```

The script:

- cleans generated demo data unless told otherwise;
- builds the custom SIFT worker image;
- starts Ollama and the backend API;
- waits for `http://localhost:8000/api/health`;
- installs frontend dependencies when needed;
- starts Vite at `http://localhost:5174`.

Open:

```text
http://localhost:5174
```

Dashboard flow:

1. Click `LOAD DEMOS`.
2. Open a demo case.
3. Click `RUN CASE`.
4. Review findings, evidence links, trace links, report output, and LLM commentary.
5. Click a finding to inspect the evidence record and trace record behind it.

## Manual Docker Compose Start

From `SiftClone/dfir-triage`:

```bash
docker compose build sift-worker-image
docker compose up -d --build ollama mcp
curl http://localhost:8000/api/health
```

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5174
```

## MCP Server Usage

The MCP server is implemented in:

```text
SiftClone/dfir-triage/dfir_backend/server.py
```

From `SiftClone/dfir-triage`, install dependencies:

```bash
cd dfir_backend
python -m pip install -r requirements.txt
cd ..
```

Run over stdio:

```bash
python dfir_backend/server.py
```

For interactive inspection:

```bash
npx @modelcontextprotocol/inspector python dfir_backend/server.py
```

Example MCP client configuration:

```toml
[mcp_servers.dfir]
command = "python"
args = ["dfir_backend/server.py"]
cwd = "/absolute/path/to/SiftClone/dfir-triage"
startup_timeout_sec = 20
tool_timeout_sec = 180
```

On Windows:

```toml
cwd = "C:\\path\\to\\SiftClone\\dfir-triage"
```

For full SIFT-backed execution through MCP, Docker must be available to the Python process and the worker image should be built:

```bash
docker compose build sift-worker-image
```

### MCP Smoke Test

Use the MCP inspector and call:

1. `create_suspicious_demo_bundle` with `reset=true`
2. `agent_run_case` with `case_id="CASE-DEMO-PERSISTENCE-001"`
3. `list_case_findings` with the same case ID
4. `get_finding_trace` for one returned finding ID

This demonstrates that the MCP server is not a chat wrapper. It calls deterministic backend functions, starts or checks the case worker, records evidence/traces/findings, validates traceability, and returns auditable IDs.

### Core MCP Tools

- `create_case`: create or return a reproducible DFIR case.
- `create_suspicious_demo_bundle`: create built-in demo cases.
- `start_worker`: start or verify the dedicated SIFT worker container.
- `case_status`: return worker, mount, evidence, trace, and finding counts.
- `check_sift_tools`: check expected SIFT tools inside the worker.
- `agent_run_case`: primary deterministic controller with validation.
- `mount_e01`: mount E01/EX01 evidence in the case worker.
- `list_directory`: list directory contents in mounted evidence.
- `list_temp_files`: list temporary files from mounted evidence.
- `extract_file`: extract a file from mounted evidence.
- `inventory_artifacts`: inventory notable artifacts.
- `extract_priority_artifacts`: extract prioritized artifacts.
- `scan_filesystem`: scan filesystem artifacts for suspicious patterns.
- `investigate_case`: run deterministic investigation steps.
- `generate_investigation_report`: compile a validated report from stores.
- `get_llm_case_brief`: return the compact LLM explanation brief.
- `answer_case_question`: answer from the compact validated case brief.
- `list_case_evidence`: list evidence records.
- `list_case_traces`: list trace records.
- `list_case_findings`: list findings.
- `get_evidence`: retrieve one evidence record.
- `get_trace`: retrieve one trace record.
- `get_finding_trace`: retrieve the trace supporting a finding.

SIFT-oriented wrappers:

- `list_processes`
- `scan_yara`
- `scan_hayabusa`
- `build_timeline`
- `query_timeline`
- `scan_timeline`

## Example Trace Chain

```text
Finding: Suspicious run key persistence
  evidence_id: EVD-001
  trace_id: TRC-042
  tool_name: registry_parser
  artifact_path: HKLM\Software\Microsoft\Windows\Run
  tool_output: shell.exe [REG_SZ] ...
```

Every evidence-backed claim should be able to move backward through that chain:

```text
claim -> finding -> evidence record -> trace record -> tool output
```

If the chain is missing, the claim is not accepted as a validated finding.

## Built-In Demo Cases

The repository includes deterministic demo cases that do not require a large forensic image:

- `CASE-DEMO-PERSISTENCE-001`
- `CASE-DEMO-EXFIL-001`

Create them through the UI with `LOAD DEMOS`, or through the API:

```bash
curl -X POST http://localhost:8000/api/cases/demo-bundle \
  -H "Content-Type: application/json" \
  -d "{\"reset\": true}"
```

Run a demo case through the API:

```bash
curl -X POST http://localhost:8000/api/cases/CASE-DEMO-PERSISTENCE-001/agent-run
```

Show per-case worker containers:

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
```

## Real Evidence Flow

Place E01 or EX01 evidence under:

```text
SiftClone/dfir-triage/evidence/
```

For example:

```text
SiftClone/dfir-triage/evidence/uploads/example.e01
```

Then use the UI:

1. Open `http://localhost:5174`.
2. Click `ADD CASE`.
3. Select or upload the evidence file.
4. Open the created case.
5. Click `RUN CASE`.
6. Inspect findings, traces, evidence records, report output, and chat.

Equivalent API flow:

```bash
curl -X POST http://localhost:8000/api/cases/from-evidence \
  -H "Content-Type: application/json" \
  -d "{\"evidence_path\":\"/cases/uploads/example.e01\"}"
```

Use the returned case ID:

```bash
curl -X POST http://localhost:8000/api/cases/<returned-case-id>/agent-run
```

Accepted upload/list extensions:

- `.e01`
- `.ex01`

## Backend API

The backend container runs:

```text
uvicorn dfir_backend.api:app --host 0.0.0.0 --port 8000
```

Key endpoints:

```text
GET  /api/health
GET  /api/contract
GET  /api/cases
GET  /api/evidence-files
POST /api/evidence-files
POST /api/cases/from-evidence
POST /api/cases/demo-bundle
GET  /api/cases/{case_id}/status
POST /api/cases/{case_id}/start
POST /api/cases/{case_id}/mount
POST /api/cases/{case_id}/investigate
POST /api/cases/{case_id}/agent-run
GET  /api/cases/{case_id}/tools
GET  /api/cases/{case_id}/report
POST /api/cases/{case_id}/llm-report
GET  /api/cases/{case_id}/llm-brief
POST /api/cases/{case_id}/chat
GET  /api/cases/{case_id}/evidence/{evidence_id}
GET  /api/cases/{case_id}/traces/{trace_id}
GET  /api/cases/{case_id}/findings/{finding_id}/trace
```

## LLM Boundary

Default local model:

```text
llama3.2:latest
```

Relevant environment variables:

```text
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_TIMEOUT=180
OLLAMA_NUM_PREDICT=260
OLLAMA_CHAT_NUM_PREDICT=220
```

The LLM receives a compact case brief, not raw evidence files by default. The brief includes case ID, finding/evidence/trace counts, linked IDs, artifact locations, and UI links for inspection.

LLM-generated text is commentary. Evidence-backed claims must cite finding, evidence, and trace IDs.

## Hackathon Requirement Mapping

### Agentic Framework as Primary Execution Engine

`agent_run_case(case_id)` is the primary controller. It is exposed through MCP and through the HTTP API.

It performs:

- case loading;
- worker startup;
- SIFT tool checks;
- evidence mount when applicable;
- deterministic investigation;
- traceability validation;
- report generation;
- compact LLM brief preparation.

### Self-Correction

The controller records correction attempts in `self_corrections`.

Current behavior:

- retries worker startup if the first start does not report `running`;
- restarts/rechecks if required tools are missing;
- inspects case status after mount errors before failing;
- rejects invalid draft reports in the demo;
- regenerates reports from stored evidence/traces if traceability validation fails.

### Accuracy Validation

Every final finding must have:

- `finding_id`
- linked evidence records
- linked trace records
- evidence artifact paths
- trace IDs
- trace tool names
- trace artifact paths

### Analytical Reasoning

The returned report is structured narrative over deterministic records:

- case summary;
- findings;
- evidence records;
- trace records;
- UI links;
- compact LLM grounding brief;
- optional Llama/Claude narrative.

## Hosted Preview Note

Hosted platforms can preview the API/frontend and deterministic demo fixture viewing. The full forensic workflow should be judged with Docker Compose locally or on a Linux/SIFT-compatible host because it starts sibling worker containers:

```text
dfir-mcp -> Docker socket -> sift-worker-<case-id>
```

That requires:

- Docker CLI in the backend container;
- access to a Docker daemon;
- `/var/run/docker.sock` mounted into the backend;
- permission to create additional containers.

## Environment Variables

Backend:

```text
OLLAMA_HOST
OLLAMA_MODEL
OLLAMA_TIMEOUT
OLLAMA_NUM_PREDICT
OLLAMA_CHAT_NUM_PREDICT
SIFT_WORKER_IMAGE
CASES_HOST_PATH
CASES_CONTAINER_PATH
DFIR_DATA_ROOT
```

Frontend:

```text
VITE_API_BASE
```

For local Vite development, `VITE_API_BASE` can be empty because `vite.config.ts` proxies `/api` to `http://localhost:8000`.

## Cleaning Generated Data

From `SiftClone/dfir-triage`:

PowerShell:

```powershell
.\scripts\clean-generated.ps1
```

Bash:

```bash
./scripts/clean-generated.sh
```

Keep large forensic files under `SiftClone/dfir-triage/evidence/` or upload them through the UI.

## Verification Commands

From `SiftClone/dfir-triage`:

Backend syntax check:

```bash
python -m py_compile dfir_backend/server.py dfir_backend/api.py
```

Docker Compose config check:

```bash
docker compose config
```

Frontend type check:

```bash
cd frontend
npx tsc -b
```

API health:

```bash
curl http://localhost:8000/api/health
```

Agent run:

```bash
curl -X POST http://localhost:8000/api/cases/CASE-DEMO-PERSISTENCE-001/agent-run
```

## Troubleshooting

### Backend Health Fails

```bash
docker compose ps
docker compose logs mcp
curl http://localhost:8000/api/health
```

### Docker Executable Not Found

The backend container needs Docker CLI and Docker socket access. Confirm `docker-compose.yml` includes:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

Then rebuild:

```bash
docker compose build mcp
docker compose up -d mcp
```

### Worker Does Not Start

```bash
docker compose build sift-worker-image
docker images
docker ps
```

### MCP Server Will Not Start

```bash
cd dfir_backend
python -m pip install -r requirements.txt
cd ..
python dfir_backend/server.py
```

The process waits on stdio for an MCP client. For manual interaction, use the MCP inspector.

### Frontend Rollup Optional Dependency Error

Bash:

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

PowerShell:

```powershell
cd frontend
Remove-Item node_modules -Recurse -Force
Remove-Item package-lock.json -Force
npm install
```

### Llama Is Slow or Times Out

- keep reports short with `OLLAMA_NUM_PREDICT`;
- keep chat answers short with `OLLAMA_CHAT_NUM_PREDICT`;
- use a smaller or faster Ollama model;
- warm up Ollama before a live demo.

### Plaso / log2timeline E01 Errors

`build_timeline` may fail on incomplete, damaged, or chunk-missing E01 images. For hackathon reliability, the recommended path is:

```text
agent_run_case -> direct filesystem/artifact inventory -> traceable findings -> compact LLM brief
```

Timeline tooling remains available, but the built-in demo does not depend on damaged image timeline generation.

## Novel Contribution

- Deterministic MCP tool wrappers over SIFT-style forensic workflows.
- Reproducible per-case Docker worker platform.
- Evidence, trace, and finding model with auditable IDs.
- Self-validating controller that rejects or rebuilds unsupported reports.
- Hallucination detection boundary: claims must trace to tool output.
- Compact LLM reporting layer where the LLM explains validated records instead of creating findings.

## License and Third-Party Tools

Review each dependency before public distribution or competition submission:

- SIFT-related tools/images
- Ollama
- Llama model license
- YARA
- Hayabusa
- Plaso/log2timeline
- React/Vite/npm dependencies
