#!/usr/bin/env python3
"""Build checks for a timber frame: spans by formula and layout rules.

    framecheck.py <frame.json> --out <checks.json>

Reads the frame file written by tools/frame.py and writes findings, each
    { "id", "level": "ok" | "check" | "fix", "title", "text", "members": [ids], "at": [x, y, z] }
in plain words, with the numbers in the frame's `units`.

THIS IS GUIDANCE FROM SIMPLE FORMULAS, NOT STRUCTURAL ENGINEERING. Joists,
rafters and headers are treated as simply supported beams under an even
load; shear, bearing, wind, uplift, fixings, the ground and the walls'
own strength are not checked. Every run ends with a finding that says so.

Two regions are treated differently on purpose (see the library's `basis`):
  eu  C24 is a *characteristic* strength: design value = k_mod * k_h * k_sys *
      f_m,k / gamma_M against factored loads (limit-state method, after
      EN 1995-1-1 and EN 1990).
  us  SPF No. 2 is an *allowable-stress* reference value: adjusted value =
      F_b * C_D * C_F * C_r against unfactored loads (after NDS 2018).
Never mix the two: the factors below belong to one method each.
"""
import argparse, json, math, os, re, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timberlib as tl  # noqa: E402
from frame_edits import contact  # noqa: E402   (separating-axis touch test shared with the edits)
from timber.spans import (FACTORS, WARN_FRACTION, MAX_FRACTION, SPACING_SHARE, _f, own_weight_kn_m,  # noqa: E402,F401
                         us_size_factor, allowable_span, level_for, terrace_loads, joist_allowed, beam_allowed,
                         _slat_dead_kn_m2, pergola_rafter_span, pergola_rafter_allowed, pergola_beam_allowed,
                         kitchen_roof_dead_kn_m2, kitchen_beam_trib_mm, kitchen_beam_allowed,
                         length_text, floor_joist_allowed, shed_rafter_allowed, header_allowed, header_trib_mm)

# ============================================================== GEOMETRY

def _axes(m):
    x, y = np.array(m["x"], float), np.array(m["y"], float)
    return x, y, np.cross(x, y)


def box_corners(m):
    x, y, z = _axes(m)
    o = np.array(m["origin"], float)
    L, W, T = m["size"]
    return np.array([o + a * L * x + b * W * y + c * T * z for a in (0, 1) for b in (0, 1) for c in (0, 1)])


def centre(m):
    c = box_corners(m).mean(axis=0)
    return [round(float(v), 1) for v in c]


def inside_box(m, p, tol=1.0):
    x, y, z = _axes(m)
    d = np.asarray(p, float) - np.array(m["origin"], float)
    L, W, T = m["size"]
    return all(-tol <= d @ ax <= s + tol for ax, s in ((x, L), (y, W), (z, T)))


def vertical_dims(m):
    """(breadth, depth) of a member's section: depth is the side most nearly vertical."""
    x, y, z = _axes(m)
    _, W, T = m["size"]
    return (T, W) if abs(y[2]) >= abs(z[2]) else (W, T)


class Boxes:
    """Many oriented boxes at once: `hit(points)` says which points lie inside any of them."""
    def __init__(self, members, tol=1.0):
        self.tol = tol
        if members:
            self.o = np.array([m["origin"] for m in members], float)
            ax = [_axes(m) for m in members]
            self.ax = np.array([[a[0], a[1], a[2]] for a in ax])             # (n, 3 axes, 3)
            self.size = np.array([m["size"] for m in members], float)        # (n, 3)
        else:
            self.o = np.zeros((0, 3))

    def hit(self, pts):
        pts = np.atleast_2d(np.asarray(pts, float))
        if not len(self.o):
            return np.zeros(len(pts), bool)
        d = pts[:, None, :] - self.o[None, :, :]                             # (p, n, 3)
        proj = np.einsum("pnk,nak->pna", d, self.ax)                         # (p, n, 3 axes)
        ok = (proj >= -self.tol) & (proj <= self.size[None, :, :] + self.tol)
        return ok.all(axis=2).any(axis=1)


FRAME_KINDS = {"stud", "plate", "header", "trimmer", "king", "jack", "cripple", "sill",
               "joist", "rim", "rafter", "blocking", "brace", "outrigger", "ridge", "tie"}


# =============================================================== FINDINGS

class Findings:
    def __init__(self, frame, lib):
        self.frame, self.lib = frame, lib
        self.units = frame["units"]
        self.items = []
        self.by_id = {m["id"]: m for m in frame["members"]}

    def add(self, id_, level, title, text, members=(), at=None):
        members = list(members)
        if at is None:
            at = centre(self.by_id[members[0]]) if members else self.default_at()
        self.items.append({"id": id_, "level": level, "title": title, "text": text,
                           "members": members, "at": [round(float(v), 1) for v in at]})

    def default_at(self):
        s = self.frame["spec"]
        return [round(s["width"] / 2, 1), round(s["depth"] / 2, 1), 0.0]

    # number formatting, in the frame's units
    def length(self, mm):
        return length_text(mm, self.units)

    def load(self, kn_m2):
        if self.units == "imperial":
            return f"{kn_m2 * _f('common', 'kn_m2_to_psf'):.0f} psf"
        return f"{kn_m2:g} kN/m2"


def section_name(lib, item):
    return lib["sections"][item]["name"] if item in lib["sections"] else item


def roof_slope(frame):
    r = [m for m in frame["members"] if m["kind"] == "rafter"]
    if not r:
        return None
    x = np.array(r[0]["x"], float)
    return math.atan2(-x[2], math.hypot(x[0], x[1]))


def span_of(frame, kind):
    """The first span of this member kind recorded by an assembly
    (frame["assemblies"]: platform joists, wall studs, roof rafters), or None
    for a frame made before assemblies were recorded."""
    for a in frame.get("assemblies", []):
        for sp in a.get("spans", []):
            if sp.get("kind") == kind:
                return sp
    return None


def spacing_of(frame, kind, spec_key):
    """Spacing in mm of the members of `kind`: from the assembly that holds
    them, else from the spec."""
    sp = span_of(frame, kind)
    return sp["spacing_mm"] if sp else frame["spec"][spec_key]


def deck_of(frame, kind, spec_key):
    sp = span_of(frame, kind)
    return sp["deck"] if sp else frame["spec"][spec_key]


def is_kitchen(frame):
    return frame["spec"].get("type") == "summer-kitchen"


def is_gable(frame):
    sp = frame["spec"]
    return sp.get("type") == "gable-shed" or (sp.get("type") == "summer-kitchen" and sp.get("roof") == "gable")


def spec_openings(spec):
    """The doors and windows of the description as a flat list with their wall (a summer kitchen lists them per wall)."""
    if "walls" in spec:
        return [dict(o, wall=w["side"]) for w in spec["walls"] for o in w["openings"]]
    return spec.get("openings", [])


def rafter_run(frame):
    """Horizontal run of a gable roof's rafters, from the eave wall's outer face to
    the ridge board: from the roof assembly, else from the members."""
    sp = span_of(frame, "rafter")
    if sp and "span_mm" in sp:
        return sp["span_mm"]
    by = {m["id"]: m for m in frame["members"]}
    ridge, plate = by.get("roof/ridge"), by.get("wall-front/plate-top")
    if not (ridge and plate):
        return frame["spec"]["depth"] / 2.0
    return round(float(box_corners(ridge)[:, 1].min() - box_corners(plate)[:, 1].min()), 1)


# ================================================================== SPANS

def check_joists(f):
    fr, lib, spec = f.frame, f.lib, f.frame["spec"]
    joists = [m for m in fr["members"] if m["kind"] == "joist"]
    if not joists:
        f.add("span-joists", "check", "Floor joists", "There are no floor joists in this frame, so no floor span was checked.")
        return
    rims = [m for m in fr["members"] if m["kind"] == "rim"]
    rim_t = rims[0]["size"][2] if rims else 0.0
    m = max(joists, key=lambda j: j["size"][0])
    span = m["size"][0] + rim_t                     # centre to centre of the two rim joists
    b, d = vertical_dims(m)
    spacing = spacing_of(fr, "joist", "joist_spacing")
    qf = spec["loads"]["floor_kn_m2"]
    res = floor_joist_allowed(lib, dict(spec, floor_deck=deck_of(fr, "joist", "floor_deck")), m["item"], spacing,
                              repetitive=len(joists) >= 4)
    allowed = res["span_mm"]
    level = level_for(span, allowed)
    name = section_name(lib, m["item"])
    verdict = {"ok": "That is comfortable.",
               "check": "That is close to the limit: use a deeper section or closer joists if the floor will carry more than people and light storage.",
               "fix": "That is too long: use a deeper section, closer spacing or a support under the middle of the joists."}[level]
    f.add("span-joists", level, f"Floor joists: {name} at {f.length(spacing)}",
          f"Floor joists span {f.length(span)} (centre to centre of the front and back rim joists). "
          f"This section is good for about {f.length(allowed)} at this spacing and a floor load of {f.load(qf)} "
          f"(limited by {res['governs']}). {verdict} "
          f"Counted as if nothing holds the joists up between the rims; posts or blocks under them only help.",
          [m["id"]])


