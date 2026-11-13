#!/usr/bin/env python3
"""Frame generator for a mono-pitch (pent) shed.

    tools/frame.py projects/<name>/structure.json --out projects/<name>/out/frame.json   (or examples/<name>/...)

Reads the input spec, fills every missing field from the region's library
defaults (tools/timberlib.py), checks that the shed can be built, and writes
the frame file: every member (box), every fastened joint, the bought
items and the assemblies (platform, walls, roof) that made them. The blocks
are in tools/timber/ (store, platform, wall, roof, recipes). The same spec
always gives the same bytes. The file format is the
contract in docs/research/timber-structures.md ("The frame file").

Conventions (millimetres, Z up, origin at the front-left outer corner of the
floor frame, X = width, Y = depth, front = Y 0, left = X 0):
- `size` is [length, width, thickness]; the box is
  origin + a*x + b*y + c*(x cross y), for a, b, c within the size.
  `length` is the longest edge of the piece (the stock you cut it from).
- A wall's depth is the frame section's wide side; its studs are on edge.
- Heights are measured from the underside of the floor frame to the top of
  the wall's top plate. Opening `x` is measured along the footprint from the
  front-left corner (X for front and back walls, Y for left and right).
  Opening `sill` and `height` are measured from the top of the floor deck.
"""
import argparse, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timberlib as tl
import framing as fr  # noqa: E402
import frame_edits as fe  # noqa: E402

from timber.store import (EPS, KINDS, layout, MIN_CRIPPLE, MIN_INFILL, MIN_SHEET, SCHEMA, WALLS,  # noqa: E402,F401
                          SpecError)
from timber import recipes  # noqa: E402
from timber import planning as pl  # noqa: E402
from timber import fields as fld  # noqa: E402
from timber import spans as spn  # noqa: E402


# ------------------------------------------------------------------ spec

REQUIRED = ("type", "width", "depth")
# the fields each recipe accepts come from the tables in timber/fields.py (also `--fields`)
KNOWN = tuple(dict.fromkeys(fld.names("pent-shed") + fld.names("gable-shed")))
TERRACE_KNOWN = fld.names("terrace")
PERGOLA_KNOWN = fld.names("pergola")
KITCHEN_KNOWN = fld.names("summer-kitchen")
KITCHEN_WALLS = ("back", "left", "right")
TYPES = ("pent-shed", "gable-shed", "terrace", "pergola", "summer-kitchen")
GABLE_ONLY = ("height_eaves", "pitch_deg", "height_ridge", "ridge_item", "tie_item")
PENT_ONLY = ("height_front", "height_back")
MAX_PITCH_DEG = 60.0
MIN_RIDGE_THICKNESS = 25.0      # mm; IRC R802.3 asks for 1 in. nominal, which is 19 mm: 25 mm is used
DEFAULT_HEIGHT_EAVES = 2000.0   # a gable shed's eaves: the gable end is taller by the roof's rise
CORNERS = ("three-stud", "california", "two-stud")
TOP_PLATES = ("double", "single")
LENGTHS = ("width", "depth", "height_front", "height_back", "stud_spacing", "joist_spacing",
           "rafter_spacing", "overhang", "overhang_side")
DEFAULT_HEIGHT_FRONT = 2300.0   # used when the spec has none: a walk-in shed
DEFAULT_HEIGHT_DROP = 300.0     # back wall is this much lower than the front by default


def _length(spec, key, where=None):
    v = spec[key]
    name = where or key
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise SpecError(f"{name}: must be a length in mm (or text like \"2.4 m\" or \"8'\")")
    try:
        mm = tl.parse_length(v) if isinstance(v, str) else float(v)
    except ValueError as e:
        raise SpecError(f"{name}: {e}")
    if not math.isfinite(mm):
        raise SpecError(f"{name}: must be a finite length")
    return mm


def resolve_spec(raw):
    """The spec with every missing field filled from the library, lengths in mm.
    Returns (spec, library). Raises SpecError naming the field."""
    if not isinstance(raw, dict):
        raise SpecError("spec: must be a JSON object")
    for k in REQUIRED:
        if k not in raw:
            raise SpecError(f"{k}: required")
    if raw["type"] == "terrace":
        return _terrace_spec(raw)
    if raw["type"] == "pergola":
        return _pergola_spec(raw)
    if raw["type"] == "summer-kitchen":
        return _kitchen_spec(raw)
    for k in raw:
        if k not in KNOWN:
            raise SpecError(f"{k}: unknown field (known: {', '.join(KNOWN)})")
    if raw["type"] not in TYPES:
        raise SpecError(f"type: {raw['type']!r} is not supported; use one of {', '.join(TYPES)}")
    gable = raw["type"] == "gable-shed"
    for k in (PENT_ONLY if gable else GABLE_ONLY):
        if k in raw:
            hint = " (a gable shed has height_eaves: both eave walls are the same height)" if gable and k.startswith("height") else ""
            raise SpecError(f"{k}: only for a {'pent-shed' if gable else 'gable-shed'}{hint}")
    region = raw.get("region", "eu")
    try:
        lib = tl.load(region)
    except ValueError as e:
        raise SpecError(f"region: {e}")
    d = lib["defaults"]
    s = pl.Spec({"type": raw["type"], "region": region,
                 "units": raw.get("units", lib.get("units", "metric"))})
    if s["units"] not in ("metric", "imperial"):
        raise SpecError(f"units: must be 'metric' or 'imperial', not {s['units']!r}")
    if "name" in raw:
        if not isinstance(raw["name"], str) or not raw["name"].strip():
            raise SpecError("name: must be text")
    s["name"] = raw.get("name", "garden-shed").strip()

    for k in ("width", "depth"):
        s[k] = _length(raw, k)
    for k in LENGTHS[2:] + ("height_eaves", "height_ridge"):
        if k in raw:
            s[k] = _length(raw, k)
    for k, dk in (("stud_spacing", "stud_spacing_mm"), ("joist_spacing", "joist_spacing_mm"),
                  ("rafter_spacing", "rafter_spacing_mm"), ("overhang", "overhang_mm"),
                  ("overhang_side", "overhang_side_mm")):
        s.setdefault(k, float(d.get(dk, d["overhang_mm"])))
    # the heights not given are worked out below (_plan_shed), once the items and openings are known
    checked = ("width", "depth", "height_eaves", "stud_spacing", "joist_spacing", "rafter_spacing",
               "overhang", "overhang_side") if gable else LENGTHS
    for k in checked:
        if k in s and not s[k] > 0 and not (k in ("overhang", "overhang_side") and s[k] == 0):
            raise SpecError(f"{k}: must be greater than 0")

    items = d["items"]
    roles = (("frame_item", "frame"), ("floor_item", "floor"), ("rafter_item", "rafter"),
             ("sheathing", "sheathing"), ("floor_deck", "floor_deck"),
             ("roof_deck", "roof_deck"), ("cladding", "cladding"))
    cats = {"frame_item": "sections", "floor_item": "sections", "rafter_item": "sections",
            "sheathing": "sheets", "floor_deck": "sheets", "roof_deck": "sheets",
            "cladding": "cladding"}
    for field, role in roles:
        key = raw.get(field, items[role])
        if not isinstance(key, str):
            raise SpecError(f"{field}: must be an item key such as {items[role]!r}")
        try:
            it = tl.item(lib, key)
        except KeyError:
            have = ", ".join(sorted(lib[cats[field]]))
            raise SpecError(f"{field}: {key!r} is not in the {region} library (have: {have})")
        if it["category"] != cats[field]:
            raise SpecError(f"{field}: {key!r} is a {it['category']} item, need one of {cats[field]}")
        s[field] = key
    tf = raw.get("treated_floor", d["treated_floor"])
    if not isinstance(tf, bool):
        raise SpecError("treated_floor: must be true or false")
    s["treated_floor"] = tf

    loads = dict(d["loads"])
    if "loads" in raw:
        if not isinstance(raw["loads"], dict):
            raise SpecError("loads: must be an object")
        for k, v in raw["loads"].items():
            if k not in loads:
                raise SpecError(f"loads.{k}: unknown load (known: {', '.join(loads)})")
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise SpecError(f"loads.{k}: must be a number of kN/m2, 0 or more")
            loads[k] = float(v)
    s["loads"] = loads
    roofing = raw.get("roofing", "roofing-felt")
    try:
        r = tl.item(lib, roofing)
    except KeyError:
        r = None
    if not (r and r["category"] == "bought" and r["unit"] == "m2"):
        raise SpecError(f"roofing: {roofing!r} is not a roofing item sold by area in the {region} library")
    s["roofing"] = roofing

    s["openings"] = _openings(raw.get("openings", []))

    # framing details: how corners, plates and headers are made (see framing.py)
    det = d.get("details", {})
    for field, allowed in (("corner", CORNERS), ("top_plate", TOP_PLATES)):
        v = raw.get(field, det.get(field, allowed[0]))
        if v not in allowed:
            raise SpecError(f"{field}: must be one of {', '.join(allowed)}, not {v!r}")
        s[field] = v
    hk = raw.get("header_item", s["frame_item"])
    try:
        hit = tl.item(lib, hk) if isinstance(hk, str) else None
    except KeyError:
        hit = None
    if not hit or hit["category"] != "sections":
        raise SpecError(f"header_item: {hk!r} is not a timber section in the {region} library")
    s["header_item"] = hk
    _plan_shed(raw, s, lib, d, gable)
    fk = raw.get("fascia_item", det.get("fascia_item", s["rafter_item"]))
    try:
        fit = tl.item(lib, fk) if isinstance(fk, str) else None
    except KeyError:
        fit = None
    if not fit or fit["category"] != "sections":
        raise SpecError(f"fascia_item: {fk!r} is not a timber section in the {region} library")
    s["fascia_item"] = fk
    def item_ok(key):
        try:
            return tl.item(lib, key)["category"] in ("sections", "sheets", "cladding")
        except KeyError:
            return False
    try:
        s["edits"] = fe.validate(raw.get("edits", []), item_ok)
    except fe.EditError as e:
        raise SpecError(str(e))
    if gable:
        _gable_roof(raw, s, lib, d)
    _shed_foundation(raw, s, lib)
    tr = tl.item(lib, s["rafter_item"])["thickness_mm"]
    os_ = s["overhang_side"]
    if os_ and not (tr + fr.MIN_OUTRIGGER - EPS <= os_ <= fr.OVERHANG_SIDE_MAX + EPS):
        raise SpecError(f"overhang_side: {os_:g} mm does not work; use 0 (no side overhang) or "
                        f"{tr + fr.MIN_OUTRIGGER:g} to {fr.OVERHANG_SIDE_MAX:g} mm (a flying rafter on "
                        f"outriggers; more needs lookouts back to the second rafter, not built yet)")
    return s, lib


