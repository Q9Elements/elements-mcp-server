"""Shared change delta vocabulary for dependent rules and backlog planning."""

# This set is a decided migration rule. Keep it stable when changing dispositions.
MIGRATION_KEYS = ("type", "data_type", "length", "values_removed", "field_required", "restricted")
ENTRY_CONDITION_CHANGE_KEY = "entry_condition_change"
VALUE_ADDED_KEYS = ("values_added",)
VALUE_REMOVED_KEYS = ("values_removed", "values_deleted", "value_deleted", "deleted_values")
VALUE_DEACTIVATED_KEYS = ("values_deactivated", "value_deactivated", "deactivated")
VALUE_RENAMED_KEYS = ("values_renamed", "api_names_renamed", "label", "new_label", "label_rename",
                      "api_name", "new_api_name", "api_name_rename")
REPORT_CHANGE_KEYS = (*VALUE_REMOVED_KEYS, *VALUE_DEACTIVATED_KEYS, *VALUE_RENAMED_KEYS)
