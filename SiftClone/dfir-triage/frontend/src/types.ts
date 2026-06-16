export type CaseRecord = {
  case_id: string;
  status?: string;
  evidence_path?: string;
  worker_container?: string;
  container_image?: string;
  image_path?: string | null;
  filesystem?: string | null;
  offset?: string | null;
  evidence_ids?: string[];
  trace_ids?: string[];
  finding_ids?: string[];
};

export type EvidenceFile = {
  name: string;
  relative_path: string;
  container_path: string;
  size_bytes: number;
  extension: string;
  accepted: boolean;
};

export type EvidenceFileList = {
  evidence_root: string;
  container_root: string;
  accepted_extensions: string[];
  files: EvidenceFile[];
};

export type EvidenceRecord = {
  case_id: string;
  evidence_id: string;
  trace_id?: string;
  collected_at?: string;
  worker?: string;
  tool?: string;
  artifact_path?: string;
  result_summary?: Record<string, unknown>;
  ui_link?: string;
};

export type TraceRecord = {
  trace_id: string;
  case_id: string;
  evidence_id?: string;
  tool?: string;
  worker_container?: string;
  container_image?: string;
  artifact_path?: string;
  inode?: string | null;
  output_path?: string | null;
  output_sha256?: string | null;
  command_args?: string[];
  status?: string;
  summary?: Record<string, unknown>;
  ui_link?: string;
};

export type FindingRecord = {
  case_id?: string;
  finding_id: string;
  status: string;
  title: string;
  severity: string;
  confidence: number;
  rule_ids: string[];
  artifact_locations: Array<Record<string, unknown>>;
  evidence: EvidenceRecord[];
  traces: TraceRecord[];
  ui_link?: string;
};

export type InvestigationReport = {
  analysis_contract?: Record<string, unknown>;
  case: CaseRecord;
  summary: {
    evidence_count: number;
    trace_count: number;
    finding_count: number;
    draft_finding_count: number;
  };
  findings: FindingRecord[];
  evidence: EvidenceRecord[];
  traces: TraceRecord[];
  links: Record<string, string>;
};

export type CaseStatus = {
  case_id: string;
  status?: string;
  worker_container?: string;
  worker_running?: boolean;
  container_image?: string;
  uses_custom_worker_image?: boolean;
  evidence_path?: string;
  image_path?: string | null;
  filesystem?: string | null;
  offset?: string | null;
  docker_available?: boolean;
  docker_status_error?: string | null;
  evidence_count: number;
  trace_count: number;
  finding_count: number;
};

export type ToolStatus = {
  tools: Record<string, { available: boolean; path?: string | null; error?: string | null }>;
};

export type LlmInput = {
  brief?: string;
  token_efficiency?: {
    raw_artifacts_sent_to_llm: boolean;
    format: string;
    estimated_prompt_chars: number;
    estimated_prompt_tokens: number;
    finding_limit: number;
    includes_raw_artifact_content?: boolean;
    includes_full_json?: boolean;
  };
};

export type LlmReport = {
  case_id: string;
  llm_explanation_is_evidence: boolean;
  narrative: string;
  llm_input?: LlmInput;
};

export type LlmBrief = {
  case_id: string;
  brief: string;
  token_efficiency: NonNullable<LlmInput["token_efficiency"]>;
  llm_explanation_is_evidence: boolean;
};

export type ChatAnswer = {
  case_id: string;
  question: string;
  answer: string;
  llm_explanation_is_evidence: boolean;
  llm_input?: LlmInput;
};

export type WorkerStartResult = {
  case_id: string;
  worker_container?: string;
  container_image?: string;
  running?: boolean;
  error?: string;
  stage?: string;
};

export type AgentRunResult = {
  agent_run_id: string;
  case_id: string;
  status: string;
  started_at: string;
  completed_at: string;
  steps: Array<{ step: string; status: string; [key: string]: unknown }>;
  self_corrections: Array<Record<string, unknown>>;
  validation: {
    ok: boolean;
    errors: string[];
    finding_count: number;
    evidence_count: number;
    trace_count: number;
  };
  report?: InvestigationReport;
  llm_input?: unknown;
};