# ------------------------------------------------------------------ planning (what the description leaves open)

def _min_pitch(lib, s):
    return lib["defaults"].get("min_roof_pitch_deg", {}).get(s["roofing"])


def _opening_tops(lib, s):
    """For each wall with openings: the height of the top plate's top that its tallest opening needs
    (floor top + sill + opening + header + the plates)."""
    zd = tl.item(lib, s["floor_item"])["width_mm"] + tl.item(lib, s["floor_deck"])["thickness_mm"]
    t = tl.item(lib, s["frame_item"])["thickness_mm"]
    courses = 2 if s["top_plate"] == "double" else 1
    hh = tl.item(lib, s["header_item"])["width_mm"]
    out = {}
    for o in s["openings"]:
        need = zd + o["sill"] + o["height"] + hh + courses * t
        if need > out.get(o["wall"], (0.0,))[0]:
            out[o["wall"]] = (need, o)
    return out


def _plan_heights(raw, s, lib, gable):
    """Fill the wall heights the description leaves out. The plain defaults are a 2000 mm eave (gable) or a
    2300 mm front and a back 300 mm lower (pent); they are raised only as far as needed so that the roof
    drains (a pent roof must slope at least the roofing's minimum, plus 2 degrees) and the doors and windows
    asked for fit under their headers. Returns the decision (what, chose, why) or None."""
    u, tops = s["units"], _opening_tops(lib, s)
    why = []
    if gable:
        if "height_eaves" in raw:
            return None
        need = max((v[0] for v in tops.values()), default=0.0)
        h = max(DEFAULT_HEIGHT_EAVES, pl.ceil_step(need))
        s["height_eaves"] = float(h)
        if h > DEFAULT_HEIGHT_EAVES:
            o = max(tops.values(), key=lambda v: v[0])[1]
            return ("Eaves height", pl.length_text(h, u) + " to the top of the eave walls",
                    f"the {o['kind']} on the {o['wall']} wall is {pl.length_text(o['height'], u)} tall and needs "
                    f"{pl.length_text(max(v[0] for v in tops.values()), u)} (floor, opening, header and wall plates); "
                    f"the usual height is {pl.length_text(DEFAULT_HEIGHT_EAVES, u)}")
        return None
    run = s["depth"] - tl.item(lib, s["frame_item"])["width_mm"]
    lim = _min_pitch(lib, s)
    deg = lambda drop: math.degrees(math.atan(drop / run))
    drop = DEFAULT_HEIGHT_DROP
    if lim is not None and deg(drop) < lim - 0.05:
        drop = max(drop, pl.ceil_step(math.tan(math.radians(lim + 2.0)) * run))
        why.append(f"a {pl.length_text(DEFAULT_HEIGHT_DROP, u)} fall would slope the roof {deg(DEFAULT_HEIGHT_DROP):.1f} degrees "
                   f"and {s['roofing']} needs at least {lim:g}; a {pl.length_text(drop, u)} fall slopes it {deg(drop):.1f}")
    back_need = max((v[0] for w, v in tops.items() if w != "front"), default=0.0)
    front_need = tops["front"][0] if "front" in tops else 0.0
    given_f, given_b = "height_front" in raw, "height_back" in raw
    if given_f and given_b:
        return None
    if given_f:
        hf = s["height_front"]
        hb = max(hf - drop, pl.ceil_step(back_need))
    elif given_b:
        hb = s["height_back"]
        hf = DEFAULT_HEIGHT_FRONT
        if lim is not None and deg(hf - hb) < lim - 0.05:
            hf = hb + max(0.0, pl.ceil_step(math.tan(math.radians(lim + 2.0)) * run))
        hf = max(hf, pl.ceil_step(front_need))
    else:
        hb = max(DEFAULT_HEIGHT_FRONT - DEFAULT_HEIGHT_DROP, pl.ceil_step(back_need))
        hf = max(hb + drop, pl.ceil_step(front_need))
        zd = tl.item(lib, s["floor_item"])["width_mm"] + tl.item(lib, s["floor_deck"])["thickness_mm"]
        cap = pl.floor_step(zd + max(tl.item(lib, s["sheathing"])["size_mm"]))      # the wall sheathing is one sheet high
        if hf > cap and front_need <= cap:
            hf = cap
            hb = max(hf - drop, pl.ceil_step(back_need))                        # a deep shed gets its fall from a lower back
    plain_f = s["height_front"] if given_f else DEFAULT_HEIGHT_FRONT
    plain_b = s["height_back"] if given_b else plain_f - DEFAULT_HEIGHT_DROP
    s["height_front"], s["height_back"] = float(hf), float(hb)
    if abs(hf - plain_f) < 0.5 and abs(hb - plain_b) < 0.5:
        return None
    for w, (need, o) in sorted(tops.items()):
        h = hf if w == "front" else hb
        if need > (plain_f if w == "front" else plain_b) + 0.5:
            why.append(f"the {o['kind']} on the {w} wall is {pl.length_text(o['height'], u)} tall and needs "
                       f"{pl.length_text(need, u)} up to the top plate (floor, opening, header and plates)")
    return ("Wall heights", f"front {pl.length_text(hf, u)}, back {pl.length_text(hb, u)} to the top plates",
            "; ".join(why) or "the heights follow from the ones you gave")


def _rafter_trial(raw, s, lib, d, key):
    """A gable roof's slope, ridge and rafter run for a rafter section: (cos of the pitch, run in mm), or None."""
    s2 = dict(s)
    s2["rafter_item"] = key
    try:
        _gable_roof(raw, s2, lib, d)
    except SpecError:
        return None
    tg = tl.item(lib, s2["ridge_item"])["thickness_mm"]
    return math.cos(math.radians(s2["pitch_deg"])), s["depth"] / 2.0 - tg / 2.0


