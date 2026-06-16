"""
filesystem_correlator.py

Deterministic filesystem detection rules.

Input:
    entries from filesystem_worker

Output:
    list of hits

No storage.
No LLM.
No file I/O.
"""

SUSPICIOUS_EXECUTABLES = {
    ".exe",
    ".dll",
    ".ps1",
    ".bat",
    ".js",
    ".vbs",
}

TEMP_PATHS = [
    "\\temp\\",
    "/temp/",
    "\\windows\\temp\\",
]

PERSISTENCE_PATHS = [
    "\\appdata\\roaming\\",
    "\\programdata\\",
    "\\windows\\tasks\\",
]


def check_temp_executables(entries: list) -> list:
    """
    FS-001

    Executable located in Temp.
    """

    hits = []

    for entry in entries:

        if entry.get("type") != "file":
            continue

        path = entry.get("path", "").lower()

        ext = entry.get("extension", "")

        if ext not in SUSPICIOUS_EXECUTABLES:
            continue

        if any(p in path for p in TEMP_PATHS):

            hits.append({
                "rule_id": "FS-001",
                "inode": entry["inode"],
                "path": entry["path"],
                "detail": f"temp_executable:{ext}",
            })

    return hits


def check_deleted_executables(entries: list) -> list:
    """
    FS-002

    Deleted executable.
    """

    hits = []

    for entry in entries:

        if entry.get("type") != "file":
            continue

        if not entry.get("deleted"):
            continue

        if entry.get("extension") not in SUSPICIOUS_EXECUTABLES:
            continue

        hits.append({
            "rule_id": "FS-002",
            "inode": entry["inode"],
            "path": entry["path"],
            "detail": "deleted_executable",
        })

    return hits


def check_persistence_locations(entries: list) -> list:
    """
    FS-003

    Executable in common persistence locations.
    """

    hits = []

    for entry in entries:

        if entry.get("type") != "file":
            continue

        path = entry.get("path", "").lower()

        ext = entry.get("extension", "")

        if ext not in SUSPICIOUS_EXECUTABLES:
            continue

        if any(p in path for p in PERSISTENCE_PATHS):

            hits.append({
                "rule_id": "FS-003",
                "inode": entry["inode"],
                "path": entry["path"],
                "detail": f"persistence_location:{ext}",
            })

    return hits


def check_flagged_entries(entries: list) -> list:
    """
    FS-004

    Uses filesystem_worker flags.
    """

    hits = []

    for entry in entries:

        flags = entry.get("flags", [])

        if not flags:
            continue

        hits.append({
            "rule_id": "FS-004",
            "inode": entry["inode"],
            "path": entry["path"],
            "detail": ",".join(flags),
        })

    return hits