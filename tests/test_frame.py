"""Tests for tools/frame.py, the pent shed frame generator.

    .venv/bin/python -m pytest tests/test_frame.py
"""
import copy, json, os, subprocess, sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import frame as fr  # noqa: E402
import timberlib as tl  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
FIXTURES = ["shed-eu", "shed-us"]
TOL = 0.5


def load_fixture(name):
    with open(os.path.join(FIX, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module", params=FIXTURES)
def shed(request):
    spec = load_fixture(request.param)
    return fr.generate(spec)


@pytest.fixture(scope="module")
def eu():
    return fr.generate(load_fixture("shed-eu"))


# ------------------------------------------------------------------ geometry

def axes(m):
    x, y = np.array(m["x"], float), np.array(m["y"], float)
    return x, y, np.cross(x, y)


def _outline(m):
    """The member's shape in its (length, width) plane: the outline, or the rectangle."""
    L, W, _ = m["size"]
    return m.get("outline") or [(0, 0), (L, 0), (L, W), (0, W)]


def corners(m):
    """Corners of the member's prism (the outline, or the box, through its thickness)."""
    x, y, z = axes(m)
    o = np.array(m["origin"], float)
    T = m["size"][2]
    return np.array([o + a * x + b * y + c * z for a, b in _outline(m) for c in (0, T)])


def aabb(m):
    c = corners(m)
    return c.min(axis=0), c.max(axis=0)


def _sat(m):
    """Face normals and edge directions of a member's prism, for the separating axis test.
    A non-convex outline (a sheet notched round an opening) is taken as its hull."""
    x, y, z = axes(m)
    ol = _outline(m)
    edges = [z]
    normals = [z]
    for (a0, b0), (a1, b1) in zip(ol, ol[1:] + ol[:1]):
        e = (a1 - a0) * x + (b1 - b0) * y
        if np.linalg.norm(e) > 1e-9:
            e = e / np.linalg.norm(e)
            edges.append(e)
            normals.append(np.cross(e, z))
    return normals, edges


def penetration(a, b):
    """How deep two members overlap (separating axis test on their prisms); 0 or
    less when they only touch or are apart."""
    ca, cb = corners(a), corners(b)
    na, ea = _sat(a)
    nb, eb = _sat(b)
    axs = na + nb
    for u in ea:
        for v in eb:
            n = np.cross(u, v)
            if np.linalg.norm(n) > 1e-6:
                axs.append(n / np.linalg.norm(n))
    best = np.inf
    for n in axs:
        pa, pb = ca @ n, cb @ n
        best = min(best, min(pa.max(), pb.max()) - max(pa.min(), pb.min()))
        if best <= 0:
            return best
    return best


def by_id(frame):
    return {m["id"]: m for m in frame["members"]}


def test_no_two_members_overlap(shed):
    mem = shed["members"]
    boxes = [aabb(m) for m in mem]
    bad = []
    for i, a in enumerate(mem):
        for j in range(i + 1, len(mem)):
            b = mem[j]
            la, ha = boxes[i]
            lb, hb = boxes[j]
            if np.any(np.minimum(ha, hb) - np.maximum(la, lb) <= TOL):
                continue                       # boxes don't even meet
            # rafters are sloped: the plan tests them against the plates (the roof
            # deck and blocking sit on them and are checked too)
            if "rafter" in (a["kind"], b["kind"]):
                other = b if a["kind"] == "rafter" else a
                if not (other["kind"] == "plate" or other["group"] == "roof"):
                    continue
            if penetration(a, b) > TOL:
                bad.append((a["id"], b["id"], round(float(penetration(a, b)), 1)))
    assert not bad, bad[:10]


def test_every_stud_touches_a_plate_at_both_ends(shed):
    mem = shed["members"]
    plates = [m for m in mem if m["kind"] == "plate"]
    full = [m for m in mem if m["kind"] in ("stud", "king")
            and "/infill-" not in m["id"] and "/corner-" not in m["id"].replace("-stud", "")
            and m["layer"] == "walls"]
    assert len(full) > 10

    def touches(m, z, want_lo):
        lo, hi = aabb(m)
        for p in plates:
            if p["group"] != m["group"]:
                continue
            pl, ph = aabb(p)
            xy = np.minimum(hi, ph)[:2] - np.maximum(lo, pl)[:2]
            if np.all(xy > TOL) and abs((ph[2] if want_lo else pl[2]) - z) <= TOL:
                return True
        return False

    for m in full:
        lo, hi = aabb(m)
        assert touches(m, lo[2], True), f"{m['id']} bottom"
        assert touches(m, hi[2], False), f"{m['id']} top"
    # the shorter studs rest on something at both ends
    ends = [m for m in mem if "/cripple-" in m["id"] or "/infill-" in m["id"]]
    assert ends
    carriers = [m for m in mem if m["kind"] in ("plate", "header", "sill", "blocking", "rafter")]
    for m in ends:
        lo, hi = aabb(m)
        for z, name in ((lo[2], "bottom"), (hi[2], "top")):
            ok = False
            for c in carriers:
                cl, ch = aabb(c)
                xy = np.minimum(hi, ch)[:2] - np.maximum(lo, cl)[:2]
                if not np.all(xy > TOL):
                    continue
                if c["kind"] == "rafter":
                    # the stud's long point meets the rafter underside; its sloped cut
                    # (cut_deg) takes off the wedge a square box would poke into it
                    ok |= name == "top" and abs(rafter_under(c, lo[1]) - z) <= TOL
                else:
                    ok |= abs(ch[2] - z) <= TOL or abs(cl[2] - z) <= TOL
            assert ok, f"{m['id']} {name}"


def rafter_under(r, y):
    """Height of a rafter's underside at world y."""
    x, yv, _ = axes(r)
    o = np.array(r["origin"], float)
    t = (y - o[1]) / x[1]
    return o[2] + t * x[2]


def wall_members(shed, name, kinds=None):
    return [m for m in shed["members"] if m["group"] == f"wall-{name}" and m["layer"] == "walls"
            and (kinds is None or m["kind"] in kinds)]


def test_wall_widths_equal_the_spec(shed):
    spec = shed["spec"]
    W, D = spec["width"], spec["depth"]
    wall_d = tl.item(tl.load(spec["region"]), spec["frame_item"])["width_mm"]
    by = by_id(shed)
    for n in ("front", "back"):
        assert by[f"wall-{n}/plate-top"]["size"][0] == pytest.approx(W, abs=0.1)
        los = np.array([aabb(m)[0] for m in wall_members(shed, n)])
        his = np.array([aabb(m)[1] for m in wall_members(shed, n)])
        assert los[:, 0].min() == pytest.approx(0, abs=0.1)
        assert his[:, 0].max() == pytest.approx(W, abs=0.1)
    for n in ("left", "right"):
        assert by[f"wall-{n}/plate-top"]["size"][0] == pytest.approx(D - 2 * wall_d, abs=0.1)
        plates = [m for m in wall_members(shed, n, ("plate",)) if not m["id"].endswith("-2")]
        his = np.array([aabb(m)[1] for m in plates])
        los = np.array([aabb(m)[0] for m in plates])
        assert los[:, 1].min() == pytest.approx(wall_d, abs=0.1)
        assert his[:, 1].max() == pytest.approx(D - wall_d, abs=0.1)
        # the upper plate of a double top plate runs on over the back wall to lap the corner
        if spec["top_plate"] == "double":
            up = aabb(by[f"wall-{n}/plate-top-2"])
            assert up[0][1] == pytest.approx(wall_d, abs=0.1) and up[1][1] == pytest.approx(D, abs=0.1)


def vertical_faces(shed, group):
    """Every stud, cripple, infill stud and trimmer with its box (a side wall's
    skin also lands on the front and back walls' end studs)."""
    out = []
    for m in shed["members"]:
        if m["layer"] == "walls" and m["kind"] in ("stud", "trimmer", "king", "jack", "cripple"):
            lo, hi = aabb(m)
            out.append((m, lo, hi))
    return out


def test_sheet_edges_along_the_studs_land_on_a_member(shed):
    mem = shed["members"]
    studs = vertical_faces(shed, None)
    n_checked = 0
    for m in mem:
        if m["kind"] != "sheet" or m["layer"] != "sheathing":
            continue
        lo, hi = aabb(m)
        ax = 1 if m["group"] in ("wall-left", "wall-right") else 0
        dax = 1 - ax
        for edge in (lo[ax], hi[ax]):
            ok = False
            for s, slo, shi in studs:
                gap = max(slo[dax] - hi[dax], lo[dax] - shi[dax])      # the stud's face meets the sheet
                if gap <= TOL and slo[ax] - TOL <= edge <= shi[ax] + TOL and \
                        min(shi[2], hi[2]) - max(slo[2], lo[2]) > TOL:
                    ok = True
                    break
            assert ok, f"{m['id']} edge at {edge}"
            n_checked += 1
    assert n_checked > 20
    # floor and roof decks: edges along the joists and rafters
    for deck, support, ax in (("floor/deck", ("joist",), 0), ("roof/deck", ("rafter", "bargeboard"), 0)):
        sup = [aabb(m) for m in mem if m["kind"] in support]
        for m in mem:
            if m["id"].startswith(deck):
                lo, hi = aabb(m)
                for edge in (lo[ax], hi[ax]):
                    assert any(slo[ax] - TOL <= edge <= shi[ax] + TOL for slo, shi in sup), (m["id"], edge)
    # the edges that run across the joists land on a rim or a block
    cross = [aabb(m) for m in mem if m["id"].startswith(("floor/rim", "floor/blocking"))]
    for m in mem:
        if m["id"].startswith("floor/deck"):
            lo, hi = aabb(m)
            for edge in (lo[1], hi[1]):
                assert any(slo[1] - TOL <= edge <= shi[1] + TOL for slo, shi in cross), (m["id"], edge)


def test_identical_bytes_on_a_second_run(tmp_path):
    for name in FIXTURES:
        spec = os.path.join(FIX, name + ".json")
        outs = []
        for i in (1, 2):
            out = tmp_path / f"{name}-{i}" / "frame.json"
            r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "frame.py"), spec,
                                "--out", str(out)], capture_output=True, text=True, cwd=tmp_path)
            assert r.returncode == 0, r.stderr
            outs.append(out.read_bytes())
        assert outs[0] == outs[1]
        # and the same through the library, with the spec keys in another order
        spec_d = load_fixture(name)
        shuffled = dict(reversed(list(spec_d.items())))
        assert fr.dumps(fr.generate(shuffled)).encode() == outs[0]


