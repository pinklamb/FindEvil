from storage.findings_store import next_finding_id, write_finding


IMPORTANT_CATEGORIES = {
    "event_log": ("Windows Event Logs Available", "low", 0.60),
    "amcache": ("Amcache Hive Available", "medium", 0.65),
    "scheduled_task": ("Scheduled Task Artifacts Available", "medium", 0.65),
    "powershell_history": ("PowerShell History Available", "medium", 0.70),
}


def run_artifact_engine(
    artifacts: list[dict],
    evidence_id: str,
    case_id: str,
    trace_id: str | None = None,
) -> list[dict]:
    findings = []
    grouped = {}
    for artifact in artifacts:
        for category in artifact.get("categories", []):
            if category in IMPORTANT_CATEGORIES:
                grouped.setdefault(category, []).append(artifact)

    for category, hits in grouped.items():
        title, severity, confidence = IMPORTANT_CATEGORIES[category]
        artifact_locations = [
            {
                "source_path": hit.get("path"),
                "inode": hit.get("inode"),
                "categories": hit.get("categories", []),
                "ui_link": f"/cases/{case_id}/artifacts/{trace_id}" if trace_id else None,
            }
            for hit in hits[:25]
        ]
        finding = write_finding(
            case_id=case_id,
            finding_id=next_finding_id(case_id),
            title=title,
            severity=severity,
            evidence_refs=[evidence_id],
            trace_refs=[trace_id] if trace_id else [],
            artifact_locations=artifact_locations,
            rule_ids=[f"ARTIFACT-{category.upper()}"],
            confidence=confidence,
        )
        finding["artifact_hits"] = hits[:25]
        findings.append(finding)
    return findings
