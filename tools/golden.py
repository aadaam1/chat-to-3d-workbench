#!/usr/bin/env python3
"""Golden hashes for the timber frame generator (the refactor oracle).

    tools/golden.py --update [--dump DIR]

For every case in tests/test_blocks_identical.py: sha256 of the frame file
(frame.dumps, without any top-level "assemblies" key), of the check findings
and of the shopping list, written to tests/golden/frames.json. Regenerate only
on purpose, when the output is meant to change, and say why in the commit.
--dump also writes the full JSON of each case to DIR so a differing hash can be
diffed.
"""
import argparse, hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
GOLDEN = os.path.join(ROOT, "tests", "golden", "frames.json")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def outputs(raw):
    """The three texts whose hashes are compared, for one description."""
    import frame, framecheck, bom
    full = frame.generate(raw)
    fr = {k: v for k, v in full.items() if k != "assemblies"}
    # a shed's checks fall back to its spec without assemblies; a terrace's read them
    src = full if full["spec"]["type"] == "terrace" else fr
    return {"frame": frame.dumps(fr),
            "checks": json.dumps(framecheck.run(src), sort_keys=True),
            "bom": json.dumps(bom.make_bom(fr, None, 10, 4), sort_keys=True)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", required=True)
    ap.add_argument("--dump", help="folder for the full JSON of each case")
    a = ap.parse_args(argv)
    from test_blocks_identical import cases
    gold = {}
    for name, raw in cases().items():
        out = outputs(raw)
        gold[name] = {k: sha(v) for k, v in out.items()}
        if a.dump:
            os.makedirs(a.dump, exist_ok=True)
            for k, v in out.items():
                with open(os.path.join(a.dump, f"{name}.{k}.json"), "w", encoding="utf-8") as f:
                    f.write(v)
    os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
    with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
        json.dump(gold, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"golden: {len(gold)} cases -> {GOLDEN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
