#!/usr/bin/env python3
"""Material library and units for timber structures.

    import timberlib
    lib = timberlib.load("eu")                 # data/timber/library/eu.json
    timberlib.item(lib, "50x100")              # one section, sheet, cladding, fastener or bought item
    timberlib.fmt_length(2400, "metric")       # '2400 mm'
    timberlib.fmt_length(2400, "imperial")     # '7\' 10-1/2"'
    timberlib.parse_length("7' 10-1/2\"")      # 2400.3 (mm)
    timberlib.price_for(rows, timberlib.item(lib, "50x100"), 3000, "sawn")

Everything is stored in millimetres; the units setting only changes how a
length is shown. Also holds what tools/timber.py shares: the Hungarian size
names, the snapshot reader and the spare-allowance rule.
"""
import csv, glob, json, math, os, re
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES = os.path.join(ROOT, "data", "timber", "prices")
LIBRARY = os.path.join(ROOT, "data", "timber", "library")

CATEGORIES = ("sections", "sheets", "cladding", "fasteners", "bought")
RULE_KINDS = ("per_joint", "per_crossing", "every_mm")
WEIGHT_UNITS = ("kg", "lb")   # nails are sold by weight; screws in packs
JOINT_TYPES = ("stud-plate", "plate-plate", "joist-rim", "rafter-plate",
               "header-trimmer", "sheet-frame", "board-frame",
               "king-jack", "jack-header", "plate-lap", "corner-stud",
               "blocking-rafter", "fascia-rafter", "barge-rafter",
               "rafter-ridge", "tie-rafter", "tie-plate",
               "post-base", "beam-post", "beam-cap", "beam-ply", "joist-beam", "deck-board",
               "brace-post", "brace-beam", "brace-rafter", "rafter-beam", "slat-rafter")
MM_PER_IN = 25.4


# --------------------------------------------------------------- the library

