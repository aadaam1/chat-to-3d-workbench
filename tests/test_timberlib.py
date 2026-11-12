"""Tests for tools/timberlib.py and the libraries in data/timber/library/.

    .venv/bin/python -m pytest tests/test_timberlib.py
"""
import os, subprocess, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import timberlib as tl  # noqa: E402

REGIONS = ["eu", "us"]
PLAN_KEYS = ["50x100", "50x150", "osb-12", "osb-18", "shiplap-19x121", "nail-framing",
             "nail-sheathing", "roofing-felt"]


@pytest.fixture(scope="module", params=REGIONS)
def lib(request):
    return tl.load(request.param)


def test_libraries_validate(lib):
    assert tl.validate(lib) == []


def test_every_default_points_at_an_existing_item(lib):
    for role, key in lib["defaults"]["items"].items():
        assert tl.item(lib, key)["key"] == key, role
    assert lib["defaults"]["grade"] in lib["grades"]


def test_every_joint_rule_names_an_existing_fastener(lib):
    rules = {t: r for t, r in lib["joint_rules"].items() if not t.startswith("_")}
    assert set(tl.JOINT_TYPES) <= set(rules)
    for t, r in rules.items():
        for part in [r] + r.get("also", []):
            assert part["fastener"] in lib["fasteners"], t


def test_nails_are_sold_by_weight_and_screws_in_packs(lib):
    for k, d in lib["fasteners"].items():
        if d["type"] == "nail":
            u = d["weight_unit"]
            assert u == ("kg" if lib["region"] == "eu" else "lb"), k
            assert d[f"pcs_per_{u}"] > 0 and d[f"box_{u}"] == sorted(d[f"box_{u}"]), k
        else:
            assert d["type"] == "screw" and d["pack_sizes"], k
    assert {k for k, d in lib["fasteners"].items() if d["type"] == "screw"} == {"screw-rafter", "screw-corner"}


def test_old_screw_keys_give_a_clear_error(lib):
    with pytest.raises(KeyError, match="not in the"):
        tl.item(lib, "screw-5x100")


def test_validate_catches_a_nail_without_a_weight(lib):
    import copy
    bad = copy.deepcopy(lib)
    del bad["fasteners"]["nail-framing"]["pcs_per_" + bad["fasteners"]["nail-framing"]["weight_unit"]]
    assert any("nail-framing" in p for p in tl.validate(bad))


def test_every_source_reference_exists(lib):
    ids = {s["id"] for s in lib["sources"]}
    assert len(ids) == len(lib["sources"])
    for s in lib["sources"]:
        assert s["title"] and s["url"] and s["read"]
    for cat in tl.CATEGORIES + ("grades",):
        for k, d in lib[cat].items():
            assert d["sources"] and set(d["sources"]) <= ids, (cat, k)


def test_plan_keys_exist_in_eu():
    eu = tl.load("eu")
    for k in PLAN_KEYS:
        tl.item(eu, k)
    assert "C24" in eu["grades"]


def test_us_has_osb_and_real_dressed_sizes():
    us = tl.load("us")
    assert "SPF-No2" in us["grades"]
    for k in ("osb-12", "osb-18", "nail-framing", "nail-sheathing", "roofing-felt"):
        tl.item(us, k)
    two_by_four = tl.item(us, "2x4")
    assert (two_by_four["thickness_mm"], two_by_four["width_mm"]) == (38, 89)
    sizes = {k: (d["thickness_mm"], d["width_mm"]) for k, d in us["sections"].items()}
    assert sizes == {"1x4": (19, 89), "2x2": (38, 38), "2x3": (38, 64), "2x4": (38, 89),
                     "2x6": (38, 140), "2x8": (38, 184), "2x10": (38, 235), "4x4": (89, 89)}
    assert us["sections"]["2x4"]["stock_lengths_mm"][0] == 2438   # 8 ft
    assert us["sections"]["2x4"]["stock_lengths_mm"][-1] == 4877  # 16 ft


def test_eu_sections_are_the_planned_nine():
    eu = tl.load("eu")
    assert sorted(eu["sections"]) == sorted(
        ["25x50", "25x100", "50x50", "50x75", "50x100", "50x150", "50x200", "75x75", "100x100"])


def test_grade_values_from_the_published_tables():
    c24 = tl.load("eu")["grades"]["C24"]
    assert (c24["bending_mpa"], c24["e_mean_mpa"], c24["density_kg_m3"]) == (24, 11000, 350)
    spf = tl.load("us")["grades"]["SPF-No2"]
    assert (spf["bending_psi"], spf["e_mean_psi"], spf["specific_gravity"]) == (875, 1400000, 0.42)
    assert spf["bending_mpa"] == pytest.approx(6.03, abs=0.01)


def test_unverified_values_are_listed(lib):
    assert tl.unverified(lib)   # fasteners and joint rules are marked, never silently trusted
    for k, d in lib["fasteners"].items():
        assert d.get("unverified"), k


def test_unknown_item_and_region():
    with pytest.raises(KeyError):
        tl.item(tl.load("eu"), "nope")
    with pytest.raises(ValueError):
        tl.load("xx")


