"""The resumable write loop: the next step to carry to Elements, preflights, library batches, saved results and id maps.

Part of the shared layout engine (see __init__.py). Standard library only; Python 3.8 or later.
"""

from mcp_result import map_name, hydrate, bind_step, write_complete, write_recovery

import hashlib
import json
import re
from pathlib import Path
from attachment_scope import unscoped_attachment_stop

from .base import MAX_CHANGES, NEW_NAMES_PER_CHANGE, PlanError, TOP, chunk, norm, read_json, slug
from .reads import REVIEW_INCLUDE, expected_content, saved_read_problems


PREFLIGHT_BOX_RESOURCES = 25   # a box is 100 + 24 px per resource tall; past about 45 it leaves a blank level's 1,200 px canvas


def preflight_batches(levels, model, per_box=PREFLIGHT_BOX_RESOURCES):
    """Dry-run batches that add every distinct resource and library attachment once, to throwaway boxes.

    Sent with dryRun only and without createResources, before any real write, so a missing resource, a
    resource whose library type refuses its RASCI, or an attachment the space cannot resolve shows up before
    the map is half drawn. An object whose entity has an API name other than its name is also probed under
    that API name ("aliases": change index -> the name it stands for), because some libraries hold objects
    by API name (Pricebook2) and adding the label as a new name would duplicate it. Each box carries at most
    per_box resources (PREFLIGHT_BOX_RESOURCES unless the caller says otherwise) so it stays inside the canvas."""
    api_names = {norm(e["name"]): e["apiName"] for e in model.get("entities", [])
                 if e.get("apiName") and norm(e["apiName"]) != norm(e["name"])}
    seen, items = set(), []
    for level in levels:
        for batch in level["batches"]:
            for change in batch["changes"]:
                if change["kind"] == "resource":
                    key = ("resource", norm(change["name"]))
                elif change["kind"] == "attachment" and change["type"] in ("metadata", "story"):
                    key = ("attachment", change["type"], change.get("apiName"), change.get("metadataType"), change.get("refModelId"), change.get("storyId"))
                else:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                items.append(({k: v for k, v in change.items() if k != "activity"}, None))
                if change["kind"] == "resource" and change["type"] == "Object" and norm(change["name"]) in api_names:
                    alias = api_names[norm(change["name"])]
                    if ("resource", norm(alias)) not in seen:
                        seen.add(("resource", norm(alias)))
                        items.append(({"op": "add", "kind": "resource", "name": alias, "type": "Object"}, change["name"]))
    batches, current = [], None
    box_resources = 0
    for item, stands_for in items:
        is_resource = item["kind"] == "resource"
        needs_box = current is None or (is_resource and box_resources >= per_box)
        if current is not None and len(current["changes"]) + (2 if needs_box else 1) > MAX_CHANGES:
            current, needs_box = None, True
        if current is None:
            current = {"changes": [], "aliases": {}}
            batches.append(current)
        if needs_box:
            boxes = sum(1 for c in current["changes"] if c["kind"] == "activity")
            current["changes"].append({"op": "add", "kind": "activity", "ref": f"preflight{boxes + 1}",
                                       "text": "Preflight check", "position": {"x": 200 * boxes, "y": 0}})
            box_resources = 0
        box = f"preflight{sum(1 for c in current['changes'] if c['kind'] == 'activity')}"
        if stands_for is not None:
            current["aliases"][str(len(current["changes"]))] = stands_for
        current["changes"].append(dict(item, activity=box))
        box_resources += 1 if is_resource else 0
    return batches


def level_results(workdir, slug):
    folder = workdir / "results" / slug
    results = {}
    if folder.is_dir():
        for path in folder.glob("*.json"):
            try:
                results[int(path.stem)] = read_json(path)
            except (ValueError, json.JSONDecodeError) as exc:
                raise PlanError(f"{path}: cannot read the saved result ({exc})")
    return results


def id_map(results):
    merged = {}
    for number in sorted(results):
        merged.update(results[number].get("idMap", {}))
    return merged


def lines_of(read):
    diagram = read.get("diagram", read)
    return diagram.get("lines", [])


