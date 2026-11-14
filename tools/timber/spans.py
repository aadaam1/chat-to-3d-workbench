"""The span engine: the factor table, the beam formula and the span limits of every member
that has one. The checks (tools/framecheck.py) and the planner (tools/frame.py, tools/timber/planning.py)
both read this, so a section the planner picks is judged by the same numbers the check uses.

THIS IS GUIDANCE FROM SIMPLE FORMULAS, NOT STRUCTURAL ENGINEERING (see framecheck.py).
"""
import math

# =========================================================== FACTOR TABLE
# Every factor the span formulas use, with where it comes from. `status`:
#   "published"  a number printed in a source the workbench read (see `source`)
#   "standard"   the value the cited standard gives, as widely reproduced;
#                the standard itself was NOT read (the tests compare the
#                result with published span tables instead)
#   "assumption" the workbench's own choice, named so it can be changed
# The research note (docs/research/timber-structures.md, T4) lists the dates
# the sources were read.
FACTORS = {
    "common": {
        "deflection_limit": {"value": 360, "status": "assumption",
            "source": "Planning decision, 2026-11-11 (not a standard): span / 360 for both regions.",
            "note": "Applied to the full characteristic load (own weight + deck + snow or floor load), no creep. At span / 300 the formulas ran up to 20% longer than the published C24 tables; those tables also cover a point load and vibration that this simple beam model leaves out, so the stricter limit stands in for them."},
        "g": {"value": 9.81, "status": "published", "source": "Standard gravity, m/s2."},
        "sheet_density_kg_m3": {"value": 600, "status": "assumption",
            "source": "Typical OSB density; not read from a datasheet.",
            "note": "Weight of the floor and roof deck sheets, per mm of thickness."},
        "covering_kn_m2": {"value": {"roofing-felt": 0.05, "metal-sheet": 0.06, "asphalt-shingle": 0.15},
            "status": "assumption", "source": "Typical weights of a light roof covering; not read from a datasheet.",
            "note": "Unknown coverings use 0.10 kN/m2."},
        "kn_m2_to_psf": {"value": 20.885, "status": "published", "source": "1 kN/m2 = 20.885 lbf/ft2."},
        "near_ground_mm": {"value": 150, "status": "assumption", "source": "Task spec: timber within 150 mm of the ground."},
    },
    "eu": {
        "gamma_G": {"value": 1.35, "status": "standard",
            "source": "EN 1990:2002 Table A1.2(B), eq. 6.10: partial factor on permanent actions."},
        "gamma_Q": {"value": 1.5, "status": "standard",
            "source": "EN 1990:2002 Table A1.2(B): partial factor on variable actions."},
        "gamma_M": {"value": 1.3, "status": "standard",
            "source": "EN 1995-1-1:2004 Table 2.3: material factor, solid timber."},
        "k_mod_permanent": {"value": 0.6, "status": "standard",
            "source": "EN 1995-1-1 Table 3.1, service class 1 or 2, permanent action.",
            "note": "Service class 2 assumed: roofed, not heated."},
        "k_mod_floor": {"value": 0.8, "status": "standard",
            "source": "EN 1995-1-1 Table 3.1, service class 2, medium-term action (imposed floor load)."},
        "k_mod_snow": {"value": 0.9, "status": "standard",
            "source": "EN 1995-1-1 Table 3.1, service class 2, short-term action (snow, below 1000 m altitude)."},
        "k_h": {"value": "min((150 / depth_mm) ** 0.2, 1.3) for depth < 150 mm, else 1.0", "status": "standard",
            "source": "EN 1995-1-1 eq. 3.1: size factor, solid timber."},
        "k_sys": {"value": 1.1, "status": "standard",
            "source": "EN 1995-1-1 6.6: load sharing, joists and rafters at 610 mm or closer under a deck.",
            "note": "Not applied to headers (a single beam)."},
    },
    "us": {
        "C_D_permanent": {"value": 0.9, "status": "standard",
            "source": "NDS 2018 Table 2.3.2: load duration factor, permanent load."},
        "C_D_floor": {"value": 1.0, "status": "published",
            "source": "Southern Forest Products Association, Maximum Spans (2013 ed.), p. 4: floor and ceiling joist tables use C_D = 1.0."},
        "C_D_snow": {"value": 1.15, "status": "published",
            "source": "Southern Forest Products Association, Maximum Spans (2013 ed.), p. 4: rafters, two-month snow load, C_D = 1.15."},
        "C_r": {"value": 1.15, "status": "published",
            "source": "Southern Forest Products Association, Maximum Spans (2013 ed.), p. 4: repetitive member factor 1.15 for at least three joists or rafters at 24 in. or closer, under a deck.",
            "note": "Not applied to headers (a single beam)."},
        "C_F": {"value": {"2": 1.5, "3": 1.5, "4": 1.5, "5": 1.4, "6": 1.3, "8": 1.2, "10": 1.1, "12": 1.0, "14": 0.9},
            "status": "published",
            "source": "NDS 2018 Supplement Table 4A, size factor for Fb, 2 in. and 3 in. thick, by nominal width (AWC NDS2018 Supplement Chapter 4, via a search excerpt: https://awc.org/wp-content/uploads/2021/10/AWC_NDS2018-Supplement_20200827_AWCWebsite_Chapter4.pdf)."},
        "C_M_C_t_C_L": {"value": 1.0, "status": "assumption",
            "source": "Dry service, normal temperature, members braced by the deck (NDS 2018 Ch. 4).",
            "note": "Wet service factors are not applied; a shed in permanent damp needs them."},
    },
}

