"""The pergola (type "pergola"): footings, posts, two beams, rafters with an
overhang, slats and 45 degree knee braces; the open-bracing check and errors.

    .venv/bin/python -m pytest tests/test_pergola.py
"""
import copy, math

import numpy as np
import pytest

from test_frame import TOL, aabb, by_id, load_fixture, penetration
from test_framing import _touch
import bom
import frame as fr
import framecheck as fc

FIXTURES = ["pergola-eu", "pergola-us"]


@pytest.fixture(scope="module", params=FIXTURES)
def spec(request):
    return load_fixture(request.param)


@pytest.fixture(scope="module")
def perg(spec):
    return fr.generate(copy.deepcopy(spec))


def kind(f, k):
    return [m for m in f["members"] if m["kind"] == k]


def ext(m, ax):
    lo, hi = aabb(m)
    return float(lo[ax]), float(hi[ax])


def levels(f):
    return {x["id"]: x["level"] for x in fc.run(f)["findings"]}


def test_no_two_members_overlap(perg):
    mem = perg["members"]
    boxes = [aabb(m) for m in mem]
    bad = []
    for i, a in enumerate(mem):
        for j in range(i + 1, len(mem)):
            if np.any(np.minimum(boxes[i][1], boxes[j][1]) - np.maximum(boxes[i][0], boxes[j][0]) <= TOL):
                continue
            if penetration(a, mem[j]) > TOL:
                bad.append((a["id"], mem[j]["id"]))
    assert not bad, bad[:10]


def test_nothing_floats(perg):
    mem = perg["members"]
    alone = [a["id"] for i, a in enumerate(mem) if not any(j != i and _touch(a, mem[j]) for j in range(len(mem)))]
    assert not alone, alone[:8]
    assert levels(perg)["floating-piece"] == "ok"


def test_every_post_stands_on_a_footing(perg):
    posts, bases = kind(perg, "post"), kind(perg, "post-base")
    bodies = kind(perg, "ground-screw") + kind(perg, "pier") + kind(perg, "footing")
    assert len(posts) == len(bases) == len(bodies) >= 4
    joined = {(j["a"], j["b"]) for j in perg["joints"] if j["type"] == "post-base"}
    for p in posts:
        mine = [b for b in bases if (b["id"], p["id"]) in joined]
        assert len(mine) == 1
        assert ext(p, 2)[0] == pytest.approx(ext(mine[0], 2)[1], abs=TOL)
        assert ext(p, 2)[1] == pytest.approx(perg["spec"]["height"], abs=TOL)       # the beams' underside
        assert [w for w in bodies if _touch(mine[0], w, 0.5)]
    assert levels(perg)["post-footing"] == "ok"


def test_beams_lie_over_posts_on_the_long_sides(perg):
    s = perg["spec"]
    ax = 0 if s["beam_axis"] == "x" else 1
    assert s["beam_axis"] == ("x" if s["width"] >= s["depth"] else "y")
    posts, beams = kind(perg, "post"), kind(perg, "beam")
    recs = [x for a in perg["assemblies"] if a["type"] == "beams" for x in a["spans"]]
    assert len(recs) == 2 and len(beams) == len(recs) * s["beam_plies"]
    for m in beams:
        lo, hi = ext(m, ax)
        assert lo == pytest.approx(0, abs=TOL) and hi == pytest.approx(s["width"] if ax == 0 else s["depth"], abs=TOL)
        assert ext(m, 2)[0] == pytest.approx(s["height"], abs=TOL)                    # underside at height
        mine = [p for p in posts if _touch(m, p, 0.5)]
        assert len(mine) >= 3                                                          # corners and a middle post
        assert all(any(j["type"] == "beam-cap" and {j["a"], j["b"]} == {m["id"], p["id"]} for j in perg["joints"]) for p in mine)
    assert all(r["span_mm"] <= s["post_spacing"] + 0.5 for r in recs)
    assert levels(perg)["beam-bearing"] == "ok"
    lines = sorted({round(np.mean(ext(m, 1 - ax)), 0) for m in kind(perg, "beam") if m["id"].count("-ply") == 0})
    assert len(lines) == 2 and lines[0] < lines[1]


