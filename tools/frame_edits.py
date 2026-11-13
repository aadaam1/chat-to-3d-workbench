"""Edits by piece: one-off changes to a generated frame, recorded in the shed
description so they survive every rebuild.

The rules in tools/frame.py place every member. A comment on one piece that
is not worth a rule ("move this stud 100 mm left", "drop this block", "add a
stud here for a shelf") becomes an entry in the description's `edits` list,
applied after the rules, in order:

    {"op": "move",   "id": "wall-front/stud-02", "by": [-100, 0, 0]}
    {"op": "resize", "id": "roof/eave-front-02", "length": 400, "keep": "centre"}
    {"op": "remove", "id": "floor/blocking-03"}
    {"op": "add",    "member": {"id": "edit/shelf-stud", "kind": "stud", "group": "wall-back",
                                "layer": "walls", "item": "50x100", "size": [1682, 100, 50],
                                "origin": [1525, 2400, 218], "x": [0, 0, 1], "y": [0, 1, 0]}}

Any edit may carry a "note" (the comment it came from). Lengths are in mm.
An edit naming a piece the rules no longer make is an error naming the edit,
so a rule change that renames pieces is noticed, not silently skipped.
Joints follow contact: a removed member's joints go; a moved, resized or
added member keeps the joints it still touches and gets one for every new
contact, typed by the two members' kinds.
"""
import numpy as np

OPS = ("move", "resize", "remove", "add")
KEEPS = ("start", "centre", "end")
CONTACT = 1.0           # mm: members this close count as touching
TIMBER = {"joist", "rim", "plate", "stud", "header", "trimmer", "king", "jack", "cripple",
          "sill", "rafter", "blocking", "brace", "outrigger", "fascia", "bargeboard", "ridge", "tie", "post", "beam", "slat"}
KINDS = TIMBER | {"board", "sheet"}
LAYERS = ("floor", "walls", "roof", "sheathing", "cladding")
GROUPS = ("floor", "wall-front", "wall-back", "wall-left", "wall-right", "roof")
UPRIGHT = {"stud", "king", "jack", "cripple", "trimmer"}
CARRIER = {"plate", "sill", "header"}


class EditError(ValueError):
    pass


def _vec(v, n, where):
    if (not isinstance(v, list) or len(v) != n
            or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)):
        raise EditError(f"{where}: must be a list of {n} numbers (mm)")
    return [float(x) for x in v]


def validate(raw, item_ok):
    """The edits list from a description, checked for shape (not against a
    frame yet). item_ok(key) says whether a library item exists."""
    if not isinstance(raw, list):
        raise EditError("edits: must be a list")
    out = []
    for i, e in enumerate(raw):
        w = f"edits[{i}]"
        if not isinstance(e, dict) or e.get("op") not in OPS:
            raise EditError(f"{w}: needs \"op\", one of {', '.join(OPS)}")
        op = e["op"]
        allowed = {"op", "note"} | {"move": {"id", "by"}, "resize": {"id", "size", "length", "keep"},
                                    "remove": {"id"}, "add": {"member"}}[op]
        extra = sorted(set(e) - allowed)
        if extra:
            raise EditError(f"{w}: unknown field {extra[0]!r} for {op} (known: {', '.join(sorted(allowed))})")
        d = {"op": op}
        if "note" in e:
            if not isinstance(e["note"], str):
                raise EditError(f"{w}.note: must be text")
            d["note"] = e["note"]
        if op != "add":
            if not isinstance(e.get("id"), str) or not e["id"]:
                raise EditError(f"{w}.id: the id of the piece, as the preview shows it")
            d["id"] = e["id"]
        if op == "move":
            d["by"] = _vec(e.get("by"), 3, f"{w}.by")
        elif op == "resize":
            if ("size" in e) == ("length" in e):
                raise EditError(f"{w}: give either \"size\" [length, width, thickness] or \"length\"")
            if "size" in e:
                d["size"] = _vec(e["size"], 3, f"{w}.size")
            else:
                d["length"] = _vec([e["length"]], 1, f"{w}.length")[0]
            vals = d.get("size") or [d["length"]]
            if not all(v > 0 for v in vals):
                raise EditError(f"{w}: sizes must be greater than 0")
            k = e.get("keep", "start")
            if k not in KEEPS:
                raise EditError(f"{w}.keep: one of {', '.join(KEEPS)}, not {k!r}")
            d["keep"] = k
        elif op == "add":
            d["member"] = _member(e.get("member"), f"{w}.member", item_ok)
        out.append(d)
    return out


