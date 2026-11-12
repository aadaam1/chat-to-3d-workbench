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

# =========================================================== FACTOR TABLE
# Every factor the span formulas use, with where it comes from. `status`:
#   "published"  a number printed in a source the workbench read (see `source`)
#   "standard"   the value the cited standard gives, as widely reproduced;
#                the standard itself was NOT read (the tests compare the
#                result with published span tables instead)
#   "assumption" the workbench's own choice, named so it can be changed
# The research note (docs/research/timber-structures.md, T4) lists the dates
# the sources were read.
FACTORS = {
    "common": {
        "deflection_limit": {"value": 360, "status": "assumption",
            "source": "Planning decision, 2026-11-11 (not a standard): span / 360 for both regions.",
            "note": "Applied to the full characteristic load (own weight + deck + snow or floor load), no creep. At span / 300 the formulas ran up to 20% longer than the published C24 tables; those tables also cover a point load and vibration that this simple beam model leaves out, so the stricter limit stands in for them."},
        "g": {"value": 9.81, "status": "published", "source": "Standard gravity, m/s2."},
        "sheet_density_kg_m3": {"value": 600, "status": "assumption",
            "source": "Typical OSB density; not read from a datasheet.",
            "note": "Weight of the floor and roof deck sheets, per mm of thickness."},
        "covering_kn_m2": {"value": {"roofing-felt": 0.05, "metal-sheet": 0.06, "asphalt-shingle": 0.15},
            "status": "assumption", "source": "Typical weights of a light roof covering; not read from a datasheet.",
            "note": "Unknown coverings use 0.10 kN/m2."},
        "kn_m2_to_psf": {"value": 20.885, "status": "published", "source": "1 kN/m2 = 20.885 lbf/ft2."},
        "near_ground_mm": {"value": 150, "status": "assumption", "source": "Task spec: timber within 150 mm of the ground."},
    },
    "eu": {
        "gamma_G": {"value": 1.35, "status": "standard",
            "source": "EN 1990:2002 Table A1.2(B), eq. 6.10: partial factor on permanent actions."},
        "gamma_Q": {"value": 1.5, "status": "standard",
            "source": "EN 1990:2002 Table A1.2(B): partial factor on variable actions."},
        "gamma_M": {"value": 1.3, "status": "standard",
            "source": "EN 1995-1-1:2004 Table 2.3: material factor, solid timber."},
        "k_mod_permanent": {"value": 0.6, "status": "standard",
            "source": "EN 1995-1-1 Table 3.1, service class 1 or 2, permanent action.",
            "note": "Service class 2 assumed: roofed, not heated."},
        "k_mod_floor": {"value": 0.8, "status": "standard",
            "source": "EN 1995-1-1 Table 3.1, service class 2, medium-term action (imposed floor load)."},
        "k_mod_snow": {"value": 0.9, "status": "standard",
            "source": "EN 1995-1-1 Table 3.1, service class 2, short-term action (snow, below 1000 m altitude)."},
        "k_h": {"value": "min((150 / depth_mm) ** 0.2, 1.3) for depth < 150 mm, else 1.0", "status": "standard",
            "source": "EN 1995-1-1 eq. 3.1: size factor, solid timber."},
        "k_sys": {"value": 1.1, "status": "standard",
            "source": "EN 1995-1-1 6.6: load sharing, joists and rafters at 610 mm or closer under a deck.",
            "note": "Not applied to headers (a single beam)."},
    },
    "us": {
        "C_D_permanent": {"value": 0.9, "status": "standard",
            "source": "NDS 2018 Table 2.3.2: load duration factor, permanent load."},
        "C_D_floor": {"value": 1.0, "status": "published",
            "source": "Southern Forest Products Association, Maximum Spans (2013 ed.), p. 4: floor and ceiling joist tables use C_D = 1.0."},
        "C_D_snow": {"value": 1.15, "status": "published",
            "source": "Southern Forest Products Association, Maximum Spans (2013 ed.), p. 4: rafters, two-month snow load, C_D = 1.15."},
        "C_r": {"value": 1.15, "status": "published",
            "source": "Southern Forest Products Association, Maximum Spans (2013 ed.), p. 4: repetitive member factor 1.15 for at least three joists or rafters at 24 in. or closer, under a deck.",
            "note": "Not applied to headers (a single beam)."},
        "C_F": {"value": {"2": 1.5, "3": 1.5, "4": 1.5, "5": 1.4, "6": 1.3, "8": 1.2, "10": 1.1, "12": 1.0, "14": 0.9},
            "status": "published",
            "source": "NDS 2018 Supplement Table 4A, size factor for Fb, 2 in. and 3 in. thick, by nominal width (AWC NDS2018 Supplement Chapter 4, via a search excerpt: https://awc.org/wp-content/uploads/2021/10/AWC_NDS2018-Supplement_20200827_AWCWebsite_Chapter4.pdf)."},
        "C_M_C_t_C_L": {"value": 1.0, "status": "assumption",
            "source": "Dry service, normal temperature, members braced by the deck (NDS 2018 Ch. 4).",
            "note": "Wet service factors are not applied; a shed in permanent damp needs them."},
    },
}