def test_rafters_lie_on_both_beams_with_the_overhang(perg):
    s = perg["spec"]
    ax = 0 if s["beam_axis"] == "x" else 1
    cross = 1 - ax
    across = s["depth"] if ax == 0 else s["width"]
    rafters, beams = kind(perg, "rafter"), kind(perg, "beam")
    assert rafters
    beam_lo = min(ext(b, cross)[0] for b in beams)
    beam_hi = max(ext(b, cross)[1] for b in beams)
    for r in rafters:
        assert ext(r, cross) == pytest.approx((0, across), abs=TOL)
        assert beam_lo - 0 == pytest.approx(s["overhang"], abs=TOL)                   # the overhang past the outer face
        assert across - beam_hi == pytest.approx(s["overhang"], abs=TOL)
        on = [b for b in beams if _touch(r, b, 0.5) and ext(b, 2)[1] == pytest.approx(ext(r, 2)[0], abs=TOL)]
        assert len(on) == len(beams)
        for b in beams:
            assert any(j["type"] == "rafter-beam" and {j["a"], j["b"]} == {r["id"], b["id"]} for j in perg["joints"])
    xs = sorted(ext(r, ax)[0] for r in rafters)
    assert all(b - a <= s["rafter_spacing"] + 0.5 for a, b in zip(xs, xs[1:]))
    assert levels(perg)["span-rafters"] == "ok"


def test_slats_lie_across_the_rafters(perg):
    s = perg["spec"]
    ax = 0 if s["beam_axis"] == "x" else 1
    slats, rafters = kind(perg, "slat"), kind(perg, "rafter")
    assert slats and s["slats"] != "none"
    top = max(ext(r, 2)[1] for r in rafters)
    for m in slats:
        assert ext(m, 2)[0] == pytest.approx(top, abs=TOL)
        assert all(_touch(m, r, 0.5) for r in rafters)
    assert max(ext(m, 2)[1] for m in perg["members"]) == pytest.approx(top + slats[0]["size"][2], abs=TOL)
    assert sum(1 for j in perg["joints"] if j["type"] == "slat-rafter") == len(slats) * len(rafters)
    assert ext(slats[0], ax) == pytest.approx((0, s["width"] if ax == 0 else s["depth"]), abs=TOL)


def test_a_knee_brace_at_every_post_beam_corner_at_45_degrees(perg):
    by = by_id(perg)
    braces, posts, beams = kind(perg, "brace"), kind(perg, "post"), kind(perg, "beam")
    s = perg["spec"]
    ax = 0 if s["beam_axis"] == "x" else 1
    assert braces
    sides = {}
    for b in braces:
        assert b["cut_deg"] == [45, 45]
        x = np.array(b["x"], float)
        assert abs(x[2]) == pytest.approx(math.sqrt(0.5), abs=1e-6) and abs(x[ax]) == pytest.approx(math.sqrt(0.5), abs=1e-6)
        mine_p = [p for p in posts if _touch(b, p, 0.5)]
        mine_b = [m for m in beams if _touch(b, m, 0.5)]
        assert len(mine_p) == 1 and mine_b
        assert any(j["type"] == "brace-post" and {j["a"], j["b"]} == {b["id"], mine_p[0]["id"]} for j in perg["joints"])
        assert all(any(j["type"] == "brace-beam" and {j["a"], j["b"]} == {b["id"], m["id"]} for j in perg["joints"]) for m in mine_b)
        assert ext(b, 2)[1] == pytest.approx(s["height"], abs=TOL)                     # head on the beam's underside
        side = 1 if np.mean(ext(b, ax)) > np.mean(ext(mine_p[0], ax)) else -1
        sides.setdefault(mine_p[0]["id"], []).append(side)
    # every post has one brace toward the span; the middle posts have one on each side
    for p in posts:
        got = sorted(sides.get(p["id"], []))
        assert got in ([-1], [1], [-1, 1]), (p["id"], got)
    assert max(len(v) for v in sides.values()) == 2 and min(len(v) for v in sides.values()) == 1
    assert levels(perg)["open-bracing"] == "ok"


