#!/usr/bin/env python3
"""Turn a timber yard's price list, as text, into a price snapshot CSV.

    timber_import.py <raw.txt> <out.csv> --supplier "Name" --region hu --date YYYY-MM-DD

The raw text is what you get by copying a supplier's price tables: one product
per line, name, net price and gross price separated by tabs. Lines starting
with "## " name the page the following rows came from; lines starting with "#"
are comments. Nothing is fetched from the internet here: the raw text is kept
in the repo next to the CSV, so the CSV can always be rebuilt from it.

Understands names like these (Hungarian timber yards):
    5cmx10cmx2fm gyalult            section in cm, length in running metres
    2,5cmx12cmx4fm Impregnált ...   decimal commas
    Gyalult deszka 19mm*116mm*4fm   mm sizes, * or x or ×
    Gyalult palló Borovi 45mm x 95mm x 5,4m C24
    Egalizált léc 3 fm 28mmx48mm    length first
    Pipaléc 20*30*2fm               bare numbers: mm, mm, m
    OSB-3 12mm (1250*2500/ 3,125m2) sheets: thickness, then sheet size

Each row gets: kind (lumber or sheet), variant (sawn, planed, impregnated),
thickness, width and length in mm, species and grade where named, prices,
and computed price per m³, per running metre (lumber) and per m² (sheets).
Lines it can't read are listed on stderr and left out; it never guesses.

The other format is a tab-separated file with "# key: value" header lines (supplier,
region, read_date, currency, prices) and a header row, one row per product, for any
kind of item: lumber, sheets, fasteners and bought items (nails by the box, screws by
the pack, felt by the roll, trims, ground screws). It is detected by its header row
(source_url, product, kind, item, ...); the columns are described in data/timber/README.md.
--supplier, --region, --date and --currency then default to the header lines (the supplier
is shortened to its name before the first bracket, comma or dash).
EU files give gross or net prices (the other is computed from the VAT rate in the
"# prices:" line); US files give the shelf price, before sales tax, as both.
"""
import argparse, csv, os, re, sys

NUM = r"(\d+(?:[.,]\d+)?)"


def num(s):
    return float(s.replace(",", "."))


def money(s):
    s = s.replace("Ft", "").replace(" ", "").replace(" ", "").replace(",", ".")
    return float(s)


def sizes(name):
    """(thickness_mm, width_mm, length_mm, kind) or None."""
    n = name.replace("×", "x").replace("*", "x")
    # sheets: "OSB-3 12mm (1250x2500/ 3,125m2 )", "Ecopanel 10mm (1150x2200) ... 2,53m2/tábla"
    m = re.search(rf"{NUM}\s*mm\s*(?:NF\s*)?\(\s*{NUM}\s*x\s*{NUM}", n)
    if m and re.search(r"OSB|panel|lemez", n, re.I):
        t, a, b = (num(g) for g in m.groups())
        area = re.search(rf"{NUM}\s*m2", n)
        if area:  # sizes may be in cm, even mixed ("67,5x2500" for 675 x 2500 mm):
            want = num(area.group(1))  # trust the stated area to pick the units
            for ka, kb in ((1, 1), (10, 10), (10, 1), (1, 10)):
                if abs(a * ka * b * kb / 1e6 - want) / want < 0.03:
                    a, b = a * ka, b * kb
                    break
            else:
                return None
        return t, min(a, b), max(a, b), "sheet"
    pats = [
        (rf"{NUM}\s*cm\s*x\s*{NUM}\s*cm\s*x\s*{NUM}\s*f?m\b", (10, 10, 1000), "tw l"),
        (rf"{NUM}\s*mm\s*x\s*{NUM}\s*mm\s*x\s*{NUM}\s*f?m\b", (1, 1, 1000), "tw l"),
        (rf"{NUM}\s*f?m\s+{NUM}\s*mm\s*x\s*{NUM}\s*mm", (1000, 1, 1), "l tw"),
        (rf"{NUM}\s*f?m\s+{NUM}\s*x\s*{NUM}\s*mm", (1000, 1, 1), "l tw"),
        (rf"\b{NUM}\s*x\s*{NUM}\s*x\s*{NUM}\s*fm\b", (1, 1, 1000), "tw l"),
    ]
    for pat, scale, order in pats:
        m = re.search(pat, n, re.I)
        if m:
            v = [num(g) * s for g, s in zip(m.groups(), scale)]
            if order == "l tw":
                v = [v[1], v[2], v[0]]
            t, w, l = v
            return min(t, w), max(t, w), l, "lumber"
    return None


