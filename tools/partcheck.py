#!/usr/bin/env python3
"""Printability check for one STL against one manufacturing process.

    partcheck.py <part.stl> [--process fdm_asa] [--flip] [--json out.json] [--md out.md]

Processes and their limits live in tools/processes.json (resin_sla, fdm_asa,
fdm_pla, fdm_petg, slm_316l, slm_alsi10mg, mjf_pa12). The part is checked as it would be built:
+Z up, lowest point on the bed (--flip turns it upside down first).

What it reports, and why each matters:

  mesh      watertight, one body, volume, size. A service rejects a mesh that
            is not closed; two bodies usually means a feature that floats.
  cavities  closed hollows inside the part. Resin and powder processes trap
            material in them; they need drain or escape holes.
  walls     local wall thickness from every face straight into the material,
            the measure JLC3DP's heatmap uses. Below wall_red is rejected,
            below wall_warn is flagged.
  overhang  downward faces flatter than overhang_deg from horizontal, off the
            bed. FDM bridges flat ceilings; laser-melted metal cannot, and a
            support inside a channel can never be removed.
  cost      volume x the process's rough rate, when one is known (print services).

Home printers (fdm_pla, fdm_petg; "home": true in processes.json) get three
more things instead of a service price:

  bed       does the bounding box fit the printer's build volume as modelled,
            only turned onto another face, or not at all? Build volume, first
            that is set: --bed 256x256x256, the BED environment variable, a
            printer.json ({"name": "...", "bed": [x, y, z]}) in the project
            folder (found by walking up from the STL), else 220x220x250 mm.
            Only axis-aligned turns are tried, and a part is not laid
            diagonally on the bed. Fits only turned = a caution; fits nowhere
            = a problem.
  filament  grams and cost at a typical fill. Simple on purpose: the outer
            shell is surface area x 1.2 mm (about three 0.4 mm walls), the rest
            is 20 % infill, so  volume_printed = min(V, A x 1.2) + 0.2 x
            (V - that).  Grams = volume x density; cost = grams x price per kg.
  settings  the slicer settings to start from (layer, walls, infill, supports,
            temperatures), in the report next to the checks.

Exit code 1 when anything would be rejected (red walls, a cavity where escape
is needed, metal ceilings), so build scripts can stop on it.

Needs: trimesh, rtree (tools/setup.sh installs them).
"""
import argparse, json, math, os, sys, warnings
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from thinwall import thickness  # noqa: E402

# trimesh warns about degenerate slivers in OpenSCAD output; they are harmless.
warnings.filterwarnings("ignore", category=RuntimeWarning)


def load_processes():
    with open(os.path.join(HERE, "processes.json")) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def components(mesh):
    """Connected face groups, without scipy or networkx."""
    parent = np.arange(len(mesh.faces))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in mesh.face_adjacency:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    roots = np.array([find(i) for i in range(len(parent))])
    return [np.where(roots == r)[0] for r in np.unique(roots)]


def signed_volume(mesh, faces):
    t = mesh.triangles[faces]
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def hotspots(centres, area, values, mask, n=8, cell=3.0):
    """Group flagged faces into cells of `cell` mm so each feature shows once."""
    if not mask.any():
        return []
    keys = np.floor(centres[mask] / cell).astype(int)
    out = {}
    for k, a, v, c in zip(map(tuple, keys), area[mask], values[mask], centres[mask]):
        e = out.setdefault(k, [0.0, math.inf, c])
        e[0] += a
        e[1] = min(e[1], v)
    rows = sorted(out.values(), key=lambda e: -e[0])[:n]
    return [{"area_mm2": round(a, 2), "worst": round(v, 2),
             "at_mm": [round(float(x), 1) for x in c]} for a, v, c in rows]


DEFAULT_BED = (220.0, 220.0, 250.0)      # mm, a common small printer
SHELL_MM, INFILL = 1.2, 0.20            # filament estimate: shell thickness, infill fraction


def parse_bed(text):
    """'256x256x256' (or 256,256,256) -> (256.0, 256.0, 256.0)."""
    parts = [float(x) for x in text.lower().replace(",", "x").split("x") if x.strip()]
    if len(parts) != 3 or min(parts) <= 0:
        raise ValueError(f"bed size must look like 220x220x250, got {text!r}")
    return tuple(parts)


