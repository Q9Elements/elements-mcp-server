"""Check card prose and write the draft backlog and uncapped members files."""

import csv
import json
import re
from pathlib import Path


def _customer_text(value):
    value = re.sub(r"\bRunner answer, verbatim:\s*", "Answer, verbatim: ", value, flags=re.IGNORECASE)
    value = re.sub(r"\bRunner request, verbatim:\s*", "Request, verbatim: ", value, flags=re.IGNORECASE)
    value = re.sub(r"\bthe runner chose\b", "the selected approach was", value, flags=re.IGNORECASE)
    return re.sub(r"\brunner\b", "requester", value, flags=re.IGNORECASE)


def finish_backlog(plan, drafts, engagement, *, requirement=None, units=()):
    entries = plan.get("entries") or []
    if not entries:
        raise ValueError("complete backlog has no plan entries")
    by_id = {story.get("id"): story for story in drafts}
    expected = {entry["id"] for entry in entries}
    if set(by_id) != expected or len(drafts) != len(entries):
        raise ValueError("draft stories do not match the story plan")
    stories = []
    for entry in entries:
        draft = dict(by_id[entry["id"]])
        for key in ("summary", "description", "problem_statement", "implementation_details"):
            if isinstance(draft.get(key), str):
                draft[key] = _customer_text(draft[key])
        if not draft.get("problem_statement") and draft.get("description"):
            draft["problem_statement"] = next((line.strip() for line in draft["description"].splitlines()
                                                if line.strip() and not line.startswith("Request, verbatim:")), "")
        draft["acceptance_criteria"] = [_customer_text(item) for item in draft.get("acceptance_criteria") or []]
        if (entry.get("outcome") == "delete" and entry.get("target_active") is False
                and re.search(r"\bdeactivate\b", draft.get("summary", ""), re.IGNORECASE)):
            draft["summary"] = entry["summary"]
        if re.search(r"(?im)^Request, verbatim:", draft.get("description", "")):
            if entry.get("requested"):
                draft["description"] = re.sub(r"(?im)^Request, verbatim:.*$",
                                               lambda _: "Request, verbatim: " + entry["request"],
                                               draft["description"])
            elif entry.get("kind") in {"change", "adopt"}:
                if not requirement:
                    raise ValueError(f"{entry['id']}: change request sentence required for verbatim request")
                draft["description"] = re.sub(r"(?im)^Request, verbatim:.*$",
                                               lambda _: "Request, verbatim: " + requirement,
                                               draft["description"])
            else:
                draft["description"] = re.sub(r"(?im)^Request, verbatim:.*(?:\n|$)", "",
                                               draft["description"])
        criteria = draft.get("acceptance_criteria") or []
        if not 3 <= len(criteria) <= 6:
            raise ValueError(f"{entry['id']}: expected 3 to 6 acceptance criteria")
        if any(fixed not in criteria for fixed in entry.get("fixed_criteria", [])):
            raise ValueError(f"{entry['id']}: fixed criterion missing")
        for key in ("summary", "description", "problem_statement", "implementation_details"):
            if not draft.get(key):
                raise ValueError(f"{entry['id']}: {key} missing")
        if entry.get("requested") and entry["request"] not in "\n".join(
                str(value) for key in ("summary", "description", "problem_statement", "implementation_details", "acceptance_criteria")
                for value in (draft[key] if isinstance(draft.get(key), list) else [draft.get(key, "")])):
            raise ValueError(f"{entry['id']}: requested story is missing the verbatim request")
        stories.append({**draft, "outcome": entry["outcome"], "targets": entry["targets"],
                        "sequence": entry["sequence"], "member_count": entry.get("member_count", 0),
                        "members_file": entry.get("members_file"),
                        "flag_note": entry.get("flag_note") or draft.get("flag_note", ""),
                        **({"requested": True, "request": entry["request"]} if entry.get("requested") else {})})
    change_prose = "\n".join(str(value) for story in stories
                             for key in ("summary", "description", "problem_statement", "implementation_details", "acceptance_criteria")
                             for value in (story.get(key) if isinstance(story.get(key), list) else [story.get(key)]))
    for answer in plan.get("answers", []):
        if answer not in change_prose:
            raise ValueError(f"requirement missing from stories: {answer}")
    covered = {target for entry in entries for target in entry["targets"]}
    covered.update(member.get("nodeId") for entry in entries for member in entry.get("members", []) if member.get("nodeId"))
    for unit in units:
        if unit.get("disposition") == "NOT_IMPACTED":
            continue
        ids = [member.get("nodeId") for member in unit.get("members", [])] if "count" in unit else [unit.get("nodeId")]
        if any(node_id not in covered for node_id in ids):
            raise ValueError(f"work unit has no story: {unit.get('nodeId') or unit.get('sfType')}")
    root = Path(engagement)
    members_dir = root / "members"
    members_dir.mkdir(parents=True, exist_ok=True)
    for group in [*entries, *plan.get("member_groups", [])]:
        if not group.get("members_file"):
            continue
        with (root / group["members_file"]).open("w", encoding="utf-8", newline="") as handle:
            members = group.get("members", [])
            fieldnames = ["api_name", "type"]
            if members and all(member.get("elements_link") for member in members):
                fieldnames.append("elements_link")
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for member in members:
                writer.writerow({key: member.get(key, "") for key in writer.fieldnames})
    member_groups = [{"name": group.get("name", "Older reports"), "member_count": group["member_count"],
                      "members_file": group["members_file"]} for group in plan.get("member_groups", [])]
    output = {"requirement": requirement, "stories": stories, "member_groups": member_groups,
              "status": "draft only: not saved as Elements stories"}
    (root / "backlog.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Draft backlog", "", "Draft only: not saved as Elements stories.", ""]
    for story in stories:
        description = story["description"]
        if next((line.strip() for line in description.splitlines() if line.strip()), "") == story["problem_statement"]:
            description = description.split("\n", 1)[1].lstrip("\n") if "\n" in description else ""
        marker = " [requested]" if story.get("requested") else ""
        lines += [f"## {story['sequence']}: {story['summary']}{marker}", "", description, "",
                  story["problem_statement"], "", "Acceptance criteria:", ""]
        lines += [f"- {criterion}" for criterion in story["acceptance_criteria"]]
        lines += ["", story["implementation_details"], ""]
        if story["members_file"]:
            lines += [f"Members: [{story['member_count']} items]({story['members_file']})", ""]
        if story["flag_note"]:
            lines += [f"Flag: {story['flag_note']}", ""]
    (root / "backlog.md").write_text("\n".join(lines), encoding="utf-8")
    return output


def incomplete_backlog(engagement, reason):
    root = Path(engagement)
    root.mkdir(parents=True, exist_ok=True)
    output = {"drafted": False, "status": "not drafted", "reason": reason, "stories": []}
    (root / "backlog.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_reason = re.sub(r"^not drafted:[ \t]*", "", str(reason), flags=re.IGNORECASE)
    (root / "backlog.md").write_text(f"# Backlog not drafted\n\n{markdown_reason}\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("finish_backlog"))
