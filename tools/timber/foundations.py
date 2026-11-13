"""Foundations: bought footings under posts or under a platform's bearing
points. A footing is two members on the `foundations` layer: a body (a ground
screw, a concrete block or a poured pier; kinds `ground-screw`, `pier`,
`footing`) and a post base on top of it (kind `post-base`). Both are bought
items counted by number. Their sizes come from the library; load capacity is
NOT checked. Millimetres, Z up; the body's top is the ground (ground screw) or
`above_mm` above it (blocks, piers).
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402
from timber.store import SpecError, r1  # noqa: E402

FOUNDATIONS = ("ground_screw", "pier_block", "concrete_footing")
BODY_KIND = {"ground_screw": "ground-screw", "pier_block": "pier", "concrete_footing": "footing"}
BASE_MARGIN = 20.0          # mm, a post base is this much wider than what it carries


def footing_item(lib, foundation, key=None):
    """The library record of the footing for a foundation kind: the named item,
    or the region's default. Raises SpecError naming `foundation`."""
    if foundation not in FOUNDATIONS:
        raise SpecError(f"foundation: {foundation!r} is not supported; use one of {', '.join(FOUNDATIONS)}")
    if key is None:
        key = lib["defaults"]["terrace"]["footings"][foundation]
    try:
        it = tl.item(lib, key) if isinstance(key, str) else None
    except KeyError:
        it = None
    f = (it or {}).get("foundation")
    if not f or f["kind"] != foundation:
        have = ", ".join(k for k, v in lib["bought"].items() if v.get("foundation", {}).get("kind") == foundation)
        raise SpecError(f"footing_item: {key!r} is not a {foundation} footing in the {lib['region']} library (have: {have})")
    return it


class Footings:
    """Footings placed at points. `place` makes one at each point and returns
    records {"id", "base", "x", "y", "ground", "top"}: `top` is the height of the
    top of the post base, where the carried member's underside lands."""

    def __init__(self, frame, lib, item, group="foundations"):
        self.fr, self.lib, self.it, self.group = frame, lib, item, group
        self.f = item["foundation"]
        self.base_it = tl.item(lib, self.f["base"])
        self.bh = float(self.base_it["post_base"]["height_mm"])
        self.records = []

    @property
    def seat(self):
        """Natural height of the top of the post base above the ground."""
        return self.f["above_mm"] + self.bh

    def place(self, points, carry, ground=None, top=None, prefix="foundations"):
        """A footing at each (x, y). `carry` is the (x, y) footprint of what it
        carries. Give the ground height, or the top of the post base, or both
        (the part above ground is then built up to fit)."""
        if ground is None and top is None:
            raise ValueError("place: give ground or top")
        if ground is None:
            ground = top - self.seat
        if top is None:
            top = ground + self.seat
        above = top - ground - self.bh
        if above < self.f["above_mm"] - 0.05:
            raise SpecError(f"height: too low for this footing: its post base ends {self.seat:g} mm above the ground "
                            f"but only {top - ground:g} mm are available")
        bw, bd = carry[0] + BASE_MARGIN, carry[1] + BASE_MARGIN
        kind = BODY_KIND[self.f["kind"]]
        w, d = self.f["body_mm"]
        out = []
        for x, y in points:
            n = len(self.records) + 1
            body = self.fr.box(f"{prefix}/{kind}-{n:02d}", kind, self.group, "foundations", self.it["key"],
                               (x - w / 2, y - d / 2, ground - self.f["below_mm"]), (x + w / 2, y + d / 2, ground + above),
                               2, 0)
            base = self.fr.box(f"{prefix}/post-base-{n:02d}", "post-base", self.group, "foundations", self.base_it["key"],
                               (x - bw / 2, y - bd / 2, ground + above), (x + bw / 2, y + bd / 2, top), 2, 0)
            rec = {"id": body, "base": base, "x": r1(x), "y": r1(y), "ground": r1(ground), "top": r1(top)}
            self.records.append(rec)
            out.append(rec)
        return out

    def fix(self, rec, member_id):
        """Record that a post, beam or rim is fixed to this footing's post base."""
        self.fr.joint("post-base", rec["base"], member_id)

    def buy(self):
        """Add the footings and their post bases to the shopping list, by number."""
        n = len(self.records)
        if not n:
            return
        self.fr.bought.append({"item": self.it["key"], "qty": n, "unit": "pcs",
                               "note": "foundation; load capacity not checked: check the maker's table for your soil"})
        self.fr.bought.append({"item": self.base_it["key"], "qty": n, "unit": "pcs", "note": "one per footing"})

    def assembly(self, aid="foundations"):
        self.fr.assembly(aid, aid, [
            {"role": "footings", "kind": "footing", "count": len(self.records), "item": self.it["key"],
             "foundation": self.f["kind"],
             "ground_mm": self.records[0]["ground"] if self.records else 0.0}])