def _plan_shed(raw, s, lib, d, gable):
    """The sections and spacings a shed's description leaves open: floor joists, rafters and headers that
    fit their spans (timber/planning.py), and the wall heights (_plan_heights). Every change from the
    library's plain defaults is recorded as a decision."""
    u, W, D = s["units"], s["width"], s["depth"]
    out = []
    # floor joists: centre to centre of the two rim joists
    def ev_j(key, spacing):
        tj = lib["sections"][key]["thickness_mm"]
        res = spn.floor_joist_allowed(lib, s, key, spacing, repetitive=len(layout(W, tj, spacing)) >= 4)
        return D - tj, res["span_mm"]
    j = pl.size_member(lib, s["floor_item"], s["joist_spacing"], ("joist",), ev_j, item_named=raw.get("floor_item"),
                       spacing_named="joist_spacing" in raw)
    if j.changed:
        out.append(("Floor joists",) + pl.explain(lib, "joists", j, s["floor_item"], s["joist_spacing"], u))
        s["floor_item"], s["joist_spacing"] = j.key, float(j.spacing)
    # wall heights, rafters and headers, which depend on each other a little
    cos_a = 1.0
    hh0 = None
    base_r, base_h = (s["rafter_item"], s["rafter_spacing"]), s["header_item"]     # the plain defaults, whatever an earlier round chose
    for _ in range(3):
        hd = _plan_heights(raw, s, lib, gable)
        if gable:
            _gable_roof(raw, dict(s), lib, d)                  # the description's own roof must work: its errors are the person's to read
            def ev_r(key, spacing):
                tr_ = _rafter_trial(raw, s, lib, d, key)
                if tr_ is None:
                    return 1e9, 1.0
                c, run = tr_
                n = len(layout(W, lib["sections"][key]["thickness_mm"], spacing))
                return run, spn.shed_rafter_allowed(lib, s, key, spacing, c, repetitive=n >= 4)["span_mm"]
        else:
            run = D - tl.item(lib, s["frame_item"])["width_mm"]
            c = 1.0 / math.sqrt(1.0 + ((s["height_front"] - s["height_back"]) / run) ** 2)
            def ev_r(key, spacing, c=c, run=run):
                n = len(layout(W, lib["sections"][key]["thickness_mm"], spacing))
                return run, spn.shed_rafter_allowed(lib, s, key, spacing, c, repetitive=n >= 4)["span_mm"]
        r = pl.size_member(lib, base_r[0], base_r[1], ("rafter",), ev_r, item_named=raw.get("rafter_item"),
                           spacing_named="rafter_spacing" in raw)
        rd = ("Rafters",) + pl.explain(lib, "rafters", r, base_r[0], base_r[1], u) if r.changed else None
        s["rafter_item"], s["rafter_spacing"] = r.key, float(r.spacing)
        cos_a = _shed_cos(raw, s, lib, d, gable)
        # headers: all at once, the deepest need decides
        hdd = None
        if s["openings"]:
            tf = tl.item(lib, s["frame_item"])["thickness_mm"]
            wf_ = tl.item(lib, s["frame_item"])["width_mm"]

            def ev_h(key, _sp):
                th = lib["sections"][key]["thickness_mm"]
                plies = 2 if 2 * th <= wf_ + EPS else 1
                worst = None
                for o in s["openings"]:
                    span = o["width"] + 2 * tf
                    al = spn.header_allowed(lib, s, key, plies, o["wall"], cos_a, s["rafter_item"], s["rafter_spacing"])["span_mm"]
                    if worst is None or span / al > worst[0] / worst[1]:
                        worst = (span, al)
                return worst
            h = pl.size_member(lib, base_h, 0.0, ("header", "joist", "rafter"), ev_h,
                               item_named=raw.get("header_item"), spacing_named=True)
            if h.changed:
                nm = lambda k: pl.section_name(lib, k)
                hdd = ("Headers over the openings", f"{nm(h.key)}, two together" if 2 * lib["sections"][h.key]["thickness_mm"] <= wf_ + EPS
                       else nm(h.key),
                       f"{nm(base_h)} is good for {pl.length_text(h.base[1], u)} and the widest opening needs "
                       f"{pl.length_text(h.base[0], u)}")
                s["header_item"] = h.key
        hh = tl.item(lib, s["header_item"])["width_mm"]
        out_h = [x for x in (hd, rd, hdd) if x]
        if hh == hh0:
            break
        hh0 = hh
    out.extend(out_h)
    for what, chose, why in out:
        pl.decide(s, what, chose, why)


def _shed_cos(raw, s, lib, d, gable):
    """The cosine of the roof's slope as the checks will see it."""
    if gable:
        tr_ = _rafter_trial(raw, s, lib, d, s["rafter_item"])
        return tr_[0] if tr_ else 1.0
    run = s["depth"] - tl.item(lib, s["frame_item"])["width_mm"]
    return 1.0 / math.sqrt(1.0 + ((s["height_front"] - s["height_back"]) / run) ** 2)



def _shed_foundation(raw, s, lib):
    """Optional footings under a shed's floor frame (see timber/foundations.py)."""
    fnd = raw.get("foundation", "none")
    if fnd == "none":
        for k in ("footing_item", "footing_spacing"):
            if k in raw:
                raise SpecError(f"{k}: only with a foundation (ground_screw, pier_block or concrete_footing)")
        return
    from timber.foundations import footing_item
    it = footing_item(lib, fnd, raw.get("footing_item"))
    s["foundation"], s["footing_item"] = fnd, it["key"]
    if "footing_spacing" in raw:
        s["footing_spacing"] = _length(raw, "footing_spacing")
        if s["footing_spacing"] < 300:
            raise SpecError("footing_spacing: must be at least 300 mm")
    else:
        s["footing_spacing"] = float(lib["defaults"]["terrace"]["footing_spacing_shed_mm"])


def _pick_item(raw, lib, field, default, cats=("sections",), what="a timber section"):
    """The library key for a field: the description's, else the default; it must be in `cats`."""
    key = raw.get(field, default)
    try:
        it = tl.item(lib, key) if isinstance(key, str) else None
    except KeyError:
        it = None
    if not it or it["category"] not in cats:
        raise SpecError(f"{field}: {key!r} is not {what} in the {lib['region']} library")
    return key


