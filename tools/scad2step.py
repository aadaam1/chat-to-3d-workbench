#!/usr/bin/env python3
"""Turn an OpenSCAD model into a STEP file of real B-rep solids.

    scad2step.py <model.scad> <out.step> [-D NAME=VALUE ...]

OpenSCAD only ever writes meshes. A mesh opened in Fusion or any other CAD
package is a heap of triangles: no cylinder to change the diameter of, no edge
to chamfer. This script asks OpenSCAD for the CSG tree instead (the .csg
export: every primitive, transform and boolean, before meshing) and rebuilds
that tree with the OpenCASCADE kernel, so

  * cylinders, cones and spheres come out as true analytic surfaces,
  * linear_extrude / rotate_extrude become prisms and revolved solids,
  * translate / rotate / mirror become exact transforms (scale too; a stretch
    turns a sphere into a free-form surface),
  * union / difference / intersection are exact booleans,

and the result is a STEP (AP214) solid that CAD tools can edit face by face.
The .scad file stays the single source; this only translates it.

Supported: cylinder, cube, sphere, polyhedron, circle, square, polygon,
linear_extrude (no twist/scale), rotate_extrude (360 deg), multmatrix,
union / group / difference / intersection. hull, offset, minkowski and text
are refused -- keep models that should export to STEP free of them.
Polyhedra come out faceted (the thread ribbon is one); everything else is exact.

Needs the OpenCASCADE bindings:  pip install cadquery-ocp
"""
import math, os, re, subprocess, sys, tempfile

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon,
                                BRepBuilderAPI_MakeSolid, BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Sewing,
                                BRepBuilderAPI_Transform, BRepBuilderAPI_GTransform)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import (BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCone,
                             BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism,
                             BRepPrimAPI_MakeRevol, BRepPrimAPI_MakeSphere)
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.ShapeFix import ShapeFix_Solid
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopTools import TopTools_ListOfShape
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax1, gp_Ax2, gp_Circ, gp_Dir, gp_GTrsf, gp_Pnt, gp_Trsf, gp_Vec

FUZZ = 1e-4          # mm; OpenSCAD models overlap cuts by 0.01, so this is safe


# ---- parse the .csg ---------------------------------------------------------
class Node:
    def __init__(self, name, args, children):
        self.name, self.args, self.children = name, args, children


def parse(text):
    pos = 0
    n = len(text)
    name_stack = []

    def skip():
        nonlocal pos
        while pos < n and text[pos] in " \t\r\n":
            pos += 1

    def args_until_paren():
        nonlocal pos
        depth, start = 1, pos
        while depth:
            c = text[pos]
            if c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
            pos += 1
        raw = text[start:pos - 1]
        if name_stack[-1] == "multmatrix":       # the one positional argument
            return {"m": eval(raw, {"__builtins__": {}})}
        py = (raw.replace("$", "S_").replace("true", "True")
                 .replace("false", "False").replace("undef", "None"))
        return eval("dict(" + py + ")", {"__builtins__": {}}, {"dict": dict})

    def node():
        nonlocal pos
        skip()
        m = re.match(r"[A-Za-z_]\w*", text[pos:])
        name = m.group(0)
        pos += len(name)
        skip()
        assert text[pos] == "(", name
        pos += 1
        name_stack.append(name)
        args = args_until_paren()
        name_stack.pop()
        skip()
        children = []
        if text[pos] == "{":
            pos += 1
            while True:
                skip()
                if text[pos] == "}":
                    pos += 1
                    break
                children.append(node())
        else:
            assert text[pos] == ";", name
            pos += 1
        return Node(name, args, children)

    roots = []
    while True:
        skip()
        if pos >= n:
            return roots
        roots.append(node())


# ---- OCC helpers --------------------------------------------------------------
def _list(shapes):
    lst = TopTools_ListOfShape()
    for s in shapes:
        lst.Append(s)
    return lst


def boolean(op, shapes):
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        return None
    if op == "union" and len(shapes) == 1:
        return shapes[0]
    head, rest = shapes[0], shapes[1:]
    if not rest:
        return head
    algo = {"union": BRepAlgoAPI_Fuse, "difference": BRepAlgoAPI_Cut,
            "intersection": BRepAlgoAPI_Common}[op]()
    if op == "intersection":
        # pairwise: a common of many tools is the common with their UNION
        out = head
        for r in rest:
            c = BRepAlgoAPI_Common()
            c.SetArguments(_list([out]))
            c.SetTools(_list([r]))
            c.SetFuzzyValue(FUZZ)
            c.Build()
            assert c.IsDone(), "intersection failed"
            out = c.Shape()
        return out
    algo.SetArguments(_list([head]))
    algo.SetTools(_list(rest))
    algo.SetFuzzyValue(FUZZ)
    algo.SetRunParallel(True)
    algo.Build()
    assert algo.IsDone(), op + " failed"
    return algo.Shape()


def transform(shape, m):
    # gp_Trsf can only move, turn and scale evenly; it silently gets a stretch wrong.
    # A stretched sphere (an ellipsoid) therefore goes through the general transform,
    # which turns its surface into a B-spline one (still an exact shape, just not analytic).
    cols = [math.sqrt(sum(m[r][c] ** 2 for r in range(3))) for c in range(3)]
    if max(cols) - min(cols) > 1e-9:
        g = gp_GTrsf()
        for r in range(3):
            for c in range(3):
                g.SetValue(r + 1, c + 1, float(m[r][c]))
            g.SetValue(r + 1, 4, float(m[r][3]))
        return BRepBuilderAPI_GTransform(shape, g, True).Shape()
    t = gp_Trsf()
    t.SetValues(m[0][0], m[0][1], m[0][2], m[0][3],
                m[1][0], m[1][1], m[1][2], m[1][3],
                m[2][0], m[2][1], m[2][2], m[2][3])
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def polygon_face(pts):
    poly = BRepBuilderAPI_MakePolygon()
    for x, y in pts:
        poly.Add(gp_Pnt(float(x), float(y), 0.0))
    poly.Close()
    return BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()