def resolve(changes, own_refs, keys, boundary_keys, parent_line_keys=None):
    def key_for(ref):
        if ref in own_refs:
            return ref
        if ref not in keys:
            raise PlanError(f"a change refers to '{ref}', which no saved result created; save every earlier batch's result first")
        return keys[ref]

    resolved = []
    for change in changes:
        change = json.loads(json.dumps(change))
        if isinstance(change.get("activity"), str):
            change["activity"] = key_for(change["activity"])
        for end in ("from", "to"):
            if isinstance(change.get(end), dict) and isinstance(change[end].get("activity"), str):
                change[end]["activity"] = key_for(change[end]["activity"])
        if isinstance(change.get("key"), dict) and "$seeded" in change["key"]:
            ref = change["key"]["$seeded"]
            if ref not in boundary_keys:
                continue   # add child seeded no copy of this parent line, so there is nothing to remove
            change["key"] = boundary_keys[ref]
        elif isinstance(change.get("key"), dict):
            ref = change["key"]["$boundary"]
            if ref not in boundary_keys:
                raise PlanError(f"no seeded child line continues the parent line '{ref}'; read the child level again")
            change["key"] = boundary_keys[ref]
        if isinstance(change.get("parentLine"), dict):
            ref = change["parentLine"]["$parentLine"]
            if ref not in (parent_line_keys or {}):
                raise PlanError(f"the parent level's saved results have no key for the line '{ref}'; finish the parent level first")
            change["parentLine"] = parent_line_keys[ref]
        resolved.append(change)
    return resolved


PATH_INDEX = re.compile(r"^changes\[(\d+)\]")


def change_index(issue):
    match = PATH_INDEX.match(issue.get("path") or "")
    return int(match.group(1)) if match else None


def preflight_current(saved, the_plan):
    """A saved preflight result counts only for the plan and the plan's attempt it was made for (see
    base.prepare_workdir): a result from an earlier attempt is asked for again."""
    return (saved is not None and saved.get("planId") == the_plan["planId"]
            and saved.get("attempt", 1) == the_plan.get("attempt", 1))


# Metadata a box may link to only when its name is unique in the org: manage_diagram attaches metadata by
# API name, and a picklist value ("New") or a record type ("Standard") often shares its name with others.
BY_NAME_ONLY = ("Custom Value", "Record Type")


def unlinkable_issue(issue, batch, any_type=False):
    """A preflight error that only says such an attachment cannot be resolved by its name. Only the BY_NAME_ONLY
    types count, unless the plan drops every attachment that does not resolve (dropUnresolved: any_type)."""
    index = change_index(issue)
    if issue.get("code") not in ("metadata_ambiguous", "metadata_not_found") or index is None or index >= len(batch["changes"]):
        return None
    change = batch["changes"][index]
    if change.get("kind") == "attachment" and change.get("type") == "metadata" and (any_type or change.get("metadataType") in BY_NAME_ONLY):
        return (change["apiName"], change.get("metadataType"))
    return None


def unlinkable(workdir, the_plan):
    """The (apiName, metadataType) attachments the preflight could not resolve by name; the write batches
    leave them out (the box's note still names the value)."""
    found = set()
    any_type = bool(the_plan.get("dropUnresolved"))
    for number, batch in enumerate(the_plan.get("preflight", []), start=1):
        path = workdir / "preflight" / f"{number}.json"
        saved = read_json(path) if path.exists() else None
        if preflight_current(saved, the_plan):
            found |= {key for key in (unlinkable_issue(i, batch, any_type) for i in saved.get("issues", [])) if key}
    return found


def drop_unlinkable(changes, skip):
    return [c for c in changes if not (c.get("kind") == "attachment" and c.get("type") == "metadata"
                                       and (c.get("apiName"), c.get("metadataType")) in skip)]