def load(region):
    """The library for a region ('eu' or 'us') as a dict."""
    path = os.path.join(LIBRARY, f"{region}.json")
    if not os.path.exists(path):
        have = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(LIBRARY, "*.json")))
        raise ValueError(f"no timber library for region {region!r}; have: {', '.join(have) or 'none'}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def item(lib, key):
    """One item by key, as a copy with `key` and `category` added.
    Keys are unique across sections, sheets, cladding, fasteners and bought items."""
    for cat in CATEGORIES:
        if key in lib.get(cat, {}):
            d = dict(lib[cat][key])
            d["key"], d["category"] = key, cat
            return d
    raise KeyError(f"{key!r} is not in the {lib.get('region', '?')} library")


def items(lib, category):
    return [item(lib, k) for k in lib.get(category, {})]


def validate(lib):
    """List of problems with a library; empty when it is sound."""
    bad = []
    seen = {}
    for cat in CATEGORIES:
        for k in lib.get(cat, {}):
            if k in seen:
                bad.append(f"key {k!r} is in both {seen[k]} and {cat}")
            seen[k] = cat
    src_ids = {s["id"] for s in lib.get("sources", [])}
    if not src_ids:
        bad.append("no sources")

    def check_src(path, d):
        ids = d.get("sources") if isinstance(d, dict) else None
        if not ids:
            bad.append(f"{path}: no sources")
        for i in ids or []:
            if i not in src_ids:
                bad.append(f"{path}: unknown source {i!r}")

    for cat in CATEGORIES:
        for k, d in lib.get(cat, {}).items():
            check_src(f"{cat}.{k}", d)
    for k, d in lib.get("grades", {}).items():
        check_src(f"grades.{k}", d)
    check_src("defaults", lib.get("defaults"))

    for k, d in lib.get("sections", {}).items():
        if not (d["thickness_mm"] > 0 and d["width_mm"] >= d["thickness_mm"]):
            bad.append(f"sections.{k}: thickness must not exceed width")
        if sorted(d["stock_lengths_mm"]) != d["stock_lengths_mm"] or not d["stock_lengths_mm"]:
            bad.append(f"sections.{k}: stock lengths must be a sorted, non-empty list")
    for k, d in lib.get("sheets", {}).items():
        if len(d["size_mm"]) != 2 or d["size_mm"][0] > d["size_mm"][1]:
            bad.append(f"sheets.{k}: size_mm must be [short, long]")
    for k, d in lib.get("cladding", {}).items():
        if not 0 < d["cover_width_mm"] <= d["face_width_mm"]:
            bad.append(f"cladding.{k}: cover width must be positive and not exceed the board width")

    rules = {t: r for t, r in lib.get("joint_rules", {}).items() if not t.startswith("_")}
    for t in JOINT_TYPES:
        if t not in rules:
            bad.append(f"joint_rules: no rule for {t!r}")
    for t, r in rules.items():
        for part in [r] + list(r.get("also", [])):
            if part.get("fastener") not in lib.get("fasteners", {}):
                bad.append(f"joint_rules.{t}: fastener {part.get('fastener')!r} is not in the library")
            if sum(1 for kd in RULE_KINDS if kd in part) != 1:
                bad.append(f"joint_rules.{t}: needs exactly one of {', '.join(RULE_KINDS)}")
    for k, d in lib.get("fasteners", {}).items():
        if d.get("type") == "nail":
            unit = d.get("weight_unit")
            if unit not in WEIGHT_UNITS or not d.get(f"pcs_per_{unit}") or not d.get(f"box_{unit}"):
                bad.append(f"fasteners.{k}: a nail needs weight_unit (kg or lb), pcs_per_<unit> and box_<unit>")
        elif not d.get("pack_sizes"):
            bad.append(f"fasteners.{k}: needs pack_sizes")

    df = lib.get("defaults", {})
    for role, key in df.get("items", {}).items():
        if key not in seen:
            bad.append(f"defaults.items.{role}: {key!r} is not in the library")
    if df.get("grade") not in lib.get("grades", {}):
        bad.append(f"defaults.grade: {df.get('grade')!r} is not a grade in the library")
    for cov in df.get("min_roof_pitch_deg", {}):
        if cov not in lib.get("bought", {}) and cov not in ("metal-sheet", "asphalt-shingle"):
            bad.append(f"defaults.min_roof_pitch_deg: unknown covering {cov!r}")
    return bad


def unverified(lib):
    """Paths of every library entry whose numbers are marked unverified."""
    out = []

    def walk(prefix, d):
        for k, v in d.items():
            if k in ("sources",):
                continue
            if k in ("unverified", "unverified_stock_lengths", "density_unverified") and v:
                out.append(prefix if k == "unverified" else f"{prefix} ({k})")
            elif isinstance(v, dict):
                walk(f"{prefix}.{k}" if prefix else k, v)
    walk("", {c: lib[c] for c in lib if isinstance(lib[c], dict)})
    return sorted(set(out))


# -------------------------------------------------------------------- lengths

def fmt_length(mm, units="metric"):
    """'2400 mm', or for imperial feet, inches and sixteenths: 7' 10-1/2"."""
    if units == "metric":
        return f"{round(mm, 1):g} mm"
    if units != "imperial":
        raise ValueError(f"units must be 'metric' or 'imperial', not {units!r}")
    sixteenths = round(abs(mm) / MM_PER_IN * 16)
    sign = "-" if mm < 0 and sixteenths else ""
    feet, rest = divmod(sixteenths, 16 * 12)
    inches, frac = divmod(rest, 16)
    f = Fraction(frac, 16)
    inch = ""
    if inches or frac:
        inch = f"{inches}" if not frac else (f"{inches}-{f.numerator}/{f.denominator}" if inches else f"{f.numerator}/{f.denominator}")
    if feet and inch:
        return f"{sign}{feet}' {inch}\""
    if feet:
        return f"{sign}{feet}'"
    return f"{sign}{inch}\"" if inch else "0\""


_NUM = r"\d+(?:\.\d+)?"
_INCHES = rf"(?:(?P<iw>{_NUM})(?:[\s-]+(?P<fn>\d+)/(?P<fd>\d+))?|(?P<on>\d+)/(?P<od>\d+))"


def parse_length(text):
    """Length in mm from '2400', '2400 mm', '2.4 m', '240 cm', 7' 10-1/2", 8', '5 ft 3 in', '96"'.
    A bare number is millimetres. Raises ValueError when it can't be read."""
    s = str(text).strip().lower().replace("″", '"').replace("′", "'").replace("”", '"')
    if not s:
        raise ValueError("empty length")
    m = re.fullmatch(rf"(?P<n>{_NUM})\s*(?P<u>mm|cm|m)?", s)
    if m:
        return float(m.group("n")) * {None: 1, "mm": 1, "cm": 10, "m": 1000}[m.group("u")]
    m = re.fullmatch(rf"(?:(?P<ft>{_NUM})\s*(?:'|ft|feet|foot)\s*[- ]?\s*)?(?:{_INCHES}\s*(?:\"|in|inch|inches)?)?", s)
    if m and (m.group("ft") or m.group("iw") or m.group("on")):
        inches = 0.0
        if m.group("iw") is not None:
            inches = float(m.group("iw"))
            if m.group("fn"):
                inches += int(m.group("fn")) / int(m.group("fd"))
        elif m.group("on") is not None:
            inches = int(m.group("on")) / int(m.group("od"))
        ft = float(m.group("ft")) if m.group("ft") else 0.0
        if not m.group("ft") and not re.search(r"\"|in", s):
            raise ValueError(f"can't read length {text!r}")
        return (ft * 12 + inches) * MM_PER_IN
    raise ValueError(f"can't read length {text!r}")


# --------------------------------------------------- Hungarian size names, etc.
# Shared with tools/timber.py.

TYPICAL = {   # what the common sections are usually used for in a small building
    (25, 50): "roof and cladding battens", (30, 50): "roof battens (tile battens)",
    (50, 50): "light framing, noggins, counter battens",
    (25, 100): "cladding, fencing", (25, 150): "cladding, floorboards, fascia",
    (50, 100): "wall studs, plates, light joists", (50, 150): "floor joists, rafters",
    (50, 200): "floor joists and rafters over longer spans",
    (100, 100): "posts, sills", (75, 150): "rafters, beams", (100, 150): "beams, sills",
    (120, 120): "posts", (150, 150): "heavy posts and beams",
}


def classify(t, w):
    """Hungarian and English name of a section, as timber yards use them (rules
    as published by szekelyfatelep.hu, adjusted to how the yards list them):
      deszka (board) 12-40 mm thick, at least 60 mm wide; léc (batten) narrower;
      palló (plank) over 40 mm, at least twice as wide as thick; zárléc (square
      batten) over 40 mm, less than twice as wide; gerenda (beam) 75 mm thick or more."""
    t, w = sorted((t, w))
    if t < 12:
        return "lap", "sheet or strip"
    if t <= 40:
        return ("deszka", "board") if w >= 60 else ("léc", "batten")
    if t < 75:
        return ("palló", "plank") if w >= 2 * t else ("zárléc", "square batten")
    return "gerenda", "beam"


def parse_section(s):
    """(thickness, width) in mm, smaller first, from '50x100', '50 × 100' or '50*100'."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*", s)
    if not m:
        raise ValueError(f"section must look like 50x100 (mm), not {s!r}")
    return tuple(sorted((float(m.group(1)), float(m.group(2)))))


def newest_snapshot(region):
    """Path of the newest price snapshot for a region; ValueError when there is none."""
    def stamp(p):
        d = re.findall(r"\d{4}-\d{2}-\d{2}", p)
        return d[-1] if d else ""
    files = sorted(glob.glob(os.path.join(PRICES, f"{region}-*.csv")), key=stamp)
    if not files:
        raise ValueError(f"no price snapshot for region {region!r} in {PRICES}")
    return files[-1]


def load_snapshot(path):
    """Rows of a price snapshot CSV, numbers as floats."""
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("thickness_mm", "width_mm", "length_mm", "price_gross", "price_net"):
            r[k] = float(r[k])
    return rows


def money(x, cur):
    return f"{x:,.0f} {cur}".replace(",", " ")


def allowance(qty, waste_pct):
    """Spare cuts for defects and mistakes: waste_pct of the count, rounded up,
    so even a small order gets one spare. No timber is perfect."""
    return math.ceil(qty * waste_pct / 100 - 1e-9) if waste_pct > 0 else 0


# ---------------------------------------------------------------------- prices

def price_for(snapshot_rows, it, length_mm=None, variant="sawn", tol_mm=0.5):
    """The snapshot row that sells library item `it` (from item()), or None.

    Sections (and cladding) are matched by actual size, thickness and width,
    either way round, against lumber rows of that variant and exactly that
    length. Sheets are matched by thickness and sheet size; `length_mm` and
    `variant` are ignored. Returns {price_gross, price_net, currency, row}.
    A snapshot lists sizes as the supplier names them, so this finds only what
    the supplier sells at that size: an item with no row gets None, never a
    price for a different size."""
    def near(a, b):
        return abs(a - b) <= tol_mm

    def hit(r):
        return {"price_gross": r["price_gross"], "price_net": r["price_net"],
                "currency": r["currency"], "row": r}

    if it["category"] == "sheets":
        short, long_ = it["size_mm"]
        for r in snapshot_rows:
            if (r["kind"] == "sheet" and near(r["thickness_mm"], it["thickness_mm"])
                    and near(r["width_mm"], short) and near(r["length_mm"], long_)):
                return hit(r)
        return None
    if it["category"] not in ("sections", "cladding"):
        return None
    if length_mm is None:
        raise ValueError("price_for needs a length for timber")
    t = it["thickness_mm"]
    w = it.get("width_mm", it.get("face_width_mm"))
    rows = [r for r in snapshot_rows
            if r["kind"] == "lumber" and r["variant"] == variant
            and near(min(r["thickness_mm"], r["width_mm"]), min(t, w))
            and near(max(r["thickness_mm"], r["width_mm"]), max(t, w))
            and near(r["length_mm"], length_mm)]
    return hit(min(rows, key=lambda r: r["price_gross"])) if rows else None
