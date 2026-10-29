"""Check every level of a process map and score it for derivability.

    python3 check_process_map.py check ENG   # the script rules of data/derivability-rubric.csv
    python3 check_process_map.py score ENG   # combine with the wording findings and score each level
    python3 check_process_map.py score ENG --check   # the same, writing nothing (for the assessor)

check reads ENG/levels/ and writes ENG/check/mechanical.json. score reads it
and ENG/check/wording.json (the process-quality-assessor's findings), scores
every level out of 10 by the rubric's weights and writes
ENG/check/scores.json.

A level's score is 10 x the weighted share of passing elements: for each rule,
the share of the level's activities, lines or the level itself that pass it,
weighted by the rule's weight; rules with nothing to check on a level are left
out. A level with no activities scores 0.

score prints one LEVEL line per level and ends with ALL PASS (exit 0) or
FAILED n OF m (exit 3); exit 1 means the wording findings do not fit the map,
exit 2 a setup problem.
"""

import sys

from common import SetupError, eng_path, level_files, load_json, load_rubric, shape_errors, write_json

WHO = {"Human", "System", "Platform / Capability"}


def is_activity(end):
    return isinstance(end, dict) and "activity" in end


def check(eng):
    rules, _ = load_rubric()
    script_rules = {r["rule_id"]: r for r in rules if r["checked_by"] == "script"}
    _, items = level_files(eng)
    out = {"levels": []}
    for item in items:
        read = load_json(eng_path(eng, "levels", f"{item['levelNumber']}.json"), f"level {item['levelNumber']}")
        diagram = read.get("diagram", {})
        acts = diagram.get("activities", [])
        lines = [l for l in diagram.get("lines", []) if is_activity(l.get("from")) or is_activity(l.get("to"))]
        keys = {a["key"] for a in acts}
        failing = []
        line_in, line_out = set(), set()
        starts = ends = False
        for line in lines:
            src, dst = line.get("from"), line.get("to")
            if is_activity(dst):
                line_in.add(dst["activity"])
                if not is_activity(src):
                    starts = True
            if is_activity(src):
                line_out.add(src["activity"])
                if not is_activity(dst):
                    ends = True
            if "D03" in script_rules and not (line.get("label") or "").strip():
                failing.append({"rule": "D03", "kind": "line", "key": line["key"], "text": f"line {line['key']}"})
        for act in acts:
            text = " ".join((act.get("text") or "").split())
            if "D01" in script_rules and not any(r.get("type") in WHO for r in act.get("resources", [])):
                failing.append({"rule": "D01", "kind": "activity", "key": act["key"], "text": text})
            if "D02" in script_rules and (act["key"] not in line_in or act["key"] not in line_out):
                failing.append({"rule": "D02", "kind": "activity", "key": act["key"], "text": text})
        if "D04" in script_rules and acts and not (starts and ends):
            failing.append({"rule": "D04", "kind": "level", "key": 0, "text": read.get("title") or item["levelNumber"]})
        out["levels"].append({"diagramId": item["diagramId"], "levelNumber": item["levelNumber"],
                              "title": read.get("title") or item.get("title"), "url": read.get("diagramUrl", ""),
                              "totals": {"activity": len(acts), "line": len(lines), "level": 1},
                              "keys": {"activity": sorted(keys), "line": sorted(l["key"] for l in lines)},
                              "failing": failing})
    write_json(eng_path(eng, "check", "mechanical.json"), out)
    count = sum(len(l["failing"]) for l in out["levels"])
    print(f"CHECKED {len(out['levels'])} levels: {count} mechanical finding(s); now run the process-quality-assessor, then score")
    return 0


def score(eng, write=True):
    rules, pass_mark = load_rubric()
    mechanical = load_json(eng_path(eng, "check", "mechanical.json"), "check/mechanical.json (run check first)")
    wording = load_json(eng_path(eng, "check", "wording.json"), "check/wording.json (the process-quality-assessor's file)")
    errors = shape_errors(wording, "wording.schema.json")
    by_level = {l["diagramId"]: l for l in wording.get("levels", [])} if not errors else {}
    for level in mechanical["levels"]:
        if not errors and level["diagramId"] not in by_level:
            errors.append(f"wording.json has no entry for level {level['levelNumber']} ({level['diagramId']})")
        for finding in by_level.get(level["diagramId"], {}).get("failing", []):
            if finding["key"] not in level["keys"][finding["kind"]]:
                errors.append(f"wording.json level {level['levelNumber']}: {finding['kind']} {finding['key']} is not on that level")
    if errors:
        for line in errors:
            print(f"ERROR {line}")
        print("REFUSED the wording findings do not fit the map; send them back to the process-quality-assessor")
        return 1
    weights = {r["rule_id"]: r for r in rules}
    result = {"passMark": pass_mark, "levels": []}
    failed = 0
    for level in mechanical["levels"]:
        findings = list(level["failing"]) + [dict(f) for f in by_level[level["diagramId"]]["failing"]]
        total_w = earned = 0.0
        for rule in rules:
            kind = rule["applies_to"]
            n = level["totals"][kind]
            if n == 0:
                continue
            bad = len({f["key"] for f in findings if f["rule"] == rule["rule_id"]})
            total_w += rule["weight"]
            earned += rule["weight"] * max(0, n - bad) / n
        value = round(10 * earned / total_w, 1) if total_w and level["totals"]["activity"] else 0.0
        passed = value >= pass_mark
        failed += 0 if passed else 1
        for f in findings:
            f["rule_text"] = weights.get(f["rule"], {}).get("rule", "")
        result["levels"].append({"levelNumber": level["levelNumber"], "diagramId": level["diagramId"], "title": level["title"],
                                 "url": level["url"], "score": value, "passed": passed, "findings": findings})
        print(f"LEVEL {level['levelNumber']} '{level['title']}' {value}/10 {'PASS' if passed else 'FAIL'} ({len(findings)} finding(s))")
    result["passed"] = failed == 0
    if write:
        write_json(eng_path(eng, "check", "scores.json"), result)
    if failed:
        print(f"FAILED {failed} OF {len(result['levels'])} levels are below the pass mark of {pass_mark:g}")
        return 3
    print(f"ALL PASS every level scores at least {pass_mark:g}")
    return 0


def main(argv):
    dry = argv[3:] == ["--check"]
    if len(argv) not in (3, 4) or argv[1] not in ("check", "score") or (len(argv) == 4 and not (dry and argv[1] == "score")):
        print(__doc__.strip())
        return 2
    try:
        return check(argv[2]) if argv[1] == "check" else score(argv[2], write=not dry)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
