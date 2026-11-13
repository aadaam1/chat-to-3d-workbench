"""Blocks of a summer kitchen: a roof line over two beams, the numbers the walls and roof
share (KitchenLayout), a wall panel between two posts (KitchenWall) and a terrace floor
inside the posts (build_floor). `recipes.summer_kitchen` puts them together with the
footings, posts, beams and knee braces of the pergola.

Coordinates: millimetres, Z up from the ground, X the width, Y the depth, the front at
Y 0. The post rectangle's outer faces are the footprint (0..width, 0..depth). A wall
panel stands between two posts with its inner face flush with the posts' inner faces;
its sheathing and cladding go on the outer face.
"""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402
from timber.store import EPS, SpecError, _clean  # noqa: E402
from timber.beam import Beam  # noqa: E402
from timber.foundations import Footings, footing_item  # noqa: E402
from timber.platform import BoardPlatform  # noqa: E402
from timber.posts import Posts  # noqa: E402
from timber.roof import RoofLine  # noqa: E402
from timber.wall import Wall  # noqa: E402

MIN_POST_LEN = 100.0           # mm, a post shorter than this is not worth cutting


def even(lo, hi, max_gap):
    """Positions from lo to hi, evenly spaced and no more than max_gap apart (at least two)."""
    n = max(1, math.ceil((hi - lo) / max_gap - 1e-9))
    return [round(lo + (hi - lo) * i / n, 1) for i in range(n + 1)]


class BeamRoofLine(RoofLine):
    """A mono roof's line over two beams: the rafters' underside touches the front beam's
    inner top edge (Y `yf`, height `zf`) and the back beam's outer top edge (`yb`, `zb`)."""

    def __init__(self, yf, zf, yb, zb):
        self.hf, self.w = zf, 0.0
        self.y0, self.z0 = yf, zf
        self.k = (zf - zb) / (yb - yf)
        self.ang = math.atan(self.k)
        self.sin, self.cos = math.sin(self.ang), math.cos(self.ang)

    def underside(self, y):
        return self.z0 - (y - self.y0) * self.k


class KitchenLayout:
    """What Wall and the roof blocks read from a Layout, for a summer kitchen: the library
    items, the section sizes, the roof's heights, plus what the roof needs to bear on beams
    (`bear_type`, `eave_inset`, `rafter_xs`, `tie_range`...). The floor level of a wall is its
    own (`Wall.zd`), so `zd` here is only a default."""

    def __init__(self, spec, lib, ptx, pty):
        self.s, self.lib = spec, lib
        s = spec
        self.W, self.D = spec["width"], spec["depth"]
        self.ptx, self.pty = ptx, pty
        self.frame = tl.item(lib, s["frame_item"])
        self.t, self.w = self.frame["thickness_mm"], self.frame["width_mm"]
        self.raf = tl.item(lib, s["rafter_item"])
        self.tr, self.wr = self.raf["thickness_mm"], self.raf["width_mm"]
        self.rdeck = tl.item(lib, s["roof_deck"])
        self.sheath = tl.item(lib, s["sheathing"])
        self.clad = tl.item(lib, s["cladding"])
        self.ts, self.tc = self.sheath["thickness_mm"], self.clad["thickness_mm"]
        self.zd = 0.0
        self.gable = s["roof"] == "gable"
        self.hf = self.hb = 0.0
        self.courses = 2 if s["top_plate"] == "double" else 1
        hd = tl.item(lib, s["header_item"])
        self.th, self.hh = hd["thickness_mm"], hd["width_mm"]
        self.plies = 2 if 2 * self.th <= self.w + EPS else 1
        self.bear_type = "rafter-beam"

    def height_field(self, wall):
        if self.gable:
            return "height_eaves"
        return "height_front" if wall == "front" else "height_back"


class KitchenWall(Wall):
    """One wall panel between two posts. `panel` = {"side", "k", "s0", "s1", "zd", "top",
    "ops"}: the range along the wall (X for the back wall, Y for the side walls) between the
    posts' faces, the height of its bottom plate's underside and of its top plates' top, and its
    openings as (index, opening). Built like a shed's side wall (end studs, no corner pieces),
    with infill studs up to the roof line on the left and right walls."""

    def __init__(self, frame, lay, line, panel, wall_index):
        super().__init__(frame, lay, panel["side"], line)
        self.panel, self.windex = panel, wall_index
        self.group = f"wall-{panel['side']}"
        self.gid = f"{self.group}/p{panel['k']}"
        self.through = False
        self.tall_rows = True
        self.zd = panel["zd"]
        self.hb = panel["top"]
        if lay.gable:
            self.hf = line.gable_top
        else:
            self.hf = line.underside(panel["s0"]) if panel["side"] != "back" else panel["top"]

    def label(self, i):
        return f"walls[{self.windex}].openings[{i}]"

    def opening_list(self, name):
        return self.panel["ops"]

    def strip_limits(self, name, wf):
        return wf["s0"], wf["s1"]

    def upper_span(self, name, S0, S1):
        return S0, S1

    def wall_frame(self, name):
        p, lay = self.panel, self.lay
        w = self.w
        if name == "back":
            return dict(s0=p["s0"], s1=p["s1"], ax=0, dax=1, sign=1, d0=self.D - lay.pty + w, top=p["top"])
        if name == "left":
            return dict(s0=p["s0"], s1=p["s1"], ax=1, dax=0, sign=-1, d0=lay.ptx - w, top=p["top"])
        return dict(s0=p["s0"], s1=p["s1"], ax=1, dax=0, sign=1, d0=self.W - lay.ptx + w, top=p["top"])

    def profile(self, a, b):
        """(y, z) points of the roof line over the wall, from Y a to b."""
        if self.gable:
            return self.line.top_profile(a, b)
        return [(a, self.line.underside(a)), (b, self.line.underside(b))]

    def wall_outline(self, name):
        wf, zd = self.wf, self.zd
        a, b = wf["s0"], wf["s1"]
        if name == "back":
            return [(a, zd), (b, zd), (b, wf["top"]), (a, wf["top"])]
        return _clean([(a, zd), (b, zd)] + self.profile(a, b)[::-1])

    def cladding_clip(self, name):
        return None if name == "back" else self.wall_outline(name)

    def _board_span(self, name, zb):
        a, b = self.wf["s0"], self.wf["s1"]
        if name == "back":
            return a, b, 0.0
        above = zb >= self.hb - EPS
        return a, b, (round(90 - math.degrees(self.line.ang), 1) if above else 0.0)


