"""What each recipe accepts: one table per recipe, the single source of the field names the description
checks (tools/frame.py takes its lists of known fields from here) and of `tools/frame.py --fields <type>`.

A field is (name, meaning, default, allowed, example): the meaning in plain words, the default (text, or a
function of the region's library) and the allowed values; `example` is a value that is accepted for it
(the tests build one with it). Defaults read the region's library, so they come out in its units.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402

REQ = "required"
LEN = 'a length: millimetres, or text such as "3 m" or "10\'"'


class Ctx:
    """The region's library, for defaults and allowed values."""

    def __init__(self, lib):
        self.lib, self.d = lib, lib["defaults"]
        self.units = lib.get("units", "metric")
        self.t, self.p, self.k = (self.d.get(x, {}) for x in ("terrace", "pergola", "summer_kitchen"))

    def L(self, mm):
        return tl.fmt_length(float(mm), self.units)

    def keys(self, category, only=None):
        ks = [k for k, v in self.lib.get(category, {}).items() if only is None or only(v)]
        return ", ".join(ks)

    def sections(self):
        return "a timber section of the library: " + self.keys("sections", lambda v: "deck" not in v)

    def sheets(self):
        return "a sheet of the library: " + self.keys("sheets")

    def deck_boards(self):
        return "a deck board of the library: " + self.keys("sections", lambda v: "deck" in v)

    def footings(self):
        return "a footing of the library: " + ", ".join(self.t.get("footings", {}).values())


def F(name, meaning, default="the library's default", allowed="", example=None):
    return {"name": name, "meaning": meaning, "default": default, "allowed": allowed, "example": example}


def _ids(c):
    return [F("type", "which recipe", REQ, "pent-shed, gable-shed, terrace, pergola or summer-kitchen"),
            F("name", "a name for the structure", "the recipe's name", "text", "my-build"),
            F("region", "which library and units: eu (metric sizes) or us (lumber sizes)", "eu", "eu or us", c.lib["region"]),
            F("units", "how lengths are shown", c.lib.get("units", "metric"), "metric or imperial", c.units)]


def _loads(c, which):
    d = {"snow_kn_m2": c.d["loads"]["snow_kn_m2"], "floor_kn_m2": c.d["loads"]["floor_kn_m2"]}
    if which == "terrace":
        d = {"floor_kn_m2": c.t["floor_kn_m2"]}
    elif which == "pergola":
        d = {"snow_kn_m2": d["snow_kn_m2"]}
    elif which == "kitchen":
        d = {"snow_kn_m2": d["snow_kn_m2"], "floor_kn_m2": c.t["floor_kn_m2"]}
    return F("loads", "design loads in kN/m2: " + ", ".join(sorted(d)), ", ".join(f"{k} {v:g}" for k, v in sorted(d.items())),
             "an object with those keys, numbers above 0", {k: v for k, v in d.items()})


EDITS = F("edits", "one-off changes to single pieces, applied after every rebuild (see the skill)", "none",
          'a list of {"op": "move" | "resize" | "remove" | "add", "id": ...}', [])
SOILS = "ground_screw, pier_block or concrete_footing"


