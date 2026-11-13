"""Tests for tools/framecheck.py, the build checks for a timber frame.

    .venv/bin/python -m pytest tests/test_framecheck.py

Each layout rule has one frame that passes it and one that trips it. The span
formulas are compared with published span tables (the sources and the dates
they were read are in docs/research/timber-structures.md, T4).
"""
import copy, json, os, subprocess, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import frame as fr  # noqa: E402
import framecheck as fc  # noqa: E402
import timberlib as tl  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
REGIONS = ["eu", "us"]


def spec_for(region, **over):
    """The fixture shed with only its door (the left window is covered by its own test)."""
    with open(os.path.join(FIX, f"shed-{region}.json"), encoding="utf-8") as f:
        s = json.load(f)
    s["openings"] = [s["openings"][0]]
    if region == "eu":
        s["roof_deck"] = "osb-15"        # 12 mm on 600 mm rafters is over the library's limit
    else:
        s["floor_item"] = "2x8"          # the fixture's 2x6 joists use 86% of their span at L/360: a `check`
    s.update(over)
    return s


def frame_for(region, **over):
    return fr.generate(spec_for(region, **over))


def check(frame):
    out = fc.run(frame)
    return {x["id"]: x for x in out["findings"]}


def drop(frame, pred):
    """A copy of the frame without the members `pred` picks (and their joints)."""
    f = copy.deepcopy(frame)
    gone = {m["id"] for m in f["members"] if pred(m)}
    f["members"] = [m for m in f["members"] if m["id"] not in gone]
    f["joints"] = [j for j in f["joints"] if j["a"] not in gone and j["b"] not in gone]
    return f, gone


@pytest.fixture(scope="module", params=REGIONS)
def good(request):
    return request.param, frame_for(request.param)


# ---------------------------------------------------------------- the whole run

def test_clean_frame_has_nothing_to_fix_or_check(good):
    region, frame = good
    res = check(frame)
    assert {i: x["level"] for i, x in res.items() if x["level"] != "ok"} == {}
    assert res["guidance-only"]["level"] == "ok"


def test_findings_have_the_agreed_shape_and_end_with_the_disclaimer(good):
    _, frame = good
    out = fc.run(frame)
    assert out["findings"][-1]["id"] == "guidance-only"
    assert "not structural engineering" in out["findings"][-1]["text"]
    assert len({x["id"] for x in out["findings"]}) == len(out["findings"])
    for x in out["findings"]:
        assert set(x) == {"id", "level", "title", "text", "members", "at"}
        assert x["level"] in ("ok", "check", "fix")
        assert len(x["at"]) == 3 and all(isinstance(v, (int, float)) for v in x["at"])
        assert x["title"] and x["text"]
        for mid in x["members"]:
            assert mid in {m["id"] for m in frame["members"]}


@pytest.mark.parametrize("region", REGIONS)
def test_both_fixtures_run_and_use_their_units(region):
    with open(os.path.join(FIX, f"shed-{region}.json"), encoding="utf-8") as f:
        frame = fr.generate(json.load(f))
    out = fc.run(frame)
    text = " ".join(x["text"] for x in out["findings"])
    if region == "us":
        assert "psf" in text and "kN" not in text
    else:
        assert "kN/m2" in text and "psf" not in text


def test_cli_writes_the_file_and_is_repeatable(tmp_path):
    frame_path = tmp_path / "frame.json"
    frame_path.write_text(json.dumps(frame_for("eu")))
    outs = []
    for n in (1, 2):
        out = tmp_path / f"checks{n}.json"
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "framecheck.py"), str(frame_path), "--out", str(out)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]
    d = json.loads(outs[0])
    assert d["schema"] == 1 and d["findings"] and d["factors"]


def test_every_factor_names_its_source():
    for region, table in fc.FACTORS.items():
        for name, rec in table.items():
            assert rec.get("source"), f"{region}.{name}"
            assert rec.get("status") in ("published", "standard", "assumption"), f"{region}.{name}"


# --------------------------------------------------------------------- spans

@pytest.mark.parametrize("region", REGIONS)
def test_joist_span_passes_then_trips(region):
    item = "50x100" if region == "eu" else "2x4"
    assert check(frame_for(region))["span-joists"]["level"] == "ok"
    res = check(frame_for(region, depth=3600, floor_item=item))["span-joists"]
    assert res["level"] == "fix" and "good for about" in res["text"]


