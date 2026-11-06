"""Shared change delta vocabulary for dependent rules and backlog planning."""

from cli_common import field_object

# This set is a decided migration rule. Keep it stable when changing dispositions.
MIGRATION_KEYS = ("type", "data_type", "length", "values_removed", "field_required", "restricted")
ENTRY_CONDITION_CHANGE_KEY = "entry_condition_change"
VALUE_ADDED_KEYS = ("values_added",)
VALUE_REMOVED_KEYS = ("values_removed", "values_deleted", "value_deleted", "deleted_values")
VALUE_DEACTIVATED_KEYS = ("values_deactivated", "value_deactivated", "deactivated")
VALUE_RENAMED_KEYS = ("values_renamed", "api_names_renamed", "label", "new_label", "label_rename",
                      "api_name", "new_api_name", "api_name_rename")
REPORT_CHANGE_KEYS = (*VALUE_REMOVED_KEYS, *VALUE_DEACTIVATED_KEYS, *VALUE_RENAMED_KEYS)


def field_name(element):
    """Return a field's qualified name from held identity facts."""
    name = element.get("apiName") or element.get("api_name") or ""
    parent = field_object(element)
    return name if "." in name or not parent else f"{parent}.{name}"


def written_fields(change):
    """Return qualified delta writes for string and structured field inputs."""
    element = change.get("element") or {}
    delta = change.get("delta") or {}
    parent = (delta.get("trigger_object") or element.get("trigger_object") or element.get("triggerObject")
              or field_object(element))
    fields = delta.get("written_fields") or delta.get("writtenFields") or []
    if isinstance(fields, str):
        fields = [fields]
    return {(field_name(field) if field_object(field)
             else field_name({**field, "parentObject": parent})) if isinstance(field, dict)
            else field_name({"apiName": field, "parentObject": parent}) for field in fields}


def writes_added_value(change, elements):
    """Whether an automation change writes a field with added values in this set."""
    if change.get("action") not in {"create", "update"}:
        return False
    return any(other is not change and other.get("action") in {"create", "update"}
               and (other.get("delta") or {}).get("values_added")
               and field_name(other.get("element") or {}) in written_fields(change) for other in elements)
