# Traceable DFIR Investigator

Traceable DFIR Investigator is a Docker-first forensic investigation platform for the SANS FindEvil / Protocol SIFT hackathon. It runs deterministic DFIR tools inside case-specific SIFT worker containers, records evidence and trace provenance, and uses Llama/Ollama only as a conversational reporting layer over already validated findings.

The core idea is simple:

```text
agent_run_case -> deterministic SIFT tools -> evidence/traces/findings -> compact Llama brief -> analyst narrative/chat
```

Llama does not decide what is suspicious, create evidence, approve findings, or receive raw artifacts by default. The agent/controller executes the investigation and validates that findings are traceable to evidence and trace records.

## Current Status

Working locally with Docker Compose:

- Backend API on `http://localhost:8000`
- React/Vite dashboard on `http://localhost:5174`
- Shared Ollama service on `http://localhost:11434`
- One dedicated SIFT worker container per case
- Two built-in suspicious demo cases
- Upload/list supported evidence files from `evidence/`
- MCP tools exposed from `dfir_backend/server.py`
- Agent execution via `agent_run_case`
- LLM chat and report generation from compact finding briefs

Important Railway note:

Railway is suitable for a lightweight hosted preview of the API/frontend and deterministic demo fixtures. The full forensic workflow that starts sibling SIFT worker containers requires access to a Docker daemon and `/var/run/docker.sock`. Standard Railway app containers should not be assumed to support that Docker-socket workflow. For judges, the most reproducible full setup is Docker Compose on a Linux/SIFT-compatible host or Docker Desktop.

## Architecture

```text
frontend/
  React + Vite + TypeScript dashboard

dfir_backend/
  FastAPI HTTP API
  MCP server tools
  deterministic agent controller
  evidence/trace/finding storage

sift_worker/
  custom SIFT worker image with yara/hayabusa support

docker-compose.yml
  ollama
  dfir-mcp backend
  dfir-sift-worker image build target
```

Runtime services:

- `dfir-mcp`: backend API and MCP tool host.
- `ollama`: shared Llama service.
- `dfir-sift-worker:latest`: image used to create one worker container per case.
- `sift-worker-<case-id>`: case-specific worker container created on demand.

