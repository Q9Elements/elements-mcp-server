"""Picture the diagrams for the solution overview.

    python3 render_diagram.py ENG

Writes PNG pictures into ENG/overview/images/:

- <name>.png for every drawing work folder ENG/drawing/<name>/ that holds a
  layout preview (preview.svg, written by the drawing skill's plan step; the
  layout check has confirmed the drawn map matches the plan);
- for every top-level step of model.json (a process area), named
  area-<step id>-<kind>.png:
  - process: the step's drill-down level of the source map, drawn from its
    saved read (levels/<levelNumber>.json, read with its layout);
  - data-model: the entities the area's steps use and the relationships
    between them, planned offline with the plugin's data model layout
    (work folder ENG/overview/areas/<step id>/data-model/);
  - architecture: when integrations serve the area's steps, those
    integrations and the systems they join, planned offline the same way
    (ENG/overview/areas/<step id>/architecture/).
  An area with no drill-down level, no entities or no integrations has no
  picture of that kind, and nothing is printed for it.

LibreOffice converts each SVG when it is installed; otherwise the script draws
the SVG's boxes, lines and text itself with Pillow. Lines are drawn straight
or with one bend between the sides the layout gives; Elements routes them in
the editor, so the live diagram (linked beside every picture) is the reference.

Prints one PICTURED or NO PICTURE line per picture and exits 0; a NO PICTURE
line says what failed. A diagram it cannot picture, a malformed preview
included, is reported, never fatal, because the document still links to it.
"""

import html
import re
import shutil
import sys
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

from common import PLUGIN, SetupError, eng_path, load_json, office_binary, process_areas, run, write_json
from design import architecture_model, data_model_part

SCALE = 1.5  # PNG pixels per SVG unit when Pillow draws the picture, so it stays sharp at the Word page's width


def with_office(svg, out):
    """Returns (pictured, why not)."""
    office = office_binary()
    if not office:
        return False, "LibreOffice is not installed"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / (out.stem + ".svg")
            shutil.copy(svg, src)
            result = run([office, "--headless", "--convert-to", "png", "--outdir", tmp, str(src)])
            made = Path(tmp) / (out.stem + ".png")
            if result.returncode != 0 or not made.exists():
                return False, "LibreOffice could not convert it"
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(made, out)
    except Exception as exc:  # a picture is never worth stopping the run for
        return False, f"LibreOffice failed ({type(exc).__name__}: {exc})"
    return True, None


def colour(value, default):
    if not value or value == "none":
        return None if value == "none" else default
    return value


