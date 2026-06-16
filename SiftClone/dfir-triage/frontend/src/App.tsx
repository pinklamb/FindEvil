import { useEffect, useMemo, useRef, useState } from "react";
import {
  agentRunCase,
  askCaseQuestion,
  createDemoBundle,
  createCaseFromEvidence,
  generateLlmReport,
  getCaseStatus,
  getCases,
  getEvidenceFiles,
  getLlmBrief,
  uploadEvidenceFile,
} from "./api";
import type {
  CaseRecord,
  ChatAnswer,
  EvidenceFile,
  EvidenceRecord,
  FindingRecord,
  InvestigationReport,
  LlmBrief,
} from "./types";

type StepState = "done" | "active" | "wait" | "error";

type LogEntry = {
  time: string;
  text: string;
  type: StepState;
};

type ChatMessage = {
  role: "system" | "user" | "ai";
  text: string;
  tag?: string;
};

const SEV_STYLES: Record<string, string> = {
  critical: "sev-critical",
  high: "sev-high",
  medium: "sev-medium",
  low: "sev-low",
};

const BOOT_STEPS = [
  ["docker", "Docker daemon"],
  ["sift", "SIFT worker"],
  ["ollama", "Ollama service"],
  ["mcp", "Backend API :8000"],
  ["store", "Evidence store"],
  ["ewf", "EWF mounted"],
] as const;

const WORKERS = [
  ["mount", "mount_worker"],
  ["fs", "filesystem_worker"],
  ["timeline", "timeline_worker"],
  ["hayabusa", "hayabusa_worker"],
  ["yara", "yara_worker"],
] as const;

function shortTime() {
  return new Date().toTimeString().slice(0, 5);
}