WARN_FRACTION = 0.85     # a span above this share of the allowable gets "check"
MAX_FRACTION = 1.0       # above this, "fix"


def _f(region, name):
    return FACTORS[region][name]["value"]


# ================================================================ FORMULAS

def own_weight_kn_m(lib, b_mm, d_mm):
    """Weight of a member in kN per metre of its length."""
    g = lib["grades"][lib["defaults"]["grade"]]
    rho = g.get("density_mean_kg_m3", g["density_kg_m3"])
    return b_mm * d_mm * 1e-6 * rho * _f("common", "g") / 1000.0


def us_size_factor(depth_mm):
    nominal = int(round(depth_mm / 25.4 + 0.5))
    table = {int(k): v for k, v in _f("us", "C_F").items()}
    keys = sorted(table)
    return table[min(max(nominal, keys[0]), keys[-1])]


def allowable_span(lib, b_mm, d_mm, g_kn_m, q_kn_m, load_kind, *, repetitive=True,
                   cos_a=1.0, defl_limit=None, defl_basis="total", add_own_weight=True):
    """Longest horizontal span of a simply supported beam under an even load.

    g_kn_m, q_kn_m: permanent and variable load per metre of horizontal span
    (kN/m = N/mm), not counting the member's own weight (added here unless
    add_own_weight is False). load_kind: 'floor' or 'snow'. cos_a: cosine of the
    slope, for a rafter. defl_basis 'total' limits the deflection under
    permanent + variable load, 'live' under the variable load only.
    Returns {"bending_mm", "deflection_mm", "span_mm", "governs"}.
    """
    region = lib["region"]
    grade = lib["grades"][lib["defaults"]["grade"]]
    defl_limit = defl_limit or _f("common", "deflection_limit")
    if add_own_weight:
        g_kn_m = g_kn_m + own_weight_kn_m(lib, b_mm, d_mm) / cos_a
    W = b_mm * d_mm ** 2 / 6.0
    I = b_mm * d_mm ** 3 / 12.0
    if region == "eu":
        kh = min((150.0 / d_mm) ** 0.2, 1.3) if d_mm < 150 else 1.0
        ksys = _f("eu", "k_sys") if repetitive else 1.0
        fmk, E = grade["bending_mpa"], grade["e_mean_mpa"]
        gG, gQ, gM = _f("eu", "gamma_G"), _f("eu", "gamma_Q"), _f("eu", "gamma_M")
        kq = _f("eu", "k_mod_floor" if load_kind == "floor" else "k_mod_snow")
        combos = [(gG * g_kn_m, _f("eu", "k_mod_permanent")), (gG * g_kn_m + gQ * q_kn_m, kq)]
        caps = [(w, kmod * kh * ksys * fmk / gM) for w, kmod in combos]
    elif region == "us":
        cf = us_size_factor(d_mm)
        cr = _f("us", "C_r") if repetitive else 1.0
        other = _f("us", "C_M_C_t_C_L")
        fb, E = grade["bending_mpa"], grade["e_mean_mpa"]
        cdq = _f("us", "C_D_floor" if load_kind == "floor" else "C_D_snow")
        combos = [(g_kn_m, _f("us", "C_D_permanent")), (g_kn_m + q_kn_m, cdq)]
        caps = [(w, fb * cd * cf * cr * other) for w, cd in combos]
    else:
        raise ValueError(f"no span method for region {region!r}")
    # bending: M = w L^2 / 8 (horizontal span and load per horizontal metre, also for a sloped rafter)
    bend = min(math.sqrt(8.0 * f * W / w) for w, f in caps if w > 0)
    w_def = (g_kn_m + q_kn_m) if defl_basis == "total" else q_kn_m
    ls = (384.0 * E * I / (5.0 * defl_limit * w_def * cos_a ** 2)) ** (1.0 / 3.0)
    defl = ls * cos_a
    span = min(bend, defl)
    return {"bending_mm": bend, "deflection_mm": defl, "span_mm": span,
            "governs": "bending" if bend <= defl else "deflection"}


