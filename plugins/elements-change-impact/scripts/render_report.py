"""Render a session report record as a self-contained customer document."""

import html
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from population import population_value
from xml.etree import ElementTree


CAUSE_NAMES = {"automation_write_target_unresolved": "automation write target could not be resolved",
               "depth_bound_reached": "the next-hop depth limit was reached",
               "lookup_change_set_unknown": "related-record changes were not fully known",
               "lookup_delete_constraint_missing": "related-record delete rules were unavailable",
               "relationship_target_unresolved": "a related-record target could not be resolved",
               "rollup_value_change_unknown": "a roll-up value change could not be determined",
               "rollup_configuration_missing": "roll-up configuration was unavailable",
               "budget_exhausted": "the check reached its work limit",
               "hierarchy_lock_rule_undocumented": "a hierarchy lock rule was unavailable"}


def _escape(value):
    value = str(value if value is not None else "")
    value = re.sub(r"\bRunner:\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\(runner\)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\brunner request\b", lambda match: "Request" if match[0][0].isupper() else "request",
                   value, flags=re.IGNORECASE)
    value = re.sub(r"\brunner\b", lambda match: "Requester" if match[0][0].isupper() else "requester",
                   value, flags=re.IGNORECASE)
    for key, phrase in CAUSE_NAMES.items():
        value = value.replace(key, phrase)
    return html.escape(value, quote=True)


# Labels follow the producer of each report field. Nested item labels take
# precedence over their section's label; the runner supplies no label fields.
CLAIM_LABELS = {
    "existing_automation": "ANALYST JUDGEMENT",
    "existing_automation.summary": "TOOL EVIDENCE",
    "existing_automation.written_field": "TOOL EVIDENCE",
    "existing_automation.reason": "ANALYST JUDGEMENT",
    "change_request.model": "TOOL EVIDENCE",
    "change_request.sentence": "ANALYST JUDGEMENT",
    "change_set.elements": "ANALYST JUDGEMENT",
    "option_rounds": "ANALYST JUDGEMENT",
    "option_rounds.options.evidence": "TOOL EVIDENCE",
    "option_rounds.options.ooe_peers": "TOOL EVIDENCE",
    "option_rounds.options.ooe_peers.judgement": "ANALYST JUDGEMENT",
    "material_findings": "ANALYST JUDGEMENT",
    "impacted_components": "TOOL EVIDENCE",
    "impacted_components.judgement": "ANALYST JUDGEMENT",
    "review_before_build": "TOOL EVIDENCE",
    "review_before_build.trigger_field_check": "ANALYST JUDGEMENT",
    "review_before_build.ooe_files": "TOOL EVIDENCE",
    "review_before_build.ooe_files.judgement": "ANALYST JUDGEMENT",
    "drawers.facts": "TOOL EVIDENCE",
    "drawers.model_text": "ANALYST JUDGEMENT",
    "backlog": "ANALYST JUDGEMENT",
    "backlog.counts": "TOOL EVIDENCE",
    "stated_limits": "ANALYST JUDGEMENT",
    "corrections": "ANALYST JUDGEMENT",
    "incomplete": "ANALYST JUDGEMENT",
}
SECTION_FIELDS = {
    "Existing automation": "existing_automation",
    "Findings to resolve before build": "material_findings",
    "Findings": "material_findings",
    "Options considered": "option_rounds",
    "Impacted components and change plan": "impacted_components",
    "Not in the backlog: review before build": "review_before_build",
    "Evidence": "drawers.facts",
    "Backlog": "backlog",
    "Stated limits": "stated_limits",
    "Corrections": "corrections",
}


def _label(field):
    return f"<span class='claim-label'>{CLAIM_LABELS[field]}</span>"


def _claims(body, field):
    return (f"<div data-claim-label='{CLAIM_LABELS[field]}' data-claim-field='{field}'>"
            + _label(field) + body + "</div>") if body else ""


def _list(items, fields=None):
    rows = []
    for index, item in enumerate(items):
        field = fields[index] if isinstance(fields, list) else fields
        label = f" data-claim-label='{CLAIM_LABELS[field]}'" if field else ""
        rows.append(f"<li{label}>" + (_label(field) if field else "") + _escape(item) + "</li>")
    return "<ul>" + "".join(rows) + "</ul>" if rows else ""


def _period(value):
    return str(value).strip().rstrip(".") + "."


def _migration_causes(causes):
    names = {"type": "field type", "data_type": "field type"}
    return ", ".join(dict.fromkeys(names.get(cause, cause.replace("_", " ")) for cause in causes))


def _section(title, body):
    return f"<section><h2>{_escape(title)}</h2>{_claims(body, SECTION_FIELDS[title])}</section>"


def _name(row):
    return row.get("name") or row.get("apiName") or "unnamed element"


def _typed_name(row):
    name = _name(row)
    kind = row.get("sfType") or row.get("type")
    return f"{name} ({kind})" if kind else name


def _existing_path(root, name):
    if not root or not name:
        return None
    base = Path(root).resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        return None
    return path


def _file(root, name):
    path = _existing_path(root, name)
    return json.loads(path.read_text(encoding="utf-8")) if path else None


def _named_values(values):
    if isinstance(values, dict):
        return ", ".join(f"{key}: {value}" for key, value in values.items())
    if isinstance(values, list):
        return ", ".join(str(value) for value in values)
    return str(values)