Data model:

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
finding -> evidence record -> trace record -> tool -> source artifact/path/inode/output/hash
```

## Hackathon Requirement Mapping

### Agentic Framework as Primary Execution Engine

`agent_run_case(case_id)` is the primary execution controller. It is exposed through MCP and the HTTP API.

It performs:

- case loading,
- worker startup,
- tool checks,
- evidence mount when applicable,
- deterministic investigation,
- traceability validation,
- report generation,
- compact LLM brief preparation.

This project’s agentic layer is deliberately deterministic and MCP-callable. Claude Code, OpenClaw, or another MCP-capable agent can call the tools, but the backend already provides the reproducible execution substrate.

### Self-Correction

The agent controller records correction attempts in `self_corrections`.

Current self-correction behavior:

- retries worker startup if the first start does not report `running`;
- restarts/rechecks if required tools are missing;
- inspects case status after mount errors before failing;
- regenerates the report from stored evidence/traces if traceability validation fails.

### Accuracy Validation

`agent_run_case` validates the generated report before returning it.

Every finding must have:

- `finding_id`
- linked evidence records
- linked trace records
- evidence artifact paths
- trace IDs
- trace tool names
- trace artifact paths

The agent run writes its own trace record, so the orchestration itself is auditable.

### Analytical Reasoning

The backend returns a structured investigative narrative object instead of a raw execution log:

- case summary,
- findings,
- evidence records,
- trace records,
- UI links,
- compact LLM grounding brief,
- optional Llama narrative.

The LLM layer is marked as non-evidence commentary.

### SIFT / Linux Integration

Case workers are Linux containers built from the local `sift_worker/Dockerfile`. The intended full platform is Docker on Linux/SIFT Workstation or Docker Desktop with Linux containers.

## Requirements

For full local operation:

- Docker Desktop or Docker Engine
- Docker Compose v2
- Node.js 20+
- npm
- Python 3.12+
- At least several GB of free disk space for images/containers

Optional:

- Ollama model already pulled, for faster first run
- SANS SIFT workstation environment or Linux Docker host

## Repository Layout

```text
.
├── dfir_backend/
│   ├── api.py                  # FastAPI API
│   ├── server.py               # MCP tools and backend functions
│   ├── findings/               # deterministic finding engines
│   ├── storage/                # case/evidence/trace/finding stores
│   ├── tools/                  # worker wrappers
│   └── Dockerfile              # backend container
├── evidence/                   # local evidence root mounted into backend/workers
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── scripts/
│   ├── start-all.ps1
│   ├── start-all.sh
│   ├── start-demo.ps1
│   ├── start-demo.sh
│   ├── clean-generated.ps1
│   └── clean-generated.sh
├── sift_worker/
│   └── Dockerfile
├── storage/
│   └── case_store.json
└── docker-compose.yml
```

## Quick Start: Full Demo

From the repository root:

```powershell
cd C:\Users\Me\Downloads\SlayEvil\SiftClone\dfir-triage
```

PowerShell:

```powershell
.\scripts\start-all.ps1
```

Bash:

```bash
./scripts/start-all.sh
```

This script:

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

Recommended UI flow:

1. Click `LOAD DEMOS`.
2. Open a case from the landing page.
3. Click `RUN CASE` to run the agent/controller path for the selected case.
4. Review findings and the investigation report in the selected case view.
5. Use the chat panel to ask case questions grounded in findings/evidence/traces.

## Manual Docker Compose Start

Build the SIFT worker image:

```bash
docker compose build sift-worker-image
```

Start backend services:

```bash
docker compose up -d --build ollama mcp
```

Check health:

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

## Backend API

The backend runs with:

```text
uvicorn dfir_backend.api:app --host 0.0.0.0 --port 8000
```

Main endpoints:

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

Example agent run:

```bash
curl -X POST http://localhost:8000/api/cases/CASE-DEMO-PERSISTENCE-001/agent-run
```

## MCP Usage

The MCP server is implemented in:

```text
dfir_backend/server.py
```

Inspect locally:

```powershell
npx @modelcontextprotocol/inspector python dfir_backend\server.py
```

Example Codex MCP configuration:

```toml
[mcp_servers.dfir]
command = "python"
args = ["dfir_backend/server.py"]
cwd = "C:\\Users\\Me\\Downloads\\SlayEvil\\SiftClone\\dfir-triage"
startup_timeout_sec = 20
tool_timeout_sec = 180
```

Core MCP tools:

- `create_case`
- `start_worker`
- `agent_run_case`
- `case_status`
- `check_sift_tools`
- `mount_e01`
- `list_directory`
- `list_temp_files`
- `extract_file`
- `inventory_artifacts`
- `extract_priority_artifacts`
- `scan_filesystem`
- `investigate_case`
- `generate_investigation_report`
- `generate_llm_investigative_report`
- `get_llm_case_brief`
- `answer_case_question`
- `list_case_evidence`
- `list_case_traces`
- `list_case_findings`
- `get_evidence`
- `get_trace`
- `get_finding_trace`

SIFT wrappers:

- `list_processes`
- `scan_yara`
- `scan_hayabusa`
- `build_timeline`
- `query_timeline`
- `scan_timeline`

## Evidence Handling

Evidence files should be placed under:

```text
evidence/
```

The frontend also supports direct upload. Uploaded files are stored under:

```text
evidence/uploads/
```

Accepted upload/list extensions:

- `.e01`
- `.ex01`

The backend maps host evidence into containers as:

```text
host:      ./evidence/...
container: /cases/...
```

Case IDs can be generated automatically from the evidence filename or created manually through API/tool calls.

## Built-In Demo Cases

The project includes deterministic suspicious demo cases that do not require a large forensic image:

- `CASE-DEMO-PERSISTENCE-001`
- `CASE-DEMO-EXFIL-001`

Create them through the UI with `LOAD DEMOS`, or through the API:

```bash
curl -X POST http://localhost:8000/api/cases/demo-bundle \
  -H "Content-Type: application/json" \
  -d "{\"reset\": true}"
