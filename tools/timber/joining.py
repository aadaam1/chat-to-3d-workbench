"""Joining: a piece longer than the longest timber on sale for its item is cut in two (or more) where a
carpenter would join it, once the frame is built, so frames whose pieces all fit are untouched.

A piece is joined only where a simple rule gives a sound joint, each end of the joint resting on the same
support (the rule per kind is in RULES, and in framing.md):
  cladding boards    butt joint on a stud, staggered from course to course
  wall plates        butt joint over a stud (bottom and lower top plate); the upper top plate's joints
                     are at least UPPER_OFFSET from the lower plate's
  rim joists         over a floor joist
  fascia boards      over a rafter
  bargeboards        beside a roof block, on the end rafter that runs the whole way behind them
  ridge board        at a rafter pair, the rafters either side holding the joint
  beams              over a post (the two plies of a beam in different places when there is a choice)
  deck joists        over a beam
Anything else (a floor joist, rafter, tie or stud as long as the span it covers) is left as it is: the
`stock-length` check reports it and says what to do.

Each piece becomes members `<id>-a`, `<id>-b`, ... and a `butt` joint between neighbours; the joints the
original had are given to every piece that touches the other member, so a joint on a support is fixed on both
sides.
"""
import os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import frame_edits as fe  # noqa: E402
from timber.store import EPS, _is_rect, _poly_clip, num  # noqa: E402

UPPER_OFFSET = 600.0        # mm: the upper top plate's joint this far (at least) from the one below (IRC R602.3.2: 24 in.)
MIN_PIECE = 300.0           # mm: no piece is cut shorter than this
VERT = ("stud", "king", "jack", "cripple")
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def longest(lib, item):
    cat = "cladding" if item in lib.get("cladding", {}) else "sections"
    rec = lib.get(cat, {}).get(item)
    if not rec or not rec.get("stock_lengths_mm"):
        return None
    return max(rec["stock_lengths_mm"] + rec.get("order_lengths_mm", []))


def _x(m):
    return np.array(m["x"], float)


def _u(m, p):
    """Position of the point p along the member's length axis, from its start."""
    return float((np.array(p, float) - np.array(m["origin"], float)) @ _x(m))


def _span(m, ref):
    """(lo, hi) of member m along the length axis of `ref`, from its start."""
    c = fe._corners(m)
    u = (c - np.array(ref["origin"], float)) @ _x(ref)
    return float(u.min()), float(u.max())


def _centre(m):
    c = fe._corners(m)
    return (c.min(0) + c.max(0)) / 2


def choose(length, limit, cands, avoid=(), apart=0.0, first_max=None):
    """Cut positions along a piece `length` long, none longer than `limit`: each on a candidate, the pieces
    at least MIN_PIECE, the first no longer than `first_max`, the cuts at least `apart` from every one in
    `avoid`. Longest pieces first. None when there is no way."""
    cs = sorted(c for c in cands if MIN_PIECE <= c <= length - MIN_PIECE and all(abs(c - a) >= apart - 0.5 for a in avoid))

    def rec(start, cuts):
        if length - start <= limit + 0.5:
            return cuts
        hi = start + limit + 0.5
        if first_max is not None and not cuts:
            hi = min(hi, first_max + 0.5)
        for c in sorted((c for c in cs if start + MIN_PIECE <= c <= hi), reverse=True):
            r = rec(c, cuts + [c])
            if r is not None:
                return r
        return None
    return rec(0.0, [])


def slice_member(m, u0, u1, first, last, pid):
    """The part of member m between u0 and u1 along its length, as a new member."""
    p = dict(m)
    x = _x(m)
    p["id"] = pid
    p["origin"] = [num(v) for v in np.array(m["origin"], float) + u0 * x]
    p["size"] = [num(u1 - u0), m["size"][1], m["size"][2]]
    cut = list(m["cut_deg"])
    p["cut_deg"] = [cut[0] if first else 0, cut[1] if last else 0]
    p["cut_deg"] = [num(v) for v in p["cut_deg"]]
    if m.get("outline"):
        poly = _poly_clip([tuple(q) for q in m["outline"]], u0, u1, -1e9, 1e9)
        local = [(a - u0, b) for a, b in poly]
        p["outline"] = None if not local or _is_rect(local, u1 - u0, m["size"][1]) else [[num(a), num(b)] for a, b in local]
    return p