def _held_field_values(root, element):
    """Read a field's value list from a held definition when the report has no list."""
    if not root or not element.get("nodeId") or not element.get("apiName"):
        return []
    base = Path(root).resolve()
    for path in (base / "work").glob(f"*/definitions/{element['nodeId']}.xml"):
        if not path.resolve().is_relative_to(base):
            continue
        tree = ElementTree.parse(path)
        for field in tree.iter():
            if field.tag.rsplit("}", 1)[-1] != "fields":
                continue
            children = {child.tag.rsplit("}", 1)[-1]: child for child in field}
            if children.get("fullName") is None or children["fullName"].text != element["apiName"]:
                continue
            value_set = children.get("valueSet")
            if value_set is None:
                return []
            return [child.text for definition in value_set if definition.tag.rsplit("}", 1)[-1] == "valueSetDefinition"
                    for value in definition if value.tag.rsplit("}", 1)[-1] == "value"
                    for child in value if child.tag.rsplit("}", 1)[-1] == "fullName" and child.text]
    return []


def _peer_judgements(peers):
    """An explicit analyst note marks the row's shown status as judgement."""
    return [peer.get("analyst_note") is not None for peer in peers]


def _peer_block(peers, field="option_rounds.options.ooe_peers", judgements=None):
    if not peers:
        return ""
    lines = []
    fields = []
    uncertain = []
    uncertain_fields = []
    if judgements is None:
        judgements = _peer_judgements(peers)
    for peer, judgement in zip(peers, judgements):
        name = peer.get("peer") or peer.get("name") or "Unnamed automation"
        status = peer.get("status") or "insufficient evidence"
        if judgement:
            existing = " (pre-existing)" if peer.get("pre_existing") else ""
            lines.append(f"{name}: {status}{existing}")
            fields.append(field + ".judgement")
            if peer.get("reason"):
                lines.append(peer["reason"])
                fields.append(field)
            if peer.get("analyst_note"):
                lines.append(peer["analyst_note"])
                fields.append(field + ".judgement")
            continue
        if status.startswith("insufficient"):
            uncertain.append(name)
            uncertain_fields.append(field + ".judgement" if judgement else field)
        else:
            reason = peer.get("reason")
            existing = " (pre-existing)" if peer.get("pre_existing") else ""
            lines.append(f"{name}: {status}{existing}" + (f"; {reason}" if reason else ""))
            fields.append(field + ".judgement" if judgement else field)
    body = _list(lines, fields)
    if uncertain:
        body += f"<p>{len(uncertain)} peers need more evidence.</p>"
        body += f"<details><summary>Names needing more evidence</summary>{_list(uncertain, uncertain_fields)}</details>"
    return body


def _option_evidence(evidence, option, zero_references=None):
    lines = []
    blast = evidence.get("blast_radius") or []
    existing_rows = [item.get("element") or {} for item in option.get("elements") or []
                     if item.get("action") != "create" and (item.get("element") or {}).get("nodeId")]
    existing = {_name(row) for row in existing_rows}
    seen_blast = set()
    for row in blast if isinstance(blast, list) else [blast]:
        if isinstance(row, str):
            lines.append(_period("Direct references: " + row))
            continue
        if existing and row.get("name") not in existing:
            continue
        seen_blast.add((row.get("name"), row.get("type") or row.get("sfType")))
        name = row.get("name") or "Element"
        if row.get("type") or row.get("sfType"):
            name += f" ({row.get('type') or row.get('sfType')})"
        totals = row.get("totals") or {}
        if totals:
            lines.append(f"{name} has direct references from " + _named_values(totals) + ".")
        elif row.get("summary"):
            if row["summary"].casefold() == "nothing references it":
                key = (row.get("name"), row.get("type") or row.get("sfType"))
                if zero_references is not None and key in zero_references:
                    continue
                if zero_references is not None:
                    zero_references.add(key)
            lines.append(_period(f"{name}: {row['summary']}"))
    for element in existing_rows:
        key = (_name(element), element.get("sfType") or element.get("type"))
        if key not in seen_blast and (key[0], None) not in seen_blast:
            lines.append(f"{_typed_name(element)}: dependent totals not available.")
    migration = evidence.get("migration") or []
    for row in migration if isinstance(migration, list) else [migration]:
        if isinstance(row, str):
            lines.append(_period("Migration: " + row))
            continue
        name = row.get("name") or "This element"
        if row.get("type") or row.get("sfType"):
            name += f" ({row.get('type') or row.get('sfType')})"
        if row.get("needed"):
            causes = _migration_causes(row.get("causes") or [])
            lines.append(f"{name} needs migration" + (f" because of {causes}" if causes else "") + ".")
        else:
            lines.append(f"{name} needs no migration.")
    population = evidence.get("population") or []
    seen_population = set()
    element_types = {_name(item.get("element") or {}): (item.get("element") or {}).get("sfType")
                     for item in option.get("elements") or []}
    for row in population if isinstance(population, list) else [population]:
        if isinstance(row, str):
            lines.append("Population: " + row + ".")
            continue
        if existing and row.get("name") not in existing:
            continue
        seen_population.add((row.get("name"), row.get("type")))
        kind = row.get("type") or element_types.get(row.get("name"))
        if kind and kind != "Field":
            continue
        name = (row.get("name") or "Element") + (f" ({kind})" if kind else "")
        value = population_value(row.get("population") or row, row.get("value"))
        lines.append(f"{name} is populated on {value}% of records."
                     if isinstance(value, (int, float)) else
                     f"{name}: {value}.")
    for element in existing_rows:
        if (element.get("sfType") or element.get("type")) != "Field":
            continue
        key = (_name(element), element.get("sfType") or element.get("type"))
        if key not in seen_population and (key[0], None) not in seen_population:
            lines.append(f"{_typed_name(element)}: population not available.")
    pattern = evidence.get("pattern") or {}
    elements = [item.get("element") or {} for item in option.get("elements") or []]
    allowed = {item.get("sfType") for item in elements} & {"Flow", "Process Builder Workflow", "Apex Trigger", "Field"}
    matches = [row for row in pattern.get("option") or [] if
               (row.get("type") in allowed or (row.get("subtype") and "Field" in allowed))]
    if matches:
        row = matches[0]
        subtype = row.get("subtype") or row.get("type")
        phase = row.get("phase")
        label = subtype + (f" ({phase})" if phase and phase != "phase unknown" else "")
        lines.append(f"Org pattern for {label}: {row.get('count', 0)} of {row.get('total', 0)} comparable elements.")
    return _list(lines)