UNITS = ("piece", "box", "pack", "roll", "m2", "m", "kg")
KINDS = ("lumber", "sheet", "fastener", "bought")
TSV_COLUMNS = ["source_url", "product", "kind", "item", "variant", "species", "grade", "thickness_mm",
               "width_mm", "length_mm", "unit", "pack_qty", "price_net", "price_gross", "notes"]
OUT_COLUMNS = ["region", "supplier", "read_date", "source_url", "product", "kind", "item", "variant",
               "species", "grade", "notes", "thickness_mm", "width_mm", "length_mm", "unit", "pack_qty",
               "price_net", "price_gross", "currency", "gross_per_m3", "gross_per_m", "gross_per_m2"]
VARIANTS = ("sawn", "planed", "impregnated")


def is_tsv(path):
    """True for the tab-separated format: it has a header row starting with source_url."""
    with open(path, encoding="utf-8") as f:
        return any(line.startswith("source_url\t") for line in f)


def plain_number(s):
    """A number with a decimal point and no thousands separators; ValueError otherwise."""
    s = s.strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", s):
        raise ValueError(s)
    return float(s)


def read_tsv(path):
    """(header dict, rows as dicts, unreadable lines with the reason) of a raw TSV file."""
    head, cols, rows, bad = {}, None, [], []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n").rstrip("\r")
        if not line.strip():
            continue
        if line.startswith("#"):
            k, _, v = line[1:].partition(":")
            head[k.strip().lower()] = v.strip()
            continue
        parts = line.split("\t")
        if cols is None:
            if parts[0] != "source_url":
                bad.append((line, "no header row before the first product")); continue
            cols = [c.strip() for c in parts]
            missing = [c for c in TSV_COLUMNS if c not in cols]
            if missing:
                raise SystemExit(f"{path}: header row lacks column(s) {', '.join(missing)}")
            continue
        if len(parts) > len(cols):
            bad.append((line, f"{len(parts)} columns, the header has {len(cols)}")); continue
        parts += [""] * (len(cols) - len(parts))
        rows.append(dict(zip(cols, (p.strip() for p in parts))))
    return head, rows, bad


def short_name(supplier):
    """A supplier's short name for the shopping list: the header's text up to its first bracket,
    comma or dash ('Larex Fatelep (Larex-Trade Kft.), Budapest' -> 'Larex Fatelep')."""
    return re.split(r"\s+\(|,|\s+[-–]\s", supplier, maxsplit=1)[0].strip() or supplier


def vat_of(head):
    """('gross' | 'net' | 'shelf', vat fraction or None) from the "# prices:" header line."""
    txt = head.get("prices", "").lower()
    if "sales tax" in txt:
        return "shelf", None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", txt)
    vat = num(m.group(1)) / 100 if m else None
    return ("net" if re.search(r"\bnet\b|excl", txt) else "gross"), vat


def item_size_error(lib, key, kind, t, w, l):
    """Why a lumber or sheet row may not carry library item `key`, or "". A row stands for a
    library section, sheet or cladding board only within timberlib.SIZE_TOL_MM of its thickness
    and width (sheets: and sides); a bigger difference is a different product."""
    import timberlib as tl
    try:
        it = tl.item(lib, key)
    except KeyError:
        return f"item {key!r} is not in the {lib.get('region', '?')} library"
    if it["category"] not in ("sections", "cladding", "sheets"):
        return f"item {key!r} is not a board or a sheet"
    gap = tl.size_gap(it, t, w, l if kind == "sheet" else None)
    if gap <= tl.SIZE_TOL_MM:
        return ""
    want = (f"{it['thickness_mm']:g} x {'x'.join(f'{x:g}' for x in sorted(it['size_mm']))}" if it["category"] == "sheets"
            else f"{it['thickness_mm']:g} x {it.get('width_mm', it.get('face_width_mm')):g}")
    got = f"{t:g} x {w:g}" + (f" x {l:g}" if kind == "sheet" else "")
    return (f"item {key!r} is {want} mm but the row is {got} mm: more than {tl.SIZE_TOL_MM} mm apart "
            f"is a different product, so the row cannot be tagged with it")


