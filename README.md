# Traceable DFIR Investigator

**Evidence-Integrity-First Forensic Analysis Through Architectural Guardrails**

Traceable DFIR Investigator is a reproducible, Docker-first forensic investigation platform built for the SANS FindEvil / Protocol SIFT hackathon. It exposes the investigation engine as an actual Model Context Protocol (MCP) server, while also providing a FastAPI backend and React dashboard for judge-friendly review.

The core contract is:

```text
MCP client or UI or Claude Agent
  -> agent_run_case
  -> deterministic SIFT-backed tools (isolated in Docker)
  -> evidence records + trace records + findings
  -> validated report (evidence integrity enforced)
  -> compact optional LLM explanation
```

**Key principle: The LLM is intentionally not the source of truth.** It does not create findings, decide what is suspicious, approve evidence, or receive raw artifacts by default. The deterministic controller performs the investigation, stores provenance, validates traceability, and only then prepares a compact brief for Llama/Claude commentary.

---

## Evidence Integrity Through Architectural Boundaries

The core design principle: **evidence guardrails, not prompt restrictions**.

### Why This Matters

**Initial approach:**
- "Please don't modify the original evidence" (prompt-based restriction)
- Agent might ignore it anyway
- Evidence integrity relies on model compliance
- Hard to audit or recover if something fails

**This approach: Architectural enforcement**
- Original evidence lives on host filesystem (read-only mount)
- Worker container gets isolated, case-specific mount point
- SIFT tools physically cannot access original files
- Every finding traces back to a specific execution in a specific container
- Original evidence is never at risk, by design

This is why we use Docker per case since it's the architectural enforcement that makes evidence spoliation **impossible.**

### The Traceability Contract

Every finding in the investigation report is auditable.

A valid finding must include:

- `finding_id`: Unique identifier
- `evidence_id`: Which evidence was analyzed
- `trace_id`: Which tool execution produced this finding
- `artifact_path`: Path within the evidence
- `tool_name`: Name of the SIFT tool that found it
- `tool_output`: Raw output snippet (for verification)

**Example trace chain:**

```
Finding: "Suspicious process persistence detected"
  ↓ evidence_id: EVD-001
  ↓ trace_id: TRC-042
  ↓ tool_name: "registry_parser"
  ↓ artifact_path: "/cases/uploads/case.e01/Windows/System32/config/SYSTEM"
  ↓ tool_output: "HKLM\Software\Microsoft\Windows\Run contains shell.exe"
```

This traceability is not optional. The controller validates it before returning the report. If a finding lacks evidence/trace links, the report is rejected and regenerated from durable stores.

---

## Architecture

```text
┌─────────────────────────────────────────────────┐
│  MCP Client / Browser / Claude Agent  
└────────────┬────────────────────────────────────┘
             │
             │ (MCP tools / HTTP API)
             ↓
┌─────────────────────────────────────────────────┐
│ dfir_backend/server.py                          │
│ (MCP Server - Interface Layer)                  │
└────────────┬────────────────────────────────────┘
             │
             │ (Function calls)
             ↓
┌─────────────────────────────────────────────────┐
│ Deterministic Controller (agent_run_case)        │
│ - Case orchestration                            │
│ - Tool sequencing logic                         │
│ - Evidence/trace/finding validation             │
│ - Self-correction (retry, recheck, rebuild)     │
└────────────┬────────────────────────────────────┘
             │
             │ (Docker spawn)
             ↓
┌─────────────────────────────────────────────────┐
│ sift-worker-<case-id> Container (ISOLATED)      │
│ ┌──────────────────────────────────────────┐    │
│ │ SIFT Tools                               │    │
│ │ (yara, hayabusa, timeline, etc.)         │    │
│ └──────────────────────────────────────────┘    │
│ ┌──────────────────────────────────────────┐    │
│ │ Mounted Evidence (case-specific)          │    │
│ │ /cases/uploads/example.e01                │    │
│ │ (read-only from original)                 │    │
│ └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
             │
             │ (tool output only)
             ↓
┌─────────────────────────────────────────────────┐
│ Storage (Durable Records)                       │
│ - Evidence records (evidence_id, path, hash)    │
│ - Trace records (trace_id, tool, output)        │
│ - Finding records (finding_id, linked IDs)      │
│ - Investigation report (validated)              │
└─────────────────────────────────────────────────┘
```