WARN_FRACTION = 0.85     # a span above this share of the allowable gets "check"
MAX_FRACTION = 1.0       # above this, "fix"


def _f(region, name):
    return FACTORS[region][name]["value"]


# ================================================================ FORMULAS

def own_weight_kn_m(lib, b_mm, d_mm):
    """Weight of a member in kN per metre of its length."""
    g = lib["grades"][lib["defaults"]["grade"]]
    rho = g.get("density_mean_kg_m3", g["density_kg_m3"])
    return b_mm * d_mm * 1e-6 * rho * _f("common", "g") / 1000.0


def us_size_factor(depth_mm):
    nominal = int(round(depth_mm / 25.4 + 0.5))
    table = {int(k): v for k, v in _f("us", "C_F").items()}
    keys = sorted(table)
    return table[min(max(nominal, keys[0]), keys[-1])]


def allowable_span(lib, b_mm, d_mm, g_kn_m, q_kn_m, load_kind, *, repetitive=True,
                   cos_a=1.0, defl_limit=None, defl_basis="total", add_own_weight=True):
    """Longest horizontal span of a simply supported beam under an even load.

    g_kn_m, q_kn_m: permanent and variable load per metre of horizontal span
    (kN/m = N/mm), not counting the member's own weight (added here unless
    add_own_weight is False). load_kind: 'floor' or 'snow'. cos_a: cosine of the
    slope, for a rafter. defl_basis 'total' limits the deflection under
    permanent + variable load, 'live' under the variable load only.
    Returns {"bending_mm", "deflection_mm", "span_mm", "governs"}.
    """
    region = lib["region"]
    grade = lib["grades"][lib["defaults"]["grade"]]
    defl_limit = defl_limit or _f("common", "deflection_limit")
    if add_own_weight:
        g_kn_m = g_kn_m + own_weight_kn_m(lib, b_mm, d_mm) / cos_a
    W = b_mm * d_mm ** 2 / 6.0
    I = b_mm * d_mm ** 3 / 12.0
    if region == "eu":
        kh = min((150.0 / d_mm) ** 0.2, 1.3) if d_mm < 150 else 1.0
        ksys = _f("eu", "k_sys") if repetitive else 1.0
        fmk, E = grade["bending_mpa"], grade["e_mean_mpa"]
        gG, gQ, gM = _f("eu", "gamma_G"), _f("eu", "gamma_Q"), _f("eu", "gamma_M")
        kq = _f("eu", "k_mod_floor" if load_kind == "floor" else "k_mod_snow")
        combos = [(gG * g_kn_m, _f("eu", "k_mod_permanent")), (gG * g_kn_m + gQ * q_kn_m, kq)]
        caps = [(w, kmod * kh * ksys * fmk / gM) for w, kmod in combos]
    elif region == "us":
        cf = us_size_factor(d_mm)
        cr = _f("us", "C_r") if repetitive else 1.0
        other = _f("us", "C_M_C_t_C_L")
        fb, E = grade["bending_mpa"], grade["e_mean_mpa"]
        cdq = _f("us", "C_D_floor" if load_kind == "floor" else "C_D_snow")
        combos = [(g_kn_m, _f("us", "C_D_permanent")), (g_kn_m + q_kn_m, cdq)]
        caps = [(w, fb * cd * cf * cr * other) for w, cd in combos]
    else:
        raise ValueError(f"no span method for region {region!r}")
    # bending: M = w L^2 / 8 (horizontal span and load per horizontal metre, also for a sloped rafter)
    bend = min(math.sqrt(8.0 * f * W / w) for w, f in caps if w > 0)
    w_def = (g_kn_m + q_kn_m) if defl_basis == "total" else q_kn_m
    ls = (384.0 * E * I / (5.0 * defl_limit * w_def * cos_a ** 2)) ** (1.0 / 3.0)
    defl = ls * cos_a
    span = min(bend, defl)
    return {"bending_mm": bend, "deflection_mm": defl, "span_mm": span,
            "governs": "bending" if bend <= defl else "deflection"}


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
        if self.units == "imperial":
            return tl.fmt_length(mm, "imperial")
        return f"{mm / 1000.0:.2f} m" if abs(mm) >= 1000 else f"{mm:.0f} mm"

    def load(self, kn_m2):
        if self.units == "imperial":
            return f"{kn_m2 * _f('common', 'kn_m2_to_psf'):.0f} psf"
        return f"{kn_m2:g} kN/m2"


