"""Tests for the shopping list's packer (each piece's stock length chosen with its
cuts), the offcut total and the "ways to waste less" hints.

    .venv/bin/python -m pytest tests/test_offcuts.py
"""
import copy, json, os, random, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import bom as bm  # noqa: E402
import frame as fr  # noqa: E402
import timberlib as tl  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
SNAPSHOT = os.path.join(ROOT, "data", "timber", "prices", "hu-szekely-fatelep-2026-11-10.csv")
PRICES = {2000: 1000, 3000: 1500, 4000: 2000, 5000: 2500, 6000: 3000, 7000: 3600, 8000: 4200}


def _load(name):
    with open(os.path.join(FIX, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _cuts(lengths):
    return [(f"c{i:02d}", ln) for i, ln in enumerate(lengths)]


def _check_plan(plan, cuts, kerf, trim):
    """Every cut once, no piece over its length."""
    kind, bins = plan
    assert sorted(c for _, b in bins for c in b) == sorted(cuts)
    for L, b in bins:
        assert bm.bin_used(b, kerf) <= L - trim + bm.EPS


def _stock(plan):
    return sum(L for L, _ in plan[1])


def old_plans(cuts, lengths, prices, kerf, trim):
    return [p for p in bm.timber_plans(cuts, lengths, prices, kerf, trim) if p[0] in ("single", "mix")]


def test_the_owners_shed_line_uses_much_less_than_seven_5m_pieces():
    # 9 x 2300, 2 x 3000, 6 x 350, 125, 325: seven 5 m pieces before (16% offcut)
    cuts = _cuts([2300] * 9 + [3000] * 2 + [350] * 6 + [125, 325])
    lengths = [2000, 3000, 4000, 5000, 6000]
    prices = {L: PRICES[L] for L in lengths}
    plans = bm.timber_plans(cuts, lengths, prices, 4, 20)
    best = min(plans, key=lambda p: bm.plan_key(p, prices, 4))
    _check_plan(best, cuts, 4, 20)
    old = min(old_plans(cuts, lengths, prices, 4, 20), key=lambda p: bm.plan_key(p, prices, 4))
    assert _stock(old) >= 33000
    assert _stock(best) <= 31000                  # 29 250 mm of cuts: under 6% offcut
    assert best[0] == "fitted"


def test_a_short_cut_goes_on_the_end_of_a_long_piece():
    # 2300 + 2300 + 1300 + kerfs fit one 6000; first-fit on 3000s would take three pieces
    cuts = _cuts([2300, 2300, 1300])
    best = min(bm.timber_plans(cuts, [3000, 6000], {}, 4, 20), key=lambda p: bm.plan_key(p, {}, 4))
    assert [L for L, _ in best[1]] == [6000]


def test_an_exact_fit_is_found_by_the_subset_search():
    # 1800 + 2200 = 4000 exactly with no kerf and no trim; the 2000s fill the rest
    cuts = _cuts([2200, 1800, 1800, 2200])
    best = min(bm.timber_plans(cuts, [4000], {}, 0, 0), key=lambda p: bm.plan_key(p, {}, 0))
    assert [L for L, _ in best[1]] == [4000, 4000]
    assert all(sum(c[1] for c in b) == 4000 for _, b in best[1])


def test_best_fills_picks_the_fullest_subset():
    # room for 1000 beside the first cut: 600 + 400 fills it, 700 alone would not
    got = bm.best_fills({700: 1, 600: 1, 400: 1}, [1000], 0)[0]
    assert got == {600: 1, 400: 1}


def test_kerf_and_trim_are_kept():
    cuts = _cuts([1000, 1000, 1000])
    # three 1000s need 3000 + 2 kerfs of 4 = 3008: a 3000 piece (less 20 trim) cannot hold them
    best = min(bm.timber_plans(cuts, [3000, 4000], {}, 4, 20), key=lambda p: bm.plan_key(p, {}, 4))
    _check_plan(best, cuts, 4, 20)
    assert [L for L, _ in best[1]] == [4000]


@pytest.mark.parametrize("priced", [True, False])
def test_never_worse_than_the_old_plans_on_random_lines(priced):
    rnd = random.Random(7)
    for _ in range(60):
        lengths = sorted(rnd.sample([2000, 3000, 4000, 5000, 6000, 7000, 8000], rnd.randint(1, 5)))
        prices = {L: PRICES[L] for L in lengths} if priced else {}
        trim, kerf = rnd.choice([0, 20]), 4
        cuts = _cuts([rnd.choice([125, 325, 350, 600, 900, 1200, 2300, 2950, 3000, 3980]) for _ in range(rnd.randint(1, 25))])
        if max(c[1] for c in cuts) > max(lengths) - trim:
            continue
        plans = bm.timber_plans(cuts, lengths, prices, kerf, trim)
        for p in plans:
            _check_plan(p, cuts, kerf, trim)
        best = min(plans, key=lambda p: bm.plan_key(p, prices, kerf))
        old = min(old_plans(cuts, lengths, prices, kerf, trim), key=lambda p: bm.plan_key(p, prices, kerf))
        assert bm.plan_key(best, prices, kerf)[:4] <= bm.plan_key(old, prices, kerf)[:4]


def test_same_input_same_plan():
    rnd = random.Random(3)
    cuts = _cuts([rnd.choice([350, 900, 2300, 3000]) for _ in range(40)])
    a = bm.timber_plans(cuts, [2000, 3000, 4000, 5000, 6000], PRICES, 4, 20)
    b = bm.timber_plans(cuts, [2000, 3000, 4000, 5000, 6000], PRICES, 4, 20)
    assert a == b


def test_a_big_line_packs_fast():
    import time
    rnd = random.Random(5)
    cuts = _cuts([rnd.choice([250, 450, 800, 1200, 2300, 2400, 3000, 4100]) for _ in range(300)])
    t = time.time()
    bm.timber_plans(cuts, [2000, 3000, 4000, 5000, 6000, 7000, 8000], PRICES, 4, 20)
    assert time.time() - t < 3


# ---- every oracle case: the new lists are no worse than the old plans, line by line

_cases = None


def oracle_frames():
    global _cases
    if _cases is None:
        from test_blocks_identical import cases
        _cases = {}
        for name, raw in cases().items():
            full = fr.generate(raw)
            _cases[name] = {k: v for k, v in full.items() if k not in ("assemblies", "decisions")}
    return _cases


@pytest.mark.parametrize("mode", ["unpriced-trim0", "priced-trim20"])
def test_no_oracle_case_got_worse(mode):
    snap = tl.load_snapshot(SNAPSHOT) if mode.startswith("priced") else None
    trim = 20 if mode.endswith("20") else 0
    for name, frame in oracle_frames().items():
        b = bm.make_bom(frame, snap, 10, 4, 0, trim)
        for ln in b["timber"]:
            cuts = [(c["id"], c["length_mm"]) for p in ln["layouts"] for c in p["cuts"]]
            it = tl.item(tl.load(frame["region"]), ln["item"])
            lens, prices = bm.stock_for(it, ln["variant"], snap)
            lens = sorted(set(lens) | {p["stock_mm"] for p in ln["layouts"]})     # special-order lengths
            old = min(old_plans(cuts, lens, prices, 4, trim), key=lambda p: bm.plan_key(p, prices, 4)) if cuts else None
            if old is None:
                continue
            mine = ("fitted" if ln["plan"] == "fitted" else ln["plan"],
                    [(p["stock_mm"], [(c["id"], c["length_mm"]) for c in p["cuts"]]) for p in ln["layouts"]])
            assert bm.plan_key(mine, prices, 4)[:4] <= bm.plan_key(old, prices, 4)[:4], (name, ln["item"], ln["variant"])


# ---- the offcut total and the hints

def _line_frame(item, variant, length, n):
    frame = _load("bom-small")
    base = frame["members"][0]
    frame["members"] = [dict(base, id=f"wall/m-{i:02d}", item=item, variant=variant, size=[length, 150, 50],
                             kind="joist", group="floor") for i in range(n)]
    frame["joints"], frame["bought"] = [], []
    return frame


def test_offcut_total_adds_up_and_is_in_the_markdown():
    frame = fr.generate(_load("shed-eu"))
    b = bm.make_bom(frame, tl.load_snapshot(SNAPSHOT), 10, 4, 0, 20)
    oc = b["offcuts"]
    stock = sum(p["stock_mm"] for ln in b["timber"] for p in ln["layouts"])
    cuts = sum(c["length_mm"] for ln in b["timber"] for p in ln["layouts"] for c in p["cuts"])
    assert oc["bought_mm"] == pytest.approx(stock) and oc["mm"] == pytest.approx(stock - cuts, abs=1)
    assert oc["pct"] == pytest.approx(100 * (stock - cuts) / stock, abs=0.1)
    md = bm.render_md(b)
    assert f"Offcuts: {oc['mm'] / 1000:.1f} m of {oc['bought_mm'] / 1000:.0f} m bought ({oc['pct']:g}%)" in md
    assert "reuse" in " ".join(b["notes"]) or "reused" in " ".join(b["notes"])


def test_hint_for_cuts_just_over_a_stock_length():
    snap = tl.load_snapshot(SNAPSHOT)
    frame = _line_frame("50x150", "impregnated", 4000, 6)
    b = bm.make_bom(frame, snap, 10, 4, 0, 20)
    hints = b["ways_to_waste_less"]
    assert len(hints) == 1
    h = hints[0]
    assert (h["cut_mm"], h["shorten_mm"]) == (4000, 20) and h["stock_mm_now"] == [5000] and h["stock_mm_then"] == [4000]
    assert "Ways to waste less" in bm.render_md(b)
    # the numbers are a real re-pack: the same list with the cuts 20 mm shorter
    short = copy.deepcopy(frame)
    for m in short["members"]:
        m["size"][0] = 3980
    b2 = bm.make_bom(short, snap, 10, 4, 0, 20)
    assert h["saves_amount"] == pytest.approx(b["totals"]["amount"] - b2["totals"]["amount"])
    assert h["saves_amount"] > 0 and not b2["ways_to_waste_less"]


def test_no_hint_when_the_cuts_fit_or_the_line_is_tidy():
    snap = tl.load_snapshot(SNAPSHOT)
    assert bm.make_bom(_line_frame("50x150", "impregnated", 3980, 6), snap, 10, 4, 0, 20)["ways_to_waste_less"] == []
    assert bm.make_bom(_line_frame("50x150", "impregnated", 4000, 6), snap, 10, 4, 0, 0)["ways_to_waste_less"] == []
    assert bm.make_bom(_line_frame("50x150", "impregnated", 2500, 6), snap, 10, 4, 0, 20)["ways_to_waste_less"] == []


def test_hint_without_prices_counts_timber_only():
    b = bm.make_bom(_line_frame("50x150", "impregnated", 5000, 6), None, 10, 4, 0, 20)
    h = b["ways_to_waste_less"][0]
    assert h["saves_amount"] is None and h["saves_stock_mm"] == 6000
    assert "less timber to buy" in h["text"] and "HUF" not in h["text"]
