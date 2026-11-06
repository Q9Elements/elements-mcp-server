#!/usr/bin/env python3
"""List what an agent package holds and how its stages run, as inventory.json.

Usage:
  inventory_package.py PACKAGE --out inventory.json [--entry PATH] [--depth top|children] [--server NAME]

PACKAGE is a folder (a skill, a playbook, a plugin, a framework) or one file (an
agent, a command). The script:
  - recognises the format from data/agent-package-formats.csv (first row whose
    detect paths all exist);
  - reads the stages where that format keeps them (stage_source): an Elements
    playbook's dispatch table and cards, a runbook's stage table, a skill's
    numbered sections, a framework's commands;
  - reads each stage's numbered instructions, outcomes and next stage, and the
    people the package names in its human moments;
  - finds the components each stage calls by fixed patterns: agents and skills by
    name, scripts and data, template and reference files by file name, MCP tools
    as mcp__server__tool, a snake_case name after 'call', or any name listed in
    data/known-mcp-tools.csv (which also gives its server); kinds and paths come
    from data/resource-prefixes.csv;
  - lists the package's own components no stage calls (unused), and the files it
    could not classify.

A plugin is a list of packages: the script lists them in 'candidates' and stops
with exit 3; run it again with --entry naming one.

Exit 0: written. 1: nothing to read (no stages found); the file is still written
with gaps. 2: setup problem. 3: a plugin; choose an entry.

Standard library only; Python 3.8 or later.
"""

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

import common
from common import SetupError, slug

ITEM_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
NUMBERED = re.compile(r"^(\s{0,3})(\d+)[.)]\s+(.*)$")
BULLET = re.compile(r"^(\s{0,3})[-*]\s+(.*)$")
H1 = re.compile(r"^#\s+(.*)$")
H2 = re.compile(r"^##\s+(.*)$")
MCP_FULL = re.compile(r"mcp__([A-Za-z0-9-]+?)__([A-Za-z0-9_-]+)")
BACKTICK_NAME = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")
MCP_CALL = re.compile(r"\b(?:[Cc]all|[Cc]alls|[Cc]alling|[Ss]end|[Ss]ends)\s+`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")
STATE_JSON = re.compile(r'"current_state"\s*:\s*"([^"]+)"')
OUTCOME = re.compile(r"^\s*[-*]\s+\*\*(.+?)\*\*(.*)$")
TR_ID = re.compile(r"^(TR-\d+)\s*[—–-]\s*")
INCLUDE = re.compile(r"@([~\w./-]+\.md)")
SKIP_SECTIONS = {"rules", "contents", "rules that matter most", "what you return", "what you are given",
                 "session contract", "shipped surfaces", "files and hand-offs", "paths"}
RECOVERY_SENDERS = 3  # stages sending their failures to one stage make it a recovery stage, when the format names none
TEXT_SUFFIXES = {".md", ".mdc", ".txt", ".json", ".yaml", ".yml", ".py", ".sh", ".js", ".mjs", ".ts", ".csv"}


# ---------------------------------------------------------------- markdown

def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise SetupError(f"cannot read {path}: {exc}")


def frontmatter(text):
    """Simple 'key: value' frontmatter (the values agents and skills use); returns (fields, body)."""
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields, text[match.end():]


def sections(body):
    """[(heading, text)] for every '## ' section; text before the first is under ''."""
    out, heading, lines = [], "", []
    for line in body.splitlines():
        match = H2.match(line)
        if match:
            out.append((heading, "\n".join(lines)))
            heading, lines = match.group(1).strip(), []
        else:
            lines.append(line)
    out.append((heading, "\n".join(lines)))
    return out


def list_items(text):
    """The top-level numbered items of a text, each with its continuation lines; bullets when none."""
    for pattern in (NUMBERED, BULLET):
        items, current, in_code = [], None, False
        for line in text.splitlines():
            if line.strip().startswith("```"):
                in_code = not in_code
                if current is not None:
                    current.append(line)
                continue
            match = pattern.match(line) if not in_code else None
            if match and len(match.group(1)) == 0:
                if current is not None:
                    items.append(current)
                current = [match.groups()[-1]]
            elif current is not None:
                if line.startswith("#"):
                    items.append(current)
                    current = None
                else:
                    current.append(line)
        if current is not None:
            items.append(current)
        items = [" ".join(" ".join(i).split()) for i in items]
        items = [i for i in items if i]
        if items:
            return items
    return []