def shed(c, gable):
    d = c.d
    f = _ids(c) + [
        F("width", "the footprint along X: the length of the front wall", REQ, LEN, 3000),
        F("depth", "the footprint along Y, front to back", REQ, LEN, 2000)]
    if gable:
        f += [F("height_eaves", "height of the eave walls' top plates above the underside of the floor frame",
                f"{c.L(2000)}, raised in 50 mm steps so the doors and windows fit", LEN, 2400),
              F("pitch_deg", "roof pitch in degrees (not with height_ridge)", f"{d.get('pitch_deg', 25):g}",
                f"the roofing's minimum up to 60", 25),
              F("height_ridge", "height of the rafters' top at the ridge, same datum as height_eaves (not with pitch_deg)",
                "from pitch_deg", LEN, None),
              F("ridge_item", "the ridge board", "the smallest deep-enough section", c.sections(), None),
              F("tie_item", "the ties beside each rafter pair", "the rafter section", c.sections(), None)]
    else:
        f += [F("height_front", "height of the front wall's top plate above the underside of the floor frame",
                f"{c.L(2300)}, higher when the roof would be too flat or a door needs it", LEN, 2500),
              F("height_back", "height of the back wall's top plate (the roof falls to the back)",
                f"{c.L(300)} below the front, more when the roof would be too flat", LEN, 2000)]
    f += [
        F("stud_spacing", "wall studs, centre to centre", c.L(d["stud_spacing_mm"]), LEN, 600),
        F("joist_spacing", "floor joists, centre to centre", f"{c.L(d['joist_spacing_mm'])}, closer when the span needs it", LEN, 400),
        F("rafter_spacing", "rafters, centre to centre", f"{c.L(d['rafter_spacing_mm'])}, closer when the span needs it", LEN, 600),
        F("overhang", "roof overhang at the eaves", c.L(d["overhang_mm"]), LEN, 150),
        F("overhang_side", "roof overhang at the sides (a flying rafter on outriggers)", c.L(d["overhang_side_mm"]),
          "0, or one rafter thickness + 50 mm up to 300 mm", 150),
        F("frame_item", "wall studs and plates", d["items"]["frame"], c.sections(), d["items"]["frame"]),
        F("floor_item", "floor joists and rim joists", f"{d['items']['floor']}, deeper when the span needs it", c.sections(), d["items"]["floor"]),
        F("rafter_item", "rafters", f"{d['items']['rafter']}, deeper when the span needs it", c.sections(), d["items"]["rafter"]),
        F("header_item", "headers over openings (two plies where they fit)", "the wall section, deeper when the span needs it",
          c.sections(), d["items"]["frame"]),
        F("fascia_item", "fascia and bargeboards", "the rafter section", c.sections(), None),
        F("sheathing", "wall sheathing", d["items"]["sheathing"], c.sheets(), d["items"]["sheathing"]),
        F("floor_deck", "floor deck sheets", d["items"]["floor_deck"], c.sheets(), d["items"]["floor_deck"]),
        F("roof_deck", "roof deck sheets", d["items"]["roof_deck"], c.sheets(), d["items"]["roof_deck"]),
        F("cladding", "outside cladding", d["items"]["cladding"], "cladding of the library: " + c.keys("cladding"), d["items"]["cladding"]),
        F("treated_floor", "treated timber for the floor frame", str(d["treated_floor"]).lower(), "true or false", True),
        F("roofing", "the roof covering", "roofing-felt", "a roofing sold by area: " + c.keys("bought", lambda v: v.get("unit") == "m2"),
          "roofing-felt"),
        F("corner", "how wall corners are framed", d.get("details", {}).get("corner", "three-stud"),
          "three-stud, california or two-stud", "california"),
        F("top_plate", "one or two top plates", d.get("details", {}).get("top_plate", "double"), "double or single", "single"),
        F("openings", "doors and windows", "none",
          'a list of {"wall": front|back|left|right, "kind": door|window, "x", "width", "height", "sill" (windows)}', []),
        F("foundation", "footings under the floor frame", "none (the frame sits on its own supports)", SOILS, "ground_screw"),
        F("footing_item", "the footing product (with a foundation)", "the library's, by foundation", c.footings(), None),
        F("footing_spacing", "footings along the front and back rims (with a foundation)", c.L(c.t["footing_spacing_shed_mm"]), LEN, None),
        _loads(c, "shed"), EDITS]
    return f


def terrace(c):
    t, d = c.t, c.d
    return _ids(c) + [
        F("width", "the deck along X (the beams and boards run this way)", REQ, LEN, 4000),
        F("depth", "the deck along Y (the joists run this way)", REQ, LEN, 3000),
        F("height", "top of the deck boards above the ground", REQ, LEN, 600),
        F("foundation", "what carries the posts: " + SOILS, t["foundation"], SOILS, t["foundation"]),
        F("footing_item", "the footing product", "the library's, by foundation", c.footings(), None),
        F("post_item", "posts", t["post_item"], c.sections(), t["post_item"]),
        F("beam_item", "beams", t["beam_item"], c.sections(), t["beam_item"]),
        F("beam_plies", "boards side by side in a beam", str(t["beam_plies"]), "1 or 2", 2),
        F("beam_mount", "how the beam sits on the posts", t["beam_mount"] + " (on_top for one ply)", "on_top or sandwich", "on_top"),
        F("frame", "how joists meet beams: stacked (beams under the joists) or flush (joists hung between the beams, "
          "for a low deck)", "chosen from the height: stacked when there is room, flush when there is not",
          "stacked or flush", "flush"),
        F("joist_item", "deck joists", t["joist_item"], c.sections(), t["joist_item"]),
        F("joist_spacing", "deck joists, centre to centre", "the deck board's limit", LEN, None),
        F("deck_board", "deck boards", t["deck_board"], c.deck_boards(), t["deck_board"]),
        F("board_gap", "gap between deck boards", "the board's own (5 mm)", "0 to 20 mm", None),
        F("row_spacing", "most between beam rows", f"worked out from the joist span, at most {c.L(t['max_row_spacing_mm'])}", LEN, None),
        F("post_spacing", "most between posts in a row", f"worked out from the beam span, at most {c.L(t['max_post_spacing_mm'])}", LEN, None),
        _loads(c, "terrace"), EDITS]