def _options(report, zero_references=None):
    rounds = report.get("option_rounds") or []
    if not rounds:
        return ""
    blocks = []
    if zero_references is None:
        zero_references = set()
    for index, round_data in enumerate(rounds, 1):
        body = f"<h3>Round {index}</h3>"
        for option in round_data.get("options") or []:
            label = option.get("label") or "Option"
            mode = option.get("mode") or "mode not available"
            body += f"<h4>{_escape(label)} ({_escape(mode)})</h4>"
            recommendation = option.get("recommendation")
            shown_reason = None
            if isinstance(recommendation, str) and recommendation:
                body += f"<p>Recommendation: {_escape(_period(recommendation))}</p>"
                shown_reason = recommendation
                if option.get("recommendation_reason") and option["recommendation_reason"] != recommendation:
                    body += f"<p>Reason: {_escape(_period(option['recommendation_reason']))}</p>"
                    shown_reason = option["recommendation_reason"]
            elif recommendation is True:
                reason = option.get("recommendation_reason")
                body += f"<p>{_escape(_period('Recommendation: ' + reason) if reason else 'Recommended option.')}</p>"
                shown_reason = reason
            elif option.get("recommendation_reason"):
                body += f"<p>Recommendation reason: {_escape(_period(option['recommendation_reason']))}</p>"
                shown_reason = option["recommendation_reason"]
            if option.get("summary"):
                body += f"<p>Analysis: {_escape(option['summary'])}</p>"
            for key, title in (("rationale", "Reason"), ("pros", "Benefits"), ("cons", "Trade-offs")):
                value = option.get(key)
                if key == "rationale" and value in {shown_reason, option.get("summary")}:
                    continue
                if isinstance(value, str) and value:
                    body += f"<p>{title}: {_escape(value)}</p>"
                elif isinstance(value, list) and value:
                    body += f"<p>{title}:</p>{_list(value)}"
            actions = [f"{item.get('action') or 'Action not available'} {_typed_name(item.get('element') or {})}"
                       for item in option.get("elements") or []
                       if item.get("action") == "create" or (item.get("element") or {}).get("nodeId")]
            body += _list(actions)
            peers = option.get("ooe_peers") or []
            judgements = _peer_judgements(peers)
            if option.get("ooe_status"):
                body += _claims(f"<p>Order of execution: {_escape(_period(option['ooe_status']))}</p>",
                                "option_rounds.options.ooe_peers" + (".judgement" if any(judgements) else ""))
            body += _claims(_peer_block(peers, judgements=judgements), "option_rounds.options.ooe_peers")
            if option.get("evidence") is not None:
                body += f"<details><summary>{_escape(label)} evidence</summary>"
                body += _claims(_option_evidence(option["evidence"], option, zero_references),
                                "option_rounds.options.evidence") + "</details>"
        if round_data.get("picked"):
            picked = f"Selected {_escape(round_data['picked'])}"
            picked += f" because {_escape(round_data['why'])}" if round_data.get("why") else ""
            body += f"<p>{_period(picked)}</p>"
        for aside in round_data.get("set_aside") or []:
            if isinstance(aside, str):
                body += f"<p>{_escape(aside)} was set aside.</p>"
            else:
                label = _escape(aside.get("label") or "Option")
                reason = aside.get("reason")
                body += f"<p>{label} was set aside" + (f": {_escape(_period(reason))}" if reason else ".") + "</p>"
        if round_data.get("overturn_reason"):
            body += f"<p>The later choice changed because {_escape(_period(round_data['overturn_reason']))}</p>"
        blocks.append(body)
    return _section("Options considered", "".join(blocks))