def level_for(span, allowed):
    if span > allowed * MAX_FRACTION:
        return "fix"
    if span > allowed * WARN_FRACTION:
        return "check"
    return "ok"


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


def is_gable(frame):
    return frame["spec"].get("type") == "gable-shed"


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


def roof_dead_plan(f, lib, spec, cos_a, rafter_b, rafter_d):
    """Permanent roof load in kN per m2 of plan: deck, covering and the rafters."""
    deck = lib["sheets"][spec["roof_deck"]]["thickness_mm"]
    dens = _f("common", "sheet_density_kg_m3")
    deck_kn = deck / 1000.0 * dens * _f("common", "g") / 1000.0
    cov = _f("common", "covering_kn_m2").get(spec.get("roofing"), 0.10)
    rafter = own_weight_kn_m(lib, rafter_b, rafter_d) / (spacing_of(f.frame, "rafter", "rafter_spacing") / 1000.0)
    return (deck_kn + cov + rafter) / cos_a


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
    s = spacing / 1000.0
    deck = lib["sheets"][deck_of(fr, "joist", "floor_deck")]["thickness_mm"]
    deck_kn = deck / 1000.0 * _f("common", "sheet_density_kg_m3") * _f("common", "g") / 1000.0
    qf = spec["loads"]["floor_kn_m2"]
    res = allowable_span(lib, b, d, deck_kn * s, qf * s, "floor", repetitive=len(joists) >= 4)
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
    plates = {p["id"]: p for p in fr["members"] if p["id"] in ("wall-front/plate-top", "wall-back/plate-top")}   # same line as any upper plate
    if is_gable(fr):
        span = rafter_run(fr)
    elif len(plates) == 2:
        ys = [p["origin"][1] + p["size"][1] / 2.0 for p in plates.values()]   # plates lie flat, width along Y
        span = abs(ys[0] - ys[1])               # centre to centre of the bearing plates, horizontal
    else:
        span = spec["depth"] - 100.0
    b, d = vertical_dims(m)
    spacing = spacing_of(fr, "rafter", "rafter_spacing")
    s = spacing / 1000.0
    snow = spec["loads"]["snow_kn_m2"]
    dead = roof_dead_plan(f, lib, spec, cos_a, b, d)
    # the rafter's own weight is already in `dead` (per plan area), so do not add it again
    res = allowable_span(lib, b, d, (dead - own_weight_kn_m(lib, b, d) / s / cos_a) * s, snow * s, "snow",
                         repetitive=len(rafters) >= 4, cos_a=cos_a)
    allowed = res["span_mm"]
    level = level_for(span, allowed)
    name = section_name(lib, m["item"])
    verdict = {"ok": "That is comfortable.",
               "check": "That is close to the limit: use a deeper section or closer rafters if heavy snow is likely.",
               "fix": "That is too long: use a deeper section or closer rafters."}[level]
    where = ("from the eave wall's outer face to the ridge board; the overhang is ignored, which errs on the safe side"
             if is_gable(fr) else "between the centres of the front and back top plates; "
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
    rb, rd = vertical_dims(rafters[0]) if rafters else (38, 140)
    dead = roof_dead_plan(f, lib, spec, cos_a, rb, rd)
    rspan = spec["depth"] - 100.0
    for m in sorted(headers, key=lambda h: h["id"]):
        wall = m["group"].split("-")[-1]
        trib = (rspan / 2.0 + spec["overhang"]) if wall in ("front", "back") else spacing_of(fr, "rafter", "rafter_spacing") / 2.0
        t = trib / 1000.0
        b, d = vertical_dims(m)
        b *= plies[m["id"]]
        span = m["size"][0]
        res = allowable_span(lib, b, d, dead * t, snow * t, "snow", repetitive=False, cos_a=1.0)
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
        longest = max(rec["stock_lengths_mm"])
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
    for i, op in enumerate(spec.get("openings", []), 1):
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
        if plates:
            walls[wall] = _extent(plates, 1)
    for wall, (y0, y1) in walls.items():
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
    for wall in ("front", "back", "left", "right"):
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


DISCLAIMER = ("This is guidance from simple formulas, not structural engineering. Joists, rafters and headers were "
              "treated as beams under an even load; wind, uplift, shear, fixings, the ground and the loads on "
              "neighbouring walls were not checked, and local building rules may apply (permits, snow and wind zones, "
              "distance from boundaries). For anything that people will shelter in or that could hurt someone if it "
              "fails, have it checked by a qualified person.")


def run(frame):
    lib = tl.load(frame["region"])
    f = Findings(frame, lib)
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
