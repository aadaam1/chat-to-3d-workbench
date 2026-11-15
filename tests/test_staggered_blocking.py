"""Blocking that only stiffens the joists is staggered by one timber thickness (so each
block can be end-nailed through its joist); blocking under a sheet seam stays in a straight
line (the seam lands on its centre).

With today's libraries the sheets are 1250 mm wide, so no joist ever runs more than 1500 mm
between seams and no stiffening-only row is made; the tests lower the limit to get one.

    .venv/bin/python -m pytest tests/test_staggered_blocking.py
"""
import json, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import frame as frm  # noqa: E402
import framecheck as fc  # noqa: E402
import framing  # noqa: E402
from timber.store import aabb  # noqa: E402

TJ = 50.0                       # the floor joists' thickness (50x150)


def _spec(**kw):
    with open(os.path.join(ROOT, "tests", "fixtures", "shed-eu.json"), encoding="utf-8") as f:
        return {**json.load(f), **dict(width=3600, depth=3000), **kw}


def _blocks(frame):
    return [m for m in frame["members"] if m["kind"] == "blocking" and m["group"] == "floor"]


def _yc(m):
    lo, hi = aabb(m)
    return (lo[1] + hi[1]) / 2


@pytest.fixture
def deep(monkeypatch):
    """A 3 m deep floor with the unblocked limit lowered to 1 m: seams at 875 and 2125, a
    stiffening row at 1500."""
    monkeypatch.setattr(framing, "MAX_UNBLOCKED", 1000.0)
    return frm.generate(_spec())


def test_todays_libraries_make_no_stiffening_only_row():
    frame = frm.generate(_spec(depth=6000))
    rows = {}
    for m in _blocks(frame):
        rows.setdefault(round(_yc(m)), []).append(m)
    assert len(rows) == 4                                    # the seams only, each row straight


def test_seam_rows_are_straight_and_the_stiffening_row_alternates(deep):
    blocks = _blocks(deep)
    seam_blocks = [m for m in blocks if abs(_yc(m) - 1500) > 100]
    assert {round(_yc(m), 1) for m in seam_blocks} == {875.0, 2125.0}       # one straight line each
    mid = sorted((m for m in blocks if abs(_yc(m) - 1500) <= 100), key=lambda m: aabb(m)[0][0])
    assert len(mid) == 9 and {round(_yc(m), 1) for m in mid} == {1500 - TJ / 2, 1500 + TJ / 2}
    for a, b in zip(mid, mid[1:]):                           # neighbours differ by one thickness
        assert abs(_yc(a) - _yc(b)) == pytest.approx(TJ)
    # the deck's seams land on the straight rows' centre lines
    sheets = {round(aabb(m)[0][1], 1) for m in deep["members"] if m["kind"] == "sheet" and m["group"] == "floor"}
    assert 875.0 in sheets and 2125.0 in sheets


def test_every_staggered_block_still_joins_two_joists(deep):
    ids = {m["id"]: m for m in deep["members"]}
    joined = {}
    for j in deep["joints"]:
        if j["type"] == "joist-rim" and ids[j["a"]]["kind"] == "blocking":
            joined.setdefault(j["a"], []).append(ids[j["b"]])
    for m in _blocks(deep):
        a, b = joined[m["id"]]
        assert a["kind"] == b["kind"] == "joist"
        lo, hi = aabb(m)
        # the block runs from one joist's face to the next one's, and sits within the joists' depth
        assert aabb(a)[1][0] == pytest.approx(lo[0]) or aabb(b)[1][0] == pytest.approx(lo[0])
        assert aabb(a)[0][1] <= lo[1] and hi[1] <= aabb(a)[1][1]


def test_staggering_adds_no_findings_and_no_members(monkeypatch):
    monkeypatch.setattr(framing, "MAX_UNBLOCKED", 1000.0)
    staggered = frm.generate(_spec())
    monkeypatch.setattr(framing, "stagger_row", lambda *a, **k: False)
    straight = frm.generate(_spec())

    def issues(f):
        full = {k: v for k, v in f.items() if k not in ("assemblies", "decisions")}
        return sorted((x["id"], x["level"]) for x in fc.run(full)["findings"] if x["level"] != "ok")

    assert issues(staggered) == issues(straight)
    assert [m["id"] for m in staggered["members"]] == [m["id"] for m in straight["members"]]


def test_a_single_bay_stays_straight(monkeypatch):
    monkeypatch.setattr(framing, "MAX_UNBLOCKED", 1000.0)
    frame = frm.generate(_spec(width=500, openings=[]))
    assert {round(_yc(m), 1) for m in _blocks(frame)} == {875.0, 1500.0, 2125.0}


def test_stagger_row_rule():
    assert framing.stagger_row(1500, [875, 2125], TJ)
    assert not framing.stagger_row(1500, [1450], TJ)         # too near a seam row: stay straight
    assert framing.stagger_row(1500, [], TJ)