def _kitchen_spec(raw):
    """A summer kitchen description with every missing field filled from the library (the
    pergola, terrace and shed defaults and defaults.summer_kitchen), lengths in mm, the post
    spacing worked out from the beam span formula, the roof's slope worked out. Returns (spec, library)."""
    import framecheck as fc
    from timber.foundations import footing_item
    for k in ("width", "depth"):
        if k not in raw:
            raise SpecError(f"{k}: required")
    for k in raw:
        if k not in KITCHEN_KNOWN:
            raise SpecError(f"{k}: unknown field for a summer kitchen (known: {', '.join(KITCHEN_KNOWN)})")
    region = raw.get("region", "eu")
    try:
        lib = tl.load(region)
    except ValueError as e:
        raise SpecError(f"region: {e}")
    d = lib["defaults"]
    kd, pg, tt = d["summer_kitchen"], d["pergola"], d["terrace"]
    s = pl.Spec({"type": "summer-kitchen", "region": region, "units": raw.get("units", lib.get("units", "metric"))})
    if s["units"] not in ("metric", "imperial"):
        raise SpecError(f"units: must be 'metric' or 'imperial', not {s['units']!r}")
    if "name" in raw and (not isinstance(raw["name"], str) or not raw["name"].strip()):
        raise SpecError("name: must be text")
    s["name"] = raw.get("name", "summer-kitchen").strip()
    for k in ("width", "depth"):
        s[k] = _length(raw, k)
        if not s[k] > 0:
            raise SpecError(f"{k}: must be greater than 0")
    s["roof"] = raw.get("roof", "gable")
    if s["roof"] not in ("mono", "gable"):
        raise SpecError("roof: use mono (the front higher, like the pent shed) or gable (a ridge along the width)")
    s["floor"] = raw.get("floor", "none")
    if s["floor"] not in ("none", "terrace"):
        raise SpecError("floor: use none or terrace (a board deck on its own beams and footings)")
    gable = s["roof"] == "gable"
    for k in (("height_front", "height_back") if gable else ("height_ridge",)):
        if k in raw:
            raise SpecError(f"{k}: only for a {'mono' if gable else 'gable'} roof"
                            + (" (a gable roof has height_eaves: both eave beams are the same height)" if gable else ""))
    # items
    items = d["items"]
    s["frame_item"] = _pick_item(raw, lib, "frame_item", items["frame"])
    s["rafter_item"] = _pick_item(raw, lib, "rafter_item", items["rafter"])
    s["header_item"] = _pick_item(raw, lib, "header_item", s["frame_item"])
    s["fascia_item"] = _pick_item(raw, lib, "fascia_item", d.get("details", {}).get("fascia_item", s["rafter_item"]))
    s["sheathing"] = _pick_item(raw, lib, "sheathing", items["sheathing"], ("sheets",), "a sheet")
    s["roof_deck"] = _pick_item(raw, lib, "roof_deck", items["roof_deck"], ("sheets",), "a sheet")
    s["cladding"] = _pick_item(raw, lib, "cladding", items["cladding"], ("cladding",), "cladding")
    s["post_item"] = _pick_item(raw, lib, "post_item", pg["post_item"])
    s["beam_item"] = _pick_item(raw, lib, "beam_item", pg["beam_item"])
    s["brace_item"] = _pick_item(raw, lib, "brace_item", pg["brace_item"])
    roofing = raw.get("roofing", "roofing-felt")
    try:
        r = tl.item(lib, roofing)
    except KeyError:
        r = None
    if not (r and r["category"] == "bought" and r["unit"] == "m2"):
        raise SpecError(f"roofing: {roofing!r} is not a roofing item sold by area in the {region} library")
    s["roofing"] = roofing
    s["foundation"] = raw.get("foundation", pg["foundation"])
    s["footing_item"] = footing_item(lib, s["foundation"], raw.get("footing_item"))["key"]
    plies = raw.get("beam_plies", pg["beam_plies"])
    if plies not in (1, 2) or isinstance(plies, bool):
        raise SpecError("beam_plies: use 1 or 2")
    s["beam_plies"] = plies
    for k, dk in (("stud_spacing", "stud_spacing_mm"), ("rafter_spacing", "rafter_spacing_mm"),
                  ("overhang", "overhang_mm"), ("overhang_side", "overhang_side_mm")):
        s[k] = _length(raw, k) if k in raw else float(d.get(dk, d["overhang_mm"]))
    for k in ("stud_spacing", "rafter_spacing"):
        sec = tl.item(lib, s["frame_item"] if k == "stud_spacing" else s["rafter_item"])
        if s[k] < 2 * sec["thickness_mm"]:
            raise SpecError(f"{k}: {s[k]:g} mm is closer than two {sec['name']} members")
    if not 0 <= s["overhang"] <= 1200:
        raise SpecError("overhang: use 0 to 1200 mm")
    tr = tl.item(lib, s["rafter_item"])["thickness_mm"]
    os_ = s["overhang_side"]
    if os_ and not (tr + fr.MIN_OUTRIGGER - EPS <= os_ <= fr.OVERHANG_SIDE_MAX + EPS):
        raise SpecError(f"overhang_side: {os_:g} mm does not work; use 0 (no side overhang) or "
                        f"{tr + fr.MIN_OUTRIGGER:g} to {fr.OVERHANG_SIDE_MAX:g} mm (a flying rafter on outriggers)")
    det = d.get("details", {})
    tp = raw.get("top_plate", det.get("top_plate", TOP_PLATES[0]))
    if tp not in TOP_PLATES:
        raise SpecError(f"top_plate: must be one of {', '.join(TOP_PLATES)}, not {tp!r}")
    s["top_plate"] = tp
    br = raw.get("braces", True)
    if not isinstance(br, bool):
        raise SpecError("braces: use true or false")
    s["braces"] = br
    v = _length(raw, "brace_leg") if "brace_leg" in raw else float(pg["brace_leg_mm"])
    if not 250 <= v <= 1500:
        raise SpecError("brace_leg: use 250 to 1500 mm")
    s["brace_leg"] = v
    # the posts and beams fix the roof's geometry
    post, beam_it = tl.item(lib, s["post_item"]), tl.item(lib, s["beam_item"])
    pty = post["width_mm"]
    bw, hbeam = plies * beam_it["thickness_mm"], beam_it["width_mm"]
    if bw > pty + EPS:
        raise SpecError(f"beam_item: {plies} x {beam_it['name']} is {bw:g} mm wide, wider than the {post['name']} posts "
                        f"({pty:g} mm); use one ply, a thinner beam or a bigger post_item")
    e = (pty - bw) / 2.0
    if s["width"] < 2 * post["thickness_mm"] + 600:
        raise SpecError(f"width: {s['width']:g} mm is too small; it needs two posts and at least 600 mm between them")
    if s["depth"] < 2 * pty + 1200:
        raise SpecError(f"depth: {s['depth']:g} mm is too small; it needs two rows of posts and at least 1200 mm between them")
    for k in ("height_eaves", "height_front", "height_back", "height_ridge"):
        if k in raw:
            s[k] = _length(raw, k)
            if not s[k] > 0:
                raise SpecError(f"{k}: must be greater than 0")
    low = s.pop("height_eaves", float(kd["height_eaves_mm"]))
    if gable:
        s["height_eaves"] = low
        top = low + hbeam                                      # the beams' top: where the rafters bear

        def gable_geometry(tgt):
            save = {k: tgt.get(k) for k in ("height_eaves", "depth")}
            tgt["height_eaves"], tgt["depth"] = top, tgt["depth"] - 2 * e   # the formulas see the eave line as the top of the beam
            try:
                _gable_roof(raw, tgt, lib, d)
            finally:
                tgt["height_eaves"], tgt["depth"] = save["height_eaves"], save["depth"]
        s_pre = dict(s)                                        # before the roof's slope is worked out (the planner tries other rafters)
        gable_geometry(s)
    else:
        if "height_back" in raw and "height_eaves" in raw and abs(s["height_back"] - low) > EPS:
            raise SpecError("height_back: for a mono roof this is the same as height_eaves (the lower beam); give one")
        hb_ = s["height_back"] if "height_back" in raw else low
        run = s["depth"] - pty                                 # between the beams' centre lines
        if "height_front" in raw:
            if "pitch_deg" in raw:
                raise SpecError("pitch_deg: give the pitch or height_front, not both")
            hf_ = s["height_front"]
            if hf_ < hb_ - EPS:
                raise SpecError(f"height_front: {hf_:g} mm is lower than the back beam ({hb_:g} mm); a mono roof falls to the back")
        else:
            pitch = raw.get("pitch_deg", kd["pitch_deg_mono"])
            if isinstance(pitch, bool) or not isinstance(pitch, (int, float)) or not 0 < pitch <= MAX_PITCH_DEG:
                raise SpecError(f"pitch_deg: use more than 0 and up to {MAX_PITCH_DEG:g} degrees")
            hf_ = round(hb_ + run * math.tan(math.radians(pitch)), 1)
        s["height_front"], s["height_back"] = hf_, hb_
        s["pitch_deg"] = round(math.degrees(math.atan((hf_ - hb_) / run)), 4)
    # loads
    loads = {"snow_kn_m2": float(d["loads"]["snow_kn_m2"]), "floor_kn_m2": float(tt["floor_kn_m2"])}
    if "loads" in raw:
        if not isinstance(raw["loads"], dict):
            raise SpecError("loads: must be an object")
        for k, v in raw["loads"].items():
            if k not in loads:
                raise SpecError(f"loads.{k}: unknown load (known: {', '.join(loads)})")
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
                raise SpecError(f"loads.{k}: must be a number of kN/m2, more than 0")
            loads[k] = float(v)
    s["loads"] = loads
    # the rafters: a section and spacing that carry the roof's span comfortably
    if gable:
        def ev(key, spacing):
            t2 = dict(s_pre, rafter_item=key)
            try:
                gable_geometry(t2)
            except SpecError:
                return 1e9, 1.0
            run = s["depth"] / 2.0 - tl.item(lib, t2["ridge_item"])["thickness_mm"] / 2.0
            c = math.cos(math.radians(t2["pitch_deg"]))
            n = len(layout(s["width"], lib["sections"][key]["thickness_mm"], spacing))
            return run, spn.shed_rafter_allowed(lib, s, key, spacing, c, repetitive=n >= 4)["span_mm"]
    else:
        run_ = s["depth"] - pty
        c_ = math.cos(math.radians(s["pitch_deg"]))

        def ev(key, spacing):
            n = len(layout(s["width"], lib["sections"][key]["thickness_mm"], spacing))
            return run_, spn.shed_rafter_allowed(lib, s, key, spacing, c_, repetitive=n >= 4)["span_mm"]
    r = pl.size_member(lib, s["rafter_item"], s["rafter_spacing"], ("rafter",), ev, item_named=raw.get("rafter_item"),
                       spacing_named="rafter_spacing" in raw)
    if r.changed:
        pl.decide(s, "Rafters", *pl.explain(lib, "rafters", r, s["rafter_item"], s["rafter_spacing"], s["units"]))
        s["rafter_item"], s["rafter_spacing"] = r.key, float(r.spacing)
        if gable:
            t3 = dict(s_pre, rafter_item=r.key)
            gable_geometry(t3)
            for k in ("pitch_deg", "ridge_item", "tie_item"):
                s[k] = t3[k]
        if "fascia_item" not in raw:
            s["fascia_item"] = _pick_item(raw, lib, "fascia_item", d.get("details", {}).get("fascia_item", s["rafter_item"]))
    # the floor
    if s["floor"] == "terrace":
        s["floor_height"] = _length(raw, "floor_height") if "floor_height" in raw else float(kd["floor_height_mm"])
        if not s["floor_height"] > 0:
            raise SpecError("floor_height: must be greater than 0")
        s["joist_item"] = _pick_item(raw, lib, "joist_item", tt["joist_item"])
        s["deck_board"] = _pick_item(raw, lib, "deck_board", tt["deck_board"])
        if "deck" not in tl.item(lib, s["deck_board"]):
            raise SpecError(f"deck_board: {s['deck_board']!r} is not a deck board in the {region} library")
        s["floor_beam_item"] = _pick_item(raw, lib, "floor_beam_item", tt["beam_item"])
        s["floor_post_item"] = _pick_item(raw, lib, "floor_post_item", tt["post_item"])
        fp = raw.get("floor_beam_plies", tt["beam_plies"])
        if fp not in (1, 2) or isinstance(fp, bool):
            raise SpecError("floor_beam_plies: use 1 or 2")
        s["floor_beam_plies"] = fp
        board = tl.item(lib, s["deck_board"])
        s["joist_spacing"] = _length(raw, "joist_spacing") if "joist_spacing" in raw else float(board["deck"]["max_joist_spacing_mm"])
        s["board_gap"] = _length(raw, "board_gap") if "board_gap" in raw else float(board["deck"]["gap_mm"])
        if s["joist_spacing"] < 2 * tl.item(lib, s["joist_item"])["thickness_mm"]:
            raise SpecError(f"joist_spacing: {s['joist_spacing']:g} mm is closer than two joists")
        if not 0 <= s["board_gap"] <= 20:
            raise SpecError("board_gap: use 0 to 20 mm")
        tspec = {"deck_board": s["deck_board"], "joist_item": s["joist_item"], "joist_spacing": s["joist_spacing"],
                 "beam_item": s["floor_beam_item"], "beam_plies": s["floor_beam_plies"], "loads": s["loads"]}
        ld = fc.terrace_loads(lib, tspec)
        allowed = fc.joist_allowed(lib, tspec, ld)
        row, why, lim = pl.spacing_under(allowed, tt["max_row_spacing_mm"])
        if row is None:
            raise SpecError(f"joist_item: {s['joist_item']!r} at {s['joist_spacing']:g} mm carries only about "
                            f"{lim / 1000:.2f} m between beams; use a deeper joist or closer spacing")
        s["floor_row_spacing"] = row
        pl.decide(s, "Floor beam rows", f"no further apart than {pl.length_text(row, s['units'])}",
                  pl.spacing_why(pl.spacing_note(allowed, tt["max_row_spacing_mm"], why,
                                                 f"{pl.section_name(lib, s['joist_item'])} deck joists at {pl.length_text(s['joist_spacing'], s['units'])}"),
                                 s["units"]))
        allowed = fc.beam_allowed(lib, tspec, ld, s["floor_row_spacing"])
        fpost, why, lim = pl.spacing_under(allowed, tt["max_post_spacing_mm"])
        if fpost is None:
            raise SpecError(f"floor_beam_item: {s['floor_beam_item']!r} carries only about {lim / 1000:.2f} m between posts; "
                            "use a deeper beam or more plies")
        s["floor_post_spacing"] = fpost
        pl.decide(s, "Floor posts", f"no further apart than {pl.length_text(fpost, s['units'])}",
                  pl.spacing_why(pl.spacing_note(allowed, tt["max_post_spacing_mm"], why,
                                                 f"A floor beam of {s['floor_beam_plies']} x {pl.section_name(lib, s['floor_beam_item'])}"),
                                 s["units"]))
    else:
        for k in ("floor_height", "joist_item", "joist_spacing", "deck_board", "board_gap", "floor_beam_item",
                  "floor_beam_plies", "floor_post_item"):
            if k in raw:
                raise SpecError(f"{k}: only with floor: terrace")
    # the walls
    s["walls"] = _kitchen_walls(raw.get("walls", []))
    if s["walls"] and tl.item(lib, s["frame_item"])["width_mm"] > min(pty, post["thickness_mm"]) + EPS:
        raise SpecError(f"frame_item: {s['frame_item']!r} is wider than the posts ({min(pty, post['thickness_mm']):g} mm); "
                        "a wall's inner face lies flush with the posts' inner faces, so it must be no wider than they are")
    # post spacing: under the beam span formula
    if "post_spacing" in raw:
        s["post_spacing"] = _length(raw, "post_spacing")
        if s["post_spacing"] < 600:
            raise SpecError("post_spacing: must be at least 600 mm")
    else:
        allowed = fc.kitchen_beam_allowed(lib, s)
        post_sp, why, lim = pl.spacing_under(allowed, pg["max_post_spacing_mm"])
        if post_sp is None:
            raise SpecError(f"beam_item: {s['beam_item']!r} carries only about {lim / 1000:.2f} m between posts "
                            "under this roof; use a deeper beam or shorter rafters")
        s["post_spacing"] = post_sp
        s.notes["post_spacing"] = pl.spacing_note(allowed, pg["max_post_spacing_mm"], why,
                                                  f"A roof beam of {s['beam_plies']} x {pl.section_name(lib, s['beam_item'])}")
    def item_ok(key):
        try:
            return tl.item(lib, key)["category"] in ("sections", "sheets", "cladding")
        except KeyError:
            return False
    try:
        s["edits"] = fe.validate(raw.get("edits", []), item_ok)
    except fe.EditError as e_:
        raise SpecError(str(e_))
    return s, lib


