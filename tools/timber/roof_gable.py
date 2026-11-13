"""A gable roof: the ridge runs along X (the width) at the middle of the depth,
the front and back walls are the eave walls (same height, carrying the
rafters) and the left and right walls are the gable walls, whose top plates
stay level and whose studs rise to the roof line.

Rafters come in pairs, plumb-cut against the faces of a ridge board, each
seated on its eave wall's top plate the way the mono roof seats its rafters
(no birdsmouth). A tie (ceiling joist) beside each pair's rafters, seated on the
plates, holds the walls from spreading. Eave blocking, fascia and a ladder
(outriggers to a flying rafter) with bargeboards on both slopes at the gable
ends finish it; the deck runs from each eave up to the ridge. The rules and
their sources are in .claude/skills/timber-build/framing.md.

The roof's line (GableLine) is a pure function of Y, known before any wall is
built. A slope is built once, in the frame of the back slope (falling toward
+Y), and the front slope is its mirror image about the ridge.
"""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402
import framing as fr_rules  # noqa: E402
from timber.store import EPS, _clean, _norm, _ov, deck_rows, layout, r1, sheet_cuts  # noqa: E402
from timber.roof import SlopeRoof  # noqa: E402

fr = fr_rules
SLOPES = ("front", "back")
RIDGE_GAP = 8.0             # mm, kept open between each slope's deck and the apex


class GableLine:
    """The roof's line: the rafters' underside as a pure function of Y. It
    touches the eave walls' top plates at their outer edges (Y 0 and the
    depth), rises at the pitch to the ridge board and runs flat across the
    ridge board's underside (`rb`) between its two faces (`yf`, `yb`)."""

    gable = True

    def __init__(self, lay, tg, dr):
        self.he, self.D, self.w, self.wr = lay.hf, lay.D, lay.w, lay.wr
        self.inset = getattr(lay, "eave_inset", 0.0)   # the bearing's outer edge is this far in from the footprint
        self.ang = math.radians(lay.s["pitch_deg"])
        self.sin, self.cos, self.k = math.sin(self.ang), math.cos(self.ang), math.tan(self.ang)
        self.tg, self.dr = tg, dr                      # the ridge board: thickness, depth
        self.yf, self.yb = self.D / 2 - tg / 2, self.D / 2 + tg / 2
        self.ridge_top = self.slope(self.yf) + self.wr / self.cos   # rafter tops, flush with the ridge top
        self.rb = self.ridge_top - dr                  # underside of the ridge board
        self.gable_top = self.slope(self.yf)           # the highest the gable walls' skin goes

    def slope(self, y):
        """The underside's sloped line, extended over the ridge board."""
        return self.he + (min(y, self.D - y) - self.inset) * self.k

    def underside(self, y):
        """Height of the underside of whatever bears the roof's weight over Y."""
        return self.rb if self.yf < y < self.yb else self.slope(y)

    def top_over(self, a, b):
        """Height a stud between Y a and b rises to: its top follows the roof line,
        so this is the highest point; under the ridge board it stops at the board."""
        if a < self.yb - EPS and b > self.yf + EPS:
            return self.rb
        return self.slope(b) if b <= self.D / 2 else self.slope(a)

    def cut_deg(self, a, b):
        return 0.0 if (a < self.yb - EPS and b > self.yf + EPS) else round(math.degrees(self.ang), 1)

    def top_profile(self, a, b):
        """(y, z) points along the roof line from Y a to b, with a vertical step
        at each edge of the ridge board."""
        e = 1e-6
        out = [(a, self.underside(a + e))]
        for y in (self.yf, self.yb):
            if a + EPS < y < b - EPS:
                out += [(y, self.underside(y - e)), (y, self.underside(y + e))]
        out.append((b, self.underside(b - e)))
        return out


