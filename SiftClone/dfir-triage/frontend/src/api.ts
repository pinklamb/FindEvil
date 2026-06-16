import type {
  CaseRecord,
  CaseStatus,
  ChatAnswer,
  EvidenceFile,
  EvidenceFileList,
  AgentRunResult,
  InvestigationReport,
  LlmBrief,
  LlmReport,
  ToolStatus,
  WorkerStartResult
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function getCases(): Promise<Record<string, CaseRecord>> {
  return request<Record<string, CaseRecord>>("/api/cases");
}

export async function createDemoCase(caseId: string): Promise<unknown> {
  return request("/api/cases/demo", {
    method: "POST",
    body: JSON.stringify({ case_id: caseId, reset: true })
  });
}

export async function createDemoBundle(): Promise<unknown> {
  return request("/api/cases/demo-bundle", {
    method: "POST",
    body: JSON.stringify({ reset: true })
  });
}

export async function getEvidenceFiles(): Promise<EvidenceFileList> {
  return request<EvidenceFileList>("/api/evidence-files");
}

export async function uploadEvidenceFile(file: File, onProgress?: (percent: number) => void): Promise<EvidenceFile> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE}/api/evidence-files`);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        try {
          resolve(JSON.parse(request.responseText) as EvidenceFile);
        } catch (err) {
          reject(err);
        }
        return;
      }
      reject(new Error(request.responseText || `Upload failed: ${request.status}`));
    };
    request.onerror = () => reject(new Error("Upload failed: network error"));
    request.send(form);
  });
}

export async function createCaseFromEvidence(evidencePath: string, caseId?: string): Promise<CaseRecord> {
  return request<CaseRecord>("/api/cases/from-evidence", {
    method: "POST",
    body: JSON.stringify({ evidence_path: evidencePath, case_id: caseId || null })
  });
}

export async function getCaseStatus(caseId: string): Promise<CaseStatus> {
  return request<CaseStatus>(`/api/cases/${encodeURIComponent(caseId)}/status`);
}

export async function startWorker(caseId: string): Promise<WorkerStartResult> {
  return request<WorkerStartResult>(`/api/cases/${encodeURIComponent(caseId)}/start`, {
    method: "POST"
  });
}

export async function mountCase(caseId: string, evidencePath: string): Promise<unknown> {
  return request(`/api/cases/${encodeURIComponent(caseId)}/mount`, {
    method: "POST",
    body: JSON.stringify({ evidence_path: evidencePath })
  });
}

export async function getToolStatus(caseId: string): Promise<ToolStatus> {
  return request<ToolStatus>(`/api/cases/${encodeURIComponent(caseId)}/tools`);
}

export async function getReport(caseId: string): Promise<InvestigationReport> {
  return request<InvestigationReport>(`/api/cases/${encodeURIComponent(caseId)}/report`);
}

export async function investigateCase(caseId: string): Promise<InvestigationReport> {
  return request<InvestigationReport>(`/api/cases/${encodeURIComponent(caseId)}/investigate`, {
    method: "POST"
  });
}

export async function agentRunCase(caseId: string): Promise<AgentRunResult> {
  return request<AgentRunResult>(`/api/cases/${encodeURIComponent(caseId)}/agent-run`, {
    method: "POST"
  });
}

export async function generateLlmReport(caseId: string): Promise<LlmReport> {
  return request<LlmReport>(`/api/cases/${encodeURIComponent(caseId)}/llm-report`, {
    method: "POST"
  });
}

export async function getLlmBrief(caseId: string): Promise<LlmBrief> {
  return request<LlmBrief>(`/api/cases/${encodeURIComponent(caseId)}/llm-brief`);
}

export async function askCaseQuestion(caseId: string, question: string): Promise<ChatAnswer> {
  return request<ChatAnswer>(`/api/cases/${encodeURIComponent(caseId)}/chat`, {
    method: "POST",
    body: JSON.stringify({ question })
  });
}