def convert_tsv(path, region, supplier, date, currency):
    """(snapshot rows, [(line, reason)]) from a raw TSV file."""
    head, raw, skipped = read_tsv(path)
    import timberlib as tl
    lib = tl.load(tl.LIBRARY_OF.get(region, region)) if region in tl.LIBRARY_OF else None
    n_row = 0
    mode, vat = vat_of(head)
    out = []
    for r in raw:
        line = "\t".join(r.values())
        n_row += 1

        def bad(why):
            skipped.append((line, why))
        kind, unit = r["kind"].lower(), (r["unit"].lower() or "piece")
        if not r["source_url"].startswith("http"):
            bad("no source_url"); continue
        if not r["product"]:
            bad("no product name"); continue
        if kind not in KINDS:
            bad(f"kind {r['kind']!r} is not one of {', '.join(KINDS)}"); continue
        if unit not in UNITS:
            bad(f"unit {r['unit']!r} is not one of {', '.join(UNITS)}"); continue
        try:
            nums = {k: (plain_number(r[k]) if r[k] else None)
                    for k in ("thickness_mm", "width_mm", "length_mm", "pack_qty", "price_net", "price_gross")}
        except ValueError as e:
            bad(f"{e.args[0]!r} is not a number (decimal point, no thousands separators)"); continue
        pn, pg = nums["price_net"], nums["price_gross"]
        if pn is None and pg is None:
            bad("no price"); continue
        if pn is not None and pn <= 0 or pg is not None and pg <= 0:
            bad("price is zero or negative"); continue
        if mode == "shelf":     # US: the shelf price, before sales tax, is the one price
            if pn is not None and pg is not None and abs(pg - pn) > 0.005:
                bad("US files give one shelf price, in price_net"); continue
            pn = pg = pn if pn is not None else pg
        else:
            if pg is None and vat is None:
                bad("only the net price is given and the header has no VAT rate, so there is no gross price"); continue
            if pn is None:
                pn = pg / (1 + vat) if vat is not None else None      # no VAT rate in the header: net stays blank
            elif pg is None:
                pg = pn * (1 + vat)
            elif vat is not None and abs(pn * (1 + vat) - pg) > max(0.03 * pg, 0.5):
                bad(f"net and gross don't match the {vat * 100:g}% VAT"); continue
        if kind in ("fastener", "bought") and not r["item"]:
            bad("a fastener or bought item needs an item key"); continue
        if unit in ("box", "pack", "roll") and not nums["pack_qty"]:
            bad(f"unit {unit} needs pack_qty"); continue
        variant = r["variant"].lower()
        t = w = l = None
        if kind in ("lumber", "sheet"):
            t, w, l = nums["thickness_mm"], nums["width_mm"], nums["length_mm"]
            if not (t and w and l):
                bad("lumber and sheets need thickness_mm, width_mm and length_mm"); continue
            if unit not in ("piece", "m2", "m"):
                bad(f"{kind} must be priced per piece, m2 or m, not per {unit}"); continue
            if kind == "sheet":
                variant = "sheet"
                t, w, l = t, min(w, l), max(w, l)
            elif variant not in VARIANTS:
                bad(f"lumber variant {r['variant']!r} is not one of {', '.join(VARIANTS)}"); continue
            else:
                t, w = min(t, w), max(t, w)
            if r["item"] and lib:
                err = item_size_error(lib, r["item"], kind, t, w, l)
                if err:
                    raise SystemExit(f"{path}, product row {n_row} ({r['product']}): {err}")
            if unit != "piece":     # a price per m2 or per m is turned into the price of the piece of the stated size
                f = w * l / 1e6 if unit == "m2" else l / 1000
                pn, pg = (x * f if x is not None else None for x in (pn, pg))
                note = f"price per {unit} x {f:.4g} {unit} per piece"
                r["notes"] = f"{r['notes']}; {note}" if r["notes"] else note
                unit = "piece"
        else:
            t, w, l = nums["thickness_mm"], nums["width_mm"], nums["length_mm"]
        fmt = lambda x: f"{x:g}" if x is not None else ""
        row = {"region": region, "supplier": supplier, "read_date": date, "source_url": r["source_url"],
               "product": r["product"], "kind": kind, "item": r["item"], "variant": variant,
               "species": r["species"], "grade": r["grade"], "notes": r["notes"],
               "thickness_mm": fmt(t), "width_mm": fmt(w), "length_mm": fmt(l), "unit": unit,
               "pack_qty": "1" if kind in ("lumber", "sheet") else
               (fmt(nums["pack_qty"]) if nums["pack_qty"] else ("1" if unit in ("piece", "m", "m2", "kg") else "")),
               "price_net": f"{pn:.2f}" if pn is not None else "", "price_gross": f"{pg:.2f}", "currency": currency,
               "gross_per_m3": "", "gross_per_m": "", "gross_per_m2": ""}
        if kind in ("lumber", "sheet"):
            vol = t * w * l / 1e9
            row["gross_per_m3"] = f"{pg / vol:.0f}"
            if kind == "lumber":
                row["gross_per_m"] = f"{pg / (l / 1000):.0f}"
            else:
                row["gross_per_m2"] = f"{pg / (w * l / 1e6):.0f}"
        out.append(row)
    return out, skipped


