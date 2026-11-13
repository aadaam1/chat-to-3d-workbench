#!/usr/bin/env python3
"""Frame generator for a mono-pitch (pent) shed.

    tools/frame.py projects/<name>/shed.json --out projects/<name>/out/frame.json   (or examples/<name>/...)

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

from timber.store import (EPS, KINDS, MIN_CRIPPLE, MIN_INFILL, MIN_SHEET, SCHEMA, WALLS,  # noqa: E402,F401
                          SpecError)
from timber import recipes  # noqa: E402


# ------------------------------------------------------------------ spec

REQUIRED = ("type", "width", "depth")
KNOWN = ("type", "name", "region", "units", "width", "depth", "height_front", "height_back",
         "stud_spacing", "joist_spacing", "rafter_spacing", "overhang", "frame_item",
         "floor_item", "rafter_item", "sheathing", "floor_deck", "roof_deck", "cladding",
         "treated_floor", "openings", "loads", "roofing", "corner", "top_plate", "header_item",
         "overhang_side", "fascia_item", "edits",
         "height_eaves", "pitch_deg", "height_ridge", "ridge_item", "tie_item",
         "foundation", "footing_item", "footing_spacing")
TERRACE_KNOWN = ("type", "name", "region", "units", "width", "depth", "height", "foundation", "footing_item",
                 "post_item", "beam_item", "beam_plies", "beam_mount", "joist_item", "joist_spacing",
                 "deck_board", "board_gap", "post_spacing", "row_spacing", "loads", "edits")
PERGOLA_KNOWN = ("type", "name", "region", "units", "width", "depth", "height", "foundation", "footing_item",
                 "post_item", "beam_item", "beam_plies", "beam_mount", "beam_axis", "rafter_item", "rafter_spacing",
                 "overhang", "beam_overhang", "slats", "braces", "brace_item", "brace_leg", "post_spacing",
                 "loads", "edits")
TYPES = ("pent-shed", "gable-shed", "terrace", "pergola")
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
    s = {"type": raw["type"], "region": region,
         "units": raw.get("units", lib.get("units", "metric"))}
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
    if gable:
        s.setdefault("height_eaves", DEFAULT_HEIGHT_EAVES)
        checked = ("width", "depth", "height_eaves", "stud_spacing", "joist_spacing", "rafter_spacing",
                   "overhang", "overhang_side")
    else:
        s.setdefault("height_front", DEFAULT_HEIGHT_FRONT)
        s.setdefault("height_back", s["height_front"] - DEFAULT_HEIGHT_DROP)
        checked = LENGTHS
    for k in checked:
        if not s[k] > 0 and not (k in ("overhang", "overhang_side") and s[k] == 0):
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
    s = {"type": "pergola", "region": region, "units": raw.get("units", lib.get("units", "metric"))}
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
        post = min(d["max_post_spacing_mm"], fc.SPACING_SHARE * allowed)
        if post < 600:
            raise SpecError(f"beam_item: {s['beam_item']!r} carries only about {post / 1000:.2f} m between posts "
                            f"at this width; use a deeper beam or shorter rafters")
        s["post_spacing"] = float(math.floor(post / 50) * 50)
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
    s = {"type": "terrace", "region": region, "units": raw.get("units", lib.get("units", "metric"))}
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
    row = caps.get("row_spacing")
    if row is None:
        row = min(t["max_row_spacing_mm"], fc.SPACING_SHARE * fc.joist_allowed(lib, s, ld))
        if row < 600:
            raise SpecError(f"joist_item: {s['joist_item']!r} at {s['joist_spacing']:g} mm carries only about "
                            f"{row / 1000:.2f} m between beams; use a deeper joist or closer spacing")
        row = math.floor(row / 50) * 50
    s["row_spacing"] = float(row)
    post = caps.get("post_spacing")
    if post is None:
        post = min(t["max_post_spacing_mm"], fc.SPACING_SHARE * fc.beam_allowed(lib, s, ld, s["row_spacing"]))
        if post < 600:
            raise SpecError(f"beam_item: {s['beam_item']!r} carries only about {post / 1000:.2f} m between posts "
                            f"over beams {s['row_spacing']:g} mm apart; use a deeper beam or closer rows")
        post = math.floor(post / 50) * 50
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
    """Frame dict from a spec dict. Raises SpecError."""
    spec, lib = resolve_spec(raw)
    if spec["type"] == "terrace":
        _check_terrace(spec, lib)
        return recipes.terrace(spec, lib)
    if spec["type"] == "pergola":
        return recipes.pergola(spec, lib)
    _check_geometry(spec, lib)
    if spec["type"] == "gable-shed":
        return recipes.gable_shed(spec, lib)
    return recipes.pent_shed(spec, lib)


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
    ap = argparse.ArgumentParser(description="Generate the frame file for a pent shed from its spec.")
    ap.add_argument("spec", help="shed spec JSON")
    ap.add_argument("--out", required=True, help="frame.json to write")
    a = ap.parse_args(argv)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