def _kitchen_walls(raw):
    """The walls list as stored: [{"side": ..., "openings": [...]}], each side at most once."""
    if not isinstance(raw, list):
        raise SpecError("walls: must be a list of sides (back, left, right), each a name or {\"side\": ..., \"openings\": [...]}")
    out, seen = [], set()
    for k, w in enumerate(raw):
        if isinstance(w, str):
            w = {"side": w}
        if not isinstance(w, dict):
            raise SpecError(f"walls[{k}]: must be a side name or an object")
        for key in w:
            if key not in ("side", "openings"):
                raise SpecError(f"walls[{k}].{key}: unknown field (use side and openings)")
        side = w.get("side")
        if side not in KITCHEN_WALLS:
            raise SpecError(f"walls[{k}].side: must be one of {', '.join(KITCHEN_WALLS)} (the front stays open)")
        if side in seen:
            raise SpecError(f"walls[{k}].side: {side!r} is listed twice")
        seen.add(side)
        ops = w.get("openings", [])
        if not isinstance(ops, list):
            raise SpecError(f"walls[{k}].openings: must be a list")
        try:
            ops = _openings([dict(o, wall=side) if isinstance(o, dict) else o for o in ops])
        except SpecError as e:
            raise SpecError(f"walls[{k}].{e}")
        out.append({"side": side, "openings": [{kk: vv for kk, vv in o.items() if kk != "wall"} for o in ops]})
    return out


