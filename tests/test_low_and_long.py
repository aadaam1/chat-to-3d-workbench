"""Low decks (a flush frame: joists hung between the beams) and pieces longer than the timber on sale
(joined over a support): what the planner builds, and that it builds clean.

    .venv/bin/python -m pytest tests/test_low_and_long.py
"""
import copy, re

import numpy as np
import pytest

from test_frame import TOL, aabb, penetration
from test_framing import _touch
import frame as fr
import framecheck as fc
import frame_edits as fe
from timber import fields as fld
import timberlib as tl

FOUNDATIONS = ["ground_screw", "pier_block", "concrete_footing"]
PIECE = re.compile(r".*-[a-z]$")


def kind(f, k):
    return [m for m in f["members"] if m["kind"] == k]


def bad_levels(f):
    return [(x["id"], x["level"]) for x in fc.run(f)["findings"] if x["level"] in ("fix", "check")]


def clash(f, only=None):
    """Pairs of members that penetrate each other (all, or those with an id matching `only`)."""
    mem = f["members"]
    boxes = [aabb(m) for m in mem]
    idx = [i for i, m in enumerate(mem) if only is None or only.match(m["id"])]
    out = []
    for i in idx:
        for j in range(len(mem)):
            if j == i or (only is not None and j in idx and j < i) or (only is None and j < i):
                continue
            if np.any(np.minimum(boxes[i][1], boxes[j][1]) - np.maximum(boxes[i][0], boxes[j][0]) <= TOL):
                continue
            if penetration(mem[i], mem[j]) > TOL:
                out.append((mem[i]["id"], mem[j]["id"]))
    return out


def floating(f, only=None):
    mem = f["members"]
    return [m["id"] for i, m in enumerate(mem) if (only is None or only.match(m["id"]))
            and not any(j != i and _touch(m, mem[j]) for j in range(len(mem)))]


# ------------------------------------------------------------------ low terraces

@pytest.mark.parametrize("foundation", FOUNDATIONS)
def test_a_terrace_300_mm_up_builds_clean_with_hung_joists(foundation):
    f = fr.generate({"type": "terrace", "width": 4000, "depth": 3000, "height": 300, "foundation": foundation})
    assert f["spec"]["frame"] == "flush"
    assert bad_levels(f) == []
    assert not clash(f) and not floating(f)
    assert not kind(f, "post")                                  # the beams sit on the post bases
    beams, joists = kind(f, "beam"), kind(f, "joist")
    tops = {round(aabb(m)[1][2], 1) for m in beams + joists}
    assert len(tops) == 1                                       # joists and beams level on top
    assert max(aabb(m)[1][2] for m in kind(f, "deckboard")) == pytest.approx(300, abs=TOL)
    hung = {(j["a"], j["b"]) for j in f["joints"] if j["type"] == "joist-hanger"}
    for j in joists:
        mine = [b for b in beams if _touch(j, b, 0.5)]
        assert len(mine) == 2                                   # one beam each end
        assert all((j["id"], b["id"]) in hung for b in mine)
    assert sum(b["qty"] for b in f["bought"] if b["item"] == "joist-hanger") == 2 * len(joists)
    assert any(d["what"] == "Frame" and "joists hung between the beams" in d["chose"] and "300 mm" in d["why"]
               for d in f["decisions"])
    levels = {x["id"]: x["level"] for x in fc.run(f)["findings"]}
    assert levels["beam-bearing"] == levels["post-footing"] == levels["span-joists"] == levels["ground-treated"] == "ok"
    assert all(m["treated"] for m in beams + joists)


def test_a_flush_frame_can_be_asked_for_at_any_height():
    f = fr.generate({"type": "terrace", "width": 4000, "depth": 3000, "height": 550, "frame": "flush"})
    assert f["spec"]["frame"] == "flush" and bad_levels(f) == []
    assert any(d["why"] == "a flush frame was asked for" for d in f["decisions"])


def test_stacked_is_kept_when_there_is_room_and_refused_when_there_is_not():
    f = fr.generate({"type": "terrace", "width": 4000, "depth": 3000, "height": 600})
    assert "frame" not in f["spec"] and kind(f, "post")
    with pytest.raises(fr.SpecError, match="frame: flush"):
        fr.generate({"type": "terrace", "width": 4000, "depth": 3000, "height": 300, "frame": "stacked"})
    with pytest.raises(fr.SpecError, match="frame"):
        fr.generate({"type": "terrace", "width": 4000, "depth": 3000, "height": 300, "frame": "hung"})


