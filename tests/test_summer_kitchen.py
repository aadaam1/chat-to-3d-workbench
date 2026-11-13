"""The summer kitchen (type "summer-kitchen"): footings, posts on a rectangle, a beam on each
long side, a mono or gable roof bearing on the beams, an optional terrace floor inside the
posts, up to three walls between the posts and knee braces on every open side.

    .venv/bin/python -m pytest tests/test_summer_kitchen.py
"""
import copy, itertools, math

import numpy as np
import pytest

from test_frame import TOL, aabb, by_id, load_fixture, penetration
from test_framing import _touch
import frame as fr
import framecheck as fc

FIXTURES = ["summer-kitchen-eu", "summer-kitchen-us"]


@pytest.fixture(scope="module", params=FIXTURES)
def spec(request):
    return load_fixture(request.param)


@pytest.fixture(scope="module")
def kit(spec):
    return fr.generate(copy.deepcopy(spec))


def kind(f, k):
    return [m for m in f["members"] if m["kind"] == k]


def ext(m, ax):
    lo, hi = aabb(m)
    return float(lo[ax]), float(hi[ax])


def levels(f):
    return {x["id"]: x["level"] for x in fc.run(f)["findings"]}


def overlaps(f):
    """Pairs of members that overlap, tested like the sheds' (a sloped rafter against plates and
    the roof only: the walls' infill studs are cut to it; a gable skin is notched under the ridge)."""
    mem = f["members"]
    boxes = [aabb(m) for m in mem]
    lo, hi = np.array([b[0] for b in boxes]), np.array([b[1] for b in boxes])
    meet = np.all(np.minimum(hi[:, None, :], hi[None, :, :]) - np.maximum(lo[:, None, :], lo[None, :, :]) > TOL, axis=2)
    bad = []
    for i, j in zip(*np.nonzero(np.triu(meet, 1))):
        a, b = mem[i], mem[j]
        if "rafter" in (a["kind"], b["kind"]):
            other = b if a["kind"] == "rafter" else a
            if not (other["kind"] == "plate" or other["group"] == "roof"):
                continue
        if f["spec"]["roof"] == "mono" and any("/infill-" in x["id"] for x in (a, b)) and "roof" in (a["group"], b["group"]):
            continue                       # a mono side wall's infill studs are cut to the roof line (their boxes are not)
        if "roof/ridge" in (a["id"], b["id"]) and {a["kind"], b["kind"]} & {"sheet", "board"}:
            continue
        if penetration(a, b) > TOL:
            bad.append((a["id"], b["id"]))
    return bad


def floats(f):
    mem = f["members"]
    boxes = [aabb(m) for m in mem]
    lo, hi = np.array([b[0] for b in boxes]) - 1.0, np.array([b[1] for b in boxes]) + 1.0
    near = np.all((lo[:, None, :] <= hi[None, :, :]) & (hi[:, None, :] >= lo[None, :, :]), axis=2)
    return [a["id"] for i, a in enumerate(mem)
            if not any(j != i and near[i, j] and _touch(a, mem[j]) for j in range(len(mem)))]


def post_dims(f):
    p = kind(f, "post")[0]
    return ext(p, 0)[1] - ext(p, 0)[0], ext(p, 1)[1] - ext(p, 1)[0]


# ------------------------------------------------------------------ the two fixtures

def test_fixtures_have_no_fix_and_no_check(kit):
    bad = [(x["id"], x["level"]) for x in fc.run(kit)["findings"] if x["level"] != "ok"]
    assert not bad, bad


def test_no_two_members_overlap(kit):
    assert not overlaps(kit)


def test_nothing_floats(kit):
    assert not floats(kit)
    assert levels(kit)["floating-piece"] == "ok"


def test_the_checks_read_through_a_json_round_trip(kit):
    import json
    again = json.loads(fr.dumps(kit))
    assert fc.run(again) == fc.run(kit)


