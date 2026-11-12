"""Edits by piece (tools/frame_edits.py): one-off changes recorded in the shed
description, applied after the rules, surviving every rebuild."""
import copy

import pytest

from test_frame import aabb, by_id, load_fixture, TOL
import frame as fr
import framecheck as fc


def gen(*edits, region="eu"):
    spec = load_fixture(f"shed-{region}")
    spec["edits"] = list(edits)
    return fr.generate(spec)


def joints_of(f, mid):
    return [j for j in f["joints"] if mid in (j["a"], j["b"])]


def other(j, mid):
    return j["b"] if j["a"] == mid else j["a"]


@pytest.fixture(scope="module")
def base():
    return gen()


def test_no_edits_changes_nothing(base):
    spec = load_fixture("shed-eu")
    assert fr.dumps(fr.generate(spec)) == fr.dumps(base)
    assert base["spec"]["edits"] == []


def test_move_a_stud_along_the_wall_keeps_it_on_its_plates(base):
    sid = "wall-back/stud-03"
    f = gen({"op": "move", "id": sid, "by": [-100, 0, 0], "note": "line up with the shelf"})
    a, b = by_id(base)[sid], by_id(f)[sid]
    assert b["origin"][0] == pytest.approx(a["origin"][0] - 100)
    plates = {other(j, sid) for j in joints_of(f, sid) if j["type"] == "stud-plate"}
    assert plates == {other(j, sid) for j in joints_of(base, sid) if j["type"] == "stud-plate"}
    assert f["spec"]["edits"][0]["note"] == "line up with the shelf"


def test_a_piece_moved_away_loses_its_joints(base):
    bid = "floor/blocking-01"
    f = gen({"op": "move", "id": bid, "by": [0, 0, -1000]})
    assert joints_of(base, bid) and not joints_of(f, bid)


def test_remove_drops_the_piece_and_its_joints(base):
    bid = "roof/eave-front-02"
    f = gen({"op": "remove", "id": bid})
    assert bid in by_id(base) and bid not in by_id(f)
    assert not joints_of(f, bid)
    assert len(f["members"]) == len(base["members"]) - 1


def test_an_added_stud_gets_joints_to_the_plates_it_stands_between(base):
    by = by_id(base)
    s1, s2 = by["wall-back/stud-02"], by["wall-back/stud-03"]
    stud = copy.deepcopy(s1)
    gap = (s2["origin"][0] - s1["origin"][0]) / 2
    stud["origin"][0] += gap
    m = {k: stud[k] for k in ("kind", "group", "layer", "item", "size", "origin", "x", "y")}
    m["id"] = "edit/shelf-stud"
    f = gen({"op": "add", "member": m})
    js = joints_of(f, "edit/shelf-stud")
    plates = sorted(other(j, m["id"]) for j in js if j["type"] == "stud-plate")
    want = sorted(other(j, s1["id"]) for j in joints_of(base, s1["id"]) if j["type"] == "stud-plate")
    assert plates == want
    assert any(j["type"] == "sheet-frame" for j in js), "the sheathing is screwed to it too"


def test_resize_keeps_the_chosen_end(base):
    bid = "wall-front/plate-top"
    old = by_id(base)[bid]
    for keep, shift in (("start", 0.0), ("centre", 100.0), ("end", 200.0)):
        f = gen({"op": "resize", "id": bid, "length": old["size"][0] - 200, "keep": keep})
        m = by_id(f)[bid]
        assert m["size"][0] == pytest.approx(old["size"][0] - 200)
        assert m["origin"][0] == pytest.approx(old["origin"][0] + shift, abs=TOL)


def test_edits_apply_in_order_and_survive_a_rebuild():
    edits = [{"op": "move", "id": "wall-back/stud-03", "by": [-100, 0, 0]},
             {"op": "move", "id": "wall-back/stud-03", "by": [50, 0, 0]}]
    a, b = gen(*edits), gen(*edits)
    assert fr.dumps(a) == fr.dumps(b)
    base = by_id(gen())["wall-back/stud-03"]
    assert by_id(a)["wall-back/stud-03"]["origin"][0] == pytest.approx(base["origin"][0] - 50)


def test_an_edit_on_a_piece_that_is_gone_names_the_edit():
    with pytest.raises(fr.SpecError, match=r"edits\[1\]: no piece 'wall-back/stud-99'"):
        gen({"op": "remove", "id": "floor/blocking-01"}, {"op": "remove", "id": "wall-back/stud-99"})
    with pytest.raises(fr.SpecError, match=r"edits\[1\]: no piece 'floor/blocking-01'"):
        gen({"op": "remove", "id": "floor/blocking-01"}, {"op": "move", "id": "floor/blocking-01", "by": [0, 1, 0]})


@pytest.mark.parametrize("bad, msg", [
    ({"op": "spin", "id": "x"}, r"edits\[0\]: needs \"op\""),
    ({"op": "move", "id": "wall-back/stud-03", "by": [1, 2]}, r"edits\[0\]\.by: must be a list of 3"),
    ({"op": "move", "id": "wall-back/stud-03", "by": [1, 2, 3], "to": 4}, r"unknown field 'to'"),
    ({"op": "resize", "id": "wall-back/stud-03"}, r"either \"size\""),
    ({"op": "resize", "id": "wall-back/stud-03", "length": 100, "keep": "middle"}, r"\.keep"),
    ({"op": "add", "member": {"id": "stud-x", "kind": "stud", "group": "wall-back", "layer": "walls",
                              "item": "50x100", "size": [100, 100, 50], "origin": [0, 0, 0],
                              "x": [1, 0, 0], "y": [0, 1, 0]}}, r"starts with \"edit/\""),
    ({"op": "add", "member": {"id": "edit/a", "kind": "stud", "group": "wall-back", "layer": "walls",
                              "item": "2x4", "size": [100, 100, 50], "origin": [0, 0, 0],
                              "x": [1, 0, 0], "y": [0, 1, 0]}}, r"not in the library"),
    ({"op": "add", "member": {"id": "edit/a", "kind": "stud", "group": "wall-back", "layer": "walls",
                              "item": "50x100", "size": [100, 100, 50], "origin": [0, 0, 0],
                              "x": [1, 0, 0], "y": [1, 0, 0]}}, r"right angles"),
])
def test_bad_edits_say_what_is_wrong(bad, msg):
    with pytest.raises(fr.SpecError, match=msg):
        gen(bad)


def test_a_cut_piece_cannot_be_resized():
    with pytest.raises(fr.SpecError, match=r"cut piece"):
        gen({"op": "resize", "id": "roof/rafter-01", "length": 1000})


def test_an_edited_frame_goes_through_the_same_checks():
    f = gen({"op": "remove", "id": "wall-front/header-01"},
            {"op": "remove", "id": "wall-front/header-01-ply2"})
    res = fc.run(f)
    items = res["findings"]
    bad = [c for c in items if c["id"] == "opening-frame" and c["level"] == "fix"]
    assert bad, "a door without its header is flagged"
