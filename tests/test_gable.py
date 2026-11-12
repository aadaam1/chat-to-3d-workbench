"""The gable shed (type "gable-shed"): geometry, carpentry rules, checks and errors.

    .venv/bin/python -m pytest tests/test_gable.py
"""
import copy, json, math, os

import numpy as np
import pytest

from test_frame import TOL, aabb, by_id, load_fixture, penetration
from test_framing import _touch
import frame as fr
import framecheck as fc
import timberlib as tl

FIXTURES = ["gable-eu", "gable-us"]


@pytest.fixture(scope="module", params=FIXTURES)
def gable(request):
    return fr.generate(load_fixture(request.param))


def ids(f, prefix):
    return [m for m in f["members"] if m["id"].startswith(prefix)]


def ext(m, ax):
    lo, hi = aabb(m)
    return float(lo[ax]), float(hi[ax])


def test_no_two_members_overlap(gable):
    mem = gable["members"]
    boxes = [aabb(m) for m in mem]
    bad = []
    for i, a in enumerate(mem):
        for j in range(i + 1, len(mem)):
            b = mem[j]
            if np.any(np.minimum(boxes[i][1], boxes[j][1]) - np.maximum(boxes[i][0], boxes[j][0]) <= TOL):
                continue
            if "roof/ridge" in (a["id"], b["id"]) and {a["kind"], b["kind"]} & {"sheet", "board"} \
                    and {a["layer"], b["layer"]} & {"sheathing", "cladding"}:
                continue          # the gable skin is notched under the ridge; the test takes a notched sheet as its hull
            if "rafter" in (a["kind"], b["kind"]):
                other = b if a["kind"] == "rafter" else a
                if not (other["kind"] == "plate" or other["group"] == "roof"):
                    continue
            if penetration(a, b) > TOL:
                bad.append((a["id"], b["id"], round(float(penetration(a, b)), 1)))
    assert not bad, bad[:10]


def test_every_member_touches_another_and_none_strays(gable):
    mem = gable["members"]
    boxes = [aabb(m) for m in mem]
    alone = [a["id"] for i, a in enumerate(mem)
             if not any(j != i and np.all(np.minimum(boxes[i][1], boxes[j][1]) - np.maximum(boxes[i][0], boxes[j][0]) >= -1.0)
                        and _touch(a, mem[j]) for j in range(len(mem)))]
    assert not alone, alone[:8]
    s, lib = gable["spec"], tl.load(gable["region"])
    tf = tl.item(lib, s["fascia_item"])["thickness_mm"]
    ex = s["overhang_side"] + tf + TOL
    ey = s["overhang"] + tf + TOL + 40            # a square-cut deck edge on the slope
    for m, (lo, hi) in zip(mem, boxes):
        assert lo[0] >= -ex and hi[0] <= s["width"] + ex, m["id"]
        assert lo[1] >= -ey and hi[1] <= s["depth"] + ey, m["id"]
        assert lo[2] >= -TOL, m["id"]


def test_symmetric_about_the_ridge(gable):
    D = gable["spec"]["depth"]
    for m in ids(gable, "roof/"):
        if "-front" in m["id"] and not m["id"].startswith("roof/fascia"):
            twin = by_id(gable)[m["id"].replace("-front", "-back")]
            (lo, hi), (tlo, thi) = aabb(m), aabb(twin)
            assert lo[1] == pytest.approx(D - thi[1], abs=0.3) and hi[1] == pytest.approx(D - tlo[1], abs=0.3), m["id"]
            assert lo[2] == pytest.approx(tlo[2], abs=0.3) and hi[2] == pytest.approx(thi[2], abs=0.3), m["id"]
            assert lo[0] == pytest.approx(tlo[0], abs=0.3) and hi[0] == pytest.approx(thi[0], abs=0.3)
    assert len({m["id"].replace("front", "back") for m in ids(gable, "roof/") if "-front" in m["id"]}) == \
        len([m for m in ids(gable, "roof/") if "-back" in m["id"]])