def test_every_post_stands_on_a_footing(kit):
    posts, bases = kind(kit, "post"), kind(kit, "post-base")
    bodies = kind(kit, "ground-screw") + kind(kit, "pier") + kind(kit, "footing")
    assert len(posts) == len([p for p in posts if p["id"].startswith("posts/")]) + len(
        [p for p in posts if p["id"].startswith("floor-posts/")])
    assert len(bases) == len(bodies) >= len(posts)
    joined = {(j["a"], j["b"]) for j in kit["joints"] if j["type"] == "post-base"}
    for p in posts:
        mine = [b for b in bases if (b["id"], p["id"]) in joined]
        assert len(mine) == 1, p["id"]
        assert ext(p, 2)[0] == pytest.approx(ext(mine[0], 2)[1], abs=TOL)
        assert [w for w in bodies if _touch(mine[0], w, 0.5)]
    assert levels(kit)["post-footing"] == "ok"


def test_the_roof_bears_on_the_beams(kit):
    s = kit["spec"]
    beams = [m for m in kind(kit, "beam") if m["id"].startswith("beams/")]
    assert len(beams) == 2 * s["beam_plies"]
    joints = {(j["type"], j["a"], j["b"]) for j in kit["joints"]}
    assert not [j for j in kit["joints"] if j["type"] == "rafter-plate"]          # no wall plate carries the roof
    roof_posts = [p for p in kind(kit, "post") if p["id"].startswith("posts/")]
    zmax = max(ext(b, 2)[1] for b in beams)
    rafters = [m for m in kind(kit, "rafter") if "flying" not in m["id"]]
    assert rafters
    for r in rafters:
        # a mono rafter touches both beams; a gable rafter its own eave's beam, and is fixed to every ply of it
        want = beams if s["roof"] == "mono" else [b for b in beams if (ext(b, 1)[0] < s["depth"] / 2) == ("-front-" in r["id"])]
        on = [b for b in beams if _touch(r, b, 0.5)]
        # (line contact on the edge of the beam nearer the rafter's span: a ply further from it can be a few mm clear)
        assert on and {b["id"] for b in on} <= {b["id"] for b in want}, r["id"]
        for line in {b["id"].split("-ply")[0] for b in want}:
            assert any(b["id"].split("-ply")[0] == line for b in on), r["id"]
        for b in want:
            assert ("rafter-beam", r["id"], b["id"]) in joints
    # the rafters and the roof sit above the beams' tops, nothing of the roof reaches into a beam
    for m in kit["members"]:
        if m["group"] == "roof" and m["kind"] in ("rafter", "tie", "ridge", "blocking", "sheet"):
            assert ext(m, 2)[0] >= min(ext(b, 2)[0] for b in beams) - TOL
    for b in beams:                                                                    # the beams rest on the posts
        assert any(abs(ext(p, 2)[1] - ext(b, 2)[0]) <= TOL and _touch(p, b, 0.5) for p in roof_posts)
    assert levels(kit)["span-beams-beam-01"] == "ok" and levels(kit)["span-beams-beam-02"] == "ok"
    assert levels(kit)["beam-bearing"] == "ok"
    if s["roof"] == "mono":                                                            # the front beam is the higher one
        f1 = max(ext(b, 2)[0] for b in beams if ext(b, 1)[1] < s["depth"] / 2)
        f2 = max(ext(b, 2)[0] for b in beams if ext(b, 1)[0] > s["depth"] / 2)
        assert f1 > f2 + 100
        assert math.degrees(math.atan((f1 - f2) / (s["depth"] - post_dims(kit)[1]))) == pytest.approx(s["pitch_deg"], abs=0.05)
    else:
        ties = kind(kit, "tie")
        assert ties
        for t in ties:
            assert ext(t, 2)[0] == pytest.approx(zmax, abs=TOL)                        # full-length ceiling joists on the beams
            assert ext(t, 1) == pytest.approx((0, s["depth"]), abs=TOL)
            assert all(_touch(t, b, 0.5) for b in beams)
        assert levels(kit)["rafter-ties"] == "ok" and levels(kit)["ridge"] == "ok"


