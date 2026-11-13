"""The timber generator's output must not change when its code is reorganised.
(The two gable-shed cases were added with the gable roof, the two terrace cases with the
terrace, the two pergola cases with the pergola and the two summer kitchen cases with the
summer kitchen, the five "planned-" cases with the planner; the rest are the pent shed.)

Each case is a description; the sha256 of its frame file (without any
"assemblies" or "decisions" key), of its check findings and of its shopping list are in
tests/golden/frames.json, made by `tools/golden.py --update`.

    .venv/bin/python -m pytest tests/test_blocks_identical.py
"""
import copy, json, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
FIX = os.path.join(ROOT, "tests", "fixtures")
GOLDEN = os.path.join(ROOT, "tests", "golden", "frames.json")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _find(*rels):
    """The first existing path: example descriptions move between branches."""
    for r in rels:
        p = os.path.join(ROOT, r)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(rels)


def _openings_all_walls():
    return [{"wall": "front", "kind": "door", "x": 500, "width": 900, "height": 1900},
            {"wall": "left", "kind": "window", "x": 600, "sill": 900, "width": 700, "height": 600},
            {"wall": "right", "kind": "window", "x": 700, "sill": 900, "width": 600, "height": 600},
            {"wall": "back", "kind": "window", "x": 800, "sill": 900, "width": 800, "height": 600}]


def cases():
    eu, us = _load(os.path.join(FIX, "shed-eu.json")), _load(os.path.join(FIX, "shed-us.json"))
    garden = _load(_find("examples/garden-shed/structure.json", "examples/garden-shed/shed.json"))
    tool = _load(_find("tests/fixtures/tool-shed.json"))
    c = {"shed-eu": eu, "shed-us": us, "garden-shed": garden, "tool-shed": tool}
    for base, spec in (("eu", eu), ("us", us)):
        for style in ("three-stud", "california", "two-stud"):
            c[f"{base}-corner-{style}"] = dict(spec, corner=style)
        c[f"{base}-top-plate-single"] = dict(spec, top_plate="single")
        c[f"{base}-overhang-side-0"] = dict(spec, overhang_side=0)
        c[f"{base}-minimal"] = {"type": "pent-shed", "width": 2400, "depth": 1800,
                                **({"region": "us"} if base == "us" else {})}
    c["eu-large-overhang"] = dict(eu, overhang=600, overhang_side=250)
    c["us-large-overhang"] = dict(us, overhang=600, overhang_side=250)
    c["eu-openings-all-walls"] = dict(eu, width=3600, depth=3000, openings=_openings_all_walls())
    c["us-openings-all-walls"] = dict(us, width=3600, depth=3000, openings=_openings_all_walls())
    c["eu-fascia-item"] = dict(eu, fascia_item=_fascia_for(eu))
    c["us-fascia-item"] = dict(us, fascia_item=_fascia_for(us))
    c["eu-low-pitch"] = dict(eu, height_front=2400, height_back=2350)
    c["eu-edits"] = dict(eu, edits=_edits(eu))
    c["gable-eu"] = _load(os.path.join(FIX, "gable-eu.json"))
    c["gable-us"] = _load(os.path.join(FIX, "gable-us.json"))
    c["terrace-eu"] = _load(os.path.join(FIX, "terrace-eu.json"))       # added with the terrace
    c["terrace-us"] = _load(os.path.join(FIX, "terrace-us.json"))
    c["pergola-eu"] = _load(os.path.join(FIX, "pergola-eu.json"))       # added with the pergola
    c["pergola-us"] = _load(os.path.join(FIX, "pergola-us.json"))
    c["summer-kitchen-eu"] = _load(os.path.join(FIX, "summer-kitchen-eu.json"))   # added with the summer kitchen
    c["summer-kitchen-us"] = _load(os.path.join(FIX, "summer-kitchen-us.json"))
    # added with the planner (sections, spacings and heights the description leaves open are chosen)
    c["planned-pent-5x4"] = {"type": "pent-shed", "width": 5000, "depth": 4000}
    c["planned-gable-5x4"] = {"type": "gable-shed", "width": 5000, "depth": 4000}
    c["planned-kitchen-mono-5x4"] = {"type": "summer-kitchen", "width": 5000, "depth": 4000, "roof": "mono"}
    c["planned-pergola-6x4"] = {"type": "pergola", "width": 6000, "depth": 4000}
    c["planned-gable-4x3-door"] = {"type": "gable-shed", "width": 4000, "depth": 3000,
                                   "openings": [{"wall": "front", "kind": "door", "x": 1000, "width": 900, "height": 2000}]}
    return c


