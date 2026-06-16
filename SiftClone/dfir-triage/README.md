# Traceable DFIR Investigator

Traceable DFIR Investigator is a reproducible, Docker-first forensic investigation platform built for the SANS FindEvil / Protocol SIFT hackathon. It exposes the investigation engine as an actual Model Context Protocol (MCP) server, while also providing a FastAPI backend and React dashboard for judge-friendly review.

The core contract is:

```text
MCP client or UI
  -> agent_run_case
  -> deterministic SIFT-backed tools
  -> evidence records + trace records + findings
  -> validated report
  -> compact optional LLM explanation
```

The LLM is intentionally not the source of truth. It does not create findings, decide what is suspicious, approve evidence, or receive raw artifacts by default. The deterministic controller performs the investigation, stores provenance, validates traceability, and only then prepares a compact brief for Llama/Ollama commentary.

## What Judges Should Recreate

The primary reproducible demo is local Docker Compose:

- Backend API: `http://localhost:8000`
- React/Vite dashboard: `http://localhost:5174`
- Ollama service: `http://localhost:11434`
- MCP stdio server: `dfir_backend/server.py`
- SIFT worker image: `dfir-sift-worker:latest`
- Per-case worker containers: `sift-worker-<case-id>`

Recommended judge flow:

1. Clone the repository and enter this project directory.
2. Start the full stack with Docker Compose.
3. Load the built-in demo cases.
4. Run a case.
5. Inspect the finding IDs, evidence IDs, trace IDs, and generated report.
6. Optionally connect an MCP client to `dfir_backend/server.py` and call the same tools directly.

## Requirements

For the full local workflow:

- Docker Desktop or Docker Engine with Linux containers
- Docker Compose v2
- Node.js 20+
- npm
- Python 3.12+
- Several GB of free disk space for images and containers

Optional but useful:

- An Ollama model already pulled, such as `llama3.2:latest`
- SANS SIFT Workstation or another Linux Docker host

The full worker orchestration requires access to a Docker daemon and, for the backend container, the Docker socket mounted at `/var/run/docker.sock`.

## Fresh Clone Quick Start

From a fresh clone, enter the project directory:

```bash
cd SiftClone/dfir-triage
```

Start everything on Linux/macOS/Git Bash:

```bash
./scripts/start-all.sh
```

Start everything on PowerShell:

```powershell
.\scripts\start-all.ps1
```

The startup script:

- cleans generated demo data unless told otherwise,
- builds the custom SIFT worker image,
- starts Ollama and the backend API,
- waits for `http://localhost:8000/api/health`,
- installs frontend dependencies when needed,
- starts Vite at `http://localhost:5174`.

Open:

```text
http://localhost:5174
```

In the UI:

1. Click `LOAD DEMOS`.
2. Open a demo case.
3. Click `RUN CASE`.
4. Review findings, evidence links, trace links, report output, and LLM commentary.

## Manual Docker Compose Start

Use this path if you want to see each layer start separately.

Build the SIFT worker image:

```bash
docker compose build sift-worker-image
```

Start Ollama and the backend/API service:

```bash
docker compose up -d --build ollama mcp
```

Check backend health:

```bash
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

## Architecture

```text
frontend/
  React + Vite dashboard for case review and demo operation

dfir_backend/api.py
  FastAPI HTTP wrapper around the same deterministic backend functions

dfir_backend/server.py
  MCP stdio server and core investigation tool definitions

dfir_backend/findings/
  Deterministic finding engines

dfir_backend/storage/
  Case, evidence, trace, and finding stores

dfir_backend/tools/
  Docker/SIFT worker wrappers

sift_worker/Dockerfile
  Custom worker image with forensic tooling support

docker-compose.yml
  Ollama, backend/API, Docker socket mount, and worker image build target
```

Runtime flow:

```text
MCP client             Browser UI
    |                     |
    | stdio               | HTTP
    v                     v
dfir_backend/server.py  dfir_backend/api.py
    |                     |
    +----------+----------+
               |
               v
        deterministic controller
               |
               v
   evidence records + trace records + findings
               |
               v
     Docker-managed SIFT worker per case
               |
               v
        validated investigation report
               |
               v
      compact LLM brief for commentary
```

The HTTP API and MCP server share the same backend functions. `api.py` imports functions from `server.py`, so UI actions and MCP tool calls exercise the same deterministic controller.

## MCP Server Usage

The MCP server is implemented in:

```text
dfir_backend/server.py
```

It runs over stdio:

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

On Windows, use the same config shape with a Windows absolute path:

```toml
cwd = "C:\\path\\to\\SiftClone\\dfir-triage"
```

Install the MCP server dependencies before launching the stdio server directly:

```bash
cd dfir_backend
python -m pip install -r requirements.txt
cd ..
```

For full SIFT-backed tool execution through MCP, Docker must be available to the Python process, and the worker image should be built:

```bash
docker compose build sift-worker-image
```

Core MCP tools include:

- `create_case`
- `create_suspicious_demo_bundle`
- `start_worker`
- `case_status`
- `check_sift_tools`
- `agent_run_case`
- `mount_e01`
- `list_directory`
- `extract_file`
- `inventory_artifacts`
- `scan_filesystem`
- `investigate_case`
- `generate_investigation_report`
- `get_llm_case_brief`
- `answer_case_question`
- `list_case_evidence`
- `list_case_traces`
- `list_case_findings`
- `get_evidence`
- `get_trace`
- `get_finding_trace`

SIFT-oriented wrapper tools include:

- `list_processes`
- `scan_yara`
- `scan_hayabusa`
- `build_timeline`
- `query_timeline`
- `scan_timeline`

### MCP Judge Smoke Test

After installing Python dependencies, inspect the MCP server:

```bash
npx @modelcontextprotocol/inspector python dfir_backend/server.py
```

In the inspector, call:

1. `create_suspicious_demo_bundle` with `reset=true`
2. `agent_run_case` with `case_id="CASE-DEMO-PERSISTENCE-001"`
3. `list_case_findings` with the same case ID
4. `get_finding_trace` for one returned finding ID

This demonstrates that the MCP server is not just a wrapper around a chat prompt. It calls deterministic backend functions, starts or checks the case worker, records evidence/traces/findings, and returns auditable IDs.

## Deterministic Outputs and Traceability

Each case is represented as durable structured records:

```text
case
  -> evidence records
  -> trace records
  -> findings
  -> investigation report
  -> compact LLM brief
