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
    assert "Alpha Timber, read 2026-11-01" in md and "Beta Yard, read 2026-11-02" in md and "| Supplier and product |" in md


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


def test_a_ground_screw_and_its_bracket_are_priced_from_their_own_rows(tmp_path):
    def row(item, price, notes):
        return {"kind": "bought", "item": item, "unit": "piece", "pack_qty": 1.0, "price_gross": price, "product": item + " product",
                "supplier": "S", "read_date": "2026-11-01", "currency": "EUR", "variant": "", "thickness_mm": None, "width_mm": None,
                "length_mm": None, "price_net": None, "notes": notes}
    bought = [{"item": "ground-screw-76x800", "name": "g", "qty": 9, "unit": "pcs", "note": "", "unit_price": None, "total": None, "priced": False},
              {"item": "post-base-u", "name": "p", "qty": 9, "unit": "pcs", "note": "", "unit_price": None, "total": None, "priced": False},
              {"item": "latch", "name": "l", "qty": 1, "unit": "pcs", "note": "x", "unit_price": None, "total": None, "priced": False}]
    bm.price_bought(bought, tl.load("eu"), bm.suppliers_of([row("ground-screw-76x800", 20.0, "NO post bracket"), row("post-base-u", 8.0, "")]))
    assert (bought[0]["total"], bought[1]["total"]) == (180.0, 72.0) and not bought[2]["priced"]
    assert bm.priced_as(bought[0]) == "S: ground-screw-76x800 product (NO post bracket)"     # supplier, product and its note
    assert bm.priced_as(bought[1]) == "S: post-base-u product" and bm.priced_as(bought[2]) == ""
    assert bm.bought_note(bought[2]) == "x"


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


def test_importer_turns_prices_per_m2_and_per_m_into_piece_prices(tmp_path):
    r, rows = rows_of(tmp_path, "zz-misc-2026-11-05")
    by = {x["product"]: x for x in rows}
    osb = by["OSB 12 per m2"]
    assert (osb["unit"], osb["price_gross"], osb["gross_per_m2"]) == ("piece", "525.00", "168") and "per m2 x 3.125" in osb["notes"]
    board = by["Board 14x121x4m per m2"]
    assert board["price_gross"] == f"{4990 * 0.121 * 4:.2f}" and board["notes"].startswith("T&G; price per m2")
    assert by["Trim per m"]["price_gross"] == "100.00"
    # a header with no VAT rate: a gross price stands alone (net stays blank); a net price alone is refused
    gs = by["Ground screw"]
    assert gs["price_gross"] == "13500.00" and gs["price_net"] == ""
    assert "Net only" not in by and "no VAT rate" in r.stderr
    loaded = tl.load_snapshot(str(tmp_path / "zz-misc-2026-11-05.csv"))
    assert next(x for x in loaded if x["item"] == "ground-screw-76x800")["price_net"] is None


def test_importer_shortens_the_suppliers_header_name(tmp_path):
    src = open(os.path.join(RAW, "zz-alpha-2026-11-01.tsv"), encoding="utf-8").read().replace(
        "# supplier: Alpha Timber", "# supplier: Alpha Timber (alpha.example), Town - pages not in the old snapshot")
    f = tmp_path / "zz-alpha-2026-11-01.tsv"
    f.write_text(src, encoding="utf-8")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "timber_import.py"), str(f), str(tmp_path / "a.csv")], check=True, capture_output=True)
    assert {r["supplier"] for r in csv.DictReader(open(tmp_path / "a.csv", encoding="utf-8"))} == {"Alpha Timber"}