def circle_face(r):
    edge = BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), r)).Edge()
    return BRepBuilderAPI_MakeFace(BRepBuilderAPI_MakeWire(edge).Wire()).Face()


def polyhedron(points, faces):
    sew = BRepBuilderAPI_Sewing(1e-6)
    for f in faces:
        poly = BRepBuilderAPI_MakePolygon()
        for i in f:
            p = points[i]
            poly.Add(gp_Pnt(*map(float, p)))
        poly.Close()
        sew.Add(BRepBuilderAPI_MakeFace(poly.Wire(), True).Face())
    sew.Perform()
    sewn = sew.SewedShape()
    exp = TopExp_Explorer(sewn, TopAbs_SHELL)
    shell = TopoDS.Shell_s(exp.Current())
    solid = BRepBuilderAPI_MakeSolid(shell).Solid()
    fix = ShapeFix_Solid(solid)
    fix.Perform()
    return fix.Solid()


# ---- evaluate the tree -----------------------------------------------------
def ev(nd):
    a, k = nd.args, nd.name
    kids = lambda: [ev(c) for c in nd.children]

    if k in ("group", "union", "render", "color"):
        return boolean("union", kids())
    if k == "difference":
        return boolean("difference", kids())
    if k == "intersection":
        return boolean("intersection", kids())
    if k == "multmatrix":
        body = boolean("union", kids())
        return None if body is None else transform(body, a["m"])

    if k == "cylinder":
        h, r1, r2 = float(a["h"]), float(a["r1"]), float(a["r2"])
        if abs(r1 - r2) < 1e-12:
            s = BRepPrimAPI_MakeCylinder(r1, h).Shape()
        else:
            s = BRepPrimAPI_MakeCone(r1, r2, h).Shape()
        if a.get("center"):
            s = transform(s, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, -h / 2]])
        return s
    if k == "cube":
        sx, sy, sz = [float(v) for v in a["size"]]
        s = BRepPrimAPI_MakeBox(sx, sy, sz).Shape()
        if a.get("center"):
            s = transform(s, [[1, 0, 0, -sx / 2], [0, 1, 0, -sy / 2], [0, 0, 1, -sz / 2]])
        return s
    if k == "sphere":
        return BRepPrimAPI_MakeSphere(float(a["r"])).Shape()
    if k == "polyhedron":
        return polyhedron(a["points"], a["faces"])

    if k == "circle":
        return circle_face(float(a["r"]))
    if k == "square":
        sx, sy = [float(v) for v in a["size"]]
        f = polygon_face([(0, 0), (sx, 0), (sx, sy), (0, sy)])
        if a.get("center"):
            f = transform(f, [[1, 0, 0, -sx / 2], [0, 1, 0, -sy / 2], [0, 0, 1, 0]])
        return f
    if k == "polygon":
        pts, paths = a["points"], a.get("paths")
        if paths is None:
            return polygon_face(pts)
        outer = polygon_face([pts[i] for i in paths[0]])
        holes = [polygon_face([pts[i] for i in p]) for p in paths[1:]]
        return boolean("difference", [outer] + holes)

    if k == "linear_extrude":
        assert list(a.get("scale", [1, 1])) == [1, 1] and not a.get("twist"), \
            "linear_extrude with scale/twist is not supported"
        h = float(a["height"])
        prof = boolean("union", kids())
        s = BRepPrimAPI_MakePrism(prof, gp_Vec(0, 0, h)).Shape()
        if a.get("center"):
            s = transform(s, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, -h / 2]])
        return s
    if k == "rotate_extrude":
        assert float(a.get("angle", 360)) == 360, "only full rotate_extrude"
        prof = boolean("union", kids())
        # OpenSCAD revolves the XY profile about Y and stands it up on Z
        prof = transform(prof, [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0]])
        return BRepPrimAPI_MakeRevol(prof, gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)),
                                     2 * math.pi).Shape()

    raise SystemExit(f"scad2step: '{k}' cannot be exported to STEP -- "
                     "rewrite that part of the model with plain primitives")


# ---- main -------------------------------------------------------------------
def solids(shape):
    exp, out = TopExp_Explorer(shape, TopAbs_SOLID), []
    while exp.More():
        out.append(exp.Current())
        exp.Next()
    return out


def volume(shape):
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, p)
    return p.Mass()


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, out, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    dargs = []                        # accepts "-D X=1" and "X=1" alike
    while rest:
        d = rest.pop(0)
        if d == "-D":
            d = rest.pop(0)
        elif d.startswith("-D"):
            d = d[2:].strip()
        dargs += ["-D", d]
    with tempfile.TemporaryDirectory() as tmp:
        csg = os.path.join(tmp, "model.csg")
        subprocess.run([os.environ.get("OPENSCAD", "openscad"), "-o", csg, *dargs, src], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tree = parse(open(csg).read())

    shape = boolean("union", [ev(n) for n in tree])
    unify = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
    unify.Build()
    shape = unify.Shape()

    ok = BRepCheck_Analyzer(shape).IsValid()
    sol = solids(shape)
    print(f"  {os.path.basename(out)}: {len(sol)} solid(s), "
          f"{volume(shape) / 1000:.2f} cm3, valid={ok}")
    if not ok or len(sol) != 1:
        sys.exit("scad2step: result is not one valid solid")

    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    if w.Write(out) != IFSelect_RetDone:
        sys.exit("scad2step: STEP write failed")


if __name__ == "__main__":
    main()