def _member(m, w, item_ok):
    if not isinstance(m, dict):
        raise EditError(f"{w}: a member: id, kind, group, layer, item, size, origin, x, y")
    for k in ("id", "kind", "group", "layer", "item", "size", "origin", "x", "y"):
        if k not in m:
            raise EditError(f"{w}.{k}: required")
    extra = sorted(set(m) - {"id", "kind", "group", "layer", "item", "size", "origin", "x", "y",
                             "variant", "treated", "cut_deg"})
    if extra:
        raise EditError(f"{w}: unknown field {extra[0]!r}")
    if not isinstance(m["id"], str) or not m["id"].startswith("edit/") or len(m["id"]) <= 5:
        raise EditError(f"{w}.id: an added piece's id starts with \"edit/\" (for example \"edit/shelf-stud\")")
    for k, allowed in (("kind", KINDS), ("group", GROUPS), ("layer", LAYERS)):
        if m[k] not in allowed:
            raise EditError(f"{w}.{k}: one of {', '.join(sorted(allowed))}, not {m[k]!r}")
    if not isinstance(m["item"], str) or not item_ok(m["item"]):
        raise EditError(f"{w}.item: {m['item']!r} is not in the library")
    size = _vec(m["size"], 3, f"{w}.size")
    if not all(v > 0 for v in size):
        raise EditError(f"{w}.size: must be greater than 0")
    x, y = np.array(_vec(m["x"], 3, f"{w}.x")), np.array(_vec(m["y"], 3, f"{w}.y"))
    if abs(np.linalg.norm(x) - 1) > 1e-3 or abs(np.linalg.norm(y) - 1) > 1e-3 or abs(x @ y) > 1e-3:
        raise EditError(f"{w}: x and y must be unit vectors at right angles")
    tr = m.get("treated", False)
    if not isinstance(tr, bool):
        raise EditError(f"{w}.treated: true or false")
    return {"id": m["id"], "kind": m["kind"], "group": m["group"], "layer": m["layer"],
            "item": m["item"], "variant": str(m.get("variant", "impregnated" if tr else "sawn")),
            "treated": tr, "size": size, "origin": _vec(m["origin"], 3, f"{w}.origin"),
            "x": [float(v) for v in x], "y": [float(v) for v in y],
            "cut_deg": _vec(m.get("cut_deg", [0, 0]), 2, f"{w}.cut_deg"), "outline": None}


# ------------------------------------------------------------- geometry

def _axes(m):
    x, y = np.array(m["x"], float), np.array(m["y"], float)
    return x, y, np.cross(x, y)


def _shape(m):
    L, W, _ = m["size"]
    return m.get("outline") or [(0, 0), (L, 0), (L, W), (0, W)]


def _corners(m):
    x, y, z = _axes(m)
    o = np.array(m["origin"], float)
    T = m["size"][2]
    return np.array([o + a * x + b * y + c * z for a, b in _shape(m) for c in (0, T)])


def _sat(m):
    x, y, z = _axes(m)
    ol = _shape(m)
    normals, edges = [z], [z]
    for (a0, b0), (a1, b1) in zip(ol, list(ol[1:]) + [ol[0]]):
        e = (a1 - a0) * x + (b1 - b0) * y
        n = np.linalg.norm(e)
        if n > 1e-9:
            edges.append(e / n)
            normals.append(np.cross(e / n, z))
    return normals, edges


def contact(a, b, tol=CONTACT):
    """None when two members are apart; else the overlap of their boxes as
    (lo, hi), for sizing the joint. Separating axis test on their prisms."""
    ca, cb = _corners(a), _corners(b)
    lo, hi = np.maximum(ca.min(0), cb.min(0)), np.minimum(ca.max(0), cb.max(0))
    if np.any(hi - lo < -tol):
        return None
    na, ea = _sat(a)
    nb, eb = _sat(b)
    axs = na + nb
    for u in ea:
        for v in eb:
            n = np.cross(u, v)
            if np.linalg.norm(n) > 1e-6:
                axs.append(n / np.linalg.norm(n))
    for n in axs:
        pa, pb = ca @ n, cb @ n
        if min(pa.max(), pb.max()) - max(pa.min(), pb.min()) < -tol:
            return None
    return lo, hi


