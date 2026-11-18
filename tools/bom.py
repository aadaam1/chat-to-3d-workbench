#!/usr/bin/env python3
"""Shopping list and cut list for a timber structure.

    bom.py <frame.json> [--snapshot <csv> | --prices <region>[:<supplier>]] [--waste 10] [--kerf 4] [--sheet-spare 0] [--trim 20] --out <dir>

Reads the frame file written by tools/frame.py and writes, into <dir>:
  bom.json     everything below, for other tools
  bom.md       what to hand a timber yard (lengths in the frame's units)
  cutlist.csv  one row per cut and per sheet part, in millimetres; the `what`
               column says in plain words what each piece is (Stud, King stud, ...)

What it works out:
  * Timber and cladding boards: the cuts of each item and variant are packed
    onto the stock lengths on offer (the supplier's lengths when it
    sells that item, else the library's) with the saw kerf between cuts and
    `--trim` kept at each piece's ends. Plans tried: every single stock
    length (first-fit decreasing), a mix (pack on the longest, then give each
    piece the cheapest length that holds its cuts), and "fitted" plans that
    choose each piece's length together with its cuts: take the longest cut
    left, fill every length that holds it as fully as possible from the cuts
    left (a subset search), keep the piece with the lowest price per mm used.
    That is how offcuts get reused: a short cut goes on the end of a long
    piece. The cheapest plan wins when every length has a price, else the one
    with the least waste; ties go to fewer pieces, then a simpler plan.
  * Offcuts: the total left over (mm and % of the timber bought, before the
    spare) is in bom.json ("offcuts") and bom.md. A line with more than 12%
    offcut whose cuts are a few mm over a stock length gets a "ways to waste
    less" hint (bom.json "ways_to_waste_less"): the same list packed again with
    the shorter cut. Advice only; nothing in the design changes.
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
  * Prices (gross; US: shelf price before sales tax) from the snapshots: `--prices hu` uses the
    newest snapshot of every supplier in the region, `--snapshot` one file. Each line is priced
    by the supplier that sells all of it cheapest (a timber line is packed on that supplier's own
    stock lengths); a supplier that can't price the whole line is skipped for it, and the line
    records its supplier. Nails are bought in the supplier's boxes (the cheapest combination
    covering the weight), screws and bolts in its packs, felt by the roll or m2, trims by the
    metre or the piece. A line no supplier prices says "no price" and the total is marked partial.

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
    "brace": ("Brace", "braces"), "board": ("Cladding board", "cladding boards"), "batten": ("Batten", "battens"),
    "sheet": ("Sheet", "sheets"),
    "post": ("Post", "posts"), "beam": ("Beam ply", "beam plies"), "deckboard": ("Deck board", "deck boards"), "slat": ("Slat", "slats"),
}

# What a recorded joint joins, for the fastener table. Every type in timberlib.JOINT_TYPES has one.
JOINT_NAMES = {
    "stud-plate": "stud to plate", "plate-plate": "plate to plate at a wall corner",
    "joist-rim": "floor joist to rim joist or blocking", "rafter-plate": "rafter to wall plate",
    "header-trimmer": "header or sill to king or jack stud", "sheet-frame": "sheet to frame",
    "board-frame": "cladding board to frame", "board-batten": "cladding board to batten",
    "batten-frame": "batten to stud, through the sheathing", "king-jack": "king stud to jack stud",
    "jack-header": "jack stud to header", "plate-lap": "plate lapped over plate",
    "corner-stud": "corner stud to wall stud", "blocking-rafter": "blocking or outrigger to rafter",
    "fascia-rafter": "fascia to rafter", "barge-rafter": "bargeboard to rafter",
    "rafter-ridge": "rafter to ridge board", "tie-rafter": "tie (ceiling joist) to rafter at the heel",
    "tie-plate": "tie (ceiling joist) to wall plate",
    "post-base": "post, beam or rim joist to its post base", "beam-post": "beam ply bolted to a post",
    "beam-cap": "beam ply on a post cap", "beam-ply": "beam plies screwed together",
    "joist-beam": "deck joist to beam", "deck-board": "deck board to joist",
    "brace-post": "knee brace to post", "brace-beam": "knee brace to beam", "brace-rafter": "cross knee brace to the rafter over a post",
    "rafter-beam": "pergola rafter on a beam", "slat-rafter": "slat to rafter",
    "joist-hanger": "deck joist hung between two beams", "butt": "two pieces butted end to end over a support",
}


PRICE_NOTE = ("Prices are gross (US: the shelf price, before sales tax). Each line is priced by the supplier that "
              "sells all of it cheapest: every stock length of a timber line is packed and priced from that supplier's "
              "own lengths, nails and screws are bought in that supplier's boxes and packs. A line no supplier "
              "sells in full has no price and is left out of the total.")


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


def _units(mm):
    """Tenths of a millimetre, rounded up: the knapsack works in whole units and
    never believes a set of cuts fits when it does not."""
    return int(math.ceil(mm * 10 - 1e-6))


def best_fills(rem, rooms, kerf):
    """For each room (mm left on a piece beside a cut already on it): the set of
    the remaining cuts that fills it as fully as possible, a kerf with each cut.
    `rem` is {length: count}; returns one {length: count} per room, in order.
    A bounded subset-sum over the distinct lengths, on a bitset."""
    items = []
    for ln in sorted(rem, reverse=True):
        n, k = rem[ln], 1
        while n > 0:
            take = min(k, n)
            items.append((ln, take, _units(ln + kerf) * take))
            n -= take
            k *= 2
    tops = [max(0, int(r * 10 + 1e-6)) for r in rooms]
    top = max(tops, default=0)
    full = (1 << (top + 1)) - 1
    mask, before = 1, []
    for _, _, w in items:
        before.append(mask)
        mask |= (mask << w) & full
    out = []
    for t in tops:
        s = (mask & ((1 << (t + 1)) - 1)).bit_length() - 1
        used = {}
        for i in range(len(items) - 1, -1, -1):
            if s and not (before[i] >> s) & 1:
                ln, take, w = items[i]
                used[ln] = used.get(ln, 0) + take
                s -= w
        out.append(used)
    return out


def pack_fitted(cuts, usable, prices, kerf, trim, by_price=True):
    """Choose each piece's stock length together with its cuts. Repeatedly take
    the longest cut left; for every stock length that holds it, fill that length
    as fully as possible from the cuts left (best_fills); keep the piece with the
    lowest price per millimetre used (the least offcut when a length has no price,
    or when by_price is off). Every piece then shrinks to the cheapest length
    that still holds its cuts. Returns [(stock_length, [cuts])]."""
    queues = {}
    for c in sorted(cuts, key=lambda c: (c[1], c[0])):
        queues.setdefault(c[1], []).append(c)
    rem = {ln: len(q) for ln, q in queues.items()}
    priced = by_price and all(prices.get(L) is not None for L in usable)
    bins = []
    while rem:
        first = max(rem)
        rem[first] -= 1
        if not rem[first]:
            del rem[first]
        opts = [L for L in usable if L - trim >= first - EPS]
        fills = best_fills(rem, [L - trim - first for L in opts], kerf)
        best = None
        for L, fill in zip(opts, fills):
            used = first + sum(ln * n + kerf * n for ln, n in fill.items())
            off = L - trim - used
            key = ((prices[L] / used, off, L) if priced else (off, L))
            if best is None or key < best[0]:
                best = (key, L, fill)
        _, L, fill = best
        b = [queues[first].pop()]
        for ln in sorted(fill, reverse=True):
            for _ in range(fill[ln]):
                b.append(queues[ln].pop())
            rem[ln] -= fill[ln]
            if not rem[ln]:
                del rem[ln]
        b.sort(key=lambda c: (-c[1], c[0]))
        bins.append((L, b))
    out = []
    for L, b in bins:
        need = bin_used(b, kerf)
        fits = [x for x in usable if x - trim >= need - EPS]
        pr = [x for x in fits if prices.get(x) is not None]
        out.append((min(pr, key=lambda x: (prices[x], x)) if pr and len(pr) == len(fits) else fits[0], b))
    return out


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
    # a stock length chosen with the cuts that go on it: short cuts fill the end of a long piece
    plans.append(("fitted", pack_fitted(cuts, usable, prices, kerf, trim)))
    if all(prices.get(L) is not None for L in usable):
        plans.append(("fitted", pack_fitted(cuts, usable, prices, kerf, trim, by_price=False)))
    if len(usable) > 1:
        for L in usable:
            plans.append(("fitted", pack_fitted(cuts, [L], prices, kerf, trim)))
    return plans


def plan_key(plan, prices, kerf):
    """Sort key of a plan, the smallest wins: priced plans by what they cost, else by waste; then fewer
    pieces, then less waste, a simpler plan, the same lengths in the same order."""
    kind, bins = plan
    stock = sum(L for L, _ in bins)
    cuts = sum(c[1] for _, b in bins for c in b)
    waste = round(stock - cuts, 3)             # sums of fractional lengths: equal plans must compare equal
    full = all(prices.get(L) is not None for L, _ in bins)
    cost = sum(prices[L] for L, _ in bins) if full else None
    primary = (0, cost, waste) if full else (1, waste, 0)
    return (primary[0], primary[1], primary[2], len(bins), {"single": 0, "mix": 1}.get(kind, 2),
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


HINT_WASTE_PCT = 12.0      # a line with more offcut than this (% of its stock) is looked at for a way to waste less
JUST_OVER_MM = 50.0        # a cut this close to a stock length (or less) that needs the next one up is worth a hint


def offcut_summary(lines):
    """Everything left over on the timber and cladding lines, before the spare pieces:
    {"mm", "bought_mm", "pct"}."""
    bought = sum(l["stock_mm"] for ln in lines for l in ln["layouts"])
    off = sum(ln["waste_mm"] for ln in lines)
    return {"mm": round(off, 1), "bought_mm": round(bought, 1), "pct": round(100 * off / bought, 1) if bought else 0.0}


def ways_to_waste_less(line, members, it, lengths, prices, kerf, waste_pct, currency, trim, units, limit=3):
    """For a line with a lot of offcut: the cuts that are just over a stock length (by
    `trim` or a few millimetres) and so need the next length up, each re-packed shorter to
    say what it would save. Advice only: nothing in the design changes. Sorted by saving."""
    if line["waste_pct"] <= HINT_WASTE_PCT:
        return []
    fmt = lambda mm: tl.fmt_length(mm, units)
    fmt_total = (lambda mm: f"{mm / 1000:.1f} m".replace(".0 m", " m")) if units == "metric" else fmt
    hints = []
    for c in sorted({m["size"][0] for m in members}):
        near = [L for L in sorted(lengths) if 0 < c - (L - trim) <= JUST_OVER_MM + EPS]
        if not near:
            continue
        L = near[0]
        short = L - trim
        d = c - short
        trial = [dict(m, size=[short] + list(m["size"][1:])) if m["size"][0] == c else m for m in members]
        alt = build_timber_line((line["item"], line["variant"]), trial, it, lengths, prices, kerf, waste_pct, currency, trim)
        stock_was = sum(l["stock_mm"] for l in line["layouts"])
        stock_now = sum(l["stock_mm"] for l in alt["layouts"])
        saved_pieces = line["pieces_to_buy"] - alt["pieces_to_buy"]
        saved = round(line["total"] - alt["total"], 2) if line["priced"] and alt["priced"] else None
        if stock_now >= stock_was - EPS or (saved is not None and saved <= 0):
            continue
        mine = [m for m in members if m["size"][0] == c]
        kinds = sorted({kind_key(m["kind"], m["id"]) for m in mine})
        what = " and ".join(KIND_NAMES[k][1] if k in KIND_NAMES else k for k in kinds)
        old_len = sorted({l["stock_mm"] for l in line["layouts"] if any(x["length_mm"] == c for x in l["cuts"])})
        new_len = sorted({l["stock_mm"] for l in alt["layouts"] if any(x["length_mm"] == short for x in l["cuts"])})
        text = (f"{what[0].upper() + what[1:]} ({line['name']}, {line['variant']}): the {fmt(c)} cuts need "
                f"{' or '.join(fmt(x) for x in old_len)} pieces because {fmt(trim)} of every piece is kept to square the ends. "
                f"Made {fmt(d)} shorter ({fmt(short)}) they would come from {' or '.join(fmt(x) for x in new_len)} pieces, "
                f"so {fmt_total(stock_was - stock_now)} less timber to buy"
                + (f" (about {money(saved, currency)})" if saved else "") + ".")
        hints.append({"item": line["item"], "variant": line["variant"], "cut_mm": c, "shorten_mm": round(d, 1),
                      "stock_mm_now": old_len, "stock_mm_then": new_len, "saves_pieces": saved_pieces,
                      "saves_stock_mm": round(stock_was - stock_now, 1), "saves_amount": saved,
                      "currency": currency if saved is not None else None, "text": text})
    hints.sort(key=lambda h: (-(h["saves_amount"] or 0), -h["saves_stock_mm"], h["cut_mm"]))
    return hints[:limit]


def with_order_lengths(it, lengths, longest, units):
    """(lengths, note): when the longest cut is longer than any stocked length but a special-order
    length holds it, the order lengths are added, with a note that they are not normally stocked."""
    order = [x for x in it.get("order_lengths_mm", []) if x not in lengths]
    if longest > max(lengths) + EPS and longest <= max(order, default=0) + EPS:
        lengths = sorted(set(lengths) | set(order))
        return lengths, (f"{it['name']}: {', '.join(tl.fmt_length(x, units) for x in order)} lengths are not "
                         "normally stocked; ask the yard whether it can supply them, or join the boards over a stud")
    return lengths, None


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


def build_sheet_line(item_key, members, it, sups, kerf, waste_pct):
    """`sups`: the suppliers (see suppliers_of); the one selling the sheet cheapest prices the line."""
    long_, short_ = max(it["size_mm"]), min(it["size_mm"])
    can_rot = bool(it.get("can_rotate", it.get("material", "") in ("osb3", "osb", "plywood")))
    parts = [(m["id"], m["size"][0], m["size"][1]) for m in members]
    sheets, problems = pack_sheets(parts, long_, short_, kerf, can_rot)
    n = len(sheets)
    spare_n = tl.allowance(n, waste_pct) if n else 0
    hits = [(h["price_gross"], i, sup["supplier"], h) for i, sup in enumerate(sups)
            for h in [tl.price_for(sup["rows"], it)] if h]
    best = min(hits, key=lambda x: x[:2]) if hits else None
    hit = best[3] if best else None
    unit = hit["price_gross"] if hit else None
    out_sheets = []
    for i, items in enumerate(sheets, 1):
        area = sum(p["w"] * p["h"] for p in items)
        out_sheets.append({"sheet": i, "parts": items,
                           "used_pct": round(100 * area / (long_ * short_), 1)})
    line = {
        "item": item_key, "name": it.get("name", item_key), "sheet_size_mm": [long_, short_],
        "thickness_mm": it["thickness_mm"], "can_rotate": can_rot, "parts": len(parts),
        "sheets_packed": n, "spare_sheets": spare_n, "sheets_to_buy": n + spare_n,
        "layouts": out_sheets, "unit_price": unit,
        "currency": hit["currency"] if hit else None,
        "total": round(unit * (n + spare_n), 2) if hit else None, "priced": bool(hit),
    }
    if sups:
        line["supplier"] = best[2] if best else None
        if best:
            line["product"], line["notes"] = hit["row"]["product"], hit["row"]["notes"]
    return line, problems


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
    return max(r.get("min", 0), math.ceil(j.get("edge_mm", 0) / r["every_mm"] - 1e-9))


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


# ------------------------------------------- prices of fasteners and bought items

LB_PER_KG = 2.2046226


def cheapest_packs(need, options, scale=1000):
    """The cheapest whole packs that add up to at least `need`. `options` are (size, price, tag);
    returns (cost, total size, [(tag, qty)]) or None when there are no options. For each size only
    the cheapest option counts. Worked in integers (sizes in thousandths) so box sizes like 2.5
    combine exactly; ties go to the smaller total, then fewer packs."""
    best = {}
    for size, price, tag in options:
        k = round(size * scale)
        if k > 0 and (k not in best or price < best[k][0]):
            best[k] = (price, tag)
    if not best:
        return None
    sizes = sorted(best)
    g = math.gcd(*sizes) if len(sizes) > 1 else sizes[0]
    units = [k // g for k in sizes]
    cents = [round(best[k][0] * 1000) for k in sizes]
    n = max(1, math.ceil(round(need * scale) / g - 1e-9))
    top = n + max(units) - 1
    INF = float("inf")
    cost, pick = [INF] * (top + 1), [None] * (top + 1)
    cost[0] = 0
    for t in range(1, top + 1):
        for i, u in enumerate(units):
            if u <= t and cost[t - u] + cents[i] < cost[t]:
                cost[t], pick[t] = cost[t - u] + cents[i], i
    cands = [t for t in range(n, top + 1) if cost[t] < INF]
    if not cands:
        return None
    t = min(cands, key=lambda t: (cost[t], t))
    qty, total = {}, t
    while t:
        i = pick[t]
        qty[i] = qty.get(i, 0) + 1
        t -= units[i]
    packs = [(best[sizes[i]][1], q) for i, q in sorted(qty.items())]
    return cost[total] / 1000, total * g / scale, packs


def pack_size(row, ctx, it):
    """How much one price buys, in the line's own unit, or None when the row doesn't fit it.
    ctx: 'weight' (nails: kg or lb of the library item), 'count' (screws, bolts, pieces),
    'm' (trim by the metre or in pieces of pack_qty m), 'm2' (felt by the m2 or the roll)."""
    u, q = row["unit"] or "piece", row["pack_qty"]
    if ctx == "weight":
        wu = it["weight_unit"]
        if u == "box":
            return q
        if u == "kg":
            return 1.0 if wu == "kg" else LB_PER_KG
        if u in ("pack", "piece"):
            return (q or 1) / it[f"pcs_per_{wu}"]
    elif ctx == "count":
        if u in ("pack", "piece"):
            return q or 1
    elif ctx == "m":
        if u == "m":
            return 1.0
        if u in ("piece", "roll") and q:
            return q
    elif ctx == "m2":
        if u == "m2":
            return 1.0
        if u == "roll":
            return q
    return None


def price_need(need, key, it, ctx, sups):
    """The cheapest supplier for `need` (in the unit of `ctx`) of the library item `key`:
    {"supplier", "cost", "bought", "packs": [{size, qty, unit_price, product}]} or None. The rows
    are those of kind fastener or bought whose item is `key`; where one supplier has several
    (sizes, finishes), the cheapest combination of whole packs that covers the need is used."""
    best = None
    for i, sup in enumerate(sups):
        opts = []
        for r in sup["rows"]:
            if r["kind"] in ("fastener", "bought") and r["item"] == key:
                size = pack_size(r, ctx, it)
                if size:
                    opts.append((size, r["price_gross"], r))
        got = cheapest_packs(need, opts)
        if got and (best is None or (round(got[0], 6), i) < (round(best[0][0], 6), best[1])):
            best = (got, i)
    if not best:
        return None
    (cost, bought, packs), i = best
    return {"supplier": sups[i]["supplier"], "currency": sups[i]["currency"], "cost": round(cost, 2),
            "bought": round(bought, 4),
            "packs": [dict({"size": round(pack_size(r, ctx, it), 4), "qty": q, "unit_price": r["price_gross"],
                            "product": r["product"]},
                           **({"count": r["pack_qty"] or 1} if ctx == "weight" and r["unit"] in ("pack", "piece") else {}),
                           **({"notes": r["notes"]} if r["notes"] else {}))
                      for r, q in packs]}


def price_fasteners(lines, lib, sups):
    """Prices the nail and screw lines from the suppliers' rows (by item key). A priced line's
    packs, weight bought and count to buy are the supplier's own pack sizes."""
    for line in lines:
        it = tl.item(lib, line["item"])
        need = line["counted"] + line["spare"]
        if line["kind"] == "nail":
            unit = it["weight_unit"]
            got = price_need(need / it[f"pcs_per_{unit}"], line["item"], it, "weight", sups)
        else:
            got = price_need(need, line["item"], it, "count", sups)
        if not got:
            line["supplier"] = None
            continue
        line.update({"packs": got["packs"], "total": got["cost"], "priced": True, "supplier": got["supplier"],
                     "currency": got["currency"],
                     "unit_price": got["packs"][0]["unit_price"] if len(got["packs"]) == 1 else None})
        if line["kind"] == "nail":
            line.update({"buy_weight": got["bought"], "to_buy": int(got["bought"] * it[f"pcs_per_{unit}"])})
        else:
            line["to_buy"] = int(round(got["bought"]))


