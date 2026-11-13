"""Framing details (tools/framing.py): the carpentry conventions a generated
shed follows, checked piece by piece in both regions. No AI is involved."""
import copy
import json

import numpy as np
import pytest

from test_frame import _sat, aabb, by_id, corners, load_fixture, penetration, TOL
import frame as fr
import timberlib as tl

REGIONS = ["eu", "us"]


def gen(region, **over):
    spec = load_fixture(f"shed-{region}")
    spec.update(over)
    return fr.generate(spec)


def touching_z(a, z, others):
    """Members in `others` whose box meets member a's box over its plan area at height z."""
    lo, hi = aabb(a)
    out = []
    for b in others:
        bl, bh = aabb(b)
        xy = np.minimum(hi, bh)[:2] - np.maximum(lo, bl)[:2]
        if np.all(xy > TOL) and (abs(bh[2] - z) <= TOL or abs(bl[2] - z) <= TOL):
            out.append(b)
    return out


@pytest.fixture(scope="module", params=REGIONS)
def shed(request):
    return gen(request.param)


def wall(frame, name):
    return [m for m in frame["members"] if m["group"] == f"wall-{name}" and m["layer"] == "walls"]


@pytest.mark.parametrize("which", [("front", 1), ("left", 1)])
def test_every_opening_has_kings_jacks_and_a_header_on_the_jacks(shed, which):
    name, i = which
    by = by_id(shed)
    g = f"wall-{name}"
    kings = [by[f"{g}/king-{2 * i - 1:02d}"], by[f"{g}/king-{2 * i:02d}"]]
    jacks = [by[f"{g}/jack-{2 * i - 1:02d}"], by[f"{g}/jack-{2 * i:02d}"]]
    header = by[f"{g}/header-{i:02d}"]
    hlo, hhi = aabb(header)
    ax = 0 if name in ("front", "back") else 1
    for j in jacks:
        jlo, jhi = aabb(j)
        assert jhi[2] == pytest.approx(hlo[2], abs=TOL), f"{j['id']} does not reach the header"
        assert hlo[ax] - TOL <= jlo[ax] and jhi[ax] <= hhi[ax] + TOL, f"the header does not rest on {j['id']}"
    plates = [m for m in wall(shed, name) if m["kind"] == "plate"]
    for k, j in zip(kings, jacks):
        klo, khi = aabb(k)
        jlo, jhi = aabb(j)
        assert abs(min(khi[ax], jhi[ax]) - max(klo[ax], jlo[ax])) <= TOL, "king and jack are not side by side"
        assert touching_z(k, klo[2], plates) and touching_z(k, khi[2], plates), f"{k['id']} is not plate to plate"
    plies = [m for m in shed["members"] if m["id"].startswith(header["id"])]
    assert len(plies) == 2, "the header is two plies"


def test_cripples_carry_the_sill_and_the_header(shed):
    spacing = shed["spec"]["stud_spacing"]
    for name in ("front", "left"):
        mem = wall(shed, name)
        crip = [m for m in mem if m["kind"] == "cripple"]
        carriers = [m for m in mem if m["kind"] in ("plate", "sill", "header")]
        for c in crip:
            lo, hi = aabb(c)
            assert touching_z(c, lo[2], carriers), f"{c['id']} bottom"
            assert touching_z(c, hi[2], carriers), f"{c['id']} top"
    sill = by_id(shed)["wall-left/sill-01"]
    slo, shi = aabb(sill)
    under = [m for m in wall(shed, "left") if m["kind"] == "cripple" and abs(aabb(m)[1][2] - slo[2]) <= TOL]
    assert len(under) >= 2, "a window sill sits on cripples, one at each end"
    ys = sorted(aabb(m)[0][1] for m in under)
    assert ys[0] == pytest.approx(slo[1], abs=TOL) and aabb(under[-1])[1][1] == pytest.approx(shi[1], abs=TOL) \
        or max(np.diff(ys)) <= spacing + TOL


