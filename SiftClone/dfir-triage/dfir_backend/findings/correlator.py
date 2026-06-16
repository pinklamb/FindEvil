"""
correlator.py

Detection rules only.

Rules are deterministic.
No LLM.
No storage access.
No file I/O.

Input:
events -> timeline artifacts
files  -> filesystem_worker entries

Output:
list[hit]
"""

SUSPICIOUS_PATHS = [
    "\\Windows\\Temp\\",
    "\\Temp\\",
    "\\AppData\\Roaming\\",
    "\\ProgramData\\",
]

SCRIPT_EXTENSIONS = [
".ps1",
".vbs",
".js",
".bat",
]

EXECUTABLE_EXTENSIONS = [
".exe",
".dll",
]

PERSISTENCE_EVENT_IDS = [
"4698",   # scheduled task
"7045",   # service install
]

LATERAL_BINARIES = [
"NET.EXE",
"PSEXEC.EXE",
"WMIC.EXE",
"POWERSHELL.EXE",
]


def check_executable_in_suspicious_path(files: list) -> list:

    hits = []

    for f in files:
        name = f.get("name", "")
        path = f.get("path", "")

        if not name.lower().endswith(tuple(EXECUTABLE_EXTENSIONS)):
            continue

        for sus_path in SUSPICIOUS_PATHS:
            if sus_path.lower() in path.lower():
                hits.append({
                    "rule_id": "FILE-001",
                    "event_id": f.get("inode", ""),
                    "detail": f"executable_in:{sus_path}",
                    "timestamp": "",
                })
                break

    return hits


def check_deleted_executables(files: list) -> list:
    """
    FILE-002

    ```
    Deleted executable discovered.
    """

    hits = []

    for f in files:
        if not f.get("deleted"):
            continue

        name = f.get("name", "").lower()

        if name.endswith(tuple(EXECUTABLE_EXTENSIONS)):
            hits.append({
                "rule_id": "FILE-002",
                "event_id": f.get("inode", ""),
                "detail": "deleted_executable",
                "timestamp": "",
            })

    return hits
   

def check_script_files(files: list) -> list:

    hits = []

    for f in files:
        name = f.get("name", "").lower()

        if name.endswith(tuple(SCRIPT_EXTENSIONS)):
            hits.append({
                "rule_id": "FILE-003",
                "event_id": f.get("inode", ""),
                "detail": f"script:{name}",
                "timestamp": "",
            })

    return hits
    

def check_persistence_locations(files: list) -> list:

    persistence_paths = [
        "startup",
        "run",
        "runonce",
        "windows\\tasks",
    ]

    hits = []

    for f in files:

        path = f.get("path", "").lower()

        for location in persistence_paths:
            if location in path:
                hits.append({
                    "rule_id": "FILE-004",
                    "event_id": f.get("inode", ""),
                    "detail": f"persistence_location:{location}",
                    "timestamp": "",
                })
                break

    return hits



def check_temp_execution(events: list) -> list:

    hits = []

    for ev in events:

        text = (
            ev.get("filename", "")
            + " "
            + ev.get("message", "")
        )

        for path in SUSPICIOUS_PATHS:
            if path.lower() in text.lower():

                hits.append({
                    "event_id": ev["event_id"],
                    "rule_id": "EXEC-001",
                    "detail": f"temp_execution:{path}",
                    "timestamp": ev.get("timestamp", ""),
                })

                break

    return hits

def check_persistence(events: list) -> list:

    hits = []

    for ev in events:

        eid = str(ev.get("event_identifier", ""))
        msg = ev.get("message", "")

        for target in PERSISTENCE_EVENT_IDS:

            if eid == target or target in msg:

                hits.append({
                    "event_id": ev["event_id"],
                    "rule_id": "PERSIST-001",
                    "detail": f"event_id:{target}",
                    "timestamp": ev.get("timestamp", ""),
                })

                break

    return hits


def check_lateral_movement(events: list) -> list:

    hits = []

    for ev in events:

        message = ev.get("message", "").upper()

        for binary in LATERAL_BINARIES:

            if binary in message:

                hits.append({
                    "event_id": ev["event_id"],
                    "rule_id": "LATERAL-001",
                    "detail": binary,
                    "timestamp": ev.get("timestamp", ""),
                })

    return hits

def check_failed_logons(events: list) -> list:

    hits = []

    for ev in events:

        message = ev.get("message", "")

        if (
            "4625" in message
            or "failed to log on" in message.lower()
        ):
            hits.append({
                "event_id": ev["event_id"],
                "rule_id": "AUTH-001",
                "detail": "failed_logon",
                "timestamp": ev.get("timestamp", ""),
            })

    return hits

