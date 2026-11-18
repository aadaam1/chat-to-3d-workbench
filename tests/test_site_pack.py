"""tools/site_pack.py: the printable site pack (shopping list, one drawing per side, cut list).

    .venv/bin/python -m pytest tests/test_site_pack.py
"""
import html, json, os, re, subprocess, sys

import pytest

import bom as bomlib
import frame as fr
import framecheck as fc
import site_pack as sp
import timberlib as tl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build(spec, tmp=None):
    frame = fr.generate(json.loads(json.dumps(spec)))
    checks = fc.run(frame)
    bom = bomlib.make_bom(frame, None, trim=20)
    return frame, checks, bom


def pages(spec):
    frame, checks, bom = build(spec)
    return sp.build_pages(frame, checks, bom, 3, "2026-11-15"), frame


def fixture(name):
    with open(os.path.join(ROOT, "tests", "fixtures", name + ".json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def shed():
    with open(os.path.join(ROOT, "examples", "garden-shed", "structure.json"), encoding="utf-8") as f:
        return pages(json.load(f))


@pytest.fixture(scope="module")
def terrace():
    return pages(fixture("terrace-eu"))


def sections(doc):
    return re.findall(r'<section class="page draw"><div class="head"><h2>([^<]*)</h2>', doc)


def test_one_drawing_page_per_part_in_site_order(shed):
    doc, frame = shed
    titles = [t for t in sections(doc) if "(continued)" not in t]
    assert titles == ["Floor frame", "Front wall", "Back wall", "Left wall", "Right wall", "Roof"]
    assert doc.index("<h2>Shopping list") < doc.index("<h2>Floor frame") < doc.index("<h2>Cut list")


def test_terrace_has_foundations_deck_and_posts(terrace):
    doc, _ = terrace
    titles = [t for t in sections(doc) if "(continued)" not in t]
    assert titles == ["Foundations", "Deck frame", "Posts and beams"]


def test_every_member_counted_once_per_part(shed):
    doc, frame = shed
    secs = sp.make_sections(frame)
    lib = tl.load(frame["region"])
    for sec in secs:
        drawn = set()
        for v in sec["views"]:
            drawn |= {m["id"] for m, _, _ in sp.View(frame, sec, v, {}, "metric").shapes}
        letters, _ = sp.section_letters(sec, drawn)
        rows = sp.piece_rows(frame, sec, letters, lib, "metric")
        assert sum(r["qty"] for r in rows) == len(sec["members"]), sec["group"]
    assert sum(len(s["members"]) for s in secs) == len(frame["members"])


def test_letters_are_stable_and_html_is_identical(shed):
    doc, frame = shed
    again, _ = pages(json.load(open(os.path.join(ROOT, "examples", "garden-shed", "structure.json"))))
    assert again == doc
    assert "http://" not in doc.replace("http://www.w3.org/2000/svg", "") and "<script" not in doc
    assert sp.letter(0) == "A" and sp.letter(23) == "Z" and sp.letter(24) == "AA"
    sec = [s for s in sp.make_sections(frame) if s["group"] == "wall-front"][0]
    ids = {m["id"] for m in sec["members"] if m["kind"] not in sp.HIDE}
    l1, _ = sp.section_letters(sec, ids)
    l2, _ = sp.section_letters(sec, ids)
    assert l1 == l2
    studs = {l1[m["id"]] for m in sec["members"] if m["id"] in l1 and m["kind"] == "stud"}
    assert len(studs) == 1                                    # same kind, section, length: one letter


def test_projection_of_a_stud_lands_where_expected(shed):
    _, frame = shed
    stud = [m for m in frame["members"] if m["id"] == "wall-front/stud-01"][0]
    lo, hi = sp.aabb(stud)
    (poly,), _ = sp.Proj("front").shapes(stud)
    xs = [p[0] for p in poly]
    zs = [p[1] for p in poly]
    assert (min(xs), max(xs)) == pytest.approx((lo[0], hi[0]))          # right = +x seen from the front
    assert (min(zs), max(zs)) == pytest.approx((lo[2], hi[2]))
    (back,), _ = sp.Proj("back").shapes(stud)                            # seen from behind: x is mirrored
    assert (min(p[0] for p in back), max(p[0] for p in back)) == pytest.approx((-hi[0], -lo[0]))
    (left,), _ = sp.Proj("left").shapes(stud)                            # from the left, right = -y
    assert (min(p[0] for p in left), max(p[0] for p in left)) == pytest.approx((-hi[1], -lo[1]))


def test_disclaimer_on_cover_and_every_page_footer(shed):
    doc, _ = shed
    cover = doc[doc.index('<section class="page cover">'):doc.index("Shopping list")]
    assert "Guidance, not structural engineering" in cover and "qualified person" in cover and "your responsibility" in cover
    assert "Looks good" in cover or "to settle before you build" in cover
    assert sp.SHORT_WARNING in doc.split("</style>")[0]                     # in the @page footer of every page
    assert "version 3" in doc.split("</style>")[0]


def test_units_switch_for_us():
    doc, frame = pages(fixture("terrace-us"))
    assert frame["units"] == "imperial"
    assert "size:letter" in doc and "size:A4" not in doc
    cover = html.unescape(doc[doc.index('<section class="page cover">'):doc.index("Shopping list")])
    assert re.search(r"Overall size</td><td>\d+'", cover) and " mm" not in cover.split("Overall size")[1].split("</tr>")[0]
    svg_text = html.unescape("".join(re.findall(r"<text[^>]*>([^<]*)</text>", doc)))
    assert " mm" not in svg_text and re.search(r"\d+'", svg_text)


def test_foundations_page_dimensions_every_footing(terrace):
    doc, frame = terrace
    feet = sp.footings_of(frame)
    assert len(feet) == 9
    sec = doc[doc.index("<h2>Foundations</h2>"):doc.index("<h2>Deck frame</h2>")]
    lo, _ = sp.structure_box(frame)
    for fx, fy, _ in feet:
        assert f">{round(fx - lo[0])} mm<" in sec and f">{round(fy - lo[1])} mm<" in sec     # the table
    for x in {round(f[0] - lo[0]) for f in feet}:
        assert f">{x}</text>" in sec                                       # and the chain along the drawing
    for y in {round(f[1] - lo[1]) for f in feet}:
        assert f">{y}</text>" in sec
    assert all(f">{i}</text>" in sec for i in range(1, 10))


def test_openings_are_dimensioned(shed):
    doc, _ = shed
    wall = doc[doc.index("<h2>Front wall</h2>"):doc.index("<h2>Back wall</h2>")]
    assert ">Door (clear opening)</text>" in wall and ">900 wide</text>" in wall and ">1950 high</text>" in wall
    left = doc[doc.index("<h2>Left wall</h2>"):doc.index("<h2>Right wall</h2>")]
    assert ">Window (clear opening)</text>" in left and ">sill 1000 above the floor</text>" in left or ">sill 1000</text>" in left


def test_dimension_text_is_at_least_2_5_mm(shed):
    doc, _ = shed
    sizes = {float(x) for x in re.findall(r'font-size="([\d.]+)"', doc)}
    assert sizes and min(sizes) >= 2.5


def test_missing_chrome_is_a_plain_message(tmp_path, monkeypatch, capsys):
    frame, checks, bom = build(fixture("terrace-eu"))
    for n, d in (("frame.json", frame), ("checks.json", checks), ("bom.json", bom)):
        (tmp_path / n).write_text(json.dumps(d))
    monkeypatch.setattr(sp, "chrome_path", lambda: None)
    monkeypatch.setattr(sys, "argv", ["site_pack.py", str(tmp_path)])
    assert sp.main() == 1 and "needs Google Chrome" in capsys.readouterr().err
    assert (tmp_path / "site-pack.html").exists()
    monkeypatch.setattr(sys, "argv", ["site_pack.py", str(tmp_path), "--html-only"])
    assert sp.main() == 0


@pytest.mark.skipif(sp.chrome_path() is None, reason="Chrome not found")
def test_pdf_smoke(tmp_path):
    frame, checks, bom = build(fixture("terrace-eu"))
    for n, d in (("frame.json", frame), ("checks.json", checks), ("bom.json", bom)):
        (tmp_path / n).write_text(json.dumps(d))
    pdf = tmp_path / "pack.pdf"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "site_pack.py"), str(tmp_path), "--out", str(pdf)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=240)
    assert r.returncode == 0, r.stdout
    assert pdf.read_bytes()[:5] == b"%PDF-" and pdf.stat().st_size > 10_000


