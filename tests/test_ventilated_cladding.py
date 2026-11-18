"""Ventilated cladding: a breather membrane, battens over the studs and an air gap behind the boards.

    .venv/bin/python -m pytest tests/test_ventilated_cladding.py
"""
import copy, hashlib, json, math

import pytest

from test_frame import aabb, load_fixture
import bom as bm
import frame as fr
import timberlib as tl


def build(name, **kw):
    raw = copy.deepcopy(load_fixture(name))
    raw.update(kw)
    return fr.generate(raw)


def kind(f, k):
    return [m for m in f["members"] if m["kind"] == k]


def area(m):
    if m.get("outline"):
        p = m["outline"]
        return abs(sum(p[i - 1][0] * p[i][1] - p[i][0] * p[i - 1][1] for i in range(len(p)))) / 2
    return m["size"][0] * m["size"][1]


@pytest.mark.parametrize("fixture", ["shed-eu", "gable-eu"])
def test_battens_over_every_stud_line(fixture):
    f = build(fixture)
    bw = tl.item(tl.load("eu"), "25x50")["width_mm"]
    for wall in ("front", "back", "left", "right"):
        g = f"wall-{wall}"
        battens = [m for m in kind(f, "batten") if m["group"] == g]
        assert battens
        lo = {m["id"]: aabb(m) for m in battens}
        ax = 0 if wall in ("front", "back") else 1
        centres = [(a[0][ax] + a[1][ax]) / 2 for a in lo.values()]
        for s in f["members"]:
            if s["group"] != g or s["kind"] not in ("stud", "king", "jack") or s["size"][0] < 1000:
                continue
            a, b = aabb(s)
            c = (a[ax] + b[ax]) / 2
            assert any(abs(c - x) <= bw + 1.0 for x in centres), f"no batten over {s['id']}"
        # no gap wider than 600 mm between the batten lines
        xs = sorted(set(round(c) for c in centres))
        assert all(q - p <= 600 + 1 for p, q in zip(xs, xs[1:])), (g, xs)


@pytest.mark.parametrize("fixture", ["shed-eu", "gable-eu"])
def test_cladding_sits_sheathing_plus_batten_out(fixture):
    f = build(fixture)
    lib = tl.load("eu")
    ts = tl.item(lib, f["spec"]["sheathing"])["thickness_mm"]
    tb = tl.item(lib, "25x50")["thickness_mm"]
    tc = tl.item(lib, f["spec"]["cladding"])["thickness_mm"]
    front = [m for m in f["members"] if m["group"] == "wall-front"]
    face = min(aabb(m)[0][1] for m in front if m["kind"] == "stud")          # the wall's outer plane (front: low Y)
    for k, off in (("sheet", ts), ("batten", ts + tb), ("board", ts + tb + tc)):
        out = min(aabb(m)[0][1] for m in front if m["kind"] == k)
        assert out == pytest.approx(face - off, abs=0.2), k


@pytest.mark.parametrize("fixture", ["shed-eu", "gable-eu"])
def test_membrane_is_the_clad_area_plus_lap(fixture):
    f = build(fixture)
    clad = sum(area(m) for m in f["members"] if m["kind"] == "sheet" and m["layer"] == "sheathing") / 1e6
    memb = next(b for b in f["bought"] if b["item"] == "breather-membrane")
    assert memb["unit"] == "m2"
    assert memb["qty"] == pytest.approx(round(clad * 1.1, 2), abs=0.011)
    mesh = next(b for b in f["bought"] if b["item"] == "insect-mesh")
    assert mesh["unit"] == "m" and mesh["qty"] > 0
    assert not any(m["kind"] == "membrane" for m in f["members"])        # not modelled as a solid


@pytest.mark.parametrize("fixture", ["shed-eu", "gable-eu"])
def test_joints_and_shopping_list(fixture):
    f = build(fixture)
    types = {j["type"] for j in f["joints"]}
    assert {"batten-frame", "board-batten"} <= types and "board-frame" not in types
    for j in f["joints"]:
        if j["type"] == "batten-frame":
            assert j["edge_mm"] > 0
    b = bm.make_bom(f)
    assert any(l["item"] == "25x50" and l["variant"] == "impregnated" for l in b["timber"])
    assert {"breather-membrane", "insect-mesh"} <= {x["item"] for x in b["bought"]}


# sha256[:16] of json.dumps({members, joints, bought}, sort_keys=True) of the frame before this feature existed (main with the 19x146 cladding default)
MAIN_HASHES = {"shed-eu": "baaa9a44fcc1304b", "gable-eu": "e83822f09452d758",
               "summer-kitchen-eu": "b7351477ed3bffe5", "tool-shed": "8d1fd4712db2e37b"}


@pytest.mark.parametrize("name", sorted(MAIN_HASHES))
def test_not_ventilated_is_exactly_todays_frame(name):
    f = build(name, ventilated=False)
    assert f["spec"]["ventilated"] is False
    d = json.dumps({k: f[k] for k in ("members", "joints", "bought")}, sort_keys=True)
    assert hashlib.sha256(d.encode()).hexdigest()[:16] == MAIN_HASHES[name]


def test_turning_it_off_only_removes_battens_and_moves_boards_back():
    on, off = build("shed-eu"), build("shed-eu", ventilated=False)
    assert not kind(off, "batten") and not any(b["item"] in ("breather-membrane", "insect-mesh") for b in off["bought"])
    assert not any(j["type"] in ("batten-frame", "board-batten") for j in off["joints"])
    assert {m["id"] for m in off["members"]} == {m["id"] for m in on["members"] if m["kind"] != "batten"}
    assert any(d["what"] == "Cladding" for d in off["decisions"])


def test_us_shed_defaults_to_not_ventilated():
    f = build("shed-us")
    assert not kind(f, "batten") and "ventilated" not in f["spec"]
    on = build("shed-us", ventilated=True)
    assert kind(on, "batten") and on["spec"]["ventilated"] is True
    assert {m["item"] for m in kind(on, "batten")} == {"1x4"}


def test_summer_kitchen_walls_get_battens():
    raw = copy.deepcopy(load_fixture("summer-kitchen-eu"))
    f = fr.generate(raw)
    assert any(m["layer"] == "sheathing" for m in f["members"])
    assert kind(f, "batten")
    assert any(b["item"] == "breather-membrane" for b in f["bought"])
    assert not kind(fr.generate(dict(raw, ventilated=False)), "batten")


def test_ventilated_must_be_true_or_false():
    with pytest.raises(fr.SpecError):
        build("shed-eu", ventilated="yes")


def test_listed_by_fields():
    import timber.fields as fl
    for t in ("pent-shed", "gable-shed", "summer-kitchen"):
        assert "ventilated" in fl.names(t)
