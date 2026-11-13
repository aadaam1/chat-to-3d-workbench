"""The terrace (type "terrace") and a shed's optional foundation: geometry, the
blocks they are made of (footings, posts, beams, a board deck), checks and errors.

    .venv/bin/python -m pytest tests/test_terrace.py
"""
import copy, json

import numpy as np
import pytest

from test_frame import TOL, aabb, by_id, load_fixture, penetration
from test_framing import _touch
import bom
import frame as fr
import framecheck as fc
import timberlib as tl

FIXTURES = ["terrace-eu", "terrace-us"]
FOUNDATIONS = ["ground_screw", "pier_block", "concrete_footing"]


@pytest.fixture(scope="module", params=FIXTURES)
def spec(request):
    return load_fixture(request.param)


@pytest.fixture(scope="module")
def terrace(spec):
    return fr.generate(copy.deepcopy(spec))


def kind(f, k):
    return [m for m in f["members"] if m["kind"] == k]


def ext(m, ax):
    lo, hi = aabb(m)
    return float(lo[ax]), float(hi[ax])


def levels(f):
    return {x["id"]: x["level"] for x in fc.run(f)["findings"]}


def test_no_two_members_overlap(terrace):
    mem = terrace["members"]
    boxes = [aabb(m) for m in mem]
    bad = []
    for i, a in enumerate(mem):
        for j in range(i + 1, len(mem)):
            if np.any(np.minimum(boxes[i][1], boxes[j][1]) - np.maximum(boxes[i][0], boxes[j][0]) <= TOL):
                continue
            if penetration(a, mem[j]) > TOL:
                bad.append((a["id"], mem[j]["id"]))
    assert not bad, bad[:10]


def test_nothing_floats(terrace):
    mem = terrace["members"]
    alone = [a["id"] for i, a in enumerate(mem) if not any(j != i and _touch(a, mem[j]) for j in range(len(mem)))]
    assert not alone, alone[:8]
    assert levels(terrace)["floating-piece"] == "ok"


def test_ground_is_zero_and_the_deck_top_is_the_height(terrace):
    top = max(ext(m, 2)[1] for m in terrace["members"])
    assert top == pytest.approx(terrace["spec"]["height"], abs=TOL)
    posts = kind(terrace, "post")
    base_tops = sorted({round(ext(m, 2)[1], 1) for m in kind(terrace, "post-base")})
    assert len(base_tops) == 1 and base_tops[0] > 0       # all bases at one height, above the ground
    for b in kind(terrace, "ground-screw") + kind(terrace, "pier") + kind(terrace, "footing"):
        assert ext(b, 2)[0] < 0 and ext(b, 2)[1] >= 0     # the body goes into the ground
    assert posts


def test_every_post_stands_on_a_footing(terrace):
    by = by_id(terrace)
    posts = kind(terrace, "post")
    joined = {(j["a"], j["b"]) for j in terrace["joints"] if j["type"] == "post-base"}
    bodies = kind(terrace, "ground-screw") + kind(terrace, "pier") + kind(terrace, "footing")
    assert len(posts) == len(bodies) == len(kind(terrace, "post-base"))
    for p in posts:
        bases = [b for b in kind(terrace, "post-base") if (b["id"], p["id"]) in joined]
        assert len(bases) == 1, p["id"]
        b = bases[0]
        assert ext(p, 2)[0] == pytest.approx(ext(b, 2)[1], abs=TOL)          # the post stands on its base
        assert [w for w in bodies if _touch(b, w, 0.5) and ext(w, 2)[1] == pytest.approx(ext(b, 2)[0], abs=TOL)]
        cx, cy = (np.mean(ext(p, a)) for a in (0, 1))
        assert abs(cx - np.mean(ext(b, 0))) < TOL and abs(cy - np.mean(ext(b, 1))) < TOL
    assert levels(terrace)["post-footing"] == "ok"


def test_beams_lie_over_posts(terrace):
    by = by_id(terrace)
    posts = kind(terrace, "post")
    s = terrace["spec"]
    beams = [m for m in kind(terrace, "beam")]
    recs = [x for a in terrace["assemblies"] if a["type"] == "beams" for x in a["spans"]]
    assert len(beams) == 2 * len(recs) and len(recs) >= 2                              # two plies per row
    for m in beams:
        lo, hi = ext(m, 0)
        assert lo == pytest.approx(0, abs=TOL) and hi == pytest.approx(s["width"], abs=TOL)
        mine = [p for p in posts if _touch(m, p, 0.5)]
        assert len(mine) >= 2, m["id"]
        assert min(np.mean(ext(p, 0)) for p in mine) - lo <= 300 and hi - max(np.mean(ext(p, 0)) for p in mine) <= 300
        # joints: bolted to each post it touches
        for p in mine:
            assert any(j["type"] == "beam-post" and {j["a"], j["b"]} == {m["id"], p["id"]} for j in terrace["joints"])
        # beam top meets the joists' underside
        assert ext(m, 2)[1] == pytest.approx(min(ext(j, 2)[0] for j in kind(terrace, "joist")), abs=TOL)
    assert levels(terrace)["beam-bearing"] == "ok"
    gaps = [x for a in terrace["assemblies"] if a["type"] == "beams" for x in a["spans"]]
    assert all(g["span_mm"] <= s["post_spacing"] + 0.5 for g in gaps)