**Architectural guardrail:** Docker isolation boundary ensures tools cannot modify original evidence.

### Directory Structure

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

### Runtime Flow

```text
MCP client             Browser UI             Claude Agent
    |                     |                        |
    | stdio               | HTTP                   | (stdio)
    v                     v                        v
dfir_backend/server.py  dfir_backend/api.py  (same tools)
    |                     |                        |
    +----------+----------+--------────────────────+
               |
               v
        deterministic controller (agent_run_case)
               |
               v
   Docker spawn: sift-worker-<case-id>
               |
               v
   evidence records + trace records + findings
               |
               v
     validated investigation report
               |
               v
      compact LLM brief for commentary
```

The HTTP API and MCP server share the same backend functions. `api.py` imports functions from `server.py`, so UI actions and MCP tool calls exercise the same deterministic controller.

---

## Built-In Self-Correction

The deterministic controller validates its own output at every step:

1. **Pre-execution:** Check worker container is ready. If not, retry startup.
2. **During execution:** Monitor tool success. Missing tools trigger a recheck.
3. **Post-execution:** Validate every finding has evidence/trace links.
   - Draft report missing links? Discard and rebuild from durable stores.
4. **Iteration logging:** Each retry/rebuild is logged with timestamps in `self_corrections`.

This is not prompt-based ("correct any mistakes"). It's structural validation built into the controller logic.

---

## Design Philosophy: Why Deterministic + MCP + Docker


**Why this architecture exists:**

**Initial approach:** "Point Claude at SIFT tools and let it orchestrate."
- Tools are shell commands (destructive)
- Claude might interpret safety instructions differently each time
- Evidence integrity relies on prompt compliance
- Difficult to reproduce failures