@pytest.mark.parametrize("path", ["examples/garden-shed/structure.json", "tests/fixtures/tool-shed.json",
                                  "tests/fixtures/shed-eu.json", "tests/fixtures/shed-us.json"])
def test_cripples_are_symmetric_across_each_opening(path):
    with open(path, encoding="utf-8") as f:
        frame = fr.generate(json.load(f))
    spacing = frame["spec"]["stud_spacing"]
    by = {m["id"]: m for m in frame["members"]}
    for jid in sorted(i for i in by if "/jack-" in i and int(i[-2:]) % 2 == 1):
        g, n = jid.split("/jack-")
        ax = 0 if g in ("wall-front", "wall-back") else 1
        jl, jr = aabb(by[jid]), aabb(by[f"{g}/jack-{int(n) + 1:02d}"])
        a, b = jl[1][ax], jr[0][ax]                       # the jacks' inner faces
        hdr = aabb(by[f"{g}/header-{(int(n) + 1) // 2:02d}"])
        for side in ("above", "below"):
            cr = [aabb(m) for m in frame["members"] if m["group"] == g and m["kind"] == "cripple"
                  and a - TOL <= aabb(m)[0][ax] and aabb(m)[1][ax] <= b + TOL
                  and ((aabb(m)[0][2] >= hdr[1][2] - TOL) == (side == "above"))]
            if not cr:
                continue
            c = sorted(float((lo[ax] + hi[ax]) / 2) for lo, hi in cr)
            mid = (a + b) / 2
            assert [round(mid - x, 1) for x in c] == [round(x - mid, 1) for x in reversed(c)], \
                f"{g} opening {n}: cripples {side} are not symmetric: {c}"
            assert min(lo[ax] for lo, _ in cr) == pytest.approx(a, abs=TOL), "a cripple next to each jack"
            assert max(hi[ax] for _, hi in cr) == pytest.approx(b, abs=TOL)
            assert len(c) == 1 or max(np.diff(c)) <= spacing + TOL


@pytest.mark.parametrize("path", ["examples/garden-shed/structure.json", "tests/fixtures/shed-us.json"])
def test_roof_deck_covers_the_fascia_and_bargeboards(path):
    with open(path, encoding="utf-8") as f:
        frame = fr.generate(json.load(f))
    mem = frame["members"]
    deck = [aabb(m) for m in mem if m["id"].startswith("roof/deck-")]
    lo = np.min([d[0] for d in deck], axis=0)
    hi = np.max([d[1] for d in deck], axis=0)
    for nm in ("roof/fascia-front", "roof/fascia-back", "roof/bargeboard-left", "roof/bargeboard-right"):
        flo, fhi = aabb(next(m for m in mem if m["id"] == nm))
        assert lo[0] <= flo[0] + TOL and hi[0] >= fhi[0] - TOL, f"the deck stops short of {nm} across"
        assert lo[1] <= flo[1] + TOL and hi[1] >= fhi[1] - TOL, f"the deck stops short of {nm} down the slope"
        board = next(m for m in mem if m["id"] == nm)
        assert all(penetration(board, d) <= TOL for d in mem if d["id"].startswith("roof/deck-")), \
            f"the deck cuts into {nm}"


@pytest.mark.parametrize("corner", ["three-stud", "california"])
def test_corners_give_the_side_wall_and_the_lining_something_to_fix_to(corner):
    for region in REGIONS:
        f = gen(region, corner=corner)
        by = by_id(f)
        spec = f["spec"]
        for front_or_back in ("front", "back"):
            for side, end in (("left", "01"), ("right", "02")):
                pieces = [m for m in f["members"] if m["id"].startswith(f"wall-{front_or_back}/corner-{end}-")]
                assert pieces, (region, corner, front_or_back, end)
                # the lining of the front/back wall ends at the side wall's inner face: a piece of the
                # corner assembly lies across that line, at the wall's inner face
                wall_d = max(m["size"][1] for m in pieces if m["kind"] == "stud") if corner == "three-stud" else None
                inner = [m for m in pieces if m["kind"] == "stud"]
                assert inner
                # fixed through into the front/back wall's corner, where the studs meet face to face
                j = [x for x in f["joints"] if x["type"] == "corner-stud"
                     and x["a"].startswith(f"wall-{side}/") and x["b"].startswith(f"wall-{front_or_back}/")]
                assert j, f"the {side} wall's end stud is not fixed to the {front_or_back} corner"


