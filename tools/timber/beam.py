"""Beams: one or two plies along a line over posts (or footings), recording the
spans between supports and the width they carry for the span checks."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402
from timber.store import SpecError, r1  # noqa: E402

MOUNTS = ("on_top", "sandwich")


class Beam:
    """Beams of one section and ply count. mount `on_top`: the plies lie side by
    side on the posts (on a post cap), `sandwich`: a ply either side of each post,
    bolted through (two plies only). `place` returns {"id" (first ply), "plies",
    "span_mm", "trib_mm"}."""

    def __init__(self, frame, lib, item_key, plies=2, mount="on_top", group="frame", treated=True):
        if mount not in MOUNTS:
            raise SpecError(f"beam_mount: {mount!r} is not supported; use one of {', '.join(MOUNTS)}")
        if mount == "sandwich" and plies != 2:
            raise SpecError("beam_plies: a sandwich beam has two plies")
        if plies not in (1, 2):
            raise SpecError("beam_plies: use 1 or 2")
        self.fr, self.lib, self.key, self.plies, self.mount, self.group = frame, lib, item_key, plies, mount, group
        it = tl.item(lib, item_key)
        self.tb, self.hb = it["thickness_mm"], it["width_mm"]
        self.kw = dict(treated=treated, variant="impregnated" if treated else "sawn")
        self.records = []
        self.caps = 0

    def width(self, post_t=0.0):
        """Overall width of the beam across its line: the plies (and the post in a sandwich)."""
        return self.plies * self.tb + (post_t if self.mount == "sandwich" else 0.0)

    def place(self, line, a0, a1, top, supports, post_t, trib, axis=0, prefix="beams", fix=None, cap=True):
        """A beam along `axis` (0 X, 1 Y) from a0 to a1, centred on `line` across it,
        its top at `top`. `supports` is a list of (position along the beam, member id)
        of the posts (or footings' post bases) it rests on or is bolted to; `post_t`
        the posts' thickness across the beam; `trib` the width of floor it carries.
        `fix(ply_id, support_id)` replaces the joint to a support (default: beam-post or beam-cap);
        `cap` False leaves out the post caps of an on_top beam (it sits on post bases)."""
        cross = 1 - axis
        n = len(self.records) + 1
        bid = f"{prefix}/beam-{n:02d}"
        if self.mount == "sandwich":
            off = [-(post_t + self.tb) / 2, (post_t + self.tb) / 2]
        else:
            off = [(i - (self.plies - 1) / 2) * self.tb for i in range(self.plies)]
        ids = []
        for k, o in enumerate(off):
            lo, hi = [0.0, 0.0, top - self.hb], [0.0, 0.0, top]
            lo[axis], hi[axis] = a0, a1
            lo[cross], hi[cross] = line + o - self.tb / 2, line + o + self.tb / 2
            mid = bid if k == 0 else f"{bid}-ply{k + 1}"
            ids.append(self.fr.box(mid, "beam", self.group, "frame", self.key, lo, hi, axis, 2, **self.kw))
        if self.mount == "on_top" and len(ids) == 2:
            self.fr.joint("beam-ply", ids[0], ids[1], edge_mm=a1 - a0)
        typ = "beam-post" if self.mount == "sandwich" else "beam-cap"
        for pos, sid in supports:
            for pid in ids:
                if fix is None:
                    self.fr.joint(typ, pid, sid)
                else:
                    fix(pid, sid)
            if cap and self.mount == "on_top":
                self.caps += 1
        pos = sorted(p for p, _ in supports)
        span = max((b - a for a, b in zip(pos, pos[1:])), default=0.0)
        rec = {"id": bid, "plies": ids, "axis": axis, "line": r1(line), "a0": r1(a0), "a1": r1(a1), "top": r1(top),
               "supports": [r1(p) for p in pos], "span_mm": r1(span), "trib_mm": r1(trib), "ply_count": self.plies}
        self.records.append(rec)
        return rec

    def buy(self):
        """Post caps for the on_top beams, by number (one per post a beam rests on)."""
        if self.caps:
            self.fr.bought.append({"item": "post-cap", "qty": self.caps, "unit": "pcs",
                                   "note": "one per post under a beam; sized to the post and the beam"})

    def assembly(self):
        self.fr.assembly("beams", "beams", [
            {"role": f"beam {r['id']}", "kind": "beam", "id": r["id"], "item": self.key, "plies": r["ply_count"],
             "line": r["line"], "axis": r["axis"],
             "span_mm": r["span_mm"], "trib_mm": r["trib_mm"], "supports": r["supports"]} for r in self.records])
