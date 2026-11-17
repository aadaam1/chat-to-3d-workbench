"""Prices from several suppliers: the TSV importer, the loader, the choice of supplier per line,
and the pricing of nails, screws, felt and other bought items.

    .venv/bin/python -m pytest tests/test_prices.py

The synthetic snapshots are in tests/fixtures/prices/: zz-alpha (gross prices, sells timber in 3 and 6 m,
OSB, nails, screws, felt rolls), zz-beta (net prices, timber in 2.5 and 5 m, OSB, felt by the m2, no nails),
us-gamma (US, shelf prices), zz-bad (lines the importer must refuse).
"""
import copy, csv, json, os, shutil, subprocess, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import bom as bm  # noqa: E402
import timber_import as ti  # noqa: E402
import timberlib as tl  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
RAW = os.path.join(FIX, "prices")
OLD_CSV = os.path.join(ROOT, "data", "timber", "prices", "hu-szekely-fatelep-2026-11-10.csv")


def imp(name, out):
    """Import a fixture TSV to a CSV; returns the importer's exit code."""
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "timber_import.py"),
                           os.path.join(RAW, name + ".tsv"), str(out)], capture_output=True, text=True)


@pytest.fixture()
def prices(tmp_path, monkeypatch):
    """A prices folder with zz-alpha and zz-beta imported, in place of data/timber/prices."""
    d = tmp_path / "prices"
    d.mkdir()
    for n in ("zz-alpha-2026-11-01", "zz-beta-2026-11-02"):
        assert imp(n, d / (n + ".csv")).returncode == 0
    monkeypatch.setattr(tl, "PRICES", str(d))
    return d


def small():
    with open(os.path.join(FIX, "bom-small.json"), encoding="utf-8") as f:
        return json.load(f)


def sups(spec):
    return [rows for _, rows in tl.load_snapshots(spec)]


def line(b, cat, item, variant=None):
    return next(l for l in b[cat] if l["item"] == item and (variant is None or l.get("variant") == variant))


# ------------------------------------------------------------------ the importer

def rows_of(tmp_path, name):
    out = tmp_path / (name + ".csv")
    r = imp(name, out)
    with open(out, encoding="utf-8") as f:
        return r, list(csv.DictReader(f))


def test_importer_reads_eu_gross_and_net_with_the_vat_in_the_header(tmp_path):
    r, rows = rows_of(tmp_path, "zz-alpha-2026-11-01")
    assert r.returncode == 0, r.stderr
    t = next(x for x in rows if x["product"] == "Spruce batten 50x100 3 m")
    assert (t["price_gross"], t["price_net"], t["currency"]) == ("15.00", "12.40", "EUR")      # net from gross
    assert (t["region"], t["supplier"], t["read_date"]) == ("zz", "Alpha Timber", "2026-11-01")
    assert (t["kind"], t["item"], t["unit"], t["pack_qty"]) == ("lumber", "50x100", "piece", "1")
    assert t["gross_per_m"] == "5" and t["gross_per_m3"] == f"{15 / (0.05 * 0.1 * 3):.0f}"
    r, rows = rows_of(tmp_path, "zz-beta-2026-11-02")
    t = next(x for x in rows if x["product"] == "Batten 50x100 2.5 m")
    assert (t["price_net"], t["price_gross"]) == ("8.00", "9.68")                              # gross from net
    s = next(x for x in rows if x["kind"] == "sheet")
    assert (s["variant"], s["width_mm"], s["length_mm"], s["gross_per_m2"]) == ("sheet", "1250", "2500", f"{35 * 1.21 / 3.125:.0f}")


def test_importer_keeps_fasteners_and_bought_items_by_item_key_unit_and_pack(tmp_path):
    _, rows = rows_of(tmp_path, "zz-alpha-2026-11-01")
    box = next(x for x in rows if x["product"] == "Framing nails 3.1x90, 2.5 kg")
    assert (box["kind"], box["item"], box["unit"], box["pack_qty"], box["variant"]) == ("fastener", "nail-framing", "box", "2.5", "")
    assert box["gross_per_m3"] == box["gross_per_m"] == box["gross_per_m2"] == ""
    felt = next(x for x in rows if x["item"] == "roofing-felt")
    assert (felt["kind"], felt["unit"], felt["pack_qty"]) == ("bought", "roll", "10")
    assert [x["item"] for x in rows if x["kind"] == "bought"] == ["hinge", "ridge-cap", "roofing-felt"]


