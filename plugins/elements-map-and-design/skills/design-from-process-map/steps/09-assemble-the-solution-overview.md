# 09 Assemble the solution overview

State: `diagrams-drawn`

## Purpose

Bring the design together as the document the customer is handed: a high-level solution design that walks the process area by area (its process level, the data it uses and the integrations that serve it, each pictured and summed up), pictures and links both diagrams, sums up the access matrix delivered beside it, and records the decisions, assumptions and gaps.

## Procedure

1. Run `python3 "$SKILL/scripts/render_diagram.py" "$ENG"`: it pictures the drawn diagrams and, for each process area, its process level, its data model and its integrations. Keep each `NO PICTURE` line for the report.
2. Run the `solution-overview-writer` agent with `pluginRoot`, `eng` and `outputPath` (`$ENG/overview/prose.json`).
3. Run `python3 "$SKILL/scripts/build_solution_overview.py" "$ENG"`. Send `ERROR overview/prose.json` lines back to the agent as `findings`, at most twice; other `ERROR` lines name a missing source, which the Failure section covers.
4. Copy the path it prints into `deliverables.overview_docx`, and `access-matrix.csv`'s path into `deliverables.access_matrix_csv`.

## Outcomes, in precedence order

The first that holds wins.

- **TR-22 — The Word file is written.** `{"current_state": "delivered", "current_step": null}`. Report the deliverables (below) and stop.
- **TR-23 — Otherwise.** Record the remaining `ERROR` lines in `blocked` (`entered_from: "diagrams-drawn"`). `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`. Record the default call in `decisions_log` and tell the solution architect.

The final report, in the solution architect's words, from the run's files so it can be repeated at `delivered`: the solution overview (`deliverables.overview_docx`), the access matrix file delivered beside it, the links in `deliverables` to each drawn diagram with the verdict and findings in its `drawing/<name>/review.json`, which pictures are missing from `overview/images/` (the `NO PICTURE` lines), the confidence when lower, the gaps, any map a re-plan left half drawn in Elements (named as abandoned and not part of the design), and that the diagrams are drafts a person releases in Elements and the document is version 0.1 for them to edit.

## Failure

`ERROR missing <file>` names a source an earlier card writes: return the state to that card (`evidence-gathered` for `model.json`, `derive/data-model.json` or `derive/integrations.json`; `structure-derived` for `derive/access.json` or the access matrix; `scoped` for the scores), as one edit with its `current_step`, and say why. `ERROR missing overview/prose.json` means step 2 did not finish: run step 2 again; the state stays at `diagrams-drawn`. `SETUP python-docx is not installed`: ask the solution architect to install it, then run step 3 again; the state stays at `diagrams-drawn`.