function nowUTC() {
  return new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`;
}

function icon(state: StepState) {
  if (state === "done") return "OK";
  if (state === "active") return ">>";
  if (state === "error") return "!!";
  return "--";
}

function normalizeFindings(report: InvestigationReport | null): FindingRecord[] {
  return report?.findings ?? [];
}

export default function App() {
  const [activeTab, setActiveTab] = useState("CASES");
  const [clock, setClock] = useState(nowUTC());
  const [cases, setCases] = useState<Record<string, CaseRecord>>({});
  const [evidenceFiles, setEvidenceFiles] = useState<EvidenceFile[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceFile | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [caseInfo, setCaseInfo] = useState<CaseRecord | null>(null);
  const [report, setReport] = useState<InvestigationReport | null>(null);
  const [reportsByCase, setReportsByCase] = useState<Record<string, InvestigationReport>>({});
  const [llmBrief, setLlmBrief] = useState<LlmBrief | null>(null);
  const [llmNarrative, setLlmNarrative] = useState("");
  const [llmGenerating, setLlmGenerating] = useState(false);
  const [chatGenerating, setChatGenerating] = useState(false);
  const [selfCorrections, setSelfCorrections] = useState<Array<Record<string, unknown>>>([]);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [reportStatus, setReportStatus] = useState<"idle" | "running" | "ready" | "error">("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "system", text: "// DFIR console ready. Select evidence, create a case, then run the pipeline." },
  ]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [bootState, setBootState] = useState<Record<string, StepState>>({
    docker: "wait",
    sift: "wait",
    ollama: "wait",
    mcp: "wait",
    store: "wait",
    ewf: "wait",
    mount: "wait",
    fs: "wait",
    timeline: "wait",
    hayabusa: "wait",
    yara: "wait",
  });

  const findings = useMemo(() => normalizeFindings(report), [report]);
  const evidence = report?.evidence ?? [];
  const demoEvidenceCards = useMemo<EvidenceFile[]>(
    () => Object.values(cases)
      .filter((caseRecord) => caseRecord.evidence_path?.startsWith("/fixtures/"))
      .map((caseRecord) => ({
        name: caseRecord.case_id,
        relative_path: caseRecord.evidence_path || "",
        container_path: caseRecord.evidence_path || "",
        size_bytes: caseRecord.finding_ids?.length ?? 0,
        extension: ".demo",
        accepted: true,
      })),
    [cases],
  );
  const visibleEvidenceFiles = useMemo(() => [...demoEvidenceCards, ...evidenceFiles], [demoEvidenceCards, evidenceFiles]);

  function addLog(text: string, type: StepState = "done") {
    setLogs((prev) => [...prev, { time: shortTime(), text, type }].slice(-80));
  }

  async function refreshAll(preferredCaseId?: string) {
    try {
      const [files, caseMap] = await Promise.all([getEvidenceFiles(), getCases()]);
      setEvidenceFiles(files.files);
      setSelectedEvidence((current) => current ?? files.files[0] ?? null);
      setCases(caseMap);
      setBootState((prev) => ({ ...prev, mcp: "done", store: "done" }));

      const nextCase = preferredCaseId || selectedCaseId || Object.keys(caseMap)[0] || "";
      if (nextCase) {
        await loadCase(nextCase);
      }
    } catch (err) {
      addLog(`backend unavailable: ${err instanceof Error ? err.message : String(err)}`, "error");
      setBootState((prev) => ({ ...prev, mcp: "error" }));
    }
  }

  async function loadCase(caseId: string) {
    setSelectedCaseId(caseId);
    const status = await getCaseStatus(caseId);
    const caseRecord = cases[caseId] ?? status;
    setCaseInfo({ ...caseRecord, ...status });
    setBootState((prev) => ({
      ...prev,
      docker: status.docker_available === false ? "error" : "done",
      sift: status.worker_running ? "done" : "wait",
      ewf: status.image_path ? "done" : "wait",
      mount: status.image_path ? "done" : "wait",
    }));
  }

  async function openCase(caseId: string) {
    await loadCase(caseId);
    setActiveTab("INVESTIGATE");
  }

  useEffect(() => {
    refreshAll();
    const id = setInterval(() => setClock(nowUTC()), 1000);
    return () => clearInterval(id);
  }, []);

  async function handleUpload(file: File | null) {
    if (!file) return;
    setLoading(true);
    setUploadName(file.name);
    setUploadProgress(0);
    try {
      addLog(`uploading ${file.name} (${formatBytes(file.size)})`, "active");
      const uploaded = await uploadEvidenceFile(file, setUploadProgress);
      addLog(`uploaded ${uploaded.relative_path}`, "done");
      setUploadProgress(100);
      addLog(`creating case from ${uploaded.container_path}`, "active");
      const created = await createCaseFromEvidence(uploaded.container_path);
      addLog(`case ready: ${created.case_id}`, "done");
      await refreshAll(created.case_id);
      setSelectedEvidence(uploaded);
      setActiveTab("INVESTIGATE");
    } catch (err) {
      addLog(`add case failed: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setUploadProgress(null);
      setUploadName("");
      setLoading(false);
    }
  }

  async function createCaseForEvidence(evidenceFile: EvidenceFile) {
    setLoading(true);
    try {
      setSelectedEvidence(evidenceFile);
      if (evidenceFile.extension === ".demo") {
        const demoCase = Object.values(cases).find((caseRecord) => caseRecord.evidence_path === evidenceFile.container_path);
        if (!demoCase) throw new Error("Demo case was not found");
        addLog(`selected demo case: ${demoCase.case_id}`, "done");
        await loadCase(demoCase.case_id);
        return;
      }
      addLog(`creating case from ${evidenceFile.container_path}`, "active");
      const created = await createCaseFromEvidence(evidenceFile.container_path);
      addLog(`case ready: ${created.case_id}`, "done");
      await refreshAll(created.case_id);
    } catch (err) {
      addLog(`case create failed: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectEvidence(file: EvidenceFile) {
    if (file.extension === ".demo") {
      setSelectedEvidence(file);
      return;
    }
    await createCaseForEvidence(file);
  }

  async function handleAgentRunCase() {
    let targetCaseId = caseInfo?.case_id || "";
    if (!targetCaseId && selectedEvidence?.extension === ".demo") {
      const demoCase = Object.values(cases).find((caseRecord) => caseRecord.evidence_path === selectedEvidence.container_path);
      targetCaseId = demoCase?.case_id || "";
    }
    if (!targetCaseId) return;
    setLoading(true);
    setReport(null);
    setLlmNarrative("");
    setLlmBrief(null);
    setSelfCorrections([]);
    setReportStatus("running");
    setBootState((prev) => ({
      ...prev,
      docker: "active",
      sift: "active",
      mcp: "active",
      store: "active",
    }));
    try {
      addLog(`agent controller started: ${targetCaseId}`, "active");
      const result = await agentRunCase(targetCaseId);
      result.steps.forEach((step) => {
        addLog(`agent ${step.step}: ${step.status}`, step.status === "error" ? "error" : "done");
      });
      if (result.self_corrections.length) {
        addLog(`self-corrections: ${result.self_corrections.length}`, "done");
        result.self_corrections.forEach((correction) => {
          addLog(`self-corrected ${String(correction.stage)} -> ${String(correction.action)}`, "done");
        });
      }
      setSelfCorrections(result.self_corrections);
      if (!result.validation.ok) {
        throw new Error(`validation failed: ${result.validation.errors.join("; ")}`);
      }
      if (result.report) {
        setReport(result.report);
        setReportsByCase((prev) => ({ ...prev, [targetCaseId]: result.report! }));
        setCaseInfo(result.report.case);
      }
      setBootState((prev) => ({
        ...prev,
        docker: "done",
        sift: "done",
        ollama: "done",
        mcp: "done",
        store: "done",
        ewf: "done",
        mount: "done",
        fs: "done",
        timeline: "done",
        hayabusa: "done",
        yara: "done",
      }));
      try {
        setLlmBrief(await getLlmBrief(targetCaseId));
      } catch {
        addLog("LLM brief not available yet", "error");
      }
      setLlmGenerating(true);
      addLog("Llama generating narrative from compact validated brief", "active");
      try {
        const llmReport = await generateLlmReport(targetCaseId);
        setLlmNarrative(llmReport.narrative);
        if (llmReport.llm_input?.token_efficiency) {
          addLog(`Llama prompt approx ${llmReport.llm_input.token_efficiency.estimated_prompt_tokens} tokens`, "done");
        }
        addLog("Llama narrative ready", "done");
      } catch (err) {
        addLog(`Llama narrative failed: ${err instanceof Error ? err.message : String(err)}`, "error");
      } finally {
        setLlmGenerating(false);
      }
      setReportStatus("ready");
      addLog(`agent run complete: ${result.agent_run_id}`, "done");
    } catch (err) {
      setReportStatus("error");
      addLog(`agent run failed: ${err instanceof Error ? err.message : String(err)}`, "error");
      setBootState((prev) => ({
        ...prev,
        docker: prev.docker === "active" ? "error" : prev.docker,
        sift: prev.sift === "active" ? "error" : prev.sift,
        mcp: prev.mcp === "active" ? "error" : prev.mcp,
        store: prev.store === "active" ? "error" : prev.store,
      }));
    } finally {
      setLoading(false);
      await refreshAll(targetCaseId);
    }
  }

  async function handleLoadDemoCases() {
    setLoading(true);
    try {
      addLog("loading two suspicious demo cases", "active");
      await createDemoBundle();
      await refreshAll("CASE-DEMO-PERSISTENCE-001");
      setSelectedEvidence({
        name: "CASE-DEMO-PERSISTENCE-001",
        relative_path: "/fixtures/suspicious-persistence-demo.json",
        container_path: "/fixtures/suspicious-persistence-demo.json",
        size_bytes: 3,
        extension: ".demo",
        accepted: true,
      });
      addLog("demo cases ready: persistence + exfiltration", "done");
    } catch (err) {
      addLog(`demo load failed: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleSend(question: string) {
    if (!question.trim()) return;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    if (!caseInfo?.case_id) {
      setMessages((prev) => [...prev, { role: "system", text: "// create or select a case first" }]);
      return;
    }
    setLoading(true);
    setChatGenerating(true);
    try {
      const answer: ChatAnswer = await askCaseQuestion(caseInfo.case_id, question);
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          text: answer.answer,
          tag: answer.llm_input?.token_efficiency
            ? `~${answer.llm_input.token_efficiency.estimated_prompt_tokens} prompt tokens`
            : undefined,
        },
      ]);
      addLog("case chat answered from compact brief", "done");
    } catch (err) {
      setMessages((prev) => [...prev, { role: "system", text: `// chat failed: ${err instanceof Error ? err.message : String(err)}` }]);
      addLog("chat failed", "error");
    } finally {
      setChatGenerating(false);
      setLoading(false);
    }
  }

  return (
    <>
      <style>{CSS}</style>
      <NavBar activeTab={activeTab} setActiveTab={setActiveTab} clock={clock} />

      {activeTab === "INVESTIGATE" && (
        <>
          <HeroBar caseInfo={caseInfo} findings={findings} />
          <EvidenceDock
            evidenceFiles={visibleEvidenceFiles}
            selectedEvidence={selectedEvidence}
            caseReady={Boolean(caseInfo?.case_id)}
            uploadName={uploadName}
            uploadProgress={uploadProgress}
            loading={loading}
            onSelectEvidence={handleSelectEvidence}
            onUpload={handleUpload}
            onLoadDemoCases={handleLoadDemoCases}
            onRunCase={handleAgentRunCase}
          />
          {reportStatus !== "idle" && (
            <div className={`report-status ${reportStatus}`}>
              {reportStatus === "running" && "Running agent pipeline. Llama will compose from the validated brief..."}
              {reportStatus === "ready" && "Report ready below."}
              {reportStatus === "error" && "Report generation failed. Check pipeline log."}
            </div>
          )}
          <div className="main-grid">
            <BootPanel bootState={bootState} caseInfo={caseInfo} />
            <ChatPanel messages={messages} onSend={handleSend} loading={loading} generating={chatGenerating} />
            <LogPanel logs={logs} />
          </div>
          <CaseRack cases={cases} reportsByCase={reportsByCase} selectedCaseId={selectedCaseId} onSelect={loadCase} />
          <FindingsPanel findings={findings} />
          {report && <ReportPanel report={report} evidence={evidence} llmBrief={llmBrief} llmNarrative={llmNarrative} llmGenerating={llmGenerating} selfCorrections={selfCorrections} />}
        </>
      )}

      {activeTab === "CASES" && (
        <CasesPanel
          cases={cases}
          reportsByCase={reportsByCase}
          selectedCaseId={selectedCaseId}
          onSelect={openCase}
          onUpload={handleUpload}
          uploadName={uploadName}
          uploadProgress={uploadProgress}
          onLoadDemoCases={handleLoadDemoCases}
          loading={loading}
        />
      )}

    </>
  );
}