def _pergola_spec(raw):
    """A pergola description with every missing field filled from the library
    (defaults.pergola), lengths in mm and the post spacing worked out from the beam
    span formula. Returns (spec, library)."""
    import framecheck as fc
    for k in ("width", "depth"):
        if k not in raw:
            raise SpecError(f"{k}: required")
    for k in raw:
        if k not in PERGOLA_KNOWN:
            raise SpecError(f"{k}: unknown field for a pergola (known: {', '.join(PERGOLA_KNOWN)})")
    region = raw.get("region", "eu")
    try:
        lib = tl.load(region)
    except ValueError as e:
        raise SpecError(f"region: {e}")
    d = lib["defaults"]["pergola"]
    s = pl.Spec({"type": "pergola", "region": region, "units": raw.get("units", lib.get("units", "metric"))})
    if s["units"] not in ("metric", "imperial"):
        raise SpecError(f"units: must be 'metric' or 'imperial', not {s['units']!r}")
    if "name" in raw and (not isinstance(raw["name"], str) or not raw["name"].strip()):
        raise SpecError("name: must be text")
    s["name"] = raw.get("name", "pergola").strip()
    for k in ("width", "depth"):
        s[k] = _length(raw, k)
        if not s[k] > 0:
            raise SpecError(f"{k}: must be greater than 0")
    s["height"] = _length(raw, "height") if "height" in raw else float(d["height_mm"])
    if not s["height"] > 0:
        raise SpecError("height: must be greater than 0")
    for field in ("post_item", "beam_item", "rafter_item", "brace_item"):
        key = raw.get(field, d[field])
        try:
            it = tl.item(lib, key) if isinstance(key, str) else None
        except KeyError:
            it = None
        if not it or it["category"] != "sections":
            raise SpecError(f"{field}: {key!r} is not a timber section in the {region} library")
        s[field] = key
    from timber.foundations import footing_item
    s["foundation"] = raw.get("foundation", d["foundation"])
    s["footing_item"] = footing_item(lib, s["foundation"], raw.get("footing_item"))["key"]
    plies = raw.get("beam_plies", d["beam_plies"])
    if plies not in (1, 2) or isinstance(plies, bool):
        raise SpecError("beam_plies: use 1 or 2")
    s["beam_plies"] = plies
    mount = raw.get("beam_mount", "on_top")
    if mount != "on_top":
        raise SpecError("beam_mount: a pergola's beams sit on top of the posts (on_top, on a post cap); "
                        "the knee braces have nothing to meet between the plies of a sandwich beam")
    s["beam_mount"] = mount
    axis = raw.get("beam_axis", "x" if s["width"] >= s["depth"] else "y")
    if axis not in ("x", "y"):
        raise SpecError("beam_axis: use x (the beams run along the width) or y (along the depth)")
    s["beam_axis"] = axis
    for k, dk, lo, hi in (("rafter_spacing", "rafter_spacing_mm", 2, None), ("overhang", "overhang_mm", 0, 1200),
                          ("beam_overhang", "beam_overhang_mm", 0, 500), ("brace_leg", "brace_leg_mm", 250, 1500)):
        v = _length(raw, k) if k in raw else float(d[dk])
        if k == "rafter_spacing":
            if v < 2 * tl.item(lib, s["rafter_item"])["thickness_mm"]:
                raise SpecError(f"rafter_spacing: {v:g} mm is closer than two rafters")
        elif v < lo or v > hi:
            raise SpecError(f"{k}: use {lo:g} to {hi:g} mm")
        s[k] = v
    br = raw.get("braces", True)
    if not isinstance(br, bool):
        raise SpecError("braces: use true or false")
    s["braces"] = br
    sl = raw.get("slats", "none")
    if sl == "none" or sl is None:
        s["slats"] = "none"
    elif isinstance(sl, dict):
        for k in sl:
            if k not in ("item", "spacing"):
                raise SpecError(f"slats.{k}: unknown (use item and spacing)")
        item = sl.get("item", d["slat_item"])
        try:
            it = tl.item(lib, item) if isinstance(item, str) else None
        except KeyError:
            it = None
        if not it or it["category"] != "sections":
            raise SpecError(f"slats.item: {item!r} is not a timber section in the {region} library")
        sp = _length(sl, "spacing", "slats.spacing") if "spacing" in sl else float(d["slat_spacing_mm"])
        if sp < it["width_mm"] + 10:
            raise SpecError(f"slats.spacing: {sp:g} mm leaves no gap between {it['name']} slats")
        s["slats"] = {"item": item, "spacing": sp}
    else:
        raise SpecError('slats: use "none" or {"item": ..., "spacing": ...}')
    loads = {"snow_kn_m2": float(lib["defaults"]["loads"]["snow_kn_m2"])}
    if "loads" in raw:
        if not isinstance(raw["loads"], dict):
            raise SpecError("loads: must be an object")
        for k, v in raw["loads"].items():
            if k != "snow_kn_m2":
                raise SpecError(f"loads.{k}: unknown load for a pergola (known: snow_kn_m2)")
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
                raise SpecError("loads.snow_kn_m2: must be a number of kN/m2, more than 0")
            loads[k] = float(v)
    s["loads"] = loads
    # the rafters: a section and spacing that carry the span between the beams comfortably
    span = fc.pergola_rafter_span(s, lib)
    ev = lambda key, spacing: (span, spn.pergola_rafter_allowed(lib, dict(s, rafter_item=key, rafter_spacing=spacing))["span_mm"])
    r = pl.size_member(lib, s["rafter_item"], s["rafter_spacing"], ("rafter",), ev, item_named=raw.get("rafter_item"),
                       spacing_named="rafter_spacing" in raw)
    if r.changed:
        pl.decide(s, "Rafters", *pl.explain(lib, "rafters", r, s["rafter_item"], s["rafter_spacing"], s["units"],
                                            "the span between the beams is"))
        s["rafter_item"], s["rafter_spacing"] = r.key, float(r.spacing)
    along = s["width"] if axis == "x" else s["depth"]
    across = s["depth"] if axis == "x" else s["width"]
    bw = plies * tl.item(lib, s["beam_item"])["thickness_mm"]
    if across < 2 * s["overhang"] + bw + 600:
        raise SpecError(f"{'depth' if axis == 'x' else 'width'}: {across:g} mm is too small: it needs the two rafter "
                        f"overhangs ({s['overhang']:g} mm each), the beams and at least 600 mm between them")
    if along < 2 * s["beam_overhang"] + 600:
        raise SpecError(f"{'width' if axis == 'x' else 'depth'}: {along:g} mm is too small for beams overhanging "
                        f"{s['beam_overhang']:g} mm at each end and at least 600 mm between the end posts")
    if "post_spacing" in raw:
        s["post_spacing"] = _length(raw, "post_spacing")
        if s["post_spacing"] < 600:
            raise SpecError("post_spacing: must be at least 600 mm")
    else:
        allowed = fc.pergola_beam_allowed(lib, s)
        post, why, lim = pl.spacing_under(allowed, d["max_post_spacing_mm"])
        if post is None:
            raise SpecError(f"beam_item: {s['beam_item']!r} carries only about {lim / 1000:.2f} m between posts "
                            f"at this width; use a deeper beam or shorter rafters")
        s["post_spacing"] = post
        s.notes["post_spacing"] = pl.spacing_note(allowed, d["max_post_spacing_mm"], why,
                                                  f"A beam of {plies} x {pl.section_name(lib, s['beam_item'])} carrying the rafters")
    def item_ok(key):
        try:
            return tl.item(lib, key)["category"] in ("sections", "sheets", "cladding")
        except KeyError:
            return False
    try:
        s["edits"] = fe.validate(raw.get("edits", []), item_ok)
    except fe.EditError as e:
        raise SpecError(str(e))
    return s, lib


def _plan_terrace_frame(raw, s, lib, t, caps, ld):
    """Stacked (beams under the joists) or flush (joists hung between the beams, on the post bases): the
    description's `frame`, else stacked when the height leaves room for it and flush when it does not. A
    flush frame steps down through shallower beams and joists that still pass their spans; if even the
    shallowest does not fit, the error names the lowest height that works. Sets `frame`, and the beam and
    joist items when they change, and records the decisions."""
    from timber.foundations import footing_item, seat_height
    want = raw.get("frame")
    if want not in (None, "stacked", "flush"):
        raise SpecError("frame: use stacked (beams under the joists) or flush (joists hung between the beams)")
    u, H = s["units"], s["height"]
    seat = seat_height(lib, footing_item(lib, s["foundation"], s["footing_item"]))
    td = tl.item(lib, s["deck_board"])["thickness_mm"]
    hj, hb = tl.item(lib, s["joist_item"])["width_mm"], tl.item(lib, s["beam_item"])["width_mm"]
    stacked_min = seat + hb + hj + td
    if want:
        s["frame"] = want
    if want == "stacked" or (want is None and H >= stacked_min - 0.05):
        if H < stacked_min - 0.05:
            raise SpecError(f"height: {H:g} mm is too low for beams under the joists on this footing; use at least "
                            f"{pl.ceil_10(stacked_min):g} mm, or frame: flush (joists hung between the beams)")
        return
    s["frame"] = "flush"
    tspec = {k: s[k] for k in ("deck_board", "joist_item", "joist_spacing", "beam_item", "beam_plies", "loads")}
    res = pl.plan_flush(lib, tspec, H - td - seat, t["max_row_spacing_mm"], t["max_post_spacing_mm"],
                        beam_named=raw.get("beam_item"), joist_named=raw.get("joist_item"),
                        row_named=caps.get("row_spacing"), post_named=caps.get("post_spacing"))
    if not res.ok:
        if res.min_depth is None:
            raise SpecError("height: no beam and joist of the library carry this deck at this spacing; "
                            "use closer joists or a deeper section")
        low = pl.ceil_10(seat + res.min_depth + td)
        raise SpecError(f"height: {H:g} mm is too low for this footing; the lowest that works is {low:g} mm "
                        f"(the post base is {pl.length_text(seat, u)} tall, the shallowest beam and joist that still pass "
                        f"their spans {pl.length_text(res.min_depth, u)}, the boards {pl.length_text(td, u)}). "
                        "A footing with a lower post base may go lower")
    changed = (res.beam, res.joist) != (s["beam_item"], s["joist_item"])
    s["beam_item"], s["joist_item"] = res.beam, res.joist
    s["beam_mount"] = "on_top"
    why = f"{pl.length_text(H, u)} leaves no room for beams under the joists"
    if want == "flush" and H >= stacked_min - 0.05:
        why = "a flush frame was asked for"
    pl.decide(s, "Frame", "joists hung between the beams, on the post bases", why)
    if changed:
        nm = lambda k: pl.section_name(lib, k)
        pl.decide(s, "Beams and joists", f"beams of {nm(res.beam)} and joists of {nm(res.joist)}",
                  f"{pl.length_text(H - td - seat, u)} are free under the boards, so nothing deeper fits, "
                  "and these still pass their spans with the footings closer together")


