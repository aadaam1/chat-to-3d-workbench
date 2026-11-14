"""An open tiled roof on the gable summer kitchen: `roof_deck: none` (bare rafters for tile battens) and
`ties: posts` (a tie over each post line only, the knee braces across the beams going up to it).

    .venv/bin/python -m pytest tests/test_open_tiled_roof.py
"""
import copy

import pytest

from test_frame import aabb
from test_summer_kitchen import floats, overlaps
import frame as fr
import framecheck as fc

BASE = {"type": "summer-kitchen", "width": 4000, "depth": 3000, "roof": "gable", "height_eaves": 2200,
        "loads": {"snow_kn_m2": 1.6}}
TILED = dict(BASE, roof_deck="none", ties="posts")


def build(**kw):
    return fr.generate(copy.deepcopy(dict(TILED, **kw)))


def kind(f, k):
    return [m for m in f["members"] if m["kind"] == k]


def findings(f):
    return {x["id"]: x for x in fc.run(f)["findings"]}


@pytest.mark.parametrize("pitch", [30, 35])
def test_the_users_case_passes_every_check_at_both_pitches(pitch):
    f = build(pitch_deg=pitch)
    bad = [(i, x["level"]) for i, x in findings(f).items() if x["level"] != "ok"]
    assert not bad, bad
    assert not overlaps(f) and not floats(f)


@pytest.mark.parametrize("pitch", [30, 35])
def test_no_roof_sheets_no_seam_blocking_but_eave_blocking_and_felt(pitch):
    f = build(pitch_deg=pitch)
    assert not [m for m in kind(f, "sheet") if m["group"] == "roof"]
    ids = [m["id"] for m in kind(f, "blocking")]
    assert not [i for i in ids if "/blocking-" in i]
    assert [i for i in ids if "/eave-" in i]
    felt = [b for b in f["bought"] if b["item"] == f["spec"]["roofing"]]
    assert felt and felt[0]["qty"] > 10 and "battens" in felt[0]["note"]
    assert findings(f)["sheet-spacing"]["level"] == "ok"


def test_ties_only_over_the_post_lines():
    f = build(pitch_deg=30)
    posts = [m for m in kind(f, "post") if aabb(m)[0][1] < 1500]
    ties = kind(f, "tie")
    assert len(ties) == len(posts) == 3
    for p in posts:
        lo, hi = aabb(p)[0][0], aabb(p)[1][0]
        assert any(lo - 1 <= (aabb(t)[0][0] + aabb(t)[1][0]) / 2 <= hi + 1 for t in ties)
    assert "rafter-ties" not in findings(f) and "rafter-thrust" in findings(f)


@pytest.mark.parametrize("pitch", [30, 35, 40])
def test_cross_braces_go_up_to_the_tie_underside(pitch):
    f = build(pitch_deg=pitch)
    ties = {m["id"]: m for m in kind(f, "tie")}
    cross = [b for b in kind(f, "brace") if "/cross-" in b["id"]]
    assert len(cross) == 6
    zt = min(aabb(t)[0][2] for t in ties.values())
    heads = {j["b"] for j in f["joints"] if j["type"] == "brace-rafter"}
    assert heads <= set(ties)
    for b in cross:
        assert abs(aabb(b)[1][2] - zt) < 1.0, (b["id"], aabb(b)[1][2], zt)


def test_default_stays_the_default():
    f = fr.generate(copy.deepcopy(dict(BASE, pitch_deg=30)))
    assert "ties" not in f["spec"] and f["spec"]["roof_deck"] != "none"
    assert kind(f, "sheet") and len(kind(f, "tie")) == 9
    assert "rafter-ties" in findings(f)


def test_bare_rafters_alone_keep_a_tie_per_pair():
    f = fr.generate(copy.deepcopy(dict(BASE, pitch_deg=30, roof_deck="none")))
    assert not [m for m in kind(f, "sheet") if m["group"] == "roof"]
    assert len(kind(f, "tie")) == 9
    assert all(x["level"] == "ok" for x in findings(f).values())


def test_a_deeper_tie_is_allowed():
    f = build(pitch_deg=35, tie_item="50x200")
    assert {m["item"] for m in kind(f, "tie")} == {"50x200"}
    assert all(x["level"] == "ok" for x in findings(f).values())


def test_a_wall_at_each_end_holds_that_end_and_needs_no_tie_there():
    f = build(pitch_deg=30, walls=["left", "right"])
    assert len(kind(f, "tie")) == 1
    assert all(x["level"] == "ok" for x in findings(f).values())


def test_a_missing_tie_is_a_fix():
    f = build(pitch_deg=30)
    gone = sorted(m["id"] for m in kind(f, "tie"))[1]
    f2 = fr.generate(copy.deepcopy(dict(TILED, pitch_deg=30, edits=[{"op": "remove", "id": gone}])))
    assert findings(f2)["rafter-thrust"]["level"] == "fix"


def test_too_far_between_the_tie_lines_is_flagged():
    f = build(pitch_deg=30, width=6000, post_spacing=5800)
    t = findings(f)["rafter-thrust"]
    assert t["level"] == "fix" and "simple estimate" in t["text"]


def test_the_thrust_estimate_is_about_what_the_hand_calculation_gives():
    import timberlib as tl
    from timber.spans import kitchen_thrust
    f = build(pitch_deg=30)
    lib = tl.load("eu")
    r = kitchen_thrust(lib, f["spec"], 1450.0, [75, 2020, 3925], [], (0, 4000), "50x150")
    assert 1.0 < r["pair_kn"] < 1.6
    assert 1800 < r["span_mm"] < 2100 and r["allowed_mm"] > r["span_mm"]
    assert 3 < r["T_kn"] < 8 and r["T_cap_kn"] > 5 * r["T_kn"]


@pytest.mark.parametrize("raw,field", [
    (dict(BASE, roof="mono", ties="posts"), "ties"),
    (dict(BASE, roof="mono", roof_deck="none"), "roof_deck"),
    (dict(BASE, ties="every"), "ties"),
    (dict(BASE, roof_deck="paper"), "roof_deck"),
])
def test_bad_descriptions_name_the_field(raw, field):
    with pytest.raises(Exception) as e:
        fr.generate(copy.deepcopy(raw))
    assert str(e.value).startswith(field)


def test_us_region_builds_and_the_checks_run():
    f = build(pitch_deg=35, region="us")
    assert len(kind(f, "tie")) == 3 and "rafter-thrust" in findings(f)
    assert findings(f)["open-bracing"]["level"] == "ok"
