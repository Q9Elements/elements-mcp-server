#!/usr/bin/env python3
"""Download and verify native part files using Python 3's standard library.

Files contain JavaScript Object Notation (JSON) in newline-delimited form (NDJSON) or
comma-separated values (CSV).

Usage: python3 scripts/fetch_parts.py -o OUTPUT PAGE.json [PAGE.json ...]

Exit codes and next actions:
  0: Complete and verified; present rows and reported coverage.
  1: Input, job or verification mismatch; correct the reported issue and rerun.
  2: Link/fetch failure; repeat the same read call for fresh links and rerun.
  3: Running or missing parts; follow the printed cursor/wait instruction and rerun.
"""

import argparse
import csv
import hashlib
from http.client import HTTPException
import io
import json
from pathlib import Path
import re
import sys
from urllib.request import urlopen


# Bound stalled downloads so the caller can refresh links rather than hang.
FETCH_TIMEOUT = 30
# The native-file contract supplies this polling fallback when its hint is absent.
POLL_FALLBACK = 30


class FetchError(Exception):
    """A fresh descriptor can repair a failed download."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(f"{message}; run with --help for usage")


def nonnegative(value):
    if type(value) is not int or value < 0:
        raise ValueError("expected a nonnegative integer")


def validate_page(page):
    if not isinstance(page, dict) or page.get("status") not in ("running", "complete", "failed"):
        raise ValueError("save a parsed, hydrated native page response with a valid status")
    if page["status"] == "failed":
        raise ValueError(f"job failed: {page.get('error')} {page.get('message', '')}; narrow or retry the read")
    if not isinstance(page.get("resultId"), str) or not page["resultId"]:
        raise ValueError("missing resultId; save the complete page response")
    for key in ("partsTotal", "totalRows"):
        nonnegative(page[key])
    if not isinstance(page["parts"], list):
        raise ValueError("hydrate parts into an array")
    indices = set()
    for descriptor in page["parts"]:
        nonnegative(descriptor["index"])
        if descriptor["index"] >= page["partsTotal"] or descriptor["index"] in indices:
            raise ValueError("part index outside partsTotal or duplicated")
        indices.add(descriptor["index"])


def validate_descriptor(descriptor):
    if descriptor["format"] not in ("ndjson", "csv"):
        raise ValueError("unsupported format; use ndjson or csv")
    for key in ("rows", "bytes", "expiresInSeconds"):
        nonnegative(descriptor[key])
    if not re.fullmatch(r"[0-9a-fA-F]{64}", descriptor["sha256"]):
        raise ValueError("invalid sha256; save the returned descriptor")
    if not isinstance(descriptor["url"], str):
        raise ValueError("missing url; repeat the read for fresh links")


def verify(body, descriptor):
    if len(body) != descriptor["bytes"]:
        raise ValueError("byte count mismatch")
    if hashlib.sha256(body).hexdigest() != descriptor["sha256"]:
        raise ValueError("sha256 mismatch")
    text = body.decode("utf-8")
    if descriptor["format"] == "csv":
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
        count = len(rows) - 1
    elif descriptor["format"] == "ndjson":
        count = len(text.split("\n")) - int(not text or text.endswith("\n"))
    else:
        raise ValueError("unsupported format; use ndjson or csv")
    if count != descriptor["rows"]:
        raise ValueError("row count mismatch")


def acquire(descriptor, path):
    validate_descriptor(descriptor)
    if path.exists():
        body = path.read_bytes()
        try:
            verify(body, descriptor)
            return body
        except ValueError:
            pass
    try:
        with urlopen(descriptor["url"], timeout=FETCH_TIMEOUT) as response:
            body = response.read()
    except (OSError, HTTPException) as error:
        raise FetchError(str(error)) from error
    verify(body, descriptor)
    path.write_bytes(body)
    return body


def reply_provenance(reply):
    """Keep the identity of the reply that verified a part's descriptor."""
    return {key: reply.get(key) for key in ('resultId', 'status', 'computedAt')}


def matches_completion(state, key, reply):
    """Require a completed descriptor, with identity for reuse across replies."""
    origin = state.get('provenance', {}).get(key, {})
    if origin.get('status') != 'complete' or origin.get('resultId') != reply.get('resultId'):
        return False
    if reply.get('computedAt'):
        return origin.get('computedAt') == reply['computedAt']
    # Without a completion identity, only this reply can attest its own parts.
    return any(str(part['index']) == key for part in reply['parts'])


