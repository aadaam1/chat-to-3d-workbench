"""The planner: what the description leaves open is chosen here, by the span engine (timber/spans.py).

A member whose section or spacing the description does not name is sized so that its span is "ok"
for the checks (not "check", not "fix"): the smallest section of the library that fits the role, at
the library's spacing; if none does, the spacing steps down the library's ladder (600, 400, 300 mm or
24, 16, 12 in.) and the sections are tried again. A value the description names is never changed.
Every choice that differs from the library's plain default is recorded as a decision, in plain
words, and ends up in the frame ("decisions") and the shopping list.
"""
import math

from timber import spans as sp

FIT = sp.WARN_FRACTION                 # a span within this share of the allowable is "ok" (see spans.level_for)
MIN_SPACING = 600.0                    # mm: a beam that carries less between posts than this is not a design
STEP = 50.0                            # mm: spacings and heights are rounded to this


class Spec(dict):
    """A resolved description. The decisions made while resolving it (and notes the recipes turn into
    decisions once the layout is known) hang on it, outside the dict: the frame's `spec` stays the plain
    description it always was."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.decisions = []
        self.notes = {}

    def copy(self):
        c = Spec(self)
        c.decisions, c.notes = self.decisions, self.notes
        return c


def decide(spec, what, chose, why):
    """Record one decision: what was decided, what was chosen and why, in plain words."""
    if hasattr(spec, "decisions"):
        spec.decisions.append({"what": what, "chose": chose, "why": why})


def ceil_step(mm, step=STEP):
    return math.ceil(mm / step - 1e-9) * step


def floor_step(mm, step=STEP):
    return math.floor(mm / step + 1e-9) * step


def length_text(mm, units):
    """A length in the frame's units (the helper the checks use)."""
    return sp.length_text(mm, units)


def section_name(lib, key):
    return lib["sections"][key]["name"]


# --------------------------------------------------------------- spacing under a span limit

def spacing_under(allowed, cap=None, share=sp.SPACING_SHARE, step=STEP):
    """The spacing the generator keeps a span under: `share` of what the formulas allow, no more than
    `cap` (None: no cap), in whole `step`s. Returns (spacing in mm or None, limiter, the unrounded limit):
    the limiter is "cap" or "span"; the spacing is None when the limit is under MIN_SPACING (nothing
    sensible fits)."""
    want = share * allowed
    lim = want if cap is None else min(cap, want)
    limiter = "cap" if cap is not None and cap <= want else "span"
    if lim < MIN_SPACING:
        return None, limiter, lim
    return float(math.floor(lim / step) * step), limiter, lim


def spacing_note(allowed, cap, limiter, what):
    """What the spacing was worked out from, for spec.notes (and the decision the recipe records)."""
    return {"allowed": allowed, "cap": cap, "limiter": limiter, "what": what}


def spacing_why(note, units):
    n = note
    t = (f"{n['what']} is good for {length_text(n['allowed'], units)}; the generator keeps spans under "
         f"{sp.SPACING_SHARE:.0%} of that")
    if n["limiter"] == "cap":
        t += f", and no further apart than the library's {length_text(n['cap'], units)}"
    return t


def decide_grid(spec, what, noun, positions, note):
    """Record a layout: `positions` along one direction, spaced by the planner (a description that
    named the spacing has no note, and no decision)."""
    if note is None or len(positions) < 2:
        return
    u = spec["units"]
    gap = positions[1] - positions[0]
    decide(spec, what, f"{len(positions)} {noun}, {length_text(gap, u)} apart", spacing_why(note, u))


# --------------------------------------------------------------- sections and spacings

def candidates(lib, default_key, words, area_up=True):
    """Sections that can take the place of `default_key` in a role: the same thickness, a `uses` entry
    naming one of `words` (or the default itself), no smaller than the default; smallest first."""
    d = lib["sections"][default_key]
    out = []
    for k, v in lib["sections"].items():
        if "deck" in v or v["thickness_mm"] != d["thickness_mm"]:
            continue
        if k != default_key and not any(w in u for u in v.get("uses", []) for w in words):
            continue
        if area_up and v["width_mm"] < d["width_mm"]:
            continue
        out.append(k)
    return sorted(out, key=lambda k: (lib["sections"][k]["width_mm"], k))


def ladder(lib, default_mm):
    """Spacings tighter than the default, from the library's steps."""
    steps = lib["defaults"].get("spacing_steps_mm", [])
    return [float(x) for x in sorted(steps, reverse=True) if x < default_mm - 0.5]


def fits(span, allowed):
    return span <= allowed * FIT + 1e-9


class Sized:
    """The outcome of sizing one member role."""

    def __init__(self, key, spacing, span, allowed, ok, changed, base):
        self.key, self.spacing, self.span, self.allowed = key, spacing, span, allowed
        self.ok, self.changed, self.base = ok, changed, base      # base: (span, allowed) of the plain default


def size_member(lib, default_key, default_spacing, words, ev, *, item_named=None, spacing_named=False):
    """Pick the section and spacing of a member role. `ev(key, spacing)` gives (span, allowed) in mm for
    that section and spacing. A named item (or spacing) stays as given."""
    key0 = item_named or default_key
    base = ev(key0, default_spacing)
    if fits(*base) or (item_named and spacing_named):
        return Sized(key0, default_spacing, base[0], base[1], fits(*base), False, base)
    keys = [item_named] if item_named else candidates(lib, default_key, words)
    steps = [default_spacing] + ([] if spacing_named else ladder(lib, default_spacing))
    best = None
    for sp_ in steps:
        for k in keys:
            span, allowed = ev(k, sp_)
            best = (k, sp_, span, allowed)
            if fits(span, allowed):
                return Sized(k, sp_, span, allowed, True, (k, sp_) != (key0, default_spacing), base)
    k, sp_, span, allowed = best
    return Sized(k, sp_, span, allowed, False, (k, sp_) != (key0, default_spacing), base)


def explain(lib, role, res, default_key, default_spacing, units, span_text="the span is"):
    """(chose, why) for a sized member that differs from the plain default."""
    nm = lambda k: section_name(lib, k)
    chose = f"{nm(res.key)} at {length_text(res.spacing, units)}"
    b_span, b_allowed = res.base
    why = (f"{nm(default_key)} at {length_text(default_spacing, units)} is good for {length_text(b_allowed, units)}; "
           f"{span_text} {length_text(b_span, units)}")
    if not res.ok:
        why += (f". Nothing in the library fits comfortably: this is the best it can do "
                f"(good for {length_text(res.allowed, units)}), and the checks say so")
    return chose, why