def pergola(c):
    p = c.p
    return _ids(c) + [
        F("width", "the whole roofed area along X, rafter tails included", REQ, LEN, 5000),
        F("depth", "the whole roofed area along Y, rafter tails included", REQ, LEN, 3000),
        F("height", "underside of the beams above the ground", c.L(p["height_mm"]), LEN, 2300),
        F("foundation", "what carries the posts: " + SOILS, p["foundation"], SOILS, p["foundation"]),
        F("footing_item", "the footing product", "the library's, by foundation", c.footings(), None),
        F("post_item", "posts", p["post_item"], c.sections(), p["post_item"]),
        F("beam_item", "beams", p["beam_item"], c.sections(), p["beam_item"]),
        F("beam_plies", "boards side by side in a beam", str(p["beam_plies"]), "1 or 2", 2),
        F("beam_mount", "how the beams sit on the posts", "on_top", "on_top", "on_top"),
        F("beam_axis", "which way the beams run", "along the longer side", "x or y", "x"),
        F("rafter_item", "rafters", f"{p['rafter_item']}, deeper when the span needs it", c.sections(), p["rafter_item"]),
        F("rafter_spacing", "rafters, centre to centre", f"{c.L(p['rafter_spacing_mm'])}, closer when the span needs it", LEN, 600),
        F("overhang", "rafters past the beams", c.L(p["overhang_mm"]), "0 to 1200 mm", 300),
        F("beam_overhang", "beams past the end posts' centres", c.L(p["beam_overhang_mm"]), "0 to 500 mm", 300),
        F("slats", "slats across the rafters", "none", '"none", or {"item": ..., "spacing": ...}', "none"),
        F("braces", "45 degree knee braces", "true", "true or false", True),
        F("brace_item", "the knee braces", p["brace_item"], c.sections(), p["brace_item"]),
        F("brace_leg", "length of each brace's legs", c.L(p["brace_leg_mm"]), "250 to 1500 mm", 600),
        F("post_spacing", "most between posts along a beam", f"worked out from the beam span, at most {c.L(p['max_post_spacing_mm'])}", LEN, None),
        _loads(c, "pergola"), EDITS]


