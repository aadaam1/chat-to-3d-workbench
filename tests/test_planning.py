"""The planner: sections, spacings and heights the description leaves open are chosen so the frame
builds without a "fix" (and without a span "check"); what the person names is never overridden;
every choice is recorded as a decision; `tools/frame.py --types` and `--fields` list what can be built."""
import copy, json, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import frame as fm  # noqa: E402
import framecheck as fc  # noqa: E402
from timber import fields as fld, planning as pl, spans  # noqa: E402

DOOR = {"wall": "front", "kind": "door", "x": 1000, "width": 900, "height": 2000}
AUDIT = {
    "pent-5x4": {"type": "pent-shed", "width": 5000, "depth": 4000},
    "gable-5x4": {"type": "gable-shed", "width": 5000, "depth": 4000},
    "kitchen-mono-5x4": {"type": "summer-kitchen", "width": 5000, "depth": 4000, "roof": "mono"},
    "pergola-6x4": {"type": "pergola", "width": 6000, "depth": 4000},
    "gable-4x3-door": {"type": "gable-shed", "width": 4000, "depth": 3000, "openings": [DOOR]},
}


def bad(frame, levels=("fix", "check")):
    """Findings at these levels, minus the ones about sheets and layout that the planner does not own."""
    out = fc.run(frame)["findings"]
    return [(x["id"], x["level"]) for x in out if x["level"] in levels and (x["level"] == "fix" or x["id"].startswith("span-"))]


# ------------------------------------------------------------------ the audit cases build clean

@pytest.mark.parametrize("name", sorted(AUDIT))
def test_audit_case_builds_with_no_fix_and_no_span_check(name):
    frame = fm.generate(copy.deepcopy(AUDIT[name]))
    assert bad(frame) == []


def test_the_span_engine_is_shared():
    assert fc.allowable_span is spans.allowable_span and fc.level_for is spans.level_for
    assert fc.FACTORS is spans.FACTORS


# ------------------------------------------------------------------ sizes

def test_default_that_passes_is_left_alone():
    frame = fm.generate({"type": "pent-shed", "width": 3000, "depth": 2000})
    sp = frame["spec"]
    assert (sp["floor_item"], sp["rafter_item"], sp["joist_spacing"], sp["rafter_spacing"]) == ("50x150", "50x150", 400, 600)
    assert (sp["height_front"], sp["height_back"]) == (2300, 2000)
    assert "decisions" not in frame


def test_smallest_section_that_fits_is_chosen_at_the_default_spacing():
    frame = fm.generate(AUDIT["pent-5x4"])
    sp = frame["spec"]
    assert (sp["floor_item"], sp["joist_spacing"]) == ("50x200", 400)
    assert (sp["rafter_item"], sp["rafter_spacing"]) == ("50x200", 600)
    assert sp["fascia_item"] == "50x200"                      # follows the rafter, as the default always did


def test_spacing_tightens_when_no_section_fits():
    frame = fm.generate({"type": "pent-shed", "width": 4000, "depth": 4400})
    sp = frame["spec"]
    assert sp["floor_item"] == "50x200" and sp["joist_spacing"] == 300
    assert bad(frame) == []


def test_nothing_fits_builds_with_the_best_and_the_check_reports():
    frame = fm.generate({"type": "pent-shed", "width": 4000, "depth": 6500})
    sp = frame["spec"]
    assert (sp["floor_item"], sp["joist_spacing"]) == ("50x200", 300)
    assert ("span-joists", "fix") in bad(frame)
    d = next(d for d in frame["decisions"] if d["what"] == "Floor joists")
    assert "best it can do" in d["why"]


def test_named_item_and_spacing_are_never_overridden_and_still_report():
    raw = {"type": "pent-shed", "width": 5000, "depth": 4000, "floor_item": "50x150", "joist_spacing": 400,
           "rafter_item": "50x150", "rafter_spacing": 600, "height_front": 2300, "height_back": 2000}
    frame = fm.generate(raw)
    sp = frame["spec"]
    assert (sp["floor_item"], sp["joist_spacing"], sp["rafter_item"], sp["rafter_spacing"]) == ("50x150", 400, "50x150", 600)
    assert (sp["height_front"], sp["height_back"]) == (2300, 2000)
    assert {"span-joists", "span-rafters", "roof-pitch"} <= {i for i, lv in bad(frame) if lv == "fix"}
    assert "decisions" not in frame


def test_a_named_item_keeps_its_section_and_only_the_spacing_moves():
    frame = fm.generate({"type": "pent-shed", "width": 5000, "depth": 4000, "floor_item": "50x150"})
    sp = frame["spec"]
    assert sp["floor_item"] == "50x150" and sp["joist_spacing"] == 300
    assert "50×150 at 300 mm" in next(d for d in frame["decisions"] if d["what"] == "Floor joists")["chose"]


