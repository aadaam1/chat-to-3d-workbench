"""The platform: a floor frame of joists between two rim joists, blocking under
the sheet seams, and a deck of sheets on top. Everything in millimetres, origin
at the front-left outer corner of the frame; the walls stand on its deck."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import framing as fr_rules  # noqa: E402
import timberlib as tl  # noqa: E402
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

# ------------------------------------------------------------ a board deck

DECK_GAP_MAX = 8.0          # mm, the widest gap the boards are spread to
MIN_RIPPED = 40.0           # mm, no board is ripped narrower than this


def board_rows(D, bw, gap):
    """Boards across a deck D deep: whole boards with `gap` between them, and the
    left-over either as a ripped last board or spread over the gaps. Returns
    [(y0, y1)], the first at 0 and the last ending at D."""
    if D <= bw:
        return [(0.0, D)]
    n = int((D + gap + EPS) // (bw + gap))
    rem = D - (n * bw + (n - 1) * gap)
    widths, gaps = [bw] * n, [gap] * (n - 1)
    if rem - gap >= MIN_RIPPED:
        widths.append(rem - gap)
        gaps.append(gap)
    elif n > 1 and gap + rem / (n - 1) <= DECK_GAP_MAX:
        gaps = [gap + rem / (n - 1)] * (n - 1)
    elif n > 1:                                     # too much left over to hide in the gaps
        widths.append(max(rem - gap, MIN_RIPPED))
        gaps.append(gap)
    rows, y = [], 0.0
    for i, w in enumerate(widths):
        rows.append((r1(y), r1(y + w)))
        y += w + (gaps[i] if i < len(gaps) else 0)
    rows[-1] = (rows[-1][0], r1(D))
    return rows


class BoardPlatform:
    """A deck of boards on joists that bear on beams (or any bearers), instead
    of the shed floor's sheets on joists on the ground. Joists run along Y from
    0 to D at `spacing`; boards run along X across them, a gap apart, in pieces
    no longer than the longest stock length with the ends staggered row to row
    and landing on joists. `top` is the height of the deck's top face. Exposes
    `joist_ids`, `joist_x`, `boards` (ids with their rows) and `bottom` (the
    joists' underside, where the bearers' tops must be)."""

    def __init__(self, frame, lib, W, D, joist_item, board_item, spacing, top, gap=None,
                 group="deck", treated=True):
        self.fr, self.lib, self.W, self.D = frame, lib, W, D
        self.ji, self.bi = tl.item(lib, joist_item), tl.item(lib, board_item)
        self.joist_item, self.board_item = joist_item, board_item
        self.tj, self.hj = self.ji["thickness_mm"], self.ji["width_mm"]
        self.bw, self.td = self.bi["width_mm"], self.bi["thickness_mm"]
        self.spacing, self.top, self.group = spacing, top, group
        self.gap = float(gap if gap is not None else self.bi.get("deck", {}).get("gap_mm", 5))
        self.bottom = top - self.td - self.hj
        self.kw = dict(treated=treated, variant="impregnated" if treated else "sawn")

    def build(self, bearers=()):
        """Make the joists and the boards. `bearers` are the Y positions of the beams'
        centre lines the joists bear on (for the span record)."""
        fr, W, D, tj, hj = self.fr, self.W, self.D, self.tj, self.hj
        z0, z1 = self.bottom, self.bottom + hj
        self.joist_x = layout(W, tj, self.spacing)
        self.joist_ids = []
        for i, x0 in enumerate(self.joist_x, 1):
            self.joist_ids.append(fr.box(f"deck/joist-{i:02d}", "joist", self.group, "floor", self.joist_item,
                                         (x0, 0, z0), (x0 + tj, D, z1), 1, 2, **self.kw))
        stock = max(self.bi["stock_lengths_mm"])
        cand = [x0 + tj / 2 for x0 in self.joist_x]
        rows = board_rows(D, self.bw, self.gap)
        self.boards, self.rows = [], rows
        for r, (y0, y1) in enumerate(rows):
            cuts = [(0.0, W)] if W <= stock + EPS else sheet_cuts(W, cand, stock, r, "deck_board", "deck")
            for k, (x0, x1) in enumerate(cuts):
                a = x0 + (self.gap / 2 if k else 0)
                b = x1 - (self.gap / 2 if k < len(cuts) - 1 else 0)
                bid = f"deck/board-{r + 1:02d}" + (f"-{k + 1}" if len(cuts) > 1 else "")
                fr.box(bid, "deckboard", self.group, "deck", self.board_item,
                       (a, y0, self.top - self.td), (b, y1, self.top), 0, 1, **self.kw)
                self.boards.append((bid, r, a, b, y0, y1))
                for jid, jx in zip(self.joist_ids, self.joist_x):
                    if _ov(a, b, jx, jx + tj) > EPS:
                        fr.joint("deck-board", bid, jid, crossings=1)
        pts = sorted(bearers)
        span = max((q - p for p, q in zip(pts, pts[1:])), default=D)
        spacing_to_check = self.spacing
        fr.assembly("deck", "platform", [
            {"role": "deck joists", "kind": "joist", "spacing_mm": _norm(spacing_to_check), "span_mm": r1(span),
             "bearers": [r1(p) for p in pts], "item": self.joist_item, "deck": self.board_item,
             "deck_role": "boards", "deck_group": "deck"},
            {"role": "deck boards", "kind": "deckboard", "item": self.board_item, "gap_mm": r1(self.gap),
             "max_joist_spacing_mm": self.bi.get("deck", {}).get("max_joist_spacing_mm")}])
        return self

    def bear_on(self, beam_ids):
        """Record that the joists bear on these beams (plies): a `joist-beam` joint at every crossing."""
        for bid in beam_ids:
            for jid in self.joist_ids:
                self.fr.joint("joist-beam", jid, bid)
