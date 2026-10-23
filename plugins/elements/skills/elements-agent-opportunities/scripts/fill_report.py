#!/usr/bin/env python3
"""Fill a local HyperText Markup Language (HTML) report and its replay digest.

Usage: python3 fill_report.py templates/report.html values.json output_directory
Values use JavaScript Object Notation (JSON); DIGEST holds the complete Markdown replay text.
Exit 0: open the populated report. Exit 2: fix named inputs and rerun until it passes.
The generatedAt header uses the system clock in Coordinated Universal Time (UTC).
"""
import argparse
from datetime import datetime, timezone
from html import escape
import math
from pathlib import Path
import json
import re
import sys

PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")  # Template keys use uppercase names.


class ActionParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}; run {self.prog} --help, fix arguments and rerun")


def main():
    parser = ActionParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("values", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    template = re.sub(r"(<!doctype html>\s*)<!--.*?-->\s*", r"\1",
                      args.template.read_text(), count=1, flags=re.S | re.I)
    values = json.loads(args.values.read_text())
    if not isinstance(values, dict):
        raise ValueError("values.json must contain an object")
    keys = set(PLACEHOLDER.findall(template))
    errors = [f"Missing {key}" for key in sorted((keys | {"DIGEST"}) - values.keys())]
    errors += [f"Unknown {key}" for key in sorted(values.keys() - keys - {"DIGEST"})]
    for key, value in values.items():
        optional_name = re.fullmatch(r"F[123]_NAME", key)
        if (isinstance(value, bool) or not isinstance(value, (str, int, float))
                or isinstance(value, float) and not math.isfinite(value)
                or not str(value).strip() and not optional_name):
            errors.append(f"Invalid or empty {key}: supply text or a number")
    rendered = PLACEHOLDER.sub(lambda match: (str(values.get(match[1], match[0]))
                              if match[1].endswith("_HTML") else
                              escape(str(values.get(match[1], match[0])))), template)
    errors += [f"Leftover {token}" for token in sorted(set(re.findall(r"\{\{.*?\}\}",
               rendered + str(values.get("DIGEST", "")), flags=re.S)))]
    if errors:
        raise ValueError("; ".join(errors))
    rendered = re.sub(r'<button\b[^>]*data-tab="f[123]"[^>]*>',
                      lambda match: (re.sub(r"\s+disabled\b", "", match[0])
                                     if values.get(re.search(r'data-tab="(f[123])"',
                                                   match[0])[1].upper() + "_NAME") else match[0]), rendered)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "agent-opportunities.html").write_text(rendered, encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (args.output_directory / "agent-opportunities.md").write_text(
        f"generatedAt: {stamp}\n\n{values['DIGEST']}\n", encoding="utf-8")
    print(f"PASS: Open {args.output_directory / 'agent-opportunities.html'} and present the digest.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: {exc}; fix the inputs and rerun fill_report.py until it passes.", file=sys.stderr)
        sys.exit(2)