@pytest.mark.parametrize("region", REGIONS)
def test_rafter_span_passes_then_trips(region):
    item = "50x100" if region == "eu" else "2x4"
    assert check(frame_for(region))["span-rafters"]["level"] == "ok"
    res = check(frame_for(region, depth=3600, rafter_item=item, height_back=1500))["span-rafters"]
    assert res["level"] == "fix" and "snow load" in res["text"]


@pytest.mark.parametrize("region", REGIONS)
def test_header_span_passes_then_trips(region):
    frame = frame_for(region)
    ok = check(frame)["span-wall-front-header-01"]
    assert ok["level"] == "ok"
    long = copy.deepcopy(frame)
    h = next(m for m in long["members"] if m["id"] == "wall-front/header-01")
    h["size"][0] = 3600
    res = check(long)["span-wall-front-header-01"]
    assert res["level"] == "fix" and res["members"] == ["wall-front/header-01"]


def test_a_heavier_load_shortens_the_allowed_span(good):
    region, frame = good
    base = check(frame)["span-joists"]["text"]
    heavy = copy.deepcopy(frame)
    heavy["spec"]["loads"]["floor_kn_m2"] = 20.0
    assert check(heavy)["span-joists"]["text"] != base
    assert check(heavy)["span-joists"]["level"] in ("check", "fix")


def test_eu_and_us_grades_are_treated_differently():
    """C24 is a characteristic strength (factored loads, material factor); SPF No. 2 an
    allowable stress (unfactored loads). The same section and load must not give the same answer
    by accident."""
    eu, us = tl.load("eu"), tl.load("us")
    assert eu["grades"]["C24"]["basis"] == "characteristic"
    assert "allowable" in us["grades"]["SPF-No2"]["basis"]
    a = fc.allowable_span(eu, 38, 140, 0.2, 0.6, "floor")
    b = fc.allowable_span(us, 38, 140, 0.2, 0.6, "floor")
    assert a["span_mm"] != pytest.approx(b["span_mm"], rel=0.01)


# ------------------------------------------------- span tables (cross-check)
#
# EU: Timber Development UK, "C24 Span Tables", Timber Knowledge Sheet D.100.02-01, published
# 1 July 2023 (read 2026-11-11), https://www.taylormaxwell.co.uk/uploads/files/D.100.02-01_C24-Span-Tables_Design_Span-Tables.pdf
#   floor joists, imposed load 1.5 kN/m2, dead load excluding the joist's own weight, p. 6;
#   flat roof joists, imposed load 0.6 kN/m2, dead load excluding own weight, p. 4.
# Spans there are maximum clear spans in metres. The table does not state its deflection limit.
EU_TABLE = [
    # (what, breadth, depth, spacing mm, dead kN/m2, imposed kN/m2, load kind, table span m)
    ("floor", 45, 145, 600, 0.50, 1.5, "floor", 2.79),
    ("floor", 45, 195, 600, 0.25, 1.5, "floor", 3.97),
    ("floor", 45, 220, 400, 1.25, 1.5, "floor", 4.19),
    ("floor", 45, 145, 400, 0.25, 1.5, "floor", 3.07),
    ("floor", 72, 195, 600, 0.50, 1.5, "floor", 4.36),
    ("flat roof", 45, 145, 400, 0.50, 0.6, "snow", 3.43),
    ("flat roof", 45, 195, 600, 0.50, 0.6, "snow", 4.43),
    ("flat roof", 45, 220, 400, 0.75, 0.6, "snow", 5.15),
    ("flat roof", 72, 170, 600, 0.50, 0.6, "snow", 4.49),
]

# US: 2012 International Residential Code Table R502.3.1(2) "Floor joist spans for common lumber species"
# (residential living areas, live load 40 psf, L/360), Spruce-pine-fir #2, as printed in the 2012 Seattle
# Residential Code, chapter 5, p. 128-129 (read 2026-11-11),
# https://seattle.gov/documents/Departments/SDCI/Codes/SeattleResidentialCode/2012SRCChapter5.pdf
# Spans are inside to inside of bearings; the 10 or 20 psf dead load includes the joist. The table's
# own criteria are used: deflection under live load only, limit span / 360.
def ft(feet, inches):
    return (feet * 12 + inches) * 25.4


US_TABLE = [
    # (nominal depth, depth mm, spacing in, dead psf, table span mm)
    ("2x6", 140, 16, 10, ft(9, 4)),
    ("2x8", 184, 16, 10, ft(12, 3)),
    ("2x10", 235, 16, 10, ft(15, 5)),
    ("2x12", 286, 16, 10, ft(17, 10)),
    ("2x10", 235, 12, 10, ft(17, 3)),
    ("2x8", 184, 19.2, 20, ft(10, 6)),
    ("2x10", 235, 16, 20, ft(14, 1)),
    ("2x12", 286, 12, 20, ft(18, 10)),
]
PSF = 0.04788   # kN/m2 per psf