def _change_plan(report, root, zero_references=None):
    impacted = report.get("impacted_components") or {}
    members = impacted.get("members") or []
    dispositions = _file(root, impacted.get("dispositions_file"))
    if not members and isinstance(dispositions, dict):
        members = dispositions.get("units") or []
    elif not members and isinstance(dispositions, list):
        members = dispositions
    change_set = report.get("change_set") or {}
    changes = change_set.get("elements") or []
    incomplete = report.get("incomplete")
    body = ""
    if changes:
        body += "<h3>Planned changes</h3>"
        body += _list([f"{(item.get('action') or 'Action not available').capitalize()} {_typed_name(item.get('element') or {})}"
                       for item in changes if item.get("action") == "create" or (item.get("element") or {}).get("nodeId")],
                      "change_set.elements")
    values = change_set.get("existing_values") or {}
    for item in changes:
        element = item.get("element") or {}
        delta = item.get("delta") or {}
        if item.get("action") == "update" and element.get("sfType") == "Field" and any(
                key in delta for key in ("values", "values_added", "values_removed")):
            existing = values.get(_name(element)) or values.get(element.get("apiName")) or _held_field_values(root, element)
            if existing:
                body += f"<p>{_escape(_name(element))}. Existing values: {_escape(_named_values(existing))}.</p>"
    if impacted.get("no_existing_target") or (changes and all(item.get("action") == "create" for item in changes)):
        body += "<p>Not assessed against existing elements: no existing target.</p>"
    judgement_rows = (dispositions.get("judgement") if isinstance(dispositions, dict) else dispositions) or []
    judged_ids = {(row.get("inputNodeId"), row.get("nodeId")) for row in judgement_rows if row.get("nodeId")}
    judged_names = {(_name(row), row.get("sfType")) for row in judgement_rows}
    judged = [row for row in members if (row.get("inputNodeId"), row.get("nodeId")) in judged_ids
              or (_name(row), row.get("sfType")) in judged_names
              or row.get("analyst_note") is not None
              or (not judgement_rows and row.get("reason"))]
    updates = sum(row.get("disposition") == "UPDATE" for row in members)
    judged_updates = sum(row.get("disposition") == "UPDATE" for row in judged)
    deletes = sum(row.get("disposition") == "DELETE" for row in members)
    candidates = sum(row.get("disposition") == "DELETE_CANDIDATE" for row in members)
    no_change = sum(row.get("disposition") == "NOT_IMPACTED" for row in members)
    other = len(members) - updates - no_change - deletes - candidates
    existing_changes = [item for item in changes if item.get("action") not in {"create", "keep"}]
    automation_types = {"Flow", "Apex Trigger", "Process Builder Workflow", "Workflow Rule"}
    def kind(item):
        return (item.get("current_type") or (item.get("element") or {}).get("sfType") or
                (item.get("element") or {}).get("type"))
    outgoing_only = bool(existing_changes) and all(
        item.get("action") == "update" and kind(item) in automation_types for item in existing_changes)
    incoming_read = any(item.get("action") == "delete" or
                        (item.get("action") == "update" and kind(item) and kind(item) not in automation_types)
                        for item in existing_changes)
    mixed = incoming_read and any(item.get("action") == "update" and kind(item) in automation_types
                                  for item in existing_changes)
    read_counts = impacted.get("read_counts") or {}
    directional = mixed or (len(existing_changes) == 1 and
                            (bool(read_counts) or any(row.get("direction") in {"incoming", "outgoing"} for row in members))
                            and not incomplete)
    incoming_ids = {(item.get("element") or {}).get("nodeId") for item in existing_changes
                    if item.get("action") == "delete" or kind(item) not in automation_types}
    outgoing_ids = {(item.get("element") or {}).get("nodeId") for item in existing_changes
                    if item.get("action") == "update" and kind(item) in automation_types}
    incoming_members = [row for row in members if row.get("direction") == "incoming" or
                        (not row.get("direction") and row.get("inputNodeId") in incoming_ids)] if directional else members
    outgoing_members = [row for row in members if row.get("direction") == "outgoing" or
                        (not row.get("direction") and row.get("inputNodeId") in outgoing_ids)] if directional else []
    if directional:
        for item in existing_changes:
            element = item.get("element") or {}
            node_id = element.get("nodeId")
            incoming_count = sum(row.get("inputNodeId") == node_id for row in incoming_members)
            outgoing_count = sum(row.get("inputNodeId") == node_id for row in outgoing_members)
            counts = read_counts.get(node_id) or {}
            incoming_count = counts.get("incoming", incoming_count or None)
            outgoing_count = counts.get("outgoing", outgoing_count or None)
            incoming = (f"{incoming_count} incoming references read" if incoming_count is not None
                        else "incoming references not assessed")
            outgoing = (f"{outgoing_count} outgoing connections read" if outgoing_count is not None
                        else "outgoing connections not assessed")
            body += f"<p>{_escape(_name(element))}: {incoming}; {outgoing}.</p>"
        members_for_summary = incoming_members
        updates = sum(row.get("disposition") == "UPDATE" for row in members_for_summary)
        no_change = sum(row.get("disposition") == "NOT_IMPACTED" for row in members_for_summary)
        judged_updates = sum(row.get("disposition") == "UPDATE" and row in judged for row in members_for_summary)
        deletes = sum(row.get("disposition") == "DELETE" for row in members_for_summary)
        candidates = sum(row.get("disposition") == "DELETE_CANDIDATE" for row in members_for_summary)
        other = len(members_for_summary) - updates - no_change - deletes - candidates
    else:
        members_for_summary = members
    if directional and not mixed:
        has_incoming_read = bool(incoming_members) or any(
            (read_counts.get(node_id) or {}).get("incoming") is not None for node_id in incoming_ids | outgoing_ids)
        if outgoing_only and not has_incoming_read:
            outgoing_total = next(((read_counts.get(node_id) or {}).get("outgoing")
                                   for node_id in outgoing_ids
                                   if (read_counts.get(node_id) or {}).get("outgoing") is not None), None)
            outgoing_total = outgoing_total if outgoing_total is not None else len(outgoing_members or members)
            body += (f"<p>{outgoing_total} outgoing connection{'s' if outgoing_total != 1 else ''} read. "
                     "Incoming references were not read for this change.</p>")
    elif members and outgoing_only:
        body += (f"<p>{len(members)} outgoing connection{'s' if len(members) != 1 else ''} read. "
                 "Incoming references were not read for this change.</p>")
    elif mixed and members_for_summary:
        body += (f"<p>{len(members_for_summary)} dependents read: {updates} need an update, "
                 f"{no_change} {'needs' if no_change == 1 else 'need'} no change, "
                 f"{judged_updates} of the updates judged individually.</p>")
    elif mixed and not incomplete:
        incoming_counts = [counts["incoming"] for counts in read_counts.values() if counts.get("incoming") is not None]
        if incoming_counts:
            body += f"<p>{sum(incoming_counts)} incoming references read.</p>"
    elif members and existing_changes and not incoming_read:
        body += f"<p>{len(members)} connections read. Read direction was not recorded.</p>"
    elif members:
        body += (f"<p>{len(members)} dependents read: {updates} need an update, "
                 f"{no_change} {'needs' if no_change == 1 else 'need'} no change, "
                 f"{judged_updates} of the updates judged individually"
                 + (f", {deletes} will be deleted" if deletes else "")
                 + (f", {candidates} may be deleted" if candidates else "")
                 + (f", {other} need review" if other else "") + ".</p>")
    elif impacted.get("zero_dependents") and not incomplete:
        if outgoing_only:
            body += "<p>0 outgoing connections read. Incoming references were not read for this change.</p>"
        elif incoming_read:
            for item in existing_changes:
                element = item.get("element") or {}
                if kind(item) in automation_types:
                    continue
                key = (_name(element), kind(item))
                if zero_references is not None and key in zero_references:
                    continue
                if zero_references is not None:
                    zero_references.add(key)
                prefix = f"{_escape(_name(element))}: " if len(existing_changes) > 1 else ""
                body += f"<p>{prefix}Nothing references it.</p>"
        elif existing_changes:
            body += "<p>Read direction was not recorded.</p>"
    elif incomplete:
        body += f"<p>Dependent assessment not available ({_escape(incomplete.get('reason') or 'evidence unavailable')}).</p>"
        if impacted.get("counts"):
            body += "<p>Previously recorded figures: " + _escape(_named_values(impacted["counts"])) + ".</p>"
    elif not directional and not impacted.get("no_existing_target") and not (changes and all(item.get("action") == "create" for item in changes)):
        body += "<p>Dependent count not available (read result not recorded).</p>"
    reports = [row for row in members if row.get("sfType") == "Report"]
    recent = sum(row.get("recent") is True for row in reports)
    older_or_undated = [row for row in reports if row.get("recent") is not True]
    old_with_stories = sum(row.get("disposition") != "NOT_IMPACTED" for row in older_or_undated)
    groups = (report.get("backlog") or {}).get("member_groups") or []
    group = next((row for row in groups if row.get("name") == "Older reports"), {})
    file_name = group.get("members_file") or impacted.get("older_reports_file") or "members/older-reports.csv"
    members_path = _existing_path(root, file_name)
    old_without_stories = len(older_or_undated) - old_with_stories
    work_names = Counter(_name(row) for row in older_or_undated if row.get("disposition") != "NOT_IMPACTED")
    listed_names = Counter()
    if members_path:
        with members_path.open(encoding="utf-8", newline="") as handle:
            listed_names = Counter(row.get("api_name") for row in csv.DictReader(handle))
    work_file = bool(listed_names and listed_names == work_names)
    if reports:
        body += (f"<p>{len(reports)} reports read: {recent} recent, "
                 f"{old_without_stories} older or undated without a story, "
                 f"{old_with_stories} older or undated with a story.</p>")
    if older_or_undated:
        if not old_with_stories:
            body += "<p>No older reports need work.</p>"
        elif work_file:
            body += f"<p>{sum(listed_names.values())} older report{'s' if sum(listed_names.values()) != 1 else ''} with work in the members file: <a href='{_escape(file_name)}'>full list</a>.</p>"
        else:
            body += (f"<p>{old_with_stories} older report{'s' if old_with_stories != 1 else ''} "
                     f"{'needs' if old_with_stories == 1 else 'need'} work; the members file is not available.</p>")
    if members:
        labels = {"UPDATE": "needs an update", "DELETE": "will be deleted", "DELETE_CANDIDATE": "may be deleted",
                  "NOT_IMPACTED": "no change needed", "UNKNOWN": "not available", "REVIEW": "needs review"}
        named_groups = {}
        named_members = [row for row in members if row.get("disposition") != "NOT_IMPACTED" and
                         (row.get("sfType") != "Report" or row.get("recent") is True)]
        for row in named_members:
            amended = row.get("analyst_note") is not None
            detail = (None if amended else row.get("report_text")) or labels.get(row.get("disposition"), "not available")
            if row.get("disposition") == "UNKNOWN" and not amended:
                detail = f"not available ({row.get('reason') or 'reason not recorded'})"
            title = ("Outgoing connections" if outgoing_only else
                     "Connections read" if existing_changes and not incoming_read else "Impacted dependents")
            if directional:
                title = ("Outgoing connections" if row in outgoing_members else
                         "Impacted dependents" if row in incoming_members else "Connections read")
            rows, row_fields = named_groups.setdefault(title, ([], []))
            rows.append(f"{_name(row)} ({row.get('sfType') or 'component'}): {detail}")
            row_fields.append("impacted_components.judgement" if row in judged else "impacted_components")
        for title, (rows, row_fields) in named_groups.items():
            body += f"<details><summary>{title} ({len(rows)} {'name' if len(rows) == 1 else 'names'})</summary>{_list(rows, row_fields)}</details>"
        unchanged = [row for row in members if row.get("disposition") == "NOT_IMPACTED" and
                     (row.get("sfType") != "Report" or row.get("recent") is True)]
        if unchanged:
            body += f"<details><summary>No change needed ({len(unchanged)} {'name' if len(unchanged) == 1 else 'names'})</summary>" + _list(
                [f"{_typed_name(row)}: " + ("no change needed" if row.get("analyst_note") is not None
                                           else row.get('report_text') or 'No build work needed') for row in unchanged],
                ["impacted_components.judgement" if row in judged else "impacted_components" for row in unchanged]) + "</details>"
        for row in members:
            if row.get("analyst_note") is None:
                continue
            facts = [row[key] for key in ("report_text", "reason") if row.get(key)]
            body += f"<details><summary>{_escape(_typed_name(row))}: assessment</summary>"
            body += _list(facts + [row["analyst_note"]], ["impacted_components"] * len(facts)
                          + ["impacted_components.judgement"]) + "</details>"
    if impacted.get("delete_order_file"):
        data = _file(root, impacted["delete_order_file"])
        if data is None:
            body += "<p>Delete order not available (file missing).</p>"
        else:
            order = data.get("delete_order") or data.get("order") or []
            names = data.get("names") or {}
            order_names = data.get("order_names") or []
            by_id = {(item.get("element") or {}).get("nodeId"): item.get("element") or {} for item in changes}
            types = {_name(item.get("element") or {}): (item.get("element") or {}).get("sfType") for item in changes}
            lines = []
            for index, entry in enumerate(order):
                if isinstance(entry, dict):
                    name = entry.get("name") or entry.get("label") or (by_id.get(entry.get("nodeId")) or {}).get("name")
                else:
                    name = (names.get(entry) if isinstance(names, dict) else names[index] if index < len(names) else None)
                    name = name or (order_names[index] if index < len(order_names) else None)
                    name = name or (by_id.get(entry) or {}).get("name") or (entry if entry not in by_id else None)
                name = re.sub(r"^\d+\.\s*", "", str(name or "name not available"))
                if re.fullmatch(r"[0-9a-f]{24}", name, flags=re.IGNORECASE):
                    name = "name not available"
                action = entry.get("action") if isinstance(entry, dict) else None
                if action not in {"update", "delete"}:
                    action = next((item.get("action") for item in changes if (item.get("element") or {}).get("nodeId") ==
                                   (entry.get("nodeId") if isinstance(entry, dict) else entry)), "delete")
                lines.append(f"{action.capitalize()} {name}" + (f" ({types[name]})" if types.get(name) else ""))
            if lines:
                body += "<h3>Delete order</h3>" + _list(lines)
    return _section("Impacted components and change plan", body)