def level_for(span, allowed):
    if span > allowed * MAX_FRACTION:
        return "fix"
    if span > allowed * WARN_FRACTION:
        return "check"
    return "ok"

# ----- terrace

SPACING_SHARE = 0.8     # the generator keeps terrace spans under this share of the allowable


def terrace_loads(lib, spec):
    """kN/m2 of deck plan: the boards (dead) and the live load."""
    board = lib["sections"][spec["deck_board"]]
    grade = lib["grades"][lib["defaults"]["grade"]]
    rho = grade.get("density_mean_kg_m3", grade["density_kg_m3"])
    dead = board["thickness_mm"] / 1000.0 * rho * _f("common", "g") / 1000.0
    return {"deck_kn_m2": dead, "live_kn_m2": spec["loads"]["floor_kn_m2"]}


def joist_allowed(lib, spec, ld, repetitive=True):
    """Longest span in mm of a terrace deck joist at the described spacing."""
    j = lib["sections"][spec["joist_item"]]
    s = spec["joist_spacing"] / 1000.0
    return allowable_span(lib, j["thickness_mm"], j["width_mm"], ld["deck_kn_m2"] * s, ld["live_kn_m2"] * s,
                          "floor", repetitive=repetitive)["span_mm"]


def beam_allowed(lib, spec, ld, trib_mm, plies=None, item=None, detail=False):
    """Longest span in mm of a terrace beam (its plies together, not a repetitive
    system) carrying a strip of deck `trib_mm` wide, with the joists' own weight."""
    b = lib["sections"][item or spec["beam_item"]]
    j = lib["sections"][spec["joist_item"]]
    t = trib_mm / 1000.0
    joist_dead = own_weight_kn_m(lib, j["thickness_mm"], j["width_mm"]) / (spec["joist_spacing"] / 1000.0)
    res = allowable_span(lib, b["thickness_mm"] * (plies or spec["beam_plies"]), b["width_mm"],
                         (ld["deck_kn_m2"] + joist_dead) * t, ld["live_kn_m2"] * t, "floor", repetitive=False)
    return res if detail else res["span_mm"]


# ----- pergola