UNIT_CTX = {"m2": "m2", "m": "m", "pcs": "count"}


def price_bought(bought, lib, sups):
    """Prices the bought items by item key: felt by the roll or the m2, trim by the metre or in
    pieces, the rest by the piece. Each line is priced from its own rows only: a ground screw
    and its post bracket (`post-base-u`) are two lines, so check the rows' notes (does the screw
    come with a bracket?)."""
    for b in bought:
        b["supplier"] = None
        try:
            it = tl.item(lib, b["item"])
        except KeyError:
            continue
        ctx = UNIT_CTX.get(b["unit"])
        got = price_need(b["qty"], b["item"], it, ctx, sups) if ctx else None
        if got:
            b.update({"packs": got["packs"], "bought_qty": got["bought"], "total": got["cost"], "priced": True,
                      "supplier": got["supplier"], "currency": got["currency"],
                      "unit_price": got["packs"][0]["unit_price"] if len(got["packs"]) == 1 else None})


def nail_packs_text(line):
    """'1 x 5 kg + 2 x 1 kg' for a nail line; a pack sold by the count reads '2 x 2000 nails'."""
    u = line["weight_unit"]
    return " + ".join(f"{p['qty']} x {p['count']:g} nails" if p.get("count") else f"{p['qty']} x {p['size']:g} {u}"
                      for p in line["packs"])


