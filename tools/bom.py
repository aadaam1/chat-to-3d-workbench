#!/usr/bin/env python3
"""Shopping list and cut list for a timber structure.

    bom.py <frame.json> [--snapshot <csv>] [--waste 10] [--kerf 4] [--sheet-spare 0] [--trim 20] --out <dir>

Reads the frame file written by tools/frame.py and writes, into <dir>:
  bom.json     everything below, for other tools
  bom.md       what to hand a timber yard (lengths in the frame's units)
  cutlist.csv  one row per cut and per sheet part, in millimetres; the `what`
               column says in plain words what each piece is (Stud, King stud, ...)

What it works out:
  * Timber and cladding boards: the cuts of each item and variant are packed
    onto the stock lengths on offer (the price snapshot's lengths when it
    sells that item, else the library's), first-fit decreasing with the saw
    kerf between cuts. Every single stock length is tried, and a mix (pack on
    the longest, then give each piece the cheapest length that still holds
    its cuts). The cheapest plan wins when every piece has a price, else the
    one with the least waste; ties go to fewer pieces, then a single length.
  * Sheets: bounding rectangles on full sheets, shelf algorithm (first-fit
    decreasing height), kerf between parts, rotation only where the library
    says the sheet can rotate (OSB, plywood).
  * Fasteners: counted from `joints` with the library's `joint_rules`, plus
    the spare margin. Nails are sold by weight: the count becomes kg (lb in
    the US) and is rounded up to the smallest combination of boxes. Structural
    screws (rafter to plate, wall corners) are sold in packs.
  * Bought items are copied through.
  * Spare: `--waste` percent of every piece count, rounded up (the rule of
    tools/timber.py). The spare pieces are of the longest stock length bought
    (timber, cladding) or full sheets, so any cut can be remade.
  * Prices (gross) from the snapshot where it sells the item, else the line
    says "no price" and the total is marked partial.

Same frame and options give the same files.
"""
import argparse, csv, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timberlib as tl

SCHEMA = 1
EPS = 1e-6

# What a member is, in plain words (the same names as KIND in tools/viewer/viewer.html),
# with the plural used in the shopping list. The order is the order counts are listed in.
SAFETY_NOTE = ("> Guidance, not structural engineering: the checks are simple formulas and rules of thumb, and "
               "so are the fixing counts. Check your local rules and permits, and have a qualified person look at "
               "anything people stand under, anything that carries snow, or anything that needs a permit. Prices "
               "are a dated snapshot, not an offer. Check everything before you build: building it is your "
               "responsibility (see DISCLAIMER.md).")

KIND_NAMES = {
    "joist": ("Floor joist", "floor joists"), "rim": ("Rim joist", "rim joists"),
    "plate": ("Plate", "plates"), "stud": ("Stud", "studs"), "king": ("King stud", "king studs"),
    "jack": ("Jack stud", "jack studs"), "cripple": ("Cripple stud", "cripple studs"),
    "header": ("Header", "headers"), "trimmer": ("Trimmer", "trimmers"), "sill": ("Sill", "sills"),
    "rafter": ("Rafter", "rafters"), "flying-rafter": ("Flying rafter", "flying rafters"),
    "blocking": ("Blocking", "blocking pieces"), "outrigger": ("Outrigger", "outriggers"),
    "fascia": ("Fascia", "fascias"), "bargeboard": ("Bargeboard", "bargeboards"),
    "ridge": ("Ridge board", "ridge boards"), "tie": ("Rafter tie", "rafter ties"),
    "brace": ("Brace", "braces"), "board": ("Cladding board", "cladding boards"),
    "sheet": ("Sheet", "sheets"),
    "post": ("Post", "posts"), "beam": ("Beam ply", "beam plies"), "deckboard": ("Deck board", "deck boards"),
}