def test_a_named_spacing_keeps_its_spacing_and_only_the_section_moves():
    frame = fm.generate({"type": "pent-shed", "width": 5000, "depth": 4000, "joist_spacing": 400})
    assert (frame["spec"]["floor_item"], frame["spec"]["joist_spacing"]) == ("50x200", 400)


def test_us_region_is_planned_in_its_own_sizes():
    frame = fm.generate({"type": "pent-shed", "width": 4000, "depth": 3000, "region": "us", "units": "imperial"})
    assert frame["spec"]["floor_item"] == "2x8"
    d = frame["decisions"][0]
    assert "'" in d["why"] or '"' in d["why"]                 # feet and inches, the frame's units
    assert bad(frame) == []


def test_pergola_and_kitchen_rafters_and_header():
    pe = fm.generate(AUDIT["pergola-6x4"])
    assert pe["spec"]["rafter_item"] == "50x200"
    ki = fm.generate(AUDIT["kitchen-mono-5x4"])
    assert ki["spec"]["rafter_item"] == "50x200" and ki["spec"]["fascia_item"] == "50x200"
    # a wide opening needs a deeper header than the studs
    wide = fm.generate({"type": "pent-shed", "width": 4000, "depth": 3000, "height_front": 2600, "height_back": 2300,
                        "openings": [{"wall": "front", "kind": "door", "x": 600, "width": 2400, "height": 2000}]})
    assert wide["spec"]["header_item"] != "50x100"
    assert [i for i, lv in bad(wide) if i.startswith("span-")] == []


# ------------------------------------------------------------------ decisions

def test_decisions_have_what_chose_why():
    frame = fm.generate(AUDIT["pent-5x4"])
    ds = frame["decisions"]
    assert {d["what"] for d in ds} == {"Floor joists", "Rafters", "Wall heights"}
    for d in ds:
        assert set(d) == {"what", "chose", "why"} and all(isinstance(v, str) and v for v in d.values())
    j = next(d for d in ds if d["what"] == "Floor joists")
    assert j["chose"] == "50×200 at 400 mm"
    assert j["why"] == "50×150 at 400 mm is good for 3.66 m; the span is 3.95 m"


def test_outdoor_layout_choices_are_decisions():
    te = fm.generate({"type": "terrace", "width": 4000, "depth": 3000, "height": 600})
    assert [d["what"] for d in te["decisions"]] == ["Beam rows", "Posts"]
    assert te["decisions"][0]["chose"].startswith("3 beam rows,")
    pe = fm.generate({"type": "pergola", "width": 5000, "depth": 3000})
    assert [d["what"] for d in pe["decisions"]] == ["Posts"]
    ki = fm.generate({"type": "summer-kitchen", "width": 4000, "depth": 3000})
    assert [d["what"] for d in ki["decisions"]] == ["Posts"]


def test_named_spacings_are_not_decisions():
    te = fm.generate({"type": "terrace", "width": 4000, "depth": 3000, "height": 600, "row_spacing": 1500, "post_spacing": 1800})
    assert "decisions" not in te


def test_decisions_are_in_the_shopping_list_and_dropped_from_the_hashes():
    import bom, golden
    frame = fm.generate(AUDIT["pent-5x4"])
    b = bom.make_bom(frame, None, 10, 4)
    assert b["decisions"] == frame["decisions"]
    md = bom.render_md(b)
    assert "How it was planned" in md and md.index("How it was planned") < md.index("## Timber and cladding")
    assert md.index("How it was planned") > md.index(bom.SAFETY_NOTE[:30])
    plain = bom.render_md(bom.make_bom(fm.generate({"type": "pent-shed", "width": 3000, "depth": 2000}), None, 10, 4))
    assert "How it was planned" not in plain
    assert "decisions" not in json.loads(json.dumps(golden.outputs(AUDIT["pent-5x4"])["bom"]))


# ------------------------------------------------------------------ default heights

def deg(frame):
    sp = frame["spec"]
    import math
    run = sp["depth"] - 100
    return math.degrees(math.atan((sp["height_front"] - sp["height_back"]) / run))


def test_default_pent_roof_drains_without_moving_cases_that_already_did():
    deep = fm.generate({"type": "pent-shed", "width": 3000, "depth": 4000})
    assert deg(deep) >= 5 + 2 - 0.5 and deep["spec"]["height_front"] >= 2300
    for depth in (1800, 2000, 3000):                          # the old defaults were already fine here
        f = fm.generate({"type": "pent-shed", "width": 3000, "depth": depth})
        assert (f["spec"]["height_front"], f["spec"]["height_back"]) == (2300, 2000)
    assert deg(fm.generate({"type": "pent-shed", "width": 3000, "depth": 3000})) >= 5