def test_joists_lie_on_the_beams(terrace):
    s = terrace["spec"]
    joists, beams = kind(terrace, "joist"), kind(terrace, "beam")
    assert joists
    rows = sorted({round(np.mean(ext(m, 1)), 1) for m in beams})
    for j in joists:
        assert ext(j, 1) == pytest.approx((0, s["depth"]), abs=TOL)
        on = {round(np.mean(ext(b, 1)), 1) for b in beams if _touch(j, b, 0.5) and ext(b, 2)[1] == pytest.approx(ext(j, 2)[0], abs=TOL)}
        assert on == set(rows), j["id"]
        for b in beams:
            assert any(x["type"] == "joist-beam" and {x["a"], x["b"]} == {j["id"], b["id"]} for x in terrace["joints"])
    xs = sorted(ext(j, 0)[0] for j in joists)
    assert xs[0] == pytest.approx(0, abs=TOL) and ext(joists[-1], 0)[1] == pytest.approx(s["width"], abs=TOL)
    assert all(b - a <= s["joist_spacing"] + 0.5 for a, b in zip(xs, xs[1:]))


def test_boards_cover_the_deck_with_the_gap(terrace):
    s = terrace["spec"]
    boards = kind(terrace, "deckboard")
    rows = {}
    for m in boards:
        rows.setdefault(round(ext(m, 1)[0], 1), []).append(m)
    ys = sorted(rows)
    assert ys[0] == pytest.approx(0, abs=TOL)
    last = max(ext(m, 1)[1] for m in boards)
    assert last == pytest.approx(s["depth"], abs=TOL)
    for a, b in zip(ys, ys[1:]):
        gap = b - ext(rows[a][0], 1)[1]
        assert s["board_gap"] - TOL <= gap <= 8.0 + TOL, (a, gap)     # the gap, spread a little at most
    for y, ms in rows.items():
        ms.sort(key=lambda m: ext(m, 0)[0])
        assert ext(ms[0], 0)[0] == pytest.approx(0, abs=TOL) and ext(ms[-1], 0)[1] == pytest.approx(s["width"], abs=TOL)
    top = max(ext(m, 2)[1] for m in boards)
    assert top == pytest.approx(s["height"], abs=TOL)
    # every board crosses joists and has two screws at each crossing
    n_cross = sum(1 for j in terrace["joints"] if j["type"] == "deck-board")
    assert n_cross >= len(boards) * 2
    assert levels(terrace)["deck-board-span"] == "ok"


def test_long_boards_are_cut_on_joists_and_staggered():
    f = fr.generate({"type": "terrace", "width": 6500, "depth": 2500, "height": 600})
    stock = max(tl.item(tl.load("eu"), f["spec"]["deck_board"])["stock_lengths_mm"])
    joists = kind(f, "joist")
    rows = {}
    for m in kind(f, "deckboard"):
        rows.setdefault(round(ext(m, 1)[0], 1), []).append(m)
    ends = set()
    for ms in rows.values():
        ms.sort(key=lambda m: ext(m, 0)[0])
        assert all(m["size"][0] <= stock + 0.5 for m in ms)
        for a, b in zip(ms, ms[1:]):
            e = ext(a, 0)[1]
            assert [j for j in joists if ext(j, 0)[0] < e + 0.5 and ext(j, 0)[1] > e - 0.5], "a butt joint off the joists"
            ends.add(round(e, 0))
    assert len(ends) > 1, "joints are not staggered"
    assert levels(f).get("stock-length") == "ok"


@pytest.mark.parametrize("region", ["eu", "us"])
@pytest.mark.parametrize("foundation", FOUNDATIONS)
def test_each_foundation_builds_and_checks_clean(region, foundation):
    f = fr.generate({"type": "terrace", "region": region, "width": 3000, "depth": 2400, "height": 650,
                     "foundation": foundation})
    lv = levels(f)
    assert "fix" not in lv.values(), {k: v for k, v in lv.items() if v == "fix"}
    kinds = {"ground_screw": "ground-screw", "pier_block": "pier", "concrete_footing": "footing"}
    assert len(kind(f, kinds[foundation])) == len(kind(f, "post"))
    lib = tl.load(region)
    items = {b["item"]: b for b in f["bought"]}
    foot = [k for k, b in items.items() if lib["bought"][k].get("foundation", {}).get("kind") == foundation]
    assert len(foot) == 1 and items[foot[0]]["qty"] == len(kind(f, "post"))
    assert items[lib["bought"][foot[0]]["foundation"]["base"]]["qty"] == len(kind(f, "post"))
    b = bom.make_bom(f)
    assert b["problems"] == []
    assert any(x["item"] == foot[0] for x in b["bought"])