def preflight_findings(workdir, the_plan):
    """Read the saved preflight results. Returns (missing, renames, blocking) or None while one is unsaved:
    missing  - resources the library lacks, as [{"name", "type"}], in plan order;
    renames  - [{"name", "libraryName"}] where the library lacks a name but holds its entity's API name as an
               Object (an API name it holds under another type, such as Contact as a person, does not count);
    blocking - every other error issue."""
    missing, found_aliases, blocking, not_found = [], {}, [], set()
    for number, batch in enumerate(the_plan.get("preflight", []), start=1):
        path = workdir / "preflight" / f"{number}.json"
        saved = read_json(path) if path.exists() else None
        if not preflight_current(saved, the_plan):
            return None
        aliases = batch.get("aliases", {})
        missed = set()
        for issue in saved.get("issues", []):
            index = change_index(issue)
            if issue.get("code") == "resource_type_differs" and index is not None and str(index) in aliases:
                missed.add(index)   # the library holds the API name, but not as an Object
            elif issue.get("code") == "resource_not_found" and index is not None and index < len(batch["changes"]):
                missed.add(index)
                if str(index) in aliases:
                    continue
                change = batch["changes"][index]
                if norm(change["name"]) not in not_found:
                    not_found.add(norm(change["name"]))
                    missing.append({"name": change["name"], "type": change["type"], "issue": issue})
            elif issue.get("severity") == "error" and not unlinkable_issue(issue, batch, bool(the_plan.get("dropUnresolved"))):
                blocking.append(issue)
        for index, stands_for in aliases.items():
            if int(index) not in missed:
                found_aliases[norm(stands_for)] = batch["changes"][int(index)]["name"]
    renames = [{"name": m["name"], "libraryName": found_aliases[norm(m["name"])]} for m in missing if norm(m["name"]) in found_aliases]
    missing = [m for m in missing if norm(m["name"]) not in found_aliases]
    return missing, renames, blocking


LIBRARY_TYPE = re.compile(r" is (.+?) in the space library")
CHECKS_LIBRARY_TYPES = ("process", "journey")   # diagram types whose fix-preflight shows library types and type clashes


def library_type(issue):
    """The type a resource_type_differs issue says the space library holds the name under ("Partner is Human in
    the space library, not Object; that one is used.")."""
    match = LIBRARY_TYPE.search(issue.get("message") or "")
    return match.group(1) if match else None


def close_matches(issue):
    """The names a resource_not_found issue offers ("... Close matches: A, B, C. To add it to the space library ..."),
    in its order. The server lists names only, so their library types come from a second dry run (match_probe)."""
    message = issue.get("message") or ""
    at = message.find("Close matches:")
    if at < 0:
        return []
    text = message[at + len("Close matches:"):]
    end = text.rfind(". To add")
    text = text[:end] if end >= 0 else text.rstrip().rstrip(".")
    return [name.strip() for name in text.split(", ") if name.strip()]


OBJECT_SUFFIX = " (object)"
OBJECT_SUFFIX_WITH_API = re.compile(r" \(object, [^()]*\)$")


def object_rename(name, alias, alias_usable):
    """The name an object is drawn under when the library holds its name under another type, in this order: its
    API name (alias: the API name the preflight probed, usable when the library does not hold that under another
    type too); else "<name> (object)"; else, when that clashes as well, "<name> (object, <API name>)". Each
    rename goes through another preflight, so a name that clashes again moves to the next form. None when no
    form is left (no API name, or the last form clashes too)."""
    if alias and alias_usable:
        return alias
    if name.endswith(OBJECT_SUFFIX):
        return f"{name[:-len(OBJECT_SUFFIX)]} (object, {alias})" if alias else None
    if OBJECT_SUFFIX_WITH_API.search(name):
        return None
    return name + OBJECT_SUFFIX


def type_clashes(workdir, the_plan):
    """Objects the space library holds under another type (resource_type_differs on an Object resource), so their
    boxes would show that type's icon: [{"name", "type", "libraryType", "rename"}]. rename is the name the object
    is drawn under instead (object_rename), or None when no name is left to try."""
    clashes, aliases, alias_clash, seen = [], {}, set(), set()
    standard = standard_names(the_plan)
    for number, batch in enumerate(the_plan.get("preflight", []), start=1):
        path = workdir / "preflight" / f"{number}.json"
        saved = read_json(path) if path.exists() else None
        if not preflight_current(saved, the_plan):
            return []
        own_aliases = batch.get("aliases", {})
        for index, stands_for in own_aliases.items():
            aliases[norm(stands_for)] = batch["changes"][int(index)]["name"]
        for issue in saved.get("issues", []):
            index = change_index(issue)
            if issue.get("code") != "resource_type_differs" or index is None or index >= len(batch["changes"]):
                continue
            change = batch["changes"][index]
            if change.get("kind") != "resource" or change.get("type") != "Object" or norm(change["name"]) in standard:
                continue
            if str(index) in own_aliases:
                alias_clash.add(norm(change["name"]))
                continue
            if norm(change["name"]) not in seen:
                seen.add(norm(change["name"]))
                clashes.append({"name": change["name"], "type": "Object", "libraryType": library_type(issue)})
    for clash in clashes:
        alias = aliases.get(norm(clash["name"]))
        clash["rename"] = object_rename(clash["name"], alias, bool(alias) and norm(alias) not in alias_clash)
    return clashes


