#!/usr/bin/env python3
"""Build the interactive 3D preview page for a part.

    make_viewer.py --title "Hose cap" --out <dir> [--process fdm_asa] \
        --versions <project folder>/out/<part>/versions        # every design version
    make_viewer.py --title "Hose cap" --out <dir> [--process fdm_asa] [--flip] \
        part.stl ["Label=other.stl" ...]                   # just these files
    add --inline for one self-contained HTML file that opens in any browser

The page has two layouts over the same functions, Studio (simple) and Advanced
(a drawing sheet with sizes and check notes on the part). Both show each part
with three colourings (shape, wall thickness against the material's limits,
overhangs), a cut-away slider, the checks, a version history, a material
switch (every process in processes.json, each with its own check and rough
price for this same shape), and numbered comments you drop on the model.

Writes into <dir>:
    index.html                    the page (tools/viewer/viewer.html, data filled in)
    v<N>/p<i>.stl.b64.txt         each version's meshes, base64 (artifact hosts
    v<N>/p<i>.thk.b64.txt         serve text, not binary), and wall thickness per face
With --inline the meshes go inside index.html instead, and nothing else is written.

Publish with the Artifact tool: file_path <dir>/index.html, every .b64.txt in
`files` (contentType text/plain), and capabilities {"db": {}, "comments": {}}:
db keeps pins with the page where Claude can read them (collection "pins"),
comments lets "Send to Claude" post them into the conversation. Without the
artifact host (a file opened in a browser), pins are kept in that browser and
"Copy for chat" hands them to Claude as text.
"""
import argparse, base64, io, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from partcheck import check, load_processes, measure  # noqa: E402

KEEP = ("verdict", "size_mm", "volume_cm3", "watertight", "bodies", "cavities",
        "cavity_volume_mm3", "thinnest_mm", "wall_red", "wall_warn", "red_mm2", "warn_mm2",
        "overhang_deg", "overhang_mm2", "ceiling_mm2", "cost_usd", "problems", "cautions", "notes",
        "red_spots", "warn_spots", "overhang_spots")
PROC_FIELDS = ("name", "short", "for", "look", "wall_red", "wall_warn", "overhang_deg", "bridges_ok",
               "needs_escape", "rate_usd_cm3", "notes")
SCHEMA = 2                                  # bump when the part data changes shape


def encode(path, process, flip):
    """(stl base64, wall-thickness base64, {process: report}) for one STL.
    Measured once, then judged against every process's limits, so the page can
    show what the same shape would mean in another material."""
    mesh, t = measure(path, flip)
    reps = {}
    for k in load_processes():
        rep = check(path, k, flip, measured=(mesh, t))[0]
        reps[k] = {f: (rep[f][:3] if f.endswith("_spots") else rep[f]) for f in KEEP}
    buf = io.BytesIO()
    mesh.export(buf, file_type="stl")                     # binary, same face order as t
    thk = np.clip(np.round(np.nan_to_num(t, posinf=12.75) * 20), 0, 255).astype(np.uint8)
    return (base64.b64encode(buf.getvalue()).decode(), base64.b64encode(thk.tobytes()).decode(),
            reps)


def build_parts(specs, process, flip, out, prefix, inline, cache_file=None):
    """specs: [(label, stl path)] -> list of part dicts; writes mesh files unless inline."""
    if cache_file and os.path.exists(cache_file) and not inline:
        with open(cache_file) as f:
            cached = json.load(f)
        if cached.get("schema") == SCHEMA and cached.get("process") == process and all(
                os.path.exists(os.path.join(out, p["stl"])) for p in cached["parts"]):
            return cached["parts"]
    parts = []
    for i, (label, path) in enumerate(specs):
        stl, thk, reps = encode(path, process, flip)
        rep = reps[process]
        part = {"label": label, "report": rep, "reports": reps}
        if inline:
            part["stl_data"], part["thk_data"] = stl, thk
        else:
            os.makedirs(os.path.join(out, prefix), exist_ok=True)
            for kind, data in (("stl", stl), ("thk", thk)):
                name = f"{prefix}/p{i}.{kind}.b64.txt"
                with open(os.path.join(out, name), "w") as f:
                    f.write(data)
                part[kind] = name
        parts.append(part)
        print(f"  {prefix} {label}: {rep['verdict']}, {rep['volume_cm3']} cm3")
    if cache_file and not inline:
        with open(cache_file, "w") as f:
            json.dump({"schema": SCHEMA, "process": process, "parts": parts}, f)
    return parts