def test_posts_on_a_rectangle_with_intermediates_so_the_beams_pass(kit):
    s = kit["spec"]
    posts = [p for p in kind(kit, "post") if p["id"].startswith("posts/")]
    ptx, pty = post_dims(kit)
    xs = sorted({round(ext(p, 0)[0], 1) for p in posts})
    assert xs[0] == pytest.approx(0, abs=TOL) and xs[-1] + ptx == pytest.approx(s["width"], abs=TOL)
    assert len(xs) >= 3
    assert all(b - a <= s["post_spacing"] + 0.5 for a, b in zip(xs, xs[1:]))
    rows = sorted({round(ext(p, 1)[0], 1) for p in posts})
    assert rows[0] == pytest.approx(0, abs=TOL) and rows[1] + pty == pytest.approx(s["depth"], abs=TOL)
    assert len(posts) == 2 * len(xs)


def test_walls_fit_between_the_posts_and_touch_the_beam_above(kit):
    s = kit["spec"]
    posts = [p for p in kind(kit, "post") if p["id"].startswith("posts/")]
    beams = [m for m in kind(kit, "beam") if m["id"].startswith("beams/")]
    tops = [m for m in kit["members"] if m["kind"] == "plate" and m["id"].endswith(("plate-top-2", "plate-top"))
            and m["id"].count("plate-top") == 1 and (m["id"].endswith("plate-top-2")
                                                      or not any(x["id"] == m["id"] + "-2" for x in kit["members"]))]
    assert tops
    ptx, pty = post_dims(kit)
    for t in tops:
        side = t["group"].split("-")[-1]
        along = 0 if side == "back" else 1
        lo, hi = ext(t, along)
        mine = [p for p in posts if _touch(t, p, 0.5)]
        assert len(mine) == 2, t["id"]                                                  # between exactly two posts
        assert not [p for p in posts if penetration(t, p) > TOL]
        face = [(ext(p, along)[1] if ext(p, along)[1] <= lo + TOL else ext(p, along)[0]) for p in mine]
        assert sorted(face) == pytest.approx(sorted([lo, hi]), abs=TOL)
        if side == "back":
            above = [b for b in beams if _touch(t, b, 0.5) and ext(b, 2)[0] == pytest.approx(ext(t, 2)[1], abs=TOL)]
            assert len(above) == s["beam_plies"], t["id"]                               # under the roof beam
    walled = {w["side"] for w in s["walls"]}
    assert {t["group"].split("-")[-1] for t in tops} == walled
    # the inner face of each wall is flush with the posts' inner face
    for t in tops:
        side = t["group"].split("-")[-1]
        if side == "back":
            assert ext(t, 1)[0] == pytest.approx(s["depth"] - pty, abs=TOL)
        elif side == "left":
            assert ext(t, 0)[1] == pytest.approx(ptx, abs=TOL)
        else:
            assert ext(t, 0)[0] == pytest.approx(s["width"] - ptx, abs=TOL)
    # the bottom plates stand on a sole plate that is bolted to the posts
    sills = [m for m in kind(kit, "sill") if m["id"].startswith("sole/")]
    assert len(sills) == len(tops)
    for sl in sills:
        assert len([p for p in posts if _touch(sl, p, 0.5)]) == 2
        assert sl["treated"]
    assert levels(kit)["wall-bracing"] == "ok" and levels(kit)["opening-frame"] == "ok"


