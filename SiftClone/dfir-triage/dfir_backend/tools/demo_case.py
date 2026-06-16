from storage.case_store import create_case, delete_case
from storage.evidence_store import next_evidence_id, write_evidence
from storage.findings_store import next_finding_id, write_finding
from storage.trace_store import write_trace


DEMO_SCENARIOS = {
    "persistence": {
        "evidence_path": "/fixtures/suspicious-persistence-demo.json",
        "samples": [
            {
                "tool": "demo_filesystem_scan",
                "worker": "demo_worker",
                "artifact_path": "Windows/Temp/stager.exe",
                "summary": {
                    "path": "Windows/Temp/stager.exe",
                    "inode": "128-1-1",
                    "signal": "Executable discovered in Windows Temp",
                    "severity": "high",
                },
                "finding": {
                    "title": "Executable Found In Temp",
                    "severity": "high",
                    "rule_ids": ["FS-001"],
                    "confidence": 0.88,
                },
            },
            {
                "tool": "demo_eventlog_scan",
                "worker": "demo_worker",
                "artifact_path": "Windows/System32/winevt/Logs/System.evtx",
                "summary": {
                    "event_id": "7045",
                    "service_name": "WinUpdateSvc",
                    "image_path": "C:\\Windows\\Temp\\stager.exe",
                    "signal": "Service installation points to Temp executable",
                    "severity": "critical",
                },
                "finding": {
                    "title": "Suspicious Service Install",
                    "severity": "critical",
                    "rule_ids": ["EVT-7045", "PERSIST-001"],
                    "confidence": 0.92,
                },
            },
            {
                "tool": "demo_powershell_scan",
                "worker": "demo_worker",
                "artifact_path": "Users/Alice/AppData/Roaming/Microsoft/Windows/PowerShell/PSReadLine/ConsoleHost_history.txt",
                "summary": {
                    "command": "powershell -nop -w hidden -enc <redacted>",
                    "signal": "PowerShell history contains encoded hidden execution",
                    "severity": "high",
                },
                "finding": {
                    "title": "Suspicious PowerShell Execution",
                    "severity": "high",
                    "rule_ids": ["PS-ENCODED", "EXEC-001"],
                    "confidence": 0.86,
                },
            },
        ],
    },
    "exfiltration": {
        "evidence_path": "/fixtures/suspicious-exfil-demo.json",
        "samples": [
            {
                "tool": "demo_filesystem_scan",
                "worker": "demo_worker",
                "artifact_path": "Users/Bob/AppData/Local/Temp/customer_export.zip",
                "summary": {
                    "path": "Users/Bob/AppData/Local/Temp/customer_export.zip",
                    "inode": "905-2-1",
                    "signal": "Large archive staged in user temp directory",
                    "severity": "high",
                },
                "finding": {
                    "title": "Sensitive Archive Staged In Temp",
                    "severity": "high",
                    "rule_ids": ["FS-ARCHIVE-STAGING", "EXFIL-001"],
                    "confidence": 0.84,
                },
            },
            {
                "tool": "demo_powershell_scan",
                "worker": "demo_worker",
                "artifact_path": "Users/Bob/AppData/Roaming/Microsoft/Windows/PowerShell/PSReadLine/ConsoleHost_history.txt",
                "summary": {
                    "command": "Compress-Archive C:\\Users\\Bob\\Documents\\Clients customer_export.zip",
                    "signal": "PowerShell history shows document archive creation",
                    "severity": "medium",
                },
                "finding": {
                    "title": "PowerShell Archive Creation",
                    "severity": "medium",
                    "rule_ids": ["PS-COMPRESS-ARCHIVE", "COLLECT-001"],
                    "confidence": 0.78,
                },
            },
            {
                "tool": "demo_network_artifact_scan",
                "worker": "demo_worker",
                "artifact_path": "Users/Bob/AppData/Local/Microsoft/Windows/WebCache/WebCacheV01.dat",
                "summary": {
                    "url": "https://file-share.example/upload",
                    "signal": "Browser history indicates upload site access after archive creation",
                    "severity": "critical",
                },
                "finding": {
                    "title": "Possible Exfiltration Upload Activity",
                    "severity": "critical",
                    "rule_ids": ["BROWSER-UPLOAD", "EXFIL-002"],
                    "confidence": 0.81,
                },
            },
        ],
    },
}


def create_suspicious_demo_case(
    case_id: str = "CASE-SUSPICIOUS-001",
    reset: bool = True,
    scenario: str = "persistence",
) -> dict:
    if reset:
        delete_case(case_id)
    scenario_data = DEMO_SCENARIOS.get(scenario, DEMO_SCENARIOS["persistence"])
    case = create_case(case_id, scenario_data["evidence_path"])
    samples = scenario_data["samples"]

    created = []
    for sample in samples:
        evidence_id = next_evidence_id(case_id)
        trace = write_trace(
            case_id,
            evidence_id=evidence_id,
            tool=sample["tool"],
            worker_container=case.get("worker_container"),
            container_image=case.get("container_image"),
            source_evidence_path=case.get("evidence_path"),
            artifact_path=sample["artifact_path"],
            inode=sample["summary"].get("inode"),
            command_args=["demo-fixture", sample["tool"], sample["artifact_path"]],
            started_at=case["created_at"],
            status="ok",
            summary=sample["summary"],
        )
        evidence = write_evidence(
            case_id=case_id,
            evidence_id=evidence_id,
            trace_id=trace["trace_id"],
            worker=sample["worker"],
            tool=sample["tool"],
            artifact_path=sample["artifact_path"],
            result_summary=sample["summary"],
        )
        finding = write_finding(
            case_id=case_id,
            finding_id=next_finding_id(case_id),
            title=sample["finding"]["title"],
            severity=sample["finding"]["severity"],
            evidence_refs=[evidence_id],
            trace_refs=[trace["trace_id"]],
            artifact_locations=[
                {
                    "source_path": sample["artifact_path"],
                    "inode": sample["summary"].get("inode"),
                    "ui_link": trace["ui_link"],
                }
            ],
            rule_ids=sample["finding"]["rule_ids"],
            confidence=sample["finding"]["confidence"],
        )
        created.append({"evidence": evidence, "trace": trace, "finding": finding})

    return {"case": case, "created": created}


def create_demo_case_bundle(reset: bool = True) -> dict:
    return {
        "cases": [
            create_suspicious_demo_case("CASE-DEMO-PERSISTENCE-001", reset=reset, scenario="persistence"),
            create_suspicious_demo_case("CASE-DEMO-EXFIL-001", reset=reset, scenario="exfiltration"),
        ]
    }