def pack_text(line, unit=""):
    """'2 x 5 kg + 1 x 2.5 kg' for a priced fastener or bought line, or '' when it has no packs."""
    return " + ".join(f"{p['qty']} x {p['size']:g}" + (f" {unit}" if unit else "") for p in line.get("packs") or [])


def suppliers_of(snapshot):
    """The snapshot given to make_bom, as a list of suppliers {supplier, read_date, currency, rows}:
    [] for none, rows of one snapshot, or a list of such rows. One region is one currency."""
    if not snapshot:
        return []
    lists = snapshot if isinstance(snapshot[0], list) else [snapshot]
    sups = [{"supplier": rows[0]["supplier"], "read_date": max(r["read_date"] for r in rows),
             "read_dates": sorted({r["read_date"] for r in rows}),
             "currency": rows[0]["currency"], "rows": rows} for rows in lists if rows]
    cur = sorted({s["currency"] for s in sups})
    if len(cur) > 1:
        raise ValueError(f"the price snapshots use more than one currency ({', '.join(cur)}): "
                         "prices of different currencies are never added together")
    return sups


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
    sups = suppliers_of(snapshot)
    for sp in sups:
        region = sp["rows"][0].get("region")
        if tl.LIBRARY_OF.get(region, frame["region"]) != frame["region"]:
            fits = ", ".join(sorted(k for k, v in tl.LIBRARY_OF.items() if v == frame["region"] and k != v) or [frame["region"]])
            raise ValueError(f"the {region} prices are for {tl.LIBRARY_OF[region]} structures (sizes, units and fasteners of the "
                             f"{tl.LIBRARY_OF[region]} library), but this structure is {frame['region']}: use PRICES={fits.replace(', ', ' or PRICES=')}")
    currency = sups[0]["currency"] if sups else None

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

    timber, special, hints = [], [], []
    for key in sorted(groups):
        it = tl.item(lib, key[0])
        longest = max(m["size"][0] for m in groups[key])
        chosen = None
        for sup in sups:                  # the supplier that prices the whole line cheapest
            lengths, prices = stock_for(it, key[1], sup["rows"])
            if not prices:
                continue
            lengths, spec_note = with_order_lengths(it, lengths, longest, frame["units"])
            if longest + trim > max(lengths) + EPS:
                continue                  # this supplier has no piece long enough for the longest cut
            line = build_timber_line(key, groups[key], it, lengths, prices, kerf, waste_pct, currency, trim)
            if line["priced"] and (chosen is None or line["total"] < chosen[0]["total"] - 1e-9):
                chosen = (line, lengths, prices, spec_note, sup["supplier"])
        if chosen:
            line, lengths, prices, spec_note, supplier = chosen
            if spec_note:
                special.append(spec_note)
        else:                              # nothing prices it all: the first supplier whose lengths hold every cut, else the library's
            lengths, prices = next(((l, p) for l, p in (stock_for(it, key[1], sup["rows"]) for sup in sups)
                                    if p and longest + trim <= max(with_order_lengths(it, l, longest, frame["units"])[0]) + EPS),
                                   stock_for(it, key[1], None))
            lengths, spec_note = with_order_lengths(it, lengths, longest, frame["units"])
            if spec_note:
                special.append(spec_note)
            supplier = None
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
        if sups:
            line["supplier"] = supplier
            if supplier:
                rows = next(sp["rows"] for sp in sups if sp["supplier"] == supplier)
                for r in line["pieces"]:
                    hit = tl.price_for(rows, it, r["length_mm"], key[1])
                    r["product"], r["notes"] = hit["row"]["product"], hit["row"]["notes"]
        timber.append(line)
        hints += ways_to_waste_less(line, groups[key], it, lengths, prices, kerf, waste_pct, currency, trim, frame["units"])

    sheets = []
    for key in sorted(sheet_groups):
        line, probs = build_sheet_line(key, sheet_groups[key], tl.item(lib, key), sups, kerf, sheet_spare_pct)
        problems += probs
        sheets.append(line)

    fasteners, probs = count_fasteners(frame.get("joints", []), lib, waste_pct)
    problems += probs
    if sups:
        price_fasteners(fasteners, lib, sups)

    bought = []
    for b in frame.get("bought", []):
        try:
            name = tl.item(lib, b["item"])["name"]
        except KeyError:
            name = b["item"]
        bought.append({"item": b["item"], "name": name, "qty": b["qty"], "unit": b["unit"],
                       "note": b.get("note", ""), "unit_price": None, "total": None, "priced": False})

    if sups:
        price_bought(bought, lib, sups)

    lines = timber + sheets + fasteners + bought
    priced = [l for l in lines if l["priced"]]
    unpriced = [l["item"] + (f" ({l['variant']})" if l.get("variant") else "") for l in lines if not l["priced"]]
    totals = {"currency": currency, "amount": round(sum(l["total"] for l in priced), 2) if sups else None,
              "priced_lines": len(priced), "lines": len(lines), "partial": bool(unpriced),
              "unpriced": unpriced}
    snap = None
    if sups:
        n_used = {s["supplier"]: sum(1 for l in priced if l.get("supplier") == s["supplier"]) for s in sups}
        used = [s for s in sups if n_used[s["supplier"]]] or sups
        snap = {"supplier": ", ".join(s["supplier"] for s in used), "read_date": max(s["read_date"] for s in used),
                "currency": currency,
                "suppliers": [{"supplier": s["supplier"], "read_date": s["read_date"], "read_dates": s["read_dates"],
                               "lines": n_used[s["supplier"]]}
                              for s in sups]}
    return {
        "schema": SCHEMA, "name": frame.get("name", ""), "region": frame["region"], "units": frame["units"],
        "waste_pct": waste_pct, "sheet_spare_pct": sheet_spare_pct, "trim_mm": trim, "kerf_mm": kerf, "snapshot": snap,
        "timber": timber, "offcuts": offcut_summary(timber), "ways_to_waste_less": hints, "sheets": sheets, "fasteners": fasteners, "bought": bought,
        "totals": totals, "problems": problems,
        "notes": [
            "Nails and screws are counted from the recorded joints only: bottom plates to the floor "
            "and the fixings of bought items are not counted. Nail counts to weight are computed or from "
            "distributor lists and vary 5-10% with coating and maker.",
            "Spare pieces are of the longest stock length bought (timber), or whole sheets or packs.",
            "Each piece's stock length is chosen together with its cuts, so a short cut is taken from the end of a "
            "long piece instead of a new one: that is how offcuts are reused. The offcut total counts what is left "
            "over, before the spare pieces.",
            "Sheet parts are laid out by their bounding rectangle; parts with a cut-out outline use "
            "more sheet than they need.",
        ] + ([PRICE_NOTE] if sups else []) + special,
        **({"decisions": frame["decisions"]} if frame.get("decisions") else {}),
    }


