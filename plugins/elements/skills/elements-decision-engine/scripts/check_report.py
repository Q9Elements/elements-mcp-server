#!/usr/bin/env python3
"""Validate a local HyperText Markup Language (HTML) report.

## Contents
- Usage and exit codes
- Report parser and content checks
- Command entry point

Usage: python3 scripts/check_report.py REPORT.html
Exit 0: checks pass; inspect the rendered report before presenting it.
Exit 1: report checks fail; fix the named content and run this command again.
Exit 2: input or usage fails; correct the path, encoding, or arguments and retry.
Uses Python 3 standard library only. It checks the template contract, not browser rendering.
"""

import argparse
import sys
from pathlib import Path
from html.parser import HTMLParser


class UsageParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}; supply REPORT.html or use --help, then retry")


# HTML void elements never push onto the nesting stack.
VOID_ELEMENTS = set("area base br col embed hr img input link meta param source track wbr".split())


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "root", "attrs": {}, "children": []}
        self.stack = [self.root]
        self.elements = []
        self.script_in_panel = False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and any("panel" in (ancestor["attrs"].get("class") or "").split()
                                   for ancestor in self.stack):
            self.script_in_panel = True
        node = {"tag": tag, "attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(node)
        self.elements.append(node)
        if tag not in VOID_ELEMENTS:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1]["children"].append(data)


def panel_text(node):
    if isinstance(node, str):
        return node
    if node["tag"] in {"h2", "script", "style"}:
        return ""
    if node["tag"] in {"img", "svg"}:
        return "graphic"
    value = "".join(panel_text(child) for child in node["children"])
    if "empty" in (node["attrs"].get("class") or "").split() and value.strip() == "Pending.":
        return ""
    return value


def main():
    parser = UsageParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        content = args.report.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"INPUT: {error}; supply a readable Unicode Transformation Format 8-bit (UTF-8) report path and retry.", file=sys.stderr)
        return 2
    if "{{" in content:
        print("FAIL: replace all {{ placeholders; fix and re-run this command.", file=sys.stderr)
        return 1
    report = ReportParser()
    report.feed(content)
    if report.script_in_panel:
        print("FAIL: escape script markup inside panels; fix and re-run this command.", file=sys.stderr)
        return 1
    panels = {node["attrs"].get("data-tab"): node for node in report.elements
              if "panel" in (node["attrs"].get("class") or "").split()}
    enabled = [node for node in report.elements
               if node["attrs"].get("role") == "tab" and "disabled" not in node["attrs"]]
    if not enabled:
        print("FAIL: enable at least one populated stage tab; fix and re-run this command.", file=sys.stderr)
        return 1
    for node in enabled:
        attrs = node["attrs"]
        if attrs.get("role") == "tab" and "disabled" not in attrs:
            name = attrs.get("data-tab")
            if name not in panels or not panel_text(panels[name]).strip():
                print(f"FAIL: populate enabled tab {name!r}; fix and re-run this command.", file=sys.stderr)
                return 1
    print("PASS: inspect the rendered report before presenting it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
