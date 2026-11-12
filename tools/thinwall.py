#!/usr/bin/env python3
"""Wall-thickness check for a printable STL, like a print service's heatmap.

    thinwall.py <part.stl> [--red 0.5] [--warn 1.2] [--png out.png]

For every face, cast a ray from just inside the face, straight into the
material (against its outward normal), and measure how far it travels before
leaving through the other side. That distance is the local wall thickness --
the same measure JLC3DP's "thin wall heatmap" uses. Faces below --red are the
ones a service rejects; below --warn it flags them.

Thin faces are grouped by height (z) and radius from the Z axis, which is
enough to tell which feature of an axisymmetric part they belong to. With
--png, writes a map of the thin faces in (radius, z) so they can be seen.

Needs: pip install trimesh rtree
"""
import argparse, math, sys
import numpy as np
import trimesh


def thickness(mesh, eps=1e-3):
    origins = mesh.triangles_center - mesh.face_normals * eps
    dirs = -mesh.face_normals
    loc, idx_ray, idx_tri = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)
    t = np.full(len(origins), np.inf)
    d = np.linalg.norm(loc - origins[idx_ray], axis=1)
    keep = idx_tri != idx_ray                 # ignore hitting the face we started on
    np.minimum.at(t, idx_ray[keep], d[keep])
    return t + eps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stl")
    ap.add_argument("--red", type=float, default=0.5)
    ap.add_argument("--warn", type=float, default=1.2)
    ap.add_argument("--png")
    a = ap.parse_args()

    m = trimesh.load(a.stl, force="mesh")
    t = thickness(m)
    area = m.area_faces
    c = m.triangles_center
    r = np.hypot(c[:, 0], c[:, 1])
    z = c[:, 2]

    red, warn = t < a.red, (t >= a.red) & (t < a.warn)
    print(f"{a.stl}: {len(t)} faces, thinnest {np.min(t):.3f} mm")
    print(f"  < {a.red} mm : {area[red].sum():7.2f} mm2 over {red.sum()} faces")
    print(f"  < {a.warn} mm : {area[warn].sum():7.2f} mm2 over {warn.sum()} faces")

    # group by (z band, r band) so each feature shows up once
    def groups(mask, label):
        if not mask.any():
            return
        bands = {}
        for zi, ri, ti, ai in zip(np.round(z[mask] * 2) / 2, np.round(r[mask] * 2) / 2,
                                  t[mask], area[mask]):
            k = (zi, ri)
            b = bands.setdefault(k, [math.inf, 0.0])
            b[0] = min(b[0], ti); b[1] += ai
        top = sorted(bands.items(), key=lambda kv: -kv[1][1])[:12]
        print(f"  {label}: largest areas by (z, r):")
        for (zi, ri), (tm, ar) in top:
            print(f"      z {zi:6.1f}  r {ri:5.1f}   thinnest {tm:5.2f} mm   {ar:6.2f} mm2")
    groups(red, f"RED   (< {a.red})")
    groups(warn, f"WARN  ({a.red}-{a.warn})")

    if a.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 7))
        ax.scatter(r, z, s=1, c="#C9D1D9")
        ax.scatter(r[warn], z[warn], s=4, c="#E8B90E", label=f"{a.red}-{a.warn} mm")
        ax.scatter(r[red], z[red], s=6, c="#D7301F", label=f"< {a.red} mm")
        ax.set_xlabel("radius from axis, mm"); ax.set_ylabel("height, mm")
        ax.set_aspect("equal"); ax.legend(loc="lower left")
        fig.tight_layout(); fig.savefig(a.png, dpi=130)
    return 1 if red.any() else 0


if __name__ == "__main__":
    sys.exit(main())
