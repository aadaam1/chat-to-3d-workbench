"""A flush deck frame: for a deck too low for beams under the joists. The beams sit directly on the post
bases (no posts), the joists hang between them in joist hangers with their tops level with the beams', and
the boards lie on top of both. Shared by the terrace and the summer kitchen's floor."""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402
from timber.store import SpecError  # noqa: E402
from timber.beam import Beam  # noqa: E402
from timber.platform import BoardPlatform  # noqa: E402


def even(lo, hi, max_gap):
    """Positions from lo to hi, evenly spaced and no more than max_gap apart (at least two)."""
    n = max(1, math.ceil((hi - lo) / max_gap - 1e-9))
    return [round(lo + (hi - lo) * i / n, 1) for i in range(n + 1)]


def build(fr, lib, foot, *, W, D, H, origin, spec, beam_key, plies, joist_key, board_key, post_key, joist_spacing,
          gap, row_spacing, post_spacing, inset, prefix_f, prefix_b, what="height"):
    """The footings, beams, hung joists and boards of a deck W x D with its top at H, its front-left corner at
    `origin`. Returns (beam, deck, footing records, ys, xs)."""
    ox, oy = origin
    board, joist, bm = tl.item(lib, board_key), tl.item(lib, joist_key), tl.item(lib, beam_key)
    td, hj, hb = board["thickness_mm"], joist["width_mm"], bm["width_mm"]
    post_t = tl.item(lib, post_key)["thickness_mm"]
    z_top = H - td
    seat = z_top - hb                                   # the beams' underside: the top of the post bases
    if seat < foot.seat - 0.05:
        raise SpecError(f"{what}: {H:g} mm is too low for this footing and a {bm['name']} beam; "
                        f"at least {foot.seat + hb + td:g} mm")
    beam = Beam(fr, lib, beam_key, plies, "on_top")
    ys = even(inset, D - inset, row_spacing)
    xs = even(inset, W - inset, post_spacing)
    pts = [(ox + x, oy + y) for y in ys for x in xs]
    recs = foot.place(pts, carry=(post_t, beam.width()), ground=0.0, top=seat, prefix=prefix_f)
    nx = len(xs)
    edges = [0.0] + [(a + b) / 2 for a, b in zip(ys, ys[1:])] + [D]
    for k, y in enumerate(ys):
        sup = [(ox + x, recs[k * nx + i]["base"]) for i, x in enumerate(xs)]
        beam.place(oy + y, ox, ox + W, z_top, sup, post_t, edges[k + 1] - edges[k], axis=0, prefix=prefix_b,
                   fix=lambda a, b: fr.joint("post-base", b, a), cap=False)
    deck = BoardPlatform(fr, lib, W, D, joist_key, board_key, joist_spacing, H, gap=gap, origin=origin,
                         flush=beam.width()).build(bearers=ys)
    deck.hang_on(beam.records)
    deck.buy_hangers()
    return beam, deck, recs, ys, xs
