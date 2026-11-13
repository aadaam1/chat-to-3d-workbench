"""Recipes: a short description turned into assemblies.

`pent_shed` is today's shed: a platform, four walls and a mono-pitch roof. It
works out the layout first (the numbers every block shares and the roof line,
a pure function of Y), then builds platform, walls and roof, puts the skins on
the walls, joins the corners between walls, adds the bought items and applies
the edits by piece. The result is the frame file's contents (see
docs/research/timber-structures.md), plus a list of the assemblies that made it.
"""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import frame_edits as fe  # noqa: E402
from timber.store import (KINDS, SCHEMA, WALLS, Frame, Layout, SpecError, aabb, num, unit, _norm)  # noqa: E402
from timber.platform import BoardPlatform, Platform  # noqa: E402
from timber.foundations import Footings, footing_item  # noqa: E402
from timber.posts import Posts  # noqa: E402
from timber.beam import Beam  # noqa: E402
from timber.pergola import Axes, KneeBraces, Rafters, Slats, MIN_BRACE_CLEAR, C45  # noqa: E402
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
    foot = shed_footings(fr, lay, spec, lib)
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
    if foot:
        foot.buy()
        foot.assembly()
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
    foot = shed_footings(fr, lay, spec, lib)
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
    if foot:
        foot.buy()
        foot.assembly()
    apply_edits(fr, spec)
    return result(fr, spec)


SHED_FOOTING_INSET = 150.0     # mm, the first footing under a rim from the corner


def shed_footings(fr, lay, spec, lib):
    """Footings under the floor frame's front and back rim joists, when the
    description has a `foundation`: None otherwise (the frame is then exactly
    as it always was). The frame keeps its origin (the underside of the rims);
    the ground is below it, by the height of the footing's post base."""
    if "foundation" not in spec:
        return None
    foot = Footings(fr, lib, footing_item(lib, spec["foundation"], spec["footing_item"]))
    W, D, tj = lay.W, lay.D, lay.tj
    n = max(1, math.ceil((W - 2 * SHED_FOOTING_INSET) / spec["footing_spacing"] - 1e-9))
    xs = [SHED_FOOTING_INSET + (W - 2 * SHED_FOOTING_INSET) * i / n for i in range(n + 1)]
    pts = [(x, y) for y in (tj / 2, D - tj / 2) for x in xs]
    recs = foot.place(pts, carry=(100.0, tj), top=0.0, prefix="foundations")
    for rec in recs:
        foot.fix(rec, "floor/rim-front" if rec["y"] < D / 2 else "floor/rim-back")
    return foot


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