```

Traceability target:

```text
finding
  -> evidence_id
  -> trace_id
  -> tool name
  -> artifact path / inode / output / hash where available
```

`agent_run_case(case_id)` validates the generated report before returning it. Findings must include linked evidence and trace records so judges can move from a narrative statement back to the deterministic tool output that supports it.

The agent/controller also writes a trace record for its own orchestration, making the run itself auditable.

## SIFT Workstation / Docker Integration

The project uses Docker to reproduce a SIFT-like execution boundary without requiring every judge to manually configure a workstation.

Important containers and images:

- `dfir-mcp`: backend API container. It includes the Docker CLI and mounts the host Docker socket.
- `ollama`: local Llama/Ollama service.
- `dfir-sift-worker:latest`: custom worker image built from `sift_worker/Dockerfile`.
- `sift-worker-<case-id>`: per-case worker container created on demand.

The backend uses the Docker socket to create one worker container per case. Evidence from `./evidence` is mounted into the worker under `/cases`, so deterministic tools operate against case-specific evidence paths.

This is why a normal hosted container platform may not reproduce the full workflow unless it supports Docker socket access or sibling container creation.

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

Show the per-case worker containers:

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
```

## Real Evidence Flow

Place E01 or EX01 evidence under:

```text
evidence/
```

For example:

```text
evidence/uploads/example.e01
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

## LLM / Ollama Boundary

The default model is:

```text
llama3.2:latest
```

Configured environment variables:

```text
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_TIMEOUT=180
OLLAMA_NUM_PREDICT=260
OLLAMA_CHAT_NUM_PREDICT=220
```

The LLM receives a compact case brief, not raw artifacts or full evidence files by default. The brief includes case ID, counts, finding IDs, evidence IDs, trace IDs, short artifact locations, and UI links.

LLM-generated text is marked as non-evidence commentary. Evidence-backed claims should cite finding, evidence, and trace IDs.

## Hackathon Requirement Mapping

### Agentic Framework as Primary Execution Engine

`agent_run_case(case_id)` is the primary controller. It is exposed through MCP and through the HTTP API.

It performs:

- case loading,
- worker startup,
- SIFT tool checks,
- evidence mount when applicable,
- deterministic investigation,
- traceability validation,
- report generation,
- compact LLM brief preparation.

### Self-Correction

The controller records correction attempts in `self_corrections`.

Current self-correction behavior:

- retries worker startup if the first start does not report `running`;
- restarts/rechecks if required tools are missing;
- inspects case status after mount errors before failing;
- regenerates the report from stored evidence/traces if traceability validation fails.

Built-in demos intentionally include a harmless draft-report self-check. The controller detects a draft missing a trace link, discards it, rebuilds the report from durable stores, and validates the final report.

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

- case summary,
- findings,
- evidence records,
- trace records,
- UI links,
- compact LLM grounding brief,
- optional Llama narrative.

## Railway / Hosted Preview Note

Railway or similar platforms can host a lightweight preview of the API/frontend and deterministic demo fixture viewing. They should not be treated as the authoritative full forensic runtime unless they support the Docker requirements above.

The full local workflow starts sibling worker containers:

```text
dfir-mcp -> Docker socket -> sift-worker-<case-id>
```

That requires:

- Docker CLI in the backend container,
- access to a Docker daemon,
- `/var/run/docker.sock` mounted into the backend,
- permission to create additional containers.

For judging the complete SIFT-backed workflow, use Docker Compose locally or on a Linux/SIFT-compatible host.

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

PowerShell:

```powershell
.\scripts\clean-generated.ps1
```

Bash:

```bash
./scripts/clean-generated.sh
```

Large forensic images should not be committed. Keep them local under `evidence/` or upload them through the UI.

## Verification Commands

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

Check containers:

```bash
docker compose ps
docker compose logs mcp
```

Check the health endpoint:

```bash
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

Build the worker image:

```bash
docker compose build sift-worker-image
```

Check Docker state:

```bash
docker images
docker ps
```

### MCP Server Will Not Start

Install Python dependencies:

```bash
cd dfir_backend
python -m pip install -r requirements.txt
cd ..
```

Then verify the server starts:

```bash
python dfir_backend/server.py
```

The process waits on stdio for an MCP client. For manual interaction, use the MCP inspector.

### Frontend Rollup Optional Dependency Error

On Bash:

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

On PowerShell:

```powershell
cd frontend
Remove-Item node_modules -Recurse -Force
Remove-Item package-lock.json -Force
npm install
```

### Llama Is Slow or Times Out

Options:

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

## License and Third-Party Tools

Review each dependency before public distribution or competition submission:

- SIFT-related tools/images
- Ollama
- Llama model license
- YARA
- Hayabusa
- Plaso/log2timeline
- React/Vite/npm dependencies

The novel contribution is the reproducible case-worker platform, deterministic MCP tool wrappers, traceable evidence/finding model, self-validating agent controller, and compact LLM reporting boundary.
