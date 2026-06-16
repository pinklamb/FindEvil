from findings.filesystem_correlator import (
    check_deleted_executables,
    check_flagged_entries,
    check_persistence_locations,
    check_temp_executables,
)
from storage.findings_store import next_finding_id, write_finding


RULES = [
    (check_temp_executables, "Executable Found In Temp", "high", 0.85),
    (check_deleted_executables, "Deleted Executable Found", "high", 0.90),
    (check_persistence_locations, "Persistence Artifact Found", "critical", 0.95),
    (check_flagged_entries, "Suspicious File Detected", "medium", 0.70),
]


def run_filesystem_engine(
    entries: list[dict],
    evidence_id: str,
    case_id: str,
    trace_id: str | None = None,
) -> list[dict]:
    findings = []
    for rule_fn, title, severity, confidence in RULES:
        hits = rule_fn(entries)
        if not hits:
            continue

        artifact_locations = [
            {
                "source_path": hit.get("path"),
                "inode": hit.get("inode"),
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
        finding["file_hits"] = hits
        findings.append(finding)
    return findings