def test_a_later_partial_read_of_a_supplier_adds_to_the_earlier_one_product_by_product(prices):
    with open(prices / "zz-alpha-2026-11-01.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    newer = [dict(r, read_date="2026-12-01", price_gross="11.00", price_net="9.09") for r in rows
             if r["item"] == "nail-framing" and r["pack_qty"] == "1"]
    with open(prices / "zz-alpha-2026-12-01.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(newer)
    [(path, merged)] = tl.load_snapshots("zz:alpha")
    assert path.endswith("zz-alpha-2026-12-01.csv")
    assert len(merged) == len(rows)                                     # nothing lost, nothing doubled
    box = next(r for r in merged if r["item"] == "nail-framing" and r["pack_qty"] == 1)
    assert (box["price_gross"], box["read_date"]) == (11.0, "2026-12-01")      # the newer price wins
    assert any(r["kind"] == "lumber" and r["read_date"] == "2026-11-01" for r in merged)   # the rest from the older read
    b = bm.make_bom(small(), [merged], 10, 4, 0, 20)
    assert b["snapshot"]["suppliers"][0]["read_dates"] == ["2026-11-01", "2026-12-01"]
    assert "read 2026-11-01 and 2026-12-01" in bm.render_md(b)
    assert line(b, "fasteners", "nail-framing")["total"] == 11.0


def test_us_untreated_members_are_priced_by_dressed_rows():
    """US dimension lumber is sold dressed (planed): the US library lets a 'sawn' member take a 'planed' row,
    never an impregnated one; the EU library does not."""
    def row(variant, price):
        return {"kind": "lumber", "variant": variant, "thickness_mm": 38.0, "width_mm": 89.0, "length_mm": 2438.0,
                "price_gross": price, "price_net": price, "currency": "USD"}
    us, eu = tl.load("us"), tl.load("eu")
    hit = tl.price_for([row("impregnated", 7.59), row("planed", 4.25)], tl.item(us, "2x4"), 2438, "sawn")
    assert hit["price_gross"] == 4.25
    assert tl.price_for([row("impregnated", 7.59)], tl.item(us, "2x4"), 2438, "sawn") is None
    assert tl.price_for([row("planed", 4.25)], tl.item(us, "2x4"), 2438, "impregnated") is None
    assert tl.price_for([row("planed", 4.25)], tl.item(eu, "50x100"), 2438, "sawn") is None


def test_the_single_snapshot_default_is_the_most_complete_lumber_list(prices):
    assert os.path.basename(tl.newest_snapshot("zz")) == "zz-beta-2026-11-02.csv"       # 2 lumber rows each: the newer one
    with open(prices / "zz-alpha-2026-11-01.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(prices / "zz-gamma-2026-10-01.csv", "w", newline="", encoding="utf-8") as f:   # older but bigger
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows([r for r in rows if r["kind"] == "lumber"] * 2)
    assert os.path.basename(tl.newest_snapshot("zz")) == "zz-gamma-2026-10-01.csv"


def test_nails_sold_by_the_count_are_shown_as_a_count():
    row = {"kind": "fastener", "item": "nail-toe", "unit": "pack", "pack_qty": 2000.0, "price_gross": 2395.0, "product": "Nails, 2000 pcs",
           "supplier": "S", "read_date": "2026-11-01", "currency": "CZK", "variant": "", "thickness_mm": None, "width_mm": None,
           "length_mm": None, "price_net": None, "notes": ""}
    it = tl.item(tl.load("eu"), "nail-toe")
    got = bm.price_need(3000 / 310, "nail-toe", it, "weight", bm.suppliers_of([row]))      # 3000 nails at 310 per kg
    assert got["packs"][0]["count"] == 2000 and got["packs"][0]["qty"] == 2 and got["cost"] == 4790.0
    assert bm.nail_packs_text({"weight_unit": "kg", "packs": got["packs"]}) == "2 x 2000 nails"
    assert bm.nail_packs_text({"weight_unit": "kg", "packs": [{"size": 5.0, "qty": 1}, {"size": 1.0, "qty": 2}]}) == "1 x 5 kg + 2 x 1 kg"


def test_every_priced_line_shows_its_supplier_and_product(prices):
    b = bm.make_bom(small(), sups("zz"), 10, 4, 0, 20)
    t = line(b, "timber", "50x100")
    assert all(p["product"].startswith("Batten 50x100") for p in t["pieces"])
    assert line(b, "sheets", "osb-12")["product"] == "OSB/3 12 mm 1250x2500"
    assert line(b, "fasteners", "nail-framing")["packs"][0]["product"] == "Framing nails 3.1x90, 1 kg"
    md = bm.render_md(b)
    assert "| Supplier and product |" in md and "Beta Yard: Batten 50x100 5 m" in md and "Alpha Timber: OSB/3 12 mm 1250x2500" in md
    assert "Alpha Timber: Framing nails 3.1x90, 1 kg" in md
    assert "Alpha Timber: Bitumen roofing felt" in md or "Beta Yard: Roofing felt per m2" in md
    unpriced = bm.render_md(bm.make_bom(small(), None, 10, 4))
    assert "Supplier" not in unpriced


def test_prices_of_another_library_are_refused_with_a_plain_message(prices, tmp_path):
    assert tl.LIBRARY_OF == {"eu": "eu", "hu": "eu", "cz": "eu", "us": "us"}
    row = dict(tl.load_snapshot(str(prices / "zz-alpha-2026-11-01.csv"))[0])
    for region, frame_region in (("us", "eu"), ("hu", "us"), ("cz", "us")):
        f = small()
        f["region"] = frame_region
        with pytest.raises(ValueError, match=rf"{region} prices .* {frame_region}: use PRICES=") as e:
            bm.make_bom(f, [[dict(row, region=region)]])
    # bom.py says so and stops, with no traceback
    frame = tmp_path / "frame.json"
    f = small()
    f["region"] = "us"
    frame.write_text(json.dumps(f))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bom.py"), str(frame), "--prices", "hu", "--out", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "Traceback" not in r.stderr and "hu prices are for eu structures" in r.stderr


# ----------------------------------------------------------------- sizes as sold (3 mm tolerance)

def _row(item, t, w, l, variant="planed", kind="lumber"):
    return {"kind": kind, "item": item, "variant": variant, "thickness_mm": t, "width_mm": w, "length_mm": l,
            "price_gross": 1000.0, "price_net": 800.0, "currency": "HUF", "product": "x", "notes": ""}


def test_a_tagged_row_within_3_mm_prices_the_library_section():
    eu = tl.load("eu")
    sec = tl.item(eu, "75x75")
    assert tl.price_for([_row("75x75", 74, 74, 2500)], sec, 2500, "planed")        # planed 74 x 74
    assert tl.price_for([_row("75x75", 78, 78, 2500, "sawn")], sec, 2500, "sawn")  # sawn 78 x 78: 3 mm
    assert tl.price_for([_row("75x75", 72, 72, 2500)], sec, 2500, "planed")        # exactly 3 mm is still in
    assert tl.price_for([_row("75x75", 71, 71, 2500)], sec, 2500, "planed") is None
    # untagged: only the exact size counts; the tag is what says "this row stands for that item"
    assert tl.price_for([_row("", 74, 74, 2500)], sec, 2500, "planed") is None
    # the length still has to match and the variant too
    assert tl.price_for([_row("75x75", 74, 74, 2400)], sec, 2500, "planed") is None
    assert tl.price_for([_row("75x75", 74, 74, 2500, "impregnated")], sec, 2500, "planed") is None
    deck = tl.item(eu, "deck-28x145")
    assert tl.price_for([_row("deck-28x145", 27, 144, 2400, "impregnated")], deck, 2400, "impregnated")


def test_importer_refuses_an_item_tag_more_than_3_mm_from_the_library_size(tmp_path):
    head = ["# supplier: Test", "# region: hu", "# read_date: 2026-11-18", "# currency: HUF", "# prices: gross (incl. 27% VAT)",
            "source_url\tproduct\tkind\titem\tvariant\tspecies\tgrade\tthickness_mm\twidth_mm\tlength_mm\tunit\tpack_qty\tprice_net\tprice_gross\tnotes"]
    ok = "https://example.com/a\t24x48 lath\tlumber\t25x50\tsawn\t\t\t24\t48\t3000\tpiece\t1\t\t500\t"
    bad = "https://example.com/b\t21x45 lath\tlumber\t25x50\tsawn\t\t\t21\t45\t3000\tpiece\t1\t\t400\t"
    f = tmp_path / "hu-test-2026-11-18.tsv"
    f.write_text("\n".join(head + [ok]) + "\n", encoding="utf-8")
    rows, skipped = ti.convert_tsv(str(f), "hu", "Test", "2026-11-18", "HUF")
    assert len(rows) == 1 and rows[0]["item"] == "25x50" and not skipped
    f.write_text("\n".join(head + [ok, bad]) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        ti.convert_tsv(str(f), "hu", "Test", "2026-11-18", "HUF")
    msg = str(e.value)
    assert "hu-test-2026-11-18.tsv" in msg and "row 2" in msg and "25x50" in msg and "21 x 45" in msg and "3 mm" in msg


def test_every_tag_in_the_committed_raw_files_is_within_3_mm():
    import glob
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "timber", "prices", "raw", "*.tsv"))):
        head = ti.read_tsv(path)[0]
        ti.convert_tsv(path, head["region"], "x", head["read_date"], head["currency"])   # exits on a bad tag