def _slat_dead_kn_m2(lib, spec):
    sl = spec.get("slats")
    if not isinstance(sl, dict):
        return 0.0
    it = lib["sections"][sl["item"]]
    return own_weight_kn_m(lib, it["thickness_mm"], it["width_mm"]) / (sl["spacing"] / 1000.0)


def pergola_rafter_span(spec, lib):
    """Centre to centre of the two beams, across them, in mm."""
    bw = spec["beam_plies"] * lib["sections"][spec["beam_item"]]["thickness_mm"]
    across = spec["depth"] if spec["beam_axis"] == "x" else spec["width"]
    return across - 2 * spec["overhang"] - bw


def pergola_rafter_allowed(lib, spec):
    r = lib["sections"][spec["rafter_item"]]
    s = spec["rafter_spacing"] / 1000.0
    return allowable_span(lib, r["thickness_mm"], r["width_mm"], _slat_dead_kn_m2(lib, spec) * s,
                          spec["loads"]["snow_kn_m2"] * s, "snow", repetitive=True)


def pergola_beam_allowed(lib, spec, detail=False):
    """Longest span in mm of a pergola beam between posts, carrying half the rafter span plus the overhang."""
    b = lib["sections"][spec["beam_item"]]
    r = lib["sections"][spec["rafter_item"]]
    t = (pergola_rafter_span(spec, lib) / 2.0 + spec["overhang"]) / 1000.0
    dead = own_weight_kn_m(lib, r["thickness_mm"], r["width_mm"]) / (spec["rafter_spacing"] / 1000.0) + _slat_dead_kn_m2(lib, spec)
    res = allowable_span(lib, b["thickness_mm"] * spec["beam_plies"], b["width_mm"], dead * t,
                         spec["loads"]["snow_kn_m2"] * t, "snow", repetitive=False)
    return res if detail else res["span_mm"]

# ----- summer kitchen

def roof_deck_mm(lib, spec):
    """Thickness of the roof deck sheets in mm; 0 when the roof has none (`roof_deck: "none"`)."""
    return 0.0 if spec["roof_deck"] == "none" else lib["sheets"][spec["roof_deck"]]["thickness_mm"]


def kitchen_roof_dead_kn_m2(lib, spec):
    """Permanent roof load of a summer kitchen in kN per m2 of plan: deck, covering, rafters."""
    cos_a = math.cos(math.radians(spec["pitch_deg"]))
    deck = roof_deck_mm(lib, spec)
    deck_kn = deck / 1000.0 * _f("common", "sheet_density_kg_m3") * _f("common", "g") / 1000.0
    cov = _f("common", "covering_kn_m2").get(spec.get("roofing"), 0.10)
    r = lib["sections"][spec["rafter_item"]]
    rafter = own_weight_kn_m(lib, r["thickness_mm"], r["width_mm"]) / (spec["rafter_spacing"] / 1000.0)
    return (deck_kn + cov + rafter) / cos_a


def kitchen_beam_trib_mm(lib, spec):
    """The width of roof (plan) each roof beam carries: half the span between the beams plus the overhang."""
    bw = spec["beam_plies"] * lib["sections"][spec["beam_item"]]["thickness_mm"]
    pty = lib["sections"][spec["post_item"]]["width_mm"]
    return (spec["depth"] - pty) / 2.0 + spec["overhang"]


def kitchen_beam_allowed(lib, spec, detail=False):
    """Longest span in mm of a summer kitchen's roof beam between posts, under snow and the roof's weight."""
    b = lib["sections"][spec["beam_item"]]
    t = kitchen_beam_trib_mm(lib, spec) / 1000.0
    res = allowable_span(lib, b["thickness_mm"] * spec["beam_plies"], b["width_mm"],
                         kitchen_roof_dead_kn_m2(lib, spec) * t, spec["loads"]["snow_kn_m2"] * t, "snow", repetitive=False)
    return res if detail else res["span_mm"]