def check_rafters(f):
    fr, lib, spec = f.frame, f.lib, f.frame["spec"]
    rafters = [m for m in fr["members"] if m["kind"] == "rafter"]
    if not rafters:
        f.add("span-rafters", "check", "Rafters", "There are no rafters in this frame, so no roof span was checked.")
        return
    ang = roof_slope(fr)
    cos_a = math.cos(ang)
    m = rafters[0]
    sp = span_of(fr, "rafter")
    plates = {p["id"]: p for p in fr["members"] if p["id"] in ("wall-front/plate-top", "wall-back/plate-top")}   # same line as any upper plate
    if is_gable(fr):
        span = rafter_run(fr)
    elif sp and "span_mm" in sp:
        span = sp["span_mm"]                    # a roof on beams records its span
    elif len(plates) == 2:
        ys = [p["origin"][1] + p["size"][1] / 2.0 for p in plates.values()]   # plates lie flat, width along Y
        span = abs(ys[0] - ys[1])               # centre to centre of the bearing plates, horizontal
    else:
        span = spec["depth"] - 100.0
    b, d = vertical_dims(m)
    spacing = spacing_of(fr, "rafter", "rafter_spacing")
    snow = spec["loads"]["snow_kn_m2"]
    res = shed_rafter_allowed(lib, spec, m["item"], spacing, cos_a, repetitive=len(rafters) >= 4)
    allowed = res["span_mm"]
    level = level_for(span, allowed)
    name = section_name(lib, m["item"])
    verdict = {"ok": "That is comfortable.",
               "check": "That is close to the limit: use a deeper section or closer rafters if heavy snow is likely.",
               "fix": "That is too long: use a deeper section or closer rafters."}[level]
    bearer = "beam" if is_kitchen(fr) else "wall"
    where = (f"from the eave {bearer}'s outer face to the ridge board; the overhang is ignored, which errs on the safe side"
             if is_gable(fr) else f"between the centres of the front and back {'beams' if is_kitchen(fr) else 'top plates'}; "
             "the overhang is ignored, which errs on the safe side")
    f.add("span-rafters", level, f"Rafters: {name} at {f.length(spacing)}",
          f"Rafters span {f.length(span)} horizontally ({where}). This section is good for about "
          f"{f.length(allowed)} at this spacing and a snow load of {f.load(snow)} on the plan area "
          f"(limited by {res['governs']}). {verdict}",
          [m["id"]])


def check_headers(f):
    fr, lib, spec = f.frame, f.lib, f.frame["spec"]
    allh = [m for m in fr["members"] if m["kind"] == "header"]
    headers = [m for m in allh if "-ply" not in m["id"]]         # a header's further plies count with it
    plies = {m["id"]: 1 + sum(1 for x in allh if x["id"].startswith(m["id"] + "-ply")) for m in headers}
    ang = roof_slope(fr)
    cos_a = math.cos(ang) if ang is not None else 1.0
    rafters = [m for m in fr["members"] if m["kind"] == "rafter"]
    snow = spec["loads"]["snow_kn_m2"]
    if not headers:
        f.add("span-headers", "ok", "Headers", "There are no door or window openings, so no header was checked.")
        return
    ritem = rafters[0]["item"] if rafters else spec["rafter_item"]
    for m in sorted(headers, key=lambda h: h["id"]):
        wall = m["group"].split("-")[-1]
        rsp = spacing_of(fr, "rafter", "rafter_spacing")
        trib = header_trib_mm(spec, wall, rsp)
        span = m["size"][0]
        res = header_allowed(lib, spec, m["item"], plies[m["id"]], wall, cos_a, ritem, rsp)
        allowed = res["span_mm"]
        level = level_for(span, allowed)
        name = section_name(lib, m["item"]) + (f", {plies[m['id']]} together" if plies[m["id"]] > 1 else "")
        verdict = {"ok": "That is comfortable.",
                   "check": "That is close to the limit: use a deeper header.",
                   "fix": "That is too long: use a deeper header, or two together."}[level]
        f.add(f"span-{m['id'].replace('/', '-')}", level, f"Header over the {wall} opening: {name}",
              f"The header over the {wall} wall opening spans {f.length(span)} and carries the roof over a strip "
              f"{f.length(trib)} wide at a snow load of {f.load(snow)}. This section is good for about "
              f"{f.length(allowed)} (limited by {res['governs']}). {verdict}", [m["id"]])


# =========================================================== LAYOUT RULES

def check_sheet_spacing(f):
    lib, spec = f.lib, f.frame["spec"]
    limits = lib.get("sheet_spans", {})
    fr = f.frame
    if is_kitchen(fr):                  # a floor of boards has no sheet limit; the walls are there only when listed
        jobs = [("roof", deck_of(fr, "rafter", "roof_deck"), spacing_of(fr, "rafter", "rafter_spacing"), "rafters", "roof")]
        if span_of(fr, "stud"):
            jobs.append(("wall", deck_of(fr, "stud", "sheathing"), spacing_of(fr, "stud", "stud_spacing"), "studs", None))
    else:
        jobs = [("floor", deck_of(fr, "joist", "floor_deck"), spacing_of(fr, "joist", "joist_spacing"), "floor joists", "floor"),
                ("roof", deck_of(fr, "rafter", "roof_deck"), spacing_of(fr, "rafter", "rafter_spacing"), "rafters", "roof"),
                ("wall", deck_of(fr, "stud", "sheathing"), spacing_of(fr, "stud", "stud_spacing"), "studs", None)]
    bad, lines, unv = [], [], False
    for role, key, spacing, what, group in jobs:
        rec = limits.get(key, {})
        lim = rec.get(role + "_mm")
        if lim is None:
            lines.append(f"No spacing limit is recorded for {key}; its {role} spacing was not checked.")
            continue
        unv = unv or rec.get("unverified", False)
        if spacing > lim + 0.5:
            bad.append(role)
            lines.append(f"The {role} sheets ({lib['sheets'][key]['name']}) sit on {what} {f.length(spacing)} apart; "
                         f"the limit for this thickness is {f.length(lim)}.")
    if bad:
        members = [m["id"] for m in f.frame["members"] if m["kind"] == "sheet"
                   and (("floor" in bad and m["group"] == "floor") or ("roof" in bad and m["group"] == "roof")
                        or ("wall" in bad and m["group"].startswith("wall-")))][:50]
        text = " ".join(lines) + " Use a thicker sheet or put the supports closer together."
        if unv:
            text += " (These limits are rules of thumb marked unverified in the library; check the sheet maker's table.)"
        f.add("sheet-spacing", "check", "Sheets on supports too far apart", text, members)
    else:
        f.add("sheet-spacing", "ok", "Sheet support spacing",
              "Every sheet floor, roof and wall deck is within the spacing limit for its thickness." +
              (" (The limits are marked unverified in the library.)" if unv else ""))


def _sheet_polygon(m):
    if m.get("outline"):
        return [tuple(p) for p in m["outline"]]
    L, W, _ = m["size"]
    return [(0, 0), (L, 0), (L, W), (0, W)]


