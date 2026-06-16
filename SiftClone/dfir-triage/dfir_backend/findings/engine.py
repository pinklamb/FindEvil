from findings.correlator import (
    check_failed_logons,
    check_lateral_movement,
    check_persistence,
    check_temp_execution,
)
from storage.findings_store import next_finding_id, write_finding


RULES = [
    (check_temp_execution, "Execution from Temp Path", "high", 0.85),
    (check_persistence, "Persistence Mechanism Detected", "critical", 0.90),
    (check_lateral_movement, "Lateral Movement Binary Observed", "high", 0.80),
    (check_failed_logons, "Failed Logon Attempts Detected", "medium", 0.75),
]


def run_engine(
    events: list[dict],
    evidence_id: str,
    case_id: str,
    trace_id: str | None = None,
) -> list[dict]:
    findings = []
    for rule_fn, title, severity, confidence in RULES:
        hits = rule_fn(events)
        if not hits:
            continue

        artifact_locations = [
            {
                "source_path": hit.get("event_id"),
                "inode": None,
                "timestamp": hit.get("timestamp"),
                "ui_link": f"/cases/{case_id}/artifacts/{trace_id}" if trace_id else None,
            }
            for hit in hits
        ]

        finding = write_finding(
            case_id=case_id,
            finding_id=next_finding_id(case_id),
            title=title,
            severity=severity,
            evidence_refs=[evidence_id],
            trace_refs=[trace_id] if trace_id else [],
            artifact_locations=artifact_locations,
            rule_ids=sorted({h["rule_id"] for h in hits}),
            confidence=confidence,
        )
        finding["event_hits"] = hits
        findings.append(finding)
    return findings