# What a recorded joint joins, for the fastener table. Every type in timberlib.JOINT_TYPES has one.
JOINT_NAMES = {
    "stud-plate": "stud to plate", "plate-plate": "plate to plate at a wall corner",
    "joist-rim": "floor joist to rim joist or blocking", "rafter-plate": "rafter to wall plate",
    "header-trimmer": "header or sill to king or jack stud", "sheet-frame": "sheet to frame",
    "board-frame": "cladding board to frame", "king-jack": "king stud to jack stud",
    "jack-header": "jack stud to header", "plate-lap": "plate lapped over plate",
    "corner-stud": "corner stud to wall stud", "blocking-rafter": "blocking or outrigger to rafter",
    "fascia-rafter": "fascia to rafter", "barge-rafter": "bargeboard to rafter",
    "rafter-ridge": "rafter to ridge board", "tie-rafter": "tie (ceiling joist) to rafter at the heel",
    "tie-plate": "tie (ceiling joist) to wall plate",
    "post-base": "post, beam or rim joist to its post base", "beam-post": "beam ply bolted to a post",
    "beam-cap": "beam ply on a post cap", "beam-ply": "beam plies screwed together",
    "joist-beam": "deck joist to beam", "deck-board": "deck board to joist",
}


def kind_key(kind, mid):
    """The KIND_NAMES key of a member: its kind, except that the flying rafters
    (kind rafter, id roof/flying-rafter-left|right) are told apart by id."""
    return "flying-rafter" if kind == "rafter" and "flying-rafter" in mid else kind


def what_is(kind, mid):
    """What a member is, in plain words."""
    k = kind_key(kind, mid)
    return KIND_NAMES[k][0] if k in KIND_NAMES else k


def count_by_kind(cuts):
    """{name: count} of cuts ({id, kind}), in the order of KIND_NAMES (unknown kinds last)."""
    n = {}
    for c in cuts:
        k = kind_key(c["kind"], c["id"])
        n[k] = n.get(k, 0) + 1
    order = list(KIND_NAMES)
    return {(KIND_NAMES[k][0] if k in KIND_NAMES else k): n[k]
            for k in sorted(n, key=lambda k: (order.index(k) if k in KIND_NAMES else len(order), k))}


def kinds_in_words(by_kind):
    """'12 studs, 4 king studs, 1 rafter' from count_by_kind."""
    plural = {v[0]: v[1] for v in KIND_NAMES.values()}
    single = {v[0]: v[0].lower() for v in KIND_NAMES.values()}
    return ", ".join(f"{n} {single.get(k, k) if n == 1 else plural.get(k, k)}" for k, n in by_kind.items())


# ------------------------------------------------------------------- timber

def pack_fixed(cuts, length, kerf):
    """First-fit decreasing onto bins of one length. `cuts` are (id, mm).
    Returns a list of bins, each a list of cuts, or None if a cut is too long."""
    bins, used = [], []
    for cut in sorted(cuts, key=lambda c: (-c[1], c[0])):
        if cut[1] > length + EPS:
            return None
        for i, b in enumerate(bins):
            if used[i] + kerf + cut[1] <= length + EPS:
                b.append(cut)
                used[i] += kerf + cut[1]
                break
        else:
            bins.append([cut])
            used.append(cut[1])
    return bins


def bin_used(b, kerf):
    return sum(c[1] for c in b) + kerf * (len(b) - 1)


def timber_plans(cuts, lengths, prices, kerf, trim=0):
    """Every candidate plan: one per single stock length that holds the longest
    cut, plus the mix. A plan is a list of (stock_length, [cuts]). `prices`
    maps stock length to gross price or None."""
    longest = max(c[1] for c in cuts)
    usable = [L for L in sorted(lengths) if L - trim >= longest - EPS]   # trim: what squaring the ends costs
    plans = []
    for L in usable:
        plans.append(("single", [(L, b) for b in pack_fixed(cuts, L - trim, kerf)]))
    if len(usable) > 1:
        big = pack_fixed(cuts, usable[-1] - trim, kerf)
        mixed = []
        for b in big:
            need = bin_used(b, kerf)
            fits = [L for L in usable if L - trim >= need - EPS]
            priced = [L for L in fits if prices.get(L) is not None]
            if priced and len(priced) == len(fits):
                L = min(priced, key=lambda x: (prices[x], x))
            else:
                L = fits[0]
            mixed.append((L, b))
        plans.append(("mix", mixed))
    return plans


def plan_key(plan, prices, kerf):
    kind, bins = plan
    stock = sum(L for L, _ in bins)
    cuts = sum(c[1] for _, b in bins for c in b)
    waste = stock - cuts
    full = all(prices.get(L) is not None for L, _ in bins)
    cost = sum(prices[L] for L, _ in bins) if full else None
    primary = (0, cost, waste) if full else (1, waste, 0)
    return (primary[0], primary[1], primary[2], len(bins), 0 if kind == "single" else 1,
            sorted((-L for L, _ in bins)))


