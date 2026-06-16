import re


def _case_token(case_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", case_id).upper() or "CASE"


def next_id(entries: list[dict], field: str, prefix: str, case_id: str) -> str:
    token = _case_token(case_id)
    marker = f"{prefix}-{token}-"
    highest = 0
    for entry in entries:
        value = str(entry.get(field, ""))
        if not value.startswith(marker):
            continue
        try:
            highest = max(highest, int(value.rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return f"{marker}{highest + 1:06d}"
