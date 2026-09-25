#!/usr/bin/env python3
"""Validate an Elements diagram export zip before re-import.

Usage: python3 validate.py <path-to-zip>
Exit 0 = valid, Exit 1 = validation errors, Exit 2 = usage error
"""
import json
import re
import sys
import zipfile
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

class _StripHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []

    def handle_data(self, data):
        self._text.append(data)

    def get_text(self):
        return ''.join(self._text)


def strip_html(html: str) -> str:
    if not html:
        return ''
    p = _StripHTML()
    p.feed(html)
    return p.get_text()


# ---------------------------------------------------------------------------
# Known subtypes and their required map type
# ---------------------------------------------------------------------------

SUBTYPE_TO_MAP_TYPE = {
    'upn': 'upn',
    'agentInstruction': 'upn',
    'customerJourney': 'upn',
    'whiteboard': 'upn',
    'agentInteraction': 'architecture',
    'capability': 'architecture',
    'dataModel': 'architecture',
    'interactionFlow': 'architecture',
    'systemArchitecture': 'architecture',
}

VALID_SUBTYPES = set(SUBTYPE_TO_MAP_TYPE.keys())


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate(zip_path: str) -> list:
    errors = []

    try:
        zf = zipfile.ZipFile(zip_path)
    except Exception as e:
        return [f"Cannot open zip: {e}"]

    names = set(zf.namelist())

    # --- map.json ---
    if 'map.json' not in names:
        errors.append("Missing map.json")
        zf.close()
        return errors

    try:
        map_data = json.loads(zf.read('map.json'))
    except json.JSONDecodeError as e:
        errors.append(f"map.json: invalid JSON: {e}")
        zf.close()
        return errors

    for field in ('name', 'type'):
        if field not in map_data:
            errors.append(f"map.json: missing required field '{field}'")

    if 'name' in map_data:
        n = len(map_data['name'])
        if not (2 <= n <= 60):
            errors.append(f"map.json: name length {n} must be 2–60 chars")

    if 'description' in map_data and len(map_data['description']) > 5000:
        errors.append("map.json: description exceeds 5000 chars")

    map_type = map_data.get('type')
    if map_type is not None and map_type not in ('upn', 'architecture'):
        errors.append(f"map.json: type must be 'upn' or 'architecture', got {map_type!r}")

    # --- Discover level files ---
    level_pattern = re.compile(r'^(\d+(?:\.\d+)*)\.json$')
    level_files = {}  # levelNumber -> filename
    for name in sorted(names):
        m = level_pattern.match(name)
        if m:
            level_files[m.group(1)] = name

    if not level_files:
        errors.append("No level JSON files found (expected 1.json, 1.1.json, etc.)")
        zf.close()
        return errors

    # Parse all levels upfront (needed for cross-level drilldown checks)
    levels = {}  # levelNumber -> parsed dict
    for level_num, fname in sorted(level_files.items()):
        try:
            levels[level_num] = json.loads(zf.read(fname))
        except json.JSONDecodeError as e:
            errors.append(f"{fname}: invalid JSON: {e}")

    zf.close()

    # --- Validate each level ---
    top_level_count = 0
    top_level_subtype = None

    for level_num, d in sorted(levels.items()):
        fname = level_files[level_num]
        _validate_level(errors, fname, level_num, d, levels)

        if d.get('topLevel'):
            top_level_count += 1
            # topLevel must be on level 1 specifically
            if level_num != '1':
                errors.append(
                    f"{fname}: topLevel: true is only valid on '1.json', not on level '{level_num}'"
                )
            top_level_subtype = d.get('subtype')

    # Exactly one topLevel
    if top_level_count == 0:
        errors.append("No level file has topLevel: true (1.json must have topLevel: true)")
    elif top_level_count > 1:
        errors.append(f"{top_level_count} level files have topLevel: true (only 1.json should)")

    # subtype vs map.json type consistency
    if top_level_subtype and map_type:
        expected_map_type = SUBTYPE_TO_MAP_TYPE.get(top_level_subtype)
        if expected_map_type and expected_map_type != map_type:
            errors.append(
                f"1.json: subtype '{top_level_subtype}' requires map.json type "
                f"'{expected_map_type}', but map.json has type '{map_type}'"
            )

    return errors