def preflight_renames(workdir, the_plan):
    """Every entity rename the saved preflight asks for, or None while a preflight result is unsaved:
    [{"name", "libraryName"}] for an object the library holds only under its API name, and
    [{"name", "libraryName", "reason", "suffixed"?}] for an object whose name the library holds under another type
    (a person, a system), renamed so it stays an Object (object_rename; suffixed when the new name carries
    "(object)"; process maps and journeys, not with acceptTypeClashes). libraryName is the name the map uses; a
    suffixed name is new to the library and is added as an Object like any missing object.
    layout_process.py plan --apply-renames applies the list to a copy of the model."""
    found = preflight_findings(workdir, the_plan)
    if found is None:
        return None
    renames = list(found[1])
    if the_plan.get("diagramType") in CHECKS_LIBRARY_TYPES and not the_plan.get("acceptTypeClashes"):
        taken = {norm(r["name"]) for r in renames}
        for clash in type_clashes(workdir, the_plan):
            if clash["rename"] and norm(clash["name"]) not in taken:
                rename = {"name": clash["name"], "libraryName": clash["rename"],
                          "reason": f"{clash['name']} is {clash['libraryType'] or 'another type'} in the space library, so the object "
                                    f"is drawn as {clash['rename']}"}
                if "(object" in clash["rename"]:
                    rename["suffixed"] = True
                renames.append(rename)
    return renames


def match_probe(asking):
    """Dry-run batches that add each close match offered for the names the user is asked about, once each, with
    the type the model needs, to throwaway boxes: the answer shows each match's library type (no issue when it
    holds that type, resource_type_differs naming the type otherwise)."""
    changes, seen = [], set()
    for missing in asking:
        for name in close_matches(missing["issue"]):
            if norm(name) not in seen:
                seen.add(norm(name))
                changes.append({"op": "add", "kind": "resource", "activity": "probe", "name": name, "type": missing["type"]})
    if not changes:
        return []
    return [{"changes": b["changes"]} for b in preflight_batches([{"batches": [{"changes": changes}]}], {})]


