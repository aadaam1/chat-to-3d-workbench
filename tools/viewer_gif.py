#!/usr/bin/env python3
"""Turn the preview page into GIFs and stills, headless, from a shot list.

    viewer_gif.py <page.html> <out.gif|out.png> --shots docs/img/shots/x.json
    viewer_gif.py <page.html> <out.gif|out.png> --frames "48:az=0..360,explode=0.4"

The page is made by tools/make_viewer.py (use --inline so it is one file). It
needs a network connection the first time: the page loads three.js from a CDN.
Each frame opens `page.html?capture=1&view=..&explode=..&layers=..&az=..&el=..&zoom=..`
in headless Chrome. Capture mode hides all the UI and draws one still frame;
see the "capture mode" block in tools/viewer/viewer.html.

Parameters: view=3d|front|side|top|below, explode=0..1, layers=foundations,frame,floor,deck,walls,roof,
sheathing,cladding (the visible ones), az=<deg> turns the camera around the model
from the view's own angle, el=<deg> its height, zoom=<factor>, mode=studio|advanced.

Shot list (JSON):
    {"size": [900, 600], "fps": 14, "colors": 160,
     "defaults": {"view": "3d", "zoom": 0.95},
     "frames": [ {..params..}, ... ]}                     # one entry per frame, or
     "frames": 56, "loop": true,                          # N frames, interpolated
     "keys": [ {"at": 0, "az": 0, "explode": 0}, {"at": 0.5, "explode": 1, "ease": "smooth"}, ... ]
Numbers between keys are interpolated (linear, or "ease": "smooth" on the
earlier key); text such as layers holds its value until the next key that sets
it. With "loop": true the last frame stops short of at=1, so it flows back to
the first. A png output is the first frame only.

--frames "N:k=v,k=a..b" is the same in one line (a..b is interpolated).
Chrome: set CHROME to its path, or it is found on macOS and Linux. Frames are
joined with ffmpeg (palettegen/paletteuse) when installed, else Pillow.
"""
import argparse, concurrent.futures, json, os, re, shutil, subprocess, sys, tempfile
from urllib.parse import urlencode

CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]
CHROME_MAC = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"]
# --use-angle=swiftshader makes WebGL work on machines without a GPU (CI, containers)
CHROME_FLAGS = ["--headless=new", "--hide-scrollbars", "--disable-gpu-vsync", "--no-first-run",
                "--no-default-browser-check", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                "--force-device-scale-factor=1"]


def find_chrome():
    p = os.environ.get("CHROME")
    if p and os.path.exists(p):
        return p
    for c in CHROME_MAC:
        if os.path.exists(c):
            return c
    for n in CHROME_NAMES:
        w = shutil.which(n)
        if w:
            return w
    sys.exit("viewer_gif: Google Chrome (or Chromium) not found. Install it, or set CHROME=/path/to/chrome.")


def _ease(k, how):
    return k * k * (3 - 2 * k) if how == "smooth" else k


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def interpolate(keys, t):
    """Parameters at time t (0..1) from sorted keys {"at":.., params, "ease":..}."""
    keys = sorted(keys, key=lambda k: k["at"])
    out, names = {}, {n for k in keys for n in k if n not in ("at", "ease")}
    for n in names:
        have = [k for k in keys if n in k]
        before = [k for k in have if k["at"] <= t]
        after = [k for k in have if k["at"] > t]
        a = before[-1] if before else have[0]
        if not before or not after or not (_num(a[n]) and _num(after[0][n])):
            out[n] = a[n]
        else:
            b = after[0]
            k = _ease((t - a["at"]) / (b["at"] - a["at"]), a.get("ease"))
            out[n] = a[n] + (b[n] - a[n]) * k
    return out


def parse_frames_arg(spec):
    """'48:az=0..360,explode=0.4' -> a shot list dict."""
    n, _, rest = spec.partition(":")
    if not n.strip().isdigit() or int(n) < 1:
        raise ValueError(f"--frames needs a frame count first, like 48:az=0..360 (got {spec!r})")
    a, b = {"at": 0.0}, {"at": 1.0}
    for part in filter(None, (p.strip() for p in re.split(r"[;,](?=\s*\w+=)", rest))):
        if "=" not in part:
            raise ValueError(f"expected key=value in {part!r}")
        k, v = part.split("=", 1)
        lo, dots, hi = v.partition("..")
        a[k], b[k] = _val(lo), _val(hi if dots else lo)
    return {"frames": int(n), "keys": [a, b], "loop": _num(a.get("az")) and _num(b.get("az")) and abs(b["az"] - a["az"]) % 360 == 0 and a["az"] != b["az"]}


def _val(s):
    try:
        return float(s) if any(c in s for c in ".eE") else int(s)
    except ValueError:
        return s