def kitchen(c):
    k, p, t, d = c.k, c.p, c.t, c.d
    return _ids(c) + [
        F("width", "the posts' outer faces along X; the roof reaches past them", REQ, LEN, 4000),
        F("depth", "the posts' outer faces along Y", REQ, LEN, 3000),
        F("roof", "the roof shape", "gable", "gable (a ridge along the width) or mono (the front higher)", "gable"),
        F("floor", "a deck floor inside the posts", "none", "none or terrace", "none"),
        F("floor_height", "top of the floor above the ground (with a floor)", c.L(k["floor_height_mm"]), LEN, None),
        F("walls", "the closed sides; the front stays open", "none (open on all sides)",
          'a list of up to three of back, left, right, each a name or {"side": ..., "openings": [...]}', []),
        F("height_eaves", "underside of the lower beam above the ground", c.L(k["height_eaves_mm"]), LEN, 2300),
        F("height_front", "mono roof: the front beam's underside", "from pitch_deg", LEN, None),
        F("height_back", "mono roof: the back beam's underside (the same as height_eaves)", "height_eaves", LEN, None),
        F("height_ridge", "gable roof: the rafters' top at the ridge (not with pitch_deg)", "from pitch_deg", LEN, None),
        F("pitch_deg", "roof pitch in degrees", f"{d.get('pitch_deg', 25):g} gable, {k['pitch_deg_mono']:g} mono", "above 0 up to 60", None),
        F("foundation", "what carries the posts: " + SOILS, p["foundation"], SOILS, p["foundation"]),
        F("footing_item", "the footing product", "the library's, by foundation", c.footings(), None),
        F("post_item", "posts", p["post_item"], c.sections(), p["post_item"]),
        F("beam_item", "roof beams", p["beam_item"], c.sections(), p["beam_item"]),
        F("beam_plies", "boards side by side in a beam", str(p["beam_plies"]), "1 or 2", 2),
        F("post_spacing", "most between posts along a beam", f"worked out from the beam span, at most {c.L(p['max_post_spacing_mm'])}", LEN, None),
        F("rafter_item", "rafters", f"{d['items']['rafter']}, deeper when the span needs it", c.sections(), d["items"]["rafter"]),
        F("rafter_spacing", "rafters, centre to centre", f"{c.L(d['rafter_spacing_mm'])}, closer when the span needs it", LEN, 600),
        F("overhang", "roof overhang at the eaves", c.L(d["overhang_mm"]), "0 to 1200 mm", 150),
        F("overhang_side", "roof overhang at the sides", c.L(d["overhang_side_mm"]), "0, or one rafter thickness + 50 mm up to 300 mm", 150),
        F("fascia_item", "fascia and bargeboards", "the rafter section", c.sections(), None),
        F("ridge_item", "gable roof: the ridge board", "the smallest deep-enough section", c.sections(), None),
        F("tie_item", "gable roof: the ties", "the rafter section", c.sections(), None),
        F("roof_deck", "roof deck sheets", d["items"]["roof_deck"], c.sheets(), d["items"]["roof_deck"]),
        F("roofing", "the roof covering", "roofing-felt", "a roofing sold by area: " + c.keys("bought", lambda v: v.get("unit") == "m2"), "roofing-felt"),
        F("braces", "45 degree knee braces on open sides", "true", "true or false", True),
        F("brace_item", "the knee braces", p["brace_item"], c.sections(), p["brace_item"]),
        F("brace_leg", "length of each brace's legs", c.L(p["brace_leg_mm"]), "250 to 1500 mm", 600),
        F("frame_item", "wall studs and plates (with walls)", d["items"]["frame"], c.sections(), d["items"]["frame"]),
        F("stud_spacing", "wall studs, centre to centre", c.L(d["stud_spacing_mm"]), LEN, 600),
        F("sheathing", "wall sheathing", d["items"]["sheathing"], c.sheets(), d["items"]["sheathing"]),
        F("cladding", "outside cladding", d["items"]["cladding"], "cladding of the library: " + c.keys("cladding"), d["items"]["cladding"]),
        F("top_plate", "one or two top plates", d.get("details", {}).get("top_plate", "double"), "double or single", "single"),
        F("header_item", "headers over openings", "the wall section", c.sections(), None),
        F("joist_item", "floor joists (with a floor)", t["joist_item"], c.sections(), None),
        F("joist_spacing", "floor joists, centre to centre (with a floor)", "the deck board's limit", LEN, None),
        F("deck_board", "floor boards (with a floor)", t["deck_board"], c.deck_boards(), None),
        F("board_gap", "gap between floor boards (with a floor)", "the board's own (5 mm)", "0 to 20 mm", None),
        F("floor_beam_item", "floor beams (with a floor)", t["beam_item"], c.sections(), None),
        F("floor_beam_plies", "boards side by side in a floor beam", str(t["beam_plies"]), "1 or 2", None),
        F("floor_post_item", "floor posts (with a floor)", t["post_item"], c.sections(), None),
        _loads(c, "kitchen"), EDITS]


TYPES = {
    "pent-shed": ("A garden shed with a mono-pitch roof on a timber floor: studs, plates, sheathing, cladding, doors and windows.",
                  lambda c: shed(c, False)),
    "gable-shed": ("A garden shed with a gable roof (ridge along the width) on a timber floor; the door usually goes in a gable end.",
                   lambda c: shed(c, True)),
    "terrace": ("A raised deck on posts and beams with joists and boards; no roof, rails or steps.", terrace),
    "pergola": ("An open roof of beams, rafters and optional slats on posts, with knee braces; free standing, no walls.", pergola),
    "summer-kitchen": ("A roof (mono or gable) on posts and beams with an optional deck floor and up to three infill walls; "
                       "a stove or flue is not covered.", kitchen),
}


def table(rtype, lib):
    """The fields a recipe accepts, for a region's library: a list of {"name", "meaning", "default", "allowed", "example"}."""
    return TYPES[rtype][1](Ctx(lib))


def names(rtype, region="eu"):
    """The field names of a recipe (the same in every region)."""
    return tuple(f["name"] for f in table(rtype, tl.load(region)))


def describe(rtype, lib):
    """Lines of text for `tools/frame.py --fields`."""
    rows = table(rtype, lib)
    w = max(len(r["name"]) for r in rows)
    out = [f"{rtype}: {TYPES[rtype][0]}",
           f"Fields for region {lib['region']} (lengths in {lib.get('units', 'metric')} units). Set only what you want to change.", ""]
    for r in rows:
        out.append(f"{r['name']:<{w}}  {r['meaning']}")
        out.append(f"{'':<{w}}  default: {r['default']}" + (f"   allowed: {r['allowed']}" if r["allowed"] else ""))
    return out