def version_specs(vdir, process):
    """The STLs of one saved version: this process's files if it has any, else all."""
    stls = sorted(n for n in os.listdir(vdir) if n.endswith(".stl"))
    mine = [n for n in stls if n.endswith(f"_{process}.stl")]
    pick = mine or stls
    label = lambda n: n[:-4][: -len(process) - 1] if n.endswith(f"_{process}.stl") else n[:-4]
    return [(label(n), os.path.join(vdir, n)) for n in pick]


MEMBER_FIELDS = ("id", "kind", "group", "layer", "item", "variant", "treated", "size", "origin", "x", "y",
                 "cut_deg", "outline")


def read_json(path):
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def build_version(frame_path, bom_path, checks_path, n, meta):
    """One version of a timber structure for the page: its members, and the
    shopping list and checks when they have been made."""
    import timberlib
    frame = read_json(frame_path)
    if not frame or "members" not in frame:
        sys.exit(f"{frame_path} is not a frame file (tools/frame.py makes them)")
    lib, items = timberlib.load(frame.get("region", "eu")), {}
    for key in sorted({m["item"] for m in frame["members"]} | {b["item"] for b in frame.get("bought", [])}):
        try:
            it = timberlib.item(lib, key)
            items[key] = {"name": it.get("name") or key}
        except Exception:
            items[key] = {"name": key.replace("-", " ")}
    checks = read_json(checks_path)
    if isinstance(checks, dict):
        checks = checks.get("findings", checks.get("checks"))
    ground = next((sp["ground_mm"] for a in frame.get("assemblies", []) if a.get("type") == "foundations"
                   for sp in a["spans"] if "ground_mm" in sp), None)      # footings reach below it
    out = {"n": n, "note": meta.get("note", ""), "created": meta.get("created", ""),
            "parts": [{"label": frame.get("name", "structure"), "report": None}],
            "build": {"name": frame.get("name", "structure"), "region": frame.get("region", "eu"),
                      "units": frame.get("units", "metric"), "items": items,
                      "members": [{k: m.get(k) for k in MEMBER_FIELDS} for m in frame["members"]],
                      "bought": frame.get("bought", []), "checks": checks, "bom": read_json(bom_path)}}
    if ground is not None:
        out["build"]["ground"] = ground
    decisions = [{k: str(d[k]) for k in ("what", "chose", "why") if d.get(k) not in (None, "")}
                 for d in (frame.get("decisions") or []) if isinstance(d, dict) and d.get("what")]
    if decisions:                       # "How it was planned": the sizes the planner chose, and why
        out["build"]["decisions"] = decisions
    return out


