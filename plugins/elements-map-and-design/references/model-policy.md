# Model policy

Which kind of model each part of the plugin needs, written so it works on any agent platform (Claude, GitHub Copilot, OpenAI Codex, Gemini and others) and survives new model releases.

## Tiers, not model names

The plugin never decides by model name. Each agent and skill has a **tier** in [`../data/model-tiers.csv`](../data/model-tiers.csv), the single authority:

- **`strong`**: the most capable reasoning model the platform offers. For work where judgement is the job: interpreting a source, deciding a grouping, reviewing a result.
- **`fast`**: the platform's cheaper general model. For bounded work into a fixed format that a script checks afterwards, or for carrying a script's steps to Elements.

Each row also has an **effort** (`low`, `medium`, `high`): how much reasoning time to allow. No agent file sets it: it is advice for platforms that let you set it. Nothing runs at the platform's maximum routinely: the fix loops give failing work a second pass.

## How a tier becomes a model

[`../data/model-hosts.csv`](../data/model-hosts.csv) maps the tiers to each platform's models, one row per platform. It is the only table of model names: the skills and the drawing protocol name no model, and the agents' `model:` lines follow it. Supporting a new platform means adding one row; changing a platform's models means editing its row (for Claude, also the agents' `model:` lines).

- **Claude:** `strong` is `opus` and `fast` is `sonnet`. Each agent file's `model:` line is this mapping of its tier, and `tests/test_model_tiers.py` keeps the two in step.
- **A platform with no row:** `strong` is its most capable model and `fast` its cheaper general model. If it cannot choose a model per agent, every agent runs on the session's model, and the tiers become advice on which session model to pick.

## Agents and skills

- **Agents** carry their tier's model for the platform, so they do not inherit the session's model. A fast agent stays cheap even when the session is strong, and a strong reviewer is not weakened by a fast session.
- **Skills** run on the session's model; a skill cannot switch it. A session runs a chain of skills (the front door, a reader, then a drawing skill), so pick the session model for the strongest skill in the chain: `strong` for anything that starts at the front door or a reader. A `fast` session is enough only to draw a model file that already exists with `draw-process-map`, `draw-interaction-flow` or `draw-capability-map`.

## Changing it

Change the row in `model-tiers.csv`, then the agent's `model:` line to its tier's Claude mapping. Run `python3 -m unittest tests.test_model_tiers` from the plugin folder. It fails when an agent or skill has no row, a row names an agent or skill that does not exist, a value is outside the vocabularies, a row has no `why`, an agent's `model:` line does not match its tier's Claude mapping, or a skill's Markdown or `references/drawing-protocol.md` names a model. Move an agent up a tier when its output keeps failing review; move it down when cost matters and its reviews pass.
