"""The shared layout engine every layout script builds on.

Each layout script (layout_process.py, layout_data_model.py, layout_architecture.py, layout_interaction.py)
imports from this package and from no other layout script, so a change inside one diagram type cannot break
another. What lives here is what more than one diagram type uses:

- base: Paths, constants, errors, data-file reading and small text helpers every layout script uses.
- geometry: Placement and line geometry: the left-to-right level layout (Level), the sides and routes lines take, canvas growth and the writes it allows, free spots and card sizing.
- write_loop: The resumable write loop: the next step to carry to Elements, preflights, library batches, saved results and id maps.
- reads: The whole-read rule: a saved review read is the whole get_diagram answer, never trimmed or summarised.
- checks: The layout check: compares saved review reads with the plan against the layout rubric rows.

A change here affects every diagram type: run the whole test suite (python3 -m unittest discover -s tests).
"""

from .base import (  # noqa: F401
    ATTACHMENT_KINDS, END, MAX_CHANGES, NEW_NAMES_PER_CHANGE, PLUGIN, PlanError,
    RESOURCE_TYPE, RUBRIC_PATH, START, STYLE_FILES, STYLE_PATH, SetupError,
    TOP, TYPES_PATH, USES_TYPE, attachment_changes, chunk, cut,
    dedupe, guard_workdir, load_style, make_ref, map_type, norm,
    parse_skip, plan_id, prepare_workdir, read_csv, read_json, slug,
    squash, unwrap, writes_saved,
)
from .geometry import (  # noqa: F401
    JETTY, Level, SAME_SIDE_PAIRS, SIDE_PAIRS, SIDE_REUSE, STEP, canvas_after,
    choose_sides, crosses, fit_blank, free_spot, inside, moves_in_passes, parallel_sides,
    overlaps, plausible, route, route_cost, route_crossings, route_length,
    segment_hits_box, shared_run, side_point, simulate_attributes, write_passes, USES_RESERVED,
    NOTE_SIZE, NOTE_GAP, NOTE_CLEARANCE, LABEL_BOX, line_paths, level_note_spot,
)
from .write_loop import (  # noqa: F401
    PATH_INDEX, PREFLIGHT_BOX_RESOURCES, BY_NAME_ONLY, change_index, creatable, drop_unlinkable, unlinkable, unlinkable_issue, id_map, level_results, library_step,
    lines_of, next_step, preflight_batches, preflight_current, preflight_findings, preflight_step, resolve,
    standard_names, standard_shadowed, standard_step, level_diagram_ids,
    CHECKS_LIBRARY_TYPES, LIBRARY_TYPE, close_matches, library_type, match_probe, match_step, match_types, preflight_renames,
    probe_id, type_clashes, OBJECT_SUFFIX, OBJECT_SUFFIX_WITH_API, object_rename,
)
from .reads import (  # noqa: F401
    ANSWER_FIELDS, LAYOUT_FIELDS, REVIEW_INCLUDE, TrimmedReads, expected_content, read_problems, refuse, reread,
    review_refusals, saved_read_problems,
)
from .checks import (  # noqa: F401
    ALLOWED, check, clearance_region, groups_by, layout_rules, refuse_partial_reads, region_overlaps,
    relation,
)
