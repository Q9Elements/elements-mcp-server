#!/usr/bin/env python3
"""Download metadata source and discover missing helper classes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from urllib.request import urlopen
from xml.etree import ElementTree

# Resolve shipped sibling modules when invoked with python3 -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))


CLASS_CALL = re.compile(
    r"(?<![\w.])(?:([A-Za-z][A-Za-z0-9_]*)\s*\.\s*)?"
    r"([A-Za-z][A-Za-z0-9_]*)\s*\.\s*[A-Za-z][A-Za-z0-9_]*\s*\("
)
NEW_CLASS = re.compile(r"\bnew\s+([A-Za-z][A-Za-z0-9_]*)\s*\(", re.I)
EXTENDS = re.compile(r"\bextends\s+([A-Za-z][A-Za-z0-9_]*)\b", re.I)
NON_CODE = re.compile(r"//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\])*'", re.S)
DECLARED_CLASS = re.compile(r"\b(?:class|interface|enum)\s+([A-Za-z][A-Za-z0-9_]*)", re.I)
DECLARED_VARIABLE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9_]*(?:\s*\.\s*[A-Za-z][A-Za-z0-9_]*)*"
    r"(?:\s*<[^;{}()=]+?>\s*|\s*(?:\[\s*\]\s*)+|\s+)"
    r"([A-Za-z][A-Za-z0-9_]*)\s*(?=[=;,:){])"
)
NEXT_VARIABLE = re.compile(r"\s*,\s*([A-Za-z][A-Za-z0-9_]*)\s*(?=[=;,])")
PACKAGE_SCHEMA = re.compile(r"\b([A-Za-z][A-Za-z0-9]*)__[A-Za-z][A-Za-z0-9_]*__(?:c|mdt|e|b|x)\b", re.I)
SOBJECT_REFERENCE = re.compile(
    r"\b(?:from|on)\s+([A-Za-z][A-Za-z0-9_]*)\b"
    r"|\b(?:Schema\s*\.\s*)?SObjectType\s*\.\s*([A-Za-z][A-Za-z0-9_]*)"
    r"|\b([A-Za-z][A-Za-z0-9_]*)\s*\.\s*(?:SObjectType|Fields)\b"
    r"|\bnew\s+([A-Za-z][A-Za-z0-9_]*)\s*\(\s*[A-Za-z][A-Za-z0-9_]*\s*=",
    re.I,
)
FLOW_ACTION = re.compile(r"<actionCalls\b[^>]*>.*?</actionCalls>", re.I | re.S)
FLOW_NAME = re.compile(r"<actionName>\s*([A-Za-z][A-Za-z0-9_]*)\s*</actionName>", re.I)
FLOW_TYPE = re.compile(r"<actionType>\s*apex\s*</actionType>", re.I)
PLATFORM_CLASSES = {
    "System", "String", "Integer", "Decimal", "Date", "Datetime", "Time", "Math",
    "JSON", "Database", "Schema", "Limits", "UserInfo", "EncodingUtil", "Crypto",
    "FeatureManagement", "Test", "Trigger", "Messaging", "ApexPages", "Label",
    "List", "Set", "Map", "Id", "Boolean", "Blob", "RestContext", "URL", "SObjectType",
    "Object", "SObject", "Long", "Double", "Type", "Pattern", "Matcher", "Timezone",
    "Http", "HttpRequest", "HttpResponse", "RestRequest", "RestResponse", "PageReference",
    "Approval", "EventBus", "ConnectApi", "Flow", "Auth", "Site", "Sites", "Page",
    "Exception", "DmlException", "QueryException", "AuraHandledException",
    "IllegalArgumentException", "NoAccessException", "NullPointerException",
    "StringException", "TypeException", "ListException", "SObjectException",
    "this", "super",
}
STANDARD_OBJECTS = {
    "Account", "Contact", "Lead", "Opportunity", "OpportunityLineItem", "OpportunityContactRole",
    "Case", "Asset", "Contract", "Order", "OrderItem", "Product2", "Pricebook2", "PricebookEntry",
    "Quote", "QuoteLineItem", "Task", "Event", "User", "UserRole", "Group", "GroupMember",
    "RecordType", "Profile", "PermissionSet", "PermissionSetAssignment", "EmailMessage",
    "Attachment", "ContentVersion", "ContentDocument", "ContentDocumentLink", "Entitlement",
    "Campaign", "CampaignMember", "AccountShare", "OpportunityShare", "CaseShare",
}
BODY_EXTENSION = {"Apex Class": ".cls", "Apex Trigger": ".trigger"}


def _variable_ranges(code: str) -> dict[str, list[tuple[int, int]]]:
    """Bound receiver exclusions by their declaring block or parameter body."""
    blocks = {-1: len(code)}
    parentheses = {}
    stack = []
    for token in re.finditer(r"[{}()]", code):
        if token[0] in "{(":
            stack.append((token[0], token.start()))
        elif stack and stack[-1][0] == {"}": "{", ")": "("}[token[0]]:
            kind, start = stack.pop()
            (blocks if kind == "{" else parentheses)[start] = token.start()

    variables = {}
    scopes = list(blocks.items()) + list(parentheses.items())
    for declaration in DECLARED_VARIABLE.finditer(code):
        start, end = min((scope for scope in scopes
                          if scope[0] <= declaration.start(1) < scope[1]),
                         key=lambda scope: scope[1] - scope[0])
        if start in parentheses:
            body = re.match(r"\s*\{", code[end + 1:])
            if not body:
                continue
            end = blocks.get(end + body.end(), end)
        names = [(declaration[1], declaration.end())]
        position = declaration.end()
        while extra := NEXT_VARIABLE.match(code, position):
            names.append((extra[1], extra.end()))
            position = extra.end()
        for name, position in names:
            variables.setdefault(name.casefold(), []).append((position, end))
    return variables


def _apex_calls(content: str, schema_names: set[str]) -> set[str]:
    code = NON_CODE.sub(" ", content)
    platform = {name.casefold() for name in PLATFORM_CLASSES}
    excluded = schema_names | platform
    excluded.update(name.casefold() for name in DECLARED_CLASS.findall(code))
    excluded.update(name.casefold() for match in SOBJECT_REFERENCE.findall(code) for name in match if name)
    variables = _variable_ranges(code)
    candidates = set()
    for match in CLASS_CALL.finditer(code):
        qualifier, name = match.groups()
        if qualifier and qualifier.casefold() in platform:
            continue
        receiver = qualifier or name
        if any(start <= match.start() < end
               for start, end in variables.get(receiver.casefold(), [])):
            continue
        candidates.add(name)
    candidates.update(NEW_CLASS.findall(code) + EXTENDS.findall(code))
    return {name for name in candidates if name.casefold() not in excluded
            and not name.casefold().endswith(("__c", "__mdt", "__e", "__b", "__x"))}


def _schema_names(manifest: dict, sources: list[tuple[dict, str]]) -> set[str]:
    names = {name.casefold() for name in STANDARD_OBJECTS}
    for entry in manifest["files"]:
        if entry["type"] in {"Object", "Custom Object", "Standard Object"}:
            names.add(entry.get("apiName", entry.get("name", "")).split(".")[-1].casefold())
    for entry, content in sources:
        if entry["type"] in BODY_EXTENSION:
            code = NON_CODE.sub(" ", content)
            names.update(name.casefold() for name in PACKAGE_SCHEMA.findall(code))
            names.update(name.casefold() for match in SOBJECT_REFERENCE.findall(code)
                         for name in match if name)
        else:
            try:
                xml = ElementTree.fromstring(content)
            except ElementTree.ParseError:
                continue
            for node in xml.iter():
                if node.tag.rsplit("}", 1)[-1] in {"object", "objectType"}:
                    names.update(part.casefold() for part in (node.text or "").strip().split(".") if part)
    return names


def _safe_part(value: str) -> str:
    if not value or value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_. -]+", value):
        raise ValueError("source name or type contains unsupported path characters")
    return value


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _fetch(url: str) -> bytes:
    if urlparse(url).scheme != "https":
        raise ValueError("source URL must use HTTPS")
    with urlopen(url, timeout=30) as response:
        if response.status != 200:
            raise OSError(f"HTTP {response.status}")
        data = response.read()
    if not data:
        raise OSError("empty source file")
    if re.match(br"\s*(?:<!doctype\s+html|<html\b)", data, re.I):
        raise OSError("HTML error page")
    return data


def _manifest(root: Path) -> dict:
    path = root / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"files": []}


def fetch(replies: Path, root: Path, sync_date: str) -> dict:
    """Write joined metadata source rows and merge the manifest by node identifier."""
    from part_files import PartError, join

    with TemporaryDirectory(prefix="dli-source-") as directory:
        joined = Path(directory) / "source.ndjson"
        try:
            join(replies, joined)
        except PartError:
            raise
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
            raise PartError(5, "invalid reply, download or file integrity error") from error
        rows = [json.loads(line) for line in joined.read_text(encoding="utf-8").splitlines()]
    manifest = _manifest(root)
    files = {str(entry["nodeId"]): entry for entry in manifest["files"]}
    for item in rows:
        node_id = str(item["nodeId"])
        name = str(item["apiName"])
        kind = str(item["sfType"])
        record = {"nodeId": node_id, "apiName": name, "type": kind,
                  "status": item["status"], "reason": item.get("reason"),
                  "xmlScope": item.get("xmlScope"), "syncDate": sync_date,
                  "outcome": "managed_code_hidden" if item.get("reason") == "managed_code_hidden"
                  else "downloaded"}
        try:
            folder = root / _safe_part(kind)
            stem = _safe_part(name)
        except ValueError:
            record.update({"outcome": "failed", "error": "unsafe_name"})
            files[node_id] = record
            continue
        if item["status"] == "not_available":
            if item["reason"] != "managed_code_hidden":
                record["outcome"] = item["reason"]
                files[node_id] = record
                continue
        folder.mkdir(parents=True, exist_ok=True)
        for key, extension in (("xml", ".xml"), ("body", BODY_EXTENSION.get(kind, ".body"))):
            if key == "body" and record["outcome"] == "managed_code_hidden":
                continue
            if item.get(key) is not None:
                path = folder / f"{stem}{extension}"
                path.write_text(item[key], encoding="utf-8")
                record[key] = {"path": str(path.relative_to(root))}
        files[node_id] = record
    manifest["files"] = sorted(files.values(), key=lambda entry: (entry["type"], entry["apiName"], entry["nodeId"]))
    _write_json(root / "manifest.json", manifest)
    return {outcome: sum(entry["outcome"] == outcome for entry in manifest["files"])
            for outcome in sorted({entry["outcome"] for entry in manifest["files"]})}


def scan(root: Path) -> dict:
    """Find plausible Apex helper names for exact metadata-name resolution."""
    manifest = _manifest(root)
    downloaded = {
        entry.get("apiName", entry.get("name"))
        for entry in manifest["files"]
        if entry.get("type") == "Apex Class" and entry.get("outcome", "downloaded") == "downloaded"
    }
    sources = []
    for entry in manifest["files"]:
        if entry.get("outcome", "downloaded") != "downloaded":
            continue
        keys = ("body",) if entry["type"] in BODY_EXTENSION else (
            ("xml",) if entry["type"] == "Flow" else ())
        for key in keys:
            file_info = entry.get(key)
            if not file_info:
                continue
            content = (root / file_info["path"]).read_text(encoding="utf-8", errors="replace")
            sources.append((entry, content))
    schema_names = _schema_names(manifest, sources)
    called = set()
    for entry, content in sources:
        if entry["type"] == "Flow":
            for action in FLOW_ACTION.findall(content):
                if FLOW_TYPE.search(action):
                    called.update(FLOW_NAME.findall(action))
        else:
            called.update(_apex_calls(content, schema_names))
    downloaded_names = {name.casefold() for name in downloaded}
    return {"missingCalledClasses": sorted(name for name in called if name.casefold() not in downloaded_names)}


def main(argv: list[str] | None = None) -> int:
    from part_files import PartError

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_parser = commands.add_parser("fetch")
    fetch_parser.add_argument("--replies", type=Path, required=True)
    fetch_parser.add_argument("--root", type=Path, required=True)
    fetch_parser.add_argument("--sync-date", required=True)
    scan_parser = commands.add_parser("scan")
    scan_parser.add_argument("--root", type=Path, default=Path("work/source"))
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            print(json.dumps(fetch(args.replies, args.root, args.sync_date)))
        else:
            print(json.dumps(scan(args.root)))
        return 0
    except PartError as error:
        print(f"source_files: {error}", file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"source_files: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