# -------------------------------------------------------------------- output

def money(x, cur):
    return tl.money(x, cur)


def bought_note(b):
    """A bought item's note, with what to buy where a supplier prices it (a roll, 2 m pieces)."""
    if not b.get("packs") or b["unit"] == "pcs":
        return b["note"]
    unit = {"m": " m", "m2": " m2"}.get(b["unit"], "")
    buy = "buy " + " + ".join(f"{p['qty']} x {p['size']:g}{unit}" for p in b["packs"])
    return "; ".join(x for x in (b["note"], buy) if x)


def priced_as(line, piece=None):
    """What a priced line was priced as, for the Supplier column: 'Supplier: product (note); product'.
    `piece` is one buy row of a timber line (each length is its own product). '' when unpriced."""
    who = line.get("supplier")
    if not who:
        return ""
    items = ([piece] if piece else line.get("packs") or [line])
    seen = dict.fromkeys(f"{x['product']}" + (f" ({x['notes']})" if x.get("notes") else "") for x in items if x.get("product"))
    return who + (": " + "; ".join(seen) if seen else "")


def price_basis(snap):
    """'gross, CZK' or, for US dollars, 'shelf prices before sales tax, USD'."""
    cur = snap["currency"]
    return f"shelf prices before sales tax, {cur}" if cur == "USD" else f"gross, {cur}"