def find_printer(path):
    """printer.json next to the STL or in a folder above it (the project folder)."""
    d = os.path.dirname(os.path.abspath(path))
    for _ in range(5):
        f = os.path.join(d, "printer.json")
        if os.path.isfile(f):
            with open(f) as fh:
                j = json.load(fh)
            return parse_bed("x".join(str(v) for v in j["bed"])), j.get("name")
        if d == os.path.dirname(d):
            break
        d = os.path.dirname(d)
    return None, None


def bed_volume(path, bed=None):
    """(build volume, where it came from)."""
    if bed:
        return tuple(bed), "set on the command line"
    if os.environ.get("BED"):
        return parse_bed(os.environ["BED"]), "from the BED environment variable"
    b, name = find_printer(path)
    if b:
        return b, f"from printer.json{' (' + name + ')' if name else ''}"
    return DEFAULT_BED, "default; set a printer.json in the project to use yours"


def bed_fit(size, bed):
    """How a bounding box (x, y, z) sits in a build volume (bx, by, bz).
    -> {"fit": "as built" | "turned" | "no", "turn": text or None}.
    Tries the three axis-aligned 'which axis points up' choices; on the bed the
    footprint may be rotated 90 degrees."""
    bx, by, bz = bed
    eps = 1e-6

    def fits(a, b, h):
        return h <= bz + eps and ((a <= bx + eps and b <= by + eps) or (a <= by + eps and b <= bx + eps))

    x, y, z = size
    if fits(x, y, z):
        return {"fit": "as built", "turn": None}
    for up, (a, b, h) in (("X", (y, z, x)), ("Y", (x, z, y))):
        if fits(a, b, h):
            return {"fit": "turned", "turn": f"stand it with its {up} axis up "
                    f"(lay it on its {'Y-Z' if up == 'X' else 'X-Z'} side), "
                    f"{a:g} x {b:g} x {h:g} mm"}
    return {"fit": "no", "turn": None}


def filament(volume_mm3, area_mm2, density, usd_kg):
    """Filament for walls plus 20 % infill: shell = area x 1.2 mm (capped at the
    whole volume), the rest at 20 %. -> (grams, cost in USD, printed cm3)."""
    shell = min(volume_mm3, area_mm2 * SHELL_MM)
    used = (shell + INFILL * (volume_mm3 - shell)) / 1000.0
    g = used * density
    return round(g, 1), round(g * usd_kg / 1000.0, 2), round(used, 2)


def print_settings(P, rep, load=False):
    """The slicer settings to start from, as short plain lines."""
    walls = 4 if load else 3
    if rep["overhang_mm2"] > 0:
        sp = rep["overhang_spots"][:3]
        where = "; ".join(f"({s['at_mm'][0]}, {s['at_mm'][1]}, {s['at_mm'][2]})" for s in sp)
        sup = (f"only under the flagged overhangs ({rep['overhang_mm2']} mm2, around x y z {where} mm); "
               "use support on those faces, not everywhere")
    else:
        sup = "none needed: the overhang check found nothing flatter than 45 degrees"
    orient = "as modelled, +Z up, lowest face on the bed"
    if rep.get("bed", {}).get("fit") == "turned":
        orient = "turned: " + rep["bed"]["turn"] + " (the checks above assume the model's own orientation; re-check)"
    return [
        "Layer height 0.2 mm, 0.4 mm nozzle",
        f"{walls} walls (4 for a part under load), 4 top and bottom layers",
        "Infill 20-40 % gyroid (the higher end for a part that is loaded)",
        f"Orientation: {orient}",
        f"Supports: {sup}",
        f"Nozzle {P['nozzle_c'][0]}-{P['nozzle_c'][1]} C, bed {P['bed_c'][0]}-{P['bed_c'][1]} C "
        "(the spool label wins)",
    ]


def measure(path, flip=False):
    """Load a mesh onto the bed (z = 0) and measure its wall thickness per face."""
    m = trimesh.load(path, force="mesh")
    if flip:
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
    m.apply_translation([0, 0, -m.bounds[0][2]])
    return m, thickness(m)