def test_both_fixtures_generate_and_follow_the_format(shed):
    assert shed["schema"] == 1
    assert set(shed) == {"schema", "name", "region", "units", "spec", "members", "joints", "bought", "assemblies"}
    lib = tl.load(shed["region"])
    ids = set()
    for m in shed["members"]:
        assert m["id"] not in ids
        ids.add(m["id"])
        assert set(m) == {"id", "kind", "group", "layer", "item", "variant", "treated", "size",
                          "origin", "x", "y", "cut_deg", "outline"}
        assert m["kind"] in ("joist", "rim", "plate", "stud", "header", "trimmer", "king", "jack",
                             "cripple", "sill", "rafter", "blocking", "brace", "outrigger", "fascia",
                             "bargeboard", "board", "sheet")
        assert m["layer"] in ("floor", "walls", "roof", "sheathing", "cladding")
        assert m["group"] in ("floor", "wall-front", "wall-back", "wall-left", "wall-right", "roof")
        tl.item(lib, m["item"])
        assert all(v > 0 for v in m["size"])
        # coordinates are rounded to 0.1 mm
        for v in m["size"] + m["origin"]:
            assert round(v, 1) == pytest.approx(v, abs=1e-9)
        x, y, _ = axes(m)
        assert np.linalg.norm(x) == pytest.approx(1, abs=1e-5)
        assert abs(x @ y) < 1e-5
    for m in shed["members"]:
        it = tl.item(lib, m["item"])
        if m["kind"] in ("stud", "plate", "joist", "rim", "rafter", "trimmer", "header"):
            sec = sorted((it["thickness_mm"], it["width_mm"]))
            assert sorted(m["size"][1:]) == pytest.approx(sec, abs=0.1), m["id"]
        if m["kind"] == "sheet":
            assert m["size"][2] == pytest.approx(it["thickness_mm"], abs=0.1)
        if m["kind"] == "board":
            assert m["size"][2] == pytest.approx(it["thickness_mm"], abs=0.1)
            assert m["size"][1] <= it["cover_width_mm"] + 0.1
    for j in shed["joints"]:
        assert j["type"] in tl.JOINT_TYPES
        assert j["a"] in ids and j["b"] in ids, j
        if j["type"] == "sheet-frame":
            assert j["edge_mm"] > 0
        if j["type"] == "board-frame":
            assert j["crossings"] >= 1
    for b in shed["bought"]:
        assert tl.item(lib, b["item"])["category"] == "bought"
    assert [m["id"] for m in shed["members"]] == sorted(m["id"] for m in shed["members"])
    # a spec that came back filled in
    for k in ("stud_spacing", "joist_spacing", "rafter_spacing", "overhang", "loads", "frame_item"):
        assert k in shed["spec"]


