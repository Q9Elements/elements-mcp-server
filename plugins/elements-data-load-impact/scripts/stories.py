"""Render the ratified data-load package as an ordered backlog of Markdown stories."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# Resolve shipped sibling modules when invoked with python3 -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .bypass_set import NARRATION_ORIGIN
    from .dli_common import ContractError, metadata_type, owner_coverage_statement, as_bool, bundle_node_names, read_csv, read_json, render_element_ids, validate_owner_steps
except ImportError:
    from bypass_set import NARRATION_ORIGIN
    from dli_common import ContractError, metadata_type, owner_coverage_statement, as_bool, bundle_node_names, read_csv, read_json, render_element_ids, validate_owner_steps


class StoryError(ContractError):
    """The safety package is not ready for deterministic story generation."""


def _criteria(items: list[str]) -> str:
    return "\n".join(f"- [ ] {item}" for item in items)


def _story(template: str, title: str, purpose: str, criteria: list[str], rehearsal_choice: str) -> str:
    evidence_links = ("ratified package and stated rehearsal risks in the final report"
                      if rehearsal_choice == "skip" else "ratified package and rehearsal reconciliation")
    return template.format(title=title, purpose=purpose, acceptance_criteria=_criteria(criteria),
                           evidence_links=evidence_links).rstrip() + "\n"


def _api_label(value: str) -> str:
    if value.startswith("Bulk API"):
        return value.replace("Bulk API", "Bulk Application Programming Interface (API)", 1)
    if value == "SOAP API":
        return "Simple Object Access Protocol Application Programming Interface (SOAP API)"
    return value


def _readable(value) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{_human_label(key)}: {_readable(item)}" for key, item in value.items())
    if isinstance(value, list):
        return "; ".join(_readable(item) for item in value) or "no entries"
    return str(value)


def _human_label(value: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value).replace("_", " ").lower()


def _named_load_order(targets: list[dict], org_context: dict, tool_targets: dict) -> list[str]:
    names = {row["object"] for row in targets}
    written = {row["object"]: set(row.get("writtenFields", []))
               for call in tool_targets.get("calls", [])
               for row in call.get("arguments", {}).get("targets", [])}
    dependencies = {name: set() for name in names}
    for name in names:
        for field in org_context.get("objects", {}).get(name, {}).get("relationshipFields", []):
            if field.get("apiName") in written.get(name, set()):
                dependencies[name].update(set(field.get("targets") or []) & names - {name})
    ordered = []
    remaining = set(names)
    while remaining:
        ready = sorted(name for name in remaining if not dependencies[name] & remaining)
        if not ready:
            ready = [min(remaining)]
        ordered.extend(ready)
        remaining.difference_update(ready)
    criteria = []
    for name in ordered:
        if dependencies[name] and any(dependency in ordered[:ordered.index(name)] for dependency in dependencies[name]):
            criteria.append("Regenerate identifiers for newly created parent rows before loading dependent targets.")
        operation = next((row.get("operation", "load") for row in targets if row["object"] == name), "load")
        criteria.append(f"Load {name} ({operation}) in this order.")
    return list(dict.fromkeys(criteria))


def _parameter_criteria(parameters: dict, rehearsal_choice: str) -> list[str]:
    criteria = []
    if "api" in parameters:
        criteria.append(f"Use {_api_label(parameters['api'])} for the load.")
    if "batchSize" in parameters:
        criteria.append(f"Use a batch size of {parameters['batchSize']}.")
    if "concurrencyMode" in parameters:
        criteria.append(f"Run with {parameters['concurrencyMode']} concurrency.")
    owner_sorts = any(step["story"] == "load" and re.match(r"\s*Sort\s+.+?\s+by\s+\S+", step["step"], re.I)
                      for step in parameters.get("ownerSteps", []))
    if parameters.get("groupByParentId") is True and not owner_sorts:
        field = parameters.get("parentSortField")
        criteria.append(f"Sort child rows by {field} to group parents before loading." if field else
                        "Parent grouping could not be applied because no single parent lookup field was identified; carry the lock risk.")
    if parameters.get("assignmentRulesEnabled") is False:
        criteria.append("Keep assignment rules off during the load.")
    if parameters.get("deduplicateSource") is True:
        criteria.append("De-duplicate the source before loading.")
    for row in parameters.get("uncataloguedLockControls", []):
        criteria.append(f"For {row['triggerCondition']}, follow the ratified API and concurrency.")
    lock_lines = Counter(
            f"Review {row.get('target') or 'the target'}: {row.get('entity') or 'related record'} "
            f"via {row.get('relationshipField') or 'relationship'} "
            f"({row.get('consequence') or 'review'} lock)."
            for row in parameters.get("lockRiskReviewEvidence", []))
    criteria.extend(line if count == 1 else f"{line} ({count} occurrences)"
                    for line, count in lock_lines.items())
    for risk in parameters.get("knownRisks", []):
        if rehearsal_choice == "rehearse" and "sandbox" in risk.lower() and "not yet established" in risk.lower():
            continue
        accepted = parameters.get("knownRisksAcceptedOn")
        criteria.append(f"Carry the owner-accepted risk: {risk.rstrip('. ')}" +
                        (f"; accepted at {accepted}." if accepted else "."))
    for change in parameters.get("parameterChanges", []):
        if change["parameter"] == "knownRisks":
            continue
        criteria.append(
            f"Use the owner-ratified {_human_label(change['parameter'])} change from "
            f"{_readable(change['proposedValue'])} to {_readable(change['ratifiedValue'])} "
            f"by {change['changedBy']} at {change['changedOn']}."
        )
    for row in parameters.get("incidentControls", []):
        if row.get("status") == "not-applicable":
            reason = row.get("notApplicableReason", "").strip()
            criteria.append(f"Treat {_human_label(row['incidentClass'])} as not applicable" +
                            (f": {reason}." if reason else "."))
        elif row.get("status") == "measured-in-rehearsal":
            if rehearsal_choice == "skip":
                criteria.append(f"Carry the stated risk that {_human_label(row['incidentClass'])} was not measured in a sandbox rehearsal.")
            else:
                criteria.append(f"Review the rehearsal result for {_human_label(row['incidentClass'])}, including any not measurable line.")
    return criteria


def render_stories(checklist: list[dict[str, str]], parameters: dict, data_dir: Path, template_path: Path,
                   duplicate_rules: dict | None = None, rehearsal_choice: str = "rehearse",
                   bundles: list[Path] | None = None, manifest_targets: list[dict] | None = None,
                   org_context: dict | None = None, tool_targets: dict | None = None):
    if rehearsal_choice not in {"rehearse", "skip"}:
        raise StoryError("rehearsal choice must be rehearse or skip")
    if parameters.get("packageStatus") != "finalized":
        raise StoryError("execution parameters are not finalized")
    if any(not row.get("owner_ruling", "").strip() for row in checklist):
        raise StoryError("checklist is not ratified")
    if not parameters.get("ratifiedBy") or parameters.get("goNoGo") != "go":
        raise StoryError("execution parameters are not ratified for go")
    validate_owner_steps(parameters.get("ownerSteps", []))
    for row in checklist:
        if (
            row.get("automation_kind") == "validationRule"
            and row.get("owner_ruling") == "deactivate"
            and not row.get("replacement_data_quality_check", "").strip()
        ):
            raise StoryError(
                f"validation rule {row.get('automation_api_name')} needs a replacement data-quality check"
            )
    template = template_path.read_text(encoding="utf-8")
    sequencing = read_csv(data_dir / "load-sequencing.csv")[1]
    re_enable = read_csv(data_dir / "re-enable-sequence.csv")[1]
    rollback = read_csv(data_dir / "rollback-rules.csv")[1]

    setup_criteria = []
    for row in checklist:
        name = row["automation_api_name"]
        disposition = row["owner_ruling"]
        action = {
            "deactivate": f"Deactivate `{name}` for the load and record its prior state.",
            "leave-on": f"Leave `{name}` active and monitor it during the production load.",
        }.get(disposition, f"For `{name}`, no action: runs only when invoked.")
        if disposition == "bypass":
            switch = f"`{row['bypass_switch']}`" if row.get("bypass_switch") else "the ratified switch"
            action = (f"Enable the ratified load-user bypass {switch} for `{name}`."
                      if row.get("bypass_scope") == "user" else
                      f"Turn off {switch} for `{name}`; this affects every user until it is turned back on.")
        if row.get("automation_kind") == "narrationOnly":
            if "non_firing" in row.get("side_effect_flags", ""):
                action = f"Keep `{name}` in its evidenced state; it does not fire for this load."
            elif "activation_unknown" in row.get("side_effect_flags", ""):
                action = f"Verify activation of `{name}` before loading and apply its ratified action: {disposition}."
            action += f" It was {NARRATION_ORIGIN}."
            action += " " + owner_coverage_statement(
                activation_unknown="activation_unknown" in row.get("side_effect_flags", ""),
                non_firing="non_firing" in row.get("side_effect_flags", ""),
                verdict=row.get("bypass_verdict", "unknown"))
        setup_criteria.append(action)
        if row["automation_kind"] == "validationRule" and disposition == "deactivate":
            setup_criteria.append(
                f"Run the replacement data-quality check for `{name}`: {row['replacement_data_quality_check']}"
            )
    setup_criteria.extend(
        check["check"].rstrip(". ") + "." for check in parameters.get("preLoadChecks", [])
    )
    if manifest_targets is None and bundles:
        manifest_targets = [target for bundle in bundles for target in read_json(bundle / "targets.json")]
    load_criteria = _named_load_order(manifest_targets, org_context or {}, tool_targets or {}) if manifest_targets else []
    load_criteria.extend(row["item"] + f" ({row['condition']})." for row in sequencing
                         if not manifest_targets or row["phase"] in {"security", "membership"})
    load_criteria.extend(_parameter_criteria(parameters, rehearsal_choice))
    retention = parameters.get("exportResultsWithinDays", 7)
    evidence_criteria = [
        f"Export success and error comma-separated value (CSV) files within {retention} days.",
        "Reconcile source and target record counts and record every difference.",
    ]
    if rehearsal_choice == "rehearse":
        evidence_criteria.append("Reconcile rehearsal predictions against observed automation names and fire counts.")
    else:
        evidence_criteria.append("Compare production automation observations with the ratified checklist and record differences.")
    applied = {(metadata_type(row.get("automation_type", "")), row["owner_ruling"], row.get("automation_kind", "")) for row in checklist}
    def was_applied(item):
        name = item["item"]
        if name == "Validation rules" or name == "Replacement data-quality checks":
            return any(kind == "validationRule" and ruling == "deactivate" for _, ruling, kind in applied)
        if name == "Apex triggers":
            return any(typ == "Apex Trigger" and ruling == "deactivate" for typ, ruling, _ in applied)
        if name == "Flows":
            return any(typ == "Flow" and ruling == "deactivate" for typ, ruling, _ in applied)
        if name == "Workflow rules":
            return any(typ == "Workflow Rule" and ruling == "deactivate" for typ, ruling, _ in applied)
        if name == "Trigger bypasses":
            return any(ruling == "bypass" for _, ruling, _ in applied)
        return False
    re_enable_criteria = [
        f"Step {row['order']}: {row['item']}. {row['verification']}"
        for row in re_enable if not as_bool(row["optional"]) and was_applied(row)
    ]
    if any(typ == "Process Builder Workflow" and ruling == "deactivate" for typ, ruling, _ in applied):
        re_enable_criteria.append("Restore each deactivated Process Builder Workflow to its recorded prior state and verify its expected actions.")
    if not re_enable_criteria and checklist:
        re_enable_criteria = [
            "Verify the automations match their ratified end state and record the result."
        ]
    target_operations = set(parameters.get("targetOperations", []))
    upsert = "upsert" in target_operations
    rollback_criteria = [row["acceptance"] for row in rollback
                         if (row["rule"] != "Use upsert match field" or upsert)
                         and (not upsert or row["rule"] not in {"Retain inserted identifiers", "Use recoverable delete"})]
    if upsert:
        rollback_criteria.extend([
            "Delete only created rows marked sf__Created true in the success file; retain Recycle Bin recovery.",
            "List updated rows separately and restore their previous values from the pre-load export.",
        ])
    if parameters.get("hardDeleteEnabled") is False:
        rollback_criteria.append("Confirm that the rollback will never use hard delete.")
    criteria_by_story = {
        "pre-load": setup_criteria, "load": load_criteria,
        "export-and-reconcile": evidence_criteria, "re-enable": re_enable_criteria,
        "rollback": rollback_criteria,
    }
    for entry in parameters.get("ownerSteps", []):
        criteria_by_story[entry["story"]].append(f"{entry['step']} (Owner ruling: {entry['ruledOn']}.)")
    if target_operations.intersection({"upsert", "update"}):
        setup_criteria.append(
            "Export the pre-load values of every row and field that rollback may restore before loading; retain the export for rollback."
        )
    if not checklist:
        for criteria in (setup_criteria, re_enable_criteria):
            if not criteria:
                criteria.append(
                    "No automation fires for this load; confirm that again against the org before loading."
                )
    stories = {
        "01-pre-load-setup.md": _story(
            template, "Pre-load setup", "Apply the ratified controls before any production rows are loaded.", setup_criteria, rehearsal_choice
        ),
        "02-sequenced-load.md": _story(
            template, "Sequenced load", "Execute the customer-owned load in dependency order with ratified parameters.", load_criteria, rehearsal_choice
        ),
        "03-export-and-reconcile.md": _story(
            template, "Export evidence and reconcile", "Preserve load evidence and prove source-to-target completeness.", evidence_criteria, rehearsal_choice
        ),
        "04-re-enable-and-verify.md": _story(
            template, "Re-enable and verify", "Restore protections in the published order without accidental replay.", re_enable_criteria, rehearsal_choice
        ),
        "05-rollback-procedure.md": _story(
            template, "Rollback procedure", "Provide a recoverable procedure tied to the exact successful rows.", rollback_criteria, rehearsal_choice
        ),
    }
    named_rules = duplicate_rules or {}
    if any(names for names in named_rules.values()):
        details = "; ".join(f"{obj}: {', '.join(names)}" for obj, names in sorted(named_rules.items()) if names)
        stories["06-review-duplicate-rejections.md"] = _story(
            template, "Review duplicate rejections", "Review rows rejected after the production load.",
            [f"Review production error rows marked `DUPLICATES_DETECTED` against active duplicate rules: {details}.",
             "Resolve each rejected row with the data-load owner and record its disposition."], rehearsal_choice,
        )
    names_by_id = bundle_node_names(bundles or [])
    return {name: render_element_ids(content, names_by_id) for name, content in stories.items()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", required=True, type=Path)
    parser.add_argument("--parameters", required=True, type=Path)
    parser.add_argument("--duplicate-rules", type=Path)
    parser.add_argument("--rehearsal-choice", choices=("rehearse", "skip"), default="rehearse")
    parser.add_argument("--bundle", action="append", type=Path, default=[])
    parser.add_argument("--org-context", type=Path)
    parser.add_argument("--tool-targets", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "skills" / "data-load-impact" / "data")
    parser.add_argument("--template", type=Path, default=Path(__file__).resolve().parent.parent / "skills" / "data-load-impact" / "references" / "story-template.md")
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        _, checklist = read_csv(arguments.checklist)
        stories = render_stories(checklist, read_json(arguments.parameters), arguments.data_dir, arguments.template,
                                 read_json(arguments.duplicate_rules) if arguments.duplicate_rules else None,
                                 arguments.rehearsal_choice, arguments.bundle,
                                 org_context=read_json(arguments.org_context) if arguments.org_context else None,
                                 tool_targets=read_json(arguments.tool_targets) if arguments.tool_targets else None)
        arguments.out_dir.mkdir(parents=True, exist_ok=True)
        for name, content in stories.items():
            (arguments.out_dir / name).write_text(content, encoding="utf-8")
        if "06-review-duplicate-rejections.md" not in stories:
            (arguments.out_dir / "06-review-duplicate-rejections.md").unlink(missing_ok=True)
    except (ContractError, OSError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"wrote {len(stories)} ordered story file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