def check_sheet_edges(f, step=25.0):
    fr = f.frame
    # the roof deck runs out over the bargeboards and the fascia, so they carry
    # its edges; a fascia's top is square, so the deck rising over it leaves a
    # gap of up to its thickness at the outer face (covered by the drip edge)
    over = [dict(m, size=[m["size"][0], m["size"][1] + m["size"][2], m["size"][2]])
            for m in fr["members"] if m["kind"] == "fascia"]
    support = Boxes([m for m in fr["members"] if m["kind"] in FRAME_KINDS | {"bargeboard"}] + over)
    sheets = [m for m in fr["members"] if m["kind"] == "sheet"]
    bad = []
    for sh in sheets:
        x, y, n = _axes(sh)
        o = np.array(sh["origin"], float)
        t = sh["size"][2]
        poly = _sheet_polygon(sh)
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        pts, outs, dirs = [], [], []
        for i in range(len(poly)):
            a, b = np.array(poly[i], float), np.array(poly[(i + 1) % len(poly)], float)
            length = float(np.linalg.norm(b - a))
            if length < 1:
                continue
            e = (b - a) / length
            out = np.array([e[1], -e[0]])
            if out @ (np.array([cx, cy]) - a) > 0:
                out = -out
            k = max(1, int(length // step))
            for j in range(k):
                p = a + e * (2.0 + (length - 4.0) * (j + 0.5) / k)
                pts.append(o + p[0] * x + p[1] * y)
                outs.append(out[0] * x + out[1] * y)
                dirs.append(e[0] * x + e[1] * y)
        pts, outs, dirs = np.array(pts), np.array(outs), np.array(dirs)
        hit_a = support.hit(pts - n * 1.0)          # frame on the face the sheet's origin is on
        hit_b = support.hit(pts + n * (t + 1.0))    # frame on the other face
        hit = hit_a if hit_a.sum() >= hit_b.sum() else hit_b
        others = Boxes([s for s in sheets if s is not sh and s["group"] == sh["group"]])
        seam = others.hit(pts + outs * 3.0 + n * t / 2.0)
        exempt = np.zeros(len(pts), bool)
        if sh["group"] == "roof":
            exempt = (~seam) & (np.abs(dirs[:, 0]) > 0.7)   # free edge across the rafters: the deck overhangs its last support
        free = int(((~hit) & (~exempt)).sum())
        if free * step > 75.0:
            bad.append((sh["id"], free * step))
    if bad:
        worst = ", ".join(f"{i} ({f.length(l)})" for i, l in bad[:5])
        f.add("sheet-edge", "fix", "Sheet edge with nothing behind it",
              f"{len(bad)} sheet edge(s) have no stud, joist, rafter or blocking behind them for some of their length: "
              f"{worst}. A sheet edge needs timber to be fixed to; add blocking or move the sheet.",
              [i for i, _ in bad][:50])
    else:
        f.add("sheet-edge", "ok", "Sheet edges", "Every sheet edge that is fixed to the frame has timber behind it.")


def check_stock_length(f):
    lib = f.lib
    over = []
    for m in f.frame["members"]:
        if m["kind"] == "sheet":
            continue
        cat = "cladding" if m["item"] in lib.get("cladding", {}) else "sections"
        rec = lib[cat].get(m["item"])
        if not rec or not rec.get("stock_lengths_mm"):
            continue
        longest = max(rec["stock_lengths_mm"] + rec.get("order_lengths_mm", []))   # special-order lengths count (the list says so)
        if m["size"][0] > longest + 0.5:
            over.append((m, longest))
    if over:
        m, longest = max(over, key=lambda p: p[0]["size"][0] - p[1])
        f.add("stock-length", "fix", "Piece longer than the longest timber for sale",
              f"{len(over)} piece(s) are longer than the longest stock length in the library; the worst is {m['id']} at "
              f"{f.length(m['size'][0])} against {f.length(longest)}. Join it, add a support, or change the size.",
              [p[0]["id"] for p in over][:50], at=centre(m))
    else:
        f.add("stock-length", "ok", "Timber lengths", "Every piece can be cut from the longest stock length in the library.")


def check_openings(f):
    spec, fr = f.frame["spec"], f.frame
    bad, lines = [], []
    for i, op in enumerate(spec_openings(spec), 1):
        wall = op["wall"]
        axis = 0 if wall in ("front", "back") else 1
        lo, hi = op["x"], op["x"] + op["width"]
        grp = [m for m in fr["members"] if m["group"] == f"wall-{wall}"]

        def along(m):
            c = box_corners(m)
            return c[:, axis].min(), c[:, axis].max()
        headers = [m for m in grp if m["kind"] == "header" and along(m)[0] >= lo - 60 and along(m)[1] <= hi + 60]
        jacks = [m for m in grp if m["kind"] in ("jack", "trimmer") and along(m)[0] >= lo - 60 and along(m)[1] <= hi + 60]
        kings = [m for m in grp if m["kind"] in ("king", "trimmer") and along(m)[0] >= lo - 110 and along(m)[1] <= hi + 110]
        trim = jacks + [k for k in kings if k not in jacks]
        miss = []
        if not headers:
            miss.append("a header")
        if len(jacks) < 2:
            miss.append("two jack studs (the posts the header rests on)")
        if len(kings) < 2:
            miss.append("two king studs (the full-height studs either side)")
        if headers and len(jacks) >= 2:
            # bearing is read from the joints: every header piece rests on a jack at each end,
            # and every jack is fixed to a king beside it
            jack_ids = {m["id"] for m in jacks}
            king_ids = {m["id"] for m in kings}
            links = [(j["a"], j["b"]) for j in fr["joints"] if j["type"] in ("jack-header", "header-trimmer")]
            if any(len({b if a == h["id"] else a for a, b in links if h["id"] in (a, b)} & jack_ids) < 2
                   for h in headers):
                miss.append("a header resting on both jack studs")
            fixed = {x for j in fr["joints"] if j["type"] == "king-jack" for x in (j["a"], j["b"])
                     if {j["a"], j["b"]} & king_ids}
            if any(m["kind"] == "jack" and m["id"] not in fixed for m in jacks):
                miss.append("a king stud fixed beside each jack")
        if miss:
            bad.append((op, [m["id"] for m in headers + trim]))
            lines.append(f"The {op['kind']} in the {wall} wall is missing {' and '.join(miss)}.")
    if bad:
        ids = [i for _, ms in bad for i in ms]
        at = None
        f.add("opening-frame", "fix", "Opening not fully framed",
              " ".join(lines) + " Studs cut for an opening need a header across the top resting on a jack stud "
              "each side, with a full-height king stud beside each jack.",
              ids, at=at)
    else:
        f.add("opening-frame", "ok", "Openings", "Every door and window opening has a header resting on a jack stud "
              "each side, with a king stud beside each jack.")


# ====================================================== FRAMING CONVENTIONS
# Habits of a well-built frame (docs/research/framing-details.md): pieces that
# a frame can be "valid" without, but a builder would not leave out. They
# read the piece names the generator uses (and that an edit may have removed).

def _extent(ms, axis):
    c = np.vstack([box_corners(m) for m in ms])
    return float(c[:, axis].min()), float(c[:, axis].max())


def _prism(m, axis):
    """(min, max) of a member's real shape (its outline, if cut) along a world axis."""
    if not m.get("outline"):
        return _extent([m], axis)
    x, y, z = _axes(m)
    o = np.array(m["origin"], float)
    v = [float((o + a * x + b * y)[axis]) for a, b in m["outline"]]
    return min(v), max(v)


def _joined(f, types):
    """The joints of the given types as (a, b) id pairs."""
    return [(j["a"], j["b"]) for j in f.frame["joints"] if j["type"] in types]


def check_corners(f):
    spec, fr = f.frame["spec"], f.frame
    # the corner's extra piece besides the end stud, by the corner style
    extra = {"three-stud": "stud", "california": "flat"}.get(spec.get("corner"))
    pairs = _joined(f, ("corner-stud",))
    bad, ids = [], []
    for side in ("left", "right"):
        for end in ("front", "back"):
            n = "01" if side == "left" else "02"
            studs = {m["id"] for m in fr["members"] if m["group"] == f"wall-{side}" and m["kind"] == "stud"}
            theirs = {m["id"]: m for m in fr["members"] if m["group"] == f"wall-{end}"}

            joined = {b if a in studs else a for a, b in pairs
                      if (a in studs and b in theirs) or (b in studs and a in theirs)}
            wanted = f"wall-{end}/corner-{n}-{extra}" if extra else None
            if wanted and wanted not in theirs:
                bad.append(f"the {side}-{end} corner has lost its corner stud ({wanted})")
                ids += sorted(joined)[:1]
            elif not any(theirs[i]["kind"] == "stud" for i in joined):
                bad.append(f"the {side} wall's end stud is not fixed to the {end} wall at the {side}-{end} corner")
                ids += [s for s in sorted(studs)[:1]]
            elif extra == "flat" and wanted not in joined:      # a three-stud corner's third stud only meets it on an edge
                bad.append(f"the {side} wall's end stud is not fixed to {wanted} at the {side}-{end} corner")
                ids += [wanted]
    text = "; ".join(bad)
    if bad:
        f.add("corner-fixing", "fix", "Corner without fixing for both walls",
              text[:1].upper() + text[1:] + ". At each corner the side wall's end stud must be fixed with structural screws to the "
              "front or back wall's corner studs, or the two walls are only held by the plates and the corner can "
              "open up. Put the missing corner piece back.", [i for i in dict.fromkeys(ids) if i in f.by_id][:10])
    else:
        f.add("corner-fixing", "ok", "Corners",
              "All four corners are fixed for both walls: each side wall's end stud is fixed with structural screws to the corner "
              "studs of the front and back walls.")


def check_plate_lap(f):
    spec = f.frame["spec"]
    if spec.get("top_plate") != "double":
        f.add("plate-lap", "ok", "Top plates", "The walls have a single top plate, so there is no upper plate to lap at the corners.")
        return
    pairs = {frozenset(p) for p in _joined(f, ("plate-lap",))}
    bad = [side for side in ("left", "right")
           if frozenset((f"wall-{side}/plate-top-2", "wall-back/plate-top")) not in pairs]
    if bad:
        ids = [f"wall-{s}/plate-top-2" for s in bad if f"wall-{s}/plate-top-2" in f.by_id] or \
              (["wall-back/plate-top"] if "wall-back/plate-top" in f.by_id else [])
        f.add("plate-lap", "check", "Upper top plate does not lap the corner",
              f"The {' and '.join(bad)} wall's upper top plate does not run over the back wall's top plate. "
              "With two top plates, the upper one should overlap the one below at each back corner, so the corner "
              "is tied together by the plate. Lengthen or put back the upper plate.", ids)
    else:
        f.add("plate-lap", "ok", "Top plates lapped at the corners",
              "The upper top plates of both side walls run over the back wall's plate and tie the back corners.")


def _bays(f, slope=None):
    """Pairs of adjacent common rafters (of one slope of a gable roof), with the lateral gap between them."""
    pat = r"roof/rafter-\d+" if slope is None else rf"roof/rafter-{slope}-\d+"
    rs = sorted((m for m in f.frame["members"] if re.fullmatch(pat, m["id"])),
                key=lambda m: _extent([m], 0)[0])
    return [(a, b) for a, b in zip(rs, rs[1:])]


def check_bay_blocking(f):
    fr = f.frame
    gable = is_gable(fr)
    bays = _bays(f)
    blocks = [m for m in fr["members"] if m["group"] == "roof" and m["kind"] == "blocking"]
    open_, walls = [], {}
    for wall in ("front", "back"):
        plates = [m for m in fr["members"] if m["group"] == f"wall-{wall}" and m["kind"] == "plate"]
        if not plates and is_kitchen(fr):      # the roof bears on the beams
            plates = [m for m in fr["members"] if m["id"].startswith("beams/beam-" + ("01" if wall == "front" else "02"))]
        if plates:
            walls[wall] = _extent(plates, 1)
    for wall, (y0, y1) in walls.items():
        if is_kitchen(fr):          # a beam can be narrower than the block is deep: any block on the beam counts
            over = [m for m in blocks if _extent([m], 1)[0] < y1 - 1.0 and _extent([m], 1)[1] > y0 + 1.0]
        else:
            over = [m for m in blocks if y0 - 1.0 <= centre(m)[1] <= y1 + 1.0]
        for a, b in (_bays(f, wall) if gable else bays):
            lo, hi = _extent([a], 0)[1], _extent([b], 0)[0]
            # a bay is closed by one block, or (gable roof) by a block and the tie beside its rafter
            cover = [_extent([m], 0) for m in over
                     if _extent([m], 0)[1] > lo + 1.0 and _extent([m], 0)[0] < hi - 1.0]
            cover += [_extent([m], 0) for m in fr["members"] if gable and m["kind"] == "tie"
                      and _extent([m], 0)[1] > lo + 1.0 and _extent([m], 0)[0] < hi - 1.0]
            at, ok = lo, False
            for c0, c1 in sorted(cover):
                if c0 > at + 1.0:
                    break
                at = max(at, c1)
            ok = at >= hi - 1.0
            if not ok:
                open_.append((wall, a["id"], b["id"]))
    if open_:
        lines = ", ".join(f"{w} wall between {a.split('/')[1]} and {b.split('/')[1]}" for w, a, b in open_[:4])
        f.add("roof-bay-blocking", "check", "Gap between rafters over a wall left open",
              f"{len(open_)} gap(s) between neighbouring rafters over the front or back wall are not closed with a "
              f"block ({lines}{', ...' if len(open_) > 4 else ''}). Unclosed, they let wind, rain and insects into the roof "
              "and leave the roof sheet's edge with nothing under it. Add a block between those rafters.",
              [i for _, a, b in open_ for i in (a, b)][:10])
    else:
        f.add("roof-bay-blocking", "ok", "Gaps between rafters closed",
              "Every gap between neighbouring rafters over the front and back walls is closed with a block.")


def check_fascia(f):
    spec = f.frame["spec"]
    roofed = any(m["kind"] == "rafter" for m in f.frame["members"])
    if not roofed:
        f.add("roof-edges", "ok", "Roof edges", "There is no roof in this frame, so no fascia or bargeboards are needed.")
        return
    want = [("roof/bargeboard-left", "bargeboard on the left"), ("roof/bargeboard-right", "bargeboard on the right")]
    if is_gable(f.frame):
        want = [(f"roof/bargeboard-{sl}-{sd}", f"bargeboard on the {sl} slope's {sd} end")
                for sd in ("left", "right") for sl in ("front", "back")]
    if spec.get("overhang", 0) > 0:
        want = [("roof/fascia-front", "fascia board at the front"), ("roof/fascia-back", "fascia board at the back")] + want
    lacking = [(i, w) for i, w in want if i not in f.by_id]
    if lacking:
        f.add("roof-edges", "check", "Roof edge board missing",
              "The roof has no " + " and no ".join(w for _, w in lacking) + ". These boards cover the cut ends of the "
              "rafters and the roof sheet's edge; without them the ends are open to rain and weather. "
              "Add the missing board.", [i for i in ("roof/rafter-01",) if i in f.by_id])
    else:
        f.add("roof-edges", "ok", "Roof edges",
              "The rafter ends are covered: " + ("fascia boards front and back, " if spec.get("overhang", 0) > 0 else "")
              + ("bargeboards along both slopes at both gable ends." if is_gable(f.frame) else "bargeboards on both sides."))


def _rafter_pairs(f):
    """(front rafter, back rafter) of each common pair of a gable roof, by number."""
    by = f.by_id
    out = []
    for i in sorted(i for i in by if re.fullmatch(r"roof/rafter-front-\d+", i)):
        back = by.get(i.replace("-front-", "-back-"))
        out.append((by[i], back))
    return out


def check_ridge(f):
    """A gable roof's ridge board: thick enough, deep enough for the rafters' plumb cut,
    and every rafter pair meets it face to face."""
    by = f.by_id
    ridge = by.get("roof/ridge")
    rafters = [m for m in f.frame["members"] if m["kind"] == "rafter"]
    if not ridge:
        f.add("ridge", "fix", "No ridge board",
              "A gable roof's rafters are plumb-cut against a ridge board; there is none here, so the rafter pairs "
              "have nothing to lean against at the top. Put the ridge board back.",
              [m["id"] for m in rafters][:1])
        return
    ang = roof_slope(f.frame)
    depth = ridge["size"][1] if abs(_axes(ridge)[1][2]) >= 0.7 else ridge["size"][2]
    thick = ridge["size"][2] if depth == ridge["size"][1] else ridge["size"][1]
    rd = vertical_dims(rafters[0])[1] if rafters else 0.0
    need = rd / math.cos(ang) if ang is not None else rd
    bad = []
    if thick < 25.0 - 0.5:
        bad.append(f"it is {f.length(thick)} thick (at least 25 mm)")
    if depth < need - 0.5:
        bad.append(f"it is {f.length(depth)} deep, less than the rafters' plumb cut ({f.length(need)})")
    ylo, yhi = _extent([ridge], 1)
    lone = []
    for a, b in _rafter_pairs(f):
        for m, face in ((a, ylo), (b, yhi)):
            if m is None or contact(m, ridge, 1.0) is None or abs(_prism(m, 1)[1 if m is a else 0] - face) > 1.0:
                lone.append(m["id"] if m else a["id"].replace("-front-", "-back-"))
    if lone:
        bad.append(f"{len(lone)} rafter(s) do not meet it face to face (first: {lone[0]})")
    if bad:
        f.add("ridge", "fix", "Ridge board too small or rafters not meeting it",
              "The ridge board: " + "; ".join(bad) + ". The ridge board must be at least 25 mm thick and at least as "
              "deep as the cut end of the rafters, with each pair of rafters landing opposite each other against its faces.",
              ["roof/ridge"] + lone[:5])
    else:
        f.add("ridge", "ok", "Ridge board",
              f"The ridge board is {f.length(thick)} thick and {f.length(depth)} deep (the rafters' plumb cut is "
              f"{f.length(need)}), and every rafter pair meets it face to face.", ["roof/ridge"])


def check_rafter_ties(f):
    """A full-length tie (ceiling joist) beside every rafter pair, bearing on both eave plates and fixed to
    both rafters. A pair over a gable wall is tied by that wall's top plates."""
    by = f.by_id
    plates = [m for m in f.frame["members"] if m["group"] in ("wall-left", "wall-right") and m["kind"] == "plate"]
    walls = [(_extent([m], 0)) for m in plates]
    gab_lo = min((lo for lo, _ in walls), default=0.0)
    gab_w = max((hi - lo for lo, hi in walls), default=0.0)
    width = f.frame["spec"]["width"]
    top = max((_extent([m], 2)[1] for m in f.frame["members"] if m["id"] == "wall-front/plate-top-2"),
              default=None)
    if top is None:
        top = max(_extent([m], 2)[1] for m in f.frame["members"] if m["id"] == "wall-front/plate-top")
    joined = {frozenset((j["a"], j["b"])) for j in f.frame["joints"] if j["type"] in ("tie-rafter", "tie-plate")}
    bear = {sl: next((by[i] for i in (f"wall-{sl}/plate-top-2", f"wall-{sl}/plate-top") if i in by), None)
            for sl in ("front", "back")}
    y_lo = _extent([bear["front"]], 1)[0] if bear["front"] else 0.0       # outer face of the front plate
    y_hi = _extent([bear["back"]], 1)[1] if bear["back"] else f.frame["spec"]["depth"]
    missing, loose, over = [], [], 0
    for a, b in _rafter_pairs(f):
        lo, hi = _extent([a], 0)
        if lo < gab_lo + gab_w - 1.0 or hi > width - gab_w + 1.0:
            over += 1
            continue
        tie = by.get(a["id"].replace("rafter-front-", "tie-"))
        if tie is None:
            missing.append(a["id"])
            continue
        ys, zs, xs = _extent([tie], 1), _extent([tie], 2), _extent([tie], 0)
        need = [(tie["id"], m["id"]) for m in (a, b, bear["front"], bear["back"]) if m is not None]
        if (abs(zs[0] - top) > 1.0 or abs(ys[0] - y_lo) > 1.0 or abs(ys[1] - y_hi) > 1.0
                or abs(xs[0] - hi) > 1.0 or b is None or None in bear.values()
                or any(frozenset(pair) not in joined for pair in need)):
            loose.append(tie["id"])
    if missing or loose:
        text = []
        if missing:
            text.append(f"{len(missing)} rafter pair(s) have no tie (first: {missing[0]})")
        if loose:
            text.append(f"{len(loose)} tie(s) do not run level on both eave plates from outer face to outer face beside the rafter, "
                        f"fixed to both rafters and both plates (first: {loose[0]})")
        f.add("rafter-ties", "fix", "Rafter pair without a tie",
              "; ".join(text).capitalize() + ". With a ridge board (not a ridge beam), the weight of the roof pushes "
              "the walls outward; a ceiling joist or tie across the building on the wall plates, fixed to both rafters of every pair, holds them in.",
              (missing + loose)[:10])
    else:
        f.add("rafter-ties", "ok", "Rafter ties",
              "Every rafter pair has a full-length tie (ceiling joist) beside it, on both eave plates, fixed to both rafters"
              + (f"; the {over} pair(s) over the gable walls are tied by those walls' top plates." if over else "."))


def check_floating(f, tol=1.0, show=5):
    ms = f.frame["members"]
    boxes = [box_corners(m) for m in ms]
    lo = np.array([b.min(0) for b in boxes]) - tol
    hi = np.array([b.max(0) for b in boxes]) + tol
    floating = []
    for i, m in enumerate(ms):
        near = np.nonzero(np.all((lo <= hi[i]) & (hi >= lo[i]), axis=1))[0]
        if not any(j != i and contact(m, ms[j], tol) is not None for j in near):
            floating.append(m["id"])
    if floating:
        shown = ", ".join(floating[:show]) + (f" and {len(floating) - show} more" if len(floating) > show else "")
        f.add("floating-piece", "fix", "Piece touching nothing",
              f"{len(floating)} piece(s) touch no other piece: {shown}. A piece that hangs in the air is held by "
              "nothing, which usually means an edit moved it away from where it belongs. Move it back against "
              "the frame or remove it.", floating[:50])
    else:
        f.add("floating-piece", "ok", "Every piece touches another", "Every piece touches at least one other piece, so nothing hangs in the air.")


def check_floor_blocking(f, tol=2.0):
    fr = f.frame
    floor = [m for m in fr["members"] if m["group"] == "floor" and m["kind"] in ("joist", "rim")]
    blocks = [m for m in fr["members"] if m["group"] == "floor" and m["kind"] == "blocking"]
    if not blocks or not floor:
        f.add("floor-blocking-symmetry", "ok", "Floor blocking", "There are no rows of floor blocking to compare.")
        return
    lo, hi = _extent(floor, 1)
    rows = []
    for y in sorted(centre(m)[1] for m in blocks):
        if not rows or y - rows[-1] > tol:
            rows.append(y)
    mirror = sorted(lo + hi - y for y in rows)
    off = [y for y in rows if not any(abs(y - z) <= tol for z in mirror)]
    if off:
        ids = [m["id"] for m in blocks if any(abs(centre(m)[1] - y) <= tol for y in off)]
        f.add("floor-blocking-symmetry", "check", "Floor blocking not symmetric",
              f"The rows of blocking between the floor joists are not the same either side of the middle "
              f"(a row sits {f.length(off[0] - lo)} from the front with none matching it at the back). "
              "It is not wrong in itself, but the floor sheets are laid symmetrically and the rows are meant to follow "
              "their joints; check that the row was moved on purpose.", ids[:20])
    else:
        f.add("floor-blocking-symmetry", "ok", "Floor blocking",
              "The rows of floor blocking are symmetric about the middle of the floor.")


def check_ground(f):
    near = _f("common", "near_ground_mm")
    bad = []
    for m in f.frame["members"]:
        if m["kind"] in ("sheet",):
            continue
        zmin = float(box_corners(m)[:, 2].min())
        if m["kind"] in ("ground-screw", "pier", "footing", "post-base"):
            continue                    # bought footings are not timber
        if zmin < near - 0.5 and not m.get("treated"):
            bad.append(m)
    if bad:
        f.add("ground-treated", "check", "Timber near the ground is not treated",
              f"{len(bad)} piece(s) lie within {f.length(near)} of the ground and are not marked treated "
              f"(first: {bad[0]['id']}). Untreated timber that close to the ground rots; use treated timber for these "
              f"pieces, or lift the frame on blocks.", [m["id"] for m in bad][:50])
    else:
        f.add("ground-treated", "ok", "Timber near the ground",
              f"Everything within {f.length(near)} of the ground is marked treated.")


def check_pitch(f):
    spec, lib = f.frame["spec"], f.lib
    ang = roof_slope(f.frame)
    cov = spec.get("roofing", "roofing-felt")
    limits = lib["defaults"].get("min_roof_pitch_deg", {})
    unv = lib["defaults"].get("unverified", False)
    if ang is None:
        f.add("roof-pitch", "ok", "Roof pitch", "There is no roof in this frame.")
        return
    deg = math.degrees(ang)
    if cov not in limits:
        f.add("roof-pitch", "check", "Roof pitch: unknown covering",
              f"The roof slopes {deg:.1f} degrees, but the library has no minimum pitch for {cov!r}; "
              f"check the maker's minimum.", [m["id"] for m in f.frame["members"] if m["kind"] == "rafter"][:1])
        return
    lim = limits[cov]
    note = " (The minimum is marked unverified in the library; check the maker's figure.)" if unv else ""
    r = [m["id"] for m in f.frame["members"] if m["kind"] == "rafter"][:1]
    if deg < lim - 0.05:
        f.add("roof-pitch", "fix", "Roof too flat for its covering",
              f"The roof slopes {deg:.1f} degrees; {cov} needs at least {lim:g}. Raise the front or lower the back wall, "
              f"or choose another covering.{note}", r)
    else:
        f.add("roof-pitch", "ok", "Roof pitch",
              f"The roof slopes {deg:.1f} degrees; {cov} needs at least {lim:g}.{note}", r)


def check_wall_bracing(f):
    bad = []
    spec = f.frame["spec"]
    sides = [w["side"] for w in spec["walls"]] if "walls" in spec else ["front", "back", "left", "right"]
    if not sides:
        f.add("wall-bracing", "ok", "Wall bracing", "There are no walls: the open sides are braced with knee braces instead.")
        return
    for wall in sides:
        grp = f"wall-{wall}"
        if not any(m["group"] == grp and m["kind"] in ("sheet", "brace") for m in f.frame["members"]):
            bad.append(wall)
    if bad:
        ids = [m["id"] for m in f.frame["members"] if m["group"] == f"wall-{bad[0]}"][:1]
        f.add("wall-bracing", "fix", "Wall with no sheathing or brace",
              f"The {' and '.join(bad)} wall{'s have' if len(bad) > 1 else ' has'} neither sheathing nor a diagonal brace, "
              f"so nothing stops the frame racking sideways. Add sheathing or a diagonal brace.", ids)
    else:
        f.add("wall-bracing", "ok", "Wall bracing", "Every wall has sheathing or a brace to stop it racking.")


# ============================================================== TERRACE
# A terrace has no walls or roof: its checks are the spans of the deck joists
# and the beams, the boards' span, and two layout rules (every post on a
# footing, every beam end over a support). Footings are bought items whose load
# capacity is not checked.

def is_terrace(frame):
    return frame["spec"].get("type") == "terrace"


def check_terrace_joists(f):
    fr, lib, spec = f.frame, f.lib, f.frame["spec"]
    sp = span_of(fr, "joist")
    joists = [m for m in fr["members"] if m["kind"] == "joist"]
    if not (sp and joists):
        f.add("span-joists", "check", "Deck joists", "There are no deck joists in this frame, so no span was checked.")
        return
    ld = terrace_loads(lib, spec)
    m = joists[0]
    b, d = vertical_dims(m)
    s = sp["spacing_mm"] / 1000.0
    res = allowable_span(lib, b, d, ld["deck_kn_m2"] * s, ld["live_kn_m2"] * s, "floor", repetitive=len(joists) >= 4)
    span, allowed = sp["span_mm"], res["span_mm"]
    level = level_for(span, allowed)
    verdict = {"ok": "That is comfortable.",
               "check": "That is close to the limit: use a deeper joist, closer joists or another beam row.",
               "fix": "That is too long: use a deeper joist, closer joists or another beam row."}[level]
    f.add("span-joists", level, f"Deck joists: {section_name(lib, m['item'])} at {f.length(sp['spacing_mm'])}",
          f"Deck joists span {f.length(span)} between beams (centre to centre of the farthest two). "
          f"This section is good for about {f.length(allowed)} at this spacing under the boards and a load of "
          f"{f.load(ld['live_kn_m2'])} (limited by {res['governs']}). {verdict} "
          f"Counted as simply supported between beams; the overhang past the end beams only helps.", [m["id"]])


def check_terrace_beams(f, atype="beams"):
    fr, lib, spec = f.frame, f.lib, f.frame["spec"]
    ld = terrace_loads(lib, spec)
    rows = [sp for a in fr.get("assemblies", []) if a["type"] == atype for sp in a["spans"] if sp["kind"] == "beam"]
    if not rows:
        f.add("span-beams", "check", "Beams", "There are no beams in this frame, so no beam span was checked.")
        return
    for r in sorted(rows, key=lambda r: r["id"]):
        res = beam_allowed(lib, spec, ld, r["trib_mm"], r["plies"], r["item"], detail=True)
        span, allowed = r["span_mm"], res["span_mm"]
        level = level_for(span, allowed)
        verdict = {"ok": "That is comfortable.",
                   "check": "That is close to the limit: use a deeper beam or put a post in sooner.",
                   "fix": "That is too long: use a deeper beam, two plies, or more posts."}[level]
        name = section_name(lib, r["item"]) + (f", {r['plies']} together" if r["plies"] > 1 else "")
        f.add(f"span-{r['id'].replace('/', '-')}", level, f"Beam {r['id'].split('/')[-1]}: {name}",
              f"The beam spans {f.length(span)} between posts and carries a strip of deck {f.length(r['trib_mm'])} wide "
              f"at {f.load(ld['live_kn_m2'])}. This section is good for about {f.length(allowed)} (limited by "
              f"{res['governs']}). {verdict}", [r["id"]] if r["id"] in f.by_id else [])


def check_deck_boards(f):
    fr, lib = f.frame, f.lib
    sp = next((x for a in fr.get("assemblies", []) for x in a["spans"] if x["kind"] == "deckboard"), None)
    jsp = span_of(fr, "joist")
    if not (sp and jsp):
        f.add("deck-board-span", "ok", "Deck boards", "There are no deck boards in this frame.")
        return
    lim, spacing = sp.get("max_joist_spacing_mm"), jsp["spacing_mm"]
    name = section_name(lib, sp["item"])
    if lim is None:
        f.add("deck-board-span", "check", "Deck boards", f"No span limit is recorded for {name}; its joist spacing was not checked.")
    elif spacing > lim + 0.5:
        ids = [m["id"] for m in fr["members"] if m["kind"] == "deckboard"][:50]
        f.add("deck-board-span", "check", "Deck boards on joists too far apart",
              f"The {name} boards span {f.length(spacing)} between joists; the limit for this board is {f.length(lim)} "
              "(a rule of thumb marked unverified in the library; check the board maker's table). Put the joists closer together or "
              "use a thicker board.", ids)
    else:
        f.add("deck-board-span", "ok", "Deck board span",
              f"The {name} boards span {f.length(spacing)} between joists, within the limit of {f.length(lim)} "
              "(a rule of thumb marked unverified in the library).")


def _members(f, kind):
    return [m for m in f.frame["members"] if m["kind"] == kind]


def check_post_footing(f):
    posts, bases, bodies = _members(f, "post"), _members(f, "post-base"), \
        [m for m in f.frame["members"] if m["kind"] in ("ground-screw", "pier", "footing")]
    joined = {(j["a"], j["b"]) for j in f.frame["joints"] if j["type"] == "post-base"}
    bad = []
    carried = posts or _members(f, "beam")
    for p in carried:
        bs = [b for b in bases if (b["id"], p["id"]) in joined]
        ok = any(contact(b, w, 1.0) is not None for b in bs for w in bodies)
        if not (bs and ok):
            bad.append(p)
    if not carried:
        f.add("post-footing", "ok", "Posts on footings", "There are no posts in this frame.")
    elif bad:
        f.add("post-footing", "fix", "Post not on a footing",
              f"{len(bad)} piece(s) are not fixed to a post base on a footing (first: {bad[0]['id']}). Every post "
              "stands on a footing through a post base, so it stays off the ground and cannot walk.", [m["id"] for m in bad][:50])
    else:
        what = "post" if posts else "beam support"
        f.add("post-footing", "ok", "Posts on footings",
              f"Every {what} stands on a post base fixed to a footing (ground screw, block or poured pier; "
              "the footings' load capacity is not checked).")


def check_beam_bearing(f, max_end=300.0, atype="beams", prefix=None, fid="beam-bearing", label="Beam"):
    """Every beam end over a post or footing. `atype` the beams' assembly type; `prefix` (a summer
    kitchen) the id prefixes of the posts and post bases they bear on, e.g. ("posts/", "foundations/")."""
    fr = f.frame
    recs = [sp for a in fr.get("assemblies", []) if a["type"] == atype for sp in a["spans"] if sp["kind"] == "beam"]
    if not recs:
        f.add(fid, "ok", f"{label} bearing", "There are no beams in this frame.")
        return
    if prefix:
        sup = [m for m in _members(f, "post") if m["id"].startswith(prefix[0])] or \
            [m for m in _members(f, "post-base") if m["id"].startswith(prefix[1])]
    else:
        sup = _members(f, "post") or _members(f, "post-base")
    by = f.by_id
    bad = []
    for r in recs:
        b = by.get(r["id"])
        if b is None:
            continue
        ax = 0 if abs(b["x"][0]) > 0.5 else 1
        ends = box_corners(b)[:, ax]
        lo, hi = float(ends.min()), float(ends.max())
        line = 1 - ax
        cl = [float(centre(s)[ax]) for s in sup if abs(float(centre(s)[line]) - r["line"]) <= 1.0]
        if not cl or min(cl) - lo > max_end + 0.5 or hi - max(cl) > max_end + 0.5:
            bad.append(b)
    if bad:
        f.add(fid, "fix", "Beam end with no support",
              f"{len(bad)} beam(s) reach more than {f.length(max_end)} past their last post or have none under them "
              f"(first: {bad[0]['id']}). Every beam end must be over a post or footing, or within a short overhang of one.",
              [m["id"] for m in bad][:50])
    else:
        f.add(fid, "ok", f"{label} bearing",
              f"Every {label.lower()} is over a post or footing at both ends, overhanging by no more than {f.length(max_end)}.")


def check_railing(f, h=None):
    h = f.frame["spec"]["height"] if h is None else h
    lim = f.lib["defaults"]["terrace"]["railing_height_mm"]
    if h > lim + 0.5:
        f.add("railing", "check", "A railing is usually required",
              f"The deck is {f.length(h)} above the ground. Above about {f.length(lim)} most places require a guard "
              "rail around the open sides (and steps with a handrail). The workbench does not draw rails or steps yet: "
              "check your local rules.", [])
    else:
        f.add("railing", "ok", "Railing",
              f"The deck is {f.length(h)} above the ground, under about {f.length(lim)}, where a railing is usually not required "
              "(check your local rules).")


def run_terrace(f):
    check_terrace_joists(f)
    check_terrace_beams(f)
    check_deck_boards(f)
    check_stock_length(f)
    check_post_footing(f)
    check_beam_bearing(f)
    check_railing(f)
    check_floating(f)


# ============================================================== PERGOLA
# An open structure: footings, posts, two beams, rafters across them (with an
# overhang), optional slats and knee braces. Its checks are the rafter and beam
# spans, post-footing, beam-bearing, and `open-bracing`: every post-to-beam corner
# that has room for one carries a knee brace. Snow is the only load; wind, uplift
# and the footings' capacity are not checked.

PERGOLA_MAX_BEAM_END = 500.0    # mm a pergola beam may reach past its last post's centre line


def is_pergola(frame):
    return frame["spec"].get("type") == "pergola"


def check_pergola_rafters(f):
    fr, lib, spec = f.frame, f.lib, f.frame["spec"]
    sp = span_of(fr, "rafter")
    rafters = [m for m in fr["members"] if m["kind"] == "rafter"]
    if not (sp and rafters):
        f.add("span-rafters", "check", "Rafters", "There are no rafters in this frame, so no span was checked.")
        return
    res = pergola_rafter_allowed(lib, spec)
    span, allowed = sp["span_mm"], res["span_mm"]
    level = level_for(span, allowed)
    verdict = {"ok": "That is comfortable.",
               "check": "That is close to the limit: use a deeper rafter or put them closer together.",
               "fix": "That is too long: use a deeper rafter, closer rafters or beams further out."}[level]
    over = sp["overhang_mm"]
    note = ""
    if over > span / 4.0 + 0.5:
        note = (f" The overhang of {f.length(over)} is more than a quarter of the span: keep the tails shorter "
                "or check them.")
        if level == "ok":
            level = "check"
    snow = spec["loads"]["snow_kn_m2"]
    f.add("span-rafters", level, f"Rafters: {section_name(lib, rafters[0]['item'])} at {f.length(sp['spacing_mm'])}",
          f"Rafters span {f.length(span)} between the beams (centre to centre). This section is good for about "
          f"{f.length(allowed)} at this spacing and a snow load of {f.load(snow)} (limited by {res['governs']}). {verdict} "
          f"Counted as simply supported between the beams; the overhang only helps.{note}", [rafters[0]["id"]])


def check_pergola_beams(f):
    fr, lib, spec = f.frame, f.lib, f.frame["spec"]
    rows = [sp for a in fr.get("assemblies", []) if a["type"] == "beams" for sp in a["spans"] if sp["kind"] == "beam"]
    if not rows:
        f.add("span-beams", "check", "Beams", "There are no beams in this frame, so no beam span was checked.")
        return
    res = pergola_beam_allowed(lib, spec, detail=True)
    for r in sorted(rows, key=lambda r: r["id"]):
        span, allowed = r["span_mm"], res["span_mm"]
        level = level_for(span, allowed)
        verdict = {"ok": "That is comfortable.",
                   "check": "That is close to the limit: use a deeper beam or put a post in sooner.",
                   "fix": "That is too long: use a deeper beam, more plies or more posts."}[level]
        name = section_name(lib, r["item"]) + (f", {r['plies']} together" if r["plies"] > 1 else "")
        f.add(f"span-{r['id'].replace('/', '-')}", level, f"Beam {r['id'].split('/')[-1]}: {name}",
              f"The beam spans {f.length(span)} between posts and carries {f.length(r['trib_mm'])} of rafters "
              f"(half the span between the beams plus the overhang) at a snow load of {f.load(spec['loads']['snow_kn_m2'])}. "
              f"This section is good for about {f.length(allowed)} (limited by {res['governs']}). {verdict}",
              [r["id"]] if r["id"] in f.by_id else [])


def check_open_bracing(f):
    """Every post under a beam is braced in both directions: along the beam (on each side where a
    brace has room) and across the beams (inward, to the rafter over the post). Each brace
    touches the post and what it braces against."""
    from timber.pergola import MIN_BRACE_CLEAR
    fr = f.frame
    recs = [sp for a in fr.get("assemblies", []) if a["type"] == "beams" for sp in a["spans"] if sp["kind"] == "beam"]
    posts, braces, rafters = _members(f, "post"), _members(f, "brace"), _members(f, "rafter")
    if not (recs and posts):
        f.add("open-bracing", "ok", "Open bracing", "There are no posts under beams in this frame.")
        return
    missing, total = [], 0
    lines = sorted({r["line"] for r in recs})
    for r in recs:
        beam = f.by_id.get(r["id"])
        if beam is None:
            continue
        ax = 0 if abs(beam["x"][0]) > 0.5 else 1
        ends = box_corners(beam)[:, ax]
        lo, hi = float(ends.min()), float(ends.max())
        kit = is_kitchen(fr)
        walled = {w["side"] for w in fr["spec"].get("walls", []) if any(m["group"] == f"wall-{w['side']}" for m in fr["members"])}
        for p in posts:
            c = centre(p)
            if abs(c[1 - ax] - r["line"]) > 1.0 or contact(p, beam, 1.0) is None:
                continue
            pe = box_corners(p)[:, ax]
            half = float(pe.max() - pe.min()) / 2.0
            back_line = kit and r["line"] > fr["spec"]["depth"] / 2.0
            end_wall = kit and ((c[ax] - half <= lo + 1.0 and "left" in walled) or (c[ax] + half >= hi - 1.0 and "right" in walled))
            for side, clear in ((1, hi - (c[ax] + half)), (-1, (c[ax] - half) - lo)):
                if clear < MIN_BRACE_CLEAR or (back_line and "back" in walled):
                    continue
                total += 1
                ok = any(contact(b, p, 1.0) is not None and contact(b, beam, 1.0) is not None
                         and (centre(b)[ax] - c[ax]) * side > 0 and abs(centre(b)[1 - ax] - r["line"]) <= 1.0
                         for b in braces)
                if not ok:
                    missing.append((p["id"], "along the beam"))
            other = [x for x in lines if abs(x - r["line"]) > 1.0]
            if other and not end_wall:
                inward = 1 if other[0] > r["line"] else -1
                pc = box_corners(p)[:, 1 - ax]
                if abs(other[0] - r["line"]) - float(pc.max() - pc.min()) >= MIN_BRACE_CLEAR:
                    total += 1
                    ok = any(contact(b, p, 1.0) is not None and any(contact(b, q, 1.0) is not None for q in rafters)
                             and (centre(b)[1 - ax] - c[1 - ax]) * inward > 0
                             and abs(centre(b)[ax] - c[ax]) <= (half + 1.0 if kit else 1.0)
                             for b in braces)
                    if not ok:
                        missing.append((p["id"], "across the beams"))
    if missing:
        names = ", ".join(sorted({f"{m[0]} ({m[1]})" for m in missing}))
        f.add("open-bracing", "fix", "Post corner with no knee brace",
              f"{len(missing)} post corner(s) have no knee brace touching both the post and what it braces against "
              f"(posts: {names}). An open side has no wall to stop it racking, so every post needs a 45 degree brace up "
              "to the beam on each side where the beam runs on, and one across the beams up to the rafter over the "
              "post. Add the brace, or turn `braces` back on.", [missing[0][0]])
    else:
        f.add("open-bracing", "ok", "Open bracing",
              f"All {total} post corners that have room carry a knee brace, along the beams and across them, "
              "touching both the post and the beam or rafter.")


# ======================================================== SUMMER KITCHEN
# Posts and beams under a mono or gable roof, with an optional terrace floor and
# up to three walls between the posts. The roof's rafter, ridge, tie, edge and
# pitch checks are the sheds'; the beams are checked under the roof's load; the
# floor's under the terrace's; the walls are infill (the beams rest on the posts)
# and braced by their sheathing; every open side has its knee braces.

def check_kitchen_beams(f):
    fr, lib, spec = f.frame, f.lib, f.frame["spec"]
    rows = [sp for a in fr.get("assemblies", []) if a["type"] == "beams" for sp in a["spans"] if sp["kind"] == "beam"]
    if not rows:
        f.add("span-beams", "check", "Beams", "There are no beams in this frame, so no beam span was checked.")
        return
    res = kitchen_beam_allowed(lib, spec, detail=True)
    snow = spec["loads"]["snow_kn_m2"]
    for r in sorted(rows, key=lambda r: r["id"]):
        span, allowed = r["span_mm"], res["span_mm"]
        level = level_for(span, allowed)
        verdict = {"ok": "That is comfortable.",
                   "check": "That is close to the limit: use a deeper beam or put a post in sooner.",
                   "fix": "That is too long: use a deeper beam, more plies or more posts."}[level]
        name = section_name(lib, r["item"]) + (f", {r['plies']} together" if r["plies"] > 1 else "")
        f.add(f"span-{r['id'].replace('/', '-')}", level, f"Roof beam {r['id'].split('/')[-1]}: {name}",
              f"The beam spans {f.length(span)} between posts and carries {f.length(r['trib_mm'])} of roof (half the span "
              f"between the beams plus the overhang) at a snow load of {f.load(snow)}. This section is good for about "
              f"{f.length(allowed)} (limited by {res['governs']}). {verdict}", [r["id"]] if r["id"] in f.by_id else [])


def check_kitchen_ties(f):
    """A gable kitchen's ties (ceiling joists): one beside every rafter pair that is not over a walled end,
    level on top of both beams from outer face to outer face and fixed to both rafters and both beams."""
    fr, by, spec = f.frame, f.by_id, f.frame["spec"]
    walled = {w["side"] for w in spec["walls"]}
    ptx = f.lib["sections"][spec["post_item"]]["thickness_mm"]
    W, D = spec["width"], spec["depth"]
    beams = {k: [m for m in fr["members"] if m["id"].startswith(f"beams/beam-{k}")] for k in ("01", "02")}
    if not all(beams.values()):
        f.add("rafter-ties", "ok", "Rafter ties", "There are no roof beams to tie.")
        return
    top = max(_extent([m], 2)[1] for ms in beams.values() for m in ms)
    joined = {frozenset((j["a"], j["b"])) for j in fr["joints"] if j["type"] in ("tie-rafter", "tie-plate")}
    missing, loose, over = [], [], 0
    for a, b in _rafter_pairs(f):
        lo, hi = _extent([a], 0)
        if ("left" in walled and lo < ptx - 1.0) or ("right" in walled and hi > W - ptx + 1.0):
            over += 1
            continue
        tie = by.get(a["id"].replace("rafter-front-", "tie-"))
        if tie is None:
            missing.append(a["id"])
            continue
        ys, zs = _extent([tie], 1), _extent([tie], 2)
        ok = abs(zs[0] - top) <= 1.0 and abs(ys[0]) <= 1.0 and abs(ys[1] - D) <= 1.0 and b is not None
        ok = ok and all(any(frozenset((tie["id"], m["id"])) in joined for m in ms) for ms in beams.values())
        ok = ok and all(frozenset((tie["id"], m["id"])) in joined for m in (a, b))
        if not ok:
            loose.append(tie["id"])
    if missing or loose:
        text = []
        if missing:
            text.append(f"{len(missing)} rafter pair(s) have no tie (first: {missing[0]})")
        if loose:
            text.append(f"{len(loose)} tie(s) do not run level on both beams from outer face to outer face, fixed to both "
                        f"rafters and both beams (first: {loose[0]})")
        f.add("rafter-ties", "fix", "Rafter pair without a tie",
              "; ".join(text).capitalize() + ". With a ridge board (not a ridge beam), the weight of the roof pushes the beams "
              "outward; a ceiling joist or tie across the building on the beams, fixed to both rafters of every pair, holds them in.",
              (missing + loose)[:10])
    else:
        f.add("rafter-ties", "ok", "Rafter ties",
              "Every rafter pair has a full-length tie (ceiling joist) beside it, on both beams, fixed to both rafters"
              + (f"; the {over} pair(s) over a walled end are held by that wall." if over else "."))


def check_kitchen_walls(f):
    spec = f.frame["spec"]
    if not spec["walls"]:
        f.add("wall-infill", "ok", "Walls", "There are no walls: every side is open and braced with knee braces.")
        return
    sides = " and ".join(w["side"] for w in spec["walls"])
    f.add("wall-infill", "ok", "Walls are infill between the posts",
          f"The {sides} wall{'s are' if len(spec['walls']) > 1 else ' is'} framed between the posts, on a treated sole plate. "
          "The beams rest on the posts alone and the top plates only touch them, so a header over a door or window carries no "
          "roof load and is not checked; the posts, not the walls, hold the roof up.")


def run_kitchen(f):
    fr = f.frame
    spec = fr["spec"]
    check_rafters(f)
    check_kitchen_beams(f)
    if is_gable(fr):
        check_ridge(f)
        check_kitchen_ties(f)
    check_fascia(f)
    check_pitch(f)
    check_sheet_spacing(f)
    check_sheet_edges(f)
    check_stock_length(f)
    check_openings(f)
    check_wall_bracing(f)
    check_kitchen_walls(f)
    check_bay_blocking(f)
    check_ground(f)
    if spec["floor"] == "terrace":
        check_terrace_joists(f)
        check_terrace_beams(f, atype="floor-beams")
        check_deck_boards(f)
        check_railing(f, spec["floor_height"])
    check_post_footing(f)
    check_beam_bearing(f, max_end=PERGOLA_MAX_BEAM_END, prefix=("posts/", "foundations/"))
    if spec["floor"] == "terrace":
        check_beam_bearing(f, atype="floor-beams", prefix=("floor-posts/", "floor-foundations/"),
                           fid="floor-beam-bearing", label="Floor beam")
    check_open_bracing(f)
    check_floating(f)


DISCLAIMER_KITCHEN = ("This is guidance from simple formulas, not structural engineering. Rafters, beams, deck joists and "
                      "headers were treated as beams under an even load (snow on the roof, people on the floor); wind and uplift "
                      "(an open roof can act like a sail), racking, the footings (ground screws, blocks, poured piers), the soil, "
                      "frost, fixings, the knee braces' strength and the walls' fire and moisture detailing were not checked, and "
                      "local building rules may apply (permits, distance from boundaries, a cooking fire or chimney). Anything people "
                      "shelter under, or that has a stove or a flue, should be checked by a qualified person.")


def run_pergola(f):
    check_pergola_rafters(f)
    check_pergola_beams(f)
    check_stock_length(f)
    check_post_footing(f)
    check_beam_bearing(f, max_end=PERGOLA_MAX_BEAM_END)
    check_open_bracing(f)
    check_floating(f)


DISCLAIMER = ("This is guidance from simple formulas, not structural engineering. Joists, rafters and headers were "
              "treated as beams under an even load; wind, uplift, shear, fixings, the ground and the loads on "
              "neighbouring walls were not checked, and local building rules may apply (permits, snow and wind zones, "
              "distance from boundaries). For anything that people will shelter in or that could hurt someone if it "
              "fails, have it checked by a qualified person.")

DISCLAIMER_TERRACE = ("This is guidance from simple formulas, not structural engineering. Deck joists and beams were "
                      "treated as beams under an even load; the footings (ground screws, blocks, poured piers), the soil, "
                      "frost, wind, fixings and the connections to a house were not checked, and local building rules may "
                      "apply (permits, rails above a certain height, distance from boundaries). For anything that people "
                      "stand on well above the ground, have it checked by a qualified person.")


DISCLAIMER_PERGOLA = ("This is guidance from simple formulas, not structural engineering. Rafters and beams were "
                      "treated as beams under snow only; wind and uplift (an open pergola can act like a sail), the footings "
                      "(ground screws, blocks, poured piers), the soil, frost, fixings and the knee braces' strength were not "
                      "checked, and local building rules may apply (permits, distance from boundaries). If it carries a roof "
                      "covering or climbing plants, or stands near people, have it checked by a qualified person.")


def run(frame):
    lib = tl.load(frame["region"])
    f = Findings(frame, lib)
    if is_kitchen(frame):
        run_kitchen(f)
        f.add("guidance-only", "ok", "Guidance only", DISCLAIMER_KITCHEN)
        return {"schema": 1, "region": frame["region"], "units": frame["units"],
                "factors": FACTORS["common"] | FACTORS[frame["region"]], "findings": f.items}
    if is_pergola(frame):
        run_pergola(f)
        f.add("guidance-only", "ok", "Guidance only", DISCLAIMER_PERGOLA)
        return {"schema": 1, "region": frame["region"], "units": frame["units"],
                "factors": FACTORS["common"] | FACTORS[frame["region"]], "findings": f.items}
    if is_terrace(frame):
        run_terrace(f)
        f.add("guidance-only", "ok", "Guidance only", DISCLAIMER_TERRACE)
        return {"schema": 1, "region": frame["region"], "units": frame["units"],
                "factors": FACTORS["common"] | FACTORS[frame["region"]], "findings": f.items}
    check_joists(f)
    check_rafters(f)
    check_headers(f)
    check_sheet_spacing(f)
    check_sheet_edges(f)
    check_stock_length(f)
    check_openings(f)
    check_ground(f)
    check_pitch(f)
    check_wall_bracing(f)
    check_corners(f)
    check_plate_lap(f)
    check_bay_blocking(f)
    check_fascia(f)
    if is_gable(frame):
        check_ridge(f)
        check_rafter_ties(f)
    check_floating(f)
    check_floor_blocking(f)
    f.add("guidance-only", "ok", "Guidance only", DISCLAIMER)   # information on every run, never a reason a structure is "not ready"
    return {"schema": 1, "region": frame["region"], "units": frame["units"],
            "factors": FACTORS["common"] | FACTORS[frame["region"]], "findings": f.items}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build checks for a timber frame (guidance, not engineering).")
    ap.add_argument("frame")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.frame, encoding="utf-8") as fh:
        frame = json.load(fh)
    out = run(frame)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    counts = {lv: sum(1 for x in out["findings"] if x["level"] == lv) for lv in ("ok", "check", "fix")}
    print(f"framecheck: {counts['ok']} ok, {counts['check']} check, {counts['fix']} fix -> {a.out}")
    for x in out["findings"]:
        if x["level"] != "ok":
            print(f"  [{x['level']}] {x['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