def check(path, proc_key, flip=False, return_mesh=False, measured=None, bed=None):
    """measured: a (mesh, thickness) pair from measure(), to judge one mesh
    against several processes without measuring it again."""
    P = load_processes()[proc_key]
    m, t = measured or measure(path, flip)

    area = m.area_faces
    cen = m.triangles_center
    n = m.face_normals
    size = (m.bounds[1] - m.bounds[0]).tolist()

    # bodies and cavities
    comps = components(m)
    vols = [signed_volume(m, c) for c in comps]
    bodies = [v for v in vols if v > 1e-3]
    cavities = [-v for v in vols if v < -1e-3]

    # walls
    red = t < P["wall_red"]
    warn = (t >= P["wall_red"]) & (t < P["wall_warn"])

    # overhangs: angle of the face from horizontal, for faces looking down
    ang = np.degrees(np.arcsin(np.clip(np.abs(n[:, 2]), 0, 1)))       # 90 = flat
    from_horiz = 90 - ang
    down = n[:, 2] < -1e-6
    off_bed = cen[:, 2] > 0.05
    thr = P["overhang_deg"]
    if thr is None:
        over = np.zeros(len(n), bool)
    else:
        over = down & off_bed & (from_horiz < thr - 0.5)   # 0.5 deg slack: exact 45s pass
    flat = over & (from_horiz < 10)

    rep = {
        "file": os.path.basename(path), "process": proc_key, "process_name": P["name"],
        "watertight": bool(m.is_watertight), "winding_ok": bool(m.is_winding_consistent),
        "bodies": len(bodies), "cavities": len(cavities),
        "cavity_volume_mm3": round(sum(cavities), 1),
        "volume_cm3": round(m.volume / 1000, 2), "size_mm": [round(s, 1) for s in size],
        "surface_cm2": round(m.area / 100, 1),
        "thinnest_mm": round(float(np.min(t)), 3),
        "wall_red": P["wall_red"], "wall_warn": P["wall_warn"],
        "red_mm2": round(float(area[red].sum()), 2), "warn_mm2": round(float(area[warn].sum()), 2),
        "red_spots": hotspots(cen, area, t, red), "warn_spots": hotspots(cen, area, t, warn),
        "overhang_deg": thr,
        "overhang_mm2": round(float(area[over].sum()), 1),
        "ceiling_mm2": round(float(area[flat].sum()), 1),
        "overhang_spots": hotspots(cen, area, from_horiz, over),
        "cost_usd": (round(m.volume / 1000 * P["rate_usd_cm3"], 1)
                     if P.get("rate_usd_cm3") else None),
        "notes": P["notes"],
    }

    # verdicts
    problems, cautions = [], []
    if not rep["watertight"]:
        problems.append("Mesh is not closed (not watertight): services reject it.")
    if rep["bodies"] != 1:
        cautions.append(f"{rep['bodies']} separate bodies: a floating feature, or meant as an assembly?")
    if rep["cavities"] and P["needs_escape"]:
        problems.append(f"{rep['cavities']} closed cavity(ies), {rep['cavity_volume_mm3']} mm3: "
                        "material is trapped inside. Add drain/escape holes.")
    if rep["red_mm2"] > 0.5:
        problems.append(f"{rep['red_mm2']} mm2 of wall under {P['wall_red']} mm.")
    elif rep["red_mm2"] > 0:
        cautions.append(f"{rep['red_mm2']} mm2 under {P['wall_red']} mm: single edge triangles, "
                        "usually harmless; check the spots.")
    if rep["warn_mm2"] > 0:
        cautions.append(f"{rep['warn_mm2']} mm2 between {P['wall_red']} and {P['wall_warn']} mm.")
    if thr is not None and rep["overhang_mm2"] > 0:
        msg = (f"{rep['overhang_mm2']} mm2 overhangs flatter than {thr} deg "
               f"({rep['ceiling_mm2']} mm2 near-flat ceilings).")
        if not P["bridges_ok"] and rep["ceiling_mm2"] > 1.0:
            problems.append(msg + " This process cannot bridge: slope them to 45 deg.")
        else:
            cautions.append(msg)
    if P.get("home"):
        vol, src = bed_volume(path, bed)
        bf = bed_fit(size, vol)
        rep["bed"] = {"volume_mm": list(vol), "source": src, **bf}
        if bf["fit"] == "no":
            problems.append(f"Does not fit the {vol[0]:g} x {vol[1]:g} x {vol[2]:g} mm build volume "
                            f"({src}) in any orientation: {' x '.join(f'{v:g}' for v in size)} mm. "
                            "Make it smaller or split it into parts.")
        elif bf["fit"] == "turned":
            cautions.append(f"Fits the {vol[0]:g} x {vol[1]:g} x {vol[2]:g} mm build volume only "
                            f"turned: {bf['turn']}. Overhangs and layer direction change with it.")
        g, usd, used = filament(m.volume, m.area, P["density_g_cm3"], P["filament_usd_kg"])
        rep.update({"filament_g": g, "filament_cost_usd": usd, "filament_cm3": used,
                    "cost_usd": None})
        rep["print_settings"] = print_settings(P, rep)
    rep["problems"], rep["cautions"] = problems, cautions
    rep["verdict"] = "fail" if problems else ("check" if cautions else "pass")
    return (rep, t, m) if return_mesh else (rep, t)