def test_double_top_plate_laps_the_back_corners(shed):
    by = by_id(shed)
    back_lo = aabb(by["wall-back/plate-top"])
    for side in ("left", "right"):
        up = aabb(by[f"wall-{side}/plate-top-2"])
        ov = np.minimum(up[1], back_lo[1]) - np.maximum(up[0], back_lo[0])
        assert ov[0] > TOL and ov[1] > TOL, f"the {side} upper plate does not lap over the back wall"
        assert up[0][2] == pytest.approx(back_lo[1][2], abs=TOL)


@pytest.mark.parametrize("over", [{"top_plate": "single"}, {"corner": "two-stud"}, {"corner": "california"}])
def test_other_details_still_generate_without_overlaps(over):
    for region in REGIONS:
        f = gen(region, **over)
        mem = [m for m in f["members"] if m["layer"] in ("floor", "walls", "roof")]
        bad = []
        for i, a in enumerate(mem):
            for b in mem[i + 1:]:
                if {a["kind"], b["kind"]} == {"rafter", "stud"} and "/infill-" in a["id"] + b["id"]:
                    continue        # square-boxed infill under a sloped rafter (cut_deg removes it)
                if penetration(a, b) > TOL:
                    bad.append((a["id"], b["id"]))
        assert not bad, bad[:5]
        if over.get("top_plate") == "single":
            assert not any(m["id"].endswith("/plate-top-2") for m in f["members"])


def test_a_door_too_tall_for_the_header_says_how_tall_it_can_be():
    spec = load_fixture("shed-eu")
    spec["openings"][0]["height"] = 2100
    with pytest.raises(fr.SpecError, match=r"openings\[0\]\.height: .* the most this door can be is"):
        fr.generate(spec)


# ------------------------------------------------------------- floor (F2)

def _frame_dims(f):
    spec = f["spec"]
    lib = fr.tl.load(spec["region"])
    item = lambda k: fr.tl.item(lib, spec[k])
    return spec, lib, item


@pytest.mark.parametrize("depth", [None, 3000])
def test_floor_deck_and_blocking_are_symmetric_about_mid_span(depth):
    for region in REGIONS:
        f = gen(region, **({"depth": depth} if depth else {}))
        spec, lib, item = _frame_dims(f)
        D = spec["depth"]
        short = item("floor_deck")["size_mm"][0]
        deck = [m for m in f["members"] if m["group"] == "floor" and m["kind"] == "sheet"]
        seams = sorted({round(float(aabb(m)[0][1]), 1) for m in deck} - {0.0})
        assert seams == pytest.approx([D - y for y in reversed(seams)], abs=TOL), (region, seams)
        rows = [0.0] + seams + [D]
        assert min(np.diff(rows)) >= short / 2 - TOL, "no row narrower than half a sheet"
        blocks = [m for m in f["members"] if m["group"] == "floor" and m["kind"] == "blocking"]
        ys = sorted({round(float((aabb(m)[0][1] + aabb(m)[1][1]) / 2), 1) for m in blocks})
        assert ys == pytest.approx([D - y for y in reversed(ys)], abs=TOL), (region, ys)
        for y in seams:
            assert any(abs(y - b) <= TOL for b in ys), f"the deck seam at {y} has no blocking under it"
        tj = item("floor_item")["thickness_mm"]
        stops = [tj] + ys + [D - tj]
        assert max(np.diff(stops)) <= 1500 + TOL


# -------------------------------------------------------------- roof (F2)