def spare_piece(bins):
    return max(L for L, _ in bins)


def build_timber_line(key, members, it, lengths, prices, kerf, waste_pct, currency, trim=0):
    cuts = [(m["id"], m["size"][0]) for m in members]
    by_id = {m["id"]: m for m in members}
    plans = timber_plans(cuts, lengths, prices, kerf, trim)
    plan = min(plans, key=lambda p: plan_key(p, prices, kerf))
    kind, bins = plan
    bins = sorted(bins, key=lambda lb: (-lb[0], -sum(c[1] for c in lb[1]), lb[1][0][0]))
    n = len(bins)
    spare_n = tl.allowance(n, waste_pct)
    spare_len = spare_piece(bins)
    pieces, layouts = {}, []
    for i, (L, b) in enumerate(bins, 1):
        pieces[L] = pieces.get(L, 0) + 1
        used = bin_used(b, kerf)
        layouts.append({
            "piece": f"{key[0]}-{key[1]}#{i}", "stock_mm": L,
            "cuts": [{"id": cid, "length_mm": l, "cut_deg": by_id[cid]["cut_deg"],
                      "group": by_id[cid]["group"], "kind": by_id[cid]["kind"],
                      "what": what_is(by_id[cid]["kind"], cid)} for cid, l in b],
            "offcut_mm": round(L - used, 1)})
    buy = [{"length_mm": L, "qty": q, "spare": 0, "unit_price": prices.get(L)}
           for L, q in sorted(pieces.items(), reverse=True)]
    if spare_n:
        row = next((r for r in buy if r["length_mm"] == spare_len))
        row["spare"] = spare_n
    for r in buy:
        r["total_qty"] = r["qty"] + r["spare"]
        r["line_total"] = None if r["unit_price"] is None else round(r["unit_price"] * r["total_qty"], 2)
    priced = all(r["unit_price"] is not None for r in buy)
    stock = sum(L for L, _ in bins)
    return {
        "item": key[0], "variant": key[1], "name": it.get("name", key[0]), "category": it["category"],
        "cuts": len(cuts), "plan": kind, "pieces": buy, "pieces_to_buy": n + spare_n, "spare_pieces": spare_n,
        "layouts": layouts, "by_kind": count_by_kind([c for lay in layouts for c in lay["cuts"]]),
        "waste_mm": round(stock - sum(c[1] for c in cuts), 1),
        "waste_pct": round(100 * (stock - sum(c[1] for c in cuts)) / stock, 1),
        "currency": currency if priced else None,
        "total": round(sum(r["line_total"] for r in buy), 2) if priced else None,
        "priced": priced,
    }


def stock_for(it, variant, snapshot):
    """(stock lengths, {length: gross price}) for a timber or cladding item. The
    snapshot's lengths when it sells the item in this variant, else the library's
    (unpriced)."""
    if snapshot:
        found = {}
        for L in sorted({r["length_mm"] for r in snapshot if r["kind"] == "lumber"}):
            hit = tl.price_for(snapshot, it, L, variant)
            if hit:
                found[L] = hit["price_gross"]
        if found:
            return sorted(found), found
    return list(it["stock_lengths_mm"]), {}


# ------------------------------------------------------------------- sheets

def pack_sheets(parts, sheet_long, sheet_short, kerf, can_rotate):
    """Shelf packing (first-fit decreasing height). `parts` are (id, w, h): w along
    the sheet's long side unless rotated. Where rotation is allowed two plans are
    tried, parts as drawn (turned only when they don't fit that way) and every part
    turned long side along the sheet; the one with fewer sheets wins, a tie going to
    as drawn. Returns (sheets, problems); each sheet is a list of placements
    {id, x, y, w, h, rotated}."""
    best = shelf_pack(parts, sheet_long, sheet_short, kerf, can_rotate, False)
    if can_rotate:
        alt = shelf_pack(parts, sheet_long, sheet_short, kerf, can_rotate, True)
        if len(alt[0]) < len(best[0]):
            best = alt
    return best