def build_floor(fr, lib, spec, rect):
    """A terrace floor on its own footings, posts (when the height allows them) and beams,
    inside `rect` = (x0, y0, x1, y1), the clear area between the posts' inner faces. Joists
    run along Y on the beams, boards along X. Ids start with floor-... so the roof's
    posts and beams keep theirs. Returns the beam records and the footings."""
    fx0, fy0, fx1, fy1 = rect
    fW, fD = fx1 - fx0, fy1 - fy0
    H = spec["floor_height"]
    tdef = lib["defaults"]["terrace"]
    board, joist = tl.item(lib, spec["deck_board"]), tl.item(lib, spec["joist_item"])
    beam_it = tl.item(lib, spec["floor_beam_item"])
    td, hj, hb = board["thickness_mm"], joist["width_mm"], beam_it["width_mm"]
    z_joist = H - td - hj
    foot = Footings(fr, lib, footing_item(lib, spec["foundation"], spec["footing_item"]))
    posts = Posts(fr, lib, spec["floor_post_item"])
    beam = Beam(fr, lib, spec["floor_beam_item"], spec["floor_beam_plies"], "on_top")
    post_top = z_joist - hb
    no_posts = post_top - foot.seat < tdef["min_post_mm"] and z_joist - hb >= foot.seat - 0.05
    inset = math.ceil((beam.width() / 2 + 25) / 5) * 5
    if min(fW, fD) < 2 * inset + 300:
        raise SpecError("floor: the clear area between the posts is too small for a floor "
                        f"({fW:g} x {fD:g} mm); make the structure bigger or use floor: none")
    ys = even(inset, fD - inset, spec["floor_row_spacing"])
    xs = even(inset, fW - inset, spec["floor_post_spacing"])
    pts = [(fx0 + x, fy0 + y) for y in ys for x in xs]
    if no_posts:
        seat = z_joist - hb
        if seat < foot.seat - 0.05:
            low = foot.seat + hb + hj + td
            raise SpecError(f"floor_height: {H:g} mm is too low for this footing, beam and deck; "
                            f"at least {low:g} mm (use a shallower floor_beam_item or a lower footing)")
        recs = foot.place(pts, carry=(posts.t, beam.width()), ground=0.0, top=seat, prefix="floor-foundations")
        pid = None
    else:
        if post_top - foot.seat < MIN_POST_LEN:
            low = H - (post_top - foot.seat) + MIN_POST_LEN
            raise SpecError(f"floor_height: {H:g} mm is too low for this footing, beam and deck; use at least {low:g} mm")
        recs = foot.place(pts, carry=(posts.t, posts.w), ground=0.0, prefix="floor-foundations")
        pid = posts.place(pts, top=post_top, footings=recs, prefix="floor-posts")
    nx = len(xs)
    edges = [0.0] + [(a + b) / 2 for a, b in zip(ys, ys[1:])] + [fD]
    for k, y in enumerate(ys):
        sup = [(fx0 + x, (pid[k * nx + i]["id"] if pid else recs[k * nx + i]["base"])) for i, x in enumerate(xs)]
        beam.place(fy0 + y, fx0, fx1, z_joist, sup, posts.w, edges[k + 1] - edges[k], axis=0, prefix="floor-beams",
                   fix=(lambda a, b: fr.joint("post-base", b, a)) if no_posts else None, cap=not no_posts)
    deck = BoardPlatform(fr, lib, fW, fD, spec["joist_item"], spec["deck_board"], spec["joist_spacing"], H,
                         gap=spec["board_gap"], origin=(fx0, fy0)).build(bearers=ys)
    deck.bear_on([p for r in beam.records for p in r["plies"]])
    foot.buy()
    beam.buy()
    foot.assembly("floor-foundations")
    if pid:
        posts.assembly("floor-posts")
    beam.assembly("floor-beams")
    return foot