def _fire_line(line):
    labels = {"field-matched": "Fires when a touched field matches", "Apex assumed": "Apex automation assumed to fire",
              "fires on every save": "Fires on every save", "validation rule": "Validation rules checked",
              "assignment rule": "Assignment rules checked"}
    if line.startswith("partial:"):
        return _partial(line.split(":", 1)[1].strip())
    if line.startswith("next hop:"):
        return "Next: " + line.split(":", 1)[1].strip() + "."
    for key, title in labels.items():
        if line.startswith(key + ":"):
            return title + ": " + line.split(":", 1)[1].strip() + "."
    return line


def _partial(reason):
    if reason is True:
        return "Coverage is incomplete."
    for key, phrase in CAUSE_NAMES.items():
        reason = reason.replace(key, phrase)
    reason = reason.replace("yes: ", "", 1).strip().rstrip(".")
    return "Coverage is incomplete" + (": " + reason + "." if reason else ".")


def _next_hops(digest_lines, review_hops, labels):
    named = {}
    detailed = {}

    def add(value):
        value = value.strip().rstrip(".")
        if not value or value == "none reported" or value.startswith("automation ") or re.fullmatch(r"\d+ more objects?", value):
            return
        match = re.fullmatch(r"(.+?) \((\d+) paths?\)", value)
        name = match[1] if match else value
        named.setdefault(name, int(match[2]) if match else None)

    for value in review_hops:
        add(str(value))
    for line in digest_lines:
        if not line.startswith("next hop:"):
            continue
        detail = line.split(":", 1)[1].strip()
        match = re.fullmatch(r"(?:automation|\S+) (?:insert|update|delete|changes) (\S+)", detail)
        if match:
            detailed[match[1]] = detailed.get(match[1], 0) + 1
        else:
            for part in detail.split(", "):
                add(part)
    for name, count in detailed.items():
        named.setdefault(name, count)
    if not named:
        return "Next-hop objects: none reported." if any(line.startswith("next hop:") for line in digest_lines) else None
    names = []
    for name, count in named.items():
        label = labels.get(name)
        display = f"{label} ({name})" if label and label != name else name
        names.append(display + (f" ({count} {'path' if count == 1 else 'paths'})" if count else ""))
    return "Next-hop objects: " + ", ".join(names) + "."