def test_joint_coverage(shed):
    """Every kind of contact the plan names is recorded."""
    types = {j["type"] for j in shed["joints"]}
    assert types == set(tl.JOINT_TYPES) - {"rafter-ridge", "tie-rafter", "tie-plate",       # the gable roof's
                                                           "post-base", "beam-post", "beam-cap", "beam-ply",
                                                           "joist-beam", "deck-board"}         # the terrace's
    by = by_id(shed)
    # every stud-plate joint is a stud end on something it touches
    for j in shed["joints"]:
        if j["type"] == "stud-plate":
            assert by[j["a"]]["kind"] in ("stud", "trimmer", "king", "jack", "cripple")
        if j["type"] == "joist-rim":
            assert by[j["a"]]["kind"] in ("joist", "blocking")
    # each rafter is screwed to the front and the back plate (the flying rafters
    # at the side overhang sit on outriggers instead)
    for m in shed["members"]:
        if m["kind"] == "rafter" and "/flying-" not in m["id"]:
            pl = [j["b"] for j in shed["joints"] if j["type"] == "rafter-plate" and j["a"] == m["id"]]
            assert sorted(pl) == ["wall-back/plate-top-2", "wall-front/plate-top-2"]   # the upper plates


def test_roofing_is_bought_by_area(shed):
    roofing = [b for b in shed["bought"] if b["unit"] == "m2"]
    assert len(roofing) == 1 and roofing[0]["item"] == "roofing-felt"
    spec = shed["spec"]
    import math
    wall_d = tl.item(tl.load(spec["region"]), spec["frame_item"])["width_mm"]
    pitch = math.atan((spec["height_front"] - spec["height_back"]) / (spec["depth"] - wall_d))
    tf = tl.item(tl.load(spec["region"]), spec["fascia_item"])["thickness_mm"]
    # the deck and its roofing run out over the fascia and the bargeboards
    area = (spec["width"] + 2 * (spec["overhang_side"] + tf)) / 1000 * \
        (spec["depth"] + 2 * (spec["overhang"] + tf)) / math.cos(pitch) / 1000
    assert roofing[0]["qty"] == pytest.approx(area * 1.1, abs=0.01)


