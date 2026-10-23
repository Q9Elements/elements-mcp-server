"""Resolve active state from automation lifecycle status and synced active facts."""

AUTOMATION_TYPES = {"Flow", "Process Builder Workflow", "Workflow Rule", "Apex Class",
                    "Apex Trigger", "Validation Rule"}


def active_state(row):
    status = str(row.get("automation_status") or row.get("status") or "").casefold()
    if status in {"obsolete", "draft", "inactive", "deleted"}:
        return False
    value = str(row.get("active")).casefold()
    if value in {"false", "0", "inactive"}:
        return False
    if status == "active" or value in {"true", "1"}:
        return True
    return None