def _review(report, root):
    review = report.get("review_before_build") or {}
    lines = []
    judgements = set()
    unavailable = review.get("fire_chain_unavailable")
    if unavailable:
        reason = {"model_not_synced": "the model has not finished syncing"}.get(str(unavailable), str(unavailable))
        lines.append("Save-driven effects are not available because " + _period(reason))
    digest_name = review.get("fire_chain_digest_file")
    digest_lines = []
    digest = None
    if digest_name:
        digest = _file(root, digest_name)
        if digest is None:
            lines.append("Fire-chain evidence not available (file missing).")
        else:
            digest_lines = digest.get("lines") or []
    partial_line = next((line for line in digest_lines if line.startswith("partial:")), None)
    if partial_line:
        lines.append(_partial(partial_line.split(":", 1)[1].strip()))
    elif review.get("partial"):
        lines.append(_partial(review["partial"]))
    check = next((line.split(":", 1)[1].strip() for line in digest_lines
                  if line.startswith("trigger-field check:")), None)
    tool_check = check is not None
    review_checks = review.get("trigger_field_check") or []
    if check is None:
        check = next((str(item) for item in review_checks if "changed fields" in str(item)
                      or "matching trigger fields" in str(item)), None)
    if check:
        line = "Trigger fields: " + check.rstrip(".") + "."
        lines.append(line)
        if not tool_check:
            judgements.add(line)
    comparisons = [str(item) for item in review_checks if str(item) != check]
    lines.extend(comparisons)
    judgements.update(comparisons)
    lines.extend(_fire_line(item) for item in digest_lines if not item.startswith((
        "partial:", "next hop:", "trigger-field check:")))
    next_line = _next_hops(digest_lines, review.get("next_hops") or [],
                           {**(digest.get("object_labels") or {} if digest else {}),
                            **(review.get("object_labels") or {})})
    if next_line:
        lines.append(next_line)
    lines.extend(str(item) for item in review.get("locks") or [])
    lines = list(dict.fromkeys(lines))
    body = _list(lines, ["review_before_build.trigger_field_check" if line in judgements
                         else "review_before_build" for line in lines])
    option_rounds = report.get("option_rounds") or []
    options = [option for round_data in option_rounds for option in round_data.get("options") or []]
    picked = next((round_data.get("picked") for round_data in reversed(option_rounds) if round_data.get("picked")), None)
    for index, name in enumerate(review.get("ooe_files") or []):
        data = _file(root, name)
        stem = Path(name).stem.removeprefix("ooe-")
        tokens = set(re.findall(r"[a-z0-9]+", stem.casefold()))
        matching = [option.get("label") for option in options if option.get("label") and
                    tokens and tokens <= set(re.findall(r"[a-z0-9]+", option["label"].casefold()))]
        label = (matching[0] if len(matching) == 1 else picked if len(review.get("ooe_files") or []) == 1 and picked
                 else options[0].get("label") if len(options) == 1 else
                 options[index].get("label") if index < len(options) else None)
        if not options:
            label = data.get("label") if data else None
        heading = "Order of execution" + (": " + str(label) if label else "")
        body += f"<h3>{_escape(heading)}</h3>"
        body += (_peer_block(data.get("peers") or [], "review_before_build.ooe_files")
                 if data else "<p>Order evidence not available (file missing).</p>")
    if not body:
        body = "<p>Not run: the analysis stopped before this step.</p>" if report.get("incomplete") else "<p>No review findings recorded.</p>"
    return _section("Not in the backlog: review before build", body)