@pytest.mark.parametrize("foundation", FOUNDATIONS)
def test_too_low_names_a_height_that_works(foundation):
    raw = {"type": "terrace", "width": 4000, "depth": 3000, "height": 200, "foundation": foundation}
    with pytest.raises(fr.SpecError) as e:
        fr.generate(raw)
    m = re.search(r"lowest that works is (\d+) mm", str(e.value))
    assert str(e.value).startswith("height:") and m
    low = int(m.group(1))
    f = fr.generate(dict(raw, height=low))
    assert bad_levels(f) == [] and not clash(f)
    with pytest.raises(fr.SpecError):
        fr.generate(dict(raw, height=low - 10))


def test_lowest_heights_per_foundation():
    lows = {}
    for fnd in FOUNDATIONS:
        with pytest.raises(fr.SpecError) as e:
            fr.generate({"type": "terrace", "width": 4000, "depth": 3000, "height": 100, "foundation": fnd})
        lows[fnd] = int(re.search(r"lowest that works is (\d+)", str(e.value)).group(1))
    assert lows == {"ground_screw": 250, "pier_block": 290, "concrete_footing": 290}


def test_sections_step_down_with_the_height():
    secs = {}
    for h in (250, 300, 350, 400):
        sp = fr.generate({"type": "terrace", "width": 4000, "depth": 3000, "height": h})["spec"]
        secs[h] = (sp["beam_item"], sp["joist_item"], sp["post_spacing"])
    assert [secs[h][0] for h in (250, 300, 350, 400)] == ["50x100", "50x150", "50x200", "50x200"]
    assert secs[250][2] < secs[400][2]                         # shallower beams: closer footings


def test_us_terrace_low_builds_clean():
    f = fr.generate({"type": "terrace", "region": "us", "width": "13'", "depth": "10'", "height": 330})
    assert f["spec"]["frame"] == "flush" and bad_levels(f) == [] and not clash(f)


def test_frame_is_a_listed_field():
    assert "frame" in [x["name"] for x in fld.table("terrace", tl.load("eu"))]
    assert "floor_frame" in [x["name"] for x in fld.table("summer-kitchen", tl.load("eu"))]


def test_the_summer_kitchen_floor_defaults_to_a_low_flush_frame():
    f = fr.generate({"type": "summer-kitchen", "width": 4000, "depth": 3000, "roof": "gable", "floor": "terrace"})
    assert f["spec"]["floor_height"] == 250 and f["spec"]["floor_frame"] == "flush"
    assert any(d["what"] == "Floor height" for d in f["decisions"])
    assert bad_levels(f) == [] and not clash(f) and not floating(f)
    g = fr.generate({"type": "summer-kitchen", "width": 4000, "depth": 3000, "roof": "gable", "floor": "terrace",
                     "floor_height": 600})
    assert "floor_frame" not in g["spec"]


# ------------------------------------------------------------------ long pieces

SHEDS = [{"type": "pent-shed", "width": 6000, "depth": 3000}, {"type": "gable-shed", "width": 7000, "depth": 3000}]


@pytest.fixture(scope="module", params=range(len(SHEDS)))
def shed(request):
    return fr.generate(copy.deepcopy(SHEDS[request.param]))


def base(mid):
    return mid[:-2]


def test_long_sheds_build_with_no_stock_length_fix(shed):
    levels = {x["id"]: x["level"] for x in fc.run(shed)["findings"]}
    assert levels["stock-length"] == "ok"
    assert [x for x in bad_levels(shed)] == []
    assert any("joined" in d["what"] for d in shed["decisions"])


def test_nothing_floats_or_overlaps_among_the_pieces(shed):
    assert not floating(shed, PIECE)
    # (a cladding board's 3 mm over a rafter, and the ridge's over a gable board, are the unjoined frame's too)
    assert not [c for c in clash(shed, PIECE) if not re.search(r"board|ridge", c[0])]


SUPPORT = {"board": ("stud", "king", "jack", "cripple"), "plate": ("stud", "king", "jack", "cripple"),
           "rim": ("joist",), "fascia": ("rafter",), "ridge": ("rafter",), "beam": ("post", "post-base")}


