"""Home-printer presets: PLA and PETG, the bed-size check, the filament estimate."""
import json, os, re, sys
import pytest
import trimesh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import partcheck  # noqa: E402

HOME = ("fdm_pla", "fdm_petg")


def box(tmp_path, name, ex):
    p = tmp_path / f"{name}.stl"
    trimesh.creation.box(extents=ex).export(p)
    return str(p)


def scad_table():
    src = open(os.path.join(ROOT, "lib", "process.scad")).read()
    rows = re.findall(r'\["(\w+)",\s*\[([^\]]*)\]\]', src.split("_PROC = [")[1].split("];")[0])
    out = {}
    for k, v in rows:
        f = [x.strip() for x in v.split(",")]
        out[k] = (float(f[0]), float(f[1]), float(f[2]), float(f[3]))
    return out


def test_partcheck_knows_home_processes():
    procs = partcheck.load_processes()
    for k in HOME:
        assert k in procs and procs[k]["home"]
        for f in ("name", "short", "for", "look", "wall_red", "wall_warn", "overhang_deg",
                  "bridges_ok", "needs_escape", "fit", "hole_comp", "min_hole",
                  "rate_usd_cm3", "notes", "density_g_cm3", "nozzle_c", "bed_c"):
            assert f in procs[k], (k, f)


def test_scad_and_json_agree():
    procs, table = partcheck.load_processes(), scad_table()
    assert set(procs) == set(table), "process.scad and processes.json list different processes"
    for k, (fit, comp, min_wall, _chamfer) in table.items():
        assert procs[k]["fit"] == fit and procs[k]["hole_comp"] == comp, k
        # min_wall in the CAD table is the wall to design to: at least the checker's warn limit
        assert min_wall >= procs[k]["wall_warn"] - 1e-9, k


def test_bed_fit_three_cases():
    bed = (220, 220, 250)
    assert partcheck.bed_fit((100, 100, 100), bed)["fit"] == "as built"
    assert partcheck.bed_fit((100, 100, 250.0), bed)["fit"] == "as built"
    r = partcheck.bed_fit((240, 50, 50), bed)            # too long for the bed, fits standing up
    assert r["fit"] == "turned" and "X axis up" in r["turn"]
    assert partcheck.bed_fit((50, 50, 300), bed)["fit"] == "no"       # 300 mm long: no way
    assert partcheck.bed_fit((100, 100, 100), (300, 300, 60))["fit"] == "no"
    assert partcheck.bed_fit((200, 200, 50), (300, 300, 60))["fit"] == "as built"
    assert partcheck.bed_fit((50, 50, 200), (300, 300, 60))["fit"] == "turned"   # low printer: lay it down
    assert partcheck.bed_fit((300, 300, 300), bed)["fit"] == "no"


def test_bed_check_in_report(tmp_path, monkeypatch):
    monkeypatch.delenv("BED", raising=False)
    ok = partcheck.check(box(tmp_path, "ok", [50, 50, 50]), "fdm_pla")[0]
    assert ok["bed"]["fit"] == "as built" and ok["verdict"] == "pass"
    turned = partcheck.check(box(tmp_path, "long", [240, 50, 50]), "fdm_pla")[0]
    assert turned["verdict"] == "check" and any("only turned" in c for c in turned["cautions"])
    big = partcheck.check(box(tmp_path, "big", [300, 300, 300]), "fdm_petg")[0]
    assert big["verdict"] == "fail" and any("any orientation" in p for p in big["problems"])
    # service processes have big machines: no bed check
    svc = partcheck.check(box(tmp_path, "big", [300, 300, 300]), "fdm_asa")[0]
    assert "bed" not in svc


def test_bed_size_sources(tmp_path, monkeypatch):
    stl = box(tmp_path, "p", [240, 50, 50])
    monkeypatch.delenv("BED", raising=False)
    assert partcheck.check(stl, "fdm_pla")[0]["bed"]["fit"] == "turned"       # default 220 x 220
    monkeypatch.setenv("BED", "256x256x256")
    assert partcheck.check(stl, "fdm_pla")[0]["bed"]["fit"] == "as built"     # environment
    monkeypatch.delenv("BED")
    (tmp_path / "printer.json").write_text(json.dumps({"name": "Test", "bed": [300, 300, 300]}))
    r = partcheck.check(stl, "fdm_pla")[0]
    assert r["bed"]["fit"] == "as built" and "printer.json" in r["bed"]["source"]
    monkeypatch.setenv("BED", "100x100x100")                                  # env beats the file
    assert partcheck.check(stl, "fdm_pla")[0]["bed"]["fit"] == "no"


def test_filament_on_a_cube(tmp_path):
    # 20 mm cube: V = 8000 mm3, A = 2400 mm2; shell = 2880 -> capped? no, 2880 < 8000
    # printed = 2880 + 0.2 * 5120 = 3904 mm3 = 3.904 cm3; PLA 1.24 g/cm3 -> 4.84 g
    r = partcheck.check(box(tmp_path, "cube", [20, 20, 20]), "fdm_pla")[0]
    assert r["filament_cm3"] == pytest.approx(3.90, abs=0.01)
    assert r["filament_g"] == pytest.approx(4.8, abs=0.05)
    assert r["filament_cost_usd"] == pytest.approx(4.84 * 20 / 1000, abs=0.01)
    assert r["cost_usd"] is None                       # no service price for a home printer
    petg = partcheck.check(box(tmp_path, "cube", [20, 20, 20]), "fdm_petg")[0]
    assert petg["filament_g"] > r["filament_g"]        # denser
    thin = partcheck.filament(1000, 5000, 1.24, 20)    # shell larger than the part: all solid
    assert thin[2] == pytest.approx(1.0)


def test_print_settings_block(tmp_path):
    r = partcheck.check(box(tmp_path, "cube", [20, 20, 20]), "fdm_petg")[0]
    text = "\n".join(r["print_settings"])
    assert "0.2 mm" in text and "gyroid" in text and "230-250" in text and "none needed" in text
    assert "Print settings" in partcheck.to_markdown(r)