# ------------------------------------------------------- openings and defaults

def test_door_and_window_give_trimmers_header_sill_and_cut_sheathing(eu):
    by = by_id(eu)
    # door in the front wall: jacks, kings, a header on the jacks, the bottom plate in two pieces
    assert {"wall-front/jack-01", "wall-front/jack-02", "wall-front/header-01"} <= set(by)
    assert "wall-front/plate-bottom" not in by
    assert {"wall-front/plate-bottom-01", "wall-front/plate-bottom-02"} <= set(by)
    t1, t2 = (aabb(by[f"wall-front/jack-0{i}"]) for i in (1, 2))
    assert t1[1][0] == pytest.approx(1000, abs=0.1) and t2[0][0] == pytest.approx(1900, abs=0.1)
    h = aabb(by["wall-front/header-01"])
    assert h[0][0] == pytest.approx(950, abs=0.1) and h[1][0] == pytest.approx(1950, abs=0.1)
    assert h[0][2] == pytest.approx(168 + 1950, abs=0.1)         # floor top 150 + 18
    # no stud stands in the door
    for m in wall_members(eu, "front", ("stud",)):
        lo, hi = aabb(m)
        assert hi[0] <= 900 + 0.1 or lo[0] >= 2000 - 0.1, m["id"]
    # window in the left wall: sill, header, trimmers, cripples above and below
    ids = [i for i in by if i.startswith("wall-left/")]
    for k in ("sill-01", "header-01", "jack-01", "jack-02", "king-01", "king-02", "cripple-01"):
        assert f"wall-left/{k}" in ids
    sill = aabb(by["wall-left/sill-01"])
    assert sill[1][2] == pytest.approx(168 + 1000, abs=0.1)
    assert sum(1 for i in ids if "/cripple-" in i) >= 2
    # the sheathing over the door is cut at the bottom: one sheet has an outline, notched
    notched = [m for m in eu["members"] if m["id"].startswith("wall-front/sheathing") and m["outline"]]
    assert notched
    o = notched[0]["outline"]
    assert len(o) == 8 and all(len(p) == 2 for p in o)
    # the window gives a sheet under it and a notched one over it
    left = [m for m in eu["members"] if m["id"].startswith("wall-left/sheathing")]
    assert any(m["outline"] for m in left)
    # the sheets leave the openings clear
    for m in eu["members"]:
        if m["id"].startswith("wall-front/sheathing"):
            lo, hi = aabb(m)
            inside = (lo[0] < 1900 - 1 and hi[0] > 1000 + 1) and lo[2] < 168 + 1950 - 1
            if inside:
                assert m["outline"], m["id"]