def test_the_floor_stands_on_its_own_supports(kit):
    s = kit["spec"]
    deck = [m for m in kit["members"] if m["group"] == "deck"]
    if s["floor"] != "terrace":
        assert not deck
        assert not [m for m in kit["members"] if m["id"].startswith(("floor-", "deck/"))]
        return
    ptx, pty = post_dims(kit)
    roof_posts = [p for p in kind(kit, "post") if p["id"].startswith("posts/")]
    floor_foot = [m for m in kit["members"] if m["id"].startswith("floor-foundations/")]
    floor_beams = [m for m in kind(kit, "beam") if m["id"].startswith("floor-beams/")]
    assert floor_foot and floor_beams
    for m in deck:
        assert ext(m, 0)[0] >= ptx - TOL and ext(m, 0)[1] <= s["width"] - ptx + TOL
        assert ext(m, 1)[0] >= pty - TOL and ext(m, 1)[1] <= s["depth"] - pty + TOL
        assert not [p for p in roof_posts if penetration(m, p) > TOL]                  # nothing overlaps a post
    top = max(ext(m, 2)[1] for m in deck)
    assert top == pytest.approx(s["floor_height"], abs=TOL)
    joists = [m for m in deck if m["kind"] == "joist"]
    joined = {(j["a"], j["b"]) for j in kit["joints"] if j["type"] == "joist-beam"}
    for j in joists:
        assert len([b for b in floor_beams if (j["id"], b["id"]) in joined]) >= 2 * s["floor_beam_plies"]
    # the beams carry only the floor: nothing of the roof's posts or beams is shared
    assert not [b for b in floor_beams if any(_touch(b, p, 0.5) for p in roof_posts) and
                not any(p["id"].startswith("floor-posts/") for p in kind(kit, "post"))]
    for b in floor_beams:
        assert any(_touch(b, m, 0.5) for m in floor_foot + [p for p in kind(kit, "post") if p["id"].startswith("floor-posts/")])
    lv = levels(kit)
    assert lv["span-joists"] == lv["floor-beam-bearing"] == lv["deck-board-span"] == "ok"
    assert lv["railing"] in ("ok", "check")


def _post_lines(f):
    s = f["spec"]
    return {p["id"]: ("front" if ext(p, 1)[0] < s["depth"] / 2 else "back") for p in kind(f, "post")
            if p["id"].startswith("posts/")}


def test_knee_braces_on_the_open_sides_in_both_directions(kit):
    s = kit["spec"]
    posts = {p["id"]: p for p in kind(kit, "post") if p["id"].startswith("posts/")}
    line = _post_lines(kit)
    walled = {w["side"] for w in s["walls"]}
    along = [b for b in kind(kit, "brace") if "/brace-" in b["id"]]
    across = [b for b in kind(kit, "brace") if "/cross-" in b["id"]]
    assert along and across                                                            # both directions
    joints = {(j["type"], j["a"], j["b"]) for j in kit["joints"]}

    def post_of(b):
        mine = [p for p in posts.values() if _touch(b, p, 0.5)]
        assert len(mine) == 1, b["id"]
        return mine[0]

    for b in along:
        p = post_of(b)
        assert ("brace-post", b["id"], p["id"]) in joints
        assert b["cut_deg"] == [45, 45]
        assert line[p["id"]] == "front" or "back" not in walled                         # not on a walled back line
        beams = [m for m in kind(kit, "beam") if m["id"].startswith("beams/") and _touch(b, m, 0.5)]
        assert beams and all(("brace-beam", b["id"], m["id"]) in joints for m in beams)
    for b in across:
        p = post_of(b)
        assert ("brace-post", b["id"], p["id"]) in joints
        rafters = [r for r in kind(kit, "rafter") if _touch(b, r, 0.5)]
        assert rafters and any(("brace-rafter", b["id"], r["id"]) in joints for r in rafters)
        ex = ext(p, 0)
        corner = ex[0] <= TOL or ex[1] >= s["width"] - TOL
        assert not (corner and ("left" in walled and ex[0] <= TOL or "right" in walled and ex[1] >= s["width"] - TOL))
        # toward the middle: a front post's brace runs to +Y, a back post's to -Y
        assert (np.mean(ext(b, 1)) > np.mean(ext(p, 1))) == (line[p["id"]] == "front")
        assert ext(b, 2)[0] >= ext(p, 2)[0] - TOL
    # every post that should have one has one
    for pid, p in posts.items():
        ex = ext(p, 0)
        exempt = (ex[0] <= TOL and "left" in walled) or (ex[1] >= s["width"] - TOL and "right" in walled)
        mine = [b for b in across if post_of(b)["id"] == pid]
        assert bool(mine) == (not exempt), pid
    assert levels(kit)["open-bracing"] == "ok"