def shelf_pack(parts, sheet_long, sheet_short, kerf, can_rotate, turn_all):
    rects, problems = [], []
    for pid, a, b in parts:
        w, h, rot = a, b, False
        if can_rotate and ((turn_all and b > a) or w > sheet_long + EPS or h > sheet_short + EPS):
            w, h, rot = b, a, True
        if w > sheet_long + EPS or h > sheet_short + EPS:
            problems.append(f"{pid}: {a:g} x {b:g} mm does not fit a {sheet_long:g} x {sheet_short:g} mm sheet"
                            + ("" if can_rotate else " (this sheet can't be rotated)"))
            continue
        rects.append((pid, w, h, rot))
    rects.sort(key=lambda r: (-r[2], -r[1], r[0]))
    sheets = []   # each: {"shelves": [[y, h, used_w]], "next_y": float, "items": []}
    for pid, w, h, rot in rects:
        placed = False
        for s in sheets:
            for sh in s["shelves"]:
                gap = kerf if sh[2] > 0 else 0
                if h <= sh[1] + EPS and sh[2] + gap + w <= sheet_long + EPS:
                    s["items"].append({"id": pid, "x": sh[2] + gap, "y": sh[0], "w": w, "h": h, "rotated": rot})
                    sh[2] += gap + w
                    placed = True
                    break
            if placed:
                break
            gap = kerf if s["shelves"] else 0
            if s["next_y"] + gap + h <= sheet_short + EPS:
                y = s["next_y"] + gap
                s["shelves"].append([y, h, w])
                s["items"].append({"id": pid, "x": 0, "y": y, "w": w, "h": h, "rotated": rot})
                s["next_y"] = y + h
                placed = True
                break
        if not placed:
            sheets.append({"shelves": [[0, h, w]], "next_y": h,
                           "items": [{"id": pid, "x": 0, "y": 0, "w": w, "h": h, "rotated": rot}]})
    return [s["items"] for s in sheets], problems


def build_sheet_line(item_key, members, it, snapshot, kerf, waste_pct):
    long_, short_ = max(it["size_mm"]), min(it["size_mm"])
    can_rot = bool(it.get("can_rotate", it.get("material", "") in ("osb3", "osb", "plywood")))
    parts = [(m["id"], m["size"][0], m["size"][1]) for m in members]
    sheets, problems = pack_sheets(parts, long_, short_, kerf, can_rot)
    n = len(sheets)
    spare_n = tl.allowance(n, waste_pct) if n else 0
    hit = tl.price_for(snapshot, it) if snapshot else None
    unit = hit["price_gross"] if hit else None
    out_sheets = []
    for i, items in enumerate(sheets, 1):
        area = sum(p["w"] * p["h"] for p in items)
        out_sheets.append({"sheet": i, "parts": items,
                           "used_pct": round(100 * area / (long_ * short_), 1)})
    return {
        "item": item_key, "name": it.get("name", item_key), "sheet_size_mm": [long_, short_],
        "thickness_mm": it["thickness_mm"], "can_rotate": can_rot, "parts": len(parts),
        "sheets_packed": n, "spare_sheets": spare_n, "sheets_to_buy": n + spare_n,
        "layouts": out_sheets, "unit_price": unit,
        "currency": hit["currency"] if hit else None,
        "total": round(unit * (n + spare_n), 2) if hit else None, "priced": bool(hit),
    }, problems


# --------------------------------------------------------------- fasteners

def pack_count(need, pack_sizes):
    """Smallest total >= need made of whole packs (fewest packs among ties).
    Returns {pack_size: count}."""
    top = need + max(pack_sizes)
    best = {0: {}}
    # dp over totals: fewest packs for each reachable total
    dp = [None] * (top + 1)
    dp[0] = (0, {})
    for s in range(top + 1):
        if dp[s] is None:
            continue
        for p in sorted(pack_sizes):
            t = s + p
            if t <= top:
                cand = (dp[s][0] + 1, dict(dp[s][1]))
                cand[1][p] = cand[1].get(p, 0) + 1
                if dp[t] is None or cand[0] < dp[t][0]:
                    dp[t] = cand
    for t in range(need, top + 1):
        if dp[t] is not None:
            return t, dp[t][1]
    raise ValueError("no pack combination")


def rule_count(r, j):
    """How many of a rule's fastener one recorded joint takes."""
    if "per_joint" in r:
        return r["per_joint"]
    if "per_crossing" in r:
        return r["per_crossing"] * j.get("crossings", 0)
    return math.ceil(j.get("edge_mm", 0) / r["every_mm"] - 1e-9)