def test_importer_us_shelf_price_is_both_net_and_gross(tmp_path):
    r, rows = rows_of(tmp_path, "us-gamma-2026-11-03")
    assert r.returncode == 0, r.stderr
    for x in rows:
        assert x["price_net"] == x["price_gross"] and x["currency"] == "USD"
    stud = next(x for x in rows if x["item"] == "2x4")
    assert (stud["price_gross"], stud["length_mm"]) == ("3.98", "2438")


def test_importer_lists_what_it_cannot_read_and_never_guesses(tmp_path):
    r, rows = rows_of(tmp_path, "zz-bad-2026-11-04")
    assert [x["product"] for x in rows] == ["Batten 50x100 3 m"]
    assert r.returncode == 1
    for why in ("No price", "Comma price", "Nails without item", "Nails without box size", "Mismatch", "No source", "Wrong unit"):
        assert any(why in l for l in r.stderr.splitlines()), (why, r.stderr)
    assert "not a number" in r.stderr and "don't match the 21% VAT" in r.stderr and "needs pack_qty" in r.stderr


def test_importer_text_format_is_unchanged(tmp_path):
    out = tmp_path / "hu.csv"
    raw = os.path.join(ROOT, "data", "timber", "prices", "raw", "hu-szekely-fatelep-2026-11-10.txt")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "timber_import.py"), raw, str(out),
                        "--supplier", "Székely Fatelep", "--region", "hu", "--date", "2026-11-10"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    new = list(csv.DictReader(open(out, encoding="utf-8")))
    old = list(csv.DictReader(open(OLD_CSV, encoding="utf-8")))
    assert len(new) == len(old) and all(all(n[k] == o[k] for k in o) for n, o in zip(new, old))


# ------------------------------------------------------------------- the loader

def test_an_old_csv_without_the_new_columns_still_loads():
    rows = tl.load_snapshot(OLD_CSV)
    assert rows and all(r["item"] == "" and r["unit"] == "" and r["pack_qty"] is None for r in rows)
    assert isinstance(rows[0]["price_gross"], float)
    eu = tl.load("eu")
    assert tl.price_for(rows, tl.item(eu, "50x100"), 3000, "sawn")           # and still prices timber


def test_the_newest_snapshot_of_each_supplier_and_one_supplier(prices):
    shutil.copy(prices / "zz-alpha-2026-11-01.csv", prices / "zz-alpha-2026-10-01.csv")        # an older alpha
    names = [os.path.basename(p) for p in tl.snapshot_paths("zz")]
    assert names == ["zz-alpha-2026-11-01.csv", "zz-beta-2026-11-02.csv"]
    assert [os.path.basename(p) for p in tl.snapshot_paths("zz:beta")] == ["zz-beta-2026-11-02.csv"]
    assert tl.snapshot_slug("/x/hu-szekely-fatelep-2026-11-10.csv") == "szekely-fatelep"
    with pytest.raises(ValueError, match="have: alpha, beta"):
        tl.snapshot_paths("zz:nobody")
    with pytest.raises(ValueError, match="no price snapshot for region"):
        tl.snapshot_paths("qq")


def test_one_region_is_one_currency(prices):
    assert imp("us-gamma-2026-11-03", prices / "zz-gamma-2026-11-03.csv").returncode == 0   # USD under region zz
    with pytest.raises(ValueError, match="more than one currency"):
        tl.load_snapshots("zz")
    assert len(tl.load_snapshots("zz:alpha")) == 1
    with pytest.raises(ValueError, match="more than one currency"):
        bm.make_bom(small(), [tl.load_snapshot(str(prices / "zz-alpha-2026-11-01.csv")),
                              tl.load_snapshot(str(prices / "zz-gamma-2026-11-03.csv"))])