def test_side_wall_infill_and_raked_sheathing(eu):
    by = by_id(eu)
    infill = [m for m in eu["members"] if "/infill-" in m["id"]]
    assert infill
    for m in infill:
        assert m["cut_deg"][0] == 0 and m["cut_deg"][1] > 0
    # the side sheathing follows the rafter line: some sheet has an outline with a sloped edge
    raked = [m for m in eu["members"] if m["id"].startswith("wall-right/sheathing") and m["outline"]]
    assert raked
    assert any(abs(p[1] - q[1]) > 1 and abs(p[0] - q[0]) > 1
               for m in raked for p, q in zip(m["outline"], m["outline"][1:] + m["outline"][:1]))
    # cladding boards on the raked part are cut at an angle
    assert any(m["cut_deg"][1] > 0 for m in eu["members"]
               if m["id"].startswith("wall-left/board") or m["id"].startswith("wall-right/board"))


def test_minimal_spec_gets_everything_from_the_library_defaults():
    frame = fr.generate({"type": "pent-shed", "width": 2400, "depth": 1800})
    lib = tl.load("eu")
    d = lib["defaults"]
    s = frame["spec"]
    assert s["region"] == "eu" and s["units"] == "metric"
    assert s["stud_spacing"] == d["stud_spacing_mm"]
    assert s["joist_spacing"] == d["joist_spacing_mm"]
    assert s["rafter_spacing"] == d["rafter_spacing_mm"]
    assert s["overhang"] == d["overhang_mm"]
    assert s["frame_item"] == d["items"]["frame"]
    assert s["floor_item"] == d["items"]["floor"] and s["rafter_item"] == d["items"]["rafter"]
    assert s["sheathing"] == d["items"]["sheathing"] and s["cladding"] == d["items"]["cladding"]
    assert s["treated_floor"] is True and s["loads"] == d["loads"] and s["openings"] == []
    assert s["height_front"] > s["height_back"] > 0
    kinds = {m["kind"] for m in frame["members"]}
    assert {"joist", "rim", "plate", "stud", "rafter", "sheet", "board", "blocking"} <= kinds
    assert not kinds & {"header", "trimmer"}
    assert frame["bought"][0]["item"] == "roofing-felt"
    # and it is as sound as the fixtures
    mem = frame["members"]
    assert len({m["id"] for m in mem}) == len(mem)
    assert fr.dumps(frame) == fr.dumps(fr.generate({"type": "pent-shed", "width": 2400, "depth": 1800}))