def _drawers(report):
    drawers = ""
    for row in report.get("drawers") or []:
        lines = []
        fields = []
        if row.get("active") is not None:
            lines.append("Active: " + ("yes" if str(row["active"]).lower() in {"true", "1"} else "no"))
            fields.append("drawers.facts")
        for key, value in row.items():
            if key in {"name", "title", "sfType", "type", "id", "nodeId", "active", "elements_url", "source"} or value in (None, "", {}, []):
                continue
            first = len(lines)
            if key == "model_text":
                analysis = " ".join(str(item) for item in value.values()) if isinstance(value, dict) else _named_values(value)
                lines.append("Analysis: " + analysis)
            elif key in {"facts", "findings", "lines"} and isinstance(value, list):
                for item in value:
                    fact = str(item).strip()
                    if fact.startswith("Definition:") or fact.startswith("Source:"):
                        continue
                    fact = re.split(r"\berror(?:ConditionFormula|DisplayField):", fact, maxsplit=1)[0].strip()
                    if fact.startswith("next hop:") and "more objects" in fact:
                        continue
                    if fact.startswith("partial:") and (report.get("review_before_build") or {}).get("partial"):
                        continue
                    if fact:
                        lines.append(_fire_line(fact))
            elif isinstance(value, dict):
                facts = ", ".join(f"{item} {name.replace('_', ' ')}" for name, item in value.items())
                lines.append(key.replace("_", " ").capitalize() + ": " + facts)
            else:
                lines.append(key.replace("_", " ").capitalize() + ": " + _named_values(value))
            field = ("drawers.facts" if key in {"facts", "lines", "population", "counts", "subtype",
                     "apiName", "description", "lastExecuted", "triggerType", "recordTriggerType"}
                     else "drawers.model_text")
            fields.extend([field] * (len(lines) - first))
        title = row.get("name") or row.get("title") or "Element evidence"
        if row.get("sfType") or row.get("type"):
            title += f" ({row.get('sfType') or row.get('type')})"
        drawers += f"<details><summary>{_escape(title)}</summary>{_list(lines, fields)}</details>"
    return _section("Evidence", drawers or ("<p>Not run: the analysis stopped before this step.</p>" if report.get("incomplete") else "<p>No element facts recorded.</p>"))


def _backlog(report, root):
    backlog = report.get("backlog") or {}
    stories = backlog.get("stories") or []
    if backlog.get("drafted") is False or backlog.get("status") == "not drafted":
        reason = backlog.get("reason") or "analysis incomplete"
        reason = re.sub(r"^not drafted:[ \t]*", "", str(reason), flags=re.IGNORECASE)
        body = f"<p>Backlog not drafted: {_escape(reason)}.</p>"
    elif report.get("incomplete") and not stories:
        body = "<p>Not run: the analysis stopped before this step.</p>"
    else:
        body = "<p>Draft only: not saved as Elements stories.</p>"
        if backlog.get("counts"):
            body += _claims("<p>" + _escape(_named_values(backlog["counts"])) + "</p>", "backlog.counts")
        items = []
        for row in stories:
            item = f"{_escape(row.get('sequence') or '')}: {_escape(row.get('summary') or 'story')}"
            if row.get("flag_note"):
                item += f"; flag: {_escape(row['flag_note'])}"
            member_file = row.get("members_file")
            if _existing_path(root, member_file):
                item += f"; <a href='{_escape(member_file)}'>full member list</a>"
            items.append(f"<li>{item}</li>")
        body += "<ul>" + "".join(items) + "</ul>" if items else ""
    return _section("Backlog", body)


