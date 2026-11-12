"""Framing details: the carpentry conventions tools/frame.py follows, one
function per detail, in wall coordinates (s along the wall, d inward from the
wall's outer face, z up; millimetres). They decide where pieces go; frame.py
turns them into members and joints.

Conventions (platform framing, as in the IRC wall framing section and UK
timber frame practice; see .claude/skills/timber-build/framing.md):

- Corners. The front and back walls run the full width; the side walls fit
  between them. At each end of the front and back walls a corner assembly
  gives the side wall's end stud something solid to screw into and the
  inside lining a fixing at the corner:
    three-stud   end stud, spacer blocks, and a second stud one wall-depth in
    california   end stud and a stud laid flat at the inner face
    two-stud     end stud only (lining needs clips)
- Top plate: double by default. The upper plate of each side wall runs over
  the back wall to tie the corner; the front corners differ in height in a
  mono-pitch shed, so there the side wall butts the front wall's framing.
- Openings: a king stud full height each side, a jack stud inside it from
  the bottom plate to the header, the header resting on the jacks, a sill
  between the jacks on cripples, and cripples above the header. Cripples are
  spaced evenly across the opening, one at each end and none further apart
  than the stud spacing, so they sit symmetric about its middle (a
  sheathing joint over an opening lands on any of them).
- Floor: deck sheets are laid in rows across the joists, symmetric about
  the middle of the span (a seam on the centre line, or a whole sheet
  centred on it), so no row is narrower than half a sheet. A row of blocking
  sits under every seam across the joists, and one at mid-span if a joist
  would still run more than 1.5 m without one.
- Roof edges: blocking between the rafters over the front and back walls
  closes the bays; a fascia board on the plumb-cut rafter ends front and
  back; at the sides a ladder (outriggers from the end rafter to a flying
  rafter) carries the side overhang, with a bargeboard on the flying rafter.
"""

import math

CORNER_STYLES = ("three-stud", "california", "two-stud")
SPACER_LEN = 300.0          # mm, each spacer block in a three-stud corner


def corner_extent(style, t, w):
    """How far along the wall a corner assembly reaches from the wall's end."""
    if style == "three-stud":
        return w + t
    if style == "california":
        return t + w
    return t


def corner_pieces(style, t, w, c0, c1, at_start, zs0, zs1):
    """The pieces of one corner assembly besides the layout's end stud (which
    frame.py places at the very end of the wall). c0..c1 is the assembly's
    range along the wall; at_start says whether it is at the low end."""
    out = []
    if style == "three-stud":
        b = (c1 - t, c1) if at_start else (c0, c0 + t)          # the inner stud, one wall-depth in
        out.append(dict(name="stud", kind="stud", s=b, d=(0, w), z=(zs0, zs1), laxis="z", waxis="d"))
        gap = (c0 + t, c1 - t) if at_start else (c0 + t, c1 - t)
        if gap[1] - gap[0] > 1.0:
            h = zs1 - zs0
            for k, zc in enumerate((zs0 + SPACER_LEN / 2, zs0 + h / 2, zs1 - SPACER_LEN / 2), 1):
                out.append(dict(name=f"spacer-{k}", kind="blocking", s=gap, d=(0, w),
                                z=(zc - SPACER_LEN / 2, zc + SPACER_LEN / 2), laxis="z", waxis="d"))
    elif style == "california":
        flat = (c0 + t, c1) if at_start else (c0, c1 - t)       # laid flat against the inner face
        out.append(dict(name="flat", kind="stud", s=flat, d=(w - t, w), z=(zs0, zs1), laxis="z", waxis="s"))
    return out


def upper_plate_span(wall, S0, S1, w, depth):
    """Where the second top plate runs. The side walls' upper plates continue
    over the back wall to lap the corner; the back wall's stops short of them."""
    if wall == "back":
        return S0 + w, S1 - w
    if wall in ("left", "right"):
        return S0, depth
    return S0, S1


def header_plies(plies, th, w):
    """Depth ranges of the header plies across a wall w deep: two plies flush
    with both faces (a spacer fills any gap between them), or one centred."""
    if plies == 2:
        return [(0.0, th), (w - th, w)]
    return [((w - th) / 2, (w + th) / 2)]


def even_cripples(a, b, t, spacing):
    """Cripples across an opening from a to b (the jacks' inner faces): one
    at each end, next to the jacks, and evenly spaced between them so no two
    are more than `spacing` apart, centre to centre. Symmetric about the
    middle of the opening; a single one in the middle if two don't fit."""
    run = b - t - a                         # first to last cripple, face to face
    if run < t - 1e-6:
        return [round((a + b - t) / 2, 1)]
    n = max(1, math.ceil(run / spacing - 1e-9))
    return [round(a + run * i / n, 1) for i in range(n + 1)]


# ----------------------------------------------------------------- floor

MAX_UNBLOCKED = 1500.0      # mm, a joist runs no further than this without a row of blocking


def deck_rows(span, step):
    """Row boundaries of a deck laid across the joists, symmetric about the
    middle: n rows, the n - 2 inner ones whole sheets, the two outer ones
    equal and at least half a sheet."""
    n = max(1, math.ceil(span / step - 1e-9))
    if n == 1:
        return [0.0, span]
    edge = (span - (n - 2) * step) / 2
    return [0.0] + [edge + i * step for i in range(n - 1)] + [span]


def blocking_rows(rows, lo, hi):
    """Where rows of blocking go between joists running from lo to hi: under
    every seam of the deck, and at mid-span if a stretch is still too long."""
    ys = [y for y in rows[1:-1] if lo < y < hi]
    stops = [lo] + ys + [hi]
    if any(b - a > MAX_UNBLOCKED for a, b in zip(stops, stops[1:])):
        mid = (lo + hi) / 2
        if all(abs(mid - y) > 1.0 for y in ys):
            ys = sorted(ys + [mid])
    return ys


# ------------------------------------------------------------------ roof

OVERHANG_SIDE_MAX = 300.0   # mm, more needs lookouts running back to the second rafter
MIN_OUTRIGGER = 50.0        # mm, shortest outrigger between the end rafter and the flying rafter


def ladder(lo, hi, required, spacing, t):
    """Centres of the outriggers in a ladder along the slope: one at each end
    (lo, hi), the required ones between (wall lines, deck seams), then more so
    no gap between centres is over `spacing`. A required one within one
    thickness of another is dropped."""
    pts = [lo]
    for p in sorted(required):
        if p - pts[-1] >= t and hi - p >= t:
            pts.append(p)
    pts.append(hi)
    out = [pts[0]]
    for p in pts[1:]:
        gap = p - out[-1]
        n = math.ceil(gap / spacing - 1e-9)
        out += [out[-1] + gap * i / n for i in range(1, n)]
        out.append(p)
    return out
