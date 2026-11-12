"""The platform: a floor frame of joists between two rim joists, blocking under
the sheet seams, and a deck of sheets on top. Everything in millimetres, origin
at the front-left outer corner of the frame; the walls stand on its deck."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import framing as fr_rules  # noqa: E402
from timber.store import EPS, _ov, layout, r1, sheet_cuts, _norm  # noqa: E402

fr = fr_rules


class Platform:
    """The floor. Exposes `top` (the height of the deck's top face, where the
    walls start), `rim` (ids of the front and back rim joists), `joist_ids`,
    `floor_sheets` and `floor_blocks`."""

    def __init__(self, frame, lay):
        self.fr = frame
        self.s, self.W, self.D = lay.s, lay.W, lay.D
        self.tj, self.hj, self.fdeck = lay.tj, lay.hj, lay.fdeck
        self.top = lay.zd
        self.box, self.joint = frame.box, frame.joint

    def build(self):
        self.floor()
        self.fr.assembly("floor", "platform", [
            {"role": "floor joists", "kind": "joist", "spacing_mm": _norm(self.s["joist_spacing"]),
             "deck": self.s["floor_deck"], "deck_role": "floor", "deck_group": "floor"}])
        return self

    def floor(self):
        s, W, D, tj, hj = self.s, self.W, self.D, self.tj, self.hj
        tr = s["treated_floor"]
        kw = dict(treated=tr, variant="impregnated" if tr else "sawn")
        fi = s["floor_item"]
        rf = self.box("floor/rim-front", "rim", "floor", "floor", fi, (0, 0, 0), (W, tj, hj), 0, 2, **kw)
        rb = self.box("floor/rim-back", "rim", "floor", "floor", fi, (0, D - tj, 0), (W, D, hj), 0, 2, **kw)
        self.rim = (rf, rb)
        self.joist_x = layout(W, tj, s["joist_spacing"])
        self.joist_ids = []
        for i, x0 in enumerate(self.joist_x, 1):
            jid = self.box(f"floor/joist-{i:02d}", "joist", "floor", "floor", fi,
                           (x0, tj, 0), (x0 + tj, D - tj, hj), 1, 2, **kw)
            self.joist_ids.append(jid)
            self.joint("joist-rim", jid, rf)
            self.joint("joist-rim", jid, rb)
        # deck: sheets across the joists in rows symmetric about mid-span, staggered;
        # blocking under every seam across the joists (and at mid-span if needed)
        short, long_ = self.fdeck["size_mm"]
        rows = [r1(y) for y in fr.deck_rows(D, short)]
        self.floor_blocks = []
        bl = 0
        for y in fr.blocking_rows(rows, tj, D - tj):
            for a, b in zip(self.joist_x, self.joist_x[1:]):
                x0, x1 = a + tj, b
                if x1 - x0 < EPS:
                    continue
                bl += 1
                bid = self.box(f"floor/blocking-{bl:02d}", "blocking", "floor", "floor", fi,
                               (x0, y - tj / 2, 0), (x1, y + tj / 2, hj), 0, 2, **kw)
                self.floor_blocks.append((bid, y))
                self.joint("joist-rim", bid, self.joist_ids[self.joist_x.index(a)])
                self.joint("joist-rim", bid, self.joist_ids[self.joist_x.index(b)])
        cand = [x0 + tj / 2 for x0 in self.joist_x]
        td = self.fdeck["thickness_mm"]
        n = 0
        self.floor_sheets = []
        for r, (y0, y1) in enumerate(zip(rows, rows[1:])):
            for x0, x1 in sheet_cuts(W, cand, long_, r, "width", "floor deck"):
                n += 1
                sid = self.box(f"floor/deck-{n:02d}", "sheet", "floor", "floor", s["floor_deck"],
                               (x0, y0, hj), (x1, y1, hj + td), 0, 1)
                self.floor_sheets.append((sid, x0, x1, y0, y1))
        # sheet-frame contacts on the top faces of joists, rims and blocking
        faces = [(rf, 0, W, 0, tj), (rb, 0, W, D - tj, D)]
        faces += [(j, x0, x0 + tj, tj, D - tj) for j, x0 in zip(self.joist_ids, self.joist_x)]
        for bid, y in self.floor_blocks:
            m = self.fr.member(bid)
            ox = m["origin"][0]
            faces.append((bid, ox, ox + m["size"][0], y - tj / 2, y + tj / 2))
        for sid, x0, x1, y0, y1 in self.floor_sheets:
            for mid, a0, a1, b0, b1 in faces:
                ox, oy = _ov(x0, x1, a0, a1), _ov(y0, y1, b0, b1)
                if ox > EPS and oy > EPS:
                    self.joint("sheet-frame", sid, mid, edge_mm=max(ox, oy))