# ------------------------------------------------------------------ variants

BASE = {"type": "summer-kitchen", "width": 4000, "depth": 3000, "height_eaves": 2400}


def variant(roof, walls, floor, **kw):
    d = dict(BASE, roof=roof, walls=[{"side": w} for w in walls], floor=floor, **kw)
    if floor == "terrace":
        d.setdefault("floor_height", 600)
    return d


VARIANTS = [(roof, walls, floor) for roof, walls, floor in itertools.product(
    ("mono", "gable"), ([], ["back"], ["back", "left", "right"]), ("none", "terrace"))]


@pytest.mark.parametrize("roof,walls,floor", VARIANTS)
def test_variants_build_clean(roof, walls, floor):
    f = fr.generate(variant(roof, walls, floor))
    assert not overlaps(f), (roof, walls, floor)
    assert not floats(f)
    bad = [(x["id"], x["level"]) for x in fc.run(f)["findings"] if x["level"] != "ok"]
    assert not bad, bad
    walled = {w["side"] for w in f["spec"]["walls"]}
    got = {m["group"].split("-")[-1] for m in f["members"] if m["group"].startswith("wall-")}
    assert got == walled
    if roof == "mono":                                  # posts of two lengths
        tops = {round(ext(p, 2)[1], 1) for p in kind(f, "post") if p["id"].startswith("posts/")}
        assert len(tops) == 2


def test_a_side_with_a_wall_needs_no_brace_and_an_open_one_does():
    open_ = fr.generate(variant("gable", [], "none"))
    walled = fr.generate(variant("gable", ["back", "left", "right"], "none"))
    a_open = [b for b in kind(open_, "brace") if "/brace-" in b["id"]]
    a_wall = [b for b in kind(walled, "brace") if "/brace-" in b["id"]]
    c_open = [b for b in kind(open_, "brace") if "/cross-" in b["id"]]
    c_wall = [b for b in kind(walled, "brace") if "/cross-" in b["id"]]
    assert len(a_open) > len(a_wall) > 0                 # the front line keeps its braces, the back line has a wall
    assert len(c_open) > len(c_wall) > 0                 # the middle posts keep theirs, the corner posts have a wall
    assert levels(open_)["open-bracing"] == levels(walled)["open-bracing"] == "ok"
    # take a brace away: the check names it
    broken = copy.deepcopy(walled)
    gone = a_wall[0]["id"]
    broken["members"] = [m for m in broken["members"] if m["id"] != gone]
    broken["joints"] = [j for j in broken["joints"] if gone not in (j["a"], j["b"])]
    assert levels(broken)["open-bracing"] == "fix"


def test_braces_can_be_turned_off_but_the_check_notices():
    f = fr.generate(variant("mono", ["back"], "none", braces=False))
    assert not kind(f, "brace")
    assert levels(f)["open-bracing"] == "fix"
    f = fr.generate(variant("mono", ["back", "left", "right"], "none", braces=False))
    assert levels(f)["open-bracing"] == "fix"            # the front line and the middle posts are still open


def test_the_roof_height_fields():
    f = fr.generate(variant("gable", [], "none", pitch_deg=30))
    assert f["spec"]["pitch_deg"] == 30
    g = fr.generate(dict(variant("gable", [], "none"), height_ridge=3200))
    assert levels(g)["ridge"] == "ok"
    ridge = by_id(g)["roof/ridge"]
    assert ext(ridge, 2)[1] == pytest.approx(3200, abs=20)
    m = fr.generate(dict(variant("mono", [], "none"), height_front=2900, height_back=2400))
    assert m["spec"]["height_front"] == 2900 and m["spec"]["height_back"] == 2400
    with pytest.raises(fr.SpecError, match="pitch_deg"):
        fr.generate(dict(variant("mono", [], "none"), height_front=2900, pitch_deg=10))