def test_every_rafter_pair_meets_the_ridge_face_to_face(gable):
    ridge = by_id(gable)["roof/ridge"]
    ylo, yhi = ext(ridge, 1)
    rafters = [m for m in gable["members"] if m["kind"] == "rafter"]
    for m in rafters:
        lo, hi = aabb(m)
        face = yhi if "-back-" in m["id"] else ylo
        assert (lo[1] if "-back-" in m["id"] else hi[1]) == pytest.approx(face, abs=0.3), m["id"]
        assert penetration(m, ridge) <= TOL
    for m in rafters:
        if "-front-" in m["id"]:
            twin = by_id(gable)[m["id"].replace("-front-", "-back-")]
            assert ext(m, 0) == pytest.approx(ext(twin, 0), abs=0.2)
    j = {(x["a"], x["b"]) for x in gable["joints"] if x["type"] == "rafter-ridge"}
    assert {a for a, _ in j} == {m["id"] for m in rafters}
    # the rafter tops are flush with the ridge top; the ridge is at least as deep as the plumb cut
    lib = tl.load(gable["region"])
    spec = gable["spec"]
    rit, raf = tl.item(lib, spec["ridge_item"]), tl.item(lib, spec["rafter_item"])
    assert rit["thickness_mm"] >= 25 and rit["width_mm"] >= raf["width_mm"] / math.cos(math.radians(spec["pitch_deg"]))
    top = max(aabb(m)[1][2] for m in rafters if m["id"].endswith("-01"))
    assert top == pytest.approx(ext(ridge, 2)[1], abs=0.3)


def test_ties_are_full_length_ceiling_joists_beside_the_rafters(gable):
    """On both eave plates, outer face to outer face, level, beside the rafter pair on its +X side,
    touching it face to face; none over a gable wall; no overlap with rafters, blocking or deck."""
    W, w = gable["spec"]["width"], tl.item(tl.load(gable["region"]), gable["spec"]["frame_item"])["width_mm"]
    by = by_id(gable)
    top = ext(by["wall-front/plate-top-2"], 2)[1]
    y_lo, y_hi = ext(by["wall-front/plate-top-2"], 1)[0], ext(by["wall-back/plate-top-2"], 1)[1]
    ties = {m["id"]: m for m in ids(gable, "roof/tie-")}
    assert ties
    for f in (m for m in gable["members"] if re_rafter(m["id"], "front")):
        i = f["id"][-2:]
        x0, x1 = ext(f, 0)
        if x0 < w - 0.1 or x1 > W - w + 0.1:
            assert f"roof/tie-{i}" not in ties
            continue
        t = ties[f"roof/tie-{i}"]
        assert ext(t, 2)[0] == pytest.approx(top, abs=0.3)                    # on the plates
        assert ext(t, 1) == pytest.approx((y_lo, y_hi), abs=0.3)             # outer face to outer face
        assert ext(t, 0)[0] == pytest.approx(x1, abs=0.3)                    # beside the rafter, +X side
        assert ext(t, 2)[1] - top <= tl.item(tl.load(gable["region"]), gable["spec"]["tie_item"])["width_mm"] + 0.3
        assert abs(t["x"][2]) < 1e-6 and abs(t["x"][0]) < 1e-6              # horizontal and straight
        for sl in ("front", "back"):
            r = by[f"roof/rafter-{sl}-{i}"]
            assert penetration(t, r) <= TOL and _touch(t, r, 0.3)
            assert any(j["type"] == "tie-rafter" and {j["a"], j["b"]} == {t["id"], r["id"]} for j in gable["joints"])
            assert any(j["type"] == "tie-plate" and {j["a"], j["b"]} == {t["id"], f"wall-{sl}/plate-top-2"}
                       for j in gable["joints"])
        for m in gable["members"]:
            if m["group"] == "roof" and m["id"] != t["id"] and m["kind"] != "ridge":
                assert penetration(t, m) <= TOL, (t["id"], m["id"])
    # every bay beside a tie is still closed over each eave wall: block plus tie reach rafter to rafter
    for sl in ("front", "back"):
        rs = sorted((m for m in gable["members"] if re_rafter(m["id"], sl)), key=lambda m: ext(m, 0)[0])
        for a, b in zip(rs, rs[1:]):
            lo, hi = ext(a, 0)[1], ext(b, 0)[0]
            cov = [ext(m, 0) for m in gable["members"] if m["id"].startswith(f"roof/eave-{sl}-")
                   or m["kind"] == "tie" and ext(m, 0)[0] >= lo - 0.3 and ext(m, 0)[1] <= hi + 0.3]
            cov = sorted(c for c in cov if c[1] > lo + 0.3 and c[0] < hi - 0.3)
            at = lo
            for c0, c1 in cov:
                assert c0 <= at + 0.3, (sl, a["id"])
                at = max(at, c1)
            assert at >= hi - 0.3, (sl, a["id"])


