"""Assemble the solution overview document from the run's files.

    python3 build_solution_overview.py ENG [--template FILE]
    python3 build_solution_overview.py ENG --check   # check the sources and the prose, write nothing

Builds ENG/overview/<project>-solution-overview.docx from the template
(templates/solution-overview.docx unless --template names another) and the
sections of data/solution-overview-sections.csv that are on. Every table and
fact comes from the run's files (execution-state.json, model.json, derive/,
access-matrix.csv, check/scores.json, evidence/targets.json, inventory.json);
the gaps add execution-state.json's evidence.gaps to those of the model, the
targets and the access matrix, each line once; the prose comes from
overview/prose.json (the solution-overview-writer's file); pictures from
overview/images/ (render_diagram.py). The access matrix is not listed: the
document names its file and sums it up. Needs python-docx.

Refuses (exit 1) when a source a section needs is missing or the prose does
not fit the model: a byArea entry for a step that is not top level, a missing
data model summary for an area that uses entities or integration summary for
an area that integrations serve, more than MAX_DIRECTIONS solution direction
bullets for an area, or a paragraph longer than MAX_SENTENCES
sentences (paragraphs are separated by a blank line). Prints a WROTE line for
the Word file.
"""

import argparse
import datetime
import re
import sys
from collections import OrderedDict
from pathlib import Path

from common import PLUGIN, SECTIONS_CSV, SKILL, SetupError, eng_path, load_json, process_areas, read_csv, shape_errors, slug

TEMPLATE = SKILL / "templates" / "solution-overview.docx"
LOGO = SKILL / "assets" / "elements-logo.png"
CRUD_WORDS = {"C": "Create", "R": "Read", "U": "Edit", "D": "Delete"}
MAX_SENTENCES = 6  # the method owner's paragraph limit for the document
MAX_DIRECTIONS = 4  # the limit on solution direction bullets per area
SENTENCE_END = re.compile(r"[.!?][)\"'”’]*\s+(?=[A-Z0-9\"'(“‘])")
KIND_WORDS = {"standard": "Standard", "custom": "Custom (exists in the org)", "proposed": "Proposed (new)",
              "external": "In another system"}


class Doc:
    """Thin helpers over python-docx so the sections read as content."""

    def __init__(self, template):
        from docx import Document
        from docx.shared import Pt
        self.Pt = Pt
        self.doc = Document(str(template)) if template and Path(template).exists() else Document()

    def heading(self, text, level=1):
        self.doc.add_heading(text, level=level)

    def para(self, text, bold=False, italic=False, size=None, align=None):
        p = self.doc.add_paragraph()
        run_ = p.add_run(text)
        run_.bold, run_.italic = bold, italic
        if size:
            run_.font.size = self.Pt(size)
        if align == "center":
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return p

    def paras(self, text):
        """One paragraph per block of text separated by a blank line."""
        for block in paragraphs(text):
            self.para(block)

    def bullets(self, items):
        for item in items:
            self.doc.add_paragraph(str(item), style="List Bullet")

    def link(self, label, url, before=""):
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        p = self.doc.add_paragraph(before)
        rel = p.part.relate_to(url, RT.HYPERLINK, is_external=True)
        hyper = OxmlElement("w:hyperlink")
        hyper.set(qn("r:id"), rel)
        r = OxmlElement("w:r")
        props = OxmlElement("w:rPr")
        for tag, attr in (("w:color", "0563C1"), ("w:u", "single")):
            el = OxmlElement(tag)
            el.set(qn("w:val"), attr)
            props.append(el)
        r.append(props)
        t = OxmlElement("w:t")
        t.text = label
        r.append(t)
        hyper.append(r)
        p._p.append(hyper)

    def table(self, header, rows):
        table = self.doc.add_table(rows=1, cols=len(header))
        try:
            table.style = "Table Grid"
        except Exception:
            pass
        for cell, text in zip(table.rows[0].cells, header):
            cell.text = ""
            cell.paragraphs[0].add_run(str(text)).bold = True
        for row in rows:
            cells = table.add_row().cells
            for cell, text in zip(cells, row):
                cell.text = "" if text is None else str(text)
        self.doc.add_paragraph()

    def picture(self, path, width_cm=16, height_cm=None):
        """At most width_cm wide and height_cm tall, and never blown up past about its own size, so a picture of
        two boxes stays small."""
        from docx.image.image import Image
        from docx.shared import Cm
        img = Image.from_file(str(path))
        w, h = max(img.px_width, 1), max(img.px_height, 1)
        width = min(width_cm, w / 60)
        if height_cm:
            width = min(width, height_cm * w / h)
        self.doc.add_picture(str(path), width=Cm(max(width, 4)))

    def page_break(self):
        self.doc.add_page_break()