def nail_weight_packs(count, it):
    """(weight needed, {box_size: qty}, weight bought) for `count` nails of a library nail,
    in its own weight unit (kg or lb). Weights are worked in thousandths so the
    box sizes (1, 2.5, 5) combine exactly."""
    unit = it["weight_unit"]
    need = count / it[f"pcs_per_{unit}"]
    sizes = [round(x * 1000) for x in it[f"box_{unit}"]]
    total, packs = pack_count(math.ceil(need * 1000 - 1e-9), sizes)
    return need, {s / 1000: q for s, q in packs.items()}, total / 1000


def count_fasteners(joints, lib, waste_pct):
    """Fastener lines from the recorded joints and the library's joint_rules. A rule may
    name a second fastener under `also` (rafter to plate: toe nails and a structural screw).
    Nails come out by weight (kg or lb, rounded up to boxes), screws in packs."""
    rules = {t: r for t, r in lib["joint_rules"].items() if not t.startswith("_")}
    need, by_type, problems = {}, {}, []
    for j in joints:
        r = rules.get(j["type"])
        if r is None:
            problems.append(f"joint type {j['type']!r} has no rule in the library")
            continue
        for part in [r] + list(r.get("also", [])):
            n = rule_count(part, j)
            need[part["fastener"]] = need.get(part["fastener"], 0) + n
            d = by_type.setdefault(part["fastener"], {})
            d[j["type"]] = d.get(j["type"], 0) + n
    lines = []
    for key in sorted(need):
        it = tl.item(lib, key)
        spare = tl.allowance(need[key], waste_pct)
        line = {"item": key, "name": it["name"], "kind": "nail" if it.get("type") == "nail" else "screw",
                "counted": need[key], "spare": spare,
                "by_joint_type": dict(sorted(by_type[key].items())),
                "unit_price": None, "total": None, "priced": False}
        if line["kind"] == "nail":
            w, packs, bought = nail_weight_packs(need[key] + spare, it)
            unit = it["weight_unit"]
            line.update({"weight_unit": unit, "weight": round(w, 2), "buy_weight": bought,
                         "to_buy": int(bought * it[f"pcs_per_{unit}"]),
                         "packs": [{"size": s, "qty": q} for s, q in sorted(packs.items())]})
        else:
            total, packs = pack_count(need[key] + spare, it["pack_sizes"])
            line.update({"to_buy": total, "packs": [{"size": s, "qty": q} for s, q in sorted(packs.items())]})
        lines.append(line)
    # nails first, in the order of the library; screws after
    order = list(lib["fasteners"])
    lines.sort(key=lambda l: (l["kind"] != "nail", order.index(l["item"])))
    return lines, problems


# ------------------------------------------------------------------ the list