def _rafters(f, flying=False):
    r = [m for m in f["members"] if m["kind"] == "rafter" and ("/flying-" in m["id"]) == flying]
    return sorted(r, key=lambda m: aabb(m)[0][0])


def test_blocking_closes_every_rafter_bay_over_both_walls(shed):
    spec, lib, item = _frame_dims(shed)
    w, D = item("frame_item")["width_mm"], spec["depth"]
    rafters = _rafters(shed)
    blocks = [m for m in shed["members"] if m["group"] == "roof" and m["kind"] == "blocking"]
    for a, b in zip(rafters, rafters[1:]):
        x0, x1 = aabb(a)[1][0], aabb(b)[0][0]
        if x1 - x0 < TOL:
            continue
        for wall_lo, wall_hi, name in ((0.0, w, "front"), (D - w, D, "back")):
            over = [m for m in blocks if aabb(m)[0][0] <= x0 + TOL and aabb(m)[1][0] >= x1 - TOL
                    and aabb(m)[0][1] >= wall_lo - 30 and aabb(m)[1][1] <= wall_hi + TOL]
            assert over, f"the bay between {a['id']} and {b['id']} is open over the {name} wall"
            for m in over:
                assert penetration(m, a) >= -TOL and penetration(m, b) >= -TOL, "blocking fills the bay"


def test_fascia_covers_the_rafter_ends_front_and_back(shed):
    spec, lib, item = _frame_dims(shed)
    by = by_id(shed)
    oh, os_ = spec["overhang"], spec["overhang_side"]
    tf = item("fascia_item")["thickness_mm"]
    ends = _rafters(shed) + _rafters(shed, True)
    for name, face in (("front", -oh), ("back", spec["depth"] + oh)):
        fa = by[f"roof/fascia-{name}"]
        lo, hi = aabb(fa)
        assert lo[0] == pytest.approx(-os_ - tf, abs=TOL) and hi[0] == pytest.approx(spec["width"] + os_ + tf, abs=TOL)
        assert (hi[1] if name == "front" else lo[1]) == pytest.approx(face, abs=TOL)
        for r in ends:
            assert penetration(fa, r) == pytest.approx(0, abs=TOL), f"{r['id']} end is not on the {name} fascia"
            rl, rh = aabb(r)
            assert (rl[1] if name == "front" else rh[1]) == pytest.approx(face, abs=TOL), "plumb cut on the fascia line"


def test_side_overhang_is_a_ladder_with_a_flying_rafter_and_a_bargeboard(shed):
    spec, lib, item = _frame_dims(shed)
    by = by_id(shed)
    os_, W = spec["overhang_side"], spec["width"]
    tr = item("rafter_item")["thickness_mm"]
    fly = _rafters(shed, True)
    common = _rafters(shed)
    assert [round(float(aabb(m)[0][0]), 1) for m in fly] == pytest.approx([-os_, W + os_ - tr], abs=TOL)
    for side, f, end in (("left", fly[0], common[0]), ("right", fly[1], common[-1])):
        outs = sorted((m for m in shed["members"] if m["id"].startswith(f"roof/outrigger-{side}-")),
                      key=lambda m: aabb(m)[0][1])
        assert len(outs) >= 3
        for o in outs:
            assert penetration(o, f) == pytest.approx(0, abs=TOL) and penetration(o, end) == pytest.approx(0, abs=TOL)
        cy = [float((aabb(o)[0][1] + aabb(o)[1][1]) / 2) for o in outs]
        assert max(np.diff(cy)) <= spec["rafter_spacing"] + 50, "outriggers no further apart than the rafters"
        fl, fh = aabb(f)
        assert cy[0] - fl[1] < 200 and fh[1] - cy[-1] < 200, "an outrigger at each end of the flying rafter"
        bb = by[f"roof/bargeboard-{side}"]
        assert penetration(bb, f) == pytest.approx(0, abs=TOL)
    # the roof deck covers the overhang too, out to the bargeboards' outer faces
    deck = [m for m in shed["members"] if m["group"] == "roof" and m["kind"] == "sheet"]
    tf = tl.item(tl.load(spec["region"]), spec["fascia_item"])["thickness_mm"]
    assert min(aabb(m)[0][0] for m in deck) == pytest.approx(-os_ - tf, abs=TOL)
    assert max(aabb(m)[1][0] for m in deck) == pytest.approx(W + os_ + tf, abs=TOL)