def paragraphs(text):
    return [" ".join(block.split()) for block in re.split(r"\n\s*\n", str(text or "")) if block.strip()]


def sentences(paragraph):
    return len([part for part in SENTENCE_END.split(paragraph) if part.strip()])


def long_paragraphs(prose):
    """(where, sentence count) for every paragraph of the prose longer than MAX_SENTENCES sentences."""
    found = []

    def visit(value, where):
        if isinstance(value, str):
            for n, block in enumerate(paragraphs(value), 1):
                count = sentences(block)
                if count > MAX_SENTENCES:
                    found.append((f"{where} paragraph {n}", count))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                visit(item, f"{where}[{i}]")
        elif isinstance(value, dict):
            for key, item in value.items():
                if key != "activity":
                    visit(item, f"{where}.{key}" if where else key)
    visit(prose, "")
    return found


def crud_words(letters):
    return ", ".join(CRUD_WORDS[ch] for ch in "CRUD" if ch in letters)


def load_sources(eng):
    need = OrderedDict([
        ("state", "execution-state.json"), ("model", "model.json"), ("dm", "derive/data-model.json"),
        ("it", "derive/integrations.json"), ("access", "derive/access.json"), ("scores", "check/scores.json"),
        ("prose", "overview/prose.json")])
    src, missing = {}, []
    for key, rel in need.items():
        path = eng_path(eng, *rel.split("/"))
        if not path.exists():
            missing.append(rel)
        else:
            src[key] = load_json(path, rel)
    if not eng_path(eng, "access-matrix.csv").exists():
        missing.append("access-matrix.csv")
    targets = eng_path(eng, "evidence", "targets.json")
    src["targets"] = load_json(targets, "evidence/targets.json") if targets.exists() else {"gaps": []}
    inventory = eng_path(eng, "inventory.json")
    src["inventory"] = load_json(inventory, "inventory.json") if inventory.exists() else {}
    return src, missing


def document_gaps(model, targets, access, state):
    """The document's gaps: the model's, the targets', the access matrix's, then those the cards wrote only to
    execution-state.json evidence.gaps (such as get_access failures), each line once."""
    gaps = [g["note"] for g in model.get("gaps", [])] + list(targets.get("gaps", [])) + \
           [g["note"] for g in access.get("gaps", [])]
    for g in (state.get("evidence") or {}).get("gaps", []):
        line = (g.get("note") or "; ".join(f"{k}: {v}" for k, v in g.items())) if isinstance(g, dict) else str(g)
        if line and line not in gaps:
            gaps.append(line)
    return gaps