def with_pillow(svg, out):
    """Returns (pictured, why not)."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    except ImportError:
        return False, "Pillow is not installed"
    try:
        draw_with_pillow(svg, out)
    except Exception as exc:  # a malformed preview is reported, never fatal
        return False, f"Pillow could not draw it ({type(exc).__name__}: {exc})"
    return True, None


def draw_with_pillow(svg, out):
    from PIL import Image, ImageDraw, ImageFont
    root = ET.parse(svg).getroot()
    ns = re.match(r"\{.*\}", root.tag)
    ns = ns.group(0) if ns else ""
    vb = [float(v) for v in (root.get("viewBox") or "0 0 1000 700").split()]
    ox, oy, w, h = vb
    img = Image.new("RGB", (int(w * SCALE), int(h * SCALE)), "white")
    draw = ImageDraw.Draw(img)

    def pt(x, y):
        return ((float(x) - ox) * SCALE, (float(y) - oy) * SCALE)

    def font(size, bold):
        for name in (["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "Arial.ttf"]):
            try:
                return ImageFont.truetype(name, int(size * SCALE))
            except OSError:
                continue
        return ImageFont.load_default()

    for el in root.iter():
        tag = el.tag.replace(ns, "")
        if tag == "rect":
            x, y = pt(el.get("x", 0), el.get("y", 0))
            x2, y2 = x + float(el.get("width", 0)) * SCALE, y + float(el.get("height", 0)) * SCALE
            draw.rounded_rectangle([x, y, x2, y2], radius=float(el.get("rx", 0)) * SCALE,
                                   fill=colour(el.get("fill"), None), outline=colour(el.get("stroke"), None),
                                   width=max(1, int(float(el.get("stroke-width", 1)) * SCALE)))
        elif tag == "circle":
            cx, cy = pt(el.get("cx"), el.get("cy"))
            r = float(el.get("r", 0)) * SCALE
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour(el.get("fill"), "#333333"))
        elif tag == "line":
            draw.line([pt(el.get("x1"), el.get("y1")), pt(el.get("x2"), el.get("y2"))],
                      fill=colour(el.get("stroke"), "#5a6b7b"), width=max(1, int(SCALE)))
        elif tag == "polyline":
            nums = [float(v) for v in re.split(r"[ ,]+", (el.get("points") or "").strip()) if v]
            points = [pt(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
            if len(points) > 1:
                draw.line(points, fill=colour(el.get("stroke"), "#5a6b7b"), width=max(1, int(1.5 * SCALE)))
                ends = []
                if el.get("marker-end"):
                    ends.append((points[-2], points[-1]))
                if el.get("marker-start"):
                    ends.append((points[1], points[0]))
                for (ax, ay), (bx, by) in ends:
                    dx, dy = bx - ax, by - ay
                    length = max((dx * dx + dy * dy) ** 0.5, 1)
                    ux, uy = dx / length, dy / length
                    s = 8 * SCALE
                    draw.polygon([(bx, by), (bx - ux * s - uy * s / 2, by - uy * s + ux * s / 2),
                                  (bx - ux * s + uy * s / 2, by - uy * s - ux * s / 2)], fill="#5a6b7b")
        elif tag == "text" and (el.text or "").strip():
            x, y = pt(el.get("x", 0), el.get("y", 0))
            size = float(el.get("font-size", 12))
            f = font(size, el.get("font-weight") == "bold")
            text = el.text.strip()
            anchor = {"middle": "ms", "end": "rs"}.get(el.get("text-anchor"), "ls")
            draw.text((x, y), text, fill=colour(el.get("fill"), "#000000"), font=f, anchor=anchor)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


# ---------------------------------------------------------------- a process level from its saved read

ARROW = ("<defs><marker id='arrow' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' orient='auto'>"
         "<path d='M0,0 L10,5 L0,10 z' fill='#5a6b7b'/></marker></defs>")
STEP = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


def _side_point(box, side):
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    return {"left": (x, y + h / 2), "right": (x + w, y + h / 2), "top": (x + w / 2, y), "bottom": (x + w / 2, y + h)}[side]


def _sides(a, b):
    """The sides a line from box a to box b leaves and enters by, when the read does not give them."""
    if b["x"] >= a["x"] + a["w"]:
        return "right", "left"
    if b["x"] + b["w"] <= a["x"]:
        return "bottom", "bottom"
    return ("bottom", "top") if b["y"] >= a["y"] else ("top", "bottom")


def _text_lines(out, x, y, lines, size, anchor="start", weight=None, fill="#1f2a36", leading=1.25):
    for i, text in enumerate(lines):
        bold = f" font-weight='{weight}'" if weight else ""
        out.append(f"<text x='{x:.0f}' y='{y + i * size * leading:.0f}' font-size='{size}' fill='{fill}' "
                   f"text-anchor='{anchor}'{bold}>{html.escape(text)}</text>")


def _wrap(text, width, most):
    lines = textwrap.wrap(" ".join(str(text or "").split()), width) or [""]
    if len(lines) > most:
        lines = lines[:most]
        lines[-1] = lines[-1][: max(1, width - 1)].rstrip() + "…"
    return lines


def process_level_svg(read):
    """An SVG of one UPN level from a get_diagram read with its layout, or None when the read has no layout."""
    diagram = read.get("diagram") or {}
    boxes = {a["key"]: a for a in diagram.get("activities", []) if all(k in a for k in ("x", "y", "w", "h"))}
    if not boxes:
        return None
    notes = [n for n in diagram.get("notes", []) if all(k in n for k in ("x", "y", "w", "h"))]
    body, extents = [], [(b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]) for b in boxes.values()]
    extents += [(n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"]) for n in notes]
    taken = {}  # box key -> sides already used, so a line with a free end does not lie on top of another

    def free_side(box, given, order):
        if given:
            return given
        used = taken.get(box["key"], set())
        return next((side for side in order if side not in used), order[0])

    for line in diagram.get("lines", []):
        a, b = boxes.get((line.get("from") or {}).get("activity")), boxes.get((line.get("to") or {}).get("activity"))
        if a and b:
            fs, ts = _sides(a, b)
            taken.setdefault(a["key"], set()).add(line.get("fromSide") or fs)
            taken.setdefault(b["key"], set()).add(line.get("toSide") or ts)
    for line in diagram.get("lines", []):
        src, dst = line.get("from") or {}, line.get("to") or {}
        a, b = boxes.get(src.get("activity")), boxes.get(dst.get("activity"))
        if not a and not b:
            continue
        if a and b:
            fs, ts = _sides(a, b)
            fs, ts = line.get("fromSide") or fs, line.get("toSide") or ts
            p, q = _side_point(a, fs), _side_point(b, ts)
            p1 = (p[0] + STEP[fs][0] * 20, p[1] + STEP[fs][1] * 20)
            q1 = (q[0] + STEP[ts][0] * 20, q[1] + STEP[ts][1] * 20)
            corner = (q1[0], p1[1]) if fs in ("left", "right") else (p1[0], q1[1])
            pts = [p, p1, corner, q1, q]
            mid = ((p1[0] + q1[0]) / 2, min(p1[1], q1[1]) - 6) if fs in ("left", "right") else ((p1[0] + q1[0]) / 2, (p1[1] + q1[1]) / 2)
            free = None
        elif a:
            fs = free_side(a, line.get("fromSide"), ("right", "bottom", "top"))
            taken.setdefault(a["key"], set()).add(fs)
            p = _side_point(a, fs)
            q = (p[0] + STEP[fs][0] * 110, p[1] + STEP[fs][1] * 110)
            pts, mid, free = [p, q], ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 - 6), (q, dst)
        else:
            ts = free_side(b, line.get("toSide"), ("left", "top", "bottom"))
            taken.setdefault(b["key"], set()).add(ts)
            q = _side_point(b, ts)
            p = (q[0] + STEP[ts][0] * 110, q[1] + STEP[ts][1] * 110)
            pts, mid, free = [p, q], ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 - 6), (p, src)
        body.append("<polyline fill='none' stroke='#5a6b7b' stroke-width='1.5' marker-end='url(#arrow)' points='"
                    + " ".join(f"{x:.0f},{y:.0f}" for x, y in pts) + "'/>")
        if free:
            (fx, fy), end = free
            if end.get("terminator"):
                body.append(f"<circle cx='{fx:.0f}' cy='{fy:.0f}' r='7' fill='#1f2a36'/>")
            elif end.get("offPage"):
                body.append(f"<rect x='{fx - 6:.0f}' y='{fy - 6:.0f}' width='12' height='12' fill='#5a6b7b'/>")
        for x, y in pts:
            extents.append((x, y, x, y))
        if line.get("label"):
            label = _wrap(line["label"], 26, 3)
            upright = len(pts) == 2 and abs(pts[0][0] - pts[1][0]) < 1
            if upright:  # beside a vertical line, not across it
                x, top, anchor = mid[0] + 8, mid[1] + 6 - (len(label) - 1) * 5, "start"
                extents.append((x, top - 10, x + 150, top + len(label) * 11))
            else:
                x, top, anchor = mid[0], mid[1] - (len(label) - 1) * 11, "middle"
                extents.append((x - 75, top - 10, x + 75, mid[1] + 4))
            _text_lines(body, x, top, label, 9, anchor=anchor, fill="#3d4a57")
    for n in notes:
        body.append(f"<rect x='{n['x']}' y='{n['y']}' width='{n['w']}' height='{n['h']}' fill='#fff4b3' stroke='#d9c46a'/>")
        _text_lines(body, n["x"] + 6, n["y"] + 15, _wrap(n.get("text"), max(10, int(n["w"] / 6)), max(1, int((n["h"] - 8) / 12))), 9)
    for b in boxes.values():
        body.append(f"<rect x='{b['x']}' y='{b['y']}' width='{b['w']}' height='{b['h']}' rx='6' fill='{b.get('fill') or '#ffffff'}' "
                    f"stroke='{b.get('border') or '#2a4d8d'}' stroke-width='1.5'/>")
        width = max(10, int(b["w"] / 6.4))
        room = max(1, int((b["h"] - 24) / 13))
        if b.get("number") is not None:
            _text_lines(body, b["x"] + 6, b["y"] + 13, [str(b["number"])], 9, weight="bold")
        text = _wrap(b.get("text"), width, max(1, room - 1))
        _text_lines(body, b["x"] + b["w"] / 2, b["y"] + 28, text, 11, anchor="middle", weight="bold")
        people = [r["name"] for r in b.get("resources", []) if r.get("type") == "Human"]
        other = [r["name"] for r in b.get("resources", []) if r.get("type") != "Human"]
        left = room - len(text)
        if left > 0 and (people or other):
            names = _wrap(", ".join(people + other), width + 2, left)
            _text_lines(body, b["x"] + b["w"] / 2, b["y"] + 28 + len(text) * 14 + 6, names, 9, anchor="middle", fill="#4a5866")
    x0 = min(e[0] for e in extents) - 30
    y0 = min(e[1] for e in extents) - 30
    x1 = max(e[2] for e in extents) + 30
    y1 = max(e[3] for e in extents) + 30
    return "\n".join([f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{x0:.0f} {y0:.0f} {x1 - x0:.0f} {y1 - y0:.0f}' "
                      f"width='{x1 - x0:.0f}' height='{y1 - y0:.0f}' font-family='sans-serif'>", ARROW,
                      f"<rect x='{x0:.0f}' y='{y0:.0f}' width='{x1 - x0:.0f}' height='{y1 - y0:.0f}' fill='#ffffff'/>"]
                     + body + ["</svg>"])


# ---------------------------------------------------------------- pictures

def picture(svg, name, eng):
    """Convert one SVG to overview/images/<name>.png and print the outcome."""
    out = eng_path(eng, "overview", "images", f"{name}.png")
    reasons = []
    for route in (with_office, with_pillow):
        pictured, why = route(svg, out)
        if pictured:
            print(f"PICTURED {name}: overview/images/{name}.png")
            return True
        reasons.append(why)
    print(f"NO PICTURE {name}: {'; '.join(reasons)}; the document links to the diagram instead")
    return False


def plan_preview(script, model_path, workdir, extra):
    """Plan a model offline with one of the plugin's layout scripts; return its preview.svg, or the reason it failed."""
    try:
        result = run([sys.executable, str(PLUGIN / "scripts" / script), "plan", str(model_path), "--workdir", str(workdir), *extra])
    except Exception as exc:  # a picture is never worth stopping the run for
        return None, f"the layout could not be planned ({type(exc).__name__}: {exc})"
    svg = Path(workdir) / "preview.svg"
    if result.returncode != 0 or not svg.exists():
        lines = [l for l in (result.stdout + result.stderr).splitlines() if l.strip()]
        return None, "the layout could not be planned (" + ("; ".join(lines[-2:]) or f"exit {result.returncode}")[:300] + ")"
    return svg, None