def test_cover_has_both_3d_views(shed):
    doc, frame = shed
    cover = doc[:doc.index("<h2>Shopping list")]
    assert "How it looks" in cover and "The frame, by part" in cover
    assert cover.count('<image ') == 2 and cover.count("data:image/png;base64,") == 2
    secs = sp.make_sections(frame)
    for i in range(len(secs)):                              # a numbered callout for every part
        assert f">{i + 1}</text>" in cover


def test_each_part_page_has_a_key_view_with_that_parts_members(shed):
    doc, frame = shed
    secs = sp.make_sections(frame)
    pages_ = re.split(r'(?=<section class="page)', doc)
    for n, sec in enumerate(secs, 1):
        page = [p for p in pages_ if f'<span class="lt pno">{n}</span>' in p and "(continued)" not in p][0]
        key = page[page.index('<div class="key">'):]
        assert "<image " in key[:key.index("</svg>")]
        picks = sp.key_picks(frame, sec)
        dark = {frame["members"][i]["id"] for i, cat, _l, _t in picks if cat == "hi"}
        want = {m["id"] for m in sec["members"] if m["kind"] not in sp.HIDE}
        assert dark == want and dark
        assert all(cat == "fa" for i, cat, _l, _t in picks if frame["members"][i]["group"] != sec["group"])


def test_3d_view_is_a_zbuffer_image_and_repeatable():
    """Depth is per pixel (no sort to defeat), and the same picks give the same bytes."""
    frame, _, _ = build(fixture("gable-eu"))
    iso = sp.Iso(frame)
    sheet = next(i for i, m in enumerate(frame["members"]) if m["kind"] == "sheet" and m["layer"] == "roof")
    rafters = [i for i, m in enumerate(frame["members"]) if m["kind"] == "rafter"]
    svg = iso.draw([(i, "tim", 0, None) for i in rafters] + [(sheet, "rof", 0, None)], 80, 80)
    assert svg.startswith("<svg") and "<image " in svg
    assert svg == iso.draw([(i, "tim", 0, None) for i in rafters] + [(sheet, "rof", 0, None)], 80, 80)


def test_long_pieces_table_is_set_tight_short_one_is_not():
    sec = {"role": "wall", "title": "Left wall"}
    row = lambda i, drawn=True, cuts="": {"letter": chr(65 + i), "name": "Stud", "item": "50×100", "length": "2000 mm",
                                         "qty": 1, "drawn": drawn, "cuts": cuts}
    short = [row(i) for i in range(sp.TIGHT_LINES - 1)]
    assert 'class="pieces"' in sp.pieces_table(sec, short, "mm", [])
    long_ = short + [row(20, cuts="0° / 8.3°"), row(21, drawn=False)]
    assert 'class="pieces tight"' in sp.pieces_table(sec, long_, "mm", [])
