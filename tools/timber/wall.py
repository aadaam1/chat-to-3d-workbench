"""A wall: its framing (plates, studs, openings with king and jack studs, header,
sill and cripples, corner pieces, infill up to the roof line it is given), then
its skin (sheathing and cladding cut to the outline under that line). The
rules for where pieces go are in tools/framing.py."""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import framing as fr_rules  # noqa: E402
import frame_edits as fe  # noqa: E402
from timber.store import (EPS, MIN_CRIPPLE, MIN_INFILL, MIN_SHEET, SpecError, _clean, _is_rect,  # noqa: E402
                          _ov, _pairs, _piece, _poly_clip, _poly_len, _norm, layout, split)

fr = fr_rules


class Wall:
    """One wall of the shed, `name` front, back, left or right, built to the
    roof line `line` (a RoofLine: its `underside(y)` is the height the side
    walls' infill studs rise to). After `build_frame` it exposes `top_id` and
    `bear_id` (the lower top plate and the one the roof bears on), `bots` (bottom
    plates), `ends`, `zs` (stud range), `ops` (the openings, with their ranges
    and heights), `studs`, `infill`, `trims`, `cripples`, `headers`, `sills`.
    `skin(aabbs)` then adds sheathing and cladding. `wall["key"]` reads the same
    values the wall frame dict holds."""

    def __init__(self, frame, lay, name, line):
        self.fr, self.name, self.line, self.lay = frame, name, line, lay
        self.gable = lay.gable
        self.s, self.W, self.D = lay.s, lay.W, lay.D
        self.t, self.w, self.zd = lay.t, lay.w, lay.zd
        self.hf, self.hb = lay.hf, lay.hb
        self.courses, self.th, self.hh, self.plies = lay.courses, lay.th, lay.hh, lay.plies
        self.sheath, self.clad, self.ts, self.tc = lay.sheath, lay.clad, lay.ts, lay.tc
        self.box, self.add, self.joint = frame.box, frame.add, frame.joint
        self.wf = None
        self.skin_sheets = {}
        self.group = self.gid = f"wall-{name}"     # the members' group, and the prefix of their ids
        self.through = name in ("front", "back")   # runs through to the corners (corner assemblies at its ends)
        self.tall_rows = False                     # a sloped top taller than a sheet is sheathed in two rows, as a gable end is

    def __getitem__(self, key):
        return self.wf[key]

    top_id = property(lambda self: self.wf["top_id"])
    bear_id = property(lambda self: self.wf["bear_id"])
    bots = property(lambda self: self.wf["bots"])
    ends = property(lambda self: self.wf["ends"])
    zs = property(lambda self: self.wf["zs"])
    ops = property(lambda self: self.wf["ops"])
    infill = property(lambda self: self.wf["infill"])

    def build(self):
        self.wf = self.build_frame()
        s = self.s
        self.fr.assembly(self.gid, "wall", [
            {"role": "wall studs", "kind": "stud", "spacing_mm": _norm(s["stud_spacing"]),
             "deck": s["sheathing"], "deck_role": "wall", "deck_group": self.group}])
        return self.wf

    def skin(self, aabbs):
        """Sheathing and cladding on the outer face, cut to the wall's outline."""
        self.aabbs = aabbs
        self._skin(self.name)

    def wall_frame(self, name):
        """Placement of a wall panel: its range along the wall, which world axis
        that is, and how wall coordinates (s along the wall, d inward from the
        outer face, z) turn into world coordinates."""
        W, D, w = self.W, self.D, self.w
        if name == "front":
            return dict(s0=0.0, s1=W, ax=0, dax=1, sign=-1, d0=0.0, top=self.hf)
        if name == "back":
            return dict(s0=0.0, s1=W, ax=0, dax=1, sign=1, d0=D, top=self.hb)
        if name == "left":
            return dict(s0=w, s1=D - w, ax=1, dax=0, sign=-1, d0=0.0, top=self.hb)
        return dict(s0=w, s1=D - w, ax=1, dax=0, sign=1, d0=W, top=self.hb)

    def wbox(self, wf, mid, kind, group, layer, item, s, d, z, laxis, waxis, **kw):
        """A member from wall coordinates; laxis and waxis are 's', 'd' or 'z'."""
        lo, hi = [0.0] * 3, [0.0] * 3
        lo[wf["ax"]], hi[wf["ax"]] = s
        # the outer face is at d0; inward is -sign
        p, q = wf["d0"] - wf["sign"] * d[0], wf["d0"] - wf["sign"] * d[1]
        lo[wf["dax"]], hi[wf["dax"]] = min(p, q), max(p, q)
        lo[2], hi[2] = z
        amap = {"s": wf["ax"], "d": wf["dax"], "z": 2}
        return self.box(mid, kind, group, layer, item, lo, hi, amap[laxis], amap[waxis], **kw)
    def build_frame(self):
        """One wall panel, framed the way a carpenter would (framing.py has the
        rules): bottom plate, one or two top plates, studs on the layout, a
        corner assembly at each end of the front and back walls, and at every
        opening a king stud and a jack stud each side, a header resting on the
        jacks, a sill on cripples for a window, and cripples above the header."""
        name = self.name
        s, t, w = self.s, self.t, self.w
        wf = self.wall_frame(name)
        wf["name"] = name
        g, ig = self.group, self.gid
        fi = s["frame_item"]
        S0, S1 = wf["s0"], wf["s1"]
        zb, ztop = self.zd, wf["top"]
        nc = self.courses
        through = self.through
        if ztop - (nc + 1) * t - self.zd <= 0:
            raise SpecError(f"{self.lay.height_field(name)}: too low for the "
                            f"floor and the wall plates (floor top is {self.zd:g} mm)")
        ext = fr.corner_extent(s["corner"], t, w) if through else t
        wf["corner_end"] = (S0 + ext, S1 - ext)
        ops = self._wall_openings(name, wf)

        # bottom plate, cut at every door
        pieces, cur = [], S0
        for o in (o for o in ops if o["kind"] == "door"):
            if o["a"] - cur > EPS:
                pieces.append((cur, o["a"]))
            cur = o["b"]
        if S1 - cur > EPS:
            pieces.append((cur, S1))
        bots = []
        for i, (a, b) in enumerate(pieces, 1):
            mid = f"{ig}/plate-bottom" if len(pieces) == 1 else f"{ig}/plate-bottom-{i:02d}"
            bots.append((self.wbox(wf, mid, "plate", g, "walls", fi, (a, b), (0, w), (zb, zb + t), "s", "d"), a, b))
        # top plates: the lower one follows the panel; a second one on top is lapped
        # over the back corners (the side walls' upper plates run over the back wall)
        top = self.wbox(wf, f"{ig}/plate-top", "plate", g, "walls", fi, (S0, S1), (0, w),
                        (ztop - nc * t, ztop - (nc - 1) * t), "s", "d")
        bear = top
        if nc == 2:
            u0, u1 = self.upper_span(name, S0, S1)
            bear = self.wbox(wf, f"{ig}/plate-top-2", "plate", g, "walls", fi, (u0, u1), (0, w),
                             (ztop - t, ztop), "s", "d")
            self.joint("plate-lap", bear, top, edge_mm=min(u1, S1) - max(u0, S0))
        zs0, zs1 = zb + t, ztop - nc * t        # studs run between the plates
        wf.update(bots=bots, top_id=top, bear_id=bear, zs=(zs0, zs1), ops=ops, studs=[], trims=[],
                  cripples=[], headers=[], sills=[], infill=[], ends={})

        def plate_for(a, b):
            for mid, p0, p1 in bots:
                if p0 - EPS <= a and b <= p1 + EPS:
                    return mid
            raise AssertionError(f"no bottom plate under {a}..{b} in {g}")

        def stud(mid, kind, a, b, z0, z1, d=(0, w), laxis="z", waxis="d", cut=(0, 0)):
            return self.wbox(wf, mid, kind, g, "walls", fi, (a, b), d, (z0, z1), laxis, waxis, cut=cut)

        # openings
        busy = []                               # ranges along the wall no layout stud may take
        for i, o in enumerate(ops, 1):
            a, b, zt = o["a"], o["b"], o["zt"]
            kl = stud(f"{ig}/king-{2 * i - 1:02d}", "king", a - 2 * t, a - t, zs0, zs1)
            kr = stud(f"{ig}/king-{2 * i:02d}", "king", b + t, b + 2 * t, zs0, zs1)
            jl = stud(f"{ig}/jack-{2 * i - 1:02d}", "jack", a - t, a, zs0, zt)
            jr = stud(f"{ig}/jack-{2 * i:02d}", "jack", b, b + t, zs0, zt)
            for k_, (x0, x1) in ((kl, (a - 2 * t, a - t)), (kr, (b + t, b + 2 * t))):
                self.joint("stud-plate", k_, plate_for(x0, x1))
                self.joint("stud-plate", k_, top)
                wf["trims"].append((k_, x0, x1))
            for j_, k_, (x0, x1) in ((jl, kl, (a - t, a)), (jr, kr, (b, b + t))):
                self.joint("stud-plate", j_, plate_for(x0, x1))
                self.joint("king-jack", j_, k_, edge_mm=zt - zs0)
            # the header: one or two plies on edge, across the opening and the jacks
            hds = []
            for ply, (d0, d1) in enumerate(fr.header_plies(self.plies, self.th, w), 1):
                hid = f"{ig}/header-{i:02d}" + ("" if ply == 1 else f"-ply{ply}")
                self.wbox(wf, hid, "header", g, "walls", s["header_item"],
                          (a - t, b + t), (d0, d1), (zt, zt + self.hh), "s", "z")
                hds.append(hid)
                for j_ in (jl, jr):
                    self.joint("jack-header", hid, j_)
                for k_ in (kl, kr):
                    self.joint("header-trimmer", hid, k_)
            for h2 in hds[1:]:
                self.joint("plate-lap", h2, hds[0], edge_mm=b - a + 2 * t)
            wf["headers"].append((hds[0], a - t, b + t, zt, zt + self.hh))
            o["header"], o["trims"] = hds[0], (kl, kr)
            busy.append((a - 2 * t, b + 2 * t))
            # cripples above the header, on the stud layout
            above = (zt + self.hh, zs1)
            if above[1] - above[0] >= MIN_CRIPPLE:
                o["cripples_above"] = above
            if o["kind"] == "window":
                sl = self.wbox(wf, f"{ig}/sill-{i:02d}", "sill", g, "walls", fi,
                               (a, b), (0, w), (o["zb"] - t, o["zb"]), "s", "d")
                wf["sills"].append((sl, a, b, o["zb"] - t, o["zb"]))
                self.joint("header-trimmer", sl, jl)
                self.joint("header-trimmer", sl, jr)
                o["sill_id"] = sl

        # corner assemblies at both ends of the front and back walls
        if through:
            for end, (c0, c1) in (("01", (S0, S0 + ext)), ("02", (S1 - ext, S1))):
                busy.append((c0 + t, c1) if end == "01" else (c0, c1 - t))
                for piece in fr.corner_pieces(s["corner"], t, w, c0, c1, end == "01", zs0, zs1):
                    mid = f"{ig}/corner-{end}-{piece['name']}"
                    self.wbox(wf, mid, piece["kind"], g, "walls", fi, piece["s"], piece["d"], piece["z"],
                              piece["laxis"], piece["waxis"])
                    self.joint("stud-plate", mid, plate_for(*piece["s"])) if piece["kind"] == "stud" else None
                    if piece["kind"] == "stud":
                        self.joint("stud-plate", mid, top)
                    wf["ends"].setdefault(end, []).append(mid)

        # studs on the regular layout
        pos = [S0 + p for p in layout(S1 - S0, t, s["stud_spacing"])]
        n_st = 0
        for p in pos:
            if any(_ov(p, p + t, x0, x1) > EPS for x0, x1 in busy):
                continue
            n_st += 1
            sid = stud(f"{ig}/stud-{n_st:02d}", "stud", p, p + t, zs0, zs1)
            wf["studs"].append((sid, p, p + t, zs0, zs1))
            self.joint("stud-plate", sid, plate_for(p, p + t))
            self.joint("stud-plate", sid, top)
            if abs(p - S0) < EPS:
                wf["ends"]["first"] = sid
            if abs(p + t - S1) < EPS:
                wf["ends"]["last"] = sid

        # cripples above every header and below every sill, evenly spaced and
        # symmetric across the opening, one at each end next to the jacks
        crip = []
        for o in ops:
            xs = fr.even_cripples(o["a"], o["b"], t, s["stud_spacing"])
            if "cripples_above" in o:
                for p in xs:
                    crip.append((p, o["cripples_above"], o["header"], top))
            if o["kind"] == "window":
                below = (zs0, o["zb"] - t)
                if below[1] - below[0] >= MIN_CRIPPLE:
                    for p in xs:
                        crip.append((p, below, plate_for(p, p + t), o["sill_id"]))
        crip.sort(key=lambda c: (c[0], c[1][0]))
        for n_cr, (p, (z0, z1), lower, upper) in enumerate(crip, 1):
            cid = stud(f"{ig}/cripple-{n_cr:02d}", "cripple", p, p + t, z0, z1)
            wf["cripples"].append((cid, p, p + t, z0, z1))
            self.joint("stud-plate", cid, lower)
            self.joint("stud-plate", cid, upper)

        # side walls: infill studs above the top plate up to the rafter line, on the
        # stud layout and over every king stud (a sheathing seam lands on each, and
        # needs timber behind it all the way up)
        if name in ("left", "right"):
            spans = [(x0, x1) for _, x0, x1 in wf["trims"]]
            todo = [(p, f"infill-{i:02d}", False) for i, p in enumerate(pos, 1)
                    if not any(_ov(p, p + t, x0, x1) > EPS for x0, x1 in spans)]
            todo += [(x0, f"infill-{len(pos) + k:02d}", True) for k, (x0, _) in enumerate(spans, 1)]
            for p, nm, forced in sorted(todo):
                zt = self.line.top_over(p, p + t)     # the long point of the stud's cut top
                if zt - ztop < (1.0 if forced else MIN_INFILL):
                    continue
                if self.gable:
                    iid = self.gable_stud(wf, f"{ig}/{nm}", p, p + t, ztop, zt)
                else:
                    iid = stud(f"{ig}/{nm}", "stud", p, p + t, ztop, zt,
                               cut=(0, self.line.cut_deg(p, p + t)))
                wf["infill"].append((iid, p, p + t, ztop, zt))
                self.joint("stud-plate", iid, bear)
                # the top end is fixed to the end rafter, joined in roof()
        return wf
    def upper_span(self, name, S0, S1):
        """Where the second top plate runs (a hook: a wall between posts has no corner to lap)."""
        return fr.upper_plate_span(name, S0, S1, self.w, self.D)

    def label(self, i):
        """How an opening is named in an error message."""
        return f"openings[{i}]"

    def raise_hint(self, name, need):
        """What to do about a wall too low for an opening, for an error message: `need` is the
        height of the top plate's top that would fit it (a shed's wall height field is named)."""
        if self.lay.s["type"] in ("pent-shed", "gable-shed"):
            return f"set {self.lay.height_field(name)} to at least {math.ceil(need - 1e-9):g}, "
        return "raise the wall, "

    def opening_list(self, name):
        """The openings of this wall as (index, opening): those of the description naming it."""
        return [(i, o) for i, o in enumerate(self.s["openings"]) if o["wall"] == name]

    def strip_limits(self, name, wf):
        """Where the sheathing at the wall's ends stops, along the wall (for the opening's edge strips)."""
        S0, S1 = wf["s0"], wf["s1"]
        return (0.0 if name in ("left", "right") else S0), (self.D if name in ("left", "right") else S1)

    def gable_stud(self, wf, mid, a, b, z0, zt):
        """An infill stud of a gable wall with its top cut to the roof line: laid out
        with its length up, its width along the wall and its outline the cut."""
        t, w = b - a, self.w
        prof = self.line.top_profile(a, b)
        outline = [(0.0, 0.0)] + [(z - z0, y - a) for y, z in prof] + [(0.0, t)]
        L = max(u for u, _ in outline)
        xc = wf["d0"] - wf["sign"] * w / 2
        return self.add(mid, "stud", f"wall-{self.name}", "walls", self.s["frame_item"], [L, t, w],
                        [xc, (a + b) / 2, z0 + L / 2], (0, 0, 1), (0, 1, 0),
                        cut=(0, self.line.cut_deg(a, b)), outline=_clean(outline))

    def _wall_openings(self, name, wf):
        t, w, zd = self.t, self.w, self.zd
        S0, S1 = wf["s0"], wf["s1"]
        ztop = wf["top"]
        ops = []
        for i, o in self.opening_list(name):
            p = self.label(i)
            if o["width"] > S1 - S0 + EPS:
                raise SpecError(f"{p}.width: {o['width']:g} mm is wider than the {name} wall "
                                f"({S1 - S0:g} mm between its corners)")
            a, b = o["x"], o["x"] + o["width"]
            c0, c1 = wf["corner_end"]
            if a - 2 * t < c0 - EPS or b + 2 * t > c1 + EPS:
                raise SpecError(f"{p}.x: the opening ({a:g} to {b:g} mm) must leave room for a king "
                                f"and a jack stud ({t:g} mm each) inside the corner framing of the "
                                f"{name} wall, which leaves {c0:g} to {c1:g} mm")
            zb = zd + o["sill"]
            zt = zb + o["height"]
            under = ztop - self.courses * t
            if zt + self.hh > under + EPS:
                room = under - self.hh - zb
                raise SpecError(f"{p}.height: the header ({self.hh:g} mm deep) would reach the top "
                                f"plate; the most this {o['kind']} can be is {room:g} mm at this "
                                f"position (or {self.raise_hint(name, zt + self.hh + self.courses * t)}"
                                "or use a shallower header_item)")
            if o["kind"] == "window" and o["sill"] < max(2 * t, MIN_SHEET) - EPS:
                raise SpecError(f"{p}.sill: at least {max(2 * t, MIN_SHEET):g} mm (room for the "
                                "sill member, the bottom plate and a sheathing strip)")
            if o["width"] + t < MIN_SHEET - EPS:
                raise SpecError(f"{p}.width: at least {MIN_SHEET - t:g} mm")
            edge_lo, edge_hi = self.strip_limits(name, wf)
            if a - 1.5 * t - edge_lo < MIN_SHEET - EPS or edge_hi - (b + 1.5 * t) < MIN_SHEET - EPS:
                raise SpecError(f"{p}.x: the opening ({a:g} to {b:g} mm) leaves a strip of sheathing "
                                f"narrower than {MIN_SHEET:g} mm at the {name} wall's corner")
            ops.append(dict(o, a=a, b=b, zb=zb, zt=zt, index=i))
        ops.sort(key=lambda o: o["a"])
        for p_, q_ in zip(ops, ops[1:]):
            if q_["a"] - 2 * t < p_["b"] + 2 * t - EPS:
                raise SpecError(f"{self.label(q_['index'])}.x: overlaps {self.label(p_['index'])} "
                                f"(each needs a king and a jack stud, {t:g} mm each, on both sides)")
            if (q_["a"] - 1.5 * t) - (p_["b"] + 1.5 * t) < MIN_SHEET - EPS:
                raise SpecError(f"{self.label(q_['index'])}.x: too close to {self.label(p_['index'])}; "
                                f"the sheathing between them would be under {MIN_SHEET:g} mm wide")
        return ops
    def wall_outline(self, name):
        """What the wall's outer skin covers, as a polygon in (s, z) with s the
        world coordinate along the wall. Front and back are rectangles; the
        side walls follow the rafter line."""
        wf, zd, W, D, w = self.wf, self.zd, self.W, self.D, self.w
        if name in ("front", "back"):
            return [(0.0, zd), (W, zd), (W, wf["top"]), (0.0, wf["top"])]
        if self.gable:
            return self.gable_outline(0.0)
        return _clean([(0.0, zd), (D, zd), (D, self.hb), (D - w, self.hb),
                       (D - w, self.line.underside(D - w)), (w, self.hf), (0.0, self.hf)])
    def gable_outline(self, wrap):
        """The gable wall's skin as a polygon in (y, z): level at the eave height
        out to the faces of the eave walls (and `wrap` beyond them), then up
        the roof line to the ridge board and across its underside."""
        zd, D, he, L = self.zd, self.D, self.hb, self.line
        return _clean([(-wrap, zd), (D + wrap, zd), (D + wrap, he), (D, he),
                       (L.yb, L.slope(L.yb)), (L.yb, L.rb), (L.yf, L.rb), (L.yf, L.slope(L.yf)),
                       (0.0, he), (-wrap, he)])

    def faces(self, name):
        """Members of the wall frames whose outer face lies in this wall's outer
        plane, as (id, kind, s0, s1, z0, z1) with s along the wall."""
        wf = self.wf
        ax = wf["ax"]
        dax, d0, sign = wf["dax"], wf["d0"], wf["sign"]
        out = []
        for m in self.fr.members:
            if not m["group"].startswith("wall-") or m["layer"] != "walls":
                continue
            lo, hi = self.aabbs[m["id"]]
            if abs((lo if sign < 0 else hi)[dax] - d0) > EPS:
                continue
            out.append((m["id"], m["kind"], lo[ax], hi[ax], lo[2], hi[2]))
        return out
    def _skin(self, name):
        s, t, zd = self.s, self.t, self.zd
        wf, g, ig = self.wf, self.group, self.gid
        ts = self.ts
        poly = self.wall_outline(name)
        s_lo, s_hi = min(p[0] for p in poly), max(p[0] for p in poly)
        zmax = max(p[1] for p in poly)
        short, long_ = self.sheath["size_mm"]
        if zmax - zd > long_ + EPS and not self.gable and not self.tall_rows:
            f = self.lay.height_field(name)
            raise SpecError(f"{f}: the {name} wall is {zmax - zd:g} mm above the floor deck, taller "
                            f"than a {long_:g} mm sheet; this version fits one sheet over the height")
        faces = self.faces(name)
        full = [(i, (p + q) / 2) for i, k, p, q, z0, z1 in faces
                if k in ("stud", "king") and z1 - z0 > q - p and z0 <= zd + t + EPS
                and z1 >= wf["zs"][1] - EPS]
        cand = [c for _, c in full]
        pieces = []          # (u0, u1, z_low, notch) ; notch = (a, b, z_top) or None
        cur = s_lo

        def plain(lo, hi):
            c = [x for x in cand if lo - EPS <= x <= hi + EPS]
            for u0, u1 in _pairs(split(lo, hi, c, short, f"{name} wall sheathing")):
                pieces.append((u0, u1, zd, None))

        for o in wf["ops"]:
            lo, hi = o["a"] - 1.5 * t, o["b"] + 1.5 * t       # on the king studs' centres
            if lo - cur > EPS:
                plain(cur, lo)
            tr = [lo, hi]
            above = [(p + q) / 2 for i, k, p, q, z0, z1 in faces
                     if k == "cripple" and o["a"] - t - EPS <= p and q <= o["b"] + t + EPS and z0 >= o["zt"] - EPS]
            label = f"{name} wall sheathing at openings[{o['index']}]"
            if o["kind"] == "door":
                for u0, u1 in _pairs(split(lo, hi, tr + above, short, label)):
                    pieces.append((u0, u1, zd, (o["a"], o["b"], o["zt"])))
            else:
                below = [(p + q) / 2 for i, k, p, q, z0, z1 in faces
                         if k == "cripple" and o["a"] - EPS <= p and q <= o["b"] + EPS and z1 <= o["zb"] + EPS]
                for u0, u1 in _pairs(split(lo, hi, tr + below, short, label)):
                    pieces.append((u0, u1, zd, "cap", o["zb"]))
                for u0, u1 in _pairs(split(lo, hi, tr + above, short, label)):
                    pieces.append((u0, u1, o["zb"], (o["a"], o["b"], o["zt"])))
            cur = hi
        if s_hi - cur > EPS:
            plain(cur, s_hi)

        ax = wf["ax"]
        e_s = [1 if j == ax else 0 for j in range(3)]
        n = 0
        self.skin_sheets = getattr(self, "skin_sheets", {})
        self.skin_sheets[name] = []
        # a gable end taller than a sheet is sheathed in two rows, the seam across the
        # top plates (in the middle of the plate course, so both rows have timber behind)
        two_rows = (self.gable or self.tall_rows) and zmax - zd > long_ + EPS
        zsplit = wf["top"] - self.courses * t / 2
        jobs = []
        for pc in pieces:
            u0, u1, zlow, notch = pc[:4]
            zhi = zmax
            if notch == "cap":                         # the strip under a window
                zhi, notch = pc[4], None
            if two_rows and zhi >= zmax - EPS and zlow < zsplit - EPS:
                jobs += [(u0, u1, zlow, zsplit, notch), (u0, u1, zsplit, zhi, None)]
            else:
                jobs.append((u0, u1, zlow, zhi, notch))
        for u0, u1, zlow, zhi, notch in jobs:
            poly_i = _piece(poly, u0, u1, zlow, zhi, notch)
            if not poly_i:
                continue
            n += 1
            su0, su1 = min(p[0] for p in poly_i), max(p[0] for p in poly_i)
            zlo, zup = min(p[1] for p in poly_i), max(p[1] for p in poly_i)
            if zup - zlo > long_ + EPS:         # a gable end: only the columns near the peak can be this tall
                raise SpecError(f"{self.lay.height_field(name)}: the {name} wall is {zup - zlo:g} mm tall at the "
                                f"{('peak of its gable' if self.gable else 'high end') if two_rows else 'top'}, taller than a {long_:g} mm sheet "
                                f"{'even in two rows ' if two_rows else ''}(this version fits one sheet over a row); lower the eaves or the pitch")
            size = [su1 - su0, zup - zlo, ts]
            local = [(p[0] - su0, p[1] - zlo) for p in poly_i]
            outline = None if _is_rect(local, size[0], size[1]) else local
            cen = [0.0, 0.0, (zlo + zup) / 2]
            cen[ax] = (su0 + su1) / 2
            cen[wf["dax"]] = wf["d0"] + wf["sign"] * ts / 2
            sid = self.add(f"{ig}/sheathing-{n:02d}", "sheet", g, "sheathing", s["sheathing"],
                           size, cen, e_s, (0, 0, 1), outline=outline)
            self.skin_sheets[name].append((sid, su0, su1, zlo, zup, poly_i))
            for mid, k, p, q, z0, z1 in faces:
                if _ov(su0, su1, p, q) <= EPS or _ov(zlo, zup, z0, z1) <= EPS:
                    continue
                length = _poly_len(poly_i, max(su0, p), min(su1, q), z0, z1)
                if length > EPS:
                    self.joint("sheet-frame", sid, mid, edge_mm=length)
        self.cladding(name, wf, faces)

    def cladding(self, name, wf, faces):
        s, ts, tc, zd = self.s, self.ts, self.tc, self.zd
        cw = self.clad["cover_width_mm"]
        ax, dax, sign = wf["ax"], wf["dax"], wf["sign"]
        e_s = [1 if j == ax else 0 for j in range(3)]
        g, ig = self.group, self.gid
        zmax = self.wf["top"] if name in ("front", "back") else self.line.gable_top if self.gable else self.hf
        cuts = [zd + i * cw for i in range(math.ceil((zmax - zd) / cw - 1e-9))] + [zmax]
        if len(cuts) > 2 and zmax - cuts[-2] < 0.4 * cw:     # no sliver at the top: share the last two courses
            cuts[-2] = zmax - (zmax - cuts[-3] + 0) / 2
        if name in ("left", "right") and zd + EPS < self.hb < zmax - EPS and self.hb not in cuts:
            cuts = sorted(set(cuts + [self.hb]))        # the course at the back wall height is split
        vert = [(i, (p + q) / 2, z0, z1) for i, k, p, q, z0, z1 in faces
                if k in ("stud", "king", "jack", "cripple") and z1 - z0 > q - p]
        clip = self.cladding_clip(name)
        n = 0
        for zb, zt in zip(cuts, cuts[1:]):
            if zt - zb < 1.0:
                continue
            lo, hi, cut_hi = self._board_span(name, zb)
            pieces = [(lo, hi, cut_hi)]
            for o in wf["ops"]:
                nxt = []
                for (a, b, ch) in pieces:
                    if zt > o["zb"] + EPS and zb < o["zt"] - EPS and a < o["b"] and b > o["a"]:
                        if o["a"] - a > 1.0:
                            nxt.append((a, o["a"], 0.0))
                        if b - o["b"] > 1.0:
                            nxt.append((o["b"], b, ch))
                    else:
                        nxt.append((a, b, ch))
                pieces = nxt
            for a, b, ch in pieces:
                z0, z1, outline = zb, zt, None
                if clip:                                # cut to the rafter line, not stepped above it
                    poly_i = _poly_clip(clip, a, b, zb, zt)
                    if not poly_i:
                        continue
                    a, b = min(p[0] for p in poly_i), max(p[0] for p in poly_i)
                    z0, z1 = min(p[1] for p in poly_i), max(p[1] for p in poly_i)
                    local = [(p[0] - a, p[1] - z0) for p in poly_i]
                    if not _is_rect(local, b - a, z1 - z0):
                        outline = local
                n += 1
                cen = [0.0, 0.0, (z0 + z1) / 2]
                cen[ax] = (a + b) / 2
                cen[dax] = wf["d0"] + sign * (ts + tc / 2)
                bid = self.add(f"{ig}/board-{n:02d}", "board", g, "cladding", s["cladding"],
                               [b - a, z1 - z0, tc], cen, e_s, (0, 0, 1),
                               cut=(ch if self.gable else 0, ch), outline=outline)
                cr = sum(1 for _, c, z0, z1 in vert if a - EPS <= c <= b + EPS
                         and _ov(zb, zt, z0, z1) > EPS)
                if not cr:                              # a course over the top plate: nailed at the studs
                    cr = max(1, sum(1 for _, c, z0, z1 in vert if a - EPS <= c <= b + EPS))
                self.joint("board-frame", bid, wf["top_id"], crossings=cr)
    def cladding_clip(self, name):
        """The polygon (s, z) the side walls' cladding is cut to: the rafter line, wrapped past the corners."""
        zd = self.zd
        clip = None
        if name in ("left", "right") and self.gable:
            clip = self.gable_outline(self.ts + self.tc)
        elif name in ("left", "right"):
            wrap, D, w = self.ts + self.tc, self.D, self.w
            clip = _clean([(-wrap, zd), (D + wrap, zd), (D + wrap, self.hb), (D - w, self.hb),
                           (D - w, self.line.underside(D - w)), (w, self.hf), (-wrap, self.hf)])
        return clip

    def _board_span(self, name, zb):
        """Range along the wall of a board whose lower edge is at zb, and the
        cut angle at its high end. Side boards wrap past the front and back
        skin; above the back wall they follow the rafter line."""
        wrap = self.ts + self.tc
        if name in ("front", "back"):
            return -self.ts, self.W + self.ts, 0.0
        D, w = self.D, self.w
        if self.gable:              # above the eave height both ends follow the roof line
            above = zb >= self.hb - EPS
            return -wrap, D + wrap, (round(90 - math.degrees(self.line.ang), 1) if above else 0.0)
        if zb < self.hb - EPS:
            return -wrap, D + wrap, 0.0
        if zb <= self.line.underside(D - w) + EPS or self.line.k <= 0:
            return -wrap, D - w, 0.0
        y = w + (self.hf - zb) / self.line.k
        return -wrap, min(y, D - w), round(90 - math.degrees(self.line.ang), 1)