def _existing_automation(report):
    existing = report.get("existing_automation") or {}
    answer = existing.get("delete_answer") or {}
    body = ""
    for category in ("fits", "partials", "covered", "partly_covered", "lost"):
        for row in existing.get(category) or []:
            if category in {"fits", "partials"}:
                prefix = "You already have this: " if category == "fits" else "Extend "
                headline = prefix + f"{row['name']} ({row['type']})"
                body += _claims("<p>" + html.escape(headline) + "</p>", "existing_automation")
            elif category in {"covered", "partly_covered"}:
                prefix = "Covered by " if category == "covered" else "Partly covered by "
                write = ""
                if row.get("written_field"):
                    write = (" <span data-claim-label='TOOL EVIDENCE'>" + _label("existing_automation.written_field")
                             + html.escape(f"which writes {row['written_field']}.") + "</span>")
                body += _claims("<p>" + html.escape(prefix + row["name"] + ",") + write + "</p>",
                                "existing_automation")
            if row.get("summary"):
                body += _claims("<p>" + html.escape(row["summary"]) + "</p>", "existing_automation.summary")
            if row.get("written_field") and category in {"fits", "partials", "lost"}:
                body += _claims("<p>" + html.escape(f"It writes {row['written_field']}.") + "</p>",
                                "existing_automation.written_field")
            if category in {"lost", "partly_covered"}:
                loss = row.get("lost_part") or row
                prefix = {"delete_anyway": "Known loss: ", "move": "Moved to the backlog: "}.get(
                    answer.get("choice"), "Lost job: ")
                body += _claims("<p>" + html.escape(prefix + _period(loss["job"])) + "</p>", "existing_automation")
                if loss.get("reason") and loss["reason"] != row.get("reason"):
                    body += _claims("<p>" + html.escape(loss["reason"]) + "</p>", "existing_automation.reason")
            if row.get("reason"):
                body += _claims("<p>" + html.escape(row["reason"]) + "</p>", "existing_automation.reason")
    if body and (existing.get("lost") or existing.get("partly_covered")) and answer.get("verbatim"):
        body += _claims("<p>" + html.escape(answer["verbatim"]) + "</p>", "existing_automation")
    return _section("Existing automation", body) if body else ""


def render_report(report, engagement=None):
    request = report.get("change_request") or {}
    model = request.get("model") or {}
    if isinstance(model, str):
        model = {"name": model}
    changes = (report.get("change_set") or {}).get("elements") or []
    header = "<h1>Change impact report</h1>"
    header += _claims(f"<p><strong>Change:</strong> {_escape(request.get('sentence') or 'Change description not available')}</p>",
                      "change_request.sentence")
    space = request.get("space")
    if isinstance(space, dict):
        space = space.get("name")
    header += f"<p><strong>Space:</strong> {_escape(space or 'not available')}</p>"
    header += f"<p><strong>Org:</strong> {_escape(model.get('name') or 'not available')}</p>"
    if model.get("last_sync"):
        sync = str(model["last_sync"])
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", sync):
                sync = datetime.fromisoformat(sync).strftime("%d %b %Y") + " (UTC time not recorded)"
            else:
                value = sync.removesuffix(" UTC") + ("+00:00" if sync.endswith(" UTC") else "")
                moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
                sync = moment.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
        except ValueError:
            pass
        header += f"<p><strong>Model sync:</strong> {_escape(sync)}</p>"
    if model.get("latest_sync_failed") is True:
        header += "<p>The latest sync failed; this analysis uses the last complete sync.</p>"
    if changes:
        targets = []
        for item in changes:
            element = item.get("element") or {}
            target = _name(element)
            if element.get("apiName") and element["apiName"] != target:
                target += f" ({element['apiName']})"
            if element.get("sfType"):
                target += f", {element['sfType']}"
            targets.append(target)
        header += "<p><strong>Targets:</strong> " + _escape("; ".join(targets)) + "</p>"
    incomplete = report.get("incomplete")
    if incomplete:
        header += _claims(f"<p class='incomplete'>Analysis incomplete: {_escape(incomplete.get('reason') or 'evidence unavailable')}. Say retry when the cause is fixed.</p>", "incomplete")
    findings = report.get("material_findings") or []
    sections = [_existing_automation(report)]
    zero_references = set()
    if findings:
        blocking = [item for item in findings if isinstance(item, dict) and item.get("blocking")]
        informational = [item for item in findings if item not in blocking]
        def finding_text(items):
            return [item.get("text") or item.get("finding") or "Finding not available"
                    if isinstance(item, dict) else item for item in items]
        if report.get("option_rounds") and any(isinstance(item, dict) and item.get("needs_repick")
                                               and not item.get("pre_existing") for item in findings):
            repick = "<p>Review these findings and reconsider the selected approach.</p>"
        else:
            repick = ""
        if blocking:
            sections.append(_section("Findings to resolve before build", _list(finding_text(blocking)) + repick))
        if informational:
            sections.append(_section("Findings", _list(finding_text(informational)) + (repick if not blocking else "")))
    if report.get("option_rounds"):
        sections.append(_options(report, zero_references))
    sections += [_change_plan(report, engagement, zero_references),
                 _review(report, engagement), _drawers(report), _backlog(report, engagement)]
    if report.get("stated_limits"):
        sections.append(_section("Stated limits", _list(report["stated_limits"])))
    if report.get("corrections"):
        sections.append(_section("Corrections", _list([(item.get("text") or item.get("correction") or "")
                                                  if isinstance(item, dict) else str(item).replace("Scope widened by runner:", "The confirmed scope includes:")
                                                  for item in report["corrections"]])))
    return "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Change impact report</title>" \
           "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#17212d}" \
           ".claim-label{display:block;font-size:.7rem;font-weight:700;letter-spacing:.04em;color:#475569;margin:.25rem 0}" \
           "section{border-top:1px solid #ccd;padding:1rem 0}details{margin:.5rem 0}.incomplete{color:#9b1c1c;font-weight:bold}</style>" \
           "</head><body>" + _claims(header, "change_request.model") + "".join(sections) + "</body></html>"


def main(argv=None):
    root = Path((argv or sys.argv[1:])[0])
    source = root / "impact-report.json"
    report = json.loads(source.read_text(encoding="utf-8"))
    (root / "impact-report.html").write_text(render_report(report, root), encoding="utf-8")


if __name__ == "__main__":
    main()