def make_bom(frame, snapshot=None, waste_pct=None, kerf=None, sheet_spare_pct=0, trim=0):
    """sheet_spare_pct: spare for sheets, 0 by default (a sheet has no knots or
    splits to allow for). trim: millimetres lost from every stock length to
    squaring its ends, so a cut list never needs the full nominal length."""
    lib = tl.load(frame["region"])
    df = lib.get("defaults", {})
    waste_pct = df.get("spare_percent", 10) if waste_pct is None else waste_pct
    kerf = df.get("kerf_mm", 4) if kerf is None else kerf
    problems = []
    currency = snapshot[0]["currency"] if snapshot else None

    groups, sheet_groups = {}, {}
    for m in frame["members"]:
        if m.get("layer") == "foundations":
            continue                    # footings and post bases are bought items, counted in frame["bought"]
        try:
            it = tl.item(lib, m["item"])
        except KeyError as e:
            problems.append(str(e.args[0]))
            continue
        if it["category"] == "sheets":
            sheet_groups.setdefault(m["item"], []).append(m)
        elif it["category"] in ("sections", "cladding"):
            groups.setdefault((m["item"], m["variant"]), []).append(m)
        else:
            problems.append(f"{m['id']}: item {m['item']!r} is a {it['category']} item, not timber or a sheet")

    timber = []
    for key in sorted(groups):
        it = tl.item(lib, key[0])
        lengths, prices = stock_for(it, key[1], snapshot)
        longest = max(m["size"][0] for m in groups[key])
        if longest > max(lengths) + EPS:
            for m in groups[key]:
                if m["size"][0] > max(lengths) + EPS:
                    problems.append(f"{m['id']}: {m['size'][0]:g} mm is longer than the longest stock length "
                                    f"({max(lengths):g} mm) of {key[0]} {key[1]}")
            groups[key] = [m for m in groups[key] if m["size"][0] <= max(lengths) + EPS]
            if not groups[key]:
                continue
        line = build_timber_line(key, groups[key], it, lengths, prices, kerf, waste_pct, currency, trim)
        line["kind"] = "cladding" if it["category"] == "cladding" else "timber"
        timber.append(line)

    sheets = []
    for key in sorted(sheet_groups):
        line, probs = build_sheet_line(key, sheet_groups[key], tl.item(lib, key), snapshot, kerf, sheet_spare_pct)
        problems += probs
        sheets.append(line)

    fasteners, probs = count_fasteners(frame.get("joints", []), lib, waste_pct)
    problems += probs

    bought = []
    for b in frame.get("bought", []):
        try:
            name = tl.item(lib, b["item"])["name"]
        except KeyError:
            name = b["item"]
        bought.append({"item": b["item"], "name": name, "qty": b["qty"], "unit": b["unit"],
                       "note": b.get("note", ""), "unit_price": None, "total": None, "priced": False})

    lines = timber + sheets + fasteners + bought
    priced = [l for l in lines if l["priced"]]
    unpriced = [l["item"] + (f" ({l['variant']})" if l.get("variant") else "") for l in lines if not l["priced"]]
    totals = {"currency": currency, "amount": round(sum(l["total"] for l in priced), 2) if snapshot else None,
              "priced_lines": len(priced), "lines": len(lines), "partial": bool(unpriced),
              "unpriced": unpriced}
    snap = None
    if snapshot:
        snap = {"supplier": snapshot[0]["supplier"], "read_date": snapshot[0]["read_date"], "currency": currency}
    return {
        "schema": SCHEMA, "name": frame.get("name", ""), "region": frame["region"], "units": frame["units"],
        "waste_pct": waste_pct, "sheet_spare_pct": sheet_spare_pct, "trim_mm": trim, "kerf_mm": kerf, "snapshot": snap,
        "timber": timber, "sheets": sheets, "fasteners": fasteners, "bought": bought,
        "totals": totals, "problems": problems,
        "notes": [
            "Nails and screws are counted from the recorded joints only: bottom plates to the floor "
            "and the fixings of bought items are not counted. Nail counts to weight are computed or from "
            "distributor lists and vary 5-10% with coating and maker.",
            "Spare pieces are of the longest stock length bought (timber), or whole sheets or packs.",
            "Sheet parts are laid out by their bounding rectangle; parts with a cut-out outline use "
            "more sheet than they need.",
        ],
    }


# -------------------------------------------------------------------- output

def money(x, cur):
    return tl.money(x, cur)


