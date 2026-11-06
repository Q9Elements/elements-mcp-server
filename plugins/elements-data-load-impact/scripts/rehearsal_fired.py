"""Parse local debug logs and loader errors into automation and aggregate error counts."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

# Resolve shipped sibling modules when invoked with python3 -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .dli_common import ContractError, write_json
except ImportError:
    from dli_common import ContractError, write_json


TRUNCATION_MARKERS = ("MAXIMUM DEBUG LOG SIZE REACHED", "LOG TRUNCATED", "TRUNCATED LOG")
SKIPPED_BYTES = re.compile(r"\*\*\*\s*SKIPPED\s+\d+\s+BYTES\s+OF\s+DETAILED\s+LOG\s*\*\*", re.IGNORECASE)
SALESFORCE_ID = re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")
RESULT_JOB = re.compile(r"^(.+?)-(?:success|failed)-records\.csv$", re.IGNORECASE)
TRIGGER_NAME = re.compile(r"^([^|]+?)\s+on\s+.+?\s+trigger event\b", re.IGNORECASE)
LIMIT_LINE = re.compile(r"^\s*([^:]+):\s*(\d+)\s+out of\s+(\d+)\s*$")
EVENT_TYPES = {
    "FLOW_START_INTERVIEW_BEGIN": "Flow",
    "VALIDATION_RULE": "Validation Rule",
    "WF_CRITERIA_BEGIN": "Workflow Rule",
    "WF_EMAIL_ALERT": "Workflow Email Alert",
}


def _safe_name(value: str) -> str | None:
    candidate = value.strip()
    if not candidate or SALESFORCE_ID.fullmatch(candidate):
        return None
    return candidate[:255]


def _event(line: str):
    fields = [field.strip() for field in line.rstrip("\r\n").split("|")]
    event_type = fields[1] if len(fields) > 1 else ""
    details = fields[2:]
    if event_type == "ENTERING_MANAGED_PKG":
        name = details[0].strip()[:255] if details else None
        return ("Managed Package", name) if name else None
    if event_type == "DUPLICATE_DETECTION_RULE_INVOCATION":
        for field in details:
            if field.startswith("DuplicateRuleName:"):
                name = _safe_name(field.split(":", 1)[1])
                return ("Duplicate Rule", name) if name else None
    if event_type == "METHOD_ENTRY":
        for position, field in enumerate(details):
            if re.fullmatch(r"01p[A-Za-z0-9]{12,15}", field) and position + 1 < len(details):
                match = re.match(r"([A-Za-z_]\w*)\.[A-Za-z_]\w*\(", details[position + 1])
                if match:
                    return "Apex Class", match.group(1)
    if event_type == "CODE_UNIT_STARTED":
        for field in details:
            match = TRIGGER_NAME.match(field)
            if match:
                name = _safe_name(match.group(1))
                return ("Apex Trigger", name) if name else None
        for position, field in enumerate(details):
            if field.startswith("Flow:"):
                return None
            if re.fullmatch(r"01p[A-Za-z0-9]{12,15}", field) and position + 1 < len(details):
                name = details[position + 1].split(".", 1)[0].strip()[:255]
                return ("Apex Class", name) if name else None
            if re.fullmatch(r"[A-Za-z_]\w*\.[A-Za-z_]\w*", field):
                name = field.split(".", 1)[0][:255]
                return ("Apex Class", name) if name else None
        return None
    if event_type == "EMAIL_QUEUE":
        return "Email Send", "Email send"
    for marker, automation_type in EVENT_TYPES.items():
        if event_type != marker:
            continue
        for field in reversed(details):
            name = _safe_name(field)
            if name:
                return automation_type, name
    return None


def parse_logs(paths: list[Path]) -> dict:
    counts = Counter()
    queued_emails = 0
    limits = {}
    truncated_count = 0
    incomplete_count = 0
    for path in paths:
        started = 0
        finished = 0
        explicit_truncation = False
        saw_content = False
        namespace = None
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    saw_content = saw_content or bool(line.strip())
                    if any(marker in line.upper() for marker in TRUNCATION_MARKERS) or SKIPPED_BYTES.search(line):
                        explicit_truncation = True
                    fields = [field.strip() for field in line.split("|")]
                    event_type = fields[1] if len(fields) > 1 else ""
                    if event_type == "LIMIT_USAGE_FOR_NS":
                        namespace = fields[2] if len(fields) > 2 else None
                    elif namespace:
                        match = LIMIT_LINE.match(line)
                        if match:
                            label, used, ceiling = match.groups()
                            current = limits.setdefault(namespace, {}).get(label)
                            if current is None or (
                                int(ceiling) <= 0 and current["ceiling"] > 0
                            ) or (
                                int(ceiling) > 0 and current["ceiling"] > 0
                                and int(used) * current["ceiling"] > current["used"] * int(ceiling)
                            ):
                                limits[namespace][label] = {"used": int(used), "ceiling": int(ceiling)}
                        else:
                            namespace = None
                    if event_type == "EMAIL_QUEUE":
                        queued_emails += 1
                    started += event_type == "EXECUTION_STARTED"
                    finished += event_type == "EXECUTION_FINISHED"
                    event = _event(line)
                    if event:
                        counts[event] += 1
        except OSError as error:
            raise ContractError(f"cannot read log file: {path}") from error
        if explicit_truncation or started != finished:
            truncated_count += 1
        if explicit_truncation or not saw_content or started != finished:
            incomplete_count += 1
    automations = [
        {"name": name, "type": automation_type, "fireCount": fire_count}
        for (automation_type, name), fire_count in sorted(counts.items(), key=lambda item: (item[0][1], item[0][0]))
    ]
    return {
        "complete": bool(paths) and incomplete_count == 0,
        "logsProcessed": len(paths),
        "truncatedLogCount": truncated_count,
        "incompleteLogCount": incomplete_count,
        "automations": automations,
        "queuedEmails": queued_emails,
        "governorLimits": limits,
    }


ERROR_CODES = ("DUPLICATES_DETECTED", "UNABLE_TO_LOCK_ROW")


def _parse_result_files(paths: list[Path], success_only_paths: set[Path] | None = None) -> dict:
    counts = Counter({code: 0 for code in ERROR_CODES})
    failed_rows = 0
    success_rows = 0
    success_only_paths = success_only_paths or set()
    for path in paths:
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle, strict=True)
                header = next(reader, [])
                if len(header) != len(set(header)):
                    raise ContractError(f"invalid error file: {path}")
                error_column = next((header.index(name) for name in ("ERROR", "sf__Error", "Error") if name in header), None)
                success_column = header.index("Success") if "Success" in header else None
                if error_column is None and path not in success_only_paths:
                    raise ContractError(f"error file has no recognized error column: {path}")
                if error_column is None and not ({"sf__Id", "sf__Created"} <= set(header) or success_column is not None or {"ID", "STATUS"} <= set(header)):
                    raise ContractError(f"success file has no recognized result columns: {path}")
                pending_blank = False
                for row in reader:
                    if not row:
                        pending_blank = True
                        continue
                    if pending_blank:
                        raise ContractError(f"invalid error file: {path}")
                    if len(row) != len(header):
                        raise ContractError(f"invalid error file: {path}")
                    cell = row[error_column].strip() if error_column is not None else ""
                    success_flag = row[success_column].strip().lower() if success_column is not None else ""
                    if success_column is not None and success_flag not in {"true", "false"}:
                        raise ContractError(f"invalid error file: {path}")
                    if success_column is not None and ((success_flag == "true" and cell) or (success_flag == "false" and not cell)):
                        raise ContractError(f"invalid error file: {path}")
                    if success_column is None and error_column is not None and not cell and path not in success_only_paths:
                        raise ContractError(f"invalid error file: {path}")
                    if not cell and not (success_flag == "true" or path in success_only_paths):
                        raise ContractError(f"invalid error file: {path}")
                    if not cell:
                        id_column = next((header.index(name) for name in ("sf__Id", "Id", "ID") if name in header), None)
                        if id_column is None or not row[id_column].strip():
                            raise ContractError(f"invalid error file: {path}")
                        success_rows += 1
                        continue
                    failed_rows += 1
                    for code in ERROR_CODES:
                        if re.search(rf"(?<![A-Za-z0-9_]){code}(?![A-Za-z0-9_])", cell):
                            counts[code] += 1
        except OSError as error:
            raise ContractError(f"cannot read error file: {path}") from error
        except (csv.Error, UnicodeError) as error:
            raise ContractError(f"unreadable error file: {path}") from error
    return {"successRowsRead": success_rows, "errorRowsRead": failed_rows, "errorCounts": dict(counts)}


def parse_error_files(paths: list[Path]) -> dict:
    result = _parse_result_files(paths)
    return {key: result[key] for key in ("errorRowsRead", "errorCounts")}


def validate_result_jobs(success_paths: list[Path], error_paths: list[Path]) -> None:
    job_ids = {match.group(1) for path in success_paths + error_paths
               if (match := RESULT_JOB.fullmatch(path.name))}
    if len(job_ids) > 1:
        raise ContractError("result files carry different job identifiers")


def _unique_result_paths(success_paths: list[Path], error_paths: list[Path]) -> tuple[list[Path], set[Path]]:
    paths = []
    success_only = set()
    seen = {}
    for is_success, path in [(True, path) for path in success_paths] + [(False, path) for path in error_paths]:
        try:
            identity = (path.stat().st_dev, path.stat().st_ino)
        except OSError as error:
            raise ContractError(f"cannot read result file: {path}") from error
        if identity not in seen:
            seen[identity] = path
            paths.append(path)
        if is_success:
            success_only.add(seen[identity])
    return paths, success_only


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--error-file", nargs="+", required=True, type=Path)
    parser.add_argument("--success-file", nargs="+", required=True, type=Path)
    parser.add_argument("--rows-loaded", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        observed = parse_logs(arguments.logs)
        if arguments.rows_loaded < 0:
            raise ContractError("rows loaded must be non-negative")
        validate_result_jobs(arguments.success_file, arguments.error_file)
        result_paths, success_paths = _unique_result_paths(arguments.success_file, arguments.error_file)
        observed.update(_parse_result_files(result_paths, success_paths))
        observed["rowsLoaded"] = arguments.rows_loaded
        observed["complete"] = observed["complete"] and (
            observed["successRowsRead"] + observed["errorRowsRead"] == arguments.rows_loaded
        )
        write_json(arguments.out, observed)
    except ContractError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"processed {observed['logsProcessed']} log(s); observed {len(observed['automations'])} automation name(s); "
        f"complete: {'yes' if observed['complete'] else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