def terrace(spec, lib):
    """The frame dict for a resolved terrace spec: footings, posts, beams in rows
    along X, deck joists across them (along Y) and deck boards on top, with the
    ground at Z 0 and the top of the boards at `height`.

    Beam rows are inset from the long edges and spaced no further than
    `row_spacing`; posts sit under every row at most `post_spacing` apart. A post
    shorter than the library's `min_post_mm` is left out: the beams then rest on the
    post bases directly, and the footings' above-ground part is built up to meet them."""
    fr = Frame()
    W, D, H = spec["width"], spec["depth"], spec["height"]
    board, joist, beam_it = (tl.item(lib, spec[k]) for k in ("deck_board", "joist_item", "beam_item"))
    td, hj, hb = board["thickness_mm"], joist["width_mm"], beam_it["width_mm"]
    z_joist = H - td - hj                                   # underside of the joists = top of the beams
    foot = Footings(fr, lib, footing_item(lib, spec["foundation"], spec["footing_item"]))
    posts = Posts(fr, lib, spec["post_item"])
    mount, plies = spec["beam_mount"], spec["beam_plies"]
    post_top = z_joist if mount == "sandwich" else z_joist - hb
    # no posts when they would be shorter than min_post_mm, if the beams then fit on the bases
    no_posts = (post_top - foot.seat < lib["defaults"]["terrace"]["min_post_mm"]
                and z_joist - hb >= foot.seat - 0.05)
    if no_posts:
        mount = "on_top"
    beam = Beam(fr, lib, spec["beam_item"], plies, mount)
    inset = math.ceil((beam.width(posts.w) / 2 + 25) / 5) * 5
    if no_posts:
        inset = math.ceil((beam.width() / 2 + 25) / 5) * 5
    ys = _even(inset, D - inset, spec["row_spacing"])
    xs = _even(inset, W - inset, spec["post_spacing"])
    pts = Posts.grid(xs, ys)
    if no_posts:
        seat = z_joist - hb
        if seat < foot.seat - 0.05:
            low = foot.seat + hb + hj + td
            raise SpecError(f"height: {H:g} mm is too low for this footing, beam and deck; "
                            f"at least {low:g} mm (use a shallower beam_item or a lower footing)")
        recs = foot.place(pts, carry=(posts.t, beam.width()), ground=0.0, top=seat, prefix="foundations")
        pid = None
    else:
        if post_top - foot.seat < MIN_POST_LEN:
            low = H - (post_top - foot.seat) + MIN_POST_LEN
            raise SpecError(f"height: {H:g} mm is too low for this footing, beam and deck; "
                            f"use at least {low:g} mm")
        recs = foot.place(pts, carry=(posts.t, posts.w), ground=0.0, prefix="foundations")
        pid = posts.place(pts, top=post_top, footings=recs, prefix="posts")
    nx = len(xs)
    edges = [0.0] + [(a + b) / 2 for a, b in zip(ys, ys[1:])] + [D]
    for k, y in enumerate(ys):
        sup = [(x, (pid[k * nx + i]["id"] if pid else recs[k * nx + i]["base"])) for i, x in enumerate(xs)]
        beam.place(y, 0.0, W, z_joist, sup, posts.w, edges[k + 1] - edges[k], axis=0, prefix="beams",
                   fix=(lambda a, b: fr.joint("post-base", b, a)) if no_posts else None, cap=not no_posts)
    deck = BoardPlatform(fr, lib, W, D, spec["joist_item"], spec["deck_board"], spec["joist_spacing"], H,
                         gap=spec["board_gap"]).build(bearers=ys)
    deck.bear_on([pid for r in beam.records for pid in r["plies"]])
    foot.buy()
    beam.buy()
    foot.assembly()
    if pid:
        posts.assembly()
    beam.assembly()
    apply_edits(fr, spec)
    return result(fr, spec)


MIN_RAFTER_FOR_BRACE = 38.0    # mm: a cross brace is ripped to the rafter's thickness, so no thinner than a 2x


def _centre(m, axis):
    """Centre of a member along a world axis (members here are axis aligned)."""
    from timber.store import aabb
    lo, hi = aabb(m)
    return (lo[axis] + hi[axis]) / 2.0