def test_validate_catches_broken_libraries():
    eu = tl.load("eu")
    eu["defaults"]["items"]["frame"] = "50x999"
    eu["joint_rules"]["stud-plate"]["fastener"] = "nail-none"
    problems = " ".join(tl.validate(eu))
    assert "50x999" in problems and "nail-none" in problems


# ------------------------------------------------------------------- lengths

METRIC = [1, 12, 38, 89, 100, 150, 450, 600, 900, 1200, 1250, 1950, 2000, 2300, 2400, 2438,
          3000, 3658, 4500, 9000]
SIXTEENTHS = [1, 3, 8, 16, 17, 24, 100, 143, 188, 190, 575, 1000, 1157, 1680, 3000, 3600,
              5000, 7500, 12345, 15360]


def test_metric_round_trip():
    assert len(METRIC) == 20
    for mm in METRIC:
        assert tl.parse_length(tl.fmt_length(mm, "metric")) == pytest.approx(mm, abs=0.05)


def test_imperial_round_trip():
    assert len(SIXTEENTHS) == 20
    for n in SIXTEENTHS:
        mm = n * 25.4 / 16
        text = tl.fmt_length(mm, "imperial")
        assert tl.parse_length(text) == pytest.approx(mm, abs=1e-6), text


def test_imperial_rounds_to_sixteenths():
    for mm in (0.4, 10.0, 99.9, 2400.0, 2438.4, 1234.5678):
        back = tl.parse_length(tl.fmt_length(mm, "imperial"))
        assert abs(back - mm) <= 25.4 / 32 + 1e-9


def test_formats():
    assert tl.fmt_length(2400, "metric") == "2400 mm"
    assert tl.fmt_length(2400.0, "imperial") == "7' 10-1/2\""
    assert tl.fmt_length(2438.4, "imperial") == "8'"
    assert tl.fmt_length(89, "imperial") == "3-1/2\""
    assert tl.fmt_length(12.7, "imperial") == "1/2\""
    assert tl.fmt_length(0, "imperial") == "0\""
    assert tl.fmt_length(2438.4, "metric") == "2438.4 mm"
    with pytest.raises(ValueError):
        tl.fmt_length(1, "furlongs")


@pytest.mark.parametrize("text,mm", [
    ("2400", 2400), ("2400 mm", 2400), ("2.4 m", 2400), ("240 cm", 2400), ("2,4 m".replace(",", "."), 2400),
    ("7' 10-1/2\"", 2400.3), ("7'-10 1/2\"", 2400.3), ("7 ft 10 1/2 in", 2400.3), ("8'", 2438.4),
    ("96\"", 2438.4), ("96 in", 2438.4), ("3-1/2\"", 88.9), ("1/2\"", 12.7), ("3.5 in", 88.9),
    ("5 ft 3 in", 1600.2),
])
def test_parse_forms(text, mm):
    assert tl.parse_length(text) == pytest.approx(mm, abs=0.1)


@pytest.mark.parametrize("text", ["", "abc", "12 parsecs", "10 1/2"])
def test_parse_rejects(text):
    with pytest.raises(ValueError):
        tl.parse_length(text)


# --------------------------------------------------------------------- prices

@pytest.fixture(scope="module")
def rows():
    return tl.load_snapshot(tl.newest_snapshot("hu"))


def test_hungarian_snapshot_prices_a_50x100_3m_piece(rows):
    eu = tl.load("eu")
    p = tl.price_for(rows, tl.item(eu, "50x100"), 3000, "sawn")
    assert p and p["currency"] == "HUF" and p["price_gross"] > 0
    assert (p["row"]["thickness_mm"], p["row"]["width_mm"], p["row"]["length_mm"]) == (50, 100, 3000)
    # the same piece impregnated costs more
    q = tl.price_for(rows, tl.item(eu, "50x100"), 3000, "impregnated")
    assert q["price_gross"] > p["price_gross"]


def test_price_for_sheets_and_misses(rows):
    eu = tl.load("eu")
    osb = tl.price_for(rows, tl.item(eu, "osb-12"))
    assert osb and osb["row"]["kind"] == "sheet" and osb["price_gross"] > 0
    assert tl.price_for(rows, tl.item(eu, "50x100"), 3100, "sawn") is None   # no such length
    assert tl.price_for(rows, tl.item(eu, "75x75"), 3000, "sawn") is None    # supplier lacks it
    assert tl.price_for(rows, tl.item(eu, "nail-framing")) is None            # not in the snapshot
    assert tl.price_for(rows, tl.item(tl.load("us"), "2x4"), 2438, "sawn") is None


# ----------------------------------------------- timber.py still gives its output

@pytest.mark.parametrize("args,expect", [
    (["classify", "50x100"], "50 x 100 mm: palló (plank); usually wall studs, plates, light joists"),
    (["buy", "50x100", "2400", "12", "--variant", "impregnated"], "12 cuts needed + 2 spare"),
])
def test_timber_cli_unchanged(args, expect):
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "timber.py"), *args],
                         capture_output=True, text=True, check=True).stdout
    assert expect in out


def test_timber_cli_errors_as_before():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "timber.py"), "classify", "wide"],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "section must look like 50x100 (mm), not 'wide'" in r.stderr