def suppliers_text(snap):
    """Every supplier the list was priced from, with its read date: 'A, read 2026-11-10; B, read ...'.
    Where several were looked at, the lines each one prices are counted."""
    sups = [s for s in snap.get("suppliers", []) if s["lines"]] or snap.get("suppliers") or [snap]
    many = len(snap.get("suppliers", [])) > 1
    return "; ".join(f"{s['supplier']}, read {' and '.join(s.get('read_dates') or [s['read_date']])}" + (f", {s['lines']} line{'s' if s['lines'] != 1 else ''}" if many else "") for s in sups)


def multi_supplier(bom):
    return len((bom.get("snapshot") or {}).get("suppliers", [])) > 1


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
        out.append(f"Prices: {suppliers_text(bom['snapshot'])} ({price_basis(bom['snapshot'])}).")
    else:
        out.append("No price snapshot given: no prices.")
    out.append("")
    t = bom["totals"]
    if bom["snapshot"]:
        out.append(f"**Total {money(t['amount'], cur)}** for {t['priced_lines']} of {t['lines']} lines"
                   + (" (partial: no price for " + ", ".join(t["unpriced"]) + ")" if t["partial"] else "") + ".")
        out.append("")
    if bom.get("decisions"):
        out += ["## How it was planned", "",
                "What the description left open, and what the planner chose (a value you set yourself is never changed):", ""]
        out += [f"- **{d['what']}**: {d['chose']}. {d['why'][0].upper() + d['why'][1:]}." for d in bom["decisions"]] + [""]
    if bom["problems"]:
        out += ["## Problems", ""] + [f"- {p}" for p in bom["problems"]] + [""]

    def price_cells(unit, total):
        if total is None:
            return "no price", "no price"
        return money(unit, cur), money(total, cur)

    out += ["## Timber and cladding", ""]
    ms = bool(bom.get("snapshot"))                 # a Supplier column (supplier and product priced as) when priced
    sc = lambda text: (f" {text} |" if ms else "")
    sh = (" Supplier and product |", "---|") if ms else ("", "")
    out += [f"| Item | Variant | Buy | Price each | Line total |{sh[0]}", f"|---|---|---|---|---|{sh[1]}"]
    for ln in bom["timber"]:
        for i, r in enumerate(ln["pieces"]):
            qty = f"{r['total_qty']} × {L(r['length_mm'])}" + (f" (incl. {r['spare']} spare)" if r["spare"] else "")
            each, tot = price_cells(r["unit_price"], r["line_total"])
            out.append(f"| {ln['name'] if i == 0 else ''} | {ln['variant'] if i == 0 else ''} | {qty} | {each} | {tot} |"
                       + sc(priced_as(ln, r)))
    out.append("")
    oc = bom["offcuts"]
    out += [f"Offcuts: {oc['mm'] / 1000:.1f} m of {oc['bought_mm'] / 1000:.0f} m bought ({oc['pct']:g}%), before the spare pieces. "
            "Short cuts are taken from the end of long pieces, so the offcuts left are the ones too short to use.", ""]
    if bom["ways_to_waste_less"]:
        out += ["### Ways to waste less", "",
                "Advice only: the design is not changed. Each figure comes from packing the list again with that change.", ""]
        out += [f"- {h['text']}" for h in bom["ways_to_waste_less"]] + [""]
    for ln in bom["timber"]:
        out += [f"### {ln['name']}, {ln['variant']}: {ln['cuts']} cuts on "
                f"{len(ln['layouts'])} pieces ({ln['plan']}, {ln['waste_pct']:g}% waste)", ""]
        out += ["| Piece | Length | Cuts | Offcut |", "|---|---|---|---|"]
        for p in ln["layouts"]:
            cuts = ", ".join(f"{c['id']} ({L(c['length_mm'])})" for c in p["cuts"])
            out.append(f"| {p['piece']} | {L(p['stock_mm'])} | {cuts} | {L(p['offcut_mm'])} |")
        out += ["", f"Cuts: {kinds_in_words(ln['by_kind'])}.", ""]

    out += ["## Sheets", ""]
    out += [f"| Item | Sheet | Buy | Price each | Line total |{sh[0]}", f"|---|---|---|---|---|{sh[1]}"]
    for ln in bom["sheets"]:
        a, b = ln["sheet_size_mm"]
        qty = f"{ln['sheets_to_buy']}" + (f" (incl. {ln['spare_sheets']} spare)" if ln["spare_sheets"] else "")
        each, tot = price_cells(ln["unit_price"], ln["total"])
        out.append(f"| {ln['name']} | {L(a)} × {L(b)} | {qty} | {each} | {tot} |" + sc(priced_as(ln)))
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

    def total_cell(line):
        return money(line["total"], cur) if line.get("priced") else "no price"

    def fastener_rows(lines, nails):
        for f in lines:
            used = ", ".join(f"{JOINT_NAMES.get(t, t)} {n:,}" for t, n in
                             sorted(f["by_joint_type"].items(), key=lambda tn: (-tn[1], tn[0])))
            if nails:
                u = f["weight_unit"]
                packs = nail_packs_text(f).replace(" x ", " × ")
                out.append(f"| {f['name']} | {f['counted']:,} | {f['spare']:,} | about {f['weight']:g} {u} | "
                           f"{packs} ({f['to_buy']:,} nails) | {used} | {total_cell(f)} |" + sc(priced_as(f)))
            else:
                packs = ", ".join(f"{p['qty']} × {p['size']:g}" for p in f["packs"])
                out.append(f"| {f['name']} | {f['counted']} | {f['spare']} | {f['to_buy']} | {packs} | {used} | {total_cell(f)} |"
                           + sc(priced_as(f)))

    nails = [f for f in bom["fasteners"] if f["kind"] == "nail"]
    screws = [f for f in bom["fasteners"] if f["kind"] != "nail"]
    out += ["## Nails", "",
            "Nails are bought by weight: the count (with the spare) is turned into kg or lb and rounded up to the box sizes.", ""]
    out += [f"| Nail | Counted | Spare | Weight | Buy | Counted for | Price |{sh[0]}", f"|---|---|---|---|---|---|---|{sh[1]}"]
    fastener_rows(nails, True)
    out.append("")
    out += ["## Structural screws", "",
            "Only where a screw is stronger than a nail: the rafters to the wall plates (uplift) and the wall panels to each other at the corners.", ""]
    out += [f"| Item | Counted | Spare | Buy | Packs | Counted for | Price |{sh[0]}", f"|---|---|---|---|---|---|---|{sh[1]}"]
    fastener_rows(screws, False)
    out.append("")
    out += ["## Bought items", ""]
    out += [f"| Item | Quantity | Note | Price |{sh[0]}", f"|---|---|---|---|{sh[1]}"]
    for b in bom["bought"]:
        out.append(f"| {b['name']} | {b['qty']:g} {b['unit']} | {bought_note(b)} | {total_cell(b)} |" + sc(priced_as(b)))
    out.append("")
    out += ["## Notes", ""] + [f"- {n}" for n in bom["notes"]] + [""]
    return "\n".join(out)


