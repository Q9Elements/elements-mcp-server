"""Build the draft safety checklist and execution parameters from ratifiable evidence."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Resolve shipped sibling modules when invoked with python3 -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .dli_common import ContractError, fires_for_operation, read_csv, read_json, validate_owner_steps, write_csv, write_json
except ImportError:
    from dli_common import ContractError, fires_for_operation, read_csv, read_json, validate_owner_steps, write_csv, write_json


CHECKLIST_COLUMNS = [
    "target", "automation_kind", "automation_type", "automation_api_name", "automation_name",
    "bypass_verdict", "bypass_scope", "bypass_switch", "proposed_disposition", "blast_radius", "side_effect_flags",
    "replacement_data_quality_check", "evidence", "owner_ruling",
]
VERDICT_VALUES = {"present", "absent", "unknown"}
AMBIGUOUS_VERDICT_EVIDENCE = "Bypass verdict ambiguous: more than one automation shares this name."
DERIVED_TARGET_FACT_VALUES = {
    "account_owner_write",
    "territory_reparent_or_membership_change",
    "user_role_id_present_or_changed",
    "user_role_reparent",
}
TARGET_FACT_VALUES = {
    "role_based_portal_user",
}
SERIAL_RISK = "Serial mode is required by load or lock evidence but unavailable in the chosen loader; the owner decides go or no-go with this risk."


def _sync_serial_risk(parameters: dict) -> None:
    def is_serial_risk(risk):
        lowered = risk.lower()
        return "serial mode" in lowered and ("unavailable" in lowered or "cannot run" in lowered)
    serial_risks = [risk for risk in parameters.get("knownRisks", []) if is_serial_risk(risk)]
    required = bool(parameters.get("serialModeEvidence") or serial_risks)
    unavailable = required and (parameters.get("loader") not in {"Data Loader", "Bulk API 1.0"}
                                or parameters.get("api") != "Bulk API 1.0")
    parameters["serialModeUnavailable"] = unavailable
    risks = [risk for risk in parameters.get("knownRisks", []) if not is_serial_risk(risk)]
    if unavailable:
        risks.append(serial_risks[0] if serial_risks else SERIAL_RISK)
    parameters["knownRisks"] = risks


def _data_rows(data_dir: Path, name: str) -> list[dict[str, str]]:
    return read_csv(data_dir / name)[1]


def _recommendation_values(data_dir: Path) -> dict[str, int]:
    api = {row["key"]: row["value"] for row in _data_rows(data_dir, "api-thresholds.csv")}
    thresholds = {row["key"]: row["value"] for row in _data_rows(data_dir, "thresholds.csv")}
    try:
        return {
            "bulkPreferred": int(api["bulk_preferred"]),
            "bulkBatch": int(api["bulk_batch_records"]),
            "lockBatch": int(api["step_down"].split("/", 1)[0]),
            "soapBatch": int(api["soap_batch_recommended"].split("-", 1)[-1]),
            "skewThreshold": int(thresholds["skew_threshold"]),
        }
    except (KeyError, ValueError) as error:
        raise ContractError("batch-size or skew data value is invalid") from error


def _applies_to(row: dict[str, str], automation_type: str) -> bool:
    return automation_type in {
        item.strip() for item in row.get("applies_to", "").split(";") if item.strip()
    }


def _disposition(
    kind: str, automation_type: str, verdict: str, email_sender: bool,
    ruling_rows: list[dict[str, str]], disposition_rows: list[dict[str, str]],
) -> str:
    automation_rules = {
        row["condition"]: row["output"] for row in ruling_rows if row["rule"] == "automation-disposition"
    }
    if kind == "assignmentRule":
        return "leave-on"
    by_disposition = {row["disposition"]: row for row in disposition_rows}
    if verdict == "present" and _applies_to(by_disposition["bypass"], automation_type):
        return "bypass"
    review = "review: runs only when invoked (trigger, flow, batch schedule or UI)"
    if automation_type == "Apex Class":
        return review
    if verdict == "unknown" and not email_sender:
        return automation_rules[verdict]
    if review in by_disposition and _applies_to(by_disposition[review], automation_type):
        return review
    if email_sender or (verdict == "absent" and _applies_to(by_disposition["deactivate"], automation_type)):
        return "deactivate"
    return automation_rules[verdict]


def _bypass_verdict(name, verdict_by_name, ambiguous_names, default=None):
    return {"verdict": "unknown", "evidence": AMBIGUOUS_VERDICT_EVIDENCE} if name in ambiguous_names else verdict_by_name.get(name, default if default is not None else {"verdict": "unknown", "evidence": "No bypass verdict supplied."})


def _bypass_radius(scope: str) -> str:
    return "Load user only" if scope == "user" else "Every user while the switch is off"


def _incident_controls(incident_rows, checklist_rows, parameters):
    by_class = {}
    for incident in incident_rows:
        name = incident["incident_class"]
        rows = []
        review_rows = []
        keys = []
        not_applicable = ""
        exposure_controlled = None
        if name == "unexpected_email":
            capable = [
                (index + 1, row) for index, row in enumerate(checklist_rows)
                if "email_fire" in row["side_effect_flags"] or row.get("automation_type") == "Managed Package"
            ]
            rows = [index for index, row in capable
                    if (row.get("owner_ruling") or row["proposed_disposition"]) in {"deactivate", "bypass"}]
            exposure_controlled = len(rows) == len(capable) and parameters.get("fireChainCoverageComplete", True)
        elif name == "lock_contention":
            if parameters.get("lockRiskDetected"):
                keys = [
                    key for key, effective in (
                        ("groupByParentId", parameters.get("groupByParentId") is True),
                        ("concurrencyMode", parameters.get("concurrencyMode") in {"parallel", "serial"}),
                        ("batchSize", isinstance(parameters.get("batchSize"), int) and parameters["batchSize"] > 0),
                    ) if effective
                ]
        elif name == "duplicate_records":
            if parameters.get("deduplicateSource") is True:
                keys = ["deduplicateSource"]
        elif name == "owner_overwritten":
            rows = [
                index + 1 for index, row in enumerate(checklist_rows)
                if "owner_clobbering" in row["side_effect_flags"]
            ]
            if parameters.get("assignmentRulesEnabled") is False:
                keys = ["assignmentRulesEnabled"]
        elif name == "bad_data_while_validation_off":
            validation_rows = [
                (index + 1, row) for index, row in enumerate(checklist_rows)
                if row["automation_kind"] == "validationRule"
            ]
            rows = [
                index for index, row in validation_rows
                if (row.get("owner_ruling") or row["proposed_disposition"]) != "deactivate"
                or row["replacement_data_quality_check"].strip()
            ]
        elif name == "governor_limit_failure":
            keys = ["api", "batchSize"] if parameters.get("api") and parameters.get("batchSize") else []
            capable = [
                (index + 1, row) for index, row in enumerate(checklist_rows)
                if row.get("automation_type") in {"Apex Class", "Apex Trigger", "Flow", "Managed Package", "Workflow Rule"}
                and "non_firing" not in row.get("side_effect_flags", "")
            ]
            rows = [index for index, row in capable
                    if (row.get("owner_ruling") or row["proposed_disposition"]) in {"deactivate", "bypass"}]
            review_rows = [index for index, row in capable
                           if (row.get("owner_ruling") or row["proposed_disposition"]).startswith("review:")]
            exposure_controlled = len(rows) == len(capable) and parameters.get("fireChainCoverageComplete", True)
        elif name == "evidence_lost":
            if parameters.get("exportResultsWithinDays") == 7:
                keys = ["exportResultsWithinDays"]
        elif name == "accidental_re_fire":
            if parameters.get("orderedReEnableRequired") is True:
                keys = ["orderedReEnableRequired"]
        elif name == "unrecoverable_rollback":
            if parameters.get("rollbackBySuccessIds") is True and parameters.get("hardDeleteEnabled") is False:
                keys = ["rollbackBySuccessIds", "hardDeleteEnabled"]
        owner_ruling = next((row for row in parameters.get("incidentClassRulings", [])
                             if row.get("incidentClass") == name and (
                                 row.get("ruling") == "measured-in-rehearsal" or
                                 row.get("ruling") == "not-applicable"
                             )), None)
        if owner_ruling and owner_ruling["ruling"] == "not-applicable":
            not_applicable = owner_ruling.get("reason", "").strip()
            review_rows = []
        if owner_ruling and owner_ruling["ruling"] == "measured-in-rehearsal":
            review_rows = []
        controlled = bool(rows or keys or not_applicable or owner_ruling) and not review_rows
        if exposure_controlled is not None and not owner_ruling:
            controlled = bool(exposure_controlled)
        if name == "owner_overwritten" and not owner_ruling:
            controlled = bool(keys)
        if name == "bad_data_while_validation_off" and not owner_ruling:
            controlled = bool(validation_rows) and len(rows) == len(validation_rows)
        if owner_ruling and owner_ruling["ruling"] == "measured-in-rehearsal":
            controlled = False
        status = (
            "measured-in-rehearsal" if owner_ruling and owner_ruling["ruling"] == "measured-in-rehearsal" else
            "not-applicable" if owner_ruling else "review"
            if review_rows or (
                name == "lock_contention"
                and parameters.get("lockRiskReviewEvidence")
                and not parameters.get("lockRiskDetected")
            )
            else "controlled" if controlled
            else "uncontrolled"
        )
        by_class[name] = {
            "incidentClass": name,
            "control": incident["control"],
            "checklistRows": rows,
            "reviewChecklistRows": review_rows,
            "parameters": keys,
            "notApplicableReason": not_applicable,
            "status": status,
            "controlled": controlled,
        }
    return [by_class[key] for key in sorted(by_class)]


def _recompute_incident_controls(rows: list[dict[str, str]], parameters: dict, data_dir: Path) -> None:
    controls = _incident_controls(_data_rows(data_dir, "incident-classes.csv"), rows, parameters)
    parameters["incidentControls"] = controls
    parameters["uncontrolledIncidentClasses"] = _owner_rulable_incident_classes(controls, rows, parameters)


def _owner_rulable_incident_classes(controls: list[dict], rows=None, parameters=None) -> list[str]:
    # Reconciliation detects unpredicted automation directly; a skip carries its risk.
    email_risk_settled = False
    if rows is not None and parameters is not None:
        capable = [row for row in rows if "email_fire" in row["side_effect_flags"]
                   or row.get("automation_type") == "Managed Package"]
        uncontrolled = [row for row in capable if (row.get("owner_ruling") or row["proposed_disposition"])
                        not in {"deactivate", "bypass"}]
        email_risk_settled = bool(uncontrolled) and all(
            row.get("owner_ruling") == "leave-on"
            and f"{row['automation_api_name']} may send email during the load" in parameters.get("knownRisks", [])
            for row in uncontrolled
        )
    return [row["incidentClass"] for row in controls
            if not row["controlled"] and row["incidentClass"] != "unpredicted_automation"
            and not (row["incidentClass"] == "unexpected_email" and email_risk_settled)]


def _validate_loader_parameters(parameters: dict) -> None:
    loader = parameters.get("loader")
    api = parameters.get("api")
    supported = {
        "Data Loader": {"SOAP API", "Bulk API 1.0", "Bulk API 2.0"},
        "Bulk API 1.0": {"Bulk API 1.0"},
        "Bulk API 2.0": {"Bulk API 2.0"},
        "sf CLI": {"Bulk API 2.0"},
        "Salesforce Inspector Reloaded": {"REST API"},
        "Workbench": {"REST API", "SOAP API", "Bulk API"},
        "dataloader.io": {"Bulk API"},
    }
    if loader not in supported or api not in supported[loader]:
        raise ContractError("API is not supported by the chosen loader")
    if parameters.get("concurrencyMode") not in {"parallel", "serial"}:
        raise ContractError("invalid concurrency mode")
    if parameters["concurrencyMode"] == "serial" and (loader not in {"Data Loader", "Bulk API 1.0"} or api != "Bulk API 1.0"):
        raise ContractError("serial mode requires a loader that supports Bulk API 1.0 serial")
    batch_size = parameters.get("batchSize")
    if api in {"Bulk API 2.0", "Bulk API"}:
        if batch_size != "server-managed":
            raise ContractError("chosen loader has server-managed batch size")
    elif not isinstance(batch_size, int) or batch_size <= 0:
        raise ContractError("chosen loader needs a positive batch size")


def apply_lock_ladder(
    checklist_rows: list[dict[str, str]], parameters: dict, lock_errors: int,
    data_dir: Path, changed_on: str,
) -> tuple[int | None, dict | None]:
    """Apply one automatic rung to a finalized package without changing checklist rulings."""
    if parameters.get("packageStatus") != "finalized":
        raise ContractError("lock ladder requires finalized parameters")
    if lock_errors <= 0:
        raise ContractError("lock ladder requires a positive lock error count")
    if parameters.get("groupByParentId") not in {True, False}:
        raise ContractError("finalized package has invalid groupByParentId")
    if parameters.get("concurrencyMode") not in {"parallel", "serial"}:
        raise ContractError("finalized package has invalid concurrencyMode")
    parent_field_known = bool(parameters.get("parentSortField"))
    if not parameters["groupByParentId"] and parent_field_known:
        rung = 1
        updates = {"groupByParentId": True}
    elif parameters["concurrencyMode"] == "parallel":
        evidence_source = "post-regrouping-rehearsal" if parent_field_known else "rehearsal-without-parent-field"
        if parameters.get("loader") not in {None, "Data Loader", "Bulk API 1.0"}:
            updated = copy.deepcopy(parameters)
            updated["serialModeEvidence"] = list(updated.get("serialModeEvidence", [])) + [
                {"source": evidence_source, "detail": str(lock_errors)}
            ]
            _sync_serial_risk(updated)
            return None, updated
        rung = 2
        updates = {
            "concurrencyMode": "serial",
            "api": "Bulk API 1.0",
            "batchSize": _recommendation_values(data_dir)["lockBatch"],
            "serialModeEvidence": list(parameters.get("serialModeEvidence", [])) + [
                {"source": evidence_source, "detail": str(lock_errors)}
            ],
        }
    else:
        return None, None
    updated = copy.deepcopy(parameters)
    changes = updated.setdefault("parameterChanges", [])
    for key, value in updates.items():
        if updated.get(key) != value:
            changes.append({
                "parameter": key,
                "proposedValue": copy.deepcopy(updated.get(key)),
                "ratifiedValue": copy.deepcopy(value),
                "changedBy": "lock ladder",
                "changedOn": changed_on,
            })
            updated[key] = value
    _recompute_incident_controls(checklist_rows, updated, data_dir)
    _sync_serial_risk(updated)
    return rung, updated


def finalize_package(
    draft_rows: list[dict[str, str]], draft_parameters: dict,
    owner_rows: list[dict[str, str]], owner_parameters: dict, data_dir: Path,
    prior_parameters: dict | None = None,
):
    if prior_parameters is not None and prior_parameters.get("packageStatus") != "finalized":
        raise ContractError("prior parameters must be finalized")
    if len(owner_rows) != len(draft_rows):
        raise ContractError("owner checklist must contain every draft row exactly once")
    owner_rows = [dict(row) for row in owner_rows]
    immutable_columns = [
        column for column in CHECKLIST_COLUMNS
        if column not in {"owner_ruling", "replacement_data_quality_check"}
    ]
    valid_rulings = {
        row["disposition"] for row in _data_rows(data_dir, "dispositions.csv")
    }
    for index, (draft, owner) in enumerate(zip(draft_rows, owner_rows), start=1):
        if any(draft.get(column, "") != owner.get(column, "") for column in immutable_columns):
            raise ContractError(f"owner checklist row {index} changes draft evidence")
        ruling = owner.get("owner_ruling", "").strip()
        if ruling not in valid_rulings:
            raise ContractError(f"owner checklist row {index} has no valid owner ruling")
        if ruling.startswith("review:") and owner.get("automation_type") != "Apex Class":
            raise ContractError(f"owner checklist row {index} can review only an Apex Class")
        if ruling == "deactivate" and owner.get("automation_type") == "Apex Class":
            raise ContractError(f"owner checklist row {index} cannot deactivate an Apex Class")
        if ruling == "deactivate" and owner.get("automation_type") == "Managed Package":
            raise ContractError(f"owner checklist row {index} cannot deactivate a Managed Package")
        if owner.get("automation_type") == "Duplicate Rule" and ruling != "leave-on":
            raise ContractError(f"owner checklist row {index} must leave a Duplicate Rule on")
        if ruling == "bypass" and owner.get("bypass_verdict") != "present":
            raise ContractError(f"owner checklist row {index} cannot use bypass without a present hook")
        if (
            owner.get("automation_kind") == "validationRule"
            and ruling == "deactivate"
            and not owner.get("replacement_data_quality_check", "").strip()
        ):
            raise ContractError(
                f"validation rule {owner.get('automation_api_name')} needs a replacement data-quality check"
            )
        owner["owner_ruling"] = ruling
        if ruling == "bypass":
            owner["blast_radius"] = _bypass_radius(owner.get("bypass_scope", ""))
    package_rulings = {}
    for owner in owner_rows:
        if owner.get("automation_type") != "Managed Package":
            continue
        namespace = owner["automation_api_name"]
        ruling = owner["owner_ruling"]
        if namespace in package_rulings and package_rulings[namespace] != ruling:
            raise ContractError(f"Managed Package {namespace} has conflicting owner rulings")
        package_rulings[namespace] = ruling
    ratified_by = owner_parameters.get("ratifiedBy")
    ratified_on = owner_parameters.get("ratifiedOn")
    if not ratified_by or not ratified_on:
        raise ContractError("owner parameters need ratifiedBy and ratifiedOn")
    go_no_go = owner_parameters.get("goNoGo")
    if go_no_go is not None and go_no_go not in {"go", "no-go"}:
        raise ContractError("owner parameters have invalid goNoGo")
    changed_on = owner_parameters.get("changedOn")
    calculated = {"incidentControls", "uncontrolledIncidentClasses", "parameterChanges", "ownerSteps"}
    finalized = copy.deepcopy(draft_parameters)
    changes = copy.deepcopy(prior_parameters.get("parameterChanges", [])) if prior_parameters else []
    for key in draft_parameters:
        if key in calculated:
            continue
        if key not in owner_parameters:
            raise ContractError(f"owner parameters are missing {key}")
        value = owner_parameters[key]
        previous_value = (
            prior_parameters.get(key) if prior_parameters is not None else draft_parameters[key]
        )
        if value != previous_value:
            if not changed_on:
                raise ContractError("changed parameters need changedOn from the owner's answer")
            changes.append({
                "parameter": key,
                "proposedValue": copy.deepcopy(previous_value),
                "ratifiedValue": copy.deepcopy(value),
                "changedBy": ratified_by,
                "changedOn": owner_parameters.get("knownRisksAcceptedOn", changed_on) if key == "knownRisks" else changed_on,
            })
        finalized[key] = copy.deepcopy(value)
    if finalized.get("loader") != draft_parameters.get("loader"):
        raise ContractError("loader must match the confirmed manifest")
    _validate_loader_parameters(finalized)
    finalized.update({
        "ratifiedBy": ratified_by,
        "ratifiedOn": ratified_on,
        "goNoGo": go_no_go,
        "incidentClassRulings": copy.deepcopy(owner_parameters.get("incidentClassRulings", [])),
        "parameterChanges": changes,
        "packageStatus": "finalized",
        "ownerSteps": copy.deepcopy(owner_parameters.get("ownerSteps", draft_parameters.get("ownerSteps", []))),
    })
    if owner_parameters.get("knownRisksAcceptedOn"):
        finalized["knownRisksAcceptedOn"] = owner_parameters["knownRisksAcceptedOn"]
    validate_owner_steps(finalized["ownerSteps"])
    risks = finalized.get("knownRisks", [])
    for owner in owner_rows:
        if owner["owner_ruling"] == "leave-on" and "email_fire" in owner.get("side_effect_flags", ""):
            risk = f"{owner['automation_api_name']} may send email during the load"
            if risk not in risks:
                risks.append(risk)
    active_email_risks = {f"{row['automation_api_name']} may send email during the load"
                          for row in owner_rows if row["owner_ruling"] == "leave-on"
                          and "email_fire" in row.get("side_effect_flags", "")}
    email_risk_names = {f"{row['automation_api_name']} may send email during the load" for row in owner_rows}
    risks = [risk for risk in risks if risk not in email_risk_names or risk in active_email_risks]
    if "knownRisks" in finalized or risks:
        finalized["knownRisks"] = risks
    if active_email_risks:
        finalized["incidentClassRulings"] = [
            ruling for ruling in finalized["incidentClassRulings"]
            if not (ruling.get("incidentClass") == "unexpected_email"
                    and ruling.get("ruling") == "measured-in-rehearsal")
        ]
    _sync_serial_risk(finalized)
    rule_rows = {(row["target"], row["automation_api_name"]): index for index, row in enumerate(owner_rows, 1)
                 if row["automation_type"] == "Duplicate Rule"}
    for field in ("duplicateRulePredictions", "preLoadChecks"):
        items = copy.deepcopy(owner_parameters.get(field, []))
        if not isinstance(items, list):
            raise ContractError(f"{field} must be an array")
        for item in items:
            if not isinstance(item, dict):
                raise ContractError(f"{field} entries must be objects")
            rule = item.get("rule")
            if rule:
                matches = {key: index for key, index in rule_rows.items()
                           if key[1] == rule and (not item.get("target") or key[0] == item["target"])}
                if len(matches) != 1:
                    raise ContractError(f"{field} names a rule absent from the checklist: {rule}")
                item["checklistRow"] = next(iter(matches.values()))
            elif "checklistRow" in item and len(rule_rows) == 1:
                item["checklistRow"] = next(iter(rule_rows.values()))
        finalized[field] = items
    _recompute_incident_controls(owner_rows, finalized, data_dir)
    duplicate = next(row for row in finalized["incidentControls"] if row["incidentClass"] == "duplicate_records")
    duplicate["checklistRows"] = sorted(set(rule_rows.values()))
    duplicate["parameters"] = ["deduplicateSource"] + [field for field in ("duplicateRulePredictions", "preLoadChecks") if finalized[field]]
    return owner_rows, finalized


def build_package(
    bundle_directories: list[Path], verdicts: list[dict[str, str]], data_dir: Path,
    named_serial_operation: str | None = None,
    target_facts: dict[tuple[str, str], set[str]] | None = None,
    tool_targets: dict | None = None,
    unpredicted_automations: list[dict] | None = None,
    prior_parameters: dict | None = None,
    loader: str = "Data Loader",
    managed_packages: dict | None = None,
    duplicate_rules: dict | None = None, *, confirmed_api: str | None = None,
    ambiguous_names=frozenset(), source_manifest: dict | None = None,
):
    if prior_parameters is not None and prior_parameters.get("packageStatus") != "finalized":
        raise ContractError("prior parameters must be finalized")
    target_facts = target_facts or {}
    source_types = {
        row["nodeId"]: row["type"] for row in (source_manifest or {}).get("files", [])
        if row.get("nodeId") and row.get("type")
    }
    managed_packages = managed_packages or {}
    duplicate_rules = duplicate_rules or {}
    if not isinstance(managed_packages, dict) or not isinstance(duplicate_rules, dict):
        raise ContractError("managed packages and duplicate rules must be grouped by target object")
    if not isinstance(tool_targets, dict) or not isinstance(tool_targets.get("calls"), list):
        raise ContractError("tool targets must contain the projected calls array")
    ambiguous_verdict_names = set()
    verdict_by_name = {}
    for row in verdicts:
        verdict = row.get("verdict", "")
        if verdict not in VERDICT_VALUES:
            raise ContractError(f"bypass verdict for {row.get('apiName', '<unknown>')} must be present, absent, or unknown")
        if str(row.get("nonFiring", "")).strip().lower() == "true" and not row.get("nonFiringEvidence", "").strip():
            raise ContractError(f"non-firing verdict for {row.get('apiName', '<unknown>')} needs evidence")
        if (name := row.get("apiName", "")) in verdict_by_name: ambiguous_verdict_names.add(name)
        verdict_by_name[name] = row
    disposition_rows = _data_rows(data_dir, "dispositions.csv")
    blast_radius = {row["disposition"]: row["blast_radius"] for row in disposition_rows}
    ruling_rows = _data_rows(data_dir, "ruling-rules.csv")
    checklist_rows = []
    maximum_volume = 0
    lock_risk = False
    parent_sort_columns = set()
    lock_review_evidence = []
    target_operations = set()
    derived_target_facts = {}
    for call in tool_targets["calls"]:
        arguments = call.get("arguments", {})
        for target in arguments.get("targets", []):
            key = (target.get("object"), target.get("operation"))
            written_fields = set(target.get("writtenFields", []))
            if key[0] == "Account" and "OwnerId" in written_fields:
                derived_target_facts.setdefault(key, set()).add("account_owner_write")
            if key[0] == "User" and "UserRoleId" in written_fields:
                derived_target_facts.setdefault(key, set()).add("user_role_id_present_or_changed")
            if key[0] == "UserRole" and "ParentRoleId" in written_fields:
                derived_target_facts.setdefault(key, set()).add("user_role_reparent")
            if (
                (key[0] == "Territory" and "ParentTerritoryId" in written_fields)
                or (
                    key[0] == "UserTerritory"
                    and bool({"UserId", "TerritoryId"} & written_fields)
                )
            ):
                derived_target_facts.setdefault(key, set()).add(
                    "territory_reparent_or_membership_change"
                )
    receipt_codes = set()
    receipt_rule_ids = set()
    fire_chain_complete = True
    seen_automations = set()
    managed_by_package = {}
    for target_name, packages in managed_packages.items():
        if not isinstance(packages, list):
            raise ContractError(f"invalid managed package lookup for {target_name}")
        for package in packages:
            if not isinstance(package, dict):
                raise ContractError(f"invalid managed package lookup for {target_name}")
            namespace = package.get("namespace", "")
            triggers = package.get("triggers", [])
            if not namespace or not isinstance(triggers, list) or not all(isinstance(name, str) and name for name in triggers):
                raise ContractError(f"invalid managed package lookup for {target_name}")
            managed_by_package.setdefault((target_name, namespace), set()).update(triggers)
    for bundle in bundle_directories:
        response = read_json(bundle / "response.json")
        bundle_operations = {target["object"]: target["operation"] for target in response.get("targets", [])}
        manifest_targets = read_json(bundle / "targets.json")
        _, automations = read_csv(bundle / "automations.csv")
        _, digest = read_csv(bundle / "fire-chain-digest.csv")
        _, lock_rows = read_csv(bundle / "lock-rows.csv")
        written_by_target = {
            target["object"]: set(target.get("writtenFields", []))
            for call in tool_targets["calls"] for target in call.get("arguments", {}).get("targets", [])
        }
        parent_sort_columns.update(
            row["column"] for row in lock_rows
            if row.get("consequence") == "locked" and row.get("column")
            and row["column"] in written_by_target.get(row.get("target"), set())
        )
        _, receipts = read_csv(bundle / "receipts.csv")
        for receipt in receipts:
            if receipt.get("code") != "automation_managed_excluded":
                continue
            try:
                detail = json.loads(receipt.get("detail") or "{}")
            except ValueError:
                continue
            qualified = detail.get("apiName") or detail.get("name") or ""
            namespace = detail.get("namespace") or (qualified.split(".", 1)[0] if "." in qualified else "")
            if namespace:
                managed_by_package.setdefault((receipt.get("target", ""), namespace), set()).add(detail.get("name") or qualified)
        receipt_codes.update(row.get("code") for row in receipts)
        receipt_rule_ids.update(row.get("ruleId") for row in receipts if row.get("ruleId"))
        email_by_node = {
            sender["nodeId"]: sender
            for target in response.get("targets", [])
            for sender in target.get("loadRisk", {}).get("emailSenders", [])
        }
        email_by_name = {sender["apiName"]: sender for sender in email_by_node.values()}
        automation_types_by_node = {row.get("nodeId"): row.get("type") for row in automations if row.get("nodeId")}
        automation_types_by_name = {row.get("apiName"): row.get("type") for row in automations if row.get("apiName")}
        node_types = {
            node["nodeId"]: node["sfType"]
            for target in response.get("targets", [])
            for chain in target.get("fireChain", [])
            for entity in chain.get("digest", [])
            for variant in entity.get("variants", [])
            if (node := variant.get("firingAutomation")) and node.get("nodeId") and node.get("sfType")
        }
        passing_validation = {
            (target["object"], row["apiName"])
            for target in response.get("targets", [])
            for row in target.get("validationRules", {}).get("matched", [])
            if row.get("loadDataPasses") is True
        }
        lock_nodes = {
            row["firingAutomationNodeId"] for row in digest
            if row.get("lockConsequence") in {"locked", "conditional"} and row.get("firingAutomationNodeId")
        }
        fire_chain_complete = fire_chain_complete and response.get("coverage", {}).get("absenceIsEvidence") is True
        lock_risk = lock_risk or any(
            row.get("lockConsequence") == "locked" for row in digest
        ) or any(
            row.get("consequence") == "locked" for row in lock_rows
        ) or any(
            item.get("skew") == "skewed"
            for target in response.get("targets", [])
            for item in target.get("loadRisk", {}).get("fanIn", [])
        )
        lock_review_evidence.extend(
            {
                "source": "fire-chain-digest",
                "target": row.get("target", ""),
                "entity": row.get("entityApiName", ""),
                "relationshipField": row.get("relationshipField", ""),
                "consequence": row.get("lockConsequence", ""),
                "ruleIds": row.get("ruleIds", "").split(),
            }
            for row in digest
            if row.get("lockConsequence") in {"conditional", "unknown"}
        )
        lock_review_evidence.extend(
            {
                "source": "lock-rows",
                "target": row.get("target", ""),
                "entity": " ".join(row.get("parentObjects", "").split()),
                "relationshipField": row.get("column", ""),
                "consequence": row.get("consequence", ""),
                "ruleIds": [row["ruleId"]] if row.get("ruleId") else [],
            }
            for row in lock_rows
            if row.get("consequence") in {"conditional", "unknown"}
        )
        maximum_volume = max(maximum_volume, *(target.get("estimatedVolume", 0) for target in response.get("targets", [])))
        for target in manifest_targets:
            key = (target.get("object"), target.get("operation"))
            target_operations.add(key)
        candidates = list(automations)
        candidates.extend(
            {
                "target": row.get("target", ""),
                "kind": "fireChainAutomation",
                "type": (node_types.get(row.get("firingAutomationNodeId"))
                         or source_types.get(row.get("firingAutomationNodeId"))
                         or automation_types_by_node.get(row.get("firingAutomationNodeId"))
                         or automation_types_by_name.get(row.get("firingAutomation"))
                         or email_by_node.get(row.get("firingAutomationNodeId"), {}).get("sfType", "Automation")),
                "apiName": row.get("firingAutomation", ""),
                "name": email_by_node.get(row.get("firingAutomationNodeId"), {}).get("name")
                or row.get("firingAutomation", ""),
                "nodeId": row.get("firingAutomationNodeId", ""),
            }
            for row in digest
            if row.get("firingAutomation")
        )
        candidates.extend(
            {
                "target": target.get("object", ""),
                "kind": "fireChainAutomation",
                "type": sender.get("sfType", "Automation"),
                "apiName": sender.get("apiName", ""),
                "name": sender.get("name") or sender.get("apiName", ""),
                "nodeId": sender.get("nodeId", ""),
            }
            for target in response.get("targets", [])
            for sender in target.get("loadRisk", {}).get("emailSenders", [])
        )
        for automation in candidates:
            name = automation["apiName"]
            identity = automation.get("nodeId") or (automation.get("target"), name)
            if identity in seen_automations:
                continue
            seen_automations.add(identity)
            verdict_row = _bypass_verdict(name, verdict_by_name, ambiguous_names)
            target_operation = bundle_operations.get(automation["target"], "")
            explicit_non_firing = str(verdict_row.get("nonFiring", "")).strip().lower()
            non_firing = bool(target_operation and not fires_for_operation(automation, target_operation)
                              and explicit_non_firing != "false")
            non_firing = non_firing or (
                automation["kind"] == "directAutomation"
                and str(verdict_row.get("nonFiring", "")).strip().lower() == "true"
            )
            email_sender = not non_firing and (automation.get("nodeId") in email_by_node or name in email_by_name)
            disposition = _disposition(
                automation["kind"], automation["type"], verdict_row["verdict"],
                email_sender, ruling_rows, disposition_rows,
            )
            if non_firing or (automation["target"], name) in passing_validation:
                disposition = "leave-on"
            flags = []
            if non_firing:
                flags.append("non_firing")
            if email_sender:
                flags.append("email_fire")
            if automation.get("nodeId") in lock_nodes:
                flags.append("lock_contribution")
            if automation["kind"] == "assignmentRule":
                flags.append("owner_clobbering")
            checklist_rows.append({
                "target": automation["target"],
                "automation_kind": automation["kind"],
                "automation_type": automation["type"],
                "automation_api_name": name,
                "automation_name": automation["name"],
                "bypass_verdict": verdict_row["verdict"],
                "proposed_disposition": disposition,
                "blast_radius": blast_radius[disposition],
                "side_effect_flags": ";".join(flags),
                "replacement_data_quality_check": "",
                "evidence": "; ".join(part for part in (
                    verdict_row.get("evidence", ""), verdict_row.get("nonFiringEvidence", "")
                ) if part),
                "owner_ruling": "",
            })
    for (target_name, namespace), names in managed_by_package.items():
        if target_name not in {name for name, _ in target_operations}:
            raise ContractError(f"managed package lookup has unknown target {target_name}")
        verdict = _bypass_verdict(namespace, verdict_by_name, ambiguous_names, {})
        checklist_rows.append({
            "target": target_name, "automation_kind": "managedPackage", "automation_type": "Managed Package",
            "automation_api_name": namespace, "automation_name": namespace,
            "bypass_verdict": verdict.get("verdict", "unknown"), "proposed_disposition": "leave-on",
            "blast_radius": blast_radius["leave-on"], "side_effect_flags": "",
            "replacement_data_quality_check": "",
            "evidence": "Managed trigger receipts and lookup: " + ", ".join(sorted(names)) +
            ("; bypass: " + verdict["evidence"] if verdict.get("evidence") else ""),
            "owner_ruling": "",
        })
    for target_name, names in duplicate_rules.items():
        if target_name not in {name for name, _ in target_operations} or not isinstance(names, list):
            raise ContractError(f"invalid duplicate rules for {target_name}")
        for name in sorted(set(names)):
            if not isinstance(name, str) or not name:
                raise ContractError(f"invalid duplicate rule for {target_name}")
            verdict = _bypass_verdict(name, verdict_by_name, ambiguous_names, {})
            checklist_rows.append({
                "target": target_name, "automation_kind": "duplicateRule", "automation_type": "Duplicate Rule",
                "automation_api_name": name, "automation_name": name,
                "bypass_verdict": verdict.get("verdict", "not applicable"), "proposed_disposition": "leave-on",
                "blast_radius": blast_radius["leave-on"], "side_effect_flags": "",
                "replacement_data_quality_check": "", "evidence": "Active duplicate rule on target." +
                (" " + verdict["evidence"] if verdict.get("evidence") else ""),
                "owner_ruling": "",
            })
    for observed in unpredicted_automations or []:
        name = str(observed.get("name", "")).strip()
        if not name:
            raise ContractError("unpredicted rehearsal automation is missing a name")
        automation_type = observed.get("type") or "Automation"
        if any(row["automation_api_name"] == name and row["automation_type"] == automation_type
               for row in checklist_rows):
            continue
        verdict_row = _bypass_verdict(name, verdict_by_name, ambiguous_names, {"verdict": "unknown", "evidence": ""})
        disposition = "leave-on" if automation_type in {"Managed Package", "Duplicate Rule"} else _disposition(
            "rehearsalObservation", automation_type, verdict_row["verdict"], False,
            ruling_rows, disposition_rows,
        )
        checklist_rows.append({
            "target": "rehearsal",
            "automation_kind": "rehearsalObservation",
            "automation_type": automation_type,
            "automation_api_name": name,
            "automation_name": name,
            "bypass_verdict": verdict_row["verdict"],
            "proposed_disposition": disposition,
            "blast_radius": blast_radius[disposition],
            "side_effect_flags": "unpredicted_automation",
            "replacement_data_quality_check": "",
            "evidence": "Observed in rehearsal, not in the fire chain." +
            (" Bypass: " + verdict_row["evidence"] if verdict_row.get("evidence") else ""),
            "owner_ruling": "",
        })
    for row in checklist_rows:
        verdict = _bypass_verdict(row["automation_api_name"], verdict_by_name, ambiguous_names)
        present = verdict["verdict"] == "present"
        row["bypass_scope"] = ("user" if verdict.get("scope") == "user" else "org-wide") if present else ""
        row["bypass_switch"] = verdict.get("switch", "") if present else ""
        if row["proposed_disposition"] == "bypass":
            row["blast_radius"] = _bypass_radius(row["bypass_scope"])
    checklist_rows.sort(key=lambda row: (row["target"], row["automation_kind"], row["automation_api_name"]))
    uncatalogued_by_row = {row["cheat_sheet_row"]: row for row in _data_rows(data_dir, "uncatalogued-lock-rows.csv")}
    matched_uncatalogued = set()
    has_fact = lambda key, fact: fact in (
        target_facts.get(key, set()) | derived_target_facts.get(key, set())
    )
    if any(name == "GroupMember" and operation in {"insert", "delete"} for name, operation in target_operations):
        matched_uncatalogued.add("10")
    if any(
        (
            name == "Territory" and operation in {"insert", "delete"}
            or has_fact((name, operation), "territory_reparent_or_membership_change")
        )
        for name, operation in target_operations
    ):
        matched_uncatalogued.add("14")
    if any(
        name == "User"
        and operation in {"insert", "update", "upsert"}
        and has_fact((name, operation), "user_role_id_present_or_changed")
        for name, operation in target_operations
    ):
        matched_uncatalogued.add("15")
    if any(name == "UserRole" and operation in {"insert", "delete"} for name, operation in target_operations):
        matched_uncatalogued.add("16")
    if any(
        name == "UserRole"
        and operation in {"update", "upsert"}
        and has_fact((name, operation), "user_role_reparent")
        for name, operation in target_operations
    ):
        matched_uncatalogued.add("17")
    if any(
        name in {"AccountTeamMember", "CaseTeamMember", "OpportunityTeamMember"}
        and operation in {"insert", "delete"}
        for name, operation in target_operations
    ):
        matched_uncatalogued.add("4")
    if (
        ("Account", "delete") in target_operations
        or any(
            name == "Account" and operation in {"insert", "update", "upsert"}
            and has_fact((name, operation), "account_owner_write")
            for name, operation in target_operations
        )
        or ("SF_LOCK_SUPPRESS_OWNER_V1" in receipt_rule_ids and any(
            name == "Account" and has_fact((name, operation), "account_owner_write")
            for name, operation in target_operations
        ))
    ):
        matched_uncatalogued.add("3")
    if any(
        name == "User"
        and operation in {"insert", "upsert"}
        and has_fact((name, operation), "role_based_portal_user")
        for name, operation in target_operations
    ):
        matched_uncatalogued.add("32")
    uncatalogued_controls = [
        {
            "cheatSheetRow": row_number,
            "triggerCondition": uncatalogued_by_row[row_number]["trigger_condition"],
            "consequence": uncatalogued_by_row[row_number]["consequence"],
            "action": uncatalogued_by_row[row_number]["action"],
        }
        for row_number in sorted(matched_uncatalogued, key=int)
    ]
    use_serial = bool(named_serial_operation or uncatalogued_controls or
                      prior_parameters and prior_parameters.get("serialModeEvidence"))
    serial_mode_evidence = []
    if named_serial_operation:
        serial_mode_evidence.append({
            "source": "named-operation", "detail": named_serial_operation,
        })
    serial_mode_evidence.extend(
        {
            "source": "uncatalogued-lock-row",
            "detail": row["cheatSheetRow"],
        }
        for row in uncatalogued_controls
    )
    recommendations = _recommendation_values(data_dir)
    loader_rows = {row["tool"]: row for row in _data_rows(data_dir, "tool-matrix.csv")}
    if loader not in loader_rows:
        raise ContractError(f"unsupported loader: {loader}")
    selected_api = confirmed_api or (
        "Bulk API 1.0" if loader == "Bulk API 1.0" else
        "Bulk API 2.0" if loader in {"Bulk API 2.0", "sf CLI"} else
        "REST API" if loader in {"Salesforce Inspector Reloaded", "Workbench"} else
        "Bulk API" if loader == "dataloader.io" else
        "Bulk API 1.0" if use_serial else
        "Bulk API 2.0" if maximum_volume > recommendations["bulkPreferred"] else "SOAP API"
    )
    serial_supported = loader in {"Data Loader", "Bulk API 1.0"} and selected_api == "Bulk API 1.0"
    serial_unavailable = use_serial and not serial_supported
    _validate_loader_parameters({"loader": loader, "api": selected_api,
                                 "concurrencyMode": "parallel",
                                 "batchSize": "server-managed" if selected_api in {"Bulk API 2.0", "Bulk API"} else 1})
    parameters = {
        "loader": loader,
        "targetOperations": sorted({operation for _, operation in target_operations}),
        "api": selected_api,
        "batchSize": "server-managed" if selected_api in {"Bulk API 2.0", "Bulk API"} else recommendations["lockBatch"] if lock_risk else (
            recommendations["bulkBatch"]
            if maximum_volume > recommendations["bulkPreferred"]
            else recommendations["soapBatch"]
        ),
        "concurrencyMode": "serial" if use_serial and serial_supported else "parallel",
        "serialModeUnavailable": serial_unavailable,
        "knownRisks": ([SERIAL_RISK] if serial_unavailable else []),
        "serialModeEvidence": serial_mode_evidence,
        "groupByParentId": lock_risk,
        "parentSortField": next(iter(parent_sort_columns)) if len(parent_sort_columns) == 1 else None,
        "lockRiskDetected": lock_risk,
        "lockRiskReviewEvidence": lock_review_evidence,
        "skewThreshold": recommendations["skewThreshold"],
        "assignmentRulesEnabled": False,
        "validationReplacementChecksRequired": True,
        "deduplicateSource": True,
        "fireChainCoverageRequired": True,
        "fireChainCoverageComplete": fire_chain_complete,
        "exportResultsWithinDays": 7,
        "orderedReEnableRequired": True,
        "rollbackBySuccessIds": True,
        "hardDeleteEnabled": False,
        "lockMitigationLadder": [row["action"] for row in _data_rows(data_dir, "lock-mitigation-ladder.csv")],
        "uncataloguedLockControls": uncatalogued_controls,
    }
    if prior_parameters is not None:
        for key in (
            "groupByParentId", "parentSortField", "concurrencyMode", "api", "batchSize",
            "serialModeEvidence",
        ):
            if key not in prior_parameters:
                raise ContractError(f"prior parameters are missing {key}")
            parameters[key] = copy.deepcopy(prior_parameters[key])
        for key in ("duplicateRulePredictions", "preLoadChecks", "knownRisksAcceptedOn", "knownRisks", "ownerSteps"):
            if key in prior_parameters:
                parameters[key] = copy.deepcopy(prior_parameters[key])
    _sync_serial_risk(parameters)
    controls = _incident_controls(_data_rows(data_dir, "incident-classes.csv"), checklist_rows, parameters)
    parameters["incidentControls"] = controls
    parameters["uncontrolledIncidentClasses"] = _owner_rulable_incident_classes(controls, checklist_rows, parameters)
    types_by_name = {name: {row["automation_type"] for row in checklist_rows if row["automation_api_name"] == name}
                     for name in {row["automation_api_name"] for row in checklist_rows}}
    output_ambiguous_names = {name for name, types in types_by_name.items() if len(types) > 1} | ambiguous_verdict_names
    if not output_ambiguous_names.issubset(ambiguous_names):
        return build_package(
            bundle_directories, verdicts, data_dir, named_serial_operation, target_facts,
            tool_targets, unpredicted_automations, prior_parameters, loader, managed_packages,
            duplicate_rules, confirmed_api=confirmed_api, ambiguous_names=output_ambiguous_names,
            source_manifest=source_manifest)
    return checklist_rows, parameters


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", nargs="*", type=Path)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--apply-lock-ladder", action="store_true")
    parser.add_argument("--checklist", type=Path)
    parser.add_argument("--parameters", type=Path)
    parser.add_argument("--lock-errors", type=int)
    parser.add_argument("--bypass-verdicts", type=Path)
    parser.add_argument("--source-manifest", type=Path, help="Local source manifest supplies missing downstream node types")
    parser.add_argument("--tool-targets", type=Path)
    parser.add_argument("--loader", default="Data Loader")
    parser.add_argument("--confirmed-api", help="API confirmed with the loader at intake")
    parser.add_argument("--draft-checklist", type=Path)
    parser.add_argument("--draft-parameters", type=Path)
    parser.add_argument("--owner-checklist", type=Path)
    parser.add_argument("--owner-parameters", type=Path)
    parser.add_argument("--prior-parameters", type=Path)
    parser.add_argument("--unpredicted-automations", type=Path)
    parser.add_argument("--managed-packages", type=Path)
    parser.add_argument("--duplicate-rules", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "skills" / "data-load-impact" / "data")
    parser.add_argument("--checklist-out", type=Path)
    parser.add_argument("--parameters-out", type=Path)
    parser.add_argument(
        "--named-serial-operation",
        choices=(
            "create-users", "ownership-change-private-sharing",
            "update-user-roles", "update-territory-hierarchy",
        ),
    )
    parser.add_argument(
        "--target-fact",
        action="append",
        default=[],
        metavar="OBJECT:OPERATION=FACT",
        help="Repeat only for role_based_portal_user, which depends on the loaded records.",
    )
    return parser


def _target_facts(values: list[str]) -> dict[tuple[str, str], set[str]]:
    result: dict[tuple[str, str], set[str]] = {}
    for value in values:
        try:
            target, fact = value.split("=", 1)
            object_name, operation = target.rsplit(":", 1)
        except ValueError:
            raise ContractError(f"invalid target fact {value!r}; expected OBJECT:OPERATION=FACT") from None
        if not object_name or operation not in {"insert", "update", "upsert", "delete"}:
            raise ContractError(f"invalid target fact target {target!r}")
        if fact in DERIVED_TARGET_FACT_VALUES:
            raise ContractError(
                f"target fact {fact!r} is derived from projected tool targets; "
                "--target-fact accepts only role_based_portal_user"
            )
        if fact not in TARGET_FACT_VALUES:
            raise ContractError(f"unknown target fact {fact!r}")
        result.setdefault((object_name, operation), set()).add(fact)
    return result


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.apply_lock_ladder:
            if arguments.finalize or arguments.bundles:
                raise ContractError("lock ladder mode cannot build or finalize a package")
            required = {
                "--checklist": arguments.checklist,
                "--parameters": arguments.parameters,
                "--lock-errors": arguments.lock_errors,
                "--parameters-out": arguments.parameters_out,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ContractError(f"lock ladder requires {', '.join(missing)}")
            rung, updated = apply_lock_ladder(
                read_csv(arguments.checklist)[1], read_json(arguments.parameters),
                arguments.lock_errors, arguments.data_dir,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            if rung is None:
                if updated is not None:
                    write_json(arguments.parameters_out, updated)
                print("no automatic rung: serial mode already ran or is unavailable in the chosen loader")
                return 2
            write_json(arguments.parameters_out, updated)
            print(f"applied lock ladder rung {rung}")
            return 0
        if arguments.checklist_out is None or arguments.parameters_out is None:
            raise ContractError("draft and finalize modes require --checklist-out and --parameters-out")
        if arguments.finalize:
            required = {
                "--draft-checklist": arguments.draft_checklist,
                "--draft-parameters": arguments.draft_parameters,
                "--owner-checklist": arguments.owner_checklist,
                "--owner-parameters": arguments.owner_parameters,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ContractError(f"finalize requires {', '.join(missing)}")
            _, draft_rows = read_csv(arguments.draft_checklist)
            _, owner_rows = read_csv(arguments.owner_checklist)
            rows, parameters = finalize_package(
                draft_rows, read_json(arguments.draft_parameters),
                owner_rows, read_json(arguments.owner_parameters), arguments.data_dir,
                read_json(arguments.prior_parameters) if arguments.prior_parameters else None,
            )
        else:
            if not arguments.bundles or arguments.bypass_verdicts is None or arguments.tool_targets is None:
                raise ContractError("draft mode requires bundles, --bypass-verdicts, and --tool-targets")
            _, verdicts = read_csv(arguments.bypass_verdicts)
            rows, parameters = build_package(
                arguments.bundles, verdicts, arguments.data_dir,
                arguments.named_serial_operation,
                _target_facts(arguments.target_fact), read_json(arguments.tool_targets),
                read_json(arguments.unpredicted_automations)
                if arguments.unpredicted_automations else [],
                read_json(arguments.prior_parameters) if arguments.prior_parameters else None,
                arguments.loader,
                read_json(arguments.managed_packages) if arguments.managed_packages else None,
                read_json(arguments.duplicate_rules) if arguments.duplicate_rules else None,
                confirmed_api=arguments.confirmed_api,
                source_manifest=read_json(arguments.source_manifest) if arguments.source_manifest else None,
            )
        write_csv(arguments.checklist_out, CHECKLIST_COLUMNS, rows)
        write_json(arguments.parameters_out, parameters)
    except ContractError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"wrote {len(rows)} checklist row(s) and {len(parameters['incidentControls'])} incident control(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