def joint_for(a, b, box):
    """The joint between two touching members, or None when they aren't
    fastened to each other (two sheets, two boards)."""
    ka, kb = a["kind"], b["kind"]
    span = float(max(np.max(box[1] - box[0]), 0.0))
    for s, t in ((a, b), (b, a)):
        ks, kt = s["kind"], t["kind"]
        if ks == "post-base" and kt in TIMBER:
            return {"type": "post-base", "a": s["id"], "b": t["id"]}
        if ks == "deckboard" and kt in TIMBER:
            return {"type": "deck-board", "a": s["id"], "b": t["id"], "crossings": 1}
        if ks == "sheet" and kt in TIMBER:
            return {"type": "sheet-frame", "a": s["id"], "b": t["id"], "edge_mm": round(span, 1)}
        if ks == "board" and kt in TIMBER:
            return {"type": "board-frame", "a": s["id"], "b": t["id"], "crossings": 1}
    if ka not in TIMBER or kb not in TIMBER:
        return None
    for s, t in ((a, b), (b, a)):
        ks, kt = s["kind"], t["kind"]
        if ks == "brace" and kt == "post":
            return {"type": "brace-post", "a": s["id"], "b": t["id"]}
        if ks == "brace" and kt == "beam":
            return {"type": "brace-beam", "a": s["id"], "b": t["id"]}
        if ks == "rafter" and kt == "beam":
            return {"type": "rafter-beam", "a": s["id"], "b": t["id"]}
        if ks == "slat" and kt == "rafter":
            return {"type": "slat-rafter", "a": s["id"], "b": t["id"], "crossings": 1}
        if ks == "joist" and kt == "beam":
            return {"type": "joist-beam", "a": s["id"], "b": t["id"]}
        if ks == "beam" and kt == "post":
            return {"type": "beam-post", "a": s["id"], "b": t["id"]}
        if ks == "beam" and kt == "beam":
            return {"type": "beam-ply", "a": s["id"], "b": t["id"], "edge_mm": round(span, 1)}
        if ks in UPRIGHT and kt in CARRIER:
            return {"type": "stud-plate", "a": s["id"], "b": t["id"]}
        if ks in ("joist", "blocking") and kt in ("rim", "joist"):
            return {"type": "joist-rim", "a": s["id"], "b": t["id"]}
        if ks == "rafter" and kt == "plate":
            return {"type": "rafter-plate", "a": s["id"], "b": t["id"]}
        if ks == "rafter" and kt == "ridge":
            return {"type": "rafter-ridge", "a": s["id"], "b": t["id"]}
        if ks == "tie" and kt == "rafter":
            return {"type": "tie-rafter", "a": s["id"], "b": t["id"]}
        if ks == "tie" and kt == "plate":
            return {"type": "tie-plate", "a": s["id"], "b": t["id"]}
        if ks in ("blocking", "outrigger") and kt == "rafter":
            return {"type": "blocking-rafter", "a": s["id"], "b": t["id"]}
        if ks in ("fascia", "bargeboard"):
            return {"type": "fascia-rafter", "a": s["id"], "b": t["id"]}
    return {"type": "plate-plate", "a": a["id"], "b": b["id"]}


# ---------------------------------------------------------------- apply

def apply(members, joints, edits):
    """Apply edits to a generated frame's members and joints (lists, changed
    in place). Raises EditError naming the edit that cannot be applied."""
    by = {m["id"]: m for m in members}
    for i, e in enumerate(edits):
        w = f"edits[{i}]"
        op = e["op"]
        if op != "add" and e["id"] not in by:
            raise EditError(f"{w}: no piece {e['id']!r} in this frame (a rule change may have "
                            f"renamed or removed it); find the piece again in the preview and update the edit")
        if op == "remove":
            m = by.pop(e["id"])
            members.remove(m)
            joints[:] = [j for j in joints if e["id"] not in (j["a"], j["b"])]
            continue
        if op == "add":
            m = dict(e["member"])
            if m["id"] in by:
                raise EditError(f"{w}.member.id: {m['id']!r} is already a piece")
            members.append(m)
            by[m["id"]] = m
        elif op == "move":
            m = by[e["id"]]
            m["origin"] = [round(o + d, 1) for o, d in zip(m["origin"], e["by"])]
        else:
            m = by[e["id"]]
            if m.get("outline"):
                raise EditError(f"{w}: {e['id']!r} is a cut piece (it has an outline) and can't be "
                                f"resized; remove it and add a new piece instead")
            old = list(m["size"])
            new = list(e["size"]) if "size" in e else [e["length"]] + old[1:]
            f = {"start": 0.0, "centre": 0.5, "end": 1.0}[e["keep"]]
            x, y, z = _axes(m)
            shift = sum(f * (o - n) * ax for o, n, ax in zip(old, new, (x, y, z)))
            m["origin"] = [round(float(v), 1) for v in np.array(m["origin"]) + shift]
            m["size"] = [round(v, 1) for v in new]
        _rejoin(m, members, joints)
    return members, joints


def _rejoin(m, members, joints):
    """Joints of m follow contact: keep those it still touches, add new ones."""
    mid = m["id"]
    keep, have = [], set()
    by = {x["id"]: x for x in members}
    for j in joints:
        if mid in (j["a"], j["b"]):
            other = by[j["b"] if j["a"] == mid else j["a"]]
            if contact(m, other) is None:
                continue
            have.add(other["id"])
        keep.append(j)
    joints[:] = keep
    for o in members:
        if o["id"] == mid or o["id"] in have:
            continue
        box = contact(m, o)
        if box is not None:
            j = joint_for(m, o, box)
            if j:
                joints.append(j)
