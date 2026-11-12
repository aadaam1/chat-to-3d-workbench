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
"""
import argparse, csv, re, sys

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
    ap.add_argument("--supplier", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--date", required=True, help="the day the prices were read, YYYY-MM-DD")
    ap.add_argument("--currency", default="HUF")
    a = ap.parse_args()

    cols = ["region", "supplier", "read_date", "source_url", "product", "kind", "variant",
            "species", "grade", "notes", "thickness_mm", "width_mm", "length_mm",
            "price_net", "price_gross", "currency", "gross_per_m3", "gross_per_m", "gross_per_m2"]
    rows, skipped, url = [], [], ""
    for line in open(a.raw, encoding="utf-8"):
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
            "region": a.region, "supplier": a.supplier, "read_date": a.date, "source_url": url,
            "product": name, "kind": kind, "variant": variant, "species": species, "grade": grade,
            "notes": notes, "thickness_mm": f"{t:g}", "width_mm": f"{w:g}", "length_mm": f"{l:g}",
            "price_net": f"{pn:.2f}", "price_gross": f"{pg:.2f}", "currency": a.currency,
            "gross_per_m3": f"{pg / vol:.0f}",
            "gross_per_m": f"{pg / (l / 1000):.0f}" if kind == "lumber" else "",
            "gross_per_m2": f"{pg / (w * l / 1e6):.0f}" if kind == "sheet" else "",
        })
    rows.sort(key=lambda r: (r["kind"], float(r["thickness_mm"]), float(r["width_mm"]),
                             r["variant"], r["species"], float(r["length_mm"])))
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)
    print(f"{len(rows)} products -> {a.out}")
    for s in skipped:
        print(f"  not understood, left out: {s}", file=sys.stderr)
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
