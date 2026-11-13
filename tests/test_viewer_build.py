"""The preview page for a timber structure: tools/make_viewer.py --build puts
the frame's members into the page. No AI is involved."""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def run(*args):
    return subprocess.run([PY, *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def page_data(path):
    with open(path) as f:
        page = f.read()
    assert "__KIT_DATA__" not in page
    m = re.search(r'<script type="application/json" id="kit-data">(.*?)</script>', page, re.S)
    assert m, "no data block in the page"
    return json.loads(m.group(1).replace("<\\/", "</"))


def frame(tmp_path, fixture):
    out = tmp_path / "frame.json"
    r = run("tools/frame.py", f"tests/fixtures/{fixture}.json", "--out", str(out))
    assert r.returncode == 0, r.stdout
    return out


def test_build_page_has_every_member(tmp_path):
    f = frame(tmp_path, "shed-eu")
    r = run("tools/make_viewer.py", "--title", "Test shed", "--build", str(f), "--out", str(tmp_path / "view"))
    assert r.returncode == 0, r.stdout
    data = page_data(tmp_path / "view" / "index.html")
    assert data["kind"] == "build" and data["title"] == "Test shed"
    b = data["versions"][0]["build"]
    with open(f) as fh:
        src = json.load(fh)
    assert [m["id"] for m in b["members"]] == [m["id"] for m in src["members"]]
    assert b["region"] == "eu" and b["units"] == "metric"
    assert all(m["item"] in b["items"] for m in b["members"]), "an item has no display name"
    assert any(m["outline"] for m in b["members"]), "outlined sheets were dropped"
    assert b["checks"] is None and b["bom"] is None


def test_build_page_takes_checks_and_versions(tmp_path):
    f = frame(tmp_path, "shed-us")
    v1 = tmp_path / "versions" / "v1"
    v1.mkdir(parents=True)
    os.replace(f, v1 / "frame.json")
    (v1 / "meta.json").write_text(json.dumps({"note": "first frame", "created": "2026-11-11T10:00:00Z"}))
    (v1 / "checks.json").write_text(json.dumps([{"id": "c1", "level": "check", "title": "A test finding",
                                                 "text": "Only here for the test.", "members": [], "at": [0, 0, 0]}]))
    r = run("tools/make_viewer.py", "--title", "Test shed", "--build", str(tmp_path / "versions"),
            "--out", str(tmp_path / "view"))
    assert r.returncode == 0, r.stdout
    v = page_data(tmp_path / "view" / "index.html")["versions"]
    assert len(v) == 1 and v[0]["n"] == 1 and v[0]["note"] == "first frame"
    assert v[0]["build"]["units"] == "imperial" and v[0]["build"]["checks"][0]["title"] == "A test finding"


def test_not_a_frame_is_refused(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_text("{}")
    r = run("tools/make_viewer.py", "--title", "x", "--build", str(bad), "--out", str(tmp_path / "view"))
    assert r.returncode != 0 and "not a frame file" in r.stdout


def test_build_page_carries_decisions(tmp_path):
    f = frame(tmp_path, "shed-eu")
    src = json.loads(f.read_text())
    src["decisions"] = [{"what": "Floor joists", "chose": "50×200", "why": "50×150 spans only 3.66 m of the 3.95 m needed"},
                        {"what": "Posts", "chose": "120×120"}, {"chose": "no name: dropped"}]
    f.write_text(json.dumps(src))
    r = run("tools/make_viewer.py", "--title", "Test shed", "--build", str(f), "--out", str(tmp_path / "view"))
    assert r.returncode == 0, r.stdout
    b = page_data(tmp_path / "view" / "index.html")["versions"][0]["build"]
    assert b["decisions"] == [{"what": "Floor joists", "chose": "50×200", "why": "50×150 spans only 3.66 m of the 3.95 m needed"},
                              {"what": "Posts", "chose": "120×120"}]


def test_build_page_without_decisions_has_none(tmp_path):
    f = frame(tmp_path, "shed-eu")
    r = run("tools/make_viewer.py", "--title", "Test shed", "--build", str(f), "--out", str(tmp_path / "view"))
    assert r.returncode == 0, r.stdout
    assert "decisions" not in page_data(tmp_path / "view" / "index.html")["versions"][0]["build"]


def test_page_has_loading_and_failure_messages():
    html = open(os.path.join(ROOT, "tools", "viewer", "viewer.html")).read()
    assert "Loading the model" in html and "The 3D view could not start" in html
    assert 'id="sec-plan"' in html and "Nails, screws and bought items" in html