def eu_rows(defl_limit=None):
    lib = tl.load("eu")
    rows = []
    for what, b, d, s, gk, qk, kind, tab in EU_TABLE:
        sm = s / 1000.0
        calc = fc.allowable_span(lib, b, d, gk * sm, qk * sm, kind, defl_limit=defl_limit)["span_mm"] / 1000.0
        rows.append((what, b, d, s, calc, tab, (calc / tab - 1) * 100))
    return rows


def us_rows():
    lib = tl.load("us")
    rows = []
    for name, d, s, dl, tab in US_TABLE:
        sm = s * 25.4 / 1000.0
        calc = fc.allowable_span(lib, 38.1, d, dl * PSF * sm, 40 * PSF * sm, "floor", defl_limit=360,
                                 defl_basis="live", add_own_weight=False)["span_mm"]
        rows.append((name, s, dl, calc, tab, (calc / tab - 1) * 100))
    return rows


def test_eu_formulas_agree_with_the_c24_span_tables():
    rows = eu_rows()          # at the default span / 360
    assert len(rows) == 9
    assert all(abs(r[-1]) <= 15 for r in rows), rows


def test_us_formulas_agree_with_the_irc_span_table():
    rows = us_rows()          # the table's own criterion: live-load deflection, span / 360
    assert len(rows) == 8
    assert all(abs(r[-1]) <= 15 for r in rows), rows


def test_default_deflection_limit_is_span_over_360():
    assert fc.FACTORS["common"]["deflection_limit"]["value"] == 360


# ------------------------------------------------------------- layout rules

@pytest.mark.parametrize("region", REGIONS)
def test_default_sheets_suit_the_default_spacing(region):
    """A shed on the library defaults passes the sheet-spacing check."""
    frame = fr.generate({"type": "pent-shed", "region": region, "width": 2400, "depth": 1800})
    assert check(frame)["sheet-spacing"]["level"] == "ok"


@pytest.mark.parametrize("region", REGIONS)
def test_sheet_spacing_passes_then_trips(region):
    assert check(frame_for(region))["sheet-spacing"]["level"] == "ok"
    if region == "eu":
        bad = frame_for("eu", roof_deck="osb-12")                  # 12 mm on 600 mm rafters
    else:
        bad = frame_for("us", floor_deck="osb-12", joist_spacing=609.6)   # 15/32 in. floor at 24 in.
    res = check(bad)["sheet-spacing"]
    assert res["level"] == "check" and "limit" in res["text"] and res["members"]


@pytest.mark.parametrize("region", REGIONS)
def test_sheet_edge_passes_then_trips(region):
    frame = frame_for(region)
    assert check(frame)["sheet-edge"]["level"] == "ok"
    bad, gone = drop(frame, lambda m: m["kind"] == "blocking" and m["group"] == "floor")
    assert gone
    res = check(bad)["sheet-edge"]
    assert res["level"] == "fix" and res["members"]


@pytest.mark.parametrize("region", REGIONS)
def test_stock_length_passes_then_trips(region):
    frame = frame_for(region)
    assert check(frame)["stock-length"]["level"] == "ok"
    bad = copy.deepcopy(frame)
    rafter = next(m for m in bad["members"] if m["kind"] == "rafter")
    rafter["size"][0] = 20000
    res = check(bad)["stock-length"]
    assert res["level"] == "fix" and rafter["id"] in res["members"]


@pytest.mark.parametrize("region", REGIONS)
def test_opening_frame_passes_then_trips(region):
    frame = frame_for(region)
    assert check(frame)["opening-frame"]["level"] == "ok"
    for kinds in ({"header"}, {"jack"}, {"king"}):
        bad, gone = drop(frame, lambda m, k=kinds: m["group"] == "wall-front" and m["kind"] in k)
        assert gone
        assert check(bad)["opening-frame"]["level"] == "fix"


@pytest.mark.parametrize("region", REGIONS)
def test_ground_treated_passes_then_trips(region):
    assert check(frame_for(region))["ground-treated"]["level"] == "ok"
    res = check(frame_for(region, treated_floor=False))["ground-treated"]
    assert res["level"] == "check" and res["members"]