def test_every_butt_joint_lands_on_a_support(shed):
    by = {m["id"]: m for m in shed["members"]}
    butts = [j for j in shed["joints"] if j["type"] == "butt"]
    assert butts
    for j in butts:
        a, b = by[j["a"]], by[j["b"]]
        k = a["kind"]
        if k == "board" or (k == "plate" and "plate-top-2" in a["id"]):
            continue          # boards are tested below; the upper plate rests on the plate below
        sup = [s for s in shed["members"] if s["kind"] in SUPPORT[k] and s["group"] == a["group"]
               and fe.contact(a, s) is not None and fe.contact(b, s) is not None]
        assert sup, (j, "no support touches both pieces")
    for j in butts:
        a, b = by[j["a"]], by[j["b"]]
        if a["kind"] == "board":
            sup = [s for s in shed["members"] if s["kind"] in SUPPORT["board"] and s["group"] == a["group"]]
            lo, hi = aabb(a), aabb(b)
            ax = int(np.argmax(np.abs(a["x"])))
            cut = aabb(a)[1][ax] if abs(aabb(a)[1][ax] - aabb(b)[0][ax]) < 1.0 else aabb(b)[0][ax]
            assert any(aabb(s)[0][ax] - 1.0 <= cut <= aabb(s)[1][ax] + 1.0 for s in sup), j


def test_joined_pieces_are_fixed_on_both_sides(shed):
    joints = shed["joints"]
    for j in [j for j in joints if j["type"] == "butt" and "plate" in j["a"] and "bottom" in j["a"]]:
        for pid in (j["a"], j["b"]):
            assert any(x["type"] == "stud-plate" and pid in (x["a"], x["b"]) for x in joints)


def test_upper_and_lower_plate_joints_are_offset(shed):
    by = {m["id"]: m for m in shed["members"]}
    cuts = {}
    for j in shed["joints"]:
        if j["type"] == "butt" and by[j["a"]]["kind"] == "plate":
            a = by[j["a"]]
            ax = int(np.argmax(np.abs(a["x"])))
            cuts.setdefault(base(j["a"]), []).append(aabb(a)[1][ax] if np.dot(a["x"], np.eye(3)[ax]) > 0 else aabb(a)[0][ax])
    checked = 0
    for k, up in cuts.items():
        if k.endswith("plate-top-2"):
            low = cuts.get(k.replace("plate-top-2", "plate-top"), [])
            for u in up:
                assert all(abs(u - l) >= 600 - 0.5 for l in low), (k, u, low)
                checked += 1
    assert checked or not any(k.endswith("plate-top-2") for k in cuts)


def test_cladding_joints_stagger(shed):
    by = {m["id"]: m for m in shed["members"]}
    for wall in ("wall-front", "wall-back"):
        rows = {}
        for j in shed["joints"]:
            if j["type"] == "butt" and j["a"].startswith(wall + "/board"):
                a = by[j["a"]]
                ax = 0
                rows.setdefault(round(aabb(a)[0][2]), []).append(round(aabb(a)[1][ax]) if aabb(a)[1][ax] < aabb(by[j["b"]])[1][ax] else round(aabb(a)[0][ax]))
        zs = sorted(rows)
        for z0, z1 in zip(zs, zs[1:]):
            assert not set(rows[z0]) & set(rows[z1]), (wall, z0, z1)


def test_what_cannot_be_joined_still_reports_with_advice():
    f = fr.generate({"type": "pent-shed", "width": 6000, "depth": 5000, "region": "us"})
    x = next(x for x in fc.run(f)["findings"] if x["id"] == "stock-length")
    assert x["level"] == "fix" and "floor joist" in x["text"] and "rafter" in x["text"]


def test_long_terrace_beams_are_joined_over_posts():
    f = fr.generate({"type": "terrace", "region": "us", "width": 12000, "depth": 4000, "height": 550})
    assert {x["id"]: x["level"] for x in fc.run(f)["findings"]}["stock-length"] == "ok"
    by = {m["id"]: m for m in f["members"]}
    for j in [j for j in f["joints"] if j["type"] == "butt"]:
        a, b = by[j["a"]], by[j["b"]]
        assert any(s["kind"] in ("post", "post-base") and fe.contact(a, s) and fe.contact(b, s) for s in f["members"])
    assert not clash(f, PIECE) and not floating(f, PIECE)