def sort_key(r):
    f = lambda k: float(r[k]) if r[k] != "" else 0.0
    return (KINDS.index(r["kind"]), r["item"] if r["kind"] in ("fastener", "bought") else "",
            f("thickness_mm"), f("width_mm"), r["variant"], r["species"], f("length_mm"),
            r["product"], f("pack_qty"))


def describe(name):
    low = name.lower()
    if "impregn" in low:
        variant = "impregnated"
    elif "gyalult" in low or "egalizált" in low:
        variant = "planed"
    else:
        variant = "sawn"
    species = ("larch" if "vörösfenyő" in low else "pine" if "borovi" in low
               else "spruce" if re.search(r"\bluc\b|lucfenyő", low) else "")
    grade = " ".join(re.findall(r"\b(C\d{2}|A/B)\b", name))
    notes = " ".join(x for x in ("dried" if "szárított" in low else "",
                                 "tongue and groove" if re.search(r"\bNF\b", name) else "") if x)
    return variant, species, grade, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("--supplier", help="required for the text format; a TSV file has it in its header")
    ap.add_argument("--region", help="required for the text format; a TSV file has it in its header")
    ap.add_argument("--date", help="the day the prices were read, YYYY-MM-DD (required for the text format)")
    ap.add_argument("--currency", help="default HUF for the text format; a TSV file has it in its header")
    a = ap.parse_args()

    if is_tsv(a.raw):
        head = read_tsv(a.raw)[0]
        supplier = a.supplier or (short_name(head["supplier"]) if head.get("supplier") else None)
        region = a.region or head.get("region")
        date, currency = a.date or head.get("read_date"), a.currency or head.get("currency")
        for name, v in (("supplier", supplier), ("region", region), ("read_date", date), ("currency", currency)):
            if not v:
                sys.exit(f"{a.raw}: no {name} (a '# {name}: ...' header line, or the command-line option)")
        rows, skipped = convert_tsv(a.raw, region, supplier, date, currency)
        skipped = [f"{line}   [{why}]" for line, why in skipped]
    else:
        for name in ("supplier", "region", "date"):
            if not getattr(a, name):
                sys.exit(f"the text format needs --{name}")
        rows, skipped = convert_text(a.raw, a.region, a.supplier, a.date, a.currency or "HUF")
    rows.sort(key=sort_key)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=OUT_COLUMNS)
        wr.writeheader()
        wr.writerows(rows)
    print(f"{len(rows)} products -> {a.out}")
    for s in skipped:
        print(f"  not understood, left out: {s}", file=sys.stderr)
    return 1 if skipped else 0


def convert_text(path, region, supplier, date, currency):
    """(snapshot rows, unreadable lines) from the Hungarian text format."""
    rows, skipped, url = [], [], ""
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("## "):
            url = line[3:].strip()
            continue
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            skipped.append(line); continue
        name, net, gross = parts[0].strip(), parts[1], parts[2]
        dims = sizes(name)
        try:
            pn, pg = money(net), money(gross)
        except ValueError:
            dims = None
        if not dims:
            skipped.append(line); continue
        t, w, l, kind = dims
        variant, species, grade, notes = describe(name)
        if kind == "sheet":
            variant = "sheet"
        vol = t * w * l / 1e9
        rows.append({
            "region": region, "supplier": supplier, "read_date": date, "source_url": url,
            "product": name, "kind": kind, "item": "", "variant": variant, "species": species, "grade": grade,
            "notes": notes, "thickness_mm": f"{t:g}", "width_mm": f"{w:g}", "length_mm": f"{l:g}",
            "unit": "piece", "pack_qty": "1",
            "price_net": f"{pn:.2f}", "price_gross": f"{pg:.2f}", "currency": currency,
            "gross_per_m3": f"{pg / vol:.0f}",
            "gross_per_m": f"{pg / (l / 1000):.0f}" if kind == "lumber" else "",
            "gross_per_m2": f"{pg / (w * l / 1e6):.0f}" if kind == "sheet" else "",
        })
    return rows, skipped


if __name__ == "__main__":
    sys.exit(main())
