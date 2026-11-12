"""Tools that make files other than the part: the timber buying list and the
preview page."""
import os, re, shutil, subprocess, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
SNAPSHOT = os.path.join(ROOT, "data", "timber", "prices", "hu-szekely-fatelep-2026-11-10.csv")


def run(*args):
    return subprocess.run([PY, *args], cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)


def test_timber_buy_is_stable():
    r = run("tools/timber.py", "--snapshot", SNAPSHOT, "buy", "50x100", "2400", "12",
            "--variant", "impregnated")
    assert r.returncode == 0, r.stdout
    out = r.stdout
    assert "12 cuts needed + 2 spare" in out and "= 14" in out
    best = [l for l in out.splitlines() if l.rstrip().endswith("best")]
    assert len(best) == 1
    assert re.search(r"buy\s+7 x 5 m\s+\(2 cuts each, 196 mm offcut each\)\s+35 791 HUF gross", best[0]), best[0]
    assert "42 945 HUF" in out and "42 952 HUF" in out and "57 260 HUF" in out


@pytest.fixture(scope="module")
def stl(tmp_path_factory):
    import trimesh
    p = tmp_path_factory.mktemp("stl") / "cube.stl"
    trimesh.creation.box(extents=[20, 20, 20]).export(p)
    return str(p)


def test_inline_viewer_has_part_data(stl, tmp_path):
    out = tmp_path / "view"
    r = run("tools/make_viewer.py", "--inline", "--title", "Test cube",
            "--out", str(out), "--process", "fdm_asa", stl)
    assert r.returncode == 0, r.stdout
    page = (out / "index.html").read_text()
    assert "Test cube" in page and "__KIT_DATA__" not in page
    m = re.search(r'<script type="application/json" id="kit-data">(.*?)</script>', page, re.S)
    assert m, "no part data block in the page"
    import json
    data = json.loads(m.group(1).replace("<\\/", "</"))
    parts = data["versions"][0]["parts"]
    assert parts[0]["label"] == "cube"
    assert parts[0]["stl_data"] and parts[0]["thk_data"], "mesh data is not inline"
    assert parts[0]["report"]["verdict"] in ("pass", "check", "fail")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_viewer_script_parses(tmp_path):
    html = open(os.path.join(ROOT, "tools", "viewer", "viewer.html")).read()
    m = re.search(r'<script type="module">(.*?)</script>', html, re.S)
    assert m, "no module script in viewer.html"
    js = tmp_path / "viewer.mjs"
    js.write_text(m.group(1))
    r = subprocess.run(["node", "--check", str(js)], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True)
    assert r.returncode == 0, r.stdout
