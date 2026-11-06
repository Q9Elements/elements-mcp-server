#!/usr/bin/env python3
"""## Contents
- Command-line download and verification of get_access file parts.

Usage: python3 fetch_parts.py REPLY.json OUTPUT_DIRECTORY
Input is a parsed reply object, a JavaScript Object Notation (JSON) text block, or parts.
Uniform resource locators (URLs) use Hypertext Transfer Protocol (HTTP)
or its secure form (HTTPS).
Exit actions: 0 verified, 1 mismatch, 2 refresh links, 3 continue or resolve evidence.
"""

import argparse
import csv
import http.client
import io
import hashlib
import json
import math
import re
from pathlib import Path
import urllib.request
import urllib.parse
import time


NETWORK_TIMEOUT = 30  # Bound socket waits independently of returned link validity.
PART_FIELDS = ("sha256", "bytes", "rows", "format")  # Compare content independently of refreshed links.


def validate_parts(parts):
    if not isinstance(parts, list):
        raise ValueError("parts must be a list")
    seen = set()
    for part in parts:
        for key in ("index", "rows", "bytes"):
            if type(part[key]) is not int or part[key] < 0:
                raise ValueError(f"invalid {key}")
        if part["index"] in seen:
            raise ValueError("duplicate part index")
        seen.add(part["index"])
        if part["format"] not in ("ndjson", "csv"):
            raise ValueError("invalid part format")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", part["sha256"]):
            raise ValueError("invalid digest")
        expiry = part["expiresInSeconds"]
        if type(expiry) not in (int, float) or not math.isfinite(expiry):
            raise ValueError("invalid returned expiry")
        if urllib.parse.urlsplit(part["url"]).scheme not in ("http", "https"):
            raise ValueError("part URL must use HTTP or HTTPS")


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


def acquire(reply, output, age=0):
    started = time.monotonic()
    if isinstance(reply, dict) and "content" in reply:
        texts = [item["text"] for item in reply["content"] if item.get("type") == "text"]
        if len(texts) != 1:
            raise ValueError("save one parsed tool reply")
        reply = json.loads(texts[0])
    if isinstance(reply, list):
        reply = {"parts": reply}
    if reply.get("isError") or reply.get("status") == "failed" or reply.get("error"):
        return 3, "Acquisition stopped: " + json.dumps(reply) + "; read references/refusals.md and re-request an actionable result."
    validate_parts(reply["parts"])
    for key in ("totalRows", "partsTotal", "nextPartsFrom", "failedTotal"):
        if key in reply and (type(reply[key]) is not int or reply[key] < 0):
            raise ValueError(f"invalid {key}")
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / "acquisition.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"parts": {}}
    validate_parts(list(state["parts"].values()))
    changed = state.get("resultId") != reply.get("resultId")
    changed |= bool(state.get("computedAt") and reply.get("computedAt")
                    and state["computedAt"] != reply["computedAt"])
    for part in reply["parts"]:
        old = state["parts"].get(str(part["index"]))
        changed |= bool(old and any(old[k] != part[k] for k in PART_FIELDS))
    if changed:
        for old in state["parts"].values():
            (output / f'part-{old["index"]}.{old["format"]}').unlink(missing_ok=True)
        state = {"parts": {}}
    state["resultId"] = reply.get("resultId")
    state["computedAt"] = reply.get("computedAt") or state.get("computedAt")
    provenance = state.setdefault("provenance", {})
    saved = state["parts"]
    errors = []
    for key, part in list(saved.items()):
        path = output / f'part-{part["index"]}.{part["format"]}'
        data = path.read_bytes() if path.exists() else b""
        if len(data) != part["bytes"] or hashlib.sha256(data).hexdigest() != part["sha256"]:
            del saved[key]
    for part in reply["parts"]:
        old = saved.get(str(part["index"]))
        if old and all(old[k] == part[k] for k in PART_FIELDS):
            provenance[str(part["index"])] = reply_provenance(reply)
            continue
        remaining = part["expiresInSeconds"] - age - (time.monotonic() - started)
        if remaining <= 0:
            errors.append((2, "Link expired: repeat the same get_access read for fresh links and rerun."))
            continue
        try:
            with urllib.request.urlopen(part["url"], timeout=min(NETWORK_TIMEOUT, remaining)) as response:
                data = response.read()
        except (OSError, http.client.HTTPException):
            errors.append((2, "Fetch failed or link expired: repeat the same get_access read for fresh links and rerun."))
            continue
        if len(data) != part["bytes"] or hashlib.sha256(data).hexdigest() != part["sha256"]:
            errors.append((1, "Verification mismatch: re-request the same get_access read and rerun."))
            continue
        count = (max(0, sum(1 for _ in csv.reader(io.StringIO(data.decode("utf-8"), newline=""))) - 1)
                 if part["format"] == "csv" else len(data.split(b"\n")) - int(not data or data.endswith(b"\n")))
        if count != part["rows"]:
            errors.append((1, "Row count mismatch: re-request the same get_access read and rerun."))
            continue
        (output / f'part-{part["index"]}.{part["format"]}').write_bytes(data)
        saved[str(part["index"])] = part
        provenance[str(part["index"])] = reply_provenance(reply)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    rows = sum(part["rows"] for part in saved.values())
    evidence = {k: reply[k] for k in ("failed", "failedTotal", "failedFile") if k in reply}
    if evidence:
        print(json.dumps(evidence, ensure_ascii=True))
    if errors:
        return min(errors)
    if "status" not in reply:
        return 3, "Parts verified: supply the final envelope to check partsTotal and totalRows, then rerun."
    if "nextPartsFrom" in reply:
        return 3, f"Continue: call get_access with partsFrom {reply['nextPartsFrom']} and rerun."
    if reply.get("status") == "running":
        return 3, f"Continue: repeat get_access after retryAfterSeconds={reply.get('retryAfterSeconds')} and rerun."
    final = (reply.get("status") == "complete" and bool(reply.get("computedAt"))
             and all(type(reply.get(k)) is int for k in ("partsTotal", "totalRows", "batchesDone", "batchesTotal"))
             and reply["batchesDone"] == reply["batchesTotal"])
    if not final:
        return 3, "Coverage incomplete: re-request get_access for a final complete envelope and rerun."
    if {p["index"] for p in saved.values()} != set(range(reply["partsTotal"])):
        return 3, "Coverage incomplete: missing parts; re-request get_access from the first missing partsFrom index and rerun."
    unconfirmed = next((index for index in range(reply["partsTotal"])
                        if not matches_completion(state, str(index), reply)), None)
    if unconfirmed is not None:
        return 3, (f"Coverage incomplete: call get_access with partsFrom {unconfirmed} "
                   "to confirm completed descriptors and rerun.")
    if rows != reply["totalRows"]:
        return 1, "Total row count mismatch: re-request the same get_access read and rerun."
    if reply.get("failedTotal", len(reply.get("failed", []))) > len(reply.get("failed", [])):
        return 3, "Failure coverage incomplete: inspect failedFile; if unavailable, re-request the same read and report the gap."
    return 0, f"Complete: {len(saved)} parts, {rows} rows verified; inspect failures before reporting."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reply", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        code, message = acquire(json.loads(args.reply.read_text(encoding="utf-8")), args.output,
                                max(0, time.time() - args.reply.stat().st_mtime))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        code, message = 1, f"Input or local storage mismatch ({error}): save a valid reply and use a writable dedicated output directory, then rerun."
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