def run(paths, output):
    output.mkdir(parents=True, exist_ok=True)
    for name in ("rows.ndjson", "rows.csv"):
        (output / name).unlink(missing_ok=True)
    state_path = output / ".acquisition.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"parts": {}}
    for source in paths:
        page = json.loads(source.read_text(encoding="utf-8"))
        validate_page(page)
        changed = state.get("resultId") != page["resultId"]
        changed |= bool(state.get("computedAt") and page.get("computedAt")
                        and state["computedAt"] != page["computedAt"])
        changed |= any(str(d["index"]) in state["parts"] and
                       any(state["parts"][str(d["index"])][key] != d[key]
                           for key in ("sha256", "bytes", "rows", "format"))
                       for d in page["parts"])
        if changed:
            for pattern in ("part-*.ndjson", "part-*.csv", "failed.ndjson"):
                for held in output.glob(pattern):
                    held.unlink()
            state = {"parts": {}}
        state["resultId"] = page["resultId"]
        if page.get("computedAt"):
            state["computedAt"] = page["computedAt"]
        provenance = state.setdefault("provenance", {})
        for descriptor in page["parts"]:
            validate_descriptor(descriptor)
            path = output / ("part-" + str(descriptor["index"]) + "." + descriptor["format"])
            acquire(descriptor, path)
            state["parts"][str(descriptor["index"])] = descriptor
            provenance[str(descriptor["index"])] = reply_provenance(page)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        failures = page.get("failed", [])
        failed_total = page.get("failedTotal", len(failures))
        if page.get("failedFile"):
            body = acquire(page["failedFile"], output / "failed.ndjson")
            failures = [json.loads(line) for line in body.decode("utf-8").split("\n") if line]
        else:
            (output / "failed.ndjson").unlink(missing_ok=True)
        if len(failures) != failed_total:
            raise ValueError("incomplete failure details; repeat the same read to retrieve failedFile")
        print(f"failedTotal={failed_total}; failed={json.dumps(failures)}")
    if page.get("nextPartsFrom") is not None:
        wait = (f" after retryAfterSeconds {page.get('retryAfterSeconds', POLL_FALLBACK)}"
                if page["status"] == "running" else "")
        print(f"Call again with partsFrom {page['nextPartsFrom']}{wait} and identical selection; save the reply and rerun.")
        return 3
    if page["status"] == "running":
        print(f"Call again after retryAfterSeconds {page.get('retryAfterSeconds', POLL_FALLBACK)}; save the reply and rerun.")
        return 3
    for index in range(page["partsTotal"]):
        if str(index) not in state["parts"] or not matches_completion(state, str(index), page):
            print(f"Call again with partsFrom {index} and identical selection; save the reply and rerun.")
            return 3
    bodies = []
    header = None
    fmt = None
    for index in range(page["partsTotal"]):
        descriptor = state["parts"][str(index)]
        if fmt and fmt != descriptor["format"]:
            raise ValueError("part format mismatch")
        fmt = descriptor["format"]
        body = acquire(descriptor, output / ("part-" + str(index) + "." + fmt))
        if fmt == "csv":
            stream = io.StringIO(body.decode("utf-8"), newline="")
            reader = csv.reader(stream, strict=True)
            current = next(reader)
            if header is not None:
                if current != header:
                    raise ValueError("CSV header mismatch")
                body = stream.read().encode("utf-8")
            header = current
        bodies.append(body)
    if sum(state["parts"][str(i)]["rows"] for i in range(page["partsTotal"])) != page["totalRows"]:
        raise ValueError("completed totalRows mismatch")
    joined = "rows." + (fmt or "ndjson")
    (output / joined).write_bytes(b"".join(bodies))
    coverage = "partial coverage" if failed_total else "reported coverage"
    print(f"Complete and verified; present {joined} and {coverage}.")
    return 0


def main():
    parser = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("pages", nargs="+", type=Path)
    try:
        args = parser.parse_args()
        return run(args.pages, args.output)
    except FetchError as error:
        print(f"Fetch failed: {error}; repeat the same read call for fresh links and rerun.", file=sys.stderr)
        return 2
    except (ValueError, KeyError, TypeError, OSError, csv.Error, StopIteration) as error:
        print(f"Mismatch: {error}; correct the input or downloaded files and rerun.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