def area_pictures(eng):
    model = load_json(eng_path(eng, "model.json"), "model.json")
    it_path = eng_path(eng, "derive", "integrations.json")
    it = load_json(it_path, "derive/integrations.json") if it_path.exists() else {"systems": [], "integrations": []}
    inv_path = eng_path(eng, "inventory.json")
    inventory = load_json(inv_path, "inventory.json") if inv_path.exists() else {}
    sources = model.get("meta", {}).get("sources", [])
    for area in process_areas(model, it, inventory):
        aid, folder = area["activity"], eng_path(eng, "overview", "areas", area["activity"])
        if area["level"]:
            name = f"area-{aid}-process"
            level_path = eng_path(eng, "levels", f"{area['level']['levelNumber']}.json")
            try:
                svg_text = process_level_svg(load_json(level_path, f"level {area['level']['levelNumber']}"))
            except Exception as exc:
                svg_text, why = None, f"its saved read could not be drawn ({type(exc).__name__}: {exc})"
            else:
                why = "its saved read has no layout; read the level again with get_diagram include ['all', 'layout']"
            if svg_text:
                svg = folder / "process.svg"
                svg.parent.mkdir(parents=True, exist_ok=True)
                svg.write_text(svg_text, encoding="utf-8")
                picture(svg, name, eng)
            else:
                print(f"NO PICTURE {name}: level {area['level']['levelNumber']} {why}; the document links to the level instead")
        meta = {"title": f"{area['name']}"[:80], "description": "", "author": "design-from-process-map render_diagram.py", "sources": sources}
        if area["entities"]:
            name = f"area-{aid}-data-model"
            path = folder / "data-model.json"
            write_json(path, data_model_part(model, set(area["entities"]), meta))
            svg, why = plan_preview("layout_data_model.py", path, folder / "data-model", ["--skip", "metadata", "--no-legend"])
            if svg:
                picture(svg, name, eng)
            else:
                print(f"NO PICTURE {name}: {why}; the document links to the data model instead")
        if area["integrations"] and it.get("integrations"):
            name = f"area-{aid}-architecture"
            path = folder / "architecture.json"
            write_json(path, architecture_model(model, it, meta, only=set(area["integrations"])))
            svg, why = plan_preview("layout_architecture.py", path, folder / "architecture", ["--no-key"])
            if svg:
                picture(svg, name, eng)
            else:
                print(f"NO PICTURE {name}: {why}; the document links to the system architecture instead")


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    eng = Path(argv[1])
    drawing = eng_path(eng, "drawing")
    found = sorted(p for p in drawing.glob("*/preview.svg")) if drawing.exists() else []
    if not found:
        print("NO PICTURE no drawing work folder holds a preview.svg; the document will carry links only")
    for svg in found:
        picture(svg, svg.parent.name, eng)
    try:
        area_pictures(eng)
    except SetupError as exc:
        print(f"NO PICTURE process areas: {exc}; the document links to the diagrams instead")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
