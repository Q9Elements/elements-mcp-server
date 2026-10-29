"""Rank search_metadata hits and resolve field names from a held field file."""

import re
from tool_reply import unwrap_reply
from cli_common import normalize_type, field_object, types_match


def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def query_forms(name):
    """Search forms for the caller to group by implied synced type."""
    bare = str(name).rsplit(".", 1)[-1]
    cleaned = re.sub(r"__c$", "", bare, flags=re.IGNORECASE)
    split_camel = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", cleaned)
    words = re.sub(r"[^A-Za-z0-9]+", " ", split_camel).strip()
    parts = words.split()
    stems = [form for size in range(len(parts) - 2, 2, -1)
             for form in ("_".join(parts[:size]), " ".join(parts[:size]))]
    substring = " ".join(parts[-2:]) if len(parts) > 2 else words
    return list(dict.fromkeys(form.strip() for form in (name, bare, words, "_".join(parts), *stems, substring)
                              if len(form.strip()) >= 2))


def _match(request, candidates):
    wanted = request.get("apiName") or request.get("name") or ""
    kind = normalize_type(request)
    candidates = [row for row in candidates if not kind or types_match(kind, row)]
    parent = field_object(request)
    if parent:
        candidates = [row for row in candidates if field_object(row) == parent]
    def score(row):
        names = [row.get("apiName"), row.get("api_name"), row.get("name")]
        if wanted in names:
            return 3
        if _key(wanted) in [_key(name) for name in names]:
            return 2
        forms = query_forms(wanted)
        substring = _key(forms[-1]) if forms else ""
        if len(substring) >= 5 and any(substring in _key(name) for name in names if name):
            return 1
        return 0
    best = max((score(row) for row in candidates), default=0)
    matches = [row for row in candidates if score(row) == best] if best else []
    return matches[0] if len(matches) == 1 else None


def resolve_names(targets, hits, *, fields=(), entry_fields=(), written_fields=(), mode="resolve"):
    """Return resolved targets and delta fields, retaining misses for confirmation."""
    if mode == "forms":
        names = [name for request in list(targets) + list(entry_fields) + list(written_fields)
                 for name in ((request.get("name"), request.get("apiName")) if isinstance(request, dict)
                              else (request,)) if name]
        return {"forms": list(dict.fromkeys(form for name in names if name for form in query_forms(name)))}
    if mode != "resolve":
        raise ValueError("mode must be forms or resolve")
    if isinstance(hits, dict):
        hits = unwrap_reply(hits).get("nodes")
    if not isinstance(hits, list):
        raise ValueError("hits must be a row list or a search result with nodes")
    result = {"targets": [], "entry_fields": [], "written_fields": [], "unresolved": []}
    for section, requests, candidates in (("targets", targets, hits),
                                           ("entry_fields", entry_fields, fields or hits),
                                           ("written_fields", written_fields, fields or hits)):
        for request in requests:
            item = request if isinstance(request, dict) else {"name": request, "sfType": "Field"}
            name = item.get("name") or item.get("apiName") or ""
            if section != "targets":
                item = {**item, "sfType": "Field"}
                if "." in name:
                    object_name, field_name = name.split(".", 1)
                    candidates_for_name = [row for row in candidates if field_object(row) == object_name]
                    item["name"] = field_name
                else:
                    candidates_for_name = candidates
            else:
                candidates_for_name = candidates
            match = _match(item, candidates_for_name)
            if match is None and section != "targets" and fields:
                match = _match(item, hits)
            if match:
                result[section].append(match)
            else:
                result["unresolved"].append({"section": section, "name": name})
    return result


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("resolve_names"))