def prose_errors(src):
    errors = shape_errors(src["prose"], "prose.schema.json")
    if errors:
        return errors
    areas = {a["activity"]: a for a in process_areas(src["model"], src["it"], src["inventory"])}
    for item in src["prose"]["byArea"]:
        area = areas.get(item["activity"])
        if not area:
            errors.append(f"byArea names '{item['activity']}', which is not a top-level step")
            continue
        if area["entities"] and not item.get("dataModelSummary"):
            errors.append(f"byArea '{item['activity']}' ({area['name']}) uses entities but has no dataModelSummary")
        if len(item["solutionDirection"]) > MAX_DIRECTIONS:
            errors.append(f"byArea '{item['activity']}' ({area['name']}) has {len(item['solutionDirection'])} solutionDirection "
                          f"bullets; keep the {MAX_DIRECTIONS} that matter most")
        if area["integrations"] and not item.get("integrationSummary"):
            errors.append(f"byArea '{item['activity']}' ({area['name']}) is served by integrations but has no integrationSummary")
    for where, count in long_paragraphs(src["prose"]):
        errors.append(f"{where} has {count} sentences; split it into paragraphs of at most {MAX_SENTENCES} "
                      "sentences, separated by a blank line")
    return errors


def build(eng, template, check_only=False):
    src, missing = load_sources(eng)
    if missing:
        for rel in missing:
            print(f"ERROR missing {rel}")
        print("REFUSED the document needs every source above; finish the card that writes it")
        return 1
    errors = prose_errors(src)
    if errors:
        for line in errors:
            print(f"ERROR overview/prose.json {line}")
        print("REFUSED send the errors back to the solution-overview-writer")
        return 1
    if check_only:
        print("CHECKED the sources and the prose fit; the document can be built")
        return 0
    try:
        d = Doc(template)
    except ImportError:
        print("SETUP python-docx is not installed: python3 -m pip install python-docx", file=sys.stderr)
        return 2
    state, model, dm, it, access, prose = (src[k] for k in ("state", "model", "dm", "it", "access", "prose"))
    slots = state["slots"]
    project = slots.get("project_name") or model["meta"]["title"]
    source = slots.get("source_map") or {}
    lower = state.get("check", {}).get("confidence") == "lower"
    acts = {a["id"]: a for a in model["activities"]}
    roles = {r["id"]: r for r in model.get("roles", [])}
    systems = {s["id"]: s for s in model.get("systems", [])}
    entities = {e["id"]: e for e in model.get("entities", [])}
    dm_extra = {e["id"]: e for e in dm["entities"]}
    areas = {a["activity"]: a for a in process_areas(model, it, src["inventory"])}
    deliver = state.get("deliverables", {})
    patterns = {r["pattern_id"]: r["short_label"] for r in read_csv(PLUGIN / "data" / "integration-patterns.csv", ["pattern_id", "short_label"])}
    images = eng_path(eng, "overview", "images")
    sections = [r for r in read_csv(SECTIONS_CSV, ["order", "section_id", "title", "on", "content"]) if r["on"] == "yes"]
    sections.sort(key=lambda r: int(r["order"]))
    numbered = [r for r in sections if r["section_id"] not in ("delivered-with", "title", "contents")]
    today = datetime.date.today().isoformat()

    def title_of(sid):
        n = next((i for i, r in enumerate(numbered, 1) if r["section_id"] == sid), None)
        r = next(r for r in sections if r["section_id"] == sid)
        return r["title"] if r["title"].startswith("Appendix") else f"{n}. {r['title']}"

    def picture(name):
        path = images / f"{name}.png"
        if path.exists():
            d.picture(path, height_cm=10)
            return True
        return False

    def map_links(kind):
        if kind == "data-model":
            for m in deliver.get("data_model_maps", []):
                d.link(m.get("name") or "Data model in Elements", m["url"], "Live diagram: ")
        elif deliver.get("architecture_map"):
            m = deliver["architecture_map"]
            d.link(m.get("name") or "System architecture in Elements", m["url"], "Live diagram: ")
        if source.get("url"):
            d.link(source.get("name") or "Source process map", source["url"], "Derived from: ")

    for sec in sections:
        sid = sec["section_id"]
        if sid == "delivered-with":
            d.para("")
            d.para("Delivered with", size=28, align="center")
            if LOGO.exists():
                from docx.shared import Cm
                d.doc.add_picture(str(LOGO), width=Cm(8))
                d.doc.paragraphs[-1].alignment = 1
            else:
                d.para("Elements.cloud", bold=True, size=32, align="center")
            d.page_break()
        elif sid == "title":
            logo = slots.get("customer_logo")
            if logo and Path(logo).exists():
                d.picture(logo, 5)
            if slots.get("customer_name"):
                d.para(slots["customer_name"], bold=True, size=20)
            d.para(project, size=26)
            d.para("High-level solution design", size=18)
            d.para(today, bold=True)
            d.para("Version 0.1 (generated for review)")
            if slots.get("prepared_by"):
                d.para(f"Prepared by {slots['prepared_by']}")
            d.page_break()
        elif sid == "contents":
            d.heading("Contents", 1)
            for r in numbered:
                d.para(title_of(r["section_id"]))
            d.page_break()
        elif sid == "overview":
            d.heading(title_of(sid), 1)
            d.heading("Purpose", 2)
            d.paras(prose["purpose"])
            d.heading("Target audience", 2)
            d.bullets(prose["audience"])
            d.heading("Context", 2)
            d.paras(prose["context"])
            d.heading("Target system and source of reference", 2)
            route = {"org": "the Salesforce org connected to Elements", "documentation": "the vendor's official documentation"}
            d.para(f"Target system: {slots.get('target_system')}. Matched against "
                   f"{route.get(slots.get('reference_source'), slots.get('reference_source'))}.")
            d.heading("How this design was produced", 2)
            scores = src["scores"]
            d.para("Every level of the source process map was read and checked for whether a design can be derived from it "
                   f"(pass mark {scores['passMark']:g} out of 10). The data the process handles was worked out from the nouns "
                   "and object resources of its steps, the systems from its system resources and handoffs, and the access "
                   "each step needs from its verbs. The solution architect reviewed and approved the result before the "
                   "diagrams were drawn.")
            if lower:
                d.para("Confidence: lower. The source map did not pass the derivability check and the solution architect "
                       f"chose to continue; read the design with that in mind (see {title_of('appendix-check')}).", bold=True)
            d.heading("Document change log", 2)
            d.table(["Date", "Author", "Version", "Change"],
                    [[today, slots.get("prepared_by") or "", "0.1", "Generated by process-led design from the source process map"]])
            d.heading("Contributors and reviewers", 2)
            rows = [[slots.get("prepared_by") or "", "Prepared"]]
            if state.get("review", {}).get("approved_by"):
                rows.append([state["review"]["approved_by"], f"Approved the derived design on {state['review'].get('approved_on') or ''}"])
            d.table(["Name", "Role"], rows)
        elif sid == "process":
            d.heading(title_of(sid), 1)
            if source.get("url"):
                d.link(source.get("name") or "Source process map", source["url"], "Source process map: ")
            d.paras(prose["summary"])
            top = [a for a in model["activities"] if not a.get("parent")]
            d.table(["Step", "Who does it"],
                    [[a["name"], ", ".join(roles[r["role"]]["name"] for r in a.get("roles", []) if r["role"] in roles)] for a in top])
            d.heading("Personas", 2)
            people = [r for r in model.get("roles", []) if r["kind"] == "human"]
            count = {r["id"]: sum(1 for a in model["activities"] for x in a.get("roles", []) if x["role"] == r["id"]) for r in people}
            d.table(["Persona", "Steps they take part in"], [[r["name"], count[r["id"]]] for r in people])
        elif sid == "by-area":
            d.heading(title_of(sid), 1)
            data_maps = deliver.get("data_model_maps", [])
            for item in prose["byArea"]:
                area = areas[item["activity"]]
                aid = area["activity"]
                d.heading(area["name"], 2)
                picture(f"area-{aid}-process")
                if area["level"] and area["level"].get("url"):
                    d.link(area["level"].get("title") or area["name"], area["level"]["url"], "Process level in Elements: ")
                d.paras(item["whatHappens"])
                if area["entities"]:
                    d.heading("Data model", 3)
                    picture(f"area-{aid}-data-model")
                    for m in data_maps:
                        d.link(m.get("name") or "Data model in Elements", m["url"], "Full data model: ")
                    d.paras(item.get("dataModelSummary"))
                if area["integrations"]:
                    d.heading("Integrations", 3)
                    picture(f"area-{aid}-architecture")
                    if deliver.get("architecture_map"):
                        m = deliver["architecture_map"]
                        d.link(m.get("name") or "System architecture in Elements", m["url"], "Full system architecture: ")
                    d.paras(item.get("integrationSummary"))
                d.para("Solution direction", bold=True)
                d.bullets(item["solutionDirection"])
        elif sid == "data-model":
            d.heading(title_of(sid), 1)
            pics = sorted(images.glob("data-model*.png")) if images.exists() else []
            for pic in pics:
                d.picture(pic)
            map_links("data-model")
            d.para("Grey cards are standard objects, purple cards custom objects that exist in the org, amber cards "
                   "proposed objects that do not exist yet.", italic=True)
            d.table(["Entity", "Object (API name)", "Kind", "Derived from", "Steps"],
                    [[e["name"], e.get("apiName", ""), KIND_WORDS.get(e.get("kind"), e.get("kind", "")),
                      ", ".join(dm_extra.get(e["id"], {}).get("sourceNouns", [])), len(dm_extra.get(e["id"], {}).get("steps", []))]
                     for e in model["entities"]])
            for e in model["entities"]:
                if e.get("kind") in ("custom", "proposed") and e.get("fields"):
                    d.para(f"{e['name']} object", bold=True)
                    d.table(["Label", "API name", "Type"], [[f["name"], f.get("apiName", ""), f.get("type", "")] for f in e["fields"]])
            if prose["dataModelNotes"]:
                d.bullets(prose["dataModelNotes"])
        elif sid == "integrations":
            d.heading(title_of(sid), 1)
            pic = images / "architecture.png"
            if pic.exists():
                d.picture(pic)
            map_links("architecture")
            status = {i["id"]: i for i in it["integrations"]}
            d.table(["From", "To", "Data", "Pattern", "Timing", "Mechanism", "Status"],
                    [[systems[i["from"]]["name"], systems[i["to"]]["name"], status.get(i.get("id"), {}).get("data", i.get("label", "")),
                      patterns.get(i.get("pattern"), i.get("pattern", "")), (i.get("timing") or "").capitalize(), i.get("technology", ""),
                      (status.get(i.get("id"), {}).get("status") or "").capitalize()] for i in model["integrations"]])
            if it["manualHandoffs"]:
                d.para("Handoffs left manual", bold=True)
                d.table(["Step", "From", "To", "Data", "Note"],
                        [[acts[h["step"]]["name"], h.get("from", ""), h.get("to", ""), h["data"], h["note"]] for h in it["manualHandoffs"]])
            if prose["integrationNotes"]:
                d.bullets(prose["integrationNotes"])
        elif sid == "security":
            d.heading(title_of(sid), 1)
            rows_ = access["rows"]
            name_of = lambda rid: (roles.get(rid) or systems.get(rid) or {"name": rid})["name"]
            words = {"create": "New", "extend": "Update", "reuse": "Existing"}
            counts = {k: sum(1 for c in access["controllers"] if c["action"] == k) for k in words}
            users = sorted({name_of(r["resource"]) for r in rows_ if r.get("integrationUser")})
            matrix_file = "access-matrix.csv"
            d.para(f"The full data access matrix is delivered with this document as a separate file, {matrix_file}, "
                   "which opens in Excel. For every process step it gives who does the step, each object the step "
                   "touches and the create, read, edit or delete access the step needs, with the permission controller "
                   "that grants it.")
            d.para(f"In total, {len(rows_)} access rows cover {len({r['step'] for r in rows_})} process steps. "
                   f"{len({r['resource'] for r in rows_})} personas and systems need access to "
                   f"{len({r['entity'] for r in rows_})} objects through {len(access['controllers'])} permission "
                   f"controllers: {counts['create']} new, {counts['extend']} updated and {counts['reuse']} existing. "
                   + (f"Integration users are needed for {', '.join(users)}." if users else "No integration user is needed."))
            deleters = OrderedDict()
            for r in rows_:
                if "D" in r["crud"]:
                    deleters.setdefault(entities[r["entity"]]["name"], set()).add(r["controller"])
            if deleters:
                d.para("Delete access, which deserves a second look, is granted on "
                       + "; ".join(f"{o} (by {', '.join(sorted(c))})" for o, c in deleters.items()) + ".")
            covers = {c["name"]: len({r["entity"] for r in rows_ if r["controller"] == c["name"]}) for c in access["controllers"]}
            d.table(["Persona", "Permission controller", "Type", "New or update", "Objects it covers"],
                    [[", ".join(name_of(p) for p in c["personas"]), c["name"], c["type"],
                      words[c["action"]] + (f" ({c['existing']})" if c.get("existing") else ""), covers[c["name"]]]
                     for c in access["controllers"]])
            if prose["securityNotes"]:
                d.bullets(prose["securityNotes"])
        elif sid == "decisions":
            d.heading(title_of(sid), 1)
            log = state.get("decisions_log", [])
            if log:
                d.heading("Decisions", 2)
                d.table(["Date", "Who", "Decision", "Evidence"],
                        [[x.get("date", ""), x.get("who", ""), x.get("what", ""), x.get("evidence", "")] for x in log])
            if prose["assumptions"]:
                d.heading("Assumptions", 2)
                d.bullets(prose["assumptions"])
            inferred = [f"{x['name']} (worked out, not stated in the map)" for sec_ in ("entities", "systems")
                        for x in model.get(sec_, []) if x.get("inferred")]
            if inferred:
                d.heading("Inferred items", 2)
                d.bullets(inferred)
            gaps = document_gaps(model, src["targets"], access, state)
            if gaps:
                d.heading("Gaps and open questions", 2)
                d.bullets(gaps)
        elif sid == "appendix-traceability":
            d.heading(title_of(sid), 1)
            rows = []
            for a in model["activities"]:
                ents = [entities[r]["name"] for r in a.get("uses", []) if r in entities]
                syss = [systems[r]["name"] for r in a.get("uses", []) if r in systems]
                rows.append([a["id"].split("-")[1] if a["id"].count("-") >= 2 else "", a["name"], ", ".join(ents), ", ".join(syss)])
            d.table(["Level", "Step", "Objects", "Systems"], rows)
        elif sid == "appendix-check":
            d.heading(title_of(sid), 1)
            d.table(["Level", "Title", "Score", "Result"],
                    [[l["levelNumber"], l["title"], l["score"], "Pass" if l["passed"] else "Below the pass mark"] for l in src["scores"]["levels"]])
            for l in src["scores"]["levels"]:
                if l["findings"]:
                    d.para(f"Level {l['levelNumber']} {l['title']}", bold=True)
                    d.bullets([f"{f['text']}: {f.get('why') or f.get('rule_text', '')}" + (f" Suggested: {f['fix']}" if f.get("fix") else "")
                               for f in l["findings"]])
    out_dir = eng_path(eng, "overview")
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"{slug(project, 60)}-solution-overview.docx"
    d.doc.save(str(docx_path))
    print(f"WROTE {docx_path}")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("eng")
    parser.add_argument("--template", default=str(TEMPLATE))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv[1:])
    try:
        return build(args.eng, args.template, args.check)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