@pytest.mark.parametrize("region", REGIONS)
def test_roof_pitch_passes_then_trips(region):
    assert check(frame_for(region))["roof-pitch"]["level"] == "ok"
    res = check(frame_for(region, height_back=spec_for(region)["height_front"] - 100))["roof-pitch"]   # 100 mm fall: about 2-3 degrees
    assert res["level"] == "fix" and "degrees" in res["text"]


def test_roof_pitch_uses_the_covering():
    frame = frame_for("eu")
    shingle = copy.deepcopy(frame)
    shingle["spec"]["roofing"] = "asphalt-shingle"     # needs 15 degrees; the shed has about 9
    assert check(shingle)["roof-pitch"]["level"] == "fix"
    odd = copy.deepcopy(frame)
    odd["spec"]["roofing"] = "thatch"
    assert check(odd)["roof-pitch"]["level"] == "check"


@pytest.mark.parametrize("region", REGIONS)
def test_wall_bracing_passes_then_trips(region):
    frame = frame_for(region)
    assert check(frame)["wall-bracing"]["level"] == "ok"
    bad, gone = drop(frame, lambda m: m["group"] == "wall-back" and m["kind"] == "sheet")
    assert gone
    res = check(bad)["wall-bracing"]
    assert res["level"] == "fix" and "back" in res["text"]
    braced = copy.deepcopy(bad)
    brace = copy.deepcopy(next(m for m in frame["members"] if m["group"] == "wall-back" and m["kind"] == "stud"))
    brace.update(id="wall-back/brace-01", kind="brace")
    braced["members"].append(brace)
    assert check(braced)["wall-bracing"]["level"] == "ok"


# ------------------------------------------------------ framing conventions (F4)

def edited(region, *edits, **over):
    """The example frame with edits by piece applied (frame_edits.py)."""
    return frame_for(region, edits=list(edits), **over)


CONVENTION_IDS = ("opening-frame", "corner-fixing", "plate-lap", "roof-bay-blocking", "roof-edges",
                  "floating-piece", "floor-blocking-symmetry")


@pytest.mark.parametrize("region", REGIONS)
def test_conventions_pass_on_the_example(region):
    res = check(frame_for(region))
    for i in CONVENTION_IDS:
        assert res[i]["level"] == "ok", i