# ------------------------------------------------- the supplier of each line

def test_each_line_goes_to_the_supplier_that_prices_all_of_it_cheapest(prices):
    frame = small()
    both = bm.make_bom(frame, sups("zz"))
    a, b = bm.make_bom(frame, sups("zz:alpha")), bm.make_bom(frame, sups("zz:beta"))
    # timber: beta's 2.5 and 5 m pieces are cheaper than alpha's 3 and 6 m; its stock lengths pack the cuts
    t = line(both, "timber", "50x100")
    assert t["supplier"] == "Beta Yard" and t["total"] == line(b, "timber", "50x100")["total"] < line(a, "timber", "50x100")["total"]
    assert {p["length_mm"] for p in t["pieces"]} <= {2500, 5000}          # packed on the supplier's own lengths
    # sheets: alpha's OSB (40.00) beats beta's (35.00 net = 42.35 gross)
    assert line(both, "sheets", "osb-12")["supplier"] == "Alpha Timber"
    assert line(both, "sheets", "osb-12")["unit_price"] == 40.0
    # a supplier that does not sell a nail is skipped for it: only alpha sells nails
    assert {f["supplier"] for f in both["fasteners"]} == {"Alpha Timber"}
    # every line is no dearer than the cheaper of the two on its own
    for cat in ("timber", "sheets", "fasteners", "bought"):
        for l in both[cat]:
            singles = [x["total"] for bb in (a, b) for x in bb[cat] if x["item"] == l["item"] and x.get("variant") == l.get("variant") and x["priced"]]
            if singles:
                assert l["total"] == min(singles), l["item"]
    assert both["totals"]["amount"] == round(sum(l["total"] for c in ("timber", "sheets", "fasteners", "bought") for l in both[c] if l["priced"]), 2)
    assert both["totals"]["currency"] == "EUR"
    # the header names every supplier used with its read date
    names = {s["supplier"]: s for s in both["snapshot"]["suppliers"]}
    assert names["Alpha Timber"]["read_date"] == "2026-11-01" and names["Beta Yard"]["lines"] >= 1
    md = bm.render_md(both)
    assert "Alpha Timber, read 2026-11-01" in md and "Beta Yard, read 2026-11-02" in md and "| Supplier |" in md


def test_a_supplier_that_cannot_price_the_whole_line_is_skipped(prices):
    frame = small()
    frame["members"] = [dict(m) for m in frame["members"]]
    for m in frame["members"]:
        if m["id"] == "wall/plate-top":
            m["size"] = [5500, 100, 50]          # alpha's 6 m piece holds it; beta's longest is 5 m (5500 > 5000 - trim)
    b = bm.make_bom(frame, sups("zz"), 10, 4, 0, 20)
    assert line(b, "timber", "50x100")["supplier"] == "Alpha Timber"
    assert b["problems"] == []


def test_prices_region_slug_limits_to_one_supplier_and_snapshot_still_works(prices, tmp_path):
    frame = fr_frame(tmp_path)
    for spec, who in (("zz:alpha", {"Alpha Timber"}), ("zz:beta", {"Beta Yard"})):
        out = tmp_path / spec.replace(":", "-")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bom.py"), str(frame), "--prices", spec, "--out", str(out)],
                           capture_output=True, text=True, env=dict(os.environ, TIMBER_PRICES_DIR=str(prices)))
        assert r.returncode == 0, r.stderr
        b = json.load(open(out / "bom.json", encoding="utf-8"))
        assert {l["supplier"] for c in ("timber", "sheets", "fasteners", "bought") for l in b[c] if l["priced"]} == who
        assert [s["supplier"] for s in b["snapshot"]["suppliers"]] == [next(iter(who))]
        head = next(csv.DictReader(open(out / "cutlist.csv", encoding="utf-8")))
        assert head["supplier"] in who
    one = tmp_path / "one"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bom.py"), str(frame), "--snapshot",
                        str(prices / "zz-alpha-2026-11-01.csv"), "--out", str(one)], capture_output=True, text=True)
    assert r.returncode == 0
    assert json.load(open(one / "bom.json", encoding="utf-8"))["snapshot"]["supplier"] == "Alpha Timber"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bom.py"), str(frame), "--prices", "zz:nobody", "--out", str(tmp_path / "none")],
                       capture_output=True, text=True, env=dict(os.environ, TIMBER_PRICES_DIR=str(prices)))
    assert r.returncode == 0 and "have: alpha, beta" in r.stderr
    assert json.load(open(tmp_path / "none" / "bom.json", encoding="utf-8"))["snapshot"] is None