def _fascia_for(spec):
    import timberlib as tl
    lib = tl.load(spec.get("region", "eu"))
    keys = sorted(k for k in lib["sections"] if k != lib["defaults"]["items"]["rafter"])
    return keys[0]


def _edits(spec):
    """One move, one remove, one add, on pieces that exist in every shed."""
    import frame
    m = {x["id"]: x for x in frame.generate(spec)["members"]}
    stud = sorted(i for i in m if "/stud-" in i)[1]
    gone = sorted(i for i in m if "/cripple-" in i or "/stud-" in i)[-1]
    new = {k: m[stud][k] for k in ("kind", "layer", "item", "size", "x", "y")}
    new.update(id="edit/shelf-stud", group="wall-back", origin=[1500.0, 2000.0, 300.0])
    return [{"op": "move", "id": stud, "by": [30, 0, 0]},
            {"op": "remove", "id": gone},
            {"op": "add", "member": new}]


GOLD = _load(GOLDEN) if os.path.exists(GOLDEN) else {}
CASES = cases()


def test_matrix_is_big_enough():
    assert len(CASES) >= 14
    assert set(GOLD) == set(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_identical(name):
    from golden import outputs, sha
    out = outputs(copy.deepcopy(CASES[name]))
    got = {k: sha(v) for k, v in out.items()}
    assert got == GOLD[name], f"{name}: changed: {[k for k in got if got[k] != GOLD[name][k]]}"


@pytest.mark.parametrize("name", sorted(CASES))
def test_checks_read_assemblies_with_the_same_findings(name):
    """The span checks read spacings from the frame's assemblies (and fall back to
    the spec, which the hashes above use); both give the same findings. Also
    through a JSON round trip, as the build script reads the file."""
    import frame, framecheck
    full = frame.generate(copy.deepcopy(CASES[name]))
    if CASES[name]["type"] in ("terrace", "pergola", "summer-kitchen"):     # their checks read the assemblies only
        want = {"terrace": ["beams", "deck", "foundations", "posts"],
                "pergola": ["beams", "braces", "foundations", "posts", "rafters", "slats"],
                "summer-kitchen": None}[CASES[name]["type"]]
        if want is None:
            ids = [a["id"] for a in full["assemblies"]]
            assert {"beams", "braces", "foundations", "posts", "roof"} <= set(ids)
            assert all(i.startswith("wall-") for i in ids if i not in ("beams", "braces", "foundations", "posts", "roof",
                                                                   "deck", "floor-beams", "floor-foundations", "floor-posts"))
            want = sorted(ids)
        assert sorted(a["id"] for a in full["assemblies"]) == want
        for fr in (full, json.loads(frame.dumps(full))):
            got = __import__("hashlib").sha256(json.dumps(framecheck.run(fr), sort_keys=True).encode()).hexdigest()
            assert got == GOLD[name]["checks"]
        return
    assert [a["id"] for a in full["assemblies"]] == ["floor", "wall-front", "wall-back",
                                                    "wall-left", "wall-right", "roof"]
    assert full["assemblies"][-1]["type"] == ("gable-roof" if CASES[name]["type"] == "gable-shed" else "mono-roof")
    for fr in (full, json.loads(frame.dumps(full))):
        got = __import__("hashlib").sha256(json.dumps(framecheck.run(fr), sort_keys=True).encode()).hexdigest()
        assert got == GOLD[name]["checks"]