def _validate_level(errors, fname, level_num, d, all_levels):
    prefix = fname

    # Required top-level fields
    for field in ('name', 'levelNumber', 'subtype', 'activities', 'flowlines'):
        if field not in d:
            errors.append(f"{prefix}: missing required field '{field}'")

    # levelNumber must match filename
    if d.get('levelNumber') != level_num:
        errors.append(
            f"{prefix}: levelNumber {d.get('levelNumber')!r} doesn't match filename level {level_num!r}"
        )

    # subtype must be a known value
    subtype = d.get('subtype')
    if subtype is not None and subtype not in VALID_SUBTYPES:
        errors.append(
            f"{prefix}: unknown subtype {subtype!r}. "
            f"Valid values: {', '.join(sorted(VALID_SUBTYPES))}"
        )

    # --- Collect all mxKeys (globally unique within a level) ---
    mxkeys = {}  # mxKey -> human-readable label

    def register(mxkey, label):
        if mxkey is None:
            errors.append(f"{prefix}: {label} has null/missing mxKey")
            return False
        if not isinstance(mxkey, int):
            errors.append(f"{prefix}: {label} mxKey must be an integer, got {type(mxkey).__name__} ({mxkey!r})")
            return False
        if mxkey in mxkeys:
            errors.append(f"{prefix}: duplicate mxKey {mxkey} (conflicts: {mxkeys[mxkey]} vs {label})")
            return False
        mxkeys[mxkey] = label
        return True

    activities = d.get('activities', [])
    activity_mxkeys = set()
    activity_numbers = {}  # number -> mxKey, for uniqueness check

    for a in activities:
        mk = a.get('mxKey')
        label = f"activity '{a.get('text', '')[:40]}'"
        if register(mk, label):
            activity_mxkeys.add(mk)

        # activity number uniqueness within level
        number = a.get('number')
        if number is not None:
            if number in activity_numbers:
                errors.append(
                    f"{prefix}: duplicate activity number={number} "
                    f"(mxKey={mk} and mxKey={activity_numbers[number]})"
                )
            else:
                activity_numbers[number] = mk

        # strippedText is stored in DB but not used by importer; warn if badly out of sync
        text = a.get('text') or ''
        stripped = a.get('strippedText') or ''
        if stripped and stripped != strip_html(text):
            errors.append(
                f"{prefix}: activity mxKey={mk}: strippedText doesn't match text "
                f"(got {stripped[:50]!r}, expected {strip_html(text)[:50]!r})"
            )

        # Attribute mxKeys must be unique within the activity
        seen_attr = set()
        for attr in a.get('attributes', []):
            amk = attr.get('mxKey')
            if amk in seen_attr:
                errors.append(f"{prefix}: activity mxKey={mk}: duplicate attribute mxKey {amk}")
            seen_attr.add(amk)

        # Drilldown: child level must exist at parentLevel.activityNumber
        if a.get('drilldowns'):
            if number is None:
                errors.append(f"{prefix}: activity mxKey={mk} has drilldowns but no 'number' field")
            else:
                child_level = f"{level_num}.{number}"
                if child_level not in all_levels:
                    errors.append(
                        f"{prefix}: activity mxKey={mk} (number={number}) has drilldowns "
                        f"but child level '{child_level}.json' is missing from zip"
                    )

    # Swimlines
    swimlines_obj = d.get('swimlines') or {}
    swimline_mxkeys = set()
    swimline_lines = swimlines_obj.get('lines', [])

    if swimline_lines:
        if 'position' not in swimlines_obj:
            errors.append(
                f"{prefix}: swimlines: missing required field 'position' when lines is non-empty"
            )
        elif not isinstance(swimlines_obj['position'], dict):
            position = swimlines_obj['position']
            errors.append(
                f"{prefix}: swimlines.position must be an object, "
                f"got {type(position).__name__} ({position!r})"
            )
        else:
            position = swimlines_obj['position']
            for field in ('x', 'y', 'w', 'h'):
                if field not in position:
                    errors.append(
                        f"{prefix}: swimlines.position: missing required field '{field}' "
                        f"when lines is non-empty"
                    )
                elif (
                    not isinstance(position[field], (int, float))
                    or isinstance(position[field], bool)
                ):
                    value = position[field]
                    errors.append(
                        f"{prefix}: swimlines.position.{field} must be numeric, "
                        f"got {type(value).__name__} ({value!r})"
                    )

        if 'horizontal' not in swimlines_obj:
            errors.append(
                f"{prefix}: swimlines: missing required field 'horizontal' when lines is non-empty"
            )
        elif (
            not isinstance(swimlines_obj['horizontal'], (int, float))
            or isinstance(swimlines_obj['horizontal'], bool)
        ):
            horizontal = swimlines_obj['horizontal']
            errors.append(
                f"{prefix}: swimlines.horizontal must be numeric (0 = lanes as top-to-bottom "
                f"bands, 1 = side-by-side columns), got {type(horizontal).__name__} ({horizontal!r})"
            )

    for sl in swimline_lines:
        mk = sl.get('mxKey')
        label = f"swimline '{sl.get('text', '')[:40]}'"
        if register(mk, label):
            swimline_mxkeys.add(mk)

    # Texts
    for t in d.get('texts', []):
        mk = t.get('mxKey')
        register(mk, f"text '{(t.get('strippedText') or t.get('text') or '')[:40]}'")

    # Notes
    for n in d.get('notes', []):
        mk = n.get('mxKey')
        register(mk, "note")

    # Images
    for img in d.get('images', []):
        mk = img.get('mxKey')
        register(mk, f"image {img.get('uuid', '')[:20]}")

    # Flowlines
    flowline_mxkeys = set()
    for fl in d.get('flowlines', []):
        mk = fl.get('mxKey')
        if register(mk, "flowline"):
            flowline_mxkeys.add(mk)

        src_type = fl.get('srcType')
        src_id = fl.get('srcId')
        tgt_type = fl.get('tgtType')
        tgt_id = fl.get('tgtId')

        if src_type == 'activity' and src_id not in activity_mxkeys:
            errors.append(f"{prefix}: flowline mxKey={mk}: srcId={src_id} not found in activities")
        elif src_type == 'swimline' and src_id not in swimline_mxkeys:
            errors.append(f"{prefix}: flowline mxKey={mk}: srcId={src_id} not found in swimlines")

        if tgt_type == 'activity' and tgt_id not in activity_mxkeys:
            errors.append(f"{prefix}: flowline mxKey={mk}: tgtId={tgt_id} not found in activities")
        elif tgt_type == 'swimline' and tgt_id not in swimline_mxkeys:
            errors.append(f"{prefix}: flowline mxKey={mk}: tgtId={tgt_id} not found in swimlines")

    # Interactions: flowlineMxKey must reference an existing flowline
    for interaction in d.get('interactions', []):
        fl_mk = interaction.get('flowlineMxKey')
        if fl_mk is None:
            errors.append(f"{prefix}: interaction missing 'flowlineMxKey'")
        elif fl_mk not in flowline_mxkeys:
            errors.append(
                f"{prefix}: interaction references flowlineMxKey={fl_mk} "
                f"which does not exist in this level's flowlines"
            )

    # Every non-root level must be reachable from a parent drilldown
    if level_num != '1':
        parts = level_num.rsplit('.', 1)
        if len(parts) == 2:
            parent_level_num, activity_number_str = parts
            parent = all_levels.get(parent_level_num)
            if parent is None:
                errors.append(f"{fname}: parent level '{parent_level_num}.json' is missing from zip")
            else:
                try:
                    activity_number = int(activity_number_str)
                except ValueError:
                    activity_number = None

                if activity_number is not None:
                    parent_acts = parent.get('activities', [])
                    matching = [a for a in parent_acts if a.get('number') == activity_number]
                    if not matching:
                        errors.append(
                            f"{fname}: no activity with number={activity_number} "
                            f"found in parent level '{parent_level_num}.json'"
                        )
                    elif not matching[0].get('drilldowns'):
                        errors.append(
                            f"{fname}: parent activity number={activity_number} in "
                            f"'{parent_level_num}.json' exists but has no drilldowns entry"
                        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python3 validate.py <path-to-zip>", file=sys.stderr)
        sys.exit(2)

    found_errors = validate(sys.argv[1])

    if found_errors:
        print(f"VALIDATION FAILED, {len(found_errors)} error(s):\n")
        for i, e in enumerate(found_errors, 1):
            print(f"  {i}. {e}")
        sys.exit(1)
    else:
        print("VALIDATION PASSED: diagram zip is ready for import")
        sys.exit(0)