def to_markdown(r):
    L = [f"### {r['file']} as {r['process_name']}: **{r['verdict'].upper()}**", "",
         "| | |", "|---|---|",
         f"| Size | {' x '.join(f'{s:g}' for s in r['size_mm'])} mm |",
         f"| Volume | {r['volume_cm3']} cm3 |",
         f"| Mesh | {'closed' if r['watertight'] else 'NOT CLOSED'}, {r['bodies']} body(ies), "
         f"{r['cavities']} cavity(ies) |",
         f"| Thinnest wall | {r['thinnest_mm']} mm |",
         f"| Under {r['wall_red']} mm / {r['wall_red']}-{r['wall_warn']} mm | "
         f"{r['red_mm2']} / {r['warn_mm2']} mm2 |"]
    if r["overhang_deg"] is not None:
        L.append(f"| Overhang < {r['overhang_deg']} deg (flat) | {r['overhang_mm2']} "
                 f"({r['ceiling_mm2']}) mm2 |")
    if r["cost_usd"] is not None:
        L.append(f"| Rough price | ${r['cost_usd']} |")
    if "bed" in r:
        v = r["bed"]["volume_mm"]
        L.append(f"| Printer bed | {v[0]:g} x {v[1]:g} x {v[2]:g} mm ({r['bed']['source']}): "
                 f"{ {'as built': 'fits', 'turned': 'fits only turned', 'no': 'DOES NOT FIT'}[r['bed']['fit']] } |")
        L.append(f"| Filament | about {r['filament_g']} g, ${r['filament_cost_usd']:.2f} "
                 "(walls plus 20 % infill; see partcheck.py) |")
    L.append("")
    for p in r["problems"]:
        L.append(f"- FIX: {p}")
    for c in r["cautions"]:
        L.append(f"- check: {c}")
    for name, key in (("thin walls", "red_spots"), ("warnings", "warn_spots"),
                      ("overhangs", "overhang_spots")):
        spots = [s for s in r[key] if s["area_mm2"] >= 0.05][:4]
        if spots:
            L.append(f"- where ({name}, x y z in mm, largest first): " + "; ".join(
                f"({s['at_mm'][0]}, {s['at_mm'][1]}, {s['at_mm'][2]}) {s['area_mm2']} mm2"
                for s in spots))
    L.append("")
    if r.get("print_settings"):
        L += ["", "**Print settings to start from**", ""] + [f"- {t}" for t in r["print_settings"]]
    L.append("")
    L += [f"> {n}" for n in r["notes"]]
    return "\n".join(L)


def main():
    procs = load_processes()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stl")
    ap.add_argument("--process", default="fdm_asa", choices=sorted(procs))
    ap.add_argument("--flip", action="store_true", help="check it built upside down")
    ap.add_argument("--bed", help="printer build volume for home processes, e.g. 256x256x256 "
                    "(else $BED, else printer.json in the project, else 220x220x250)")
    ap.add_argument("--load", action="store_true", help="part is under load: 4 walls in the settings")
    ap.add_argument("--json", help="write the full report as JSON")
    ap.add_argument("--md", help="write the report as Markdown")
    a = ap.parse_args()
    r, _ = check(a.stl, a.process, a.flip, bed=parse_bed(a.bed) if a.bed else None)
    if a.load and r.get("print_settings"):
        r["print_settings"] = print_settings(load_processes()[a.process], r, load=True)
    md = to_markdown(r)
    print(md)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(r, f, indent=1)
    if a.md:
        with open(a.md, "w") as f:
            f.write(md + "\n")
    return 1 if r["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
