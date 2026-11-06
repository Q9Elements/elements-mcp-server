#!/usr/bin/env python3
"""Join saved tool reply parts into one verified local file."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Resolve shipped sibling modules when invoked with python3 -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from source_files import _fetch


class PartError(ValueError):
    """A safe diagnostic and exit code for a refused join."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def join(replies: Path, out: Path) -> dict:
    saved = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(
        replies.glob("*.json"), key=lambda path: int(path.stem))]
    kept = []
    group = None
    previous_status = None
    for item in saved:
        reply = item["reply"]
        if "resultId" not in reply and "error" in reply:
            continue
        key = (reply["resultId"], reply.get("computedAt"))
        if (group is None or key[0] != group[0]
                or (reply["status"] == "running" and previous_status == "complete")
                or (key[1] is not None and group[1] is not None and key[1] != group[1])):
            kept = []
        group = key
        previous_status = reply["status"]
        kept.append(item)
    if any(item["reply"].get("status") == "failed" or item["reply"].get("failed")
           or item["reply"].get("failedTotal") is not None
           for item in kept):
        raise PartError(4, "result contains failed items")
    final_reply = saved[-1]["reply"] if saved else None
    if (not kept or kept[-1]["reply"]["status"] != "complete"
            or (final_reply is not None and "resultId" not in final_reply
                and "error" in final_reply)):
        raise PartError(2, "incomplete result; collect a final complete reply")
    parts = {}
    for item in kept:
        for part in item["reply"]["parts"]:
            previous = parts.get(part["index"])
            if previous and previous["sha256"] != part["sha256"]:
                raise PartError(5, "conflicting checksums for a repeated part index")
            parts[part["index"]] = part
    saved_at = {part["index"]: datetime.fromisoformat(item["savedAt"].replace("Z", "+00:00")).timestamp()
                for item in kept for part in item["reply"]["parts"]}
    final = kept[-1]["reply"]
    if "nextPartsFrom" in final:
        raise PartError(2, "incomplete paging; collect the remaining replies")
    if set(parts) != set(range(final["partsTotal"])):
        raise PartError(2, "incomplete part indices")
    if any(part["format"] != "ndjson" for part in parts.values()):
        raise PartError(5, "unsupported part format; expected NDJSON")
    if any(time.time() >= saved_at[index] + part["expiresInSeconds"]
           for index, part in parts.items()):
        raise PartError(3, "part expired; make the identical call again")
    chunks = []
    for index in sorted(parts):
        part = parts[index]
        chunk = _fetch(part["url"])
        if len(chunk) != part["bytes"]:
            raise PartError(5, "part byte count mismatch")
        if hashlib.sha256(chunk).hexdigest() != part["sha256"]:
            raise PartError(5, "part checksum mismatch")
        chunks.append(chunk)
    data = b"".join(chunks)
    if len(data.splitlines()) != final["totalRows"]:
        raise PartError(5, "joined row count mismatch")
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(out)
    return {"parts": len(parts), "rows": len(data.splitlines()), "bytes": len(data)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("join")
    command.add_argument("--replies", type=Path, required=True)
    command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(join(args.replies, args.out)))
        return 0
    except PartError as error:
        print(f"part_files: {error}", file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        print("part_files: invalid reply, download or file integrity error", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