def test_default_height_rises_for_a_door_in_steps_of_50():
    f = fm.generate(AUDIT["gable-4x3-door"])
    assert f["spec"]["height_eaves"] == 2400
    d = f["decisions"][0]
    assert d["what"] == "Eaves height" and "2.37 m" in d["why"]
    p = fm.generate({"type": "pent-shed", "width": 3000, "depth": 2000,
                     "openings": [{"wall": "front", "kind": "door", "x": 1000, "width": 900, "height": 2200}]})
    assert (p["spec"]["height_front"], p["spec"]["height_back"]) == (2600, 2000)       # the door needs 2.57 m: the front rises, the back stays


def test_given_heights_are_not_raised():
    with pytest.raises(fm.SpecError):
        fm.generate({"type": "gable-shed", "width": 4000, "depth": 3000, "height_eaves": 2000, "openings": [DOOR]})
    f = fm.generate({"type": "pent-shed", "width": 3000, "depth": 2000, "height_front": 2300, "height_back": 2000})
    assert "decisions" not in f


def test_error_says_what_height_would_work():
    with pytest.raises(fm.SpecError) as e:
        fm.generate({"type": "gable-shed", "width": 4000, "depth": 3000, "height_eaves": 2000, "openings": [DOOR]})
    msg = str(e.value)
    assert "the most this door can be is 1632 mm" in msg and "set height_eaves to at least 2368" in msg
    # and the number works
    fm.generate({"type": "gable-shed", "width": 4000, "depth": 3000, "height_eaves": 2368, "openings": [DOOR]})
    with pytest.raises(fm.SpecError) as e2:
        fm.generate({"type": "pent-shed", "width": 4000, "depth": 3000, "height_front": 2000, "height_back": 1700, "openings": [DOOR]})
    assert "set height_front to at least" in str(e2.value)


# ------------------------------------------------------------------ the helper both the terrace and the pergola use

def test_spacing_under():
    assert pl.spacing_under(5000.0, 2000.0) == (2000.0, "cap", 2000.0)
    sp, why, lim = pl.spacing_under(2900.0, 2400.0)
    assert (sp, why) == (2300.0, "span") and lim == pytest.approx(2320.0)
    assert pl.spacing_under(700.0, 2000.0)[0] is None


# ------------------------------------------------------------------ --types and --fields

def test_types_lists_every_recipe(capsys):
    assert fm.main(["--types"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert [l.split()[0] for l in lines] == list(fm.TYPES)
    assert all(len(l.split()) > 4 for l in lines)


def test_fields_lists_defaults_in_the_regions_units(capsys):
    assert fm.main(["--fields", "terrace"]) == 0
    eu = capsys.readouterr().out
    assert "post_item" in eu and "default: 100x100" in eu and "at most 2000 mm" in eu
    assert fm.main(["--fields", "terrace", "--region", "us"]) == 0
    us = capsys.readouterr().out
    assert "default: 4x4" in us and "'" in us
    assert fm.main(["--fields", "nonsense"]) == 2


BASE = {"pent-shed": {"width": 3000, "depth": 2000}, "gable-shed": {"width": 3000, "depth": 2000},
        "terrace": {"width": 3000, "depth": 2000, "height": 500}, "pergola": {"width": 4000, "depth": 3000},
        "summer-kitchen": {"width": 4000, "depth": 3000}}


def _unknown(rtype, name, value):
    try:
        fm.resolve_spec(dict(BASE[rtype], type=rtype, **{name: value}))
    except fm.SpecError as e:
        return "unknown field" in str(e)
    return False


@pytest.mark.parametrize("rtype", sorted(fld.TYPES))
@pytest.mark.parametrize("region", ["eu", "us"])
def test_every_listed_field_is_accepted_and_every_accepted_field_is_listed(rtype, region):
    import timberlib as tl
    rows = fld.table(rtype, tl.load(region))
    listed = [r["name"] for r in rows]
    assert len(listed) == len(set(listed))
    for r in rows:
        assert r["meaning"] and r["default"] and isinstance(r["allowed"], str)
        if r["name"] in BASE[rtype] or r["name"] in ("type", "region", "units"):
            continue
        assert not _unknown(rtype, r["name"], r["example"] if r["example"] is not None else "x"), r["name"]
    everything = {r["name"] for t in fld.TYPES for r in fld.table(t, tl.load(region))}
    for name in sorted(everything - set(listed)) + ["no_such_field"]:
        assert _unknown(rtype, name, "x") or rtype in ("pent-shed", "gable-shed") and name in fm.KNOWN, (rtype, name)


def test_the_sheds_known_fields_are_exactly_the_two_tables():
    assert set(fm.KNOWN) == set(fld.names("pent-shed")) | set(fld.names("gable-shed"))
    assert fm.TERRACE_KNOWN == fld.names("terrace") and fm.PERGOLA_KNOWN == fld.names("pergola")
    assert fm.KITCHEN_KNOWN == fld.names("summer-kitchen")
