"""Save a data-load impact bundle under an engagement work directory."""

import hashlib
import io
import json
import re
import shutil
import sys
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from zipfile import BadZipFile, ZipFile

from cli_common import SingleLineParser


class HTTPSRedirectHandler(HTTPRedirectHandler):
    """Keep downloads on Hypertext Transfer Protocol Secure (HTTPS)."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise ValueError("download redirects must use HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


urlopen = build_opener(HTTPSRedirectHandler()).open


def fetch_bundle(envelope, work, refetch=None):
    """Download a complete zip; refetch() repeats the original tool arguments."""
    current = envelope
    for attempt in range(2):
        if current.get("status") != "complete":
            raise ValueError(f"bundle status: {current.get('status')}")
        if current.get("tool", "run_data_load_impact") != "run_data_load_impact":
            raise ValueError("fetch_bundle accepts run_data_load_impact zips only")
        if not re.fullmatch(r"[0-9a-fA-F]+", str(current.get("jobId", ""))):
            raise ValueError("unsafe jobId: expected hex")
        url = current["bundleUrl"]
        if urlsplit(url).scheme != "https":
            raise ValueError("bundleUrl must use HTTPS")
        try:
            with urlopen(url, timeout=30) as response:
                content = response.read()
        except urllib.error.HTTPError as error:
            if attempt or refetch is None or error.code not in (401, 403):
                raise
            current = refetch()
            continue
        actual = hashlib.sha256(content).hexdigest()
        if actual.lower() == current["bundleSha256"].lower():
            break
        if attempt or refetch is None:
            raise ValueError("bundle SHA-256 does not match")
        current = refetch()
    destination = Path(work) / current["jobId"]
    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(io.BytesIO(content)) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("unsafe bundle member path")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
    manifest_path = destination / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else
                {"coverage": json.loads((destination / "coverage.json").read_text(encoding="utf-8"))})
    return {"path": destination, "manifest": manifest, "envelope": current}


def main(argv=None):
    parser = SingleLineParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--job-id", "--result-id", dest="job_id")
    args = parser.parse_args(argv)
    try:
        envelope = {"bundleUrl": args.url, "bundleSha256": args.sha256,
                    "jobId": args.job_id or args.sha256, "status": "complete", "tool": "run_data_load_impact"}
        result = fetch_bundle(envelope, args.work)
        name = "manifest.json" if (result['path'] / "manifest.json").exists() else "coverage.json"
        print(f"bundle: {result['path']} {name}: {result['path'] / name}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError, BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