def probe_id(probe):
    return hashlib.sha1(json.dumps(probe, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def match_step(workdir, the_plan, the_map, probe):
    """The next close-match dry run to send, or None when every one is saved for this plan, attempt and probe."""
    ident = probe_id(probe)
    for number, batch in enumerate(probe, start=1):
        path = workdir / "preflight" / f"matches-{number}.json"
        saved = read_json(path) if path.exists() else None
        if not (preflight_current(saved, the_plan) and saved.get("probeId") == ident):
            return {"action": "preflight", "purpose": "library types of the close matches", "tool": "manage_diagram",
                    "batch": number, "of": len(probe),
                    "arguments": {"diagramId": the_map["diagramId"], "baseVersion": the_map.get("version", 0),
                                  "dryRun": True, "changes": batch["changes"]},
                    "saveTo": str(path),
                    "save": f'{{"planId": "{the_plan["planId"]}", "attempt": {the_plan.get("attempt", 1)}, "probeId": "{ident}", '
                            f'"issues": <the issues from the result, each with its path>}} as JSON. Always a dry run: never send it without dryRun'}
    return None


def match_types(workdir, probe, asking):
    """Per name the user is asked about, its close matches with the type the library holds each under:
    [{"name", "type", "matches": [{"name", "libraryType", "typeDiffers"?}]}]."""
    held = {}
    for number, batch in enumerate(probe, start=1):
        saved = read_json(workdir / "preflight" / f"matches-{number}.json")
        issues = {change_index(i): i for i in saved.get("issues", []) if change_index(i) is not None}
        for index, change in enumerate(batch["changes"]):
            if change.get("kind") != "resource":
                continue
            issue = issues.get(index) or {}
            if issue.get("code") == "resource_type_differs":
                held[norm(change["name"])] = library_type(issue)
            elif issue.get("code") == "resource_not_found":
                held[norm(change["name"])] = None
            else:
                held[norm(change["name"])] = change["type"]
    out = []
    for missing in asking:
        matches = []
        for name in close_matches(missing["issue"]):
            kind = held.get(norm(name))
            match = {"name": name, "libraryType": kind}
            if kind != missing["type"]:
                match["typeDiffers"] = True
            matches.append(match)
        out.append({"name": missing["name"], "type": missing["type"], "matches": matches})
    return out


def creatable(the_plan, missing):
    """Whether the run adds this missing name to the space library without asking: every name with
    --create-resources; Object resources (named after the data model) by default on process maps and
    journeys (plan field createObjects). People and systems are business decisions, so the user is asked."""
    return bool(the_plan.get("createResources") or (the_plan.get("createObjects") and missing.get("type") == "Object"))


def preflight_step(workdir, the_plan, the_map):
    for number, batch in enumerate(the_plan.get("preflight", []), start=1):
        path = workdir / "preflight" / f"{number}.json"
        saved = read_json(path) if path.exists() else None
        if not preflight_current(saved, the_plan):
            return {"action": "preflight", "tool": "manage_diagram", "batch": number, "of": len(the_plan["preflight"]),
                    "arguments": {"diagramId": the_map["diagramId"], "baseVersion": the_map.get("version", 0),
                                  "dryRun": True, "changes": batch["changes"]},
                    "saveTo": str(path),
                    "save": f'{{"planId": "{the_plan["planId"]}", "attempt": {the_plan.get("attempt", 1)}, "issues": <the issues from the result, each with its path>}} as JSON. Always a dry run: never send it without dryRun'}
    missing, renames, blocking = preflight_findings(workdir, the_plan)
    step = standard_step(workdir, the_plan, missing)
    if step:
        for issue in blocking + [m["issue"] for m in missing]:
            if issue not in step["issues"]:
                step["issues"].append(issue)
        return step
    missing = [m for m in missing if norm(m["name"]) not in standard_names(the_plan)]
    asking = [m for m in missing if not creatable(the_plan, m)]
    checks_types = the_plan.get("diagramType") in CHECKS_LIBRARY_TYPES
    clashes = []
    if checks_types and not the_plan.get("acceptTypeClashes"):
        renames = preflight_renames(workdir, the_plan)
        renamed = {norm(r["name"]) for r in renames}
        clashes = [c for c in type_clashes(workdir, the_plan) if c["rename"] is None and norm(c["name"]) not in renamed]
    matches = None
    if checks_types and asking:
        probe = match_probe(asking)
        if probe:
            step = match_step(workdir, the_plan, the_map, probe)
            if step:
                return step
            matches = match_types(workdir, probe, asking)
    if blocking or renames or asking or clashes:
        step = {"action": "fix-preflight", "issues": blocking + [m["issue"] for m in asking],
                "how": "resource_not_found: ask the user, per name, to use a close match (rename the role or system in the model) or add the names to the library (plan again with --create-resources). "
                       "Missing Object resources are not listed: the run adds them to the library itself. "
                       "rasci_not_human: the library has that name under another type; use another name or drop the RASCI letters in the model. "
                       "org_not_connected, metadata_not_found, metadata_no_access, story_not_found: plan again with --skip metadata (or story), or fix the model. "
                       "Then validate and plan again into this folder; the preflight runs again."}
        if matches:
            step["closeMatches"] = matches
            step["how"] = ("closeMatches: each name asked about, with the type the space library holds each close match under (libraryType). "
                           "Show the user every match with its type; a match marked typeDiffers is not the type the model needs, and the box "
                           "would show that type's icon (a person for Human), so say so when offering it. " + step["how"])
        if clashes:
            step["typeClashes"] = [{k: v for k, v in c.items() if k != "rename"} for c in clashes]
            step["how"] = ("typeClashes: objects whose name the space library holds under another type (libraryType), so their boxes would show "
                           "that type's icon, such as a person, and none of the names tried instead (the API name, '<name> (object)', "
                           "'<name> (object, <API name>)') avoids it. Ask the user, per object, to rename the entity in the model (the new name "
                           "is added to the library as an Object), or to draw it as the library holds it (plan again with --accept-type-clashes). "
                           + step["how"])
        if renames:
            step["renames"] = renames
            step["how"] = ("renames: the library holds each of these objects under its API name, or holds its name under another type (reason), "
                           "so it is drawn under its API name or, when that does not help, as '<name> (object)' (suffixed); the entity is "
                           "renamed to libraryName so the map shows the object. Apply them without asking: plan again into this folder with "
                           "the same options and --apply-renames, which writes the renamed copy of the model beside it and plans from that "
                           "copy; the done step lists them under renamed for the report. " + step["how"])
        return step
    return None


def standard_names(the_plan):
    """Names the plan draws as standard Elements resources (the interaction flow header icons): never added to
    the space library, and a library entry of the same name under another type is a custom duplicate."""
    return {norm(item["name"]) for item in the_plan.get("standardResources", [])}


def standard_shadowed(workdir, the_plan):
    """The standard resources the space library holds under another type: [{"name", "type", "libraryType"}].
    manage_diagram matches by name only, so a custom entry of the same name hides the standard one."""
    wanted = {norm(item["name"]): item for item in the_plan.get("standardResources", [])}
    shadowed, seen = [], set()
    for number, batch in enumerate(the_plan.get("preflight", []), start=1):
        path = workdir / "preflight" / f"{number}.json"
        saved = read_json(path) if path.exists() else None
        if not preflight_current(saved, the_plan):
            continue
        for issue in saved.get("issues", []):
            index = change_index(issue)
            if issue.get("code") != "resource_type_differs" or index is None or index >= len(batch["changes"]):
                continue
            name = norm(batch["changes"][index].get("name", ""))
            if name in wanted and name not in seen:
                seen.add(name)
                shadowed.append({"name": wanted[name]["name"], "type": wanted[name]["type"],
                                 "libraryType": library_type(issue), "issue": issue})
    return shadowed


def standard_step(workdir, the_plan, missing):
    """Stop before writing when a standard header icon would come out as a custom one, or is missing."""
    standard = standard_names(the_plan)
    if not standard:
        return None
    absent = [m for m in missing if norm(m["name"]) in standard]
    shadowed = [] if the_plan.get("allowCustomIcons") else standard_shadowed(workdir, the_plan)
    if not absent and not shadowed:
        return None
    step = {"action": "fix-preflight", "issues": [m["issue"] for m in absent + shadowed],
            "standardIcons": {"shadowed": [{k: v for k, v in m.items() if k != "issue"} for m in shadowed],
                              "missing": [m["name"] for m in absent]},
            "how": "These header icons are standard Elements resources; the drawing never adds them to the space library. "
                   "shadowed: the space library also holds a custom resource of the same name (libraryType), and manage_diagram, "
                   "which matches resources by name only, would put the custom one on the cards. Tell the user which names, and ask "
                   "whether to remove those custom entries from the space's resource library in Elements (then plan again into this "
                   "folder: the preflight runs again) or to draw with the custom icons (plan again with --allow-custom-icons). "
                   "missing: the space library has no resource of that name; tell the user, and when they agree to draw without it, "
                   "plan again into this folder with --drop-icons and the names (change data/automation-elements.csv or "
                   "data/automation-types.csv only if they want it for every run)."}
    return step


def library_step(workdir, the_plan, the_map):
    """With --create-resources, or for Object resources by default (createObjects), add the names the preflight found missing, at most NEW_NAMES_PER_CHANGE per
    change, on a throwaway box on the top level, then remove the boxes. Returns (step, top-level version)."""
    version = the_map.get("version", 0)
    if not (the_plan.get("createResources") or the_plan.get("createObjects")):
        return None, version
    missing, _, _ = preflight_findings(workdir, the_plan)
    missing = [m for m in missing if norm(m["name"]) not in standard_names(the_plan) and creatable(the_plan, m)]
    if not missing:
        return None, version
    chunks = [missing[i:i + NEW_NAMES_PER_CHANGE] for i in range(0, len(missing), NEW_NAMES_PER_CHANGE)]
    boxes = []
    for number, chunk in enumerate(chunks, start=1):
        path = workdir / "library" / f"{number}.json"
        if not path.exists():
            ref = f"staging{number}"
            changes = [{"op": "add", "kind": "activity", "ref": ref, "text": f"Library staging {number}", "position": {"x": 0, "y": 0}}]
            changes += [{"op": "add", "kind": "resource", "activity": ref, "name": m["name"], "type": m["type"]} for m in chunk]
            return {"action": "library-batch", "tool": "manage_diagram", "batch": number, "of": len(chunks),
                    "names": [m["name"] for m in chunk],
                    "arguments": {"diagramId": the_map["diagramId"], "baseVersion": version, "createResources": True, "changes": changes},
                    "saveTo": str(path),
                    "save": "saved, version, idMap and issues from the result of the real (not dry-run) call, as JSON"}, version
        result = read_json(path)
        if write_recovery(result):
            return write_recovery(result), version
        if not write_complete(result):
            raise PlanError(f"library batch {number}: the saved result says nothing was saved; fix its issues and send it again")
        version = result.get("version", version)
        boxes.append(result.get("idMap", {}).get(f"staging{number}"))
    path = workdir / "library" / "cleanup.json"
    if not path.exists():
        if None in boxes:
            raise PlanError("a saved library result has no key for its staging box; save the idMap from the real call")
        return {"action": "library-cleanup", "tool": "manage_diagram",
                "arguments": {"diagramId": the_map["diagramId"], "baseVersion": version, "confirm": True,
                              "changes": [{"op": "remove", "kind": "activity", "key": key} for key in boxes]},
                "saveTo": str(path),
                "save": "saved, version, idMap, children, diff and issues from the result of the real (not dry-run) call, as JSON"}, version
    result = read_json(path)
    if write_recovery(result):
        return write_recovery(result), version
    if not write_complete(result):
        raise PlanError("library cleanup: the saved result says nothing was saved; fix its issues and send it again")
    return None, result.get("version", version)


def level_diagram_ids(workdir, the_plan):
    """{level slug: diagramId} for each level whose diagram is known: the top level from map.json, a child level
    from the children its parent level's saved results list. A level not yet created is left out."""
    workdir = Path(workdir)
    ids = {}
    if (workdir / "map.json").exists():
        ids[TOP] = read_json(workdir / "map.json").get("diagramId")
    levels = the_plan.get("levels", [])
    for level in levels:
        if level.get("slug") == TOP or level.get("parent") is None:
            continue
        parent_level = next((lv for lv in levels if any(b.get("id") == level["parent"] for b in lv.get("boxes", []))), None)
        if parent_level is None:
            continue
        results = level_results(workdir, parent_level["slug"])
        parent_ref = next(b["ref"] for b in parent_level["boxes"] if b.get("id") == level["parent"])
        parent_key = id_map(results).get(parent_ref)
        for number in sorted(results):
            for child in results[number].get("children", []):
                if parent_key is not None and child.get("activity") == parent_key and child.get("diagramId"):
                    ids[level["slug"]] = child["diagramId"]
    return ids


@bind_step
def next_step(workdir, script):
    workdir = Path(workdir)
    the_plan = read_json(workdir / "plan.json")
    stop = unscoped_attachment_stop(the_plan)
    if stop:
        return stop
    for level in the_plan.get("levels", []):
        if len(level.get("boxes", [])) > 150 or len(level.get("lines", [])) > 300:
            raise PlanError("level exceeds supported growth (150 activities or 300 lines); split the level before creating a map")
    map_path = workdir / "map.json"
    if not map_path.exists():
        return {"action": "create-map", "tool": "create_map",
                "arguments": {"name": map_name(the_plan["mapName"]), "type": the_plan["mapType"], "description": the_plan["mapDescription"][:5000]},
                "saveTo": str(map_path), "save": "mapId, diagramId and version from the result, as JSON"}
    the_map = read_json(map_path)
    step = preflight_step(workdir, the_plan, the_map)
    if step:
        return step
    step, top_version = library_step(workdir, the_plan, the_map)
    if step:
        return step
    diagram_ids = {TOP: the_map["diagramId"]}
    keys_by_level = {}
    skip = unlinkable(workdir, the_plan)
    for level in the_plan["levels"]:
        slug = level["slug"]
        results = level_results(workdir, slug)
        if slug != TOP:
            parent_level = next(lv for lv in the_plan["levels"] if any(b["id"] == level["parent"] for b in lv["boxes"]))
            parent_results = level_results(workdir, parent_level["slug"])
            parent_keys = keys_by_level.get(parent_level["slug"], id_map(parent_results))
            parent_ref = next(b["ref"] for b in parent_level["boxes"] if b["id"] == level["parent"])
            parent_key = parent_keys.get(parent_ref)
            child_id = None
            for number in sorted(parent_results):
                for child in parent_results[number].get("children", []):
                    if child.get("activity") == parent_key and child.get("diagramId"):
                        child_id = child["diagramId"]
            if child_id is None:
                raise PlanError(f"level '{slug}': the parent level's saved results have no child level for '{level['parent']}'; finish the parent level first")
            diagram_ids[slug] = child_id
            read_path = workdir / "reads" / f"{slug}.json"
            if not read_path.exists():
                return {"action": "read-level", "tool": "get_diagram", "level": slug,
                        "arguments": {"diagramId": child_id, "include": ["layout"], "delivery": "file"},
                        "saveTo": str(read_path), "save": "the whole result, as JSON"}
            read = read_json(read_path)
            by_parent_line = {ln["parentLine"]: ln["key"] for ln in lines_of(read) if "parentLine" in ln}
            boundary_keys, parent_line_keys = {}, {}
            for ln in level["lines"] + [{"boundary": ref} for ref in level.get("seeded", [])]:
                if "boundary" in ln:
                    parent_line_key = parent_keys.get(ln["boundary"])
                    parent_line_keys[ln["boundary"]] = parent_line_key
                    if parent_line_key in by_parent_line:
                        boundary_keys[ln["boundary"]] = by_parent_line[parent_line_key]
            base = read.get("version", 0)
        else:
            boundary_keys, parent_line_keys = {}, {}
            base = top_version
        keys = id_map(results)
        keys_by_level[slug] = keys
        for number, batch in enumerate(level["batches"], start=1):
            if number in results:
                result = results[number]
                if write_recovery(result):
                    return write_recovery(result)
                if not write_complete(result):
                    raise PlanError(f"level '{slug}' batch {number}: the saved result says nothing was saved; fix its issues and send it again")
                base = result.get("version", base)
                continue
            own = {c["ref"] for c in batch["changes"] if c.get("op") == "add" and "ref" in c}
            return {"action": "write-batch", "tool": "manage_diagram", "level": slug, "batch": number, "of": len(level["batches"]),
                    "kind": batch["kind"], "dryRunFirst": True,
                    **({"unlinkable": sorted(f"{a} ({t})" for a, t in skip)} if skip else {}),
                    "arguments": dict({"diagramId": diagram_ids[slug], "baseVersion": base,
                                       "changes": drop_unlinkable(resolve(batch["changes"], own, keys, boundary_keys, parent_line_keys), skip)},
                                      **({"confirm": True} if batch.get("confirm") else {})),
                    "saveTo": str(workdir / "results" / slug / f"{number}.json"),
                    "save": "saved, version, idMap, children, diff and issues from the result of the real (not dry-run) call, as JSON"}
    review = []
    for lv in the_plan["levels"]:
        path = workdir / "review" / f"{lv['slug']}.json"
        entry = {"level": lv["slug"], "diagramId": diagram_ids[lv["slug"]], "include": list(REVIEW_INCLUDE), "delivery": "file", "saveTo": str(path)}
        if path.exists():
            # A saved read that is not the whole answer is asked for again (reads.py says why).
            problems = saved_read_problems(path, lv["slug"] != TOP, REVIEW_INCLUDE, expected_content(lv, skip), diagram_ids[lv["slug"]])
            if not problems:
                continue
            entry["refused"] = "not the whole get_diagram answer: " + "; ".join(problems)
        review.append(entry)
    if review:
        return {"action": "review-reads", "tool": "get_diagram", "include": list(REVIEW_INCLUDE), "delivery": "file", "reads": review,
                "save": "each whole result, as JSON, exactly as get_diagram returns it: never trimmed or summarised "
                        "(an entry with refused was saved trimmed; read it again)",
                "then": f"python3 {script} check {workdir}"}
    done = {"action": "done", "mapId": the_map.get("mapId"), "levels": [lv["slug"] for lv in the_plan["levels"]]}
    if (workdir / "renames.json").exists():
        done["renamed"] = read_json(workdir / "renames.json")   # entity renames plan --apply-renames made, for the report
    if skip:
        done["unlinkable"] = sorted(f"{a} ({t})" for a, t in skip)
    return done