def _terrace_spec(raw):
    """A terrace description with every missing field filled from the library
    (defaults.terrace), lengths in mm, the beam row and post spacings worked out
    from the span formulas. Returns (spec, library)."""
    import framecheck as fc
    for k in ("width", "depth", "height"):
        if k not in raw:
            raise SpecError(f"{k}: required")
    for k in raw:
        if k not in TERRACE_KNOWN:
            raise SpecError(f"{k}: unknown field for a terrace (known: {', '.join(TERRACE_KNOWN)})")
    region = raw.get("region", "eu")
    try:
        lib = tl.load(region)
    except ValueError as e:
        raise SpecError(f"region: {e}")
    t = lib["defaults"]["terrace"]
    s = pl.Spec({"type": "terrace", "region": region, "units": raw.get("units", lib.get("units", "metric"))})
    if s["units"] not in ("metric", "imperial"):
        raise SpecError(f"units: must be 'metric' or 'imperial', not {s['units']!r}")
    if "name" in raw and (not isinstance(raw["name"], str) or not raw["name"].strip()):
        raise SpecError("name: must be text")
    s["name"] = raw.get("name", "terrace").strip()
    for k in ("width", "depth", "height"):
        s[k] = _length(raw, k)
        if not s[k] > 0:
            raise SpecError(f"{k}: must be greater than 0")
    for field in ("post_item", "beam_item", "joist_item", "deck_board"):
        key = raw.get(field, t[field])
        try:
            it = tl.item(lib, key) if isinstance(key, str) else None
        except KeyError:
            it = None
        if not it or it["category"] != "sections":
            raise SpecError(f"{field}: {key!r} is not a timber section in the {region} library")
        if field == "deck_board" and "deck" not in it:
            raise SpecError(f"deck_board: {key!r} is not a deck board in the {region} library "
                            f"(have: {', '.join(k for k, v in lib['sections'].items() if 'deck' in v)})")
        s[field] = key
    from timber.foundations import footing_item
    s["foundation"] = raw.get("foundation", t["foundation"])
    s["footing_item"] = footing_item(lib, s["foundation"], raw.get("footing_item"))["key"]
    plies = raw.get("beam_plies", t["beam_plies"])
    if plies not in (1, 2) or isinstance(plies, bool):
        raise SpecError("beam_plies: use 1 or 2")
    s["beam_plies"] = plies
    mount = raw.get("beam_mount", t["beam_mount"] if plies == 2 else "on_top")
    if mount not in ("on_top", "sandwich"):
        raise SpecError("beam_mount: use on_top (on the posts, on a post cap) or sandwich (a ply either side, bolted)")
    if mount == "sandwich" and plies != 2:
        raise SpecError("beam_mount: a sandwich beam has two plies; use on_top for one")
    s["beam_mount"] = mount
    board = tl.item(lib, s["deck_board"])
    lim = board["deck"]["max_joist_spacing_mm"]
    s["joist_spacing"] = _length(raw, "joist_spacing") if "joist_spacing" in raw else float(lim)
    s["board_gap"] = _length(raw, "board_gap") if "board_gap" in raw else float(board["deck"]["gap_mm"])
    joist = tl.item(lib, s["joist_item"])
    if s["joist_spacing"] < 2 * joist["thickness_mm"]:
        raise SpecError(f"joist_spacing: {s['joist_spacing']:g} mm is closer than two {joist['name']} joists")
    if not 0 <= s["board_gap"] <= 20:
        raise SpecError("board_gap: use 0 to 20 mm")
    loads = {"floor_kn_m2": float(t["floor_kn_m2"])}
    if "loads" in raw:
        if not isinstance(raw["loads"], dict):
            raise SpecError("loads: must be an object")
        for k, v in raw["loads"].items():
            if k != "floor_kn_m2":
                raise SpecError(f"loads.{k}: unknown load for a terrace (known: floor_kn_m2)")
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
                raise SpecError("loads.floor_kn_m2: must be a number of kN/m2, more than 0")
            loads[k] = float(v)
    s["loads"] = loads
    # spacings: the library's caps, kept under 80% of what the span formulas allow
    ld = fc.terrace_loads(lib, s)
    caps = {}
    for k, cap_k, calc in (("row_spacing", "max_row_spacing_mm", fc.joist_allowed),
                           ("post_spacing", "max_post_spacing_mm", None)):
        if k in raw:
            caps[k] = _length(raw, k)
            if caps[k] < 300:
                raise SpecError(f"{k}: must be at least 300 mm")
    u = s["units"]
    _plan_terrace_frame(raw, s, lib, t, caps, ld)
    row = caps.get("row_spacing")
    if row is None:
        allowed = fc.joist_allowed(lib, s, ld)
        row, why, lim = pl.spacing_under(allowed, t["max_row_spacing_mm"])
        if row is None:
            raise SpecError(f"joist_item: {s['joist_item']!r} at {s['joist_spacing']:g} mm carries only about "
                            f"{lim / 1000:.2f} m between beams; use a deeper joist or closer spacing")
        s.notes["row_spacing"] = pl.spacing_note(allowed, t["max_row_spacing_mm"], why,
                                                 f"deck joists of {pl.section_name(lib, s['joist_item'])}")
    s["row_spacing"] = float(row)
    post = caps.get("post_spacing")
    if post is None:
        allowed = fc.beam_allowed(lib, s, ld, s["row_spacing"])
        post, why, lim = pl.spacing_under(allowed, t["max_post_spacing_mm"])
        if post is None:
            raise SpecError(f"beam_item: {s['beam_item']!r} carries only about {lim / 1000:.2f} m between posts "
                            f"over beams {s['row_spacing']:g} mm apart; use a deeper beam or closer rows")
        s.notes["post_spacing"] = pl.spacing_note(allowed, t["max_post_spacing_mm"], why,
                                                  f"a beam of {s['beam_plies']} × {pl.section_name(lib, s['beam_item'])}")
    s["post_spacing"] = float(post)
    def item_ok(key):
        try:
            return tl.item(lib, key)["category"] in ("sections", "sheets", "cladding")
        except KeyError:
            return False
    try:
        s["edits"] = fe.validate(raw.get("edits", []), item_ok)
    except fe.EditError as e:
        raise SpecError(str(e))
    return s, lib


def _gable_roof(raw, s, lib, d):
    """Pitch (from pitch_deg or height_ridge), ridge board and ties of a gable shed."""
    rafter = tl.item(lib, s["rafter_item"])
    wr, tr = rafter["width_mm"], rafter["thickness_mm"]
    D = s["depth"]
    if "pitch_deg" in raw and "height_ridge" in raw:
        raise SpecError("height_ridge: give the pitch (pitch_deg) or the ridge height, not both")
    if "height_ridge" in s:
        rise = s["height_ridge"] - s["height_eaves"]
        if rise <= 0:
            raise SpecError(f"height_ridge: {s['height_ridge']:g} mm is not above height_eaves ({s['height_eaves']:g} mm)")
        # the rafter tops at the centre line: eaves + (depth / 2) * tan(pitch) + rafter depth / cos(pitch)
        lo, hi = 0.0, math.radians(MAX_PITCH_DEG)
        f = lambda a: D / 2 * math.tan(a) + wr / math.cos(a)
        if rise < f(lo) - EPS:
            raise SpecError(f"height_ridge: {s['height_ridge']:g} mm is too low: even a flat roof needs "
                            f"{s['height_eaves'] + f(lo):g} mm for the rafters")
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) < rise else (lo, mid)
        pitch = round(math.degrees((lo + hi) / 2), 4)
        del s["height_ridge"]
    else:
        pitch = raw.get("pitch_deg", lib["defaults"].get("pitch_deg", 25))
        if isinstance(pitch, bool) or not isinstance(pitch, (int, float)):
            raise SpecError("pitch_deg: must be a number of degrees")
    if not 0 < pitch <= MAX_PITCH_DEG:
        raise SpecError(f"pitch_deg: {pitch:g} degrees does not work; use more than 0 and up to {MAX_PITCH_DEG:g}")
    cov = s["roofing"]
    lim = lib["defaults"].get("min_roof_pitch_deg", {}).get(cov)
    if lim is not None and pitch < lim - 0.05:
        raise SpecError(f"pitch_deg: {pitch:g} degrees is too flat for {cov} (it needs at least {lim:g}); "
                        "raise the pitch (or the ridge) or choose another roofing")
    s["pitch_deg"] = float(pitch)
    need = wr / math.cos(math.radians(pitch))               # the depth of the rafter's plumb cut
    secs = [(k, v) for k, v in lib["sections"].items()
            if MIN_RIDGE_THICKNESS - EPS <= v["thickness_mm"] <= tr + EPS and v["width_mm"] >= need - EPS]
    rk = raw.get("ridge_item")
    if rk is None:
        if not secs:
            raise SpecError(f"ridge_item: no section in the library is at least {need:.0f} mm deep and "
                            f"{MIN_RIDGE_THICKNESS:g} to {tr:g} mm thick; lower the pitch or name one")
        rk = min(secs, key=lambda kv: (kv[1]["thickness_mm"] * kv[1]["width_mm"], kv[0]))[0]
    else:
        try:
            rit = tl.item(lib, rk) if isinstance(rk, str) else None
        except KeyError:
            rit = None
        if not rit or rit["category"] != "sections":
            raise SpecError(f"ridge_item: {rk!r} is not a timber section in the {s['region']} library")
        if rit["thickness_mm"] < MIN_RIDGE_THICKNESS - EPS:
            raise SpecError(f"ridge_item: {rk!r} is {rit['thickness_mm']:g} mm thick; a ridge board is at least "
                            f"{MIN_RIDGE_THICKNESS:g} mm")
        if rit["width_mm"] < need - EPS:
            raise SpecError(f"ridge_item: {rk!r} is {rit['width_mm']:g} mm deep; the ridge board must be at least "
                            f"as deep as the rafters' plumb cut ({need:.0f} mm at {pitch:g} degrees)")
    s["ridge_item"] = rk
    tk = raw.get("tie_item", s["rafter_item"])
    try:
        tit = tl.item(lib, tk) if isinstance(tk, str) else None
    except KeyError:
        tit = None
    if not tit or tit["category"] != "sections":
        raise SpecError(f"tie_item: {tk!r} is not a timber section in the {s['region']} library")
    s["tie_item"] = tk


