"""Posts: upright members on footings. A grid or a list of points, a section
from the library, each standing on a footing's post base."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402
from timber.store import r1  # noqa: E402


class Posts:
    """Posts of one section. `place` stands one at each point from `bottom` to
    `top` (millimetres above the origin) and returns {"id", "x", "y", "bottom", "top"}."""

    def __init__(self, frame, lib, item_key, group="frame", treated=True):
        self.fr, self.lib, self.key = frame, lib, item_key
        it = tl.item(lib, item_key)
        self.t, self.w = it["thickness_mm"], it["width_mm"]       # a post is square or nearly
        self.kw = dict(treated=treated, variant="impregnated" if treated else "sawn")
        self.group = group
        self.records = []

    @staticmethod
    def grid(xs, ys):
        """Points of a grid, row by row (y, then x)."""
        return [(x, y) for y in ys for x in xs]

    def place(self, points, top, bottom=None, footings=None, prefix="posts"):
        """A post at each (x, y). `bottom` is one height for all, or taken from the
        matching footing record in `footings` (its post-base top); each post is
        joined to that footing's post base."""
        out = []
        for i, (x, y) in enumerate(points):
            foot = footings[i] if footings else None
            z0 = foot["top"] if foot else bottom
            n = len(self.records) + 1
            pid = self.fr.box(f"{prefix}/post-{n:02d}", "post", self.group, "frame", self.key,
                              (x - self.t / 2, y - self.w / 2, z0), (x + self.t / 2, y + self.w / 2, top), 2, 0, **self.kw)
            rec = {"id": pid, "x": r1(x), "y": r1(y), "bottom": r1(z0), "top": r1(top)}
            self.records.append(rec)
            out.append(rec)
            if foot:
                self.fr.joint("post-base", foot["base"], pid)
        return out

    def assembly(self):
        self.fr.assembly("posts", "posts", [
            {"role": "posts", "kind": "post", "count": len(self.records), "item": self.key}])