def re_rafter(i, sl):
    import re
    return re.fullmatch(rf"roof/rafter-{sl}-\d+", i)


def test_gable_studs_stop_under_the_roof_line(gable):
    s = gable["spec"]
    for m in gable["members"]:
        if "/infill-" in m["id"]:
            lo, hi = aabb(m)
            assert hi[2] > s["height_eaves"]
    ridge = by_id(gable)["roof/ridge"]
    ylo, yhi = ext(ridge, 1)
    for m in gable["members"]:           # a stud under the ridge board stops at it
        if "/infill-" in m["id"] and ext(m, 1)[0] < yhi - 0.1 and ext(m, 1)[1] > ylo + 0.1:
            assert aabb(m)[1][2] <= ext(ridge, 2)[0] + TOL, m["id"]


def test_roofing_covers_both_slopes_and_the_ridge_is_capped(gable):
    s = gable["spec"]
    roofing = [b for b in gable["bought"] if b["unit"] == "m2"]
    assert len(roofing) == 1
    decks = [m for m in gable["members"] if m["id"].startswith("roof/deck-")]
    area = sum(m["size"][0] * m["size"][1] for m in decks) / 1e6
    assert area * 1.1 == pytest.approx(roofing[0]["qty"], abs=0.05)
    assert {m["id"].split("-")[1] for m in decks} == {"front", "back"}
    assert any(b["item"] == "ridge-cap" and b["unit"] == "m" for b in gable["bought"])


def test_bargeboards_follow_both_slopes_and_meet_at_the_peak(gable):
    D = gable["spec"]["depth"]
    barges = ids(gable, "roof/bargeboard-")
    assert len(barges) == 4
    for nm in ("left", "right"):
        f, b = (by_id(gable)[f"roof/bargeboard-{sl}-{nm}"] for sl in ("front", "back"))
        assert ext(f, 1)[1] == pytest.approx(D / 2, abs=0.3) and ext(b, 1)[0] == pytest.approx(D / 2, abs=0.3)
        assert max(aabb(f)[1][2], aabb(b)[1][2]) == pytest.approx(min(aabb(f)[1][2], aabb(b)[1][2]), abs=0.3)


def test_fixtures_have_no_fix_or_check(gable):
    out = fc.run(gable)
    bad = [(x["id"], x["level"]) for x in out["findings"] if x["level"] != "ok"]
    assert not bad, bad


def test_sheet_edges_are_supported(gable):
    f = {x["id"]: x for x in fc.run(gable)["findings"]}
    assert f["sheet-edge"]["level"] == "ok"


def test_checks_agree_with_and_without_assemblies(gable):
    a = fc.run(gable)
    stripped = {k: v for k, v in gable.items() if k != "assemblies"}
    assert json.dumps(fc.run(stripped), sort_keys=True) == json.dumps(a, sort_keys=True)


def test_checks_trip_when_the_ridge_or_ties_go():
    f = fr.generate(load_fixture("gable-eu"))
    g = copy.deepcopy(f)
    g["members"] = [m for m in g["members"] if m["id"] != "roof/ridge"]
    g["joints"] = [j for j in g["joints"] if "roof/ridge" not in (j["a"], j["b"])]
    r = {x["id"]: x for x in fc.run(g)["findings"]}
    assert r["ridge"]["level"] == "fix"
    g = copy.deepcopy(f)
    gone = "roof/tie-02"
    g["members"] = [m for m in g["members"] if m["id"] != gone]
    g["joints"] = [j for j in g["joints"] if gone not in (j["a"], j["b"])]
    r = {x["id"]: x for x in fc.run(g)["findings"]}
    assert r["rafter-ties"]["level"] == "fix"
    # an edited-in thinner ridge
    g = copy.deepcopy(f)
    rid = next(m for m in g["members"] if m["id"] == "roof/ridge")
    rid["size"] = [rid["size"][0], 100, rid["size"][2]]
    assert {x["id"]: x for x in fc.run(g)["findings"]}["ridge"]["level"] == "fix"


# ------------------------------------------------------------ descriptions

def spec(**kw):
    s = load_fixture("gable-eu")
    s.update(kw)
    return s


@pytest.mark.parametrize("region,kw", [("eu", dict(overhang_side=0)), ("us", dict(overhang_side=0)),
                                       ("eu", dict(pitch_deg=40, height_eaves=1500, openings=[])),
                                       ("eu", dict(pitch_deg=18)), ("us", dict(pitch_deg=18)),
                                       ("eu", dict(pitch_deg=30, height_eaves=1900, openings=[]))])