def table_rows(text):
    """Rows of every markdown table in a text, as lists of cells, header rows included."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                continue
            rows.append(cells)
        elif rows and rows[-1] is not None:
            rows.append(None)
    return rows


def tables(text):
    """Each markdown table as (header, rows)."""
    out, current = [], []
    for row in table_rows(text) + [None]:
        if row is None:
            if current:
                out.append((current[0], current[1:]))
            current = []
        else:
            current.append(row)
    return out


def plain(cell):
    """A table cell or heading without markdown: links keep their text, code marks and bold go."""
    cell = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cell)
    return " ".join(cell.replace("`", "").replace("**", "").split())


def stage_id(text, taken):
    base = slug(re.sub(r"^\d+[-_. ]+", "", text), 40) or "stage"
    sid, n = base, 2
    while sid in taken:
        sid = f"{base}-{n}"
        n += 1
    taken.add(sid)
    assert ITEM_ID.match(sid), sid
    return sid


# ---------------------------------------------------------------- the package

class Package:
    def __init__(self, path, entry=None, server=None):
        self.input = Path(path).resolve()
        if not self.input.exists():
            raise SetupError(f"{self.input} does not exist")
        self.formats = common.load_formats()
        self.prefixes = common.load_prefixes()
        self.server_override = server
        self.known_tools = common.load_known_tools()
        self.gaps = []
        self.root = self.input if self.input.is_dir() else self.input.parent
        if entry:
            target = (self.root / entry).resolve()
            if not target.exists():
                raise SetupError(f"entry {entry} does not exist under {self.root}")
            self.input = target
            self.root = target if target.is_dir() else target.parent
        self.format = self.detect()
        self.search_root = self.find_search_root()

    # ------------------------------------------------------------ format

    def detect(self):
        for row in self.formats:
            if all(self.matches(rule) for rule in row["detect"]):
                return row
        raise SetupError(f"{self.input} matches no format in agent-package-formats.csv; add a row for it")

    def matches(self, rule):
        if rule.startswith("file:"):
            if not self.input.is_file():
                return False
            pattern = rule[len("file:"):]
            rel = f"{self.input.parent.name}/{self.input.name}"
            return fnmatch.fnmatch(rel, pattern)
        if not self.input.is_dir():
            return False
        return any(True for _ in self.root.glob(rule))

    def find_search_root(self):
        """Components can live above the package: a skill's agents and shared scripts sit at its plugin's root."""
        for folder in [self.root] + list(self.root.parents):
            if (folder / ".claude-plugin").is_dir() or (folder / ".codex-plugin").is_dir():
                return folder
            if folder == self.root.anchor:
                break
        return self.root

    # ------------------------------------------------------------ components

    def components(self):
        """Every component under the search root, keyed by the names that refer to it."""
        found, by_name = [], {}
        files = [p for p in self.search_root.rglob("*") if p.is_file() and not any(
            part.startswith((".git", "__pycache__", "node_modules", "_workspace")) for part in p.relative_to(self.search_root).parts)]
        for kind, row in self.prefixes.items():
            for glob in row["path_globs"]:
                for path in files:
                    rel = path.relative_to(self.search_root).as_posix()
                    if (fnmatch.fnmatch(rel, glob) or (glob.startswith("**/") and fnmatch.fnmatch(rel, glob[3:]))
                            or ("/" not in glob and fnmatch.fnmatch(path.name, glob))):
                        found.append((kind, path))
        seen, components = set(), []
        for kind, path in found:
            if path in seen:
                continue
            seen.add(path)
            if kind in ("agent", "command") or (kind == "skill"):
                text = read_text(path)
                fields, _ = frontmatter(text)
                name = fields.get("name") or (path.parent.name if kind == "skill" else path.stem.replace(".prompt", ""))
                description = fields.get("description", "")
                keys = {name, path.stem} if kind != "skill" else {name, path.parent.name}
            else:
                name, description, keys = path.name, "", {path.name}
            cid = f"{self.prefixes[kind]['id_prefix']}:{name}"
            comp = {"id": cid, "kind": kind, "name": name, "path": path.relative_to(self.search_root).as_posix()}
            if description:
                comp["description"] = description[:600]
            components.append(comp)
            for key in keys:
                by_name.setdefault((kind, key), comp)
        self.all_components = components
        self.by_name = by_name
        return components

    def references(self, text, exclude=()):
        """Component ids a text calls, in the order they first appear."""
        hits = []

        def add(cid, at):
            hits.append((at, cid))

        for (kind, key), comp in self.by_name.items():
            if comp["id"] in exclude:
                continue
            if kind in ("agent", "skill", "command"):
                for m in re.finditer(r"(?<![\w/-])" + re.escape(key) + r"(?![\w-])", text):
                    add(comp["id"], m.start())
                    break
            else:
                for m in re.finditer(r"(?<![\w-])" + re.escape(key) + r"(?![\w-])", text):
                    add(comp["id"], m.start())
                    break
                if kind == "script" and key.endswith(".py"):
                    m = re.search(r"^\s*(?:import|from)\s+" + re.escape(key[:-3]) + r"\b", text, re.M)
                    if m:
                        add(comp["id"], m.start())
        for m in MCP_FULL.finditer(text):
            add(self.tool(m.group(1), m.group(2)), m.start())
        for m in MCP_CALL.finditer(text):
            name = m.group(1)
            if not any(c["name"] in (name, name + ".py") for c in self.all_components):
                add(self.tool(None, name), m.start())
        for m in BACKTICK_NAME.finditer(text):  # a known tool named anywhere, not only after 'call'
            name = m.group(1)
            if name in self.known_tools and not self.is_component_name(name):
                add(self.tool(None, name), m.start())
        ordered, seen = [], set()
        for _, cid in sorted(hits):
            if cid not in seen:
                seen.add(cid)
                ordered.append(cid)
        return ordered

    def tool(self, server, name):
        server = (server or self.server_override or self.known_tools.get(name) or self.format["default_mcp_server"]
                  or self.declared_server() or "mcp").lower()
        cid = f"tool:{server}/{name}"
        if cid not in self.tools:
            self.tools[cid] = {"id": cid, "kind": "mcp-tool", "name": f"{server}/{name}", "server": server}
        return cid

    def is_component_name(self, name):
        """A known tool name that is also a component (a script called get_diagram.py) is the component."""
        return any(c["name"] in (name, name + ".py") for c in self.all_components)

    def declared_server(self):
        for path in (self.search_root / ".mcp.json", self.search_root / ".claude-plugin" / "plugin.json"):
            if path.exists():
                try:
                    servers = json.loads(read_text(path)).get("mcpServers") or {}
                except ValueError:
                    continue
                if isinstance(servers, dict) and len(servers) == 1:
                    return next(iter(servers))
        return None

    # ------------------------------------------------------------ text with includes

    def expand(self, text, depth=0):
        """Text with '@path.md' includes that resolve inside the search root appended (frameworks such as GSD)."""
        if depth > 1:
            return text
        extra = []
        for m in INCLUDE.finditer(text):
            parts = Path(m.group(1)).parts
            hits = [p for p in self.search_root.rglob(parts[-1]) if p.is_file()]
            for n in range(2, len(parts) + 1):  # several files of that name: keep those that end with more of the path
                tail = "/".join(parts[-n:])
                narrower = [p for p in hits if p.as_posix().endswith("/" + tail)]
                if not narrower:
                    break
                hits = narrower
            if len(hits) == 1:
                extra.append(f"\n\n<!-- included from {hits[0].relative_to(self.search_root).as_posix()} -->\n" + self.expand(read_text(hits[0]), depth + 1))
        return text + "".join(extra)

    # ------------------------------------------------------------ stages

    def stages(self, depth):
        source = self.format["stage_source"]
        if source == "package-list":
            return []
        reader = {"dispatch-table": self.stages_dispatch, "stage-table": self.stages_table,
                  "headings": self.stages_headings, "commands": self.stages_commands}[source]
        stages = reader()
        self.mark_recovery(stages)
        for stage in stages:
            stage["drillDown"] = (depth == "children" and len(stage.get("instructions", [])) >= 2
                                  and not stage.get("recovery"))
        return stages

    def mark_recovery(self, stages):
        """A recovery stage (a playbook's blocked card) only gets the run unstuck and resumes where it stopped,
        so it belongs inside each stage that can fail, not on the top level. It is a stage that serves a state
        in the format's recovery_states, or one that three or more other stages send their failures to."""
        named = set(self.format.get("recovery_states", []))
        senders = {}
        for stage in stages:
            for outcome in stage["outcomes"]:
                if outcome.get("to") and outcome["to"] != stage["id"]:
                    senders.setdefault(outcome["to"], set()).add(stage["id"])
        recovery = {s["id"] for s in stages
                    if named & set(s.get("states", []))
                    or (not named and len(senders.get(s["id"], ())) >= RECOVERY_SENDERS and not s.get("terminal")
                        and all(o.get("to") in (None, s["id"]) for o in s["outcomes"]))}
        for stage in stages:
            if stage["id"] in recovery:
                stage["recovery"] = True
            for outcome in stage["outcomes"]:
                if outcome.get("to") in recovery and outcome["to"] != stage["id"]:
                    outcome["recovery"] = True

    def entry_text(self):
        entry = self.format["entry"]
        path = self.root / entry if entry and self.input.is_dir() else self.input
        if path.is_dir():
            raise SetupError(f"format {self.format['format']} needs an entry file in {path}")
        if not path.exists():
            raise SetupError(f"{path} does not exist; format {self.format['format']} keeps its stages there")
        self.entry_path = path
        return read_text(path)

    def stages_dispatch(self):
        text = self.entry_text()
        _, body = frontmatter(text)
        dispatch = None
        for header, rows in tables(body):
            if header and "current_state" in header[0].replace("`", "") and len(header) >= 2:
                dispatch = rows
                break
        if dispatch is None:
            raise SetupError(f"{self.entry_path.name} has no state dispatch table (a table whose first column is current_state)")
        taken, stages, by_state, cards = set(), [], {}, {}
        for row in dispatch:
            state = plain(row[0])
            link = re.search(r"\(([^)]+\.md)\)", row[1])
            if link:
                card = (self.root / link.group(1)).resolve()
                if card in cards:
                    by_state[state] = cards[card]
                    continue
                stage = self.read_card(card, taken)
                cards[card] = stage
            else:
                said = plain(row[1])
                name = said.split(";", 1)[1] if said.casefold().startswith("terminal;") else said.split(";")[0]
                name = name.strip()[:1].upper() + name.strip()[1:]
                stage = {"id": stage_id(state, taken), "name": name,
                         "source": self.entry_path.name, "states": [], "terminal": True, "instructions": [],
                         "outcomes": [], "text": plain(row[1])}
            stage["states"].append(state)
            by_state[state] = stage
            stages.append(stage)
        for stage in stages:
            for outcome in stage["outcomes"]:
                target = by_state.get(outcome.pop("state", None) or "")
                outcome["to"] = target["id"] if target else None
        self.human_moments(body, stages, by_state)
        return stages

    def read_card(self, path, taken):
        text = read_text(path)
        _, body = frontmatter(text)
        title = next((H1.match(l).group(1) for l in body.splitlines() if H1.match(l)), path.stem)
        name = re.sub(r"^\d+\s+", "", title).strip()
        stage = {"id": stage_id(path.stem, taken), "name": name, "source": path.relative_to(self.search_root).as_posix(),
                 "states": [], "instructions": [], "outcomes": []}
        for heading, section in sections(body):
            key = heading.casefold()
            if key == "purpose":
                stage["purpose"] = " ".join(section.split())[:1000]
            elif key.startswith("procedure"):
                stage["instructions"] = list_items(section)
            elif key.startswith("outcomes"):
                for line in section.splitlines():
                    match = OUTCOME.match(line)
                    if not match:
                        continue
                    condition, rest = match.group(1).strip(), match.group(2)
                    tr = TR_ID.match(condition)
                    outcome = {"condition": TR_ID.sub("", condition).rstrip(".").strip()}
                    if tr:
                        outcome["id"] = tr.group(1)
                    state = STATE_JSON.search(rest)
                    if state:
                        outcome["state"] = state.group(1)
                    if "Otherwise" in condition or "otherwise" in condition[:12]:
                        outcome["default"] = True
                    stage["outcomes"].append(outcome)
            elif key == "failure":
                stage["failure"] = " ".join(section.split())[:1000]
        stage["text"] = self.expand(body)
        return stage

    def human_moments(self, body, stages, by_state):
        roles = []
        for heading, section in sections(body):
            if heading.casefold().startswith("human moment"):
                roles += [plain(m) for m in re.findall(r"\*\*([^*]+)\*\*", section)]
                by_number = {re.match(r"\d+", Path(s.get("source", "")).name).group(0): s
                             for s in stages if re.match(r"\d+", Path(s.get("source", "")).name)}
                for header, rows in tables(section):
                    for row in rows:
                        where = plain(row[-1])
                        stage = by_number.get(where.zfill(2)) or by_number.get(where) or by_state.get(where)
                        if stage is None and where.casefold() == "terminal":
                            stage = next((s for s in stages if s.get("terminal")), None)
                        if stage is not None:
                            stage.setdefault("humanMoments", []).append(plain(row[0]))
        roles = [re.sub(r"^(the|a|an)\s+", "", r, flags=re.I) for r in roles]
        self.human_roles = common.dedupe([r[0].upper() + r[1:] for r in roles if r])

    def stages_table(self):
        text = self.entry_text()
        _, body = frontmatter(text)
        table = None
        for header, rows in tables(body):
            names = [plain(h).casefold() for h in header]
            if "stage" in names and rows:
                table = (names, rows)
                break
        if table is None:
            raise SetupError(f"{self.entry_path.name} has no stage table (a table with a Stage column)")
        names, rows = table
        col = {n: i for i, n in enumerate(names)}
        bodies = {}
        for heading, section in sections(body):
            match = re.match(r"(?:Stage\s+)?(\d+)[.:]?\s+(.*)", heading)
            if match:
                bodies[match.group(1)] = (match.group(2), section)
        taken, stages = set(), []
        for row in rows:
            number = plain(row[col.get("#", 0)])
            name = plain(row[col["stage"]])
            stage = {"id": stage_id(name, taken), "name": name, "source": self.entry_path.name, "states": [],
                     "instructions": [], "outcomes": []}
            for key, label in (("who does the work", "who"), ("finished when", "finishedWhen")):
                if key in col and col[key] < len(row):
                    stage[label] = plain(row[col[key]])
            confirm = next((i for n, i in col.items() if n.startswith("the person confirms")), None)
            if confirm is not None and confirm < len(row) and plain(row[confirm]):
                stage["humanMoments"] = [plain(row[confirm])]
            if number in bodies:
                section = bodies[number][1]
                stage["instructions"] = list_items(section) or [p for p in (" ".join(x.split()) for x in section.split("\n\n")) if p][:12]
                stage["text"] = section
            stages.append(stage)
        for a, b in zip(stages, stages[1:]):
            a["outcomes"].append({"condition": a.get("finishedWhen") or f"{a['name']} finished", "to": b["id"]})
        if stages:
            stages[-1]["outcomes"].append({"condition": stages[-1].get("finishedWhen") or "Run finished", "to": None})
        self.human_roles = []
        return stages

    def stages_headings(self):
        text = self.entry_text() if self.format["entry"] or self.input.is_file() else ""
        if not text:
            raise SetupError(f"format {self.format['format']} needs an entry file")
        _, body = frontmatter(self.expand(text))
        parts = [(h, s) for h, s in sections(body) if h and h.casefold() not in SKIP_SECTIONS]
        numbered = [(h, s) for h, s in parts if re.match(r"^\d+[.)]?\s", h)]
        taken, stages = set(), []
        if numbered:
            chosen = [(re.sub(r"^\d+[.)]?\s+", "", h), s) for h, s in numbered]
        else:
            with_list = [(h, s) for h, s in parts if list_items(s)]
            if len(with_list) == 1:
                chosen = [(item, item) for item in list_items(with_list[0][1])]
                self.gaps.append({"note": f"Stages are the numbered items of the section '{with_list[0][0]}'; the reader names each one."})
            else:
                chosen = parts
                self.gaps.append({"note": "The package has no numbered stages; every section was listed as a stage, so the reader decides which ones are work."})
        for heading, section in chosen:
            name = plain(heading)[:120]
            stage = {"id": stage_id(name, taken), "name": name, "source": self.entry_path.name, "states": [],
                     "instructions": list_items(section) if section != heading else [], "outcomes": [], "text": section}
            stages.append(stage)
        for a, b in zip(stages, stages[1:]):
            a["outcomes"].append({"condition": f"{a['name']} done", "to": b["id"], "inferred": True})
        if stages:
            stages[-1]["outcomes"].append({"condition": "Done", "to": None, "inferred": True})
        self.human_roles = []
        return stages

    def stages_commands(self):
        files = []
        for rule in self.format["detect"]:
            if rule.startswith("commands") or rule.startswith(".github") or rule.startswith(".cursor"):
                files += sorted(p for p in self.root.glob(rule) if p.is_file())
        if not files:
            raise SetupError(f"no command files found for format {self.format['format']}")
        taken, stages = set(), []
        self.entry_path = files[0]
        for path in files:
            fields, body = frontmatter(read_text(path))
            body = self.expand(body)
            name = fields.get("description") or path.stem
            stage = {"id": stage_id(path.stem.replace(".prompt", ""), taken), "name": plain(name)[:120],
                     "source": path.relative_to(self.search_root).as_posix(), "command": path.stem, "states": [],
                     "instructions": list_items(body), "outcomes": [], "text": body}
            stages.append(stage)
        self.gaps.append({"note": "The commands do not say their order; the reader orders them by what each one needs first."})
        self.human_roles = []
        return stages

    def mentions(self, unused):
        """For each component no stage calls, the package files that still mention it (a script reading a
        data table, an agent following a reference); one mentioned nowhere is dead."""
        files = [p for p in (self.root.rglob("*") if self.input.is_dir() else [self.input])
                 if p.is_file() and p.suffix in TEXT_SUFFIXES and "__pycache__" not in p.parts]
        texts = {}
        for path in files:
            try:
                texts[path] = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
        entry = getattr(self, "entry_path", None)
        for comp in unused:
            own = (self.search_root / comp["path"]).resolve()
            if entry is not None:
                texts.pop(entry, None)
            keys = {comp["name"], Path(comp["path"]).name}
            hits = [p.relative_to(self.search_root).as_posix() for p, t in texts.items()
                    if p.resolve() != own and any(re.search(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", t) for k in keys)]
            if hits:
                comp["mentionedIn"] = hits[:10]

    # ------------------------------------------------------------ the inventory

    def candidates(self):
        rows = []
        for kind in ("skill", "agent", "command"):
            for comp in self.all_components:
                if comp["kind"] == kind:
                    rows.append({"entry": str(Path(comp["path"]).parent if kind == "skill" else comp["path"]),
                                 "kind": kind, "name": comp["name"], "description": comp.get("description", "")})
        return rows

    def inventory(self, depth):
        self.tools = {}
        self.human_roles = []
        self.components()
        stages = self.stages(depth)
        own = {self.input.resolve()} | ({p.resolve() for p in self.root.rglob("*")} if self.input.is_dir() else set())
        exclude = set()
        if self.format["entry"] or self.input.is_file():
            entry = self.root / self.format["entry"] if self.input.is_dir() else self.input
            exclude = {c["id"] for c in self.all_components if (self.search_root / c["path"]).resolve() == entry.resolve()}
        used = {}
        comp_by_id = {c["id"]: c for c in self.all_components}
        for stage in stages:
            text = stage.pop("text", "") or " ".join(stage.get("instructions", []))
            stage["uses"] = self.references(text, exclude)
            # one level down: what the scripts, agents and skills a stage calls use in turn (a data table a script reads)
            indirect = []
            for cid in list(stage["uses"]):
                comp = comp_by_id.get(cid)
                if comp is None or comp["kind"] not in ("script", "agent", "skill", "command"):
                    continue
                inner = read_text(self.search_root / comp["path"])
                for other in self.references(inner, exclude | {cid}):
                    kind = (comp_by_id.get(other) or {}).get("kind")
                    if other not in stage["uses"] and kind in ("data", "template", "reference", "script"):
                        stage["uses"].append(other)
                        indirect.append({"id": other, "via": cid})
            if indirect:
                stage["indirect"] = indirect
            for cid in stage["uses"]:
                used.setdefault(cid, []).append(stage["id"])
        by_id = {c["id"]: c for c in self.all_components}
        by_id.update(self.tools)
        components = [{"id": common.ASSISTANT, "kind": "assistant", "name": "AI Assistant",
                       "description": "The session that runs the package", "usedBy": [s["id"] for s in stages]}]
        servers = {}
        for cid, stage_ids in used.items():
            comp = dict(by_id[cid])
            comp["usedBy"] = stage_ids
            components.append(comp)
            if comp["kind"] == "mcp-tool":
                servers.setdefault(comp["server"], []).extend(s for s in stage_ids if s not in servers.get(comp["server"], []))
        for server, stage_ids in servers.items():
            components.append({"id": f"server:{server}", "kind": "mcp-server", "name": server.replace("-", " ").title(),
                               "server": server, "usedBy": stage_ids})
        unused = [dict(c) for c in self.all_components if c["id"] not in used and c["id"] not in exclude
                  and (self.search_root / c["path"]).resolve() in own]
        self.mentions(unused)
        classified = {(self.search_root / c["path"]).resolve() for c in self.all_components}
        unclassified = []
        if self.input.is_dir():
            for path in sorted(self.root.rglob("*")):
                rel = path.relative_to(self.root)
                if not path.is_file() or any(p.startswith((".", "__pycache__", "_workspace")) for p in rel.parts):
                    continue
                if path.resolve() in classified or path.resolve() == getattr(self, "entry_path", Path("/")).resolve():
                    continue
                if any((s.get("source") or "") == path.relative_to(self.search_root).as_posix() for s in stages):
                    continue
                unclassified.append(rel.as_posix())
        name = self.input.name if self.input.is_dir() else self.input.stem
        fields = {}
        if getattr(self, "entry_path", None) and self.entry_path.suffix == ".md":
            fields, _ = frontmatter(read_text(self.entry_path))
        inv = {
            "schemaVersion": "1.0",
            "package": {"name": fields.get("name") or name, "path": str(self.input), "format": self.format["format"],
                        "stageSource": self.format["stage_source"], "tested": self.format["tested"] == "yes"},
            "stages": stages,
            "components": components,
            "humanRoles": self.human_roles,
            "unused": [{k: c[k] for k in ("id", "kind", "path", "mentionedIn") if c.get(k)} for c in unused],
            "unclassified": unclassified[:200],
            "gaps": self.gaps,
        }
        if fields.get("description"):
            inv["package"]["description"] = fields["description"][:2000]
        if not stages:
            inv["gaps"].append({"note": "No stages were found where this format keeps them; the reader works from the files."})
        return inv


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Inventory an agent package: its format, stages and the components each stage calls.")
    parser.add_argument("package", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--entry", help="for a plugin: the skill folder, agent or command file to draw, relative to the plugin")
    parser.add_argument("--depth", choices=("top", "children"), default="children",
                        help="children (the default): stages with two or more instructions get a level of their own")
    parser.add_argument("--server", help="name of the MCP server that bare tool names belong to, when the format does not say")
    args = parser.parse_args(argv)
    try:
        pkg = Package(args.package, args.entry, args.server)
        if pkg.format["stage_source"] == "package-list":
            pkg.tools = {}
            pkg.components()
            rows = pkg.candidates()
            common.write_json(args.out, {"schemaVersion": "1.0", "package": {"name": pkg.root.name, "path": str(pkg.root),
                              "format": pkg.format["format"], "stageSource": "package-list", "tested": True},
                              "candidates": rows})
            print(f"{pkg.root.name} is a plugin ({pkg.format['format']}) holding {len(rows)} package(s); run again with --entry naming one:")
            for row in rows:
                print(f"  --entry {row['entry']}   ({row['kind']} {row['name']})")
            return 3
        inv = pkg.inventory(args.depth)
        problems = common.shape_errors(inv)
        if problems:
            raise SetupError("the inventory does not match its schema:\n  " + "\n  ".join(problems[:10]))
        common.write_json(args.out, inv)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    kinds = {}
    for comp in inv["components"]:
        kinds[comp["kind"]] = kinds.get(comp["kind"], 0) + 1
    drill = sum(1 for s in inv["stages"] if s.get("drillDown"))
    print(f"{inv['package']['name']}: format {inv['package']['format']}"
          f"{'' if inv['package']['tested'] else ' (adapter not yet tested on a real package)'}; "
          f"{len(inv['stages'])} stage(s), {drill} with a level of their own; "
          + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) + "; "
          f"{len(inv['humanRoles'])} human role(s); {sum(1 for u in inv['unused'] if not u.get('mentionedIn'))} unused, "
          f"{sum(1 for u in inv['unused'] if u.get('mentionedIn'))} called only by other files, {len(inv['unclassified'])} unclassified file(s). "
          f"Written to {args.out}.")
    for gap in inv["gaps"]:
        print(f"GAP {gap['note']}")
    return 0 if inv["stages"] else 1


if __name__ == "__main__":
    sys.exit(main())