CUT_FIELDS = ["type", "item", "variant", "piece", "stock_mm", "member", "group", "kind", "what", "length_mm",
              "width_mm", "x_mm", "y_mm", "cut_deg_a", "cut_deg_b", "rotated"]


def write_cutlist(bom, path):
    """One row per cut and per sheet part; with prices, a last `supplier` column: where the line it belongs to is bought."""
    fields = CUT_FIELDS + (["supplier"] if bom.get("snapshot") else [])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields, extrasaction="ignore")
        w.writeheader()
        for ln in bom["timber"]:
            for p in ln["layouts"]:
                for c in p["cuts"]:
                    w.writerow({"type": ln["kind"], "item": ln["item"], "variant": ln["variant"],
                                "piece": p["piece"], "stock_mm": p["stock_mm"], "member": c["id"],
                                "group": c["group"], "kind": c["kind"], "what": c["what"], "length_mm": c["length_mm"],
                                "cut_deg_a": c["cut_deg"][0], "cut_deg_b": c["cut_deg"][1],
                                "supplier": ln.get("supplier") or ""})
        for ln in bom["sheets"]:
            for s in ln["layouts"]:
                for p in s["parts"]:
                    w.writerow({"type": "sheet", "item": ln["item"], "variant": "", "piece": f"{ln['item']}#{s['sheet']}",
                                "stock_mm": "", "member": p["id"], "what": KIND_NAMES["sheet"][0], "length_mm": p["w"], "width_mm": p["h"],
                                "x_mm": p["x"], "y_mm": p["y"], "rotated": int(p["rotated"]),
                                "supplier": ln.get("supplier") or ""})


def nail_summary(bom):
    w = {}
    for f in bom["fasteners"]:
        if f["kind"] == "nail":
            w[f["weight_unit"]] = w.get(f["weight_unit"], 0) + f["buy_weight"]
    return ", ".join(f"{v:g} {u} of nails" for u, v in w.items()) or "no nails"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("frame", help="frame.json from tools/frame.py")
    ap.add_argument("--snapshot", help="one price snapshot CSV (data/timber/prices/); without it there are no prices")
    ap.add_argument("--prices", metavar="REGION[:SUPPLIER]",
                    help="price from the newest snapshot of every supplier in a region (hu, cz, us), or of one "
                         "supplier (hu:szekely-fatelep); each line goes to the supplier that sells all of it cheapest")
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
    if a.prices and not a.snapshot:
        try:
            snap = [rows for _, rows in tl.load_snapshots(a.prices)]
        except ValueError as e:
            if "currency" in str(e):
                sys.exit(f"bom: {e}")
            print(f"   {e}: the list has no prices", file=sys.stderr)
    try:
        bom = make_bom(frame, snap, a.waste, a.kerf, a.sheet_spare, a.trim)
    except ValueError as e:
        sys.exit(f"bom: {e}")
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