def test_no_side_overhang_puts_the_bargeboard_on_the_end_rafter():
    for region in REGIONS:
        f = gen(region, overhang_side=0)
        assert not _rafters(f, True)
        assert not any(m["kind"] == "outrigger" for m in f["members"])
        by = by_id(f)
        assert penetration(by["roof/bargeboard-left"], _rafters(f)[0]) == pytest.approx(0, abs=TOL)


@pytest.mark.parametrize("bad", [60, 500])
def test_a_side_overhang_that_cannot_be_built_says_what_works(bad):
    with pytest.raises(fr.SpecError, match=r"overhang_side: .* use 0 \(no side overhang\) or"):
        gen("eu", overhang_side=bad)


def test_side_cladding_stops_at_the_rafter_line(shed):
    spec, lib, item = _frame_dims(shed)
    w = item("frame_item")["width_mm"]
    hf, hb, D = spec["height_front"], spec["height_back"], spec["depth"]
    k = (hf - hb) / (D - w)
    for m in shed["members"]:
        if m["kind"] == "board" and m["group"] in ("wall-left", "wall-right"):
            for p in corners(m):
                y = min(max(p[1], w), D)
                assert p[2] <= hf - (y - w) * k + TOL, f"{m['id']} rises above the roof line"


# ----------------------------------------------- nothing floats, nothing strays

def _touch(a, b, tol=1.0):
    """True when two members' prisms meet or are within tol of each other."""
    ca, cb = corners(a), corners(b)
    na, ea = _sat(a)
    nb, eb = _sat(b)
    axs = na + nb + [np.cross(u, v) / np.linalg.norm(np.cross(u, v))
                     for u in ea for v in eb if np.linalg.norm(np.cross(u, v)) > 1e-6]
    for n in axs:
        pa, pb = ca @ n, cb @ n
        if min(pa.max(), pb.max()) - max(pa.min(), pb.min()) < -tol:
            return False
    return True


SHEDS = ["tests/fixtures/shed-eu.json", "tests/fixtures/shed-us.json",
         "examples/garden-shed/structure.json", "tests/fixtures/tool-shed.json"]


@pytest.mark.parametrize("path", SHEDS)
def test_every_member_touches_another_and_none_strays_outside(path):
    import json, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, path), encoding="utf-8") as fh:
        f = fr.generate(json.load(fh))
    spec, lib, item = _frame_dims(f)
    mem = f["members"]
    boxes = [aabb(m) for m in mem]
    alone = []
    for i, a in enumerate(mem):
        la, ha = boxes[i]
        if not any(j != i and np.all(np.minimum(ha, boxes[j][1]) - np.maximum(la, boxes[j][0]) >= -1.0)
                   and _touch(a, mem[j]) for j in range(len(mem))):
            alone.append(a["id"])
    assert not alone, f"floating: {alone[:8]}"
    # inside the footprint plus the overhangs, fascia and the wall skins
    skin = item("sheathing")["thickness_mm"] + item("cladding")["thickness_mm"]
    tf = item("fascia_item")["thickness_mm"]
    ex = max(spec["overhang_side"] + tf, skin) + TOL
    ey = max(spec["overhang"] + tf + item("roof_deck")["thickness_mm"], skin) + TOL   # a square-cut deck edge on the slope
    for m, (lo, hi) in zip(mem, boxes):
        assert lo[0] >= -ex and hi[0] <= spec["width"] + ex, m["id"]
        assert lo[1] >= -ey and hi[1] <= spec["depth"] + ey, m["id"]
        assert lo[2] >= -TOL, m["id"]