def pergola(spec, lib):
    """The frame dict for a resolved pergola spec: footings, posts, two beams on the
    posts along the long sides (or `beam_axis`), rafters across the beams on top
    of them with an overhang past each, optional slats across the rafters, and
    45 degree knee braces from the posts up to the beams. The ground is at Z 0 and
    the underside of the beams at `height`."""
    fr = Frame()
    ax = Axes(0 if spec["beam_axis"] == "x" else 1)
    W, D, H = spec["width"], spec["depth"], spec["height"]
    L, Wd = (W, D) if ax.axis == 0 else (D, W)
    foot = Footings(fr, lib, footing_item(lib, spec["foundation"], spec["footing_item"]))
    posts = Posts(fr, lib, spec["post_item"])
    beam = Beam(fr, lib, spec["beam_item"], spec["beam_plies"], "on_top")
    bw, bo, oh = beam.width(), spec["beam_overhang"], spec["overhang"]
    zb = H + beam.hb                                          # top of the beams
    if H - foot.seat < MIN_POST_LEN:
        raise SpecError(f"height: {H:g} mm is too low for this footing; use at least {foot.seat + MIN_POST_LEN:g} mm")
    us = _even(bo, L - bo, spec["post_spacing"])
    lines = [oh + bw / 2, Wd - oh - bw / 2]
    pts = [tuple(ax.pt(u, v)[:2]) for v in lines for u in us]
    recs = foot.place(pts, carry=(posts.t, posts.w), ground=0.0, prefix="foundations")
    pid = posts.place(pts, top=H, footings=recs, prefix="posts")
    rs = lines[1] - lines[0]
    trib = rs / 2 + oh
    braces = KneeBraces(fr, lib, ax, spec["brace_item"], spec["brace_leg"])
    n = len(us)
    plan = []                                                  # (line index, post record, u face, side, leg)
    cross_plan = []                                            # (post record, u, v face, side, leg)
    rt = tl.item(lib, spec["rafter_item"])["thickness_mm"]
    if spec["braces"] and rt < MIN_RAFTER_FOR_BRACE:
        raise SpecError(f"rafter_item: {spec['rafter_item']!r} is {rt:g} mm thick; the knee braces across the beams "
                        f"meet a rafter over each post and need one at least {MIN_RAFTER_FOR_BRACE:g} mm thick "
                        "(or braces: false)")
    pv = posts.w if ax.axis == 0 else posts.t                  # a post's size across the beams
    if spec["braces"]:
        for k, v in enumerate(lines):
            for i, u in enumerate(us):
                for side in (-1, 1):
                    if side == 1:
                        clear = (us[i + 1] - u - posts.t) if i < n - 1 else (L - u - posts.t / 2)
                    else:
                        clear = (u - us[i - 1] - posts.t) if i > 0 else (u - posts.t / 2)
                    if clear < MIN_BRACE_CLEAR:
                        continue
                    leg = braces.leg_for(clear)
                    if H - braces.lowest(leg) < foot.seat - 0.05:
                        low = foot.seat + braces.lowest(leg)
                        raise SpecError(f"height: {H:g} mm is too low for 45 degree knee braces on these posts; "
                                        f"use at least {low:g} mm, a shorter brace_leg, or braces: false")
                    plan.append((k, pid[k * n + i], u + side * posts.t / 2, side, leg))
        clear = rs - pv
        if clear >= MIN_BRACE_CLEAR:
            leg = braces.leg_for(clear)
            if zb - braces.lowest(leg) < foot.seat - 0.05 or zb - (leg - braces.w * C45) > H + 0.05:
                raise SpecError(f"height: {H:g} mm does not fit 45 degree knee braces across the beams under the "
                                "rafters; use a shorter brace_leg, a taller pergola, or braces: false")
            for k, v in enumerate(lines):
                for i, u in enumerate(us):
                    cross_plan.append((pid[k * n + i], u, v + (1 if k == 0 else -1) * pv / 2, 1 if k == 0 else -1, leg))
    for k, v in enumerate(lines):
        sup = [(u, pid[k * n + i]["id"]) for i, u in enumerate(us)]
        beam.place(v, 0.0, L, zb, sup, posts.w, trib, axis=ax.axis, prefix="beams")
    plies = [x for r in beam.records for x in r["plies"]]
    rafters = Rafters(fr, lib, ax, spec["rafter_item"], spec["rafter_spacing"]).build(L, Wd, zb, plies, lines, oh, rs, over=us)
    if spec["slats"] != "none":
        Slats(fr, lib, ax, spec["slats"]["item"], spec["slats"]["spacing"]).build(L, Wd, rafters.top, rafters.ids)
    for k, post, u_face, side, leg in plan:
        braces.add(lines[k], u_face, side, H, leg, post["id"], beam.records[k]["plies"])
    for post, u, vface, side, leg in cross_plan:
        rid = next(r for r in rafters.ids if abs(_centre(fr.member(r), ax.axis) - u) < 0.2 or
                   _centre(fr.member(r), ax.axis) - rt / 2 < u < _centre(fr.member(r), ax.axis) + rt / 2 + 0.2)
        braces.add(u, vface, side, zb, leg, post["id"], [rid], across=True, thick=rt)
    foot.buy()
    beam.buy()
    foot.assembly()
    posts.assembly()
    beam.assembly()
    braces.assembly()
    apply_edits(fr, spec)
    return result(fr, spec)


MIN_POST_LEN = 100.0           # mm, a post shorter than this is not worth cutting


def _even(lo, hi, max_gap):
    """Positions from lo to hi, evenly spaced and no more than max_gap apart (at least two)."""
    n = max(1, math.ceil((hi - lo) / max_gap - 1e-9))
    return [round(lo + (hi - lo) * i / n, 1) for i in range(n + 1)]