def expand(shots):
    """A shot list -> (list of per-frame parameter dicts, width, height, fps)."""
    w, h = shots.get("size", [900, 600])
    defaults = dict(shots.get("defaults", {}))
    fr = shots.get("frames")
    if isinstance(fr, list):
        frames = [dict(f) for f in fr]
    elif isinstance(fr, int) and fr > 0:
        keys = shots.get("keys")
        if not keys:
            raise ValueError("a frame count needs 'keys'")
        n, loop = fr, bool(shots.get("loop"))
        div = n if loop else max(1, n - 1)
        frames = [interpolate(keys, i / div) for i in range(n)]
    else:
        raise ValueError("shot list needs 'frames' (a list, or a count with 'keys')")
    return [{**defaults, **f} for f in frames], int(w), int(h), float(shots.get("fps", 14))


def frame_url(page, params):
    """file:// URL of the page in capture mode with these parameters."""
    q = []
    for k, v in params.items():
        if k in ("hold",):
            continue
        if isinstance(v, (list, tuple)):
            v = ",".join(map(str, v))
        elif isinstance(v, float):
            v = f"{v:.4f}".rstrip("0").rstrip(".")
        q.append((k, v))
    base = "file://" + os.path.abspath(page)
    return f"{base}?{urlencode([('capture', '1')] + q, safe=',')}"


def shoot(chrome, url, png, w, h, budget_ms):
    prof = tempfile.mkdtemp(prefix="viewer-gif-")
    try:
        cmd = [chrome, *CHROME_FLAGS, f"--user-data-dir={prof}", f"--screenshot={png}",
               f"--window-size={w},{h}", f"--virtual-time-budget={budget_ms}", url]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    if not os.path.exists(png) or os.path.getsize(png) < 2000:
        sys.exit(f"viewer_gif: Chrome produced no picture for {url}")


def assemble(pngs, out, fps, colors, loop=0):
    ff = shutil.which("ffmpeg")
    if ff:
        d = os.path.dirname(pngs[0])
        subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(d, "f%04d.png"),
                        "-vf", f"split[a][b];[a]palettegen=max_colors={colors}:stats_mode=diff[p];"
                               f"[b][p]paletteuse=dither=none:diff_mode=rectangle", "-loop", str(loop), out], check=True)
        return
    from PIL import Image
    ims = [Image.open(p).convert("RGB").quantize(colors) for p in pngs]
    ims[0].save(out, save_all=True, append_images=ims[1:], duration=round(1000 / fps), loop=loop, optimize=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 1)[1])
    ap.add_argument("page"), ap.add_argument("out")
    ap.add_argument("--shots", help="JSON shot list")
    ap.add_argument("--frames", help='one-line spec, like "48:az=0..360,explode=0.4"')
    ap.add_argument("--size", help="WxH, overrides the shot list")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--budget", type=int, default=12000, help="virtual time budget per frame in ms (default 12000)")
    ap.add_argument("--jobs", type=int, default=4, help="Chrome processes at once")
    ap.add_argument("--keep", help="keep the frame PNGs in this folder")
    a = ap.parse_args(argv)
    if bool(a.shots) == bool(a.frames):
        ap.error("give exactly one of --shots or --frames")
    try:
        shots = json.load(open(a.shots)) if a.shots else parse_frames_arg(a.frames)
        frames, w, h, fps = expand(shots)
    except (ValueError, OSError, KeyError) as e:
        sys.exit(f"viewer_gif: {e}")
    if a.size:
        w, h = map(int, a.size.lower().split("x"))
    fps = a.fps or fps
    if not os.path.exists(a.page):
        sys.exit(f"viewer_gif: no such page {a.page}")
    still = a.out.lower().endswith(".png")
    if still:
        frames = frames[:1]
    chrome = find_chrome()
    tmp = a.keep or tempfile.mkdtemp(prefix="viewer-frames-")
    os.makedirs(tmp, exist_ok=True)
    # a frame held for "hold" frames is shot once and repeated
    shots_list, seq = [], []
    for f in frames:
        seq.append(len(shots_list)); shots_list.append(f)
        seq.extend([len(shots_list) - 1] * (int(f.get("hold", 1)) - 1))
    files = [os.path.join(tmp, f"s{i:04d}.png") for i in range(len(shots_list))]
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda i: shoot(chrome, frame_url(a.page, shots_list[i]), files[i], w, h, a.budget), range(len(files))))
    if still:
        shutil.copy(files[0], a.out)
    else:
        for n, i in enumerate(seq):
            shutil.copy(files[i], os.path.join(tmp, f"f{n:04d}.png"))
        assemble([os.path.join(tmp, f"f{n:04d}.png") for n in range(len(seq))], a.out, fps, int(shots.get("colors", 160)))
    if not a.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    size = os.path.getsize(a.out)
    print(f"{a.out}: {len(seq)} frames, {w}x{h}, {size / 1e6:.2f} MB")
    if size > 3e6:
        print("viewer_gif: over 3 MB; use fewer frames, a smaller size or fewer colors", file=sys.stderr)


if __name__ == "__main__":
    main()
