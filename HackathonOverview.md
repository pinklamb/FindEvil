# FindEvil / Protocol SIFT Alignment

This project is a deterministic DFIR platform designed for agent execution on top of SIFT-style worker containers.

## Requirement Mapping

- Agentic framework as primary execution engine:
  - `agent_run_case(case_id)` is the primary orchestration tool.
  - It is exposed through MCP and the HTTP API.
  - It runs deterministic backend tools, records each step, performs validation, and returns a structured investigation report.

- Self-correction:
  - The agent controller retries worker startup when the first start fails.
  - It restarts and rechecks when required tools are missing.
  - It inspects case status after mount errors before failing.
  - It regenerates reports from stored evidence/traces when traceability validation fails.
  - Each correction is recorded in `self_corrections`.

- Accuracy validation:
  - Every finding must link to evidence and trace records.
  - Validation checks for `finding_id`, `evidence_id`, `trace_id`, tool name, and artifact path.
  - The agent run writes its own trace record, so orchestration is auditable too.

- Analytical reasoning:
  - `generate_investigation_report` returns a structured case report with findings, evidence records, trace records, and UI links.
  - `generate_llm_investigative_report` turns the compact validated findings brief into narrative prose.
  - Llama is not allowed to create findings, mutate evidence, or decide what is suspicious.

- SIFT / Linux platform:
  - Case work runs inside dedicated SIFT worker containers.
  - Multiple cases map to independent worker containers.
  - Ollama is shared as a separate service.

## Novel Contribution

The novel layer is the reproducible case-worker platform and traceable agent controller:

- one SIFT worker container per case,
- deterministic MCP tool wrappers,
- per-case evidence, trace, and finding stores,
- self-correcting agent execution,
- compact LLM brief generation to reduce token usage,
- UI-ready evidence links for future report/dashboard views.

## LLM Boundary

The LLM is a conversational and narrative layer only. It receives compact finding summaries, evidence IDs, trace IDs, artifact paths, and UI links. It does not receive raw artifacts or full tool output by default, and its prose is clearly marked as non-evidence commentary.
