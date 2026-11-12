#!/usr/bin/env python3
"""Keep the design versions of a part, so the preview can switch between them.

    versions.py snapshot <versions_dir> <part.stl> [more.stl ...] [--note "what changed"]
    versions.py list <versions_dir>

`snapshot` copies the given STL files into <versions_dir>/v<N>/ with a
meta.json, but only when they differ from the latest version: the same files
with the same bytes are the same version, so rebuilding without a change
saves nothing. Versions live in the project's out/ folder and are never
committed; delete a v<N> folder to forget that version.
"""
import argparse, datetime, hashlib, json, os, shutil, sys


def numbers(d):
    if not os.path.isdir(d):
        return []
    return sorted(int(n[1:]) for n in os.listdir(d) if n.startswith("v") and n[1:].isdigit())


def shape_bytes(raw):
    """A binary STL's geometry in a fixed order. OpenSCAD writes the same shape
    with its triangles in a different order from run to run, so comparing
    bytes would call every rebuild a new version. Vertices go on a 0.1 µm
    grid, each triangle starts at its smallest vertex (winding kept), and the
    triangles are sorted."""
    import numpy as np
    n = int(np.frombuffer(raw[80:84], "<u4")[0])
    if len(raw) != 84 + 50 * n:
        return raw                                        # not binary STL: compare bytes
    rec = np.frombuffer(raw[84:], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    t = np.round(rec["v"].astype(np.float64), 4)
    first = np.argmin(t[:, :, 0] * 1e12 + t[:, :, 1] * 1e6 + t[:, :, 2], axis=1)
    idx = (np.arange(3)[None, :] + first[:, None]) % 3
    t = np.take_along_axis(t, idx[:, :, None], axis=1).reshape(len(t), 9)
    return t[np.lexsort(t.T[::-1])].tobytes()


def digest(paths):
    h = hashlib.sha256()
    for p in sorted(paths, key=os.path.basename):
        h.update(os.path.basename(p).encode())
        with open(p, "rb") as f:
            raw = f.read()
        h.update(shape_bytes(raw) if p.lower().endswith(".stl") else raw)
    return h.hexdigest()


def snapshot(d, stls, note):
    stls = [p for p in stls if os.path.isfile(p)]
    if not stls:
        sys.exit("versions.py: no STL files to save")
    h = digest(stls)
    ns = numbers(d)
    if ns:
        with open(os.path.join(d, f"v{ns[-1]}", "meta.json")) as f:
            if json.load(f).get("hash") == h:
                print(f"version: unchanged, still v{ns[-1]}")
                return ns[-1]
    n = (ns[-1] if ns else 0) + 1
    vd = os.path.join(d, f"v{n}")
    os.makedirs(vd)
    for p in stls:
        shutil.copy2(p, vd)
    meta = {"n": n,
            "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": note or "",
            "files": sorted(os.path.basename(p) for p in stls),
            "hash": h}
    with open(os.path.join(vd, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(f"version: saved v{n}" + (f" ({note})" if note else ""))
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("dir")
    s.add_argument("stl", nargs="+")
    s.add_argument("--note", default="")
    l = sub.add_parser("list")
    l.add_argument("dir")
    a = ap.parse_args()
    if a.cmd == "snapshot":
        snapshot(a.dir, a.stl, a.note)
    else:
        for n in numbers(a.dir):
            with open(os.path.join(a.dir, f"v{n}", "meta.json")) as f:
                m = json.load(f)
            print(f"v{n}  {m['created']}  {', '.join(m['files'])}" + (f"  -- {m['note']}" if m["note"] else ""))


if __name__ == "__main__":
    main()