def test_minimal_us_spec_uses_the_us_defaults():
    frame = fr.generate({"type": "pent-shed", "region": "us", "width": 3048, "depth": 2438.4})
    assert frame["spec"]["frame_item"] == "2x4" and frame["spec"]["stud_spacing"] == 406.4
    assert frame["units"] == "imperial"


def test_lengths_may_be_written_as_text():
    a = fr.generate({"type": "pent-shed", "region": "us", "width": "10'", "depth": "8'"})
    b = fr.generate({"type": "pent-shed", "region": "us", "width": 3048, "depth": 2438.4})
    assert a["spec"]["width"] == b["spec"]["width"] and a["spec"]["depth"] == b["spec"]["depth"]


# --------------------------------------------------------------------- errors

def spec_with(**kw):
    s = load_fixture("shed-eu")
    s.update(kw)
    return s


def fails(spec, field, *words):
    with pytest.raises(fr.SpecError) as e:
        fr.generate(spec)
    msg = str(e.value)
    assert msg.startswith(field), msg
    for w in words:
        assert w in msg, msg
    return msg


def test_opening_wider_than_its_wall():
    s = spec_with(openings=[{"wall": "left", "kind": "door", "x": 100, "width": 2000, "height": 1900}])
    fails(s, "openings[0].width", "wider than the left wall")


def test_opening_too_near_a_corner():
    s = spec_with(openings=[{"wall": "front", "kind": "door", "x": 50, "width": 900, "height": 1900}])
    fails(s, "openings[0].x")


def test_opening_too_tall_for_the_wall():
    s = spec_with(openings=[{"wall": "back", "kind": "door", "x": 500, "width": 900, "height": 1950}])
    fails(s, "openings[0].height", "header")


def test_overlapping_openings():
    s = spec_with(openings=[{"wall": "front", "kind": "door", "x": 500, "width": 900, "height": 1900},
                            {"wall": "front", "kind": "window", "x": 1300, "sill": 900, "width": 600, "height": 600}])
    fails(s, "openings[1].x", "overlaps openings[0]")


def test_back_height_above_front_height():
    fails(spec_with(height_front=2000, height_back=2300), "height_back", "height_front")


@pytest.mark.parametrize("field", ["frame_item", "floor_item", "rafter_item", "sheathing",
                                   "floor_deck", "roof_deck", "cladding"])
def test_unknown_item_key_names_the_field(field):
    fails(spec_with(**{field: "nope-1x1"}), field, "'nope-1x1'", "eu library")


def test_item_of_the_wrong_kind():
    fails(spec_with(frame_item="osb-12"), "frame_item", "sheets")


def test_missing_and_unknown_fields():
    with pytest.raises(fr.SpecError, match="^depth: required"):
        fr.generate({"type": "pent-shed", "width": 3000})
    with pytest.raises(fr.SpecError, match="^studspacing: unknown field"):
        fr.generate(spec_with(studspacing=600))
    with pytest.raises(fr.SpecError, match="^type: "):
        fr.generate(spec_with(type="roundhouse"))
    with pytest.raises(fr.SpecError, match="^region: "):
        fr.generate(spec_with(region="xx"))
    with pytest.raises(fr.SpecError, match="^width: "):
        fr.generate(spec_with(width="wide"))


def test_the_command_line_reports_a_spec_error_and_writes_nothing(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(spec_with(height_back=9999)))
    out = tmp_path / "out" / "frame.json"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "frame.py"), str(bad),
                        "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 1 and "height_back" in r.stderr and not out.exists()


# ---------------------------------------- seams backed all the way up; no slivers

def two_window_spec(**kw):
    s = load_fixture("shed-eu")
    s["openings"] = [
        {"wall": "left", "kind": "window", "x": 600, "sill": 1000, "width": 600, "height": 600},
        {"wall": "right", "kind": "window", "x": 1000, "sill": 1000, "width": 600, "height": 600},
        {"wall": "front", "kind": "door", "x": 1000, "width": 900, "height": 1950}]
    s.update(kw)
    return s