# ------------------------------------------------------- corners between walls

def corners(frame, lay, walls):
    """Joints where the side walls meet the front and back walls (corner
    studs, plate ties and laps); the walls are already built."""
    joint, courses, w, W = frame.joint, lay.courses, lay.w, lay.W

    def face_contact(a, b):
        """True when two members touch over a face (an area), not along an edge."""
        c = fe.contact(frame.member(a), frame.member(b))
        if c is None:
            return False
        lo, hi = c
        return sum(1 for v in (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) if v > 1.0) >= 2

    for sw in ("left", "right"):
        for fw in ("front", "back"):
            a, b = walls[sw], walls[fw]
            joint("plate-plate", a["top_id"], b["top_id"])
            end_b = "01" if sw == "left" else "02"
            end_a = a["ends"].get("first" if fw == "front" else "last")
            post = [m for m in b["ends"].get(end_b, [])]
            main = b["ends"].get("first" if sw == "left" else "last")
            # one line of fixings, into each stud the side wall's end stud
            # meets face to face (not the spacer blocks or an edge contact)
            h = a["zs"][1] - a["zs"][0]
            if not end_a:
                continue
            cands = [m for m in [main] + post if m]
            face = [mid for mid in cands if face_contact(end_a, mid) and frame.member(mid)["kind"] == "stud"]
            for mid in face or cands[:1]:
                joint("corner-stud", end_a, mid, edge_mm=h)
            if courses == 2 and fw == "back":
                joint("plate-lap", a["bear_id"], b["top_id"], edge_mm=w)
            lo, hi = (0.0, w) if sw == "left" else (W - w, W)
            pa = a["bots"][0][0] if fw == "front" else a["bots"][-1][0]
            pb = next(m for m, p0, p1 in b["bots"] if _ov(lo, hi, p0, p1) > EPS)
            joint("plate-plate", pa, pb)