def main_build(a):
    """--build: the page for a timber structure. No mesh files: the page draws the members itself."""
    versions = []
    if os.path.isdir(a.build):
        ns = sorted(int(n[1:]) for n in os.listdir(a.build) if n.startswith("v") and n[1:].isdigit())
        if not ns:
            sys.exit(f"no versions in {a.build}")
        for n in ns:
            d = os.path.join(a.build, f"v{n}")
            versions.append(build_version(os.path.join(d, "frame.json"), os.path.join(d, "bom.json"),
                                          os.path.join(d, "checks.json"), n, read_json(os.path.join(d, "meta.json")) or {}))
    else:
        versions.append(build_version(a.build, a.bom, a.checks, 0, {}))
    data = {"title": a.title, "kind": "build",
            "process": {"name": "Timber frame", "key": "timber", "wall_red": 0, "wall_warn": 0,
                        "overhang_deg": None, "bridges_ok": True},
            "versions": versions}
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(HERE, "viewer", "viewer.html")) as f:
        page = f.read()
    title = a.title.replace("<", "").replace(">", "")
    page = page.replace("__TITLE__", title, 1).replace("__KIT_DATA__", json.dumps(data).replace("</", "<\\/"), 1)
    with open(os.path.join(a.out, "index.html"), "w") as f:
        f.write(page)
    v = versions[-1]["build"]
    print(f"wrote {a.out}/index.html: {len(v['members'])} members"
          + (", with checks" if v["checks"] is not None else "") + (", with a shopping list" if v["bom"] else ""))


def main():
    procs = load_processes()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("parts", nargs="*", help="part.stl or Label=part.stl (without --versions)")
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--process", default="fdm_asa", choices=sorted(procs))
    ap.add_argument("--versions", help="a versions folder made by tools/versions.py")
    ap.add_argument("--inline", action="store_true", help="one self-contained HTML file")
    ap.add_argument("--flip", action="store_true")
    ap.add_argument("--build", help="a frame.json from tools/frame.py, or a folder of versions "
                    "(v1/frame.json, v2/frame.json ...): a timber structure instead of printed parts")
    ap.add_argument("--bom", help="with --build FILE: the bom.json from tools/bom.py")
    ap.add_argument("--checks", help="with --build FILE: the checks.json from tools/framecheck.py")
    a = ap.parse_args()
    if a.build:
        return main_build(a)
    if bool(a.versions) == bool(a.parts):
        ap.error("give either --versions DIR or STL files, not both")

    os.makedirs(a.out, exist_ok=True)
    P = procs[a.process]
    data = {"title": a.title,
            "process": dict({k: P[k] for k in ("name", "wall_red", "wall_warn", "overhang_deg", "bridges_ok")},
                            key=a.process),
            "processes": {k: {f: p.get(f) for f in PROC_FIELDS} for k, p in procs.items()},
            "versions": []}

    if a.versions:
        ns = sorted(int(n[1:]) for n in os.listdir(a.versions) if n.startswith("v") and n[1:].isdigit())
        if not ns:
            sys.exit(f"no versions in {a.versions} (tools/build_part.sh makes them)")
        for n in ns:
            vdir = os.path.join(a.versions, f"v{n}")
            with open(os.path.join(vdir, "meta.json")) as f:
                meta = json.load(f)
            cache = os.path.join(a.out, f"v{n}", "parts.json")
            parts = build_parts(version_specs(vdir, a.process), a.process, a.flip,
                                a.out, f"v{n}", a.inline, cache)
            data["versions"].append({"n": n, "note": meta.get("note", ""),
                                     "created": meta.get("created", ""), "parts": parts})
    else:
        specs = [(s.split("=", 1) if "=" in s else (os.path.splitext(os.path.basename(s))[0], s))
                 for s in a.parts]
        data["versions"].append({"n": 0, "note": "", "created": "",
                                 "parts": build_parts(specs, a.process, a.flip, a.out, "v0", a.inline)})

    with open(os.path.join(HERE, "viewer", "viewer.html")) as f:
        page = f.read()
    blob = json.dumps(data).replace("</", "<\\/")
    title = a.title.replace("<", "").replace(">", "")
    page = page.replace("__TITLE__", title, 1).replace("__KIT_DATA__", blob, 1)
    with open(os.path.join(a.out, "index.html"), "w") as f:
        f.write(page)
    files = [] if a.inline else [p[k] for v in data["versions"] for p in v["parts"] for k in ("stl", "thk")]
    print(f"wrote {a.out}/index.html" + (f" and {len(files)} mesh files" if files else " (self-contained)"))


if __name__ == "__main__":
    main()