```

These demos are useful for showing:

- two independent cases,
- two independent SIFT worker containers,
- traceable findings,
- compact LLM summaries,
- case-specific chat.

## Real E01 Flow

Place an E01 or EX01 file under `evidence/`, for example:

```text
evidence/uploads/example.e01
```

Then use the UI:

1. Open `http://localhost:5174`.
2. Click `ADD CASE` and choose the evidence file.
3. The app uploads the evidence, creates a case, and opens it.
4. Click `RUN CASE`.
5. Inspect findings, report, evidence, traces, and chat in the selected case view.

Equivalent API flow:

```bash
curl -X POST http://localhost:8000/api/cases/from-evidence \
  -H "Content-Type: application/json" \
  -d "{\"evidence_path\":\"/cases/uploads/example.e01\"}"
```

Then:

```bash
curl -X POST http://localhost:8000/api/cases/CASE-EXAMPLE-001/agent-run
```

Use the generated case ID returned by `from-evidence`.

## LLM / Ollama Behavior

Ollama is shared across cases. The default model is:

```text
llama3.2:latest
```

Configured in `docker-compose.yml`:

```text
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_TIMEOUT=180
OLLAMA_NUM_PREDICT=260
OLLAMA_CHAT_NUM_PREDICT=220
```

The LLM receives a compact brief, not raw artifacts or full JSON by default.

The brief includes:

- case ID,
- finding count,
- evidence count,
- trace count,
- finding IDs,
- evidence IDs,
- trace IDs,
- short artifact locations,
- UI links.

This keeps token usage low and makes the LLM layer explainable.

## Railway Deployment

### What Works on Railway

Railway can be used for a hosted preview of:

- the FastAPI backend,
- deterministic demo fixture APIs,
- the React frontend,
- LLM chat/reporting if an Ollama-compatible endpoint is reachable.

### What Does Not Reliably Work on Standard Railway

The full local workflow starts sibling Docker containers from inside the backend:

```text
dfir-mcp -> Docker socket -> sift-worker-CASE-ID containers
```

That requires:

- Docker CLI in the backend container,
- access to a Docker daemon,
- `/var/run/docker.sock` mounted into the backend,
- permission to create additional containers.

Standard Railway deployments should not be assumed to allow this. Because of that, the full forensic container orchestration demo should be run with Docker Compose locally or on a Linux host you control.

### Recommended Railway Strategy

Use Railway as a preview layer, not the authoritative forensic execution layer:

1. Deploy the frontend as a static/Vite build.
2. Deploy the backend API for demo fixtures and report viewing.
3. Point `VITE_API_BASE` at the backend URL.
4. Keep full case-worker orchestration for Docker Compose/local SIFT demos.

### Two-Service GitHub Setup

You can use one GitHub repository and create two Railway services from it:

Backend service:

- Root directory: repository root or `dfir_backend`
- Dockerfile path: `dfir_backend/Dockerfile`
- Start command: handled by the Dockerfile
- Public URL: generate a Railway domain for the backend

Frontend service:

- Root directory: `frontend`
- Dockerfile path: `frontend/Dockerfile`
- Start command: handled by the Dockerfile
- Public URL: generate a Railway domain for the frontend
- Environment variable: `VITE_API_BASE=https://<your-backend-service>.railway.app`

Railway supports Dockerfile-based services and lets a service specify a custom Dockerfile path with `RAILWAY_DOCKERFILE_PATH`. It can also expose services over public HTTP(S) domains from the service networking settings.

Frontend build:

```bash
cd frontend
npm install
npm run build
```

Backend start command:

```bash
uvicorn dfir_backend.api:app --host 0.0.0.0 --port $PORT
```

