"""Tests for tools/bom.py, the shopping list and cut list.

    .venv/bin/python -m pytest tests/test_bom.py
"""
import csv, json, os, subprocess, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import bom as bm  # noqa: E402
import frame as fr  # noqa: E402
import timberlib as tl  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
SNAPSHOT = os.path.join(ROOT, "data", "timber", "prices", "hu-szekely-fatelep-2026-11-10.csv")


def load(name):
    with open(os.path.join(FIX, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module", params=["shed-eu", "shed-us"])
def shed_bom(request):
    frame = fr.generate(load(request.param))
    snap = tl.load_snapshot(SNAPSHOT) if request.param == "shed-eu" else None
    return frame, bm.make_bom(frame, snap)


# ---------------------------------------------------------- the small frame
# bom-small.json: 8 studs of 1000 mm and 2 plates of 2400 mm (50x100 sawn,
# stock 2000-6000 mm in 1000 steps), four OSB 12 parts (2400x1250,
# 1200x1250 twice, and 1250x2400 which must turn), one shiplap board of
# 2900 mm. Kerf 4 mm.
#
# Hand packing of the timber, longest first (2400, 2400, 8 x 1000):
#   6000 mm pieces: [2400 2400 1000] = 5808, then 5 x 1000 = 5016, then 2 x 1000
#     -> 3 pieces; with the mix, the last one shrinks to 3000: 6000+6000+3000 = 15000 mm
#   5000 mm pieces: [2400 2400] = 4804, [1000 x4] = 4012, [1000 x4] = 4012 -> 3 pieces, 15000 mm
#   4000: 4 pieces (16000), 3000: 6 (18000), 2000: not possible (2400 cut).
# 5000 x 3 ties with the mix on waste and pieces, and a single length wins ties.
# Spare at 10%: ceil(0.3) = 1 piece, so 4 x 5000 mm are bought.
# Sheets (2500 x 1250, kerf 4): A (2400) on sheet 1; B and C side by side
#   (1200 + 4 + 1200 = 2404 <= 2500) on sheet 2; D turned to 2400 x 1250 on
#   sheet 3 -> 3 sheets, spare ceil(0.3) = 1, buy 4.
# Cladding: one 2900 mm board on a 3000 mm piece, spare 1 -> 2 x 3000 mm.
# Fasteners (library joint rules, eu):
#   nail-framing:   16 stud-plate x 2 + 1 plate-plate x 2 = 34, spare ceil(3.4) = 4 -> 38 nails
#                   at 180 per kg = 0.21 kg -> one 1 kg box (about 180 nails)
#   nail-sheathing: one sheet edge of 2400 mm every 150 mm = 16, spare 2 -> 18 nails -> one 1 kg box
#   nail-cladding:  one board over 3 studs x 2 = 6, spare 1 -> 7 nails -> one 1 kg box
#   No rafter-plate or corner-stud joint, so no structural screws.

@pytest.fixture(scope="module")
def small():
    return bm.make_bom(load("bom-small"), None, 10, 4)


def line(b, section, item, variant=None):
    for ln in b[section]:
        if ln["item"] == item and (variant is None or ln.get("variant") == variant):
            return ln
    raise AssertionError(f"no {item} in {section}")


def test_small_timber(small):
    ln = line(small, "timber", "50x100", "sawn")
    assert ln["cuts"] == 10
    assert [(p["length_mm"], p["qty"], p["spare"]) for p in ln["pieces"]] == [(5000, 3, 1)]
    assert ln["pieces_to_buy"] == 4 and ln["plan"] == "single"
    lay = {tuple(sorted(c["length_mm"] for c in p["cuts"])) for p in ln["layouts"]}
    assert lay == {(2400, 2400), (1000,) * 4}
    assert sorted(p["offcut_mm"] for p in ln["layouts"]) == [196, 988, 988]
    assert small["totals"]["amount"] is None and small["totals"]["partial"]


def test_small_waste_zero_has_no_spare():
    b = bm.make_bom(load("bom-small"), None, 0, 4)
    assert line(b, "timber", "50x100")["pieces_to_buy"] == 3
    assert line(b, "sheets", "osb-12")["sheets_to_buy"] == 3


def test_small_cladding(small):
    ln = line(small, "timber", "shiplap-19x121")
    assert ln["kind"] == "cladding"
    assert [(p["length_mm"], p["qty"], p["spare"]) for p in ln["pieces"]] == [(3000, 1, 1)]


def test_small_sheets(small):
    ln = line(small, "sheets", "osb-12")
    assert ln["sheets_packed"] == 3 and ln["sheets_to_buy"] == 3      # sheets get no spare unless asked
    by_sheet = [sorted(p["id"] for p in s["parts"]) for s in ln["layouts"]]
    assert sorted(by_sheet) == [["skin/sheet-A"], ["skin/sheet-B", "skin/sheet-C"], ["skin/sheet-D"]]
    d = next(p for s in ln["layouts"] for p in s["parts"] if p["id"] == "skin/sheet-D")
    assert d["rotated"] and (d["w"], d["h"]) == (2400, 1250)
    bc = next(s for s in ln["layouts"] if len(s["parts"]) == 2)
    assert sorted(p["x"] for p in bc["parts"]) == [0, 1204]


def test_sheets_without_rotation_refuse_a_part_that_only_fits_turned():
    parts = [("p", 1250, 2400)]
    sheets, problems = bm.pack_sheets(parts, 2500, 1250, 4, can_rotate=False)
    assert not sheets and problems and "can't be rotated" in problems[0]
    sheets, problems = bm.pack_sheets(parts, 2500, 1250, 4, can_rotate=True)
    assert len(sheets) == 1 and not problems


def test_small_fasteners(small):
    f = {x["item"]: x for x in small["fasteners"]}
    assert set(f) == {"nail-framing", "nail-sheathing", "nail-cladding"}   # no screws on these joints
    n = f["nail-framing"]
    assert (n["counted"], n["spare"], n["kind"]) == (34, 4, "nail")
    assert (n["weight_unit"], n["weight"], n["buy_weight"]) == ("kg", 0.21, 1)     # 38 nails / 180 per kg
    assert n["packs"] == [{"size": 1, "qty": 1}] and n["to_buy"] == 180
    assert (f["nail-sheathing"]["counted"], f["nail-sheathing"]["spare"]) == (16, 2)
    assert (f["nail-cladding"]["counted"], f["nail-cladding"]["spare"]) == (6, 1)
    assert small["fasteners"][0]["kind"] == "nail"          # nails are listed before screws


def test_nail_weight_rounds_up_to_boxes():
    eu, us = tl.load("eu"), tl.load("us")
    nail = tl.item(eu, "nail-framing")                       # 180 per kg, boxes 1 / 2.5 / 5 kg
    need, packs, bought = bm.nail_weight_packs(1240, nail)
    assert round(need, 2) == 6.89 and bought == 7 and packs == {5: 1, 1: 2}   # the smallest total that covers it
    need, packs, bought = bm.nail_weight_packs(180 * 10, nail)
    assert bought == 10 and packs == {5: 2}
    need, packs, bought = bm.nail_weight_packs(1, nail)
    assert bought == 1 and packs == {1: 1}
    nail = tl.item(us, "nail-framing")                       # 47 per lb, boxes 1 / 5 lb
    need, packs, bought = bm.nail_weight_packs(47 * 7, nail)
    assert bought == 7 and packs == {5: 1, 1: 2}


def test_structural_screws_only_where_chosen():
    joints = [{"type": t, "a": "a", "b": "b", **({"edge_mm": 2400} if t == "corner-stud" else {})}
              for t in ("rafter-plate", "rafter-plate", "corner-stud", "stud-plate")]
    frame = {"region": "eu", "units": "metric", "members": [], "joints": joints}
    b = bm.make_bom(frame, None, 0, 4)
    f = {x["item"]: x for x in b["fasteners"]}
    assert f["screw-rafter"]["counted"] == 2 and f["screw-rafter"]["by_joint_type"] == {"rafter-plate": 2}
    assert f["screw-corner"]["counted"] == 5 and f["screw-corner"]["by_joint_type"] == {"corner-stud": 5}  # 2400 / 500
    assert f["nail-toe"]["counted"] == 4 and f["nail-framing"]["counted"] == 2    # rafters keep 2 toe nails each
    screws = {k for k, x in f.items() if x["kind"] == "screw"}
    assert screws == {"screw-rafter", "screw-corner"}
    for region in ("eu", "us"):
        lib = tl.load(region)
        used = {r["fastener"] for t, r in lib["joint_rules"].items() if not t.startswith("_") and "fastener" in r}
        used |= {a["fastener"] for r in lib["joint_rules"].values() for a in r.get("also", [])}
        outdoor = {"screw-deck", "screw-connector"}          # only the terrace's joints use these
        assert {k for k in used if lib["fasteners"][k]["type"] == "screw"} - outdoor == screws


def test_md_separates_nails_and_structural_screws(small):
    md = bm.render_md(small)
    assert md.index("## Nails") < md.index("## Structural screws") < md.index("## Bought items")
    assert "1 × 1 kg" in md and "Counted for" in md


def test_pack_count():
    assert bm.pack_count(38, [100, 200]) == (100, {100: 1})
    assert bm.pack_count(201, [100, 200]) == (300, {100: 1, 200: 1})
    assert bm.pack_count(400, [100, 200]) == (400, {200: 2})


def test_bought_copied(small):
    assert small["bought"][0]["item"] == "roofing-felt" and small["bought"][0]["qty"] == 2.5


def test_cheapest_wins_when_priced():
    # 3 cuts of 1900 mm of 50x150 impregnated: 4000 mm holds two (3804), so 2 x 4000
    # (12 270 Ft) beats 3 x 2000 (the snapshot's price for 2000 is higher per cut).
    frame = load("bom-small")
    frame["members"] = [dict(m, item="50x150", variant="impregnated", size=[1900, 150, 50])
                        for m in frame["members"] if m["id"].startswith("wall/stud-0") and m["id"][-1] in "123"]
    frame["joints"], frame["bought"] = [], []
    snap = tl.load_snapshot(SNAPSHOT)
    b = bm.make_bom(frame, snap, 0, 4)
    ln = b["timber"][0]
    assert ln["priced"]
    # whatever it chose, no other single length is cheaper
    for L in (2000, 3000, 4000, 5000, 6000):
        hit = tl.price_for(snap, tl.item(tl.load("eu"), "50x150"), L, "impregnated")
        if not hit:
            continue
        bins = bm.pack_fixed([(m["id"], 1900) for m in frame["members"]], L, 4)
        assert ln["total"] <= len(bins) * hit["price_gross"] + 1e-6


def test_prices_and_partial_total():
    snap = tl.load_snapshot(SNAPSHOT)
    b = bm.make_bom(load("bom-small"), snap, 10, 4)
    lib = tl.load("eu")
    p5 = tl.price_for(snap, tl.item(lib, "50x100"), 5000, "sawn")["price_gross"]
    t = line(b, "timber", "50x100")
    assert t["total"] == round(4 * p5, 2)
    s = tl.price_for(snap, tl.item(lib, "osb-12"))["price_gross"]
    assert line(b, "sheets", "osb-12")["total"] == round(3 * s, 2)      # three sheets, no spare
    assert b["totals"]["partial"] and "nail-framing" in b["totals"]["unpriced"]
    assert b["totals"]["amount"] == round(t["total"] + line(b, "sheets", "osb-12")["total"], 2)


# ---------------------------------------------------------- the shed fixtures

def test_shed_has_no_problems(shed_bom):
    frame, b = shed_bom
    assert b["problems"] == []
    assert b["timber"] and b["sheets"] and b["fasteners"] and b["bought"]


def test_no_piece_over_its_stock_length(shed_bom):
    _, b = shed_bom
    for ln in b["timber"]:
        for p in ln["layouts"]:
            used = sum(c["length_mm"] for c in p["cuts"]) + b["kerf_mm"] * (len(p["cuts"]) - 1)
            assert used <= p["stock_mm"] + 1e-6, p["piece"]
            assert p["offcut_mm"] >= -1e-6
    for ln in b["sheets"]:
        long_, short_ = ln["sheet_size_mm"]
        for s in ln["layouts"]:
            for p in s["parts"]:
                assert p["x"] + p["w"] <= long_ + 1e-6 and p["y"] + p["h"] <= short_ + 1e-6


def test_sheet_parts_do_not_overlap(shed_bom):
    _, b = shed_bom
    for ln in b["sheets"]:
        for s in ln["layouts"]:
            ps = s["parts"]
            for i, p in enumerate(ps):
                for q in ps[i + 1:]:
                    assert (p["x"] + p["w"] <= q["x"] + 1e-6 or q["x"] + q["w"] <= p["x"] + 1e-6
                            or p["y"] + p["h"] <= q["y"] + 1e-6 or q["y"] + q["h"] <= p["y"] + 1e-6)


def test_every_member_appears_once(shed_bom):
    frame, b = shed_bom
    ids = [c["id"] for ln in b["timber"] for p in ln["layouts"] for c in p["cuts"]]
    ids += [p["id"] for ln in b["sheets"] for s in ln["layouts"] for p in s["parts"]]
    assert sorted(ids) == sorted(m["id"] for m in frame["members"])


def test_cut_lengths_match_members(shed_bom):
    frame, b = shed_bom
    size = {m["id"]: m["size"][0] for m in frame["members"]}
    for ln in b["timber"]:
        for p in ln["layouts"]:
            for c in p["cuts"]:
                assert c["length_mm"] == size[c["id"]]


def test_fastener_counts_equal_a_hand_count(shed_bom):
    frame, b = shed_bom
    lib = tl.load(frame["region"])
    rules = lib["joint_rules"]
    want = {}
    for j in frame["joints"]:
        r = rules[j["type"]]
        for part in [r] + r.get("also", []):
            if "per_joint" in part:
                n = part["per_joint"]
            elif "per_crossing" in part:
                n = part["per_crossing"] * j["crossings"]
            else:
                n = -(-j["edge_mm"] // part["every_mm"])
            want[part["fastener"]] = want.get(part["fastener"], 0) + n
    got = {f["item"]: f for f in b["fasteners"]}
    assert set(got) == set(want)
    for k, n in want.items():
        assert got[k]["counted"] == n
        assert got[k]["spare"] == tl.allowance(n, b["waste_pct"])
        if got[k]["kind"] == "nail":     # by weight: kg or lb, boxes round up
            it = tl.item(lib, k)
            u = got[k]["weight_unit"]
            assert u == ("kg" if frame["region"] == "eu" else "lb")
            assert got[k]["buy_weight"] == sum(p["size"] * p["qty"] for p in got[k]["packs"])
            assert got[k]["buy_weight"] * it[f"pcs_per_{u}"] >= n + got[k]["spare"] - 1e-6
            assert all(p["size"] in it[f"box_{u}"] for p in got[k]["packs"])
        else:
            assert got[k]["to_buy"] >= n + got[k]["spare"]
            assert got[k]["to_buy"] == sum(p["size"] * p["qty"] for p in got[k]["packs"])


def test_spare_counts_follow_the_allowance(shed_bom):
    _, b = shed_bom
    for ln in b["timber"]:
        n = len(ln["layouts"])
        assert ln["spare_pieces"] == tl.allowance(n, b["waste_pct"])
        assert ln["pieces_to_buy"] == n + ln["spare_pieces"]
    for ln in b["sheets"]:
        assert ln["sheets_to_buy"] == ln["sheets_packed"] + tl.allowance(ln["sheets_packed"], b["sheet_spare_pct"])


def test_eu_shed_priced_with_the_hungarian_snapshot():
    frame = fr.generate(load("shed-eu"))
    b = bm.make_bom(frame, tl.load_snapshot(SNAPSHOT))
    assert b["totals"]["amount"] > 0 and b["totals"]["currency"] == "HUF"
    assert b["totals"]["partial"]       # fasteners, felt, door, window and cladding have no price
    for ln in b["timber"] + b["sheets"]:
        assert ln["priced"] == (ln["total"] is not None)
    assert all(not f["priced"] for f in b["fasteners"])


def test_markdown_uses_the_frames_units(shed_bom):
    frame, b = shed_bom
    md = bm.render_md(b)
    assert "no price" in md or b["snapshot"]
    if frame["units"] == "imperial":
        assert "14'" in md and "4000 mm" not in md and "6000 mm" not in md
    else:
        assert tl.fmt_length(6000, "metric") in md


def test_same_frame_same_files(tmp_path):
    frame = fr.generate(load("shed-eu"))
    fp = tmp_path / "frame.json"
    fp.write_text(json.dumps(frame), encoding="utf-8")
    outs = []
    for name in ("a", "b"):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bom.py"), str(fp),
                        "--snapshot", SNAPSHOT, "--out", str(tmp_path / name)], check=True, capture_output=True)
        outs.append({f: (tmp_path / name / f).read_bytes() for f in ("bom.json", "bom.md", "cutlist.csv")})
    assert outs[0] == outs[1]
    rows = list(csv.DictReader(open(tmp_path / "a" / "cutlist.csv", encoding="utf-8")))
    assert len(rows) == len(frame["members"])


def test_a_cut_longer_than_any_stock_is_reported():
    frame = load("bom-small")
    frame["members"][0] = dict(frame["members"][0], size=[9000, 100, 50])
    b = bm.make_bom(frame, None, 10, 4)
    assert any("longer than the longest stock" in p for p in b["problems"])


def test_sheet_spare_and_end_trim_are_options():
    b = bm.make_bom(load("bom-small"), None, 10, 4, sheet_spare_pct=10)
    assert line(b, "sheets", "osb-12")["sheets_to_buy"] == 4
    frame = json.load(open(os.path.join(ROOT, "tests", "fixtures", "bom-small.json")))
    plain, trimmed = bm.make_bom(frame, None, 0, 4), bm.make_bom(frame, None, 0, 4, trim=50)
    for ln in trimmed["timber"]:
        for piece in ln["layouts"]:
            assert piece["offcut_mm"] >= 50 - 1e-6, "a stock length was planned to its very end"
    assert sum(l["pieces_to_buy"] for l in trimmed["timber"]) >= sum(l["pieces_to_buy"] for l in plain["timber"])


# ---------------------------------------------- what each piece is, in words

def test_every_kind_the_frame_makes_has_a_plain_name(shed_bom):
    frame, _ = shed_bom
    for m in frame["members"]:
        assert bm.kind_key(m["kind"], m["id"]) in bm.KIND_NAMES, (m["id"], m["kind"])


def test_flying_rafters_are_told_apart_from_rafters_by_id():
    assert bm.what_is("rafter", "roof/rafter-01") == "Rafter"
    assert bm.what_is("rafter", "roof/flying-rafter-left") == "Flying rafter"
    assert bm.what_is("king", "wall-front/king-01") == "King stud"
    assert bm.what_is("sheet", "floor/deck-01") == "Sheet"


def test_cutlist_has_a_what_column_after_kind(shed_bom, tmp_path):
    frame, b = shed_bom
    bm.write_cutlist(b, tmp_path / "cutlist.csv")
    with open(tmp_path / "cutlist.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        f.seek(0)
        head = next(csv.reader(f))
    assert head[head.index("kind") + 1] == "what"
    assert head[:8] == ["type", "item", "variant", "piece", "stock_mm", "member", "group", "kind"]
    by_id = {m["id"]: m for m in frame["members"]}
    assert len(rows) == len(by_id)
    for r in rows:
        m = by_id[r["member"]]
        assert r["what"] == bm.what_is(m["kind"], m["id"])
        assert r["what"] and (r["type"] != "sheet" or r["what"] == "Sheet")
        assert r["type"] == "sheet" or r["kind"] == m["kind"]
    assert {"King stud", "Jack stud", "Cripple stud", "Flying rafter"} <= {r["what"] for r in rows}


def test_counts_by_kind_add_up_and_are_in_the_markdown(shed_bom):
    frame, b = shed_bom
    md = bm.render_md(b)
    for ln in b["timber"]:
        assert sum(ln["by_kind"].values()) == ln["cuts"]
        assert f"Cuts: {bm.kinds_in_words(ln['by_kind'])}." in md
    total = {}
    for ln in b["timber"]:
        for k, n in ln["by_kind"].items():
            total[k] = total.get(k, 0) + n
    want = {}
    for m in frame["members"]:
        if m["kind"] != "sheet":
            w = bm.what_is(m["kind"], m["id"])
            want[w] = want.get(w, 0) + 1
    assert total == want


def test_counts_in_words():
    by = bm.count_by_kind([{"id": "a", "kind": "stud"}, {"id": "b", "kind": "king"}, {"id": "c", "kind": "stud"},
                           {"id": "roof/flying-rafter-left", "kind": "rafter"}, {"id": "d", "kind": "cripple"}])
    assert list(by) == ["Stud", "King stud", "Cripple stud", "Flying rafter"]
    assert bm.kinds_in_words(by) == "2 studs, 1 king stud, 1 cripple stud, 1 flying rafter"


def test_every_joint_type_has_a_plain_name():
    assert set(bm.JOINT_NAMES) == set(tl.JOINT_TYPES)
    for t, name in bm.JOINT_NAMES.items():
        assert name and name == name.lower() and "-" not in name, (t, name)


def test_fastener_table_names_what_each_fastener_joins(shed_bom):
    _, b = shed_bom
    md = bm.render_md(b)
    assert "Counted for" in md
    used = {t for f in b["fasteners"] for t in f["by_joint_type"]}
    assert "king-jack" in used
    for t in used:
        assert bm.JOINT_NAMES[t] in md
        assert f" {t} " not in md       # never the raw joint type


def test_the_shopping_list_says_it_is_guidance_not_engineering(small):
    lines = bm.render_md(small).splitlines()
    assert lines[0].startswith("# Shopping list") and "not structural engineering" in lines[2]