def test_removing_one_brace_trips_open_bracing(spec):
    f = fr.generate(copy.deepcopy(spec))
    gone = kind(f, "brace")[0]["id"]
    g = fr.generate(dict(copy.deepcopy(spec), edits=[{"op": "remove", "id": gone}]))
    assert gone not in by_id(g) and len(kind(g, "brace")) == len(kind(f, "brace")) - 1
    lv = levels(g)
    assert lv["open-bracing"] == "fix"
    item = next(x for x in fc.run(g)["findings"] if x["id"] == "open-bracing")
    assert "post-" in item["text"]


def test_no_braces_builds_and_trips_the_check(spec):
    g = fr.generate(dict(copy.deepcopy(spec), braces=False))
    assert not kind(g, "brace")
    assert levels(g)["open-bracing"] == "fix"
    assert levels(g)["floating-piece"] == "ok"


@pytest.mark.parametrize("name", FIXTURES)
def test_framecheck_on_the_fixtures_has_nothing_to_fix_or_check(name):
    import json
    f = fr.generate(load_fixture(name))
    bad = {x["id"]: x["level"] for x in fc.run(f)["findings"] if x["level"] != "ok"}
    assert not bad, bad
    assert fc.run(json.loads(fr.dumps(f))) == fc.run(f)


def test_shopping_list_covers_every_new_kind(perg):
    b = bom.make_bom(perg)
    assert b["problems"] == []
    text = str(b)
    for k in ("brace", "slat", "rafter", "post", "beam"):
        assert k in text.lower()
    assert any(x["item"] == "post-cap" for x in b["bought"])


def test_beam_axis_y_builds_the_same_structure_turned(spec):
    f = fr.generate(dict(copy.deepcopy(spec), width=spec["depth"] if spec.get("region") != "us" else 3000, depth=4000,
                         beam_axis="y"))
    assert f["spec"]["beam_axis"] == "y"
    assert "fix" not in levels(f).values()
    assert len(kind(f, "brace")) == 8


def test_long_spans_are_reported():
    f = fr.generate({"type": "pergola", "width": 6000, "depth": 4500, "post_spacing": 5400, "rafter_spacing": 900,
                     "rafter_item": "50x100"})
    lv = levels(f)
    assert any(v == "fix" for k, v in lv.items() if k.startswith("span-"))


def test_post_spacing_follows_the_beam_span_and_the_library_cap():
    s = fr.generate({"type": "pergola", "width": 6000, "depth": 3000})["spec"]
    assert s["post_spacing"] <= 2400
    assert len(kind(fr.generate({"type": "pergola", "width": 6000, "depth": 3000}), "post")) >= 8


@pytest.mark.parametrize("raw,field", [
    ({"type": "pergola", "depth": 3000}, "width"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "foundation": "slab"}, "foundation"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "beam_mount": "sandwich"}, "beam_mount"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "beam_axis": "z"}, "beam_axis"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "braces": "yes"}, "braces"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "slats": {"item": "50x50", "spacing": 20}}, "slats.spacing"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "slats": {"item": "nope"}}, "slats.item"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "overhang": 5000}, "overhang"),
    ({"type": "pergola", "width": 4000, "depth": 800}, "depth"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "height": 600}, "height"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "roofing": "x"}, "roofing"),
    ({"type": "pergola", "width": 4000, "depth": 3000, "loads": {"floor_kn_m2": 1}}, "loads.floor_kn_m2"),
])
def test_bad_descriptions_name_the_field(raw, field):
    with pytest.raises(fr.SpecError) as e:
        fr.generate(raw)
    assert str(e.value).startswith(field)