def fr_frame(tmp_path):
    p = tmp_path / "frame.json"
    p.write_text(json.dumps(small()))
    return p


def test_no_prices_means_no_new_keys(prices):
    """The shopping list made without prices has no supplier keys (the oracle hashes it)."""
    b = bm.make_bom(small(), None, 10, 4)
    assert b["snapshot"] is None and b["totals"]["amount"] is None
    assert not any("supplier" in l for c in ("timber", "sheets", "fasteners", "bought") for l in b[c])
    assert "Supplier" not in bm.render_md(b)


# ------------------------------------------ nails, screws, felt and other items

def test_nail_boxes_combine_to_the_cheapest_cover(prices):
    it = tl.item(tl.load("eu"), "nail-framing")
    got = bm.price_need(6.2, "nail-framing", it, "weight", [dict(s, rows=r) for s, r in zip(
        [{"supplier": "Alpha Timber", "currency": "EUR"}], sups("zz:alpha"))])
    # boxes of 1 kg 10.00, 2.5 kg 22.00, 5 kg 35.00: 5 + 1 + 1 = 7 kg for 55.00 beats 5 + 2.5 (57.00)
    assert got["cost"] == 55.0 and got["bought"] == 7.0
    assert {(p["size"], p["qty"]) for p in got["packs"]} == {(5.0, 1), (1.0, 2)}


def test_the_list_buys_the_suppliers_boxes_and_screw_packs(prices):
    b = bm.make_bom(small(), sups("zz"), 10, 4, 0, 20)
    n = line(b, "fasteners", "nail-framing")
    assert n["priced"] and n["supplier"] == "Alpha Timber" and n["packs"][0]["size"] == 1.0 and n["buy_weight"] == 1.0
    assert n["total"] == 10.0 and n["to_buy"] == 180
    # nails with no price row stay unpriced and the total says partial
    toe = [f for f in b["fasteners"] if f["item"] not in ("nail-framing", "nail-sheathing", "nail-cladding")]
    assert toe == []
    # screws by the pack: 700 deck screws = 500 + 200 (28.00), not 2 x 500 or 4 x 200
    it = tl.item(tl.load("eu"), "screw-deck")
    got = bm.price_need(700, "screw-deck", it, "count", [{"supplier": "Alpha Timber", "currency": "EUR", "rows": sups("zz:alpha")[0]}])
    assert got["cost"] == 28.0 and {(p["size"], p["qty"]) for p in got["packs"]} == {(500.0, 1), (200.0, 1)}
    got = bm.price_need(650, "screw-deck", it, "count", [{"supplier": "Alpha Timber", "currency": "EUR", "rows": sups("zz:alpha")[0]}])
    assert got["cost"] == 28.0 and got["bought"] == 700


def test_felt_by_roll_or_by_the_m2_whichever_is_cheaper(prices):
    def felt(qty):
        f = small()
        f["bought"] = [{"item": "roofing-felt", "note": "t", "qty": qty, "unit": "m2"}]
        return line(bm.make_bom(f, sups("zz"), 10, 4, 0, 20), "bought", "roofing-felt")
    small_roof = felt(2.5)                    # 3 m2 at 7.00 gross (beta) = 21.00 beats a 10 m2 roll at 50.00
    assert (small_roof["supplier"], small_roof["total"], small_roof["bought_qty"]) == ("Beta Yard", 21.0, 3.0)
    big = felt(25)                            # 3 rolls = 150.00 (alpha) beats 25 m2 at 7.00 = 175.00
    assert (big["supplier"], big["total"], big["bought_qty"]) == ("Alpha Timber", 150.0, 30.0)
    assert big["packs"] == [{"size": 10.0, "qty": 3, "unit_price": 50.0, "product": "Bitumen roofing felt, 10 m2 roll"}]


