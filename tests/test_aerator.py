"""Regression test: rebuild the tap aerator and compare every STL with
tests/baseline/tap-aerator.json (volume and size within 0.5%, closed solid,
bodies, check verdict per process). No AI is involved.

  tools/test.sh --update-baseline   rewrites the baseline on purpose
Set TEST_SKIP_BUILD=1 to reuse the STLs already in examples/tap-aerator/out/stl.
"""
import glob, json, os, shutil, subprocess, sys, tempfile
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = os.path.join(ROOT, "examples", "tap-aerator")
STL_DIR = os.path.join(PROJ, "out", "stl")
BASELINE = os.path.join(ROOT, "tests", "baseline", "tap-aerator.json")
TOL = 0.005
UPDATE = os.environ.get("UPDATE_BASELINE") == "1"

sys.path.insert(0, os.path.join(ROOT, "tools"))
import partcheck  # noqa: E402


def build():
    # build.sh refreshes the committed README renders in img/: put them back.
    img = os.path.join(PROJ, "img")
    keep = tempfile.mkdtemp()
    shutil.copytree(img, os.path.join(keep, "img"))
    try:
        r = subprocess.run([os.path.join(PROJ, "build.sh")], cwd=ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert r.returncode == 0, ("build.sh exit %d\n--- stdout ---\n%s\n--- stderr ---\n%s"
                                   % (r.returncode, r.stdout[-2000:], r.stderr[-2000:]))
    finally:
        shutil.rmtree(img)
        shutil.copytree(os.path.join(keep, "img"), img)
        shutil.rmtree(keep)


def measure_all():
    out = {}
    for path in sorted(glob.glob(os.path.join(STL_DIR, "*.stl"))):
        name = os.path.basename(path)
        measured = partcheck.measure(path)
        verdicts, rep = {}, None
        for proc in sorted(partcheck.load_processes()):
            rep, _ = partcheck.check(path, proc, measured=measured)
            verdicts[proc] = rep["verdict"]
        out[name] = {"volume_cm3": rep["volume_cm3"], "size_mm": rep["size_mm"],
                     "watertight": rep["watertight"], "bodies": rep["bodies"],
                     "verdicts": verdicts}
    return out


@pytest.fixture(scope="session")
def results():
    if os.environ.get("TEST_SKIP_BUILD") != "1":
        build()
    res = measure_all()
    assert res, "build produced no STL files"
    if UPDATE:
        with open(BASELINE, "w") as f:
            json.dump(res, f, indent=1, sort_keys=True)
            f.write("\n")
    return res


def baseline():
    if not os.path.exists(BASELINE):
        return {}
    with open(BASELINE) as f:
        return json.load(f)


def close(a, b):
    return abs(a - b) <= TOL * abs(b) + 0.01


def test_same_files(results):
    assert sorted(results) == sorted(baseline()), "the build makes a different set of STL files"


@pytest.mark.parametrize("name", sorted(baseline()))
def test_stl_matches_baseline(results, name):
    assert name in results, f"{name} was not built"
    got, want = results[name], baseline()[name]
    assert got["watertight"], f"{name} is not a closed solid"
    assert got["bodies"] == want["bodies"], f"{name} bodies {got['bodies']} != {want['bodies']}"
    assert close(got["volume_cm3"], want["volume_cm3"]), \
        f"{name} volume {got['volume_cm3']} cm3, baseline {want['volume_cm3']}"
    for ax, g, w in zip("XYZ", got["size_mm"], want["size_mm"]):
        assert close(g, w), f"{name} size {ax} {g} mm, baseline {w}"
    assert got["verdicts"] == want["verdicts"], \
        f"{name} check verdicts changed: {got['verdicts']} (baseline {want['verdicts']})"