function NavBar({ activeTab, setActiveTab, clock }: {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  clock: string;
}) {
  return (
    <nav className="topnav">
      <div className="logo">DFIR<span className="logo-slash">//</span>TRIAGE</div>
      <div className="nav-links">
        {["CASES", "INVESTIGATE"].map((tab) => (
          <button key={tab} className={`nav-link ${activeTab === tab ? "active" : ""}`} onClick={() => setActiveTab(tab)}>
            {tab}
          </button>
        ))}
      </div>
      <div className="clock mono">{clock}</div>
    </nav>
  );
}

function EvidenceDock({
  evidenceFiles,
  selectedEvidence,
  caseReady,
  uploadName,
  uploadProgress,
  loading,
  onSelectEvidence,
  onUpload,
  onLoadDemoCases,
  onRunCase,
}: {
  evidenceFiles: EvidenceFile[];
  selectedEvidence: EvidenceFile | null;
  caseReady: boolean;
  uploadName: string;
  uploadProgress: number | null;
  loading: boolean;
  onSelectEvidence: (file: EvidenceFile) => void;
  onUpload: (file: File | null) => void;
  onLoadDemoCases: () => void;
  onRunCase: () => void;
}) {
  return (
    <div className="evidence-dock">
      <div>
        <div className="panel-label">Evidence Intake</div>
        <div className="evidence-list">
          {evidenceFiles.map((file) => (
            <button
              key={file.container_path}
              className={`evidence-chip ${selectedEvidence?.container_path === file.container_path ? "active" : ""}`}
              onClick={() => onSelectEvidence(file)}
            >
              <span>{file.extension === ".demo" ? `${file.name} (demo)` : file.name}</span>
              <small>{file.extension === ".demo" ? "prebuilt suspicious case - select, then run" : `${file.container_path} - click to add case`}</small>
            </button>
          ))}
          {evidenceFiles.length === 0 && <span className="empty">// no evidence files or demo cases loaded</span>}
        </div>
      </div>
      <div className="case-create">
        <label className="upload-btn">
          ADD CASE
          <input type="file" accept=".e01,.ex01" onChange={(event) => onUpload(event.currentTarget.files?.[0] ?? null)} />
        </label>
        <button className="btn-outline" disabled={loading} onClick={onLoadDemoCases}>LOAD DEMOS</button>
        <button className="btn" disabled={loading || (!caseReady && selectedEvidence?.extension !== ".demo")} onClick={onRunCase}>RUN CASE</button>
        {uploadProgress !== null && (
          <div className="upload-status">
            <span>{uploadName || "uploading evidence"}</span>
            <div className="upload-track"><div style={{ width: `${uploadProgress}%` }} /></div>
            <small>{uploadProgress}%</small>
          </div>
        )}
      </div>
    </div>
  );
}

function CaseRack({
  cases,
  reportsByCase,
  selectedCaseId,
  onSelect,
}: {
  cases: Record<string, CaseRecord>;
  reportsByCase: Record<string, InvestigationReport>;
  selectedCaseId: string;
  onSelect: (caseId: string) => void;
}) {
  const caseList = Object.values(cases);
  if (!caseList.length) return null;
  return (
    <section className="case-rack">
      <div className="panel-label">Independent Case Workers</div>
      <div className="case-rack-grid">
        {caseList.map((caseRecord) => {
          const ready = Boolean(reportsByCase[caseRecord.case_id]);
          return (
            <button
              key={caseRecord.case_id}
              className={`case-worker-card ${selectedCaseId === caseRecord.case_id ? "active" : ""}`}
              onClick={() => onSelect(caseRecord.case_id)}
            >
              <span className={ready ? "worker-dot ready" : "worker-dot"} />
              <strong>{caseRecord.case_id}</strong>
              <small>{caseRecord.worker_container || "worker pending"}</small>
              <em>{ready ? "report ready" : caseRecord.status || "created"}</em>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function BootPanel({ bootState, caseInfo }: { bootState: Record<string, StepState>; caseInfo: CaseRecord | null }) {
  return (
    <aside className="panel left-panel">
      <div className="panel-label">System Boot</div>
      {BOOT_STEPS.map(([key, label]) => (
        <div key={key} className={`boot-line ${bootState[key] || "wait"}`}>
          <span className="boot-icon">{icon(bootState[key] || "wait")}</span>{label}
        </div>
      ))}
      <div className="panel-label" style={{ marginTop: 24 }}>Workers</div>
      {WORKERS.map(([key, label]) => (
        <div key={key} className={`boot-line ${bootState[key] || "wait"}`}>
          <span className="boot-icon">{icon(bootState[key] || "wait")}</span>{label}
        </div>
      ))}
      {caseInfo && (
        <>
          <div className="panel-label" style={{ marginTop: 24 }}>Case</div>
          <div className="boot-line done"><span className="boot-icon">#</span>{caseInfo.case_id}</div>
          <div className="boot-line done"><span className="boot-icon">&gt;</span>{caseInfo.evidence_path?.split("/").pop()}</div>
          {caseInfo.filesystem && <div className="boot-line done"><span className="boot-icon">&gt;</span>{caseInfo.filesystem.toUpperCase()}</div>}
          <div className="boot-line done">
            <span className="boot-icon">&gt;</span>{caseInfo.finding_ids?.length ?? 0} findings / {caseInfo.evidence_ids?.length ?? 0} evidence
          </div>
        </>
      )}
    </aside>
  );
}

function ChatPanel({ messages, onSend, loading, generating }: { messages: ChatMessage[]; onSend: (message: string) => void; loading: boolean; generating: boolean }) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), [messages]);
  function send() {
    if (!input.trim()) return;
    onSend(input.trim());
    setInput("");
  }
  return (
    <div className="panel center-panel">
      <div className="panel-label">Analyst Chat - Llama</div>
      <div className="chat-area">
        {messages.map((message, index) => (
          <div key={index} className={`msg ${message.role}`}>
            {message.text}
            {message.tag && <div className="ev-tag">{message.tag}</div>}
          </div>
        ))}
        {generating && (
          <div className="msg ai generating">
            Llama is generating a grounded response<span className="dots" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input-row">
        <input className="chat-input mono" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => event.key === "Enter" && send()} placeholder="Ask about findings, evidence IDs, or traces..." />
        <button className="btn" disabled={loading} onClick={send}>SEND</button>
      </div>
    </div>
  );
}

function LogPanel({ logs }: { logs: LogEntry[] }) {
  return (
    <aside className="panel right-panel">
      <div className="panel-label">Pipeline Log</div>
      {logs.map((log, index) => (
        <div key={index} className={`tl-item ${log.type}`}>
          <span className="tl-time">{log.time}</span>
          <span className="tl-event">{log.text}</span>
        </div>
      ))}
      {logs.length === 0 && <div className="empty">// waiting for case action</div>}
    </aside>
  );
}

function HeroBar({ caseInfo, findings }: { caseInfo: CaseRecord | null; findings: FindingRecord[] }) {
  const critical = findings.filter((finding) => finding.severity === "critical").length;
  const high = findings.filter((finding) => finding.severity === "high").length;
  return (
    <header className="hero">
      <div>
        <div className="hero-eyebrow">Traceable DFIR Platform</div>
        <h1 className="hero-title">Case <span className="red">Investigator</span></h1>
        <p className="hero-subtitle">Create cases from mounted evidence, watch Docker/SIFT stages, and generate Llama summaries from compact findings only.</p>
      </div>
      <div className="hero-metrics">
        <div className="metric"><span className="metric-val red">{critical}</span><span className="metric-label">Critical</span></div>
        <div className="metric"><span className="metric-val amber">{high}</span><span className="metric-label">High</span></div>
        <div className="metric"><span className="metric-val">{caseInfo?.evidence_ids?.length ?? 0}</span><span className="metric-label">Evidence</span></div>
      </div>
      <div className="hero-corner mono">{caseInfo?.case_id ?? "NO CASE SELECTED"}</div>
    </header>
  );
}

function FindingsPanel({ findings }: { findings: FindingRecord[] }) {
  const [selected, setSelected] = useState<string>("");
  return (
    <section className="panel findings-panel">
      <div className="panel-label">Findings</div>
      {findings.map((finding) => (
        <div key={finding.finding_id} className={`finding ${selected === finding.finding_id ? "selected" : ""}`} onClick={() => setSelected(selected === finding.finding_id ? "" : finding.finding_id)}>
          <span className={`sev ${SEV_STYLES[finding.severity] ?? "sev-low"}`}>{finding.severity.toUpperCase()}</span>
          <div>
            <div className="finding-title">{finding.title}</div>
            <div className="finding-ev mono">
              {finding.finding_id} | EV {(finding.evidence ?? []).map((entry) => entry.evidence_id).join(", ")} | TR {(finding.traces ?? []).map((entry) => entry.trace_id).join(", ")}
            </div>
            {selected === finding.finding_id && (
              <div className="finding-explain">
                Rules: {finding.rule_ids.join(", ")}. Confidence: {Math.round(finding.confidence * 100)}%.
              </div>
            )}
          </div>
        </div>
      ))}
      {findings.length === 0 && <div className="empty">// no findings yet - run case pipeline</div>}
    </section>
  );
}

function CasesPanel({
  cases,
  reportsByCase,
  selectedCaseId,
  onSelect,
  onUpload,
  uploadName,
  uploadProgress,
  onLoadDemoCases,
  loading,
}: {
  cases: Record<string, CaseRecord>;
  reportsByCase: Record<string, InvestigationReport>;
  selectedCaseId: string;
  onSelect: (caseId: string) => void;
  onUpload: (file: File | null) => void;
  uploadName: string;
  uploadProgress: number | null;
  onLoadDemoCases: () => void;
  loading: boolean;
}) {
  return (
    <div className="landing">
      <section className="landing-header">
        <div>
          <div className="hero-eyebrow">Case Container Landing</div>
          <h1 className="hero-title">Independent <span className="red">Investigations</span></h1>
          <p className="hero-subtitle">Each case maps to its own SIFT worker container. Open a case to inspect findings, chat, reports, traces, and Llama grounding.</p>
        </div>
        <div className="landing-actions">
          <label className="upload-btn">
            ADD CASE
            <input type="file" accept=".e01,.ex01" onChange={(event) => onUpload(event.currentTarget.files?.[0] ?? null)} />
          </label>
          <button className="btn-outline" disabled={loading} onClick={onLoadDemoCases}>LOAD DEMOS</button>
          {uploadProgress !== null && (
            <div className="upload-status">
              <span>{uploadName || "uploading evidence"}</span>
              <div className="upload-track"><div style={{ width: `${uploadProgress}%` }} /></div>
              <small>{uploadProgress}%</small>
            </div>
          )}
        </div>
      </section>
      <section className="case-container-grid">
        {Object.values(cases).map((caseRecord) => {
          const ready = Boolean(reportsByCase[caseRecord.case_id]);
          return (
            <button key={caseRecord.case_id} className={`container-card ${selectedCaseId === caseRecord.case_id ? "active" : ""}`} onClick={() => onSelect(caseRecord.case_id)}>
              <div className="container-card-top">
                <span className={ready ? "worker-dot ready" : "worker-dot"} />
                <span className="sev sev-medium">{caseRecord.status ?? "CREATED"}</span>
              </div>
              <strong>{caseRecord.case_id}</strong>
              <small>{caseRecord.worker_container || "worker pending"}</small>
              <p>{caseRecord.evidence_path}</p>
              <div className="container-metrics">
                <span>{caseRecord.finding_ids?.length ?? 0} findings</span>
                <span>{caseRecord.evidence_ids?.length ?? 0} evidence</span>
                <span>{ready ? "report ready" : "report pending"}</span>
              </div>
            </button>
          );
        })}
        {Object.keys(cases).length === 0 && <div className="empty landing-empty">// no cases loaded - click LOAD DEMOS or create a case from evidence</div>}
      </section>
    </div>
  );
}

function ReportPanel({
  report,
  evidence,
  llmBrief,
  llmNarrative,
  llmGenerating,
  selfCorrections,
}: {
  report: InvestigationReport | null;
  evidence: EvidenceRecord[];
  llmBrief: LlmBrief | null;
  llmNarrative: string;
  llmGenerating: boolean;
  selfCorrections: Array<Record<string, unknown>>;
}) {
  return (
    <div className="panel page-panel">
      <div className="panel-label">Investigation Report</div>
      {selfCorrections.length > 0 && (
        <div className="brief-box correction-box">
          <div className="finding-title">Agent Self-Correction Loop</div>
          {selfCorrections.map((correction, index) => (
            <div key={`${String(correction.stage)}-${index}`} className="correction-line">
              <span className="sev sev-high">FIXED</span>
              <div>
                <strong>{String(correction.stage)}</strong>
                <p>{String(correction.reason || "validation mismatch detected")}</p>
                <code>{String(correction.action)}</code>
              </div>
            </div>
          ))}
        </div>
      )}
      {llmBrief && (
        <div className="brief-box">
          <div className="finding-title">LLM Grounding Brief</div>
          <div className="finding-ev mono">~{llmBrief.token_efficiency.estimated_prompt_tokens} prompt tokens | raw artifacts sent: no | full JSON sent: no</div>
          <pre>{llmBrief.brief}</pre>
        </div>
      )}
      {llmGenerating && (
        <div className="brief-box llm-generating">
          <div className="finding-title">Llama Generating Narrative<span className="dots" /></div>
          <pre>Composing from validated findings, evidence IDs, trace IDs, and artifact paths only.</pre>
        </div>
      )}
      {llmNarrative && <div className="brief-box"><div className="finding-title">LLM Narrative</div><pre>{llmNarrative}</pre></div>}
      <FindingsPanel findings={normalizeFindings(report)} />
      <div className="panel-label" style={{ marginTop: 18 }}>Evidence Records</div>
      {evidence.map((entry) => (
        <div key={entry.evidence_id} className="finding">
          <span className="sev sev-low">{entry.tool}</span>
          <div>
            <div className="finding-title">{entry.evidence_id}</div>
            <div className="finding-ev mono">{entry.artifact_path}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #08090B; color: #F2F2F2; font-family: 'Rajdhani', sans-serif; min-height: 100vh; font-size: 16px; }
  button, input { font: inherit; }
  button { cursor: pointer; }
  .mono { font-family: 'Share Tech Mono', monospace; }
  .topnav { height: 58px; background: #050607; border-bottom: 1px solid #22262C; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; }
  .logo { font-family: 'Share Tech Mono', monospace; font-size: 19px; color: #FF365F; letter-spacing: 3px; text-transform: uppercase; }
  .logo-slash { color: #FFB13B; }
  .nav-links { display: flex; gap: 6px; }
  .nav-link { background: none; border: none; color: #9A8A8E; font-size: 14px; font-weight: 700; letter-spacing: 1.5px; padding: 6px 14px; text-transform: uppercase; }
  .nav-link:hover, .nav-link.active { color: #FFFFFF; border-bottom: 1px solid #FF365F; }
  .clock { color: #AFA3A6; font-size: 12px; }
  .hero { position: relative; min-height: 250px; padding: 38px 34px; background: linear-gradient(135deg, #0E1116 0%, #090A0D 58%, #121012 100%); border-bottom: 1px solid #22262C; display: flex; align-items: center; justify-content: space-between; gap: 26px; }
  .hero-eyebrow { font-family: 'Share Tech Mono', monospace; font-size: 12px; color: #FF365F; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 16px; }
  .hero-title { font-size: 52px; font-weight: 700; line-height: 1.05; color: #F0F0F0; text-transform: uppercase; letter-spacing: 2px; }
  .hero-title .red { color: #FF365F; }
  .hero-subtitle { margin-top: 16px; max-width: 680px; color: #B8AAAE; font-size: 17px; line-height: 1.55; }
  .hero-metrics { display: flex; gap: 24px; }
  .metric { min-width: 88px; text-align: right; }
  .metric-val { display: block; font-family: 'Share Tech Mono', monospace; font-size: 36px; color: #DDD; }
  .metric-val.red { color: #FF365F; }
  .metric-val.amber { color: #E8A020; }
  .metric-label { font-size: 12px; color: #AFA3A6; text-transform: uppercase; letter-spacing: 2px; }
  .hero-corner { position: absolute; top: 24px; right: 28px; color: #AFA3A6; font-size: 11px; letter-spacing: 2px; }
  .evidence-dock { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 16px; padding: 16px 20px; background: #0B0D10; border-bottom: 1px solid #22262C; }
  .evidence-list { display: flex; flex-wrap: wrap; gap: 8px; }
  .evidence-chip, .case-row { background: #101318; border: 1px solid #2A3038; color: #D7DCE2; padding: 9px 11px; text-align: left; display: grid; gap: 4px; }
  .evidence-chip.active, .case-row.active { border-color: #FF365F; color: #FFF; background: #171A20; }
  .evidence-chip small { color: #AFA3A6; overflow-wrap: anywhere; }
  .case-create { display: flex; gap: 8px; align-items: end; }
  .chat-input { background: #11151B; border: 1px solid #303742; color: #F1E8EA; padding: 0 12px; outline: none; min-width: 180px; height: 42px; }
  .chat-input:hover, .chat-input:focus { border-color: #FF365F; background: #151A21; }
  .upload-btn { background: #11151B; border: 1px solid #303742; color: #D7DCE2; padding: 0 14px; height: 42px; display: inline-flex; align-items: center; justify-content: center; font-family: 'Share Tech Mono', monospace; font-size: 12px; letter-spacing: 1.5px; cursor: pointer; white-space: nowrap; }
  .upload-btn:hover { border-color: #FF365F; color: #FF365F; background: #171A20; }
  .upload-btn input { display: none; }
  .upload-status { min-width: 220px; max-width: 320px; display: grid; gap: 5px; color: #D7DCE2; font-family: 'Share Tech Mono', monospace; font-size: 11px; align-self: center; }
  .upload-status span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .upload-status small { color: #FFB13B; }
  .upload-track { height: 6px; background: #0B0D10; border: 1px solid #303742; overflow: hidden; }
  .upload-track div { height: 100%; background: #FF365F; transition: width .15s linear; }
  .quick-actions { display: flex; gap: 8px; padding: 14px 20px; background: #080808; border-bottom: 1px solid #141414; }
  .btn-outline { background: #11151B; border: 1px solid #303742; color: #D7DCE2; font-family: 'Share Tech Mono', monospace; font-size: 12px; letter-spacing: 1.5px; height: 42px; min-width: 118px; padding: 0 14px; text-transform: uppercase; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; }
  .btn-outline:hover:not(:disabled), .btn-outline.active { border-color: #FF365F; color: #FF365F; background: #171A20; }
  .btn-outline.amber:hover:not(:disabled) { border-color: #E8A020; color: #E8A020; }
  .btn { background: #D92346; color: #FFF; border: 1px solid #FF5272; height: 42px; min-width: 118px; padding: 0 16px; font-family: 'Share Tech Mono', monospace; font-size: 12px; letter-spacing: 2px; text-transform: uppercase; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; }
  .btn:hover:not(:disabled) { background: #FF365F; }
  .btn:disabled, .btn-outline:disabled { opacity: .45; cursor: default; }
  .main-grid { display: grid; grid-template-columns: 250px minmax(0, 1fr) 300px; gap: 1px; background: #141414; border-bottom: 1px solid #141414; min-height: 520px; height: min(680px, calc(100vh - 360px)); }
  .report-status { margin: 0; padding: 12px 20px; background: #101318; border-bottom: 1px solid #22262C; color: #F1E8EA; font-family: 'Share Tech Mono', monospace; font-size: 13px; }
  .report-status.running { color: #FFB13B; }
  .report-status.ready { color: #2ECC40; }
  .report-status.error { color: #FF365F; }
  .report-status button { background: #101A10; border: 1px solid #2ECC40; color: #2ECC40; padding: 8px 12px; font-family: 'Share Tech Mono', monospace; cursor: pointer; }
  .panel { background: #0D0F13; padding: 18px; }
  .page-panel { margin: 20px; }
  .landing { padding: 22px; display: grid; gap: 18px; }
  .landing-header { min-height: 220px; padding: 32px; border: 1px solid #22262C; background: linear-gradient(135deg, #0E1116 0%, #090A0D 68%, #101318 100%); display: flex; justify-content: space-between; gap: 24px; align-items: center; }
  .landing-actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
  .case-container-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 14px; }
  .container-card { min-height: 210px; text-align: left; background: #101318; border: 1px solid #2A3038; color: #D7DCE2; padding: 16px; display: grid; gap: 10px; transition: border-color .12s, background .12s, transform .12s; }
  .container-card:hover { border-color: #FF365F; background: #171A20; transform: translateY(-2px); }
  .container-card.active { border-color: #FF365F; box-shadow: inset 4px 0 0 #FF365F; }
  .container-card-top { display: flex; align-items: center; justify-content: space-between; }
  .container-card strong { font-size: 20px; color: #F1E8EA; }
  .container-card small { color: #AFA3A6; font-family: 'Share Tech Mono', monospace; font-size: 13px; overflow-wrap: anywhere; }
  .container-card p { color: #B8C0CA; line-height: 1.45; overflow-wrap: anywhere; }
  .container-metrics { display: flex; flex-wrap: wrap; gap: 8px; align-self: end; }
  .container-metrics span { border: 1px solid #303742; background: #0D0F13; color: #D7DCE2; padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 12px; }
  .landing-empty { border: 1px dashed #303742; padding: 30px; }
  .panel-label { font-family: 'Share Tech Mono', monospace; font-size: 11px; color: #FF365F; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #2A0B12; }
  .left-panel { min-height: 100%; overflow-y: auto; }
  .center-panel { display: flex; flex-direction: column; min-height: 100%; min-width: 0; }
  .right-panel { overflow-y: auto; max-height: none; min-height: 100%; }
  .boot-line { font-family: 'Share Tech Mono', monospace; font-size: 14px; color: #AEB6C2; line-height: 2.15; display: flex; align-items: center; gap: 8px; }
  .boot-line.done { color: #2ECC40; }
  .boot-line.active { color: #E8A020; }
  .boot-line.error { color: #C41E3A; }
  .boot-icon { width: 20px; text-align: center; }
  .chat-area { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; margin-bottom: 12px; padding-right: 4px; }
  .msg { padding: 9px 13px; font-size: 13px; line-height: 1.6; max-width: 92%; white-space: pre-wrap; }
  .msg.system { background: #11151B; border-left: 2px solid #FF365F; color: #D7DCE2; font-family: 'Share Tech Mono', monospace; font-size: 13px; }
  .msg.user { background: #171A20; border-left: 2px solid #E8A020; color: #F1E8EA; align-self: flex-end; }
  .msg.ai { background: #0F1A10; border-left: 2px solid #2ECC40; color: #D5E8D5; }
  .msg.generating { color: #CFEBD0; border-left-color: #E8A020; background: #11170F; }
  .dots::after { content: ''; display: inline-block; width: 1.4em; text-align: left; animation: dots 1.2s steps(4, end) infinite; }
  @keyframes dots { 0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; } 75%, 100% { content: '...'; } }
  .ev-tag { display: inline-block; margin-top: 7px; font-family: 'Share Tech Mono', monospace; font-size: 10px; color: #2ECC40; background: #0A120A; padding: 2px 8px; border: 1px solid #1A3A1A; }
  .chat-input-row { display: flex; gap: 8px; margin-top: auto; }
  .chat-input { flex: 1; }
  .tl-item { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid #171A20; font-size: 13px; align-items: flex-start; transition: background .12s, padding-left .12s; }
  .tl-item:hover { background: #11151B; padding-left: 4px; }
  .tl-time { font-family: 'Share Tech Mono', monospace; font-size: 12px; color: #E8A020; white-space: nowrap; min-width: 42px; }
  .tl-event { color: #B8AAAE; line-height: 1.5; overflow-wrap: anywhere; }
  .tl-item.active .tl-event { color: #E8A020; }
  .tl-item.error .tl-event { color: #C41E3A; }
  .findings-panel { margin: 0; border-top: 1px solid #141414; }
  .finding { display: flex; align-items: flex-start; gap: 10px; padding: 10px 0; border-bottom: 1px solid #111; cursor: pointer; transition: background .1s; }
  .finding:hover, .finding.selected { background: #151A21; }
  .sev { font-family: 'Share Tech Mono', monospace; font-size: 9px; letter-spacing: 1px; padding: 3px 7px; white-space: nowrap; margin-top: 2px; }
  .sev-critical { background: #1A0508; color: #C41E3A; border: 1px solid #C41E3A44; }
  .sev-high { background: #1A1200; color: #E8A020; border: 1px solid #E8A02044; }
  .sev-medium { background: #00101A; color: #4A9ECC; border: 1px solid #4A9ECC44; }
  .sev-low { background: #0A100A; color: #2ECC40; border: 1px solid #2ECC4044; }
  .finding-title { font-size: 16px; color: #F1E8EA; font-weight: 700; }
  .finding-ev { font-size: 12px; color: #AFA3A6; margin-top: 3px; overflow-wrap: anywhere; }
  .finding-explain { font-size: 13px; color: #C9BBC0; margin-top: 8px; line-height: 1.7; border-left: 1px solid #FF365F55; padding-left: 10px; }
  .brief-box { border: 1px solid #1A1A1A; background: #090909; padding: 14px; margin-bottom: 16px; }
  .correction-box { border-color: #E8A02055; background: #120E07; }
  .correction-line { display: flex; gap: 10px; padding: 10px 0; border-top: 1px solid #2A2010; align-items: flex-start; }
  .correction-line:first-of-type { border-top: none; }
  .correction-line strong { color: #F1E8EA; font-size: 15px; }
  .correction-line p { color: #D1B98A; margin: 4px 0; line-height: 1.45; }
  .correction-line code { color: #FFB13B; font-family: 'Share Tech Mono', monospace; font-size: 12px; overflow-wrap: anywhere; }
  .llm-generating { border-color: #2ECC4055; background: #071007; }
  .brief-box pre { white-space: pre-wrap; color: #D4C8CB; font-family: 'Share Tech Mono', monospace; font-size: 12px; line-height: 1.6; margin-top: 10px; }
  .empty { color: #AFA3A6; font-family: 'Share Tech Mono', monospace; font-size: 12px; padding: 10px 0; }
  .case-rack { background: #0B0D10; border-top: 1px solid #22262C; border-bottom: 1px solid #22262C; padding: 16px 20px; }
  .case-rack-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; }
  .case-worker-card { display: grid; grid-template-columns: auto 1fr; grid-template-areas: "dot title" "dot worker" "dot status"; gap: 2px 10px; align-items: center; text-align: left; background: #101318; border: 1px solid #2A3038; color: #D7DCE2; padding: 12px; transition: border-color .12s, background .12s, transform .12s; }
  .case-worker-card:hover { border-color: #FF365F; background: #171A20; transform: translateY(-1px); }
  .case-worker-card.active { border-color: #FF365F; box-shadow: inset 3px 0 0 #FF365F; }
  .case-worker-card strong { grid-area: title; font-size: 15px; }
  .case-worker-card small { grid-area: worker; color: #AFA3A6; font-family: 'Share Tech Mono', monospace; font-size: 12px; overflow-wrap: anywhere; }
  .case-worker-card em { grid-area: status; color: #E8A020; font-style: normal; font-family: 'Share Tech Mono', monospace; font-size: 12px; }
  .worker-dot { grid-area: dot; width: 12px; height: 12px; border-radius: 999px; background: #3A414C; }
  .worker-dot.ready { background: #2ECC40; box-shadow: 0 0 12px #2ECC4077; }
  @media (max-width: 1000px) { .main-grid, .evidence-dock { grid-template-columns: 1fr; } .case-create, .hero, .hero-metrics { flex-direction: column; align-items: stretch; } }
`;