@pytest.mark.parametrize("path", ["examples/garden-shed/structure.json", "tests/fixtures/tool-shed.json"])
def test_conventions_pass_on_the_example_projects(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        res = check(fr.generate(json.load(f)))
    for i in CONVENTION_IDS:
        assert res[i]["level"] == "ok", i


@pytest.mark.parametrize("region", REGIONS)
def test_header_bearing_and_kings_trip_when_the_header_is_lifted_off_its_jacks(region):
    frame = edited(region, {"op": "move", "id": "wall-front/header-01", "by": [0, 0, 300]})
    res = check(frame)["opening-frame"]
    assert res["level"] == "fix" and "resting on both jack studs" in res["text"]
    assert "wall-front/header-01" in res["members"] or "wall-front/jack-01" in res["members"]


@pytest.mark.parametrize("region", REGIONS)
def test_every_jack_needs_a_king(region):
    bad, _ = drop(frame_for(region), lambda m: m["id"] == "wall-front/king-01")
    res = check(bad)["opening-frame"]
    assert res["level"] == "fix"


@pytest.mark.parametrize("region", REGIONS)
@pytest.mark.parametrize("piece", ["wall-front/corner-01-stud", "wall-back/corner-02-stud"])
def test_corner_fixing_trips_when_a_corner_piece_is_removed(region, piece):
    if region == "us" and not any(m["id"] == piece for m in frame_for(region)["members"]):
        pytest.skip("this region's example uses another corner style")
    res = check(edited(region, {"op": "remove", "id": piece}))["corner-fixing"]
    assert res["level"] == "fix" and "corner" in res["text"]


def test_corner_fixing_trips_when_the_side_end_stud_is_not_joined():
    frame = frame_for("eu")
    bad = copy.deepcopy(frame)
    end = next(j["a"] for j in frame["joints"] if j["type"] == "corner-stud"
               and j["a"].startswith("wall-left/") and j["b"].startswith("wall-back/"))
    assert end.startswith("wall-left/")
    bad["joints"] = [j for j in bad["joints"] if not (j["type"] == "corner-stud" and end in (j["a"], j["b"]))]
    res = check(bad)["corner-fixing"]
    assert res["level"] == "fix" and "left-back" in res["text"]


def test_corner_fixing_follows_the_corner_style():
    for style in ("california", "two-stud"):
        frame = frame_for("eu", corner=style)
        assert check(frame)["corner-fixing"]["level"] == "ok", style
    flat = frame_for("eu", corner="california")
    gone = next(m["id"] for m in flat["members"] if m["id"].startswith("wall-front/corner-01-flat"))
    res = check(edited("eu", {"op": "remove", "id": gone}, corner="california"))["corner-fixing"]
    assert res["level"] == "fix"


@pytest.mark.parametrize("region", REGIONS)
def test_plate_lap_trips_when_an_upper_plate_is_cut_short(region):
    assert check(frame_for(region))["plate-lap"]["level"] == "ok"
    res = check(edited(region, {"op": "resize", "id": "wall-left/plate-top-2", "length": 1000,
                                "keep": "start"}))["plate-lap"]
    assert res["level"] == "check" and "left" in res["text"]
    gone = check(edited(region, {"op": "remove", "id": "wall-right/plate-top-2"}))["plate-lap"]
    assert gone["level"] == "check" and "right" in gone["text"]


@pytest.mark.parametrize("region", REGIONS)
def test_plate_lap_is_not_asked_of_a_single_top_plate(region):
    res = check(frame_for(region, top_plate="single"))["plate-lap"]
    assert res["level"] == "ok" and "single" in res["text"]


@pytest.mark.parametrize("region", REGIONS)
def test_every_rafter_bay_over_a_wall_is_closed(region):
    frame = frame_for(region)
    assert len(fc._bays(fc.Findings(frame, tl.load(region)))) >= 3       # the check has bays to look at
    for side in ("front", "back"):
        gone = next(m["id"] for m in frame["members"] if m["id"].startswith(f"roof/eave-{side}-"))
        res = check(edited(region, {"op": "remove", "id": gone}))["roof-bay-blocking"]
        assert res["level"] == "check" and f"{side} wall" in res["text"], gone
        assert any(i.startswith("roof/rafter-") for i in res["members"])


@pytest.mark.parametrize("region", REGIONS)
def test_a_roof_block_away_from_the_wall_does_not_close_the_bay(region):
    frame = frame_for(region)
    eave = next(m["id"] for m in frame["members"] if m["id"].startswith("roof/eave-front-"))
    res = check(edited(region, {"op": "move", "id": eave, "by": [0, 900, -300]}))["roof-bay-blocking"]
    assert res["level"] == "check"


@pytest.mark.parametrize("region", REGIONS)
def test_fascia_and_bargeboards_are_present(region):
    assert check(frame_for(region))["roof-edges"]["level"] == "ok"
    for gone, word in (("roof/fascia-front", "front"), ("roof/fascia-back", "back"),
                       ("roof/bargeboard-left", "left"), ("roof/bargeboard-right", "right")):
        res = check(edited(region, {"op": "remove", "id": gone}))["roof-edges"]
        assert res["level"] == "check" and word in res["text"], gone


def test_no_fascia_is_asked_for_without_an_overhang():
    frame = frame_for("eu", overhang=0, overhang_side=0)
    res = check(frame)["roof-edges"]
    assert res["level"] == "ok"
    gone = check(edited("eu", {"op": "remove", "id": "roof/fascia-front"}, overhang=0, overhang_side=0))["roof-edges"]
    assert gone["level"] == "ok"


@pytest.mark.parametrize("region", REGIONS)
def test_a_floating_piece_is_flagged_by_name(region):
    res = check(edited(region, {"op": "move", "id": "floor/blocking-01", "by": [0, 0, -2000]}))["floating-piece"]
    assert res["level"] == "fix" and res["members"] == ["floor/blocking-01"]
    assert "floor/blocking-01" in res["text"]


def test_floating_lists_a_few_names_and_says_how_many_more():
    edits = [{"op": "move", "id": f"floor/blocking-{i:02d}", "by": [0, 0, -2000]} for i in range(1, 8)]
    res = check(edited("eu", *edits))["floating-piece"]
    assert res["level"] == "fix" and len(res["members"]) == 7
    assert "and 2 more" in res["text"]


@pytest.mark.parametrize("region", REGIONS)
def test_floor_blocking_symmetry_is_a_check_not_a_fix(region):
    assert check(frame_for(region))["floor-blocking-symmetry"]["level"] == "ok"
    res = check(edited(region, {"op": "move", "id": "floor/blocking-01", "by": [0, 120, 0]}))["floor-blocking-symmetry"]
    assert res["level"] == "check" and "floor/blocking-01" in res["members"]