def test_a_beam_span_that_is_too_long_is_flagged():
    f = fr.generate(variant("gable", [], "none", post_spacing=3900, beam_plies=1, depth=5000))
    assert levels(f)["span-beams-beam-01"] in ("check", "fix")


@pytest.mark.parametrize("raw,field", [
    ({"walls": ["front"]}, "walls[0].side"),
    ({"walls": ["back", "back"]}, "walls[1].side"),
    ({"roof": "flat"}, "roof"),
    ({"floor": "slab"}, "floor"),
    ({"floor_height": 400}, "floor_height"),
    ({"floor": "terrace", "floor_height": 200}, "floor_height"),
    ({"height_ridge": 3000, "roof": "mono"}, "height_ridge"),
    ({"height_front": 3000}, "height_front"),
    ({"nonsense": 1}, "nonsense"),
    ({"foundation": "slab"}, "foundation"),
    ({"beam_item": "50x200", "beam_plies": 2, "post_item": "75x75"}, "beam_item"),
    ({"walls": [{"side": "back", "openings": [{"kind": "window", "x": 1850, "sill": 900, "width": 300, "height": 500}]}]},
     "walls[0].openings[0].x"),
])
def test_bad_descriptions_name_the_field(raw, field):
    with pytest.raises(fr.SpecError) as e:
        fr.generate(dict(BASE, **raw))
    assert str(e.value).startswith(field), str(e.value)


def test_an_opening_must_lie_between_two_posts():
    raw = dict(variant("gable", ["back"], "none"))
    raw["walls"] = [{"side": "back", "openings": [{"kind": "window", "x": 1500, "sill": 900, "width": 1000, "height": 600}]}]
    with pytest.raises(fr.SpecError, match="between two posts"):
        fr.generate(raw)


def test_a_door_in_a_side_wall():
    raw = variant("mono", ["right"], "none")
    raw["walls"] = [{"side": "right", "openings": [{"kind": "door", "x": 1000, "width": 900, "height": 1800}]}]
    f = fr.generate(raw)
    assert not overlaps(f) and not floats(f)
    assert levels(f)["opening-frame"] == "ok"
    assert any(b["item"] == "door" for b in f["bought"])


def test_the_floor_height_has_a_floor():
    with pytest.raises(fr.SpecError, match="too low"):
        fr.generate(variant("gable", [], "terrace", floor_height=300))


def test_edits_and_the_checks_after_an_edit():
    d = variant("gable", ["back"], "none")
    f0 = fr.generate(d)
    post = kind(f0, "post")[0]["id"]
    d["edits"] = [{"op": "remove", "id": post}]
    f1 = fr.generate(d)
    assert post not in by_id(f1)
    assert levels(f1)["post-footing"] == "fix" or levels(f1)["beam-bearing"] == "fix" or levels(f1)["floating-piece"] != "ok" \
        or levels(f1)["open-bracing"] == "fix"


@pytest.mark.parametrize("kw", [{"foundation": "pier_block", "floor": "terrace"},
                                {"foundation": "concrete_footing", "floor": "terrace", "walls": ["back"]},
                                {"beam_plies": 1}, {"roof": "mono", "overhang_side": 0}])
def test_other_footings_plies_and_overhangs_build_clean(kw):
    raw = dict(BASE, width=5000, depth=3500, **kw)
    if raw.get("floor") == "terrace":
        raw["floor_height"] = 600
    raw["walls"] = [{"side": w} for w in raw.get("walls", [])]
    f = fr.generate(raw)
    assert not overlaps(f) and not floats(f)
    assert [x["id"] for x in fc.run(f)["findings"] if x["level"] == "fix"] == []
    if "floor" in kw:                          # the floor's footings clear the posts' footings
        feet = [m for m in f["members"] if m["kind"] in ("pier", "footing") and m["id"].startswith("floor-")]
        roof = [m for m in f["members"] if m["kind"] in ("pier", "footing") and not m["id"].startswith("floor-")]
        assert feet and roof and not [(a["id"], b["id"]) for a in feet for b in roof if penetration(a, b) > TOL]