NET_SECTION = 0.7        # share of a tie's section counted in tension (holes, notches and the trimmed top)


def kitchen_thrust(lib, spec, run_mm, ties_x, held_x, beam_ends, tie_item):
    """The sideways push of a gable roof on its two eave beams when the ties are only over the post lines
    (`ties: posts`), as a hand estimate. HAND CALCULATION, NOT ENGINEERING (docs/research/timber-structures.md, T9).

    A rafter pair with a ridge board and no tie on that pair is a three-hinged arch: each eave pushes out with
    H = w a / (2 tan(pitch)) per metre of beam, where w is the roof's load per m2 of plan (the roof's own weight
    and snow, kept apart for the load factors) and a the horizontal run from the eave to the ridge. That line load
    bends each eave beam sideways between the tie lines (simply supported, the beam's two plies as one section,
    its depth for this direction the plies' total width), and each tie carries the push of its share of both
    beams as a tension T = p x (half the gap to either neighbouring line).

    ties_x: x of every tie line; held_x: x of anything else that holds a beam sideways (a walled end);
    beam_ends: (x0, x1) of the beam. Returns a dict: `p_g`, `p_q` (kN/m), the longest beam span between lines
    `span_mm` and what the beam allows `allowed_mm` (with `governs`), the worst tie's tension `T_kn`, what it
    resists `T_cap_kn` and the load per rafter pair `pair_kn` (at the rafters' spacing)."""
    a = run_mm / 1000.0
    tan_a = math.tan(math.radians(spec["pitch_deg"]))
    g = kitchen_roof_dead_kn_m2(lib, spec) * a / (2.0 * tan_a)
    q = spec["loads"]["snow_kn_m2"] * a / (2.0 * tan_a)
    sup = sorted(set(round(x, 1) for x in list(ties_x) + list(held_x)))
    x0, x1 = beam_ends
    gaps = [b - a_ for a_, b in zip(sup, sup[1:])] + [2.0 * (sup[0] - x0), 2.0 * (x1 - sup[-1])]
    span = max(gaps)
    b = lib["sections"][spec["beam_item"]]
    res = allowable_span(lib, b["width_mm"], spec["beam_plies"] * b["thickness_mm"], g, q, "snow", repetitive=False,
                         add_own_weight=False)
    # each line's share: from the middle of the gap on one side to the middle of the gap on the other
    mids = [x0] + [(u + v) / 2.0 for u, v in zip(sup, sup[1:])] + [x1]
    trib = {u: (mids[i + 1] - mids[i]) / 1000.0 for i, u in enumerate(sup)}
    tie_trib = max((trib[round(u, 1)] for u in ties_x), default=0.0)
    t = lib["sections"][tie_item]
    area = t["thickness_mm"] * t["width_mm"] * NET_SECTION
    grade = lib["grades"][lib["defaults"]["grade"]]
    ft = grade["tension_mpa"]
    if lib["region"] == "eu":
        kh = min((150.0 / t["width_mm"]) ** 0.2, 1.3) if t["width_mm"] < 150 else 1.0
        gG, gQ, gM = _f("eu", "gamma_G"), _f("eu", "gamma_Q"), _f("eu", "gamma_M")
        combos = [(gG * g, _f("eu", "k_mod_permanent")), (gG * g + gQ * q, _f("eu", "k_mod_snow"))]
        use = max(w * tie_trib / (km * kh * ft / gM * area / 1000.0) for w, km in combos)
        cap = (_f("eu", "k_mod_snow") * kh * ft / gM) * area / 1000.0
        load = (gG * g + gQ * q) * tie_trib
    else:
        combos = [(g, _f("us", "C_D_permanent")), (g + q, _f("us", "C_D_snow"))]
        use = max(w * tie_trib / (ft * cd * area / 1000.0) for w, cd in combos)
        cap = ft * _f("us", "C_D_snow") * area / 1000.0
        load = (g + q) * tie_trib
    s_m = spec["rafter_spacing"] / 1000.0
    return {"p_g": g, "p_q": q, "span_mm": span, "allowed_mm": res["span_mm"], "governs": res["governs"],
            "T_kn": load, "T_cap_kn": cap, "T_use": use, "tie_trib_m": tie_trib, "pair_kn": (g + q) * s_m}