def test_other_shapes_build_and_check_clean(region, kw):
    s = load_fixture(f"gable-{region}")
    s.update(kw)
    f = fr.generate(s)
    out = fc.run(f)
    bad = [(x["id"], x["level"]) for x in out["findings"] if x["level"] == "fix"]
    assert not bad, bad
    if kw.get("overhang_side") == 0:
        assert len(ids(f, "roof/bargeboard-")) == 4 and not ids(f, "roof/flying")


def test_height_ridge_gives_the_pitch():
    f = fr.generate({k: v for k, v in spec(height_ridge=3000, openings=[]).items() if k != "pitch_deg"})
    top = max(aabb(m)[1][2] for m in f["members"] if m["id"] == "roof/rafter-back-01")
    # rafter tops at the ridge face: a little under the centre-line value
    assert 2850 < top <= 3000 + 0.5
    assert "height_ridge" not in f["spec"] and f["spec"]["pitch_deg"] > 5


def fails(s, field, *words):
    with pytest.raises(fr.SpecError) as e:
        fr.generate(s)
    assert str(e.value).startswith(field + ":"), str(e.value)
    for w in words:
        assert w in str(e.value), str(e.value)


def test_errors_name_the_field():
    fails(spec(pitch_deg=2), "pitch_deg", "too flat")
    fails(spec(pitch_deg=75), "pitch_deg")
    fails(spec(pitch_deg="steep"), "pitch_deg")
    fails(spec(height_ridge=2500, pitch_deg=25, openings=[]), "height_ridge", "not both")
    s = {k: v for k, v in spec(height_ridge=2000, openings=[]).items() if k != "pitch_deg"}
    fails(s, "height_ridge", "not above")
    s = {k: v for k, v in spec(height_ridge=2330, openings=[]).items() if k != "pitch_deg"}
    fails(s, "height_ridge", "too low")
    fails(spec(height_eaves=100), "height_eaves")
    fails(spec(height_eaves=-1), "height_eaves")
    fails(spec(height_eaves=2800), "height_eaves", "taller than")
    fails(spec(height_front=2000), "height_front", "height_eaves")
    fails(spec(ridge_item="25x100"), "ridge_item", "deep")
    fails(spec(ridge_item="nope"), "ridge_item")
    fails(spec(tie_item="osb-12"), "tie_item")
    fails(spec(overhang_side=40), "overhang_side")
    with pytest.raises(fr.SpecError) as e:
        fr.generate(dict(load_fixture("shed-eu"), pitch_deg=20))
    assert str(e.value).startswith("pitch_deg:")


def test_default_ridge_is_the_smallest_deep_enough_section():
    for region, want in (("eu", "50x200"), ("us", "2x8")):
        f = fr.generate(dict(load_fixture(f"gable-{region}"), height_eaves=2000, openings=[]))
        assert f["spec"]["ridge_item"] == want and f["spec"]["tie_item"] == f["spec"]["rafter_item"]


def test_a_tall_gable_wall_is_sheathed_in_two_rows_with_the_seam_on_the_plates(gable):
    s = gable["spec"]
    sheets = [m for m in gable["members"] if m["id"].startswith("wall-left/sheathing-")]
    plate = by_id(gable)["wall-front/plate-top"]
    top = ext(by_id(gable)["wall-front/plate-top-2"], 2)[1]
    assert max(ext(m, 2)[1] - ext(m, 2)[0] for m in sheets) <= tl.item(tl.load(gable["region"]), s["sheathing"])["size_mm"][1] + 0.1
    seam = {round(ext(m, 2)[1], 1) for m in sheets if ext(m, 2)[1] < top} & {round(ext(m, 2)[0], 1) for m in sheets}
    assert len(seam) == 1
    z = seam.pop()
    assert top - 2 * 38 - 0.1 <= z <= top - 18      # inside the double plate (course of 38 or 50 mm)
    assert plate


def test_pent_descriptions_are_untouched():
    f = fr.generate(load_fixture("shed-eu"))
    assert [a["id"] for a in f["assemblies"]] == ["floor", "wall-front", "wall-back", "wall-left", "wall-right", "roof"]
    assert not [m for m in f["members"] if m["kind"] in ("ridge", "tie")]