class Joiner:
    def __init__(self, fr, lib):
        self.fr, self.lib = fr, lib
        self.by = {m["id"]: m for m in fr.members}
        self.cuts = {}                  # id -> cut positions chosen
        self.notes = {}                 # label -> dict(count, max_len, item, limit, support)

    # ------------------------------------------------------------ supports per kind

    def touching(self, m, kinds, group=None, pred=None):
        out = []
        for s in self.fr.members:
            if s is m or s["kind"] not in kinds or (group and s["group"] != group):
                continue
            if pred and not pred(s):
                continue
            if fe.contact(m, s) is not None:
                out.append(s)
        return out

    def cands(self, m, kinds, group=None, pred=None):
        return sorted(_u(m, _centre(s)) for s in self.touching(m, kinds, group, pred))

    def plan(self, m, limit, boards_rank):
        """(cut positions, label, support) for a piece too long, or None when no simple rule applies."""
        k, mid, L = m["kind"], m["id"], m["size"][0]
        g = m["group"]
        if k == "board":
            rank = boards_rank.get((g, round(float(fe._corners(m)[:, 2].min()), 0)), 0)
            lo_z, hi_z = fe._corners(m)[:, 2].min(), fe._corners(m)[:, 2].max()
            c = [_u(m, _centre(s)) for s in self.fr.members
                 if s["group"] == g and s["kind"] in VERT
                 and min(hi_z, fe._corners(s)[:, 2].max()) - max(lo_z, fe._corners(s)[:, 2].min()) >= 30.0]
            if not c:               # a course above the top plate is nailed at the studs below it, as the generator does
                c = [_u(m, _centre(s)) for s in self.fr.members if s["group"] == g and s["kind"] in VERT]
            return choose(L, limit, c, first_max=limit * (0.5 if rank % 2 else 1.0)), "Cladding boards", "stud"
        if k == "plate":
            if "plate-top-2" in mid:
                low = self.by.get(mid.replace("plate-top-2", "plate-top"))
                avoid = [self._rel(m, self._abs(low, u)) for u in self.cuts.get(low["id"], [])] if low else []
                c = [_u(m, _centre(s)) for s in self.fr.members if s["group"] == g and s["kind"] in VERT]
                return choose(L, limit, c, avoid=avoid, apart=UPPER_OFFSET), "Upper top plates", "stud"
            c = self.cands(m, VERT, g)
            return choose(L, limit, c), ("Top plates" if "plate-top" in mid else "Bottom plates"), "stud"
        if k == "rim":
            return choose(L, limit, self.cands(m, ("joist",), g)), "Rim joists", "floor joist"
        if k == "fascia":
            return choose(L, limit, self.cands(m, ("rafter",), "roof")), "Fascia boards", "rafter"
        if k == "bargeboard":
            c = sorted(_u(m, _centre(s)) for s in self.fr.members if s["group"] == "roof" and s["kind"] in ("blocking", "outrigger")
                       and 0 < _u(m, _centre(s)) < L)
            c = sorted(set(round(v, 1) for v in c))
            return choose(L, limit, c), "Bargeboards", "roof block, on the end rafter behind"
        if k == "ridge":
            c = self.cands(m, ("rafter",), "roof")
            return choose(L, limit, c), "Ridge board", "rafter pair"
        if k == "beam":
            c = self.cands(m, ("post", "post-base"))
            avoid = []
            base = mid.split("-ply")[0]
            if mid != base:
                first = self.by.get(base)
                avoid = [self._rel(m, self._abs(first, u)) for u in self.cuts.get(base, [])]
            got = choose(L, limit, c, avoid=avoid, apart=1.0)
            if got is None and avoid:
                got = choose(L, limit, c)
            return got, "Beams", "post"
        if k == "joist" and g == "deck":
            c = self.cands(m, ("beam",))
            c = [v for i, v in enumerate(c) if i == 0 or v - c[i - 1] > 60.0]       # one candidate per beam, not per ply
            return choose(L, limit, c), "Deck joists", "beam"
        return None

    def _abs(self, m, u):
        """World position along the member's axis (a projection on its x axis from the world origin)."""
        return float(np.array(m["origin"], float) @ _x(m)) + u

    def _rel(self, m, a):
        return a - float(np.array(m["origin"], float) @ _x(m))

    # ------------------------------------------------------------ the pass

    def run(self):
        fr, lib = self.fr, self.lib
        over = []
        for m in fr.members:
            if m["kind"] == "sheet":
                continue
            lim = longest(lib, m["item"])
            if lim is not None and m["size"][0] > lim + 0.5:
                over.append((m, lim))
        if not over:
            return []
        zlo = {}
        for m in fr.members:
            if m["kind"] == "board":
                zlo.setdefault(m["group"], set()).add(round(min(fe._corners(m)[:, 2]), 0))
        rank = {(g, z): i for g, zs in zlo.items() for i, z in enumerate(sorted(zs))}
        # the lower plate before the upper one (the upper reads the lower's cuts), the first ply before the second
        order = sorted(over, key=lambda p: (p[0]["id"].endswith("-2") or "-ply" in p[0]["id"], p[0]["id"]))
        pieces = {}
        for m, lim in order:
            got = self.plan(m, lim, rank)
            if not got or got[0] is None or not got[0]:
                continue
            cuts, label, support = got
            self.cuts[m["id"]] = cuts
            edges = [0.0] + cuts + [m["size"][0]]
            pieces[m["id"]] = [slice_member(m, a, b, i == 0, i == len(edges) - 2,
                                            f"{m['id']}-{LETTERS[i]}") for i, (a, b) in enumerate(zip(edges, edges[1:]))]
            n = self.notes.setdefault(label, dict(count=0, max_len=0.0, item=m["item"], limit=lim, support=support, pieces=0))
            n["count"] += 1
            n["pieces"] += len(edges) - 1
            n["max_len"] = max(n["max_len"], m["size"][0])
        self.pieces = pieces
        if not pieces:
            return []
        self.rewire()
        return self.notes

    def rewire(self):
        fr = self.fr
        old = {m["id"]: m for m in fr.members}
        members = []
        for m in fr.members:
            if m["id"] in self.pieces:
                members += self.pieces[m["id"]]
            else:
                members.append(m)
        new = {m["id"]: m for m in members}
        joints = []

        def opts(mid):
            return self.pieces.get(mid) or [new[mid]]

        for j in fr.joints:
            a, b = j["a"], j["b"]
            if a not in self.pieces and b not in self.pieces:
                joints.append(j)
                continue
            pa, pb = opts(a), opts(b)
            pairs = [(x, y) for x in pa for y in pb]
            if j["type"] != "board-frame":
                touch = [(x, y) for x, y in pairs if fe.contact(x, y) is not None]
                pairs = touch or pairs
            whole_a, whole_b = old[a], old[b]
            for x, y in pairs:
                nj = dict(j, a=x["id"], b=y["id"])
                if "edge_mm" in j:
                    ref = whole_a if a in self.pieces else whole_b
                    w0 = _ov(_span(whole_a, ref), _span(whole_b, ref))
                    w1 = _ov(_span(x, ref), _span(y, ref))
                    nj["edge_mm"] = num(j["edge_mm"] * (w1 / w0 if w0 > EPS else 1.0 / len(pairs)))
                    if nj["edge_mm"] <= 0:
                        continue
                if j["type"] == "board-frame":
                    nj["crossings"] = max(1, self.crossings(x))
                joints.append(nj)
        for oid, ps in self.pieces.items():
            for p, q in zip(ps, ps[1:]):
                joints.append({"type": "butt", "a": p["id"], "b": q["id"]})
        fr.members[:] = members
        fr.joints[:] = joints

    def crossings(self, board):
        lo_z, hi_z = fe._corners(board)[:, 2].min(), fe._corners(board)[:, 2].max()
        lo, hi = 0.0, board["size"][0]
        n = n_any = 0
        for s in self.fr.members:
            if s["group"] != board["group"] or s["kind"] not in VERT:
                continue
            if not lo - 1.0 <= _u(board, _centre(s)) <= hi + 1.0:
                continue
            n_any += 1
            c = fe._corners(s)
            if c[:, 2].max() >= lo_z + 1.0 and c[:, 2].min() <= hi_z - 1.0:
                n += 1
        return n or n_any


def _ov(r, s):
    return max(0.0, min(r[1], s[1]) - max(r[0], s[0]))


def join_long(fr, lib):
    """Join every piece longer than its item's longest stock length that a rule covers. Returns
    {label: {count, pieces, max_len, item, limit, support}} (empty when nothing was joined)."""
    return Joiner(fr, lib).run() or {}
