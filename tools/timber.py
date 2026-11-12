#!/usr/bin/env python3
"""The timber table: what a timber yard sells, what it's called, and what to buy.

    timber.py classify 50x100                     what this section is called
    timber.py sections [--snapshot CSV]           every section on offer, with lengths and price per m³
    timber.py buy 50x100 2400 12 [--variant impregnated] [--waste 10] [--kerf 4] [--snapshot CSV]
                                                  cheapest way to get 12 cuts of 2400 mm,
                                                  plus 10% spare for knots, splits and miscuts

Sizes are thickness x width in mm, smaller first ("50x100" = "100x50").
The price data is a dated snapshot in data/timber/prices/, made from a
supplier's price list by tools/timber_import.py. Without --snapshot the newest
snapshot for --region (default hu) is used. Everything here is plain
arithmetic on that table: the same snapshot and request always give the
same answer.
"""
import argparse, csv, glob, math, os, re, sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timberlib
from timberlib import ROOT, PRICES, TYPICAL, classify, money, allowance
# Hungarian size names, the snapshot reader and the spare rule live in
# timberlib so the shed tools share them; the library (sections, sheets,
# fasteners, units) is there too.


def section(s):
    try:
        return timberlib.parse_section(s)
    except ValueError as e:
        sys.exit(str(e))


def newest(region):
    try:
        return timberlib.newest_snapshot(region)
    except ValueError as e:
        sys.exit(str(e))


load = timberlib.load_snapshot


def cmd_classify(a):
    t, w = section(a.size)
    hu, en = classify(t, w)
    use = TYPICAL.get((int(t), int(w)), "")
    print(f"{t:g} x {w:g} mm: {hu} ({en})" + (f"; usually {use}" if use else ""))


def cmd_sections(a):
    rows = [r for r in load(a.snapshot) if r["kind"] == "lumber"]
    by = defaultdict(list)
    for r in rows:
        by[(r["thickness_mm"], r["width_mm"])].append(r)
    cur = rows[0]["currency"] if rows else ""
    print(f"{'section mm':>11}  {'name':<22} {'variants':<28} {'lengths m':<30} {'gross per m³':>16}")
    for (t, w), rs in sorted(by.items()):
        hu, en = classify(t, w)
        variants = ", ".join(sorted({r["variant"] for r in rs}))
        lengths = ", ".join(f"{l / 1000:g}" for l in sorted({r["length_mm"] for r in rs}))
        per = [float(r["gross_per_m3"]) for r in rs]
        rng = f"{min(per) / 1000:,.0f}k-{max(per) / 1000:,.0f}k {cur}"
        print(f"{t:>5g} x{w:>4g}  {hu + ' (' + en + ')':<22} {variants:<28} {lengths:<30} {rng:>16}")
    print(f"\nfrom {os.path.relpath(a.snapshot, ROOT)}")


def options(rows, t, w, variant, cut, qty, kerf):
    """Every way to buy qty cuts of `cut` mm from one stock length, cheapest first."""
    out = []
    for r in rows:
        if (r["kind"], r["thickness_mm"], r["width_mm"], r["variant"]) != ("lumber", t, w, variant):
            continue
        per = int((r["length_mm"] + kerf) // (cut + kerf))
        if per < 1:
            continue
        n = math.ceil(qty / per)
        offcut = r["length_mm"] - per * cut - (per - 1) * kerf
        out.append({"row": r, "per": per, "pieces": n, "cost": n * r["price_gross"],
                    "offcut": offcut, "spare": n * per - qty})
    return sorted(out, key=lambda o: (o["cost"], o["pieces"]))


def cmd_buy(a):
    t, w = section(a.size)
    rows = load(a.snapshot)
    extra = allowance(a.qty, a.waste)
    total = a.qty + extra
    opts = options(rows, t, w, a.variant, a.length, total, a.kerf)
    hu, en = classify(t, w)
    if not opts:
        have = sorted({(r["variant"], r["length_mm"]) for r in rows
                       if (r["thickness_mm"], r["width_mm"]) == (t, w)})
        sys.exit(f"{t:g}x{w:g} {a.variant}: nothing long enough for {a.length:g} mm. "
                 f"On offer: {', '.join(f'{v} {l / 1000:g} m' for v, l in have) or 'nothing in this size'}")
    cur = opts[0]["row"]["currency"]
    need = (f"{a.qty} cuts needed + {extra} spare ({a.waste:g}% for knots, splits and miscuts) = {total}"
            if extra else f"{a.qty} cuts, no spare allowance")
    print(f"{a.length:g} mm in {t:g} x {w:g} {a.variant} ({hu}, {en}), saw kerf {a.kerf:g} mm")
    print(f"{need}:")
    for i, o in enumerate(opts):
        r = o["row"]
        tag = "  best" if i == 0 else ""
        cuts = f"{o['per']} cut{'s' if o['per'] > 1 else ''} each"
        wood = f" {r['species']}" if r["species"] else ""
        print(f"  buy {o['pieces']:>3} x {r['length_mm'] / 1000:g} m{wood}  ({cuts}, "
              f"{o['offcut']:g} mm offcut each" + (f", {o['spare']} more than that" if o["spare"] else "") + ")  "
              f""
              f"{money(o['cost'], cur):>14} gross{tag}")
    r = opts[0]["row"]
    print(f"\nprices: {r['supplier']}, read {r['read_date']}  ({os.path.relpath(a.snapshot, ROOT)})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--region", default="hu")
    ap.add_argument("--snapshot", help="a price CSV in data/timber/prices/ (default: newest for --region)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classify"); c.add_argument("size")
    sub.add_parser("sections")
    b = sub.add_parser("buy")
    b.add_argument("size"); b.add_argument("length", type=float, help="cut length in mm")
    b.add_argument("qty", type=int)
    b.add_argument("--variant", default="sawn", choices=["sawn", "planed", "impregnated"])
    b.add_argument("--kerf", type=float, default=4, help="saw blade width in mm (default 4)")
    b.add_argument("--waste", type=float, default=10,
                   help="spare cuts for defects and miscuts, in %% of the count, rounded up (default 10; 0 for none)")
    a = ap.parse_args()
    if a.cmd != "classify":
        a.snapshot = a.snapshot or newest(a.region)
    {"classify": cmd_classify, "sections": cmd_sections, "buy": cmd_buy}[a.cmd](a)


if __name__ == "__main__":
    main()