Railway environment variables for preview mode:

```text
OLLAMA_HOST=<reachable ollama host, if available>
OLLAMA_MODEL=llama3.2:latest
OLLAMA_TIMEOUT=180
SIFT_WORKER_IMAGE=dfir-sift-worker:latest
CASES_CONTAINER_PATH=/cases
```

If Railway does not provide Docker socket access, `start_worker` and real E01 `agent_run_case` will report Docker unavailable. Demo fixture reports can still be used to show the UI and report structure.

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

Generated case stores, traces, timelines, and extracted artifacts can be removed.

PowerShell:

```powershell
.\scripts\clean-generated.ps1
```

Bash:

```bash
./scripts/clean-generated.sh
```

Large forensic images should not be committed. Keep them local under `evidence/` or upload them through the UI.

## Troubleshooting

### Backend Health Fails

Check containers:

```bash
docker compose ps
docker compose logs mcp
```

Health endpoint:

```bash
curl http://localhost:8000/api/health
```

### Docker Executable Not Found

The backend container needs Docker CLI and Docker socket access.

Confirm `docker-compose.yml` has:

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

Check Docker:

```bash
docker images | grep dfir-sift-worker
docker ps
```

### Frontend Rollup Optional Dependency Error

If npm reports a missing Rollup native optional dependency:

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

The project intentionally sends compact briefs, but local model speed still depends on hardware.

Options:

- keep reports short with `OLLAMA_NUM_PREDICT`;
- keep chat answers short with `OLLAMA_CHAT_NUM_PREDICT`;
- use a smaller/faster Ollama model;
- make sure Ollama is warmed up before judging.

### Plaso / log2timeline E01 Errors

`build_timeline` may fail on incomplete, damaged, or chunk-missing E01 images. For hackathon reliability, the recommended path is:

```text
agent_run_case -> direct filesystem/artifact inventory -> traceable findings -> compact LLM brief
```

Timeline tooling remains available, but the demo should not depend on damaged image timeline generation.

## Verification Commands

Frontend type check:

```bash
cd frontend
npx tsc -b
```

Backend syntax check:

```bash
python -m py_compile dfir_backend/server.py dfir_backend/api.py
```

Docker Compose check:

```bash
docker compose config
```

API health:

```bash
curl http://localhost:8000/api/health
```

Agent run:

```bash
curl -X POST http://localhost:8000/api/cases/CASE-DEMO-PERSISTENCE-001/agent-run
```

## Demo Script for Judges

1. Start the platform:

   ```bash
   ./scripts/start-all.sh
   ```

2. Open:

   ```text
   http://localhost:5174
   ```

3. Click `LOAD DEMOS`.

4. Open one of the demo cases from the landing page.

5. Click `RUN CASE`.

6. Show that each case has its own worker container:

   ```bash
   docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
   ```

7. Show:

   - agent steps,
   - self-corrections if any,
   - validation status,
   - traceable findings,
   - evidence IDs,
   - trace IDs,
   - compact LLM brief,
   - Llama chat/report as non-evidence commentary.

Built-in demo cases intentionally run a harmless draft-report self-check. The agent detects that the draft is missing a trace link, discards the incomplete draft, rebuilds the report from durable evidence/trace stores, and then validates the final report. This is the visible self-correction loop for the hackathon demo; source evidence is not modified.

When Llama is generating, the UI shows an in-progress narrative/chat state. The text is generated from the compact validated brief only, so the demo can show token-conscious reporting without sending raw artifacts to the model.

## License and Third-Party Tools

This project uses open-source tooling and container images. Review each dependency before public distribution or competition submission:

- SIFT-related tools/images
- Ollama
- Llama model license
- YARA
- Hayabusa
- Plaso/log2timeline
- React/Vite/npm dependencies

The novel contribution is the reproducible case-worker platform, deterministic MCP tool wrappers, traceable evidence/finding model, self-validating agent controller, and compact LLM reporting boundary.
