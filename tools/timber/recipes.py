"""Recipes: a short description turned into assemblies.

`pent_shed` is today's shed: a platform, four walls and a mono-pitch roof. It
works out the layout first (the numbers every block shares and the roof line,
a pure function of Y), then builds platform, walls and roof, puts the skins on
the walls, joins the corners between walls, adds the bought items and applies
the edits by piece. The result is the frame file's contents (see
docs/research/timber-structures.md), plus a list of the assemblies that made it.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import frame_edits as fe  # noqa: E402
from timber.store import (KINDS, SCHEMA, WALLS, Frame, Layout, SpecError, aabb, num, unit, _norm)  # noqa: E402
from timber.platform import Platform  # noqa: E402
from timber.roof import MonoRoof, RoofLine  # noqa: E402
from timber.roof_gable import GableLine, GableRoof  # noqa: E402
import timberlib as tl  # noqa: E402
from timber.wall import Wall, corners  # noqa: E402


def pent_shed(spec, lib):
    """The frame dict for a resolved pent-shed spec (see tools/frame.py)."""
    lay = Layout(spec, lib)
    line = RoofLine(lay)
    fr = Frame()
    platform = Platform(fr, lay).build()
    walls = {n: Wall(fr, lay, n, line) for n in WALLS}
    for w in walls.values():
        w.build()
    roof = MonoRoof(fr, lay, line, walls["front"].bear_id, walls["back"].bear_id,
                    {nm: [iid for iid, *_ in walls[nm].infill] for nm in ("left", "right")}).build()
    aabbs = {m["id"]: aabb(m) for m in fr.members}
    for n in WALLS:
        walls[n].skin(aabbs)
    corners(fr, lay, walls)
    roof.buy()
    buy_openings(fr, spec)
    apply_edits(fr, spec)
    return result(fr, spec)


def gable_shed(spec, lib):
    """The frame dict for a resolved gable-shed spec: a platform, four walls (the
    left and right ones with gable tops) and a gable roof on the front and back walls."""
    lay = Layout(spec, lib)
    rit = tl.item(lib, spec["ridge_item"])
    line = GableLine(lay, rit["thickness_mm"], rit["width_mm"])
    fr = Frame()
    Platform(fr, lay).build()
    walls = {n: Wall(fr, lay, n, line) for n in WALLS}
    for w in walls.values():
        w.build()
    roof = GableRoof(fr, lay, line, {"front": walls["front"].bear_id, "back": walls["back"].bear_id},
                     {nm: walls[nm].infill for nm in ("left", "right")}).build()
    aabbs = {m["id"]: aabb(m) for m in fr.members}
    for n in WALLS:
        walls[n].skin(aabbs)
    corners(fr, lay, walls)
    roof.buy()
    buy_openings(fr, spec)
    apply_edits(fr, spec)
    return result(fr, spec)


def buy_openings(fr, spec):
    """Doors and windows are bought ready made, one per opening."""
    for kind in KINDS:
        ops = [o for o in spec["openings"] if o["kind"] == kind]
        for n, o in enumerate(ops, 1):
            fr.bought.append({"item": kind, "qty": 1, "unit": "pcs",
                              "note": f"{o['wall']} wall, {o['width']:g} x {o['height']:g} mm opening"})


def apply_edits(fr, spec):
    """One-off changes by piece from the description (frame_edits.py)."""
    if not spec["edits"]:
        return
    try:
        fe.apply(fr.members, fr.joints, spec["edits"])
    except fe.EditError as e:
        raise SpecError(str(e))
    for m in fr.members:
        m["size"] = [num(v) for v in m["size"]]
        m["origin"] = [num(v) for v in m["origin"]]
        m["x"], m["y"] = unit(m["x"]), unit(m["y"])
        m["cut_deg"] = [num(v) for v in m["cut_deg"]]
    for j in fr.joints:
        for k, v in j.items():
            if isinstance(v, float):
                j[k] = num(v)


def result(fr, s):
    mem = sorted(fr.members, key=lambda m: m["id"])
    jt = sorted(fr.joints, key=lambda j: (j["type"], j["a"], j["b"]))
    return {"schema": SCHEMA, "name": s["name"], "region": s["region"], "units": s["units"],
            "spec": _norm(s), "members": mem, "joints": jt, "bought": fr.bought,
            "assemblies": fr.assemblies}