def render_md(bom):
    u = bom["units"]
    L = lambda mm: tl.fmt_length(mm, u)
    cur = (bom["snapshot"] or {}).get("currency")
    out = [f"# Shopping list: {bom['name']}", ""]
    out += [SAFETY_NOTE, ""]
    out.append(f"Region {bom['region']}, lengths in {u} units. Spare allowance {bom['waste_pct']:g}% of the timber "
               f"and fastener counts (rounded up)"
               + (f", {bom['sheet_spare_pct']:g}% of the sheets" if bom.get("sheet_spare_pct") else ", none on sheets")
               + f"; saw kerf {L(bom['kerf_mm'])}"
               + (f"; {L(bom['trim_mm'])} of every length kept for squaring its ends." if bom.get("trim_mm") else "."))
    if bom["snapshot"]:
        s = bom["snapshot"]
        out.append(f"Prices: {s['supplier']}, read {s['read_date']} (gross, {cur}).")
    else:
        out.append("No price snapshot given: no prices.")
    out.append("")
    t = bom["totals"]
    if bom["snapshot"]:
        out.append(f"**Total {money(t['amount'], cur)}** for {t['priced_lines']} of {t['lines']} lines"
                   + (" (partial: no price for " + ", ".join(t["unpriced"]) + ")" if t["partial"] else "") + ".")
        out.append("")
    if bom["problems"]:
        out += ["## Problems", ""] + [f"- {p}" for p in bom["problems"]] + [""]

    def price_cells(unit, total):
        if total is None:
            return "no price", "no price"
        return money(unit, cur), money(total, cur)

    out += ["## Timber and cladding", ""]
    out += ["| Item | Variant | Buy | Price each | Line total |", "|---|---|---|---|---|"]
    for ln in bom["timber"]:
        for i, r in enumerate(ln["pieces"]):
            qty = f"{r['total_qty']} × {L(r['length_mm'])}" + (f" (incl. {r['spare']} spare)" if r["spare"] else "")
            each, tot = price_cells(r["unit_price"], r["line_total"])
            out.append(f"| {ln['name'] if i == 0 else ''} | {ln['variant'] if i == 0 else ''} | {qty} | {each} | {tot} |")
    out.append("")
    for ln in bom["timber"]:
        out += [f"### {ln['name']}, {ln['variant']}: {ln['cuts']} cuts on "
                f"{len(ln['layouts'])} pieces ({ln['plan']}, {ln['waste_pct']:g}% waste)", ""]
        out += ["| Piece | Length | Cuts | Offcut |", "|---|---|---|---|"]
        for p in ln["layouts"]:
            cuts = ", ".join(f"{c['id']} ({L(c['length_mm'])})" for c in p["cuts"])
            out.append(f"| {p['piece']} | {L(p['stock_mm'])} | {cuts} | {L(p['offcut_mm'])} |")
        out += ["", f"Cuts: {kinds_in_words(ln['by_kind'])}.", ""]

    out += ["## Sheets", ""]
    out += ["| Item | Sheet | Buy | Price each | Line total |", "|---|---|---|---|---|"]
    for ln in bom["sheets"]:
        a, b = ln["sheet_size_mm"]
        qty = f"{ln['sheets_to_buy']}" + (f" (incl. {ln['spare_sheets']} spare)" if ln["spare_sheets"] else "")
        each, tot = price_cells(ln["unit_price"], ln["total"])
        out.append(f"| {ln['name']} | {L(a)} × {L(b)} | {qty} | {each} | {tot} |")
    out.append("")
    for ln in bom["sheets"]:
        out += [f"### {ln['name']}: {ln['parts']} parts on {ln['sheets_packed']} sheets"
                + ("" if ln["can_rotate"] else " (no rotation)"), ""]
        out += ["| Sheet | Parts (position from the sheet corner, size) | Used |", "|---|---|---|"]
        for s in ln["layouts"]:
            parts = ", ".join(f"{p['id']} at {L(p['x'])}, {L(p['y'])}, {L(p['w'])} × {L(p['h'])}"
                              + (" turned" if p["rotated"] else "") for p in s["parts"])
            out.append(f"| {s['sheet']} | {parts} | {s['used_pct']:g}% |")
        out.append("")

    def fastener_rows(lines, nails):
        for f in lines:
            used = ", ".join(f"{JOINT_NAMES.get(t, t)} {n:,}" for t, n in
                             sorted(f["by_joint_type"].items(), key=lambda tn: (-tn[1], tn[0])))
            if nails:
                u = f["weight_unit"]
                packs = " + ".join(f"{p['qty']} × {p['size']:g} {u}" for p in f["packs"])
                out.append(f"| {f['name']} | {f['counted']:,} | {f['spare']:,} | about {f['weight']:g} {u} | "
                           f"{packs} ({f['to_buy']:,} nails) | {used} | no price |")
            else:
                packs = ", ".join(f"{p['qty']} × {p['size']}" for p in f["packs"])
                out.append(f"| {f['name']} | {f['counted']} | {f['spare']} | {f['to_buy']} | {packs} | {used} | no price |")

    nails = [f for f in bom["fasteners"] if f["kind"] == "nail"]
    screws = [f for f in bom["fasteners"] if f["kind"] != "nail"]
    out += ["## Nails", "",
            "Nails are bought by weight: the count (with the spare) is turned into kg or lb and rounded up to the box sizes.", ""]
    out += ["| Nail | Counted | Spare | Weight | Buy | Counted for | Price |", "|---|---|---|---|---|---|---|"]
    fastener_rows(nails, True)
    out.append("")
    out += ["## Structural screws", "",
            "Only where a screw is stronger than a nail: the rafters to the wall plates (uplift) and the wall panels to each other at the corners.", ""]
    out += ["| Item | Counted | Spare | Buy | Packs | Counted for | Price |", "|---|---|---|---|---|---|---|"]
    fastener_rows(screws, False)
    out.append("")
    out += ["## Bought items", ""]
    out += ["| Item | Quantity | Note | Price |", "|---|---|---|---|"]
    for b in bom["bought"]:
        out.append(f"| {b['name']} | {b['qty']:g} {b['unit']} | {b['note']} | no price |")
    out.append("")
    out += ["## Notes", ""] + [f"- {n}" for n in bom["notes"]] + [""]
    return "\n".join(out)


