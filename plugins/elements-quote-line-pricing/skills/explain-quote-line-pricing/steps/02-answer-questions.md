# 02 Answer questions

State: `diagnostics-built`

## Purpose

Explain this line's price and answer follow-up questions from its evidence.

All paths below resolve from the skill directory for `data/`, `references/` and `steps/`; `scripts/` and `agents/` resolve from the plugin root.

## Procedure

Classify the question using the outcomes in order. When `slots.question` is set on entry, answer that stored question, including on resume; otherwise use the current message. A resume request with no new question and no stored question takes TR-11: report where the engagement stands and re-offer the latest saved `answers/<NNN>/answer.md`, using the highest existing answer number. If no answer exists, ask what the user would like to understand about this quote line. Keep `slots.question` null and finish TR-11 without selecting agents. For a pricing question under TR-11:

1. Read `slots.quote_line_id` and `diagnostics.file`, and map the question to topics using `data/question-routing.csv`. Use `broad` for a broad, multi-topic or unclear question. Use `broad` alone for a broad question; `select` picks the agents from the line's flags. Record the topic mapping and its evidence in `decisions_log`.
2. Run `scripts/compose_answer.py select --diagnostic <file> --topics <list|broad>`. Add `--full` when answering `slots.question` from card 01 or when the user explicitly requests a full re-analysis. Run scripts from the plugin root and pass the absolute path in `diagnostics.file` as `<file>`. Use exactly the printed `agents` and `mode` for dispatch and composition.
3. Dispatch the selected agents in parallel. Each printed identifier `<agent>` maps to the registered agent `<agent>-agent` and `references/guides/<agent>-agent.md`. In Claude Code, dispatch `elements-quote-line-pricing:<agent>-agent`; in Codex, use `agents/<agent>-agent.md` as the agent's instructions with read-only file access. Pass `question`, `diagnostic_path` (absolute), `guide_path` (absolute) and `mode`. Each returns `agent`, `status`, `summary`, `answer`, `evidence` and `gaps`. In chat name each selected agent and its task on dispatch: Pricing Method Agent looks at pricing method and proration; Discount Agent at discounts; Bundle and Options Agent at bundle and option context; Price Rules Agent at calculator rules and their history; MDQ Agent (Multi-Dimensional Quoting) at segments and uplift. In the dispatch chat line, `<topic>` is the task phrase given for that agent. Say "The <name> is now looking at <topic> for this line." When each returns, say "The <name> has returned: <summary>".
4. Save each structured return in the engagement directory at `answers/<NNN>/<agent>.json`, where `NNN` is the next three-digit number starting at `001`, based on the existing answer directories. Run `scripts/compose_answer.py compose --diagnostic <file> --returns <engagement directory>/answers/<NNN>/ --mode <mode>` from the plugin root. When compose prints `returnSchemaErrors` or `evidenceDropped` as JavaScript Object Notation (JSON) lines on standard error, record every entry in `decisions_log`, including the agent and validation error or dropped evidence path. Save the composed answer as `answers/<NNN>/answer.md` and record that path with `slots.quote_line_ref` in `decisions_log`. Present the printed answer unchanged and clear `slots.question`.

## Outcomes, in precedence order

The first that holds wins.

- **TR-08: The user names a different quote line.** Set `slots.quote_line_ref` and `slots.question` from the message; clear `slots.quote_line_id` and all `diagnostics` fields, keeping the earlier evidence directory on disk. Write `{"current_state": "kickoff", "current_step": "steps/01-build-diagnostics.md"}`. Next card: `steps/01-build-diagnostics.md` in the same turn.
- **TR-09: The user asks to rebuild data for this line, or the diagnostic file is missing on resume.** Keep `slots.quote_line_ref`, set `slots.question` if the message includes one, and clear all `diagnostics` fields. Record a missing-file rebuild in `decisions_log`. Write `{"current_state": "kickoff", "current_step": "steps/01-build-diagnostics.md"}`. Next card: `steps/01-build-diagnostics.md` in the same turn.
- **TR-10: The user says they are finished.** Clear `slots.question`. Write `{"current_state": "engagement-closed", "current_step": null}`. Terminal: report the distinct quote lines with saved-answer entries in `decisions_log`, then stop.
- **TR-11: The message is a pricing question about this line, or a resume request with no new question.** Run the procedure. Write `{"current_state": "diagnostics-built", "current_step": "steps/02-answer-questions.md"}`. Next card: `steps/02-answer-questions.md`; stop for the next message.
- **TR-12: The message is outside scope or about the whole quote.** Reply with `OUT-OF-SCOPE` or `QUOTE-NOT-LINE` from `data/canned-messages.csv`, as applicable, and clear `slots.question`. Write `{"current_state": "diagnostics-built", "current_step": "steps/02-answer-questions.md"}`. Next card: `steps/02-answer-questions.md`; stop.
- **TR-13: Otherwise.** Reply with `FALLBACK` from `data/canned-messages.csv` and clear `slots.question`. Write `{"current_state": "diagnostics-built", "current_step": "steps/02-answer-questions.md"}`. Next card: `steps/02-answer-questions.md`. Record the default call and evidence in `decisions_log` and stop.

## Failure

If the diagnostic file is missing on resume, re-check its recorded path and take TR-09. If an agent return fails validation, the compose script uses `FALLBACK` for that section and the answer still ships. Record any unresolved prerequisite in `open_items` and stay on `diagnostics-built` until the prerequisite is available.