**This approach:** Type-safe MCP server + deterministic controller + Docker isolation.
- Tools are structured functions (can't be misused)
- Controller logic is explicit, deterministic, and auditable
- Evidence integrity is architectural, not behavioral
- Every finding is traceable to code execution
- Fully reproducible: same input → same execution → same output

**The MCP server is designed to accept a Claude agent or other AI orchestrator,** but the core analysis engine doesn't depend on it. Evidence integrity and traceability work whether the caller is:
- A human with the MCP inspector
- A Claude agent
- The HTTP API
- An AutoGen/CrewAI multi-agent system

The deterministic controller is the source of truth. The LLM (Llama/Claude) is an optional explanation layer on top.

---

## What Judges Should Recreate

The primary reproducible demo is local Docker Compose:

- Backend API: `http://localhost:8000`
- React/Vite dashboard: `http://localhost:5174`
- Ollama service: `http://localhost:11434`
- MCP stdio server: `dfir_backend/server.py`
- SIFT worker image: `dfir-sift-worker:latest`
- Per-case worker containers: `sift-worker-<case-id>`

### Recommended Flow

1. Clone the repository and enter this project directory.
2. Start the full stack with Docker Compose.
3. Load the built-in demo cases.
4. Run a case.
5. Inspect the finding IDs, evidence IDs, trace IDs, and generated report.
6. Click on finding links to see the evidence record and tool output that supports each claim.
7. Optionally connect an MCP client to `dfir_backend/server.py` and call the same tools directly.

---

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

---

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
5. Click on any finding to see its evidence record and trace record.

---

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

---

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

### Example MCP Client Configuration

For Claude Code or another MCP client:

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

### Core MCP Tools

- `create_case` — Create or return a reproducible DFIR case with an assigned SIFT worker
- `create_suspicious_demo_bundle` — Create demo cases with built-in findings
- `start_worker` — Start or verify the dedicated SIFT worker container for a case
- `case_status` — Return worker, mount, evidence, trace, and finding counts for a case
- `check_sift_tools` — Check which expected SIFT tools are available in the case worker
- `agent_run_case` — **Primary execution engine.** Runs full analysis pipeline with self-validation
- `mount_e01` — Mount E01/EX01 evidence in the case worker
- `list_directory` — List directory contents in the mounted evidence
- `extract_file` — Extract a file from the mounted evidence
- `inventory_artifacts` — Scan mounted evidence for notable artifacts (registry, logs, etc.)
- `scan_filesystem` — Scan filesystem for suspicious patterns
- `investigate_case` — Run the investigation pipeline
- `generate_investigation_report` — Compile findings into validated report
- `get_llm_case_brief` — Get compact case brief for LLM explanation
- `answer_case_question` — Answer a follow-up question about the case
- `list_case_evidence` — List all evidence records for a case
- `list_case_traces` — List all trace records for a case
- `list_case_findings` — List all findings for a case
- `get_evidence` — Get a specific evidence record
- `get_trace` — Get a specific trace record
- `get_finding_trace` — Get the trace record that supports a finding

**SIFT-oriented wrapper tools:**

- `list_processes` — List processes from memory artifacts
- `scan_yara` — Run YARA rules
- `scan_hayabusa` — Run Hayabusa timeline analysis
- `build_timeline` — Build event timeline from disk/memory artifacts
- `query_timeline` — Query the built timeline
- `scan_timeline` — Scan timeline for suspicious patterns

### MCP Smoke Test

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

---

## Example Output

When you run `agent_run_case("CASE-DEMO-PERSISTENCE-001")`:

```json
{
  "case_id": "CASE-DEMO-PERSISTENCE-001",
  "status": "completed",
  "findings": [
    {
      "finding_id": "FND-001",
      "title": "Suspicious run key persistence",
      "description": "Registry run key contains suspicious executable",
      "severity": "high",
      "evidence_id": "EVD-001",
      "trace_id": "TRC-042",
      "artifact_path": "HKLM\\Software\\Microsoft\\Windows\\Run",
      "tool_name": "registry_parser",
      "confidence": "high"
    }
  ],
  "evidence_records": [
    {
      "evidence_id": "EVD-001",
      "path": "/cases/uploads/case.e01",
      "hash": "sha256:a1b2c3...",
      "mounted_in_container": "sift-worker-CASE-DEMO-PERSISTENCE-001",
      "mount_point": "/cases/uploads"
    }
  ],
  "trace_records": [
    {
      "trace_id": "TRC-042",
      "tool_name": "registry_parser",
      "command": "registry_parser /cases/case.e01 'HKLM\\Software\\Microsoft\\Windows\\Run'",
      "output": "shell.exe [REG_SZ] ...",
      "container": "sift-worker-CASE-DEMO-PERSISTENCE-001",
      "timestamp": "2026-06-16T03:17:41Z"
    }
  ],
  "report": {
    "summary": "Case analysis complete. 1 high-severity finding.",
    "findings_count": 1,
    "validated": true
  }
}
```

**Every finding → evidence record → trace record → tool output.**

Any claim back to the specific tool execution that produced it, the container where it ran, and the evidence file analyzed.

---

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

`agent_run_case(case_id)` validates the generated report before returning it. Findings must include linked evidence and trace records so it can move from a narrative statement back to the deterministic tool output that supports it.

The agent/controller also writes a trace record for its own orchestration, making the run itself auditable.

---

## SIFT Workstation / Docker Integration

The project uses Docker to reproduce a SIFT-like execution boundary without requiring manual configuration of a workstation.

**Important containers and images:**

- `dfir-mcp`: backend API container. It includes the Docker CLI and mounts the host Docker socket.
- `ollama`: local Llama/Ollama service.
- `dfir-sift-worker:latest`: custom worker image built from `sift_worker/Dockerfile`.
- `sift-worker-<case-id>`: per-case worker container created on demand.

The backend uses the Docker socket to create one worker container per case. Evidence from `./evidence` is mounted into the worker under `/cases`, so deterministic tools operate against case-specific evidence paths.

**Why this approach:**

- ✅ Original evidence on host is never modified (read-only mount)
- ✅ Tools execute only inside isolated container
- ✅ Each case gets a fresh, reproducible SIFT environment
- ✅ Full auditability: which tool ran in which container for which case
- ✅ No manual SIFT VM setup required for judges

This is why a normal hosted container platform may not reproduce the full workflow unless it supports Docker socket access or sibling container creation.

---

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

---

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

---

## Backend API

The backend container runs:

```text
uvicorn dfir_backend.api:app --host 0.0.0.0 --port 8000
```

### Key Endpoints

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

---

## LLM / Ollama Boundary

The default model is:

```text
llama3.2:latest
```

### Configured Environment Variables

```text
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_TIMEOUT=180
OLLAMA_NUM_PREDICT=260
OLLAMA_CHAT_NUM_PREDICT=220
```

The LLM receives a compact case brief, not raw artifacts or full evidence files by default. The brief includes:
- case ID
- counts (findings, evidence, traces)
- finding IDs
- evidence IDs
- trace IDs
- artifact locations
- UI links for deep inspection

**LLM-generated text is marked as non-evidence commentary.** Evidence-backed claims should cite finding, evidence, and trace IDs.

---

## Hackathon Requirement Mapping

### Agentic Framework as Primary Execution Engine

`agent_run_case(case_id)` is the primary controller. It is exposed through MCP and through the HTTP API.

It performs:

- case loading
- worker startup
- SIFT tool checks
- evidence mount when applicable
- deterministic investigation
- traceability validation
- report generation
- compact LLM brief preparation

### Self-Correction

The controller records correction attempts in `self_corrections`.

Current self-correction behavior:

- retries worker startup if the first start does not report `running`
- restarts/rechecks if required tools are missing
- inspects case status after mount errors before failing
- regenerates the report from stored evidence/traces if traceability validation fails

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

- case summary
- findings
- evidence records
- trace records
- UI links
- compact LLM grounding brief
- optional Llama/Claude narrative

---

## Railway / Hosted Preview Note

Railway or similar platforms can host a lightweight preview of the API/frontend and deterministic demo fixture viewing. They should not be treated as the authoritative full forensic runtime unless they support the Docker requirements above.

The full local workflow starts sibling worker containers:

```text
dfir-mcp -> Docker socket -> sift-worker-<case-id>
```

That requires:

- Docker CLI in the backend container
- access to a Docker daemon
- `/var/run/docker.sock` mounted into the backend
- permission to create additional containers

For judging the complete SIFT-backed workflow, use Docker Compose locally or on a Linux/SIFT-compatible host.

---

## Environment Variables

### Backend

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

### Frontend

```text
VITE_API_BASE
```

For local Vite development, `VITE_API_BASE` can be empty because `vite.config.ts` proxies `/api` to `http://localhost:8000`.

---

## Cleaning Generated Data

PowerShell:

```powershell
.\scripts\clean-generated.ps1
```

Bash:

```bash
./scripts/clean-generated.sh
```
 
 Keep large forensic files under `evidence/` or upload them through the UI.

---

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

---

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

- keep reports short with `OLLAMA_NUM_PREDICT`
- keep chat answers short with `OLLAMA_CHAT_NUM_PREDICT`
- use a smaller or faster Ollama model
- warm up Ollama before a live demo

### Plaso / log2timeline E01 Errors

`build_timeline` may fail on incomplete, damaged, or chunk-missing E01 images. For hackathon reliability, the recommended path is:

```text
agent_run_case -> direct filesystem/artifact inventory -> traceable findings -> compact LLM brief
```

Timeline tooling remains available, but the built-in demo does not depend on damaged image timeline generation.

---

## License and Third-Party Tools

Review each dependency before public distribution or competition submission:

- SIFT-related tools/images
- Ollama
- Llama model license
- YARA
- Hayabusa
- Plaso/log2timeline
- React/Vite/npm dependencies

**The novel contribution is:**
- Reproducible case-worker platform with Docker isolation
- Deterministic MCP tool wrappers (type-safe, non-destructive)
- Traceable evidence/finding/trace model
- Self-validating agent controller
- Architectural guardrails (not prompt-based) for evidence integrity
- Compact LLM reporting boundary (LLM as explanation layer, not source of truth)