@pytest.mark.parametrize("foundation", FOUNDATIONS)
def test_every_foundation_has_a_working_post_base(foundation):
    f = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 650, "foundation": foundation})
    assert levels(f)["post-footing"] == "ok"
    z = {round(ext(p, 2)[0], 1) for p in kind(f, "post")}
    assert len(z) == 1


def test_a_low_terrace_has_beams_on_the_post_bases_and_no_posts():
    f = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 560, "beam_plies": 2,
                     "beam_mount": "on_top", "foundation": "pier_block"})
    assert not kind(f, "post")
    bases = kind(f, "post-base")
    assert bases
    lv = levels(f)
    assert "fix" not in lv.values() and lv["post-footing"] == "ok" and lv["beam-bearing"] == "ok"
    for m in kind(f, "beam"):
        assert [b for b in bases if _touch(b, m, 0.5) and ext(b, 2)[1] == pytest.approx(ext(m, 2)[0], abs=TOL)]
    assert max(ext(m, 2)[1] for m in f["members"]) == pytest.approx(560, abs=TOL)
    gen = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 560, "foundation": "pier_block"})
    assert kind(gen, "post")                  # a sandwich beam keeps a short post (222 mm) where it fits


def test_on_top_beams_get_post_caps():
    f = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 700, "beam_mount": "on_top"})
    caps = [b for b in f["bought"] if b["item"] == "post-cap"]
    assert caps and caps[0]["qty"] == len(kind(f, "post"))
    assert any(j["type"] == "beam-cap" for j in f["joints"]) and any(j["type"] == "beam-ply" for j in f["joints"])
    assert levels(f)["post-footing"] == "ok" and levels(f)["beam-bearing"] == "ok"


@pytest.mark.parametrize("name", FIXTURES)
def test_framecheck_on_the_fixtures_has_nothing_to_fix_or_check(name):
    f = fr.generate(load_fixture(name))
    bad = {x["id"]: x["level"] for x in fc.run(f)["findings"] if x["level"] != "ok"}
    assert not bad, bad
    f2 = json.loads(fr.dumps(f))
    assert fc.run(f2) == fc.run(f)


def test_a_terrace_over_600_mm_needs_a_railing():
    f = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 900})
    assert levels(f)["railing"] == "check"
    f = fr.generate({"type": "terrace", "region": "us", "width": 3000, "depth": 2400, "height": 900})
    assert levels(f)["railing"] == "check"
    assert levels(fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 600}))["railing"] == "ok"


def test_a_missing_footing_or_beam_support_is_a_fix():
    f = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 700})
    drop = kind(f, "post-base")[0]["id"]
    g = copy.deepcopy(f)
    g["members"] = [m for m in g["members"] if m["id"] != drop]
    g["joints"] = [j for j in g["joints"] if drop not in (j["a"], j["b"])]
    assert levels(g)["post-footing"] == "fix"
    g = copy.deepcopy(f)
    g["members"] = [m for m in g["members"] if m["kind"] not in ("post", "post-base")]
    g["joints"] = [j for j in g["joints"] if j["type"] not in ("beam-post",)]
    assert levels(g)["beam-bearing"] == "fix"


def test_too_long_spans_are_reported():
    f = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 600,
                     "row_spacing": 2400, "post_spacing": 3000, "beam_plies": 2, "beam_item": "50x100",
                     "joist_item": "50x100", "joist_spacing": 500})
    lv = levels(f)
    assert "fix" in lv.values() or "check" in lv.values()
    assert any(v == "fix" for k, v in lv.items() if k.startswith("span-"))


def test_spacings_follow_the_span_formulas_and_the_library_caps():
    eu = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 600})["spec"]
    t = tl.load("eu")["defaults"]["terrace"]
    assert eu["row_spacing"] <= t["max_row_spacing_mm"] and eu["post_spacing"] <= t["max_post_spacing_mm"]
    assert eu["joist_spacing"] == 500 and eu["board_gap"] == 5
    sp = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 600, "row_spacing": 900,
                      "post_spacing": 1000})["spec"]
    assert (sp["row_spacing"], sp["post_spacing"]) == (900, 1000)