CUT_FIELDS = ["type", "item", "variant", "piece", "stock_mm", "member", "group", "kind", "what", "length_mm",
              "width_mm", "x_mm", "y_mm", "cut_deg_a", "cut_deg_b", "rotated"]


def write_cutlist(bom, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, CUT_FIELDS)
        w.writeheader()
        for ln in bom["timber"]:
            for p in ln["layouts"]:
                for c in p["cuts"]:
                    w.writerow({"type": ln["kind"], "item": ln["item"], "variant": ln["variant"],
                                "piece": p["piece"], "stock_mm": p["stock_mm"], "member": c["id"],
                                "group": c["group"], "kind": c["kind"], "what": c["what"], "length_mm": c["length_mm"],
                                "cut_deg_a": c["cut_deg"][0], "cut_deg_b": c["cut_deg"][1]})
        for ln in bom["sheets"]:
            for s in ln["layouts"]:
                for p in s["parts"]:
                    w.writerow({"type": "sheet", "item": ln["item"], "variant": "", "piece": f"{ln['item']}#{s['sheet']}",
                                "stock_mm": "", "member": p["id"], "what": KIND_NAMES["sheet"][0], "length_mm": p["w"], "width_mm": p["h"],
                                "x_mm": p["x"], "y_mm": p["y"], "rotated": int(p["rotated"])})


def nail_summary(bom):
    w = {}
    for f in bom["fasteners"]:
        if f["kind"] == "nail":
            w[f["weight_unit"]] = w.get(f["weight_unit"], 0) + f["buy_weight"]
    return ", ".join(f"{v:g} {u} of nails" for u, v in w.items()) or "no nails"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("frame", help="frame.json from tools/frame.py")
    ap.add_argument("--snapshot", help="price snapshot CSV (data/timber/prices/); without it there are no prices")
    ap.add_argument("--waste", type=float, default=None,
                    help="spare, in %% of every piece count, rounded up (default: the library's, 10)")
    ap.add_argument("--kerf", type=float, default=None, help="saw blade width in mm (default: the library's, 4)")
    ap.add_argument("--sheet-spare", type=float, default=0, help="spare sheets, in %% of the sheet count (default 0)")
    ap.add_argument("--trim", type=float, default=20,
                    help="mm of every stock length kept for squaring its ends (default 20)")
    ap.add_argument("--out", required=True, help="output folder")
    a = ap.parse_args()
    with open(a.frame, encoding="utf-8") as f:
        frame = json.load(f)
    snap = tl.load_snapshot(a.snapshot) if a.snapshot else None
    bom = make_bom(frame, snap, a.waste, a.kerf, a.sheet_spare, a.trim)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "bom.json"), "w", encoding="utf-8") as f:
        json.dump(bom, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(a.out, "bom.md"), "w", encoding="utf-8") as f:
        f.write(render_md(bom))
    write_cutlist(bom, os.path.join(a.out, "cutlist.csv"))
    t = bom["totals"]
    print(f"bom: {sum(l['pieces_to_buy'] for l in bom['timber'])} timber pieces, "
          f"{sum(l['sheets_to_buy'] for l in bom['sheets'])} sheets, "
          f"{sum(l['to_buy'] for l in bom['fasteners'])} fasteners ({nail_summary(bom)}) -> {a.out}")
    if bom["snapshot"]:
        print(f"total {tl.money(t['amount'], t['currency'])}" + (" (partial)" if t["partial"] else ""))
    for p in bom["problems"]:
        print("problem:", p, file=sys.stderr)
    sys.exit(1 if bom["problems"] else 0)


if __name__ == "__main__":
    main()
