"""tools/build_frame.sh: from a shed description to frame, checks, shopping
list and a saved version. No AI is involved."""
import json, os, shutil, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = os.path.join(ROOT, "projects", "zz-frame-test")


def run(env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([os.path.join(ROOT, "tools", "build_frame.sh"), "zz-frame-test"], cwd=ROOT, env=e,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def test_pipeline_makes_everything_and_versions_only_on_change():
    shutil.rmtree(PROJ, ignore_errors=True)
    os.makedirs(PROJ)
    try:
        shutil.copy(os.path.join(ROOT, "examples", "garden-shed", "structure.json"), os.path.join(PROJ, "structure.json"))
        r = run({"PRICES": "hu", "NOTE": "first"})
        assert r.returncode == 0, r.stdout
        out = os.path.join(PROJ, "out")
        for name in ("frame.json", "checks.json", "bom.json", "bom.md", "cutlist.csv"):
            assert os.path.getsize(os.path.join(out, name)) > 0, name
            assert os.path.exists(os.path.join(out, "versions", "v1", name)), f"v1/{name}"
        with open(os.path.join(out, "bom.json")) as f:
            bom = json.load(f)
        assert bom["totals"]["amount"] > 0 and bom["trim_mm"] == 20 and bom["sheet_spare_pct"] == 0
        with open(os.path.join(out, "versions", "v1", "meta.json")) as f:
            assert json.load(f)["note"] == "first"
        assert "Preview:" in r.stdout and "--build" in r.stdout

        assert "unchanged" in run({"PRICES": "hu"}).stdout, "an identical rebuild saved a new version"

        with open(os.path.join(PROJ, "structure.json")) as f:
            spec = json.load(f)
        spec["width"] = 3600
        with open(os.path.join(PROJ, "structure.json"), "w") as f:
            json.dump(spec, f)
        assert run({"PRICES": "hu"}).returncode == 0
        assert os.path.exists(os.path.join(out, "versions", "v2", "frame.json"))
    finally:
        shutil.rmtree(PROJ, ignore_errors=True)


def test_a_missing_spec_is_an_error():
    r = subprocess.run([os.path.join(ROOT, "tools", "build_frame.sh"), "zz-no-such-project"], cwd=ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert r.returncode != 0 and "no spec" in r.stdout


def test_the_old_description_name_and_the_title_still_work():
    shutil.rmtree(PROJ, ignore_errors=True)
    os.makedirs(PROJ)
    try:
        shutil.copy(os.path.join(ROOT, "examples", "garden-shed", "structure.json"), os.path.join(PROJ, "shed.json"))
        r = run()
        assert r.returncode == 0, r.stdout
        assert "--title 'Garden shed'" in r.stdout          # the description's name
        # a path gives the same title, not the path
        r = subprocess.run([os.path.join(ROOT, "tools", "build_frame.sh"), "projects/zz-frame-test"], cwd=ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert r.returncode == 0 and "--title 'Garden shed'" in r.stdout
    finally:
        shutil.rmtree(PROJ, ignore_errors=True)