# ----- sheds (and any roof on walls or beams): joists, rafters, headers

def roof_dead_plan(lib, spec, cos_a, rafter_b, rafter_d, spacing_mm):
    """Permanent roof load in kN per m2 of plan: deck, covering and the rafters."""
    deck = roof_deck_mm(lib, spec)
    dens = _f("common", "sheet_density_kg_m3")
    deck_kn = deck / 1000.0 * dens * _f("common", "g") / 1000.0
    cov = _f("common", "covering_kn_m2").get(spec.get("roofing"), 0.10)
    rafter = own_weight_kn_m(lib, rafter_b, rafter_d) / (spacing_mm / 1000.0)
    return (deck_kn + cov + rafter) / cos_a


def floor_joist_allowed(lib, spec, item, spacing_mm, repetitive=True):
    """Longest span in mm of a shed's floor joist of section `item` at `spacing_mm` under the floor deck
    and the floor load (the result of allowable_span)."""
    j = lib["sections"][item]
    s = spacing_mm / 1000.0
    deck = lib["sheets"][spec["floor_deck"]]["thickness_mm"]
    deck_kn = deck / 1000.0 * _f("common", "sheet_density_kg_m3") * _f("common", "g") / 1000.0
    qf = spec["loads"]["floor_kn_m2"]
    return allowable_span(lib, j["thickness_mm"], j["width_mm"], deck_kn * s, qf * s, "floor", repetitive=repetitive)


def shed_rafter_allowed(lib, spec, item, spacing_mm, cos_a, repetitive=True):
    """Longest horizontal span in mm of a roof rafter of section `item` at `spacing_mm` under the roof deck,
    covering and snow, on a slope with cosine `cos_a` (the result of allowable_span)."""
    r = lib["sections"][item]
    b, d = r["thickness_mm"], r["width_mm"]
    s = spacing_mm / 1000.0
    dead = roof_dead_plan(lib, spec, cos_a, b, d, spacing_mm)
    # the rafter's own weight is already in `dead` (per plan area), so do not add it again
    return allowable_span(lib, b, d, (dead - own_weight_kn_m(lib, b, d) / s / cos_a) * s, spec["loads"]["snow_kn_m2"] * s,
                          "snow", repetitive=repetitive, cos_a=cos_a)


def header_trib_mm(spec, wall, rafter_spacing_mm):
    """The width of roof (plan) a wall's header carries."""
    rspan = spec["depth"] - 100.0
    return (rspan / 2.0 + spec["overhang"]) if wall in ("front", "back") else rafter_spacing_mm / 2.0


def header_allowed(lib, spec, item, plies, wall, cos_a, rafter_item, rafter_spacing_mm):
    """Longest span in mm of a header (`plies` of section `item` together) over an opening in `wall`."""
    r = lib["sections"][rafter_item]
    dead = roof_dead_plan(lib, spec, cos_a, r["thickness_mm"], r["width_mm"], rafter_spacing_mm)
    t = header_trib_mm(spec, wall, rafter_spacing_mm) / 1000.0
    h = lib["sections"][item]
    return allowable_span(lib, h["thickness_mm"] * plies, h["width_mm"], dead * t, spec["loads"]["snow_kn_m2"] * t,
                          "snow", repetitive=False, cos_a=1.0)


def length_text(mm, units):
    """A length in the frame's units: metres or millimetres, or feet and inches."""
    if units == "imperial":
        import timberlib as tl
        return tl.fmt_length(mm, "imperial")
    return f"{mm / 1000.0:.2f} m" if abs(mm) >= 1000 else f"{mm:.0f} mm"