def _openings(raw):
    if not isinstance(raw, list):
        raise SpecError("openings: must be a list")
    out = []
    for i, o in enumerate(raw):
        p = f"openings[{i}]"
        if not isinstance(o, dict):
            raise SpecError(f"{p}: must be an object")
        for k in o:
            if k not in ("wall", "kind", "x", "width", "height", "sill"):
                raise SpecError(f"{p}.{k}: unknown field")
        if o.get("wall") not in WALLS:
            raise SpecError(f"{p}.wall: must be one of {', '.join(WALLS)}")
        if o.get("kind") not in KINDS:
            raise SpecError(f"{p}.kind: must be 'door' or 'window'")
        n = {"wall": o["wall"], "kind": o["kind"]}
        for k in ("x", "width", "height"):
            if k not in o:
                raise SpecError(f"{p}.{k}: required")
            n[k] = _length(o, k, f"{p}.{k}")
        if o["kind"] == "window":
            if "sill" not in o:
                raise SpecError(f"{p}.sill: required for a window (height of its bottom above the floor deck)")
            n["sill"] = _length(o, "sill", f"{p}.sill")
        elif "sill" in o:
            raise SpecError(f"{p}.sill: a door starts at the floor; remove it")
        else:
            n["sill"] = 0.0
        if n["width"] <= 0:
            raise SpecError(f"{p}.width: must be greater than 0")
        if n["height"] <= 0:
            raise SpecError(f"{p}.height: must be greater than 0")
        if n["sill"] < 0:
            raise SpecError(f"{p}.sill: must be 0 or more")
        out.append(n)
    return out


# ------------------------------------------------------------------ output

def dumps(frame):
    """Sorted keys, one member or joint per line, so the file diffs well."""
    def one(v):
        return json.dumps(v, sort_keys=True, separators=(", ", ": "), ensure_ascii=False)
    parts = []
    for key in sorted(frame):
        v = frame[key]
        if isinstance(v, list) and v and isinstance(v[0], dict):
            body = ",\n".join("  " + one(x) for x in v)
            parts.append(f' "{key}": [\n{body}\n ]')
        else:
            parts.append(f' "{key}": {one(v)}')
    return "{\n" + ",\n".join(parts) + "\n}\n"


def generate(raw):
    """Frame dict from a spec dict. Raises SpecError. What the planner chose is in the frame's
    "decisions" (left out when it chose nothing)."""
    spec, lib = resolve_spec(raw)
    if spec["type"] == "terrace":
        _check_terrace(spec, lib)
        fr = recipes.terrace(spec, lib)
    elif spec["type"] == "pergola":
        fr = recipes.pergola(spec, lib)
    elif spec["type"] == "summer-kitchen":
        fr = recipes.summer_kitchen(spec, lib)
    else:
        _check_geometry(spec, lib)
        fr = recipes.gable_shed(spec, lib) if spec["type"] == "gable-shed" else recipes.pent_shed(spec, lib)
    if getattr(spec, "decisions", None):
        fr["decisions"] = list(spec.decisions)
    return fr


def _check_terrace(s, lib):
    for k in ("width", "depth"):
        if s[k] < 600:
            raise SpecError(f"{k}: {s[k]:g} mm is too small for a terrace; use at least 600 mm")
    t = {k: tl.item(lib, s[k]) for k in ("post_item", "beam_item", "joist_item", "deck_board")}
    low = t["deck_board"]["thickness_mm"] + t["joist_item"]["width_mm"]
    if s["height"] <= low:
        raise SpecError(f"height: {s['height']:g} mm leaves no room for the joists and boards ({low:g} mm)")


def _check_geometry(s, lib):
    fr = tl.item(lib, s["frame_item"])
    w = fr["width_mm"]
    gable = s["type"] == "gable-shed"
    hb = s["height_eaves"] if gable else s["height_back"]
    if not gable and s["height_back"] > s["height_front"] + EPS:
        raise SpecError(f"height_back: {s['height_back']:g} mm is higher than height_front "
                        f"({s['height_front']:g} mm); the roof falls to the back, so the back must be "
                        "the same or lower")
    if s["depth"] <= 2 * w + 2 * fr["thickness_mm"]:
        raise SpecError(f"depth: {s['depth']:g} mm is too small for two walls of {w:g} mm")
    if s["width"] <= 2 * w + 2 * fr["thickness_mm"]:
        raise SpecError(f"width: {s['width']:g} mm is too small for two walls of {w:g} mm")
    fl = tl.item(lib, s["floor_item"])
    zd = fl["width_mm"] + tl.item(lib, s["floor_deck"])["thickness_mm"]
    if hb - 2 * fr["thickness_mm"] - zd <= 0:
        raise SpecError(f"{'height_eaves' if gable else 'height_back'}: {hb:g} mm leaves no room above the floor "
                        f"(its top is {zd:g} mm up)")
    for k in ("stud_spacing", "joist_spacing", "rafter_spacing"):
        sec = {"stud_spacing": fr, "joist_spacing": fl, "rafter_spacing": tl.item(lib, s["rafter_item"])}[k]
        if s[k] < 2 * sec["thickness_mm"]:
            raise SpecError(f"{k}: {s[k]:g} mm is closer than two {sec['name']} members")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the frame file for a timber structure from its description, "
                                             "or list what can be described (--types, --fields).")
    ap.add_argument("spec", nargs="?", help="description JSON")
    ap.add_argument("--out", help="frame.json to write")
    ap.add_argument("--types", action="store_true", help="list the recipes, one line each")
    ap.add_argument("--fields", metavar="TYPE", help="list every field the recipe accepts, with meaning, default and allowed values")
    ap.add_argument("--region", default="eu", help="library for --fields: eu (default) or us")
    a = ap.parse_args(argv)
    if a.types:
        w = max(len(k) for k in fld.TYPES)
        for k, (text, _) in fld.TYPES.items():
            print(f"{k:<{w}}  {text}")
        return 0
    if a.fields:
        if a.fields not in fld.TYPES:
            print(f"frame: {a.fields!r} is not a recipe; use one of {', '.join(fld.TYPES)}", file=sys.stderr)
            return 2
        try:
            lib = tl.load(a.region)
        except ValueError as e:
            print(f"frame: region: {e}", file=sys.stderr)
            return 2
        print("\n".join(fld.describe(a.fields, lib)))
        return 0
    if not (a.spec and a.out):
        ap.error("give a description and --out, or --types, or --fields <type>")
    try:
        with open(a.spec, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"frame: can't read {a.spec}: {e}", file=sys.stderr)
        return 2
    try:
        frame = generate(raw)
    except SpecError as e:
        print(f"frame: {e}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(frame))
    from collections import Counter
    c = Counter(m["kind"] for m in frame["members"])
    print(f"frame: {len(frame['members'])} members, {len(frame['joints'])} joints -> {a.out}")
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
    if frame.get("decisions"):
        print("How it was planned:")
        for d in frame["decisions"]:
            print(f"  {d['what']}: {d['chose']} ({d['why']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