class GableRoof(SlopeRoof):
    """The gable roof. Given the line, the ids of the two eave walls' bearing
    plates and the infill studs of the gable walls. Exposes `rafters` (ids per
    slope), `rafter_x`, `flying`, `ridge`, `ties`, `barges`, `roof_blocks`,
    `roof_sheets` and `deck_len`; `buy()` adds the roofing and the ridge cap."""

    def __init__(self, frame, lay, line, bear, infill):
        super().__init__(frame, lay, line)
        self.bear, self.infill, self.he = bear, infill, lay.hf
        self.lay = lay
        self.flip = False
        self._add = frame.add
        self.add = self._add_slope

    def _add_slope(self, mid, kind, group, layer, item, size, centre, x, y, **kw):
        """Members of the front slope are the back slope's mirror image about the ridge."""
        if self.flip:
            centre = [centre[0], self.D - centre[1], centre[2]]
            x, y = (x[0], -x[1], x[2]), (y[0], -y[1], y[2])
        return self._add(mid, kind, group, layer, item, size, centre, x, y, **kw)

    def slope_underside(self, y):
        return self.line.slope(y)

    def underside(self, y):
        return self.line.underside(y)

    # ---------------------------------------------------------------- build

    def build(self):
        self.roof()
        s = self.s
        L = self.line
        run = r1(L.yf)                         # horizontal, from the eave wall's outer face to the ridge board
        self.fr.assembly("roof", "gable-roof", [
            {"role": "rafters", "kind": "rafter", "spacing_mm": _norm(s["rafter_spacing"]),
             "deck": s["roof_deck"], "deck_role": "roof", "deck_group": "roof",
             "span_mm": run, "pitch_deg": _norm(s["pitch_deg"])},
            {"role": "rafter ties", "kind": "tie", "spacing_mm": _norm(s["rafter_spacing"]),
             "span_mm": r1(self.D)},
            {"role": "ridge board", "kind": "ridge", "span_mm": r1(self.W + 2 * s["overhang_side"])}])
        return self

    def tie_outline(self, wt):
        """The tie's shape in (Y along the building, height above the plate top): a
        straight bar of depth wt, level and full length, whose top corners are
        trimmed to the roof plane (the rafter tops) if it would reach above it.
        None when nothing needs trimming."""
        D, L = self.D, self.line
        top = lambda y: L.slope(y) + self.wr / self.cos - self.he        # the rafter tops over Y
        if top(0.0) >= wt - EPS:
            return None
        y1 = (wt - self.wr / self.cos) / L.k
        pts = [(0.0, 0.0), (D, 0.0), (D, top(D)), (D - y1, wt), (y1, wt), (0.0, top(0.0))]
        return _clean([(r1(y), r1(v)) for y, v in pts])

    def roof(self):
        s, W, D, w, tr, wr, lib = self.s, self.W, self.D, self.w, self.tr, self.wr, self.lib
        oh, os_, L, he = s["overhang"], s["overhang_side"], self.line, self.he
        sn, cs = self.sin, self.cos
        tan_a = sn / cs
        tg = L.tg
        y_ref = L.yb                           # a slope's plumb line at the ridge, in its own frame
        self.d, self.nrm = (0, cs, -sn), (0, sn, cs)
        self.p0 = (0.0, y_ref, L.slope(y_ref))
        ri = s["rafter_item"]
        xs = self.rafter_xs or layout(W, tr, s["rafter_spacing"])
        self.rafter_x = xs
        fi = s["fascia_item"]
        fit = tl.item(lib, fi)
        tf, wf = fit["thickness_mm"], fit["width_mm"]
        ext = tf / cs                          # the fascia's thickness, measured down the slope

        # the ridge board: rafter tops flush with its top, rafters plumb-cut against its faces
        self.ridge = self.box("roof/ridge", "ridge", "roof", "roof", s["ridge_item"],
                              (-os_, L.yf, L.ridge_top - L.dr), (W + os_, L.yb, L.ridge_top), 0, 2)

        # lengths along a slope, measured down from the ridge-side plumb line (u = 0 on the underside)
        lu_h = (D + oh - y_ref) / cs           # underside, ridge plumb line to eave plumb line
        u_e = lu_h - wr * tan_a                # the rafter tops' plumb line at the eave
        U_E = u_e + ext                        # the deck's outer edge, over the fascia
        short, long_ = self.rdeck["size_mm"]
        # from the fascia's outer face up to 8 mm short of the apex: the two slopes' decks never touch, the ridge cap covers the gap
        self.deck_len = deck_len = lu_h + ext + tg / (2 * cs) - RIDGE_GAP
        rows = deck_rows(deck_len, short)      # rows from the eave up to the ridge
        seams = [U_E - e for e in rows[1:-1]]
        eaves = [(D - self.eave_in - y_ref - wr * sn) / cs - tr / 2]               # block's outer face over the eave wall
        eaves = [u for u in eaves if all(abs(u - v) >= tr for v in seams)]
        td = self.rdeck["thickness_mm"]
        barge_len = (D + oh - D / 2) / cs
        # the ties lie beside their rafters on the +X side; the blocking in that bay is shortened to fit
        tit = tl.item(lib, s["tie_item"])
        tt, wt = tit["thickness_mm"], tit["width_mm"]
        lo_t, hi_t = getattr(self.lay, "tie_range", (w, W - w))   # where ties may lie along X (a shed: between its gable walls)
        tied = [i for i, x0 in enumerate(xs[:-1])
                if x0 >= lo_t - EPS and x0 + tr + tt <= hi_t + EPS and xs[i + 1] - (x0 + tr) - tt >= 20.0]
        # a roof with no gable wall at its far end ties the last pair too, on the tie's -X side
        last = len(xs) - 1
        tie_last = bool(getattr(self.lay, "tie_last", False)) and last > 0 and xs[last] - tt >= lo_t - EPS \
            and xs[last] + tr <= hi_t + EPS and xs[last] - tt - (xs[last - 1] + tr) >= 20.0
        tie_x = {i: xs[i] + tr for i in tied}
        if tie_last:
            tie_x[last] = xs[last] - tt
        self.rafters = {sl: [] for sl in SLOPES}
        self.flying = {sl: [] for sl in SLOPES}
        self.roof_blocks = {sl: [] for sl in SLOPES}
        self.roof_sheets = {sl: [] for sl in SLOPES}
        self.barges = []
        self.ties = []
        ztop_f = L.slope(-oh) + wr / cs - tf * tan_a     # fascia tops, dropped to clear the deck over them
        outer_x = [("left", -os_ - tf), ("right", W + os_)]
        for sl in SLOPES:
            self.flip = sl == "front"
            bear = self.bear[sl]
            rafters = self.rafters[sl]
            for i, x0 in enumerate(xs, 1):
                rid = self.slope_member(f"roof/rafter-{sl}-{i:02d}", "rafter", ri, x0, tr, wr, y0=y_ref, y1=D + oh)
                rafters.append(rid)
                self.on_bear(rid, bear)
                self.joint("rafter-ridge", rid, self.ridge)
            # the side overhang: a flying rafter each side, carried on outriggers
            flying = self.flying[sl]
            if os_ > 0:
                for nm, x0 in (("left", -os_), ("right", W + os_ - tr)):
                    fid = self.slope_member(f"roof/flying-rafter-{sl}-{nm}", "rafter", ri, x0, tr, wr,
                                            y0=y_ref, y1=D + oh)
                    flying.append(fid)
                    self.on_bear(fid, bear)
                    self.joint("rafter-ridge", fid, self.ridge)
            # blocking over the eave wall and under the deck seams
            blocks = self.roof_blocks[sl]
            bl = ne = 0
            for u in sorted(eaves + seams):
                seam = u in seams
                for xa, xb in zip(xs, xs[1:]):
                    x0, x1 = xa + tr, xb
                    low = self.p0[2] - (u + tr / 2) * sn < he + wt - EPS    # the block's lowest point is below the tie's top
                    if xs.index(xa) in tied and low:
                        x0 += tt
                    if tie_last and xb == xs[last] and low:
                        x1 -= tt
                    if x1 - x0 < EPS:
                        continue
                    if seam:
                        bl += 1
                        bid = self.slope_block(f"roof/blocking-{sl}-{bl:02d}", "blocking", x0, x1, u)
                    else:
                        ne += 1
                        bid = self.slope_block(f"roof/eave-{sl}-{ne:02d}", "blocking", x0, x1, u)
                    blocks.append((bid, x0, x1, U_E - u))
                    self.joint("blocking-rafter", bid, rafters[xs.index(xa)])
                    self.joint("blocking-rafter", bid, rafters[xs.index(xb)])
            # the ladders: outriggers from the end rafter to the flying rafter
            if flying:
                at = fr.ladder(tr / 2, u_e - tr / 2, eaves + seams, s["rafter_spacing"], tr)
                for nm, fly, rid, (x0, x1) in (("left", flying[0], rafters[0], (-os_ + tr, 0.0)),
                                               ("right", flying[1], rafters[-1], (W, W + os_ - tr))):
                    for i, u in enumerate(at, 1):
                        oid = self.slope_block(f"roof/outrigger-{sl}-{nm}-{i:02d}", "outrigger", x0, x1, u)
                        blocks.append((oid, x0, x1, U_E - u))
                        self.joint("blocking-rafter", oid, rid)
                        self.joint("blocking-rafter", oid, fly)
            # fascia on the plumb-cut rafter ends
            y = -oh - tf if sl == "front" else D + oh
            fid = self.box(f"roof/fascia-{sl}", "fascia", "roof", "roof", fi,
                           (-os_ - tf, y, ztop_f - wf), (W + os_ + tf, y + tf, ztop_f), 0, 2)
            for rid in rafters + flying:
                self.joint("fascia-rafter", fid, rid)
            # bargeboards along the outer rafters, meeting the other slope's at the peak
            # (each plumb-cut at the centre line, which is the mitre between two equal slopes)
            outer = flying or [rafters[0], rafters[-1]]
            for (nm, x0), rid in zip(outer_x, outer):
                bid = self.slope_member(f"roof/bargeboard-{sl}-{nm}", "bargeboard", fi, x0, tf, wf,
                                        y0=D / 2, y1=D + oh)
                self.joint("barge-rafter", bid, rid, edge_mm=barge_len)
                self.barges.append((bid, x0))
            # the deck, edge to edge over the bargeboards, each sheet edge on a rafter
            allx = sorted(xs + ([-os_, W + os_ - tr] if flying else []))
            cand = [x0 + tr / 2 + os_ + tf for x0 in allx]
            n = 0
            sheets = self.roof_sheets[sl]
            for r, (e0, e1) in enumerate(zip(rows, rows[1:])):
                for a, b in sheet_cuts(W + 2 * (os_ + tf), cand, long_, r, "width", "roof deck"):
                    x0, x1 = r1(a - os_ - tf), r1(b - os_ - tf)
                    n += 1
                    uc = U_E - (e0 + e1) / 2
                    ctr = [(x0 + x1) / 2,
                           self.p0[1] + uc * self.d[1] + (wr + td / 2) * self.nrm[1],
                           self.p0[2] + uc * self.d[2] + (wr + td / 2) * self.nrm[2]]
                    sid = self.add(f"roof/deck-{sl}-{n:02d}", "sheet", "roof", "roof", s["roof_deck"],
                                   [x1 - x0, e1 - e0, td], ctr, (1, 0, 0), self.d)
                    sheets.append((sid, x0, x1, e0, e1))
            rf = list(zip(rafters, xs))
            if flying:
                rf += [(flying[0], -os_), (flying[1], W + os_ - tr)]
            bg = [(b, bx) for b, bx in self.barges if f"-{sl}-" in b]
            for sid, x0, x1, e0, e1 in sheets:
                for rid, rx in rf:
                    if _ov(x0, x1, rx, rx + tr) > EPS:
                        self.joint("sheet-frame", sid, rid, edge_mm=e1 - e0)
                for bid, bx in bg:
                    if _ov(x0, x1, bx, bx + tf) > EPS:
                        self.joint("sheet-frame", sid, bid, edge_mm=e1 - e0)
                if e0 <= EPS:
                    self.joint("sheet-frame", sid, f"roof/fascia-{sl}", edge_mm=x1 - x0)
                if abs(e1 - deck_len) <= EPS:
                    self.joint("sheet-frame", sid, self.ridge, edge_mm=x1 - x0)
                for bid, b0, b1, be in blocks:
                    if e0 - EPS <= be <= e1 + EPS and _ov(x0, x1, b0, b1) > EPS:
                        self.joint("sheet-frame", sid, bid, edge_mm=_ov(x0, x1, b0, b1))

        # the ties (ceiling joists): full depth, level, on both eave walls' top plates from outer face to
        # outer face, each beside the rafter pair on its +X side, face-nailed to both rafters at the heel.
        # A pair over a gable wall has none: that wall's top plates, lapped over the eave walls', tie that end.
        poly = self.tie_outline(wt)
        for i in sorted(tie_x):
            tid = self.add(f"roof/tie-{i + 1:02d}", "tie", "roof", "roof", s["tie_item"],
                           [D, wt, tt], [tie_x[i] + tt / 2, D / 2, he + wt / 2], (0, 1, 0), (0, 0, 1),
                           outline=poly)
            self.ties.append(tid)
            for sl in SLOPES:
                self.joint("tie-rafter", tid, self.rafters[sl][i])
                for b in ([self.bear[sl]] if isinstance(self.bear[sl], str) else self.bear[sl]):
                    self.joint("tie-plate", tid, b)
        # the gable walls' studs are fixed to the rafter (or the ridge board) over them
        for nm, k in (("left", 0), ("right", -1)):
            for iid, p, q, *_ in self.infill[nm]:
                if p < L.yb - EPS and q > L.yf + EPS:
                    self.joint("stud-plate", iid, self.ridge)
                else:
                    self.joint("stud-plate", iid, self.rafters["front" if q <= D / 2 else "back"][k])

    def buy(self):
        """The roofing the two slopes are covered with (by area) and the ridge cap (by length)."""
        s = self.s
        tf = tl.item(self.lib, s["fascia_item"])["thickness_mm"]
        wide = self.W + 2 * (s["overhang_side"] + tf)
        area = 2 * (wide / 1000) * (self.deck_len / 1000)
        note = f"roof area (2 slopes of {wide / 1000:g} x {self.deck_len / 1000:.3f} m) plus 10% overlap"
        self.bought.append({"item": s["roofing"], "qty": round(area * 1.1, 2), "unit": "m2", "note": note})
        cap = (wide / 1000) * 1.1
        self.bought.append({"item": "ridge-cap", "qty": round(cap, 2), "unit": "m",
                            "note": f"along the ridge ({wide / 1000:g} m) plus 10% overlap"})