def test_trim_by_the_piece_and_pieces(prices):
    f = small()
    f["bought"] = [{"item": "ridge-cap", "note": "", "qty": 3.74, "unit": "m"},
                   {"item": "hinge", "note": "", "qty": 3, "unit": "pcs"},
                   {"item": "latch", "note": "", "qty": 1, "unit": "pcs"}]
    b = bm.make_bom(f, sups("zz"), 10, 4, 0, 20)
    ridge, hinge, latch = (line(b, "bought", k) for k in ("ridge-cap", "hinge", "latch"))
    assert ridge["total"] == 16.0 and ridge["packs"][0]["qty"] == 2          # two 2 m pieces cover 3.74 m
    assert hinge["supplier"] == "Beta Yard" and hinge["total"] == 3 * 2.42     # beta: net 2.00 = 2.42 gross
    assert not latch["priced"] and latch["supplier"] is None                  # no row: stays unpriced
    assert "latch" in b["totals"]["unpriced"] and b["totals"]["partial"]


def test_a_ground_screw_price_includes_its_post_bracket(tmp_path):
    rows = [{"kind": "bought", "item": "ground-screw-76x800", "unit": "piece", "pack_qty": 1.0, "price_gross": 20.0,
             "product": "Ground screw 76x800 with bracket", "supplier": "S", "read_date": "2026-11-01", "currency": "EUR",
             "variant": "", "thickness_mm": None, "width_mm": None, "length_mm": None, "price_net": 16.5, "notes": ""}]
    bought = [{"item": "ground-screw-76x800", "name": "g", "qty": 9, "unit": "pcs", "note": "", "unit_price": None, "total": None, "priced": False},
              {"item": "post-base-u", "name": "p", "qty": 9, "unit": "pcs", "note": "", "unit_price": None, "total": None, "priced": False}]
    bm.price_bought(bought, tl.load("eu"), bm.suppliers_of(rows))
    assert bought[0]["total"] == 180.0 and bought[1]["total"] == 0.0 and bought[1]["priced"]
    assert "included" in bm.bought_note(bought[1])


def test_us_list_is_priced_in_dollars_before_sales_tax(tmp_path, monkeypatch):
    d = tmp_path / "prices"
    d.mkdir()
    assert imp("us-gamma-2026-11-03", d / "us-gamma-2026-11-03.csv").returncode == 0
    monkeypatch.setattr(tl, "PRICES", str(d))
    b = bm.make_bom({"name": "t", "region": "us", "units": "imperial", "spec": {}, "joints": [], "bought": [],
                     "members": [{"id": "w/s%d" % i, "item": "2x4", "variant": "sawn", "layer": "walls", "group": "w", "kind": "stud",
                                  "size": [2000, 89, 38], "cut_deg": [0, 0]} for i in range(3)]}, sups("us"))
    assert b["totals"]["currency"] == "USD" and b["timber"][0]["supplier"] == "Gamma Lumber"
    assert "shelf prices before sales tax, USD" in bm.render_md(b)
    assert "3.98 USD" in bm.render_md(b)


def test_cheapest_packs_exact_and_deterministic():
    pk = lambda need, sizes: bm.cheapest_packs(need, [(s, p, s) for s, p in sizes])
    assert pk(0.21, [(1, 10), (2.5, 22), (5, 35)])[2] == [(1, 1)]
    assert pk(3.6, [(1, 10), (2.5, 22), (5, 35)])[:2] == (35.0, 5.0)   # one 5 kg box beats 2.5 + 1 + 1 (42.00)
    assert pk(10, [(5, 35), (5, 30)])[0] == 60.0                 # the cheaper of equal sizes
    assert pk(5, []) is None