@pytest.mark.parametrize("raw,field", [
    ({"type": "terrace", "width": 3000, "depth": 2400}, "height"),
    ({"type": "terrace", "width": 3000, "depth": 2400, "height": 600, "foundation": "slab"}, "foundation"),
    ({"type": "terrace", "width": 3000, "depth": 2400, "height": 600, "deck_board": "50x100"}, "deck_board"),
    ({"type": "terrace", "width": 3000, "depth": 2400, "height": 600, "beam_mount": "hang"}, "beam_mount"),
    ({"type": "terrace", "width": 3000, "depth": 2400, "height": 600, "beam_plies": 1, "beam_mount": "sandwich"}, "beam_mount"),
    ({"type": "terrace", "width": 3000, "depth": 2400, "height": 600, "footing_item": "pier-block-300"}, "footing_item"),
    ({"type": "terrace", "width": 3000, "depth": 2400, "height": 600, "roofing": "x"}, "roofing"),
    ({"type": "terrace", "width": 3000, "depth": 2400, "height": 100}, "height"),
    ({"type": "terrace", "width": 3000, "depth": 2400, "height": 200}, "height"),
    ({"type": "terrace", "width": 3000, "depth": 2400, "height": 600, "loads": {"snow_kn_m2": 1}}, "loads.snow_kn_m2"),
])
def test_bad_descriptions_name_the_field(raw, field):
    with pytest.raises(fr.SpecError) as e:
        fr.generate(raw)
    assert str(e.value).startswith(field)


def test_edits_work_on_a_terrace():
    base = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 600})
    gone = "deck/board-03"
    f = fr.generate({"type": "terrace", "width": 3000, "depth": 2400, "height": 600,
                     "edits": [{"op": "remove", "id": gone}]})
    assert gone not in by_id(f) and len(f["members"]) == len(base["members"]) - 1


# ------------------------------------------------------------ a shed on footings

@pytest.mark.parametrize("fixture", ["shed-eu", "shed-us", "gable-eu"])
@pytest.mark.parametrize("foundation", FOUNDATIONS)
def test_a_shed_on_footings_builds_and_passes_its_checks(fixture, foundation):
    spec = load_fixture(fixture)
    plain = fr.generate(copy.deepcopy(spec))
    spec["foundation"] = foundation
    f = fr.generate(spec)
    # the frame itself is untouched: only footings are added, below it
    old = {m["id"]: m for m in plain["members"]}
    new = by_id(f)
    assert all(new[i] == m for i, m in old.items())
    extra = [m for m in f["members"] if m["id"] not in old]
    assert extra and all(m["layer"] == "foundations" for m in extra)
    rims = [m for m in f["members"] if m["kind"] == "rim"]
    for base in kind(f, "post-base"):
        assert ext(base, 2)[1] == pytest.approx(0, abs=TOL)                  # on the underside of the rims
        assert [r for r in rims if _touch(base, r, 0.5)], base["id"]
    assert len([j for j in f["joints"] if j["type"] == "post-base"]) == len(kind(f, "post-base"))
    assert f["assemblies"][-1]["id"] == "foundations"
    mem = f["members"]
    for i, a in enumerate(extra):
        for b in mem:
            if b is not a and b["id"] > a["id"] if b["layer"] == "foundations" else True:
                if b["id"] != a["id"] and np.all(np.minimum(aabb(a)[1], aabb(b)[1]) - np.maximum(aabb(a)[0], aabb(b)[0]) > TOL):
                    assert penetration(a, b) <= TOL, (a["id"], b["id"])
    lv_new, lv_old = levels(f), levels(plain)
    assert [k for k, v in lv_new.items() if v == "fix"] == [k for k, v in lv_old.items() if v == "fix"]
    assert lv_new["floating-piece"] == "ok"
    b = bom.make_bom(f)
    assert b["problems"] == [] and any(x["item"].startswith(("ground", "pier", "concrete")) for x in b["bought"])


def test_a_shed_without_a_foundation_is_unchanged_and_none_means_none():
    spec = load_fixture("shed-eu")
    a = fr.dumps(fr.generate(copy.deepcopy(spec)))
    assert fr.dumps(fr.generate(dict(spec, foundation="none"))) == a
    with pytest.raises(fr.SpecError) as e:
        fr.generate(dict(spec, footing_item="pier-block-300"))
    assert str(e.value).startswith("footing_item")
    with pytest.raises(fr.SpecError) as e:
        fr.generate(dict(spec, foundation="stilts"))
    assert str(e.value).startswith("foundation")
    f = fr.generate(dict(spec, foundation="pier_block", footing_spacing=1000))
    g = fr.generate(dict(spec, foundation="pier_block", footing_spacing=2000))
    assert len(kind(f, "pier")) > len(kind(g, "pier"))