def unbacked_length(frame, sheet):
    """Length of a sheathing sheet's two vertical edges with no wall member behind them."""
    lo, hi = aabb(sheet)
    side = sheet["group"] in ("wall-left", "wall-right")
    ax, dax = (1, 0) if side else (0, 1)
    pts = sheet["outline"] or [[0, 0], [sheet["size"][0], 0], sheet["size"][:2], [0, sheet["size"][1]]]
    w = sheet["size"][0]
    z0 = lo[2]
    backing = []
    for m in frame["members"]:
        if m["layer"] != "walls":
            continue
        mlo, mhi = aabb(m)
        if max(mlo[dax] - hi[dax], lo[dax] - mhi[dax]) <= TOL:        # its face meets the sheet
            backing.append((mlo[ax], mhi[ax], mlo[2], mhi[2]))
    gap = 0.0
    for u, edge in ((0.0, lo[ax]), (w, hi[ax])):
        vs = [p[1] for p in pts if abs(p[0] - u) < 0.2]
        if not vs:
            continue
        a, b = z0 + min(vs), z0 + max(vs)
        spans = sorted((z0_, z1_) for s0, s1, z0_, z1_ in backing if s0 - TOL <= edge <= s1 + TOL)
        cur = a
        for z0_, z1_ in spans:
            if z0_ > cur + TOL:
                gap += z0_ - cur
            cur = max(cur, z1_)
        top = b - cur                    # under 50 mm above the plate the rafter covers it
        gap += top if top > 50.0 else 0.0
    return gap


@pytest.fixture(scope="module", params=FIXTURES + ["two-windows"])
def seamed(request):
    if request.param == "two-windows":
        return fr.generate(two_window_spec())
    return fr.generate(load_fixture(request.param))


def test_every_sheathing_seam_has_timber_behind_it_all_the_way_up(seamed):
    sheets = [m for m in seamed["members"] if m["kind"] == "sheet" and m["layer"] == "sheathing"]
    assert sheets
    for m in sheets:
        assert unbacked_length(seamed, m) <= 1.0, (m["id"], unbacked_length(seamed, m))


def test_no_sheathing_sheet_is_narrower_than_150(seamed):
    for m in seamed["members"]:
        if m["kind"] == "sheet" and m["layer"] == "sheathing":
            assert min(m["size"][:2]) >= 150, (m["id"], m["size"])


def test_the_infill_over_a_trimmer_is_joined_like_the_others(seamed):
    ids = {m["id"] for m in seamed["members"]}
    for j in seamed["joints"]:
        assert j["a"] in ids and j["b"] in ids
    infill = [m["id"] for m in seamed["members"] if "/infill-" in m["id"]]
    for i in infill:
        bs = [j["b"] for j in seamed["joints"] if j["type"] == "stud-plate" and j["a"] == i]
        assert len(bs) == 2 and sum(b.endswith(("/plate-top", "/plate-top-2")) for b in bs) == 1 \
            and sum("/rafter-" in b for b in bs) == 1, (i, bs)


def test_openings_that_would_leave_a_sheathing_sliver_are_refused():
    s = spec_with(openings=[{"wall": "front", "kind": "door", "x": 120, "width": 900, "height": 1950}])
    fails(s, "openings[0].x", "corner framing")      # the corner rule now comes first
    s = spec_with(openings=[{"wall": "front", "kind": "door", "x": 500, "width": 900, "height": 1950},
                            {"wall": "front", "kind": "window", "x": 1600, "sill": 900, "width": 600, "height": 600}])
    fails(s, "openings[1].x", "too close")


@pytest.mark.parametrize("region", ["eu", "us"])
@pytest.mark.parametrize("window", [False, True])
def test_a_nearly_flat_roof_generates_with_every_seam_backed(region, window):
    spec = load_fixture(f"shed-{region}")
    spec["height_back"] = spec["height_front"] - 100
    if not window:
        spec["openings"] = [o for o in spec["openings"] if o["wall"] != "left"]
    frame = fr.generate(spec)
    for m in frame["members"]:
        if m["kind"] == "sheet" and m["layer"] == "sheathing":
            assert unbacked_length(frame, m) <= 1.0, m["id"]
            assert min(m["size"][:2]) >= 150
