---
name: draw-capability-map
description: "Draws a validated model's capabilities as an Elements business capability map on one level: business drivers across the top, a column of capability cards under each top-level heading, platform bands below, optional rating colours with a legend; then checks the layout. Called by the start skill once a model with capabilities exists. Not for working out what the capabilities are, editing an existing map, or other diagram types."
user-invocable: false
---

# Draw a capability map

Follow [result acquisition](../../references/result-acquisition.md) for complete reads, native jobs, failure evidence and write outcomes.

Input: a model file in the format of `schemas/ba-model.schema.json` with `capabilities` and, optionally, `drivers`. Output: a new draft capability map in the active Elements space, with one level holding the whole map, and a review verdict.

The layout is computed by a script, not by you: `scripts/layout_capability.py` places every card (`data/style-capability.csv`), picks colours (`data/capability-ratings.csv`) and turns the plan into `manage_diagram` batches. `references/capability-conventions.md` explains the layout and why groupings are headings rather than boxes; read it when you need to explain a warning or a choice to the user.

Follow the plugin's [drawing protocol](../../references/drawing-protocol.md) with `<script>` = `scripts/layout_capability.py`. This file adds only what is particular to capability maps.

Paths: this file's folder holds `references/`; the plugin root is two levels up and holds `scripts/`, `data/`, `schemas/`, `agents/` and `references/`.

## 1. Check the model and ask what it does not say

Validate with `--for capability` (protocol section 1). Work folder: the one the calling skill names, otherwise `<model name>-capability-map/`. Then ask the user only what the model does not say and they have not told you:

- **Ratings.** When capabilities carry a `rating`, which scale it is: `assessment` (advanced, intermediate, underperforming, missing; the default), `maturity` (1 to 5) or `coverage` (covered, partial, outside, planned). The scales are rows of `data/capability-ratings.csv`.
- **Lists or cards.** When the lowest level has many short names, whether to draw them as list lines on their parent's card (`--children-as list`) rather than as cards of their own. Cards (`boxes`) are the default; a capability's own `childrenAs` (`boxes` or `list`) overrides either.

## 2. Plan

`python3 <plugin>/scripts/layout_capability.py plan MODEL --workdir DIR`, adding as needed:

- `--scale NAME` for the rating scale chosen in step 1;
- `--children-as list` (step 1);
- `--no-drivers` when the user does not want the drivers row, `--no-legend` when they do not want the rating legend;
- `--skip metadata,story,link,note` to leave those attachment kinds out (`note` also leaves out the Inferred and Description notes);
- `--name "TEXT"` when the user wants a map name other than the model's title.

Planning into a folder that already holds a created map is refused; use a new folder.

What to tell the user about the plan: how many capability cards, headings, list lines, drivers and legend swatches the map has. The `WARN` lines particular to capability maps include sub-capabilities continuing into a second column; what a heading cannot show (a rating, icon, description, attachment or Inferred note on a capability that groups others); a rating that cannot be shown on a list line; and a long title, heading word or footer that a fixed-size card or text box will crowd or cut. `DIR/preview.svg` shows the planned layout.

## 3. Write the map

The protocol's write loop, with these actions in place of `write-batch`, because `next` itself decides what to send for real after each dry run:

| `action` | Do |
|---|---|
| `dry-run` | Send `manage_diagram` with `arguments` (they hold `"dryRun": true`; nothing is written). Save `{"issues"}` from the result at `saveTo`, keeping each issue's `path`, even when it holds errors. |
| `write` | Send `manage_diagram` with `arguments`. Save `{"saved", "version", "idMap", "issues"}` at `saveTo`. |
| `retry-dry-run` | The level was busy (`code` `lock_held` or `being_edited`: someone, maybe the user, has it open in edit mode; `rate_limited` or `server_busy`: too many requests). Do what `before` says (ask the user to leave edit mode, or wait `retryAfter` seconds or a minute), then send `manage_diagram` with `arguments` and save the new result at `saveTo`, in place of the old one. |
| `stop` | Something is not as this run expects. Tell the user `reason` and stop. |

What `next` does with a dry run: a header icon the space library lacks (`resource_not_found` on a resource) is left out of the real call and listed in `droppedIcons` when the run is done; a card the canvas refuses (`position_out_of_bounds`) waits for a later batch; a busy level (`lock_held`, `being_edited`, `rate_limited`, `server_busy`) gets `retry-dry-run`. Any other error makes it answer `stop`. `next` handles these, so send its `arguments` unchanged (protocol section 3).

Batches go in this order: the cards that fit the level's canvas (a blank level takes positions inside 2000 x 1200 px; the canvas grows once there is content, so the rest follow after a `read-level`), then, once every card is on the level, a read-back that moves any card Elements did not put where the layout says. Usually there is nothing to move.

## 4. Check and report

Check with the protocol (layout rubric rows R26-R28; `diagramType` `capability`; `levels` is `DIR/review/top.json`). In the report, also list the icons the space library did not have (`droppedIcons`), with the dry run's `message` for each, so the user can add them in Elements or rename them in the model for next time.

What the drawing does not do: nothing is drawn inside anything else, because `manage_diagram` cannot size a card or a text box; a capability that groups others is a heading (a text box) over its cards instead (`references/capability-conventions.md`, section 4), so it cannot carry a colour, icon, footer or attachment. A card below the top level keeps its description in a note attachment titled Description. A `realisedBy` link is not drawn (other skills draw the processes, data and systems behind a capability). Everything is on one level, with no drill-downs.
