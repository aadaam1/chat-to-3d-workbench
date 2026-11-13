# Framing reference

What the generator (`tools/framing.py`, `tools/frame.py`) does, why, and
where that comes from. Read it to explain a piece in plain words, or to
judge an unusual request. It is not a design standard: the span checks and
the "fix"/"check" findings stay the authority on a given shed.

Each section: **In plain words**, **Rule of thumb**, **Source** (with the
date it was read, 2026-11-12). Section numbers are the 2021 International
Residential Code (IRC) unless said otherwise. The ICC's own site
(codes.iccsafe.org) refused automated access, so the IRC text was read on
UpCodes' copy of the 2021 IRC as adopted by Colorado with no amendments
(`up.codes/viewer/colorado/irc-2021/...`). The IRC is a US code for houses;
it is the closest public yardstick for a shed, not a rule for yours. Local
rules win.

"Unverified" marks a number or claim not confirmed in a source read. "Not
read" marks a page that could not be opened.

## Wall corners

**In plain words.** Two walls meet at a corner. Each wall's end stud
needs something solid on the inside of the corner to fix the inner lining
(plasterboard, plywood) to, otherwise the lining floats at the corner.

- *Three-stud* (the default): an end stud, a second stud one wall-depth
  in, and short spacer blocks between them. Solid, easy to fix to, but the
  corner cannot be insulated well.
- *California*: two studs at right angles, plus one laid flat to give a
  fixing face. Less timber, and the corner can be insulated.
- *Two-stud*: end studs only. The lining is held with clips or scraps.

**Rule of thumb.** Every corner offers a fixing face for the lining of both
walls. Pick three-stud unless the walls are insulated (then California).

**Source.**
- Wikipedia, "Framing (construction)", read 2026-11-12:
  https://en.wikipedia.org/wiki/Framing_(construction). Says a multiple-stud
  post of at least three studs is typical at exterior corners and that a
  corner needs at least two. Terminology only.
- This Old House, "How To Frame a Corner", read 2026-11-12:
  https://www.thisoldhouse.com/walls/frame-a-corner. Describes the
  three-stud corner as solid but wasteful and cold, the California corner as
  two studs at right angles with a third inside for backing, and the
  two-stud corner with drywall clips. Does not say why the third stud
  matters beyond backing and insulation.
- The IRC prescribes no corner layout (none found in the chapters read).

## Double top plate, lapped at corners

**In plain words.** The top plate is the horizontal board across the stud
tops. A second plate laid on it, running past the corner onto the next wall,
ties the walls together, evens out the top, and spreads a load that lands
between studs.

**Rule of thumb.** Double plate; joints of the upper plate at least 610 mm
(24 in) from joints below; upper plate overlapping at corners. A single
plate is allowed if tied at corners and splices with steel plates.

**Source.**
- IRC R602.3.2 Top plate, read 2026-11-12 on UpCodes (Colorado copy):
  https://up.codes/viewer/colorado/irc-2021/chapter/6/wall-construction.
  Quote: "capped with a double top plate installed to provide overlapping at
  corners". The 24 in. offset of end joints and the single-plate
  alternative (tied per Table R602.3.2) were read in a search summary of the
  same section, not the page itself: treat the 24 in. figure as
  confirmed by that summary only.
- Fine Homebuilding, "The Evolution of Top-Plate Building Codes" (issue 306,
  2022), read 2026-11-12:
  https://www.finehomebuilding.com/project-guides/framing/the-evolution-of-top-plate-building-codes.
  Double plates tie walls and straighten them and behave like small beams
  between studs; single plates need steel ties at corners.
- Wikipedia (as above): second plate offset so joints sit at least a stud
  space from the joints below.

## Openings: king, jack, header, cripples, sill

**In plain words.** A door or window interrupts the studs. A *header* (a
deep beam on edge) spans the gap and carries the load above. It rests on
*jack* studs (short, one each side), which stand beside full-height *king*
studs that keep the wall straight and share the load. Short *cripple* studs
fill the space above the header and, under a window, below the *sill* (the
horizontal board at the window's bottom), so the stud pattern carries on.

**Rule of thumb.** King and jack each side; header on the jacks, not
screwed between studs; cripples above the header and below the sill; sill
on cripples. On site cripples are often kept on the wall's stud layout;
the workbench spaces them evenly across the opening instead (one next to
each jack, none further apart than the stud spacing), so they are
symmetric. The sheathing over an opening joins on whichever cripple suits
it, so nothing is lost.

**Source.**
- IRC R602.7.5 Supports for headers, read 2026-11-12 on UpCodes (link
  above): "Headers shall be supported on each end with one or more jack
  studs or with approved framing anchors"; the number of jacks (NJ) comes
  from Table R602.7(1). The IRC does not name king studs or cripples in the
  parts read.
- Wikipedia, "Framing (construction)", read 2026-11-12: headers rest on
  "trimmers", "also called jacks"; cripples run from the bottom plate to a
  sill or from a header up to a plate; defines lintel as header.

## Header sizing

**In plain words.** How deep the header must be depends on the opening
width, the roof or snow load it carries, and the building width.

**Rule of thumb.** The workbench uses two plies of the frame section on edge
(100 mm deep in `eu`, 89 mm in `us`) and the span check says whether that
is enough. Do not size a header by hand: change `header_item` and rebuild.

**Source.** IRC R602.7 and Table R602.7(1), "Girder Spans and Header Spans
for Exterior Bearing Walls", read 2026-11-12 on UpCodes (link above): the
section points to Tables R602.7(1)-(3) for spans. The table cells were not
read and none are quoted. R602.7.1 also allows a header of one deep
member, with a flat 2-in. member or wall plate above and below it; the
workbench builds the other common kind, two plies on edge.

## Floor joists, rim joists, blocking, deck sheets

**In plain words.** Joists are the parallel boards that carry the floor.
Rim joists close the ends of the joists and tie them. Blocking is short
pieces between joists that stop them twisting, and gives the sheets an edge
to land on. The deck sheets (plywood or OSB) go across the joists, with
joints in a row staggered from the next, and every joint across the joists
over a support, so no edge is left unsupported.

**Rule of thumb.** Blocking under every seam across the joists, and a row at
mid-span if a joist would run more than 1.5 m unblocked (unverified: the
1.5 m limit is the workbench's own choice, not found in a source). Joists
over a nominal 2x12 need bridging or blocking at 2.4 m (8 ft) or less.

**Source.**
- IRC R502.7 Lateral restraint at supports and R502.7.1 Bridging, read
  2026-11-12 on UpCodes:
  https://up.codes/viewer/colorado/irc-2021/chapter/5/floors. Joist ends are
  supported laterally by full-depth solid blocking or by a full-depth
  header, band or rim joist; joists over a nominal 2x12 need solid
  blocking, diagonal bridging or a nailed strip at intervals not over 8 ft.
- IRC R502.6 Bearing (same page): 1 1/2 in. (38 mm) of bearing on wood.
- IRC R503.1.1 (same page): end joints in lumber subflooring over supports.
  The staggering of panel joints (R503.2) was not found on the page read:
  staggered seams are common practice, source not read.
- Wikipedia, "Framing (construction)": rim joist is the perimeter member;
  bridging near mid-span.

## Roof: rafters, blocking, fascia, side overhang

**In plain words.** Rafters are the sloping boards that carry the roof.
They sit on the wall plates. A *birdsmouth* is a notch cut in a rafter so
it sits flat on the plate. Blocking between rafters over the wall closes the
gap above the wall and gives the roof sheet and the wall top a fixing.
The *fascia* is the board across the rafter ends. At the sides, the roof
sticks out past the end wall. A short overhang is carried by a *ladder*:
two long rails (the end rafter and a *flying rafter*, the outer one) joined
by short *outriggers* (the rungs) tied back into the roof. A *bargeboard*
covers the outer face and the rafter ends. The roof deck runs out over
the fascia and the bargeboards to their outer faces, so the roofing and
its drip edge cover their top edges.

**Rule of thumb.**
- Rafters bear at least 38 mm on the plate.
- Do not notch a rafter beyond the limits (notch depth limits not read).
- Side overhang on a ladder: about 300 mm (12 in) is the usual practical
  limit, with outriggers at about 600 mm (24 in) apart or closer. Beyond
  that, use lookouts (outlookers) running back over the second rafter. They
  can cantilever to about 600 mm (24 in).
- Rake fascia of at least a 2x6 in the DOE guide; in the workbench, the
  rafter section.

**Source.**
- IRC R802.6 Bearing, R802.7 Cutting and notching (rafters over a cantilever
  keep at least 3 1/2 in. of material and 24 in. of cantilever), R802.8
  Lateral support (depth to thickness over 5 to 1), read 2026-11-12 on
  UpCodes:
  https://up.codes/viewer/colorado/irc-2021/chapter/8/roof-ceiling-construction.
  The page shows no rake overhang, lookout or birdsmouth detail; the notch
  limits are cross-referenced to R502.8.1, which was not read.
- Building America Solution Center (US DOE, PNNL), "Framing of Gable Roof
  Overhangs", last updated 2020-09-26, read 2026-11-12:
  https://basc.pnnl.gov/resource-guides/framing-gable-roof-overhangs.
  Ladder framing is limited to 8 to 12 in., outrigger framing beyond 12 in.;
  ladder blocks of 2x4 or 2x6 at 24 in.; rake fascia at least 2x6 fixed
  with screws at 8 in.; FEMA suggests a lower ladder limit in high wind.
- Simpson Strong-Tie blog, "Designing Gable End Overhangs", September 2016,
  read 2026-11-12:
  https://seblog.strongtie.com/2016/09/designing-overhangs-gable-ends/. Ladder
  outlookers limited to 12 in., cantilevered outlookers up to 24 in. (it
  cites the AWC Wood Frame Construction Manual for that; the manual itself
  was not read, so the 24 in. figure is unconfirmed beyond the blog).
- Fine Homebuilding forum "max. overhang on gable end ladder" (2005),
  read 2026-11-12:
  https://www.finehomebuilding.com/forum/max-overhang-on-gable-end-ladder.
  Anecdote only: builders range from 12 in. as the limit to 24 in. with
  doubled rafters and straps. Shows there is no code figure.
- Wikipedia, "Bargeboard", read 2026-11-12:
  https://en.wikipedia.org/wiki/Bargeboard. A board fixed to a projecting
  gable, also called rake fascia.

## Gable roof: ridge board, rafter pairs, ties

**In plain words.** In a gable roof two slopes meet at a *ridge*. Rafters
come in pairs that lean on each other at the top, with a *ridge board*
between them to line them up. Because the pairs push the walls outward,
a *tie* (a ceiling joist, or a rafter tie) runs across the building at the
top of the walls and is fixed to both rafters of each pair. The two long
walls that carry the rafters are the eave walls; the two end walls are
gable walls, whose studs rise into the triangle under the roof.

**Rules as built** (`gable-shed`):
- **Ridge board** at least 25 mm thick and at least as deep as the plumb
  cut of the rafter (rafter depth / cos(pitch)). The default `ridge_item`
  is the smallest section in the library that is no thicker than the
  rafter, at least 25 mm thick, and deep enough (50x200 for 50x150 rafters
  at 25 degrees; 2x8 for 2x6). Rafters land opposite each other, plumb-cut
  against its two faces, their tops flush with the ridge board's top. The
  deck stops 8 mm short of the apex on each slope; the ridge cap covers it.
- **Rafters** in pairs on the same layout as the mono roof, seated on the
  eave walls' top plates at the plates' outer edge (no birdsmouth, as in
  the mono roof), plumb cut at the eaves, `overhang` both sides.
- **Ties** are ceiling joists: full depth of the building, level and straight,
  bearing on both eave walls' top plates from the outer face of one to the outer
  face of the other (default `tie_item` is the rafter section). Each lies
  beside its rafter pair, on the +X side (right, seen from the front) for
  every pair, touching both rafters face to face, face-nailed to each at the
  heel (`tie-rafter`) and toe-nailed to each plate (`tie-plate`). Only the top
  corners at the ends are trimmed to the roof plane, where a deep tie would
  poke above the deck. A pair over a gable wall has no tie of its own: that
  wall's top plates, lapped over the eave walls' plates at the corners, tie
  that end.
- **Eaves:** blocking closes every rafter bay over both eave walls (in a
  bay beside a tie the block is shortened by the tie's thickness, so block
  and tie together close it); fascia
  on both eaves (tops dropped so the deck runs over them).
- **Gable ends:** `overhang_side` as before, a ladder on each slope with a
  bargeboard on each; the two bargeboards are plumb-cut at the centre line,
  which is the mitre between two equal slopes. `overhang_side: 0` puts the
  bargeboards on the end rafters.
- **Deck** on both slopes, rows from each eave up to the ridge, blocking
  under the seams; roofing bought for both slopes plus a ridge cap by length.
- **Gable studs** follow the roof line (a bevelled top); under the ridge
  board they stop at it. `height_ridge` is the top of the rafters at the
  centre line, measured like `height_eaves`.

**Source.**
- IRC 2021 R802.3 Ridge: a ridge board used to connect opposing rafters is at
  least 1 in. nominal thick and at least as deep as the cut end of the
  rafter; a ridge board is allowed where continuous ceiling joists or rafter
  ties hold the walls, otherwise the ridge is a supported beam. Read
  2026-11-12 as a paraphrase on
  https://www.jaspector.com/codes/irc-2021/ch08-roof-ceiling-construction/ridge-board-size-code/
  (codes.iccsafe.org refused the request and up.codes had no page; Seattle's
  amended 2021 copy,
  https://seattle.gov/documents/departments/sdci/codes/seattleresidentialcode/2021srcchapter8.pdf,
  is a PDF that could not be read as text, but a search snippet of it carries
  the same rule). The text of R802.3.1 (ceiling joist and rafter ties),
  R802.4 and R802.5 was **not read**: the ties rule is from the paraphrase
  above and the span tables are not used. 1 in. nominal is 19 mm; the
  workbench asks for 25 mm.
- The IRC fastening schedule rows for rafter to ridge, ceiling joist to
  rafter (the heel joint table R802.5.1(9)) and ceiling joist to plate were not
  read; the counts for `rafter-ridge` (4 toe nails, 3 end nails), `tie-rafter`
  (4 face nails) and `tie-plate` (3 toe nails) in the library are marked
  unverified.

**Where the workbench differs.** Rafter span is taken horizontally from the
eave wall's outer face to the ridge board and checked as a simply supported
rafter (the ridge board is not a beam). The ridge and tie members are not
checked for strength, only for size and layout (`ridge`, `rafter-ties`). Below
about 17 degrees a 150 mm deep tie fills the bay up to the first deck seam
and the sheet-edge check may flag the seam: use a shallower `tie_item` or a
steeper roof.
The sheathing on a gable wall is one sheet high, so a very tall gable end
is refused (`height_eaves`).

## Terrace: footings, posts, beams, joists, deck boards

**In plain words.** A raised terrace is a floor with no walls. It stands on
footings (ground screws, precast concrete blocks, or poured piers), each with a
post base; posts stand on the bases; beams run along the rows of posts; deck
joists lie across the beams; deck boards go across the joists with a gap
between them for water and air. `"type": "terrace"` builds all of it, with the
ground at Z 0 and the top of the boards at `height`. Footings and post bases
are bought items, drawn on the `foundations` layer.

**Rules the generator follows.**
- Beam rows are inset from the long edges (half the beam width plus 25 mm) and
  no further apart than `row_spacing`; posts under every row at most
  `post_spacing` apart. Both default to the library's cap (2 m in `eu`, 80 in.
  in `us`) or 80% of what the span formulas allow for the joist or beam, the
  smaller. Joists run across the beams and overhang the outer rows a little.
- A **sandwich** beam (the default, two plies) has a ply on each side of every
  post, bolted through, its top level with the post top and the joists lying
  on it. An **on_top** beam lies on the posts' tops on a post cap. One ply
  needs `on_top`.
- **Low terraces.** A post shorter than the library's `min_post_mm` (150 mm) is
  left out: the beams then sit on the post bases directly (`on_top`), and the
  footings' above-ground part is built up to meet them. If even that does not
  fit, the description is refused with the lowest height that works.
- Deck boards run across the joists, the gap `board_gap` (5 mm) between rows,
  spread to at most 8 mm to use up the remainder or finished with one ripped
  board. A row longer than the longest stock length is cut on joists with the
  joints staggered from row to row. Two screws at every joist crossing.
- Joist spacing defaults to the board's limit (500 mm for a 28 mm board, 400
  mm for 25 mm, 16 in. for 5/4 decking).
- Checks: spans of the joists and each beam (the load is the deck, the joists
  and `loads.floor_kn_m2`, 2.5 kN/m2 in `eu`, 40 psf in `us`), the board span,
  `post-footing` (every post on a post base on a footing), `beam-bearing`
  (every beam end over a post or footing, at most 300 mm past it), and a
  `check` that a terrace higher than about 600 mm usually needs a railing.
  Footing capacity (soil, frost, wind, uplift) is **not** checked.
- A shed may carry `"foundation"`: footings under its front and back rim
  joists (`footing_spacing`, 1.5 m by default); the floor frame is unchanged.

**Sources** (all read 2026-11-13, none from a primary table: values are
marked `unverified` in the libraries). Ground screw ranges, for example
Krinner's (https://www.krinner.com/en/products/ground-screws/): the page
answered HTTP 429, so the sizes (Ø76 mm, 800 to 1200 mm long, a post bracket)
and the 2 m spacing are what such ranges typically offer, not read. Precast
pier blocks and poured piers: typical builders' sizes (300 mm block; 300 mm
diameter by 800 mm pier; 400 mm square pad), frost depth decides the real
depth. Deck boards: 28 x 145 mm is the usual board, 25 x 150 is in the
supplier price snapshot (data/timber/prices/hu-szekely-fatelep-2026-11-10.csv);
the span limit per thickness and the 5 mm gap are rules of thumb. Terrace load
2.5 kN/m2: EN 1991-1-1 Table 6.2, category A balconies, as widely reproduced;
US 40 psf: IRC R301.5 for decks. Posts 100 x 100, 120 x 120 are listed by the
supplier (140 x 140 is not); US 4x4 and 6x6 are PS 20 dressed sizes.

## Pergola: posts, beams, rafters, slats, knee braces

**In plain words.** An open pergola has no walls and no floor. Posts stand on
footings (as for the terrace); two beams lie on the posts along the long sides;
rafters lie across the beams and reach past them (the overhang); optional slats
lie across the rafters; a knee brace runs at 45 degrees from each post up to the
beam. `"type": "pergola"` builds it with the ground at Z 0 and the underside of
the beams at `height`; `width` x `depth` is the whole roofed area.

**Rules the generator follows.**
- Beams run along the longer side (or `beam_axis`), their centre lines
  `overhang` plus half the beam width from the edges, so the rafters reach
  `overhang` (300 mm) past each beam's outer face. A beam reaches
  `beam_overhang` (300 mm) past the centre of its end post. Posts at the ends and
  between, at most `post_spacing` apart (the library's cap, 2.4 m, or 80% of
  what the span formula allows the beam, whichever is less).
- Beams are one or two plies on the post, on a post cap (`on_top`). A sandwich beam
  is refused: a brace needs the beam's underside to meet.
- Rafters lie on the beams: one flush at each end, one centred over every post, and
  more between them, no further apart than `rafter_spacing`; slats lie
  flat across them, one flush at each edge. Rafters are not notched (a notch
  takes wood from a beam that already carries the span) and are skew-screwed
  into each beam ply; a hurricane tie is the upgrade where wind matters.
- **Knee braces.** 45 degrees, centreline legs of 600 mm (24 in. in `us`), a 75 x 75
  mm (4x4) section; the foot is cut plumb against the post and the head level
  against the beam's underside, bolted through the post and screwed into the beam.
  One goes on each side of a post where at least 700 mm of beam runs on past the
  post face, so end posts are braced inward only and middle posts both ways. The
  leg shrinks to fit between close posts (at most 45% of the gap each).
- **Cross braces.** Every post also gets a brace across the beams (the short sides),
  on the inner side, from the post up to the rafter that sits over it (same 45
  degrees, leg and section; the foot is on the post face under the beam, so the
  brace passes beside the beam). It is ripped to the rafter's thickness, so a rafter
  must be at least 38 mm thick (a 2x), otherwise the description is refused with
  `rafter_item` (or turn `braces` off). A tie beam across the ends was not needed.
  The legs and the angle are the usual builders' rule of thumb; no source was
  read (marked unverified, id `pergola-practice`).
- Checks: spans of the rafters (between beam centres, snow `loads.snow_kn_m2`,
  the overhang only helps and is flagged above a quarter of the span) and of each
  beam (half the rafter span plus the overhang), `post-footing`, `beam-bearing`
  (a beam may reach up to 500 mm past its last post), and `open-bracing`: a `fix`
  naming the post and the direction (along the beams or across them) when a
  brace is missing, or does not touch both the post and the beam or rafter. Wind, uplift, footing capacity and the braces' strength
  are **not** checked; an open pergola can act like a sail.

## European (UK/EU) names and equivalents

| In this workbench / US | UK and Europe | Note |
|---|---|---|
| blocking (between joists or rafters) | noggins, noggings, dwangs (Scotland) | horizontal members between studs, joists or rafters |
| header | lintel | |
| jack stud | cripple stud in UK timber frame; "trimmer" | NHBC and LABC use "cripple studs" for the studs that carry the lintel, which is what the US calls jacks |
| cripple (above or below an opening) | short studs, noggings | |
| top plate, double | head binder (and wall plate on the roof side) | |
| bottom plate | sole plate | |
| flying rafter, rake | fly rafter, verge, verge rafter | |
| rim joist | ring beam, header joist | NHBC: "ring beam or header joist" |
| bargeboard | bargeboard, verge board | |

**Rule of thumb.** In a UK or EU conversation use the left-hand names once,
with the local name in brackets, then the local name.

**Source.**
- NHBC Standards 2025, Chapter 6.2 "External timber framed walls", read
  2026-11-12 (PDF copy hosted at newbuildinspections.com, text extracted
  from it):
  https://www.newbuildinspections.com/wp-content/uploads/2025/04/NHBC-Standards-2025-Chapter-6-2-External-timber-framed-walls.pdf.
  Studs at least 38 mm wide at not more than 600 mm centres; "Lintels and
  cripple studs should be provided at openings in load-bearing panels"
  except where the opening does not affect the stud spacing or the loads go
  to a ring beam or header joist; sole plates and head binders bind panels
  together, joints over a stud. The 2025 edition was read, not the 2023
  one. No head-binder lap length found in this chapter.
- LABC Warranty Technical Manual Version 11, section 6 "External Walls",
  read 2026-11-12 (text extracted from the PDF; the date of the version
  is not shown in the text I read):
  https://www.labcwarranty.co.uk/hubfs/Technical%20Manual%20V11%20-%20Thumbnails/Technical%20Manual%20V11%20-%20Section%20PDF%20Downloads/Section%206%20External%20Walls.pdf.
  "Head binder laps should wherever possible occur over a stud, preferably
  at least 600mm from the panel junction"; "A lintel should be provided
  where one or more studs is cut or displaced to form an opening"; lintels
  need the support of cripple studs.
- Trussed Rafter Association (TRA), "Gable ladders - deemed to satisfy
  details", technical card dated 12 March 2026, read 2026-11-12:
  https://trustspan.co.uk/upload/library/gable-ladders-technical-card.pdf.
  A ladder of at least 35x72 mm timber, noggings at 600 mm centres at most,
  and "Overhang from face of brickwork should not exceed the back span of
  the ladder"; the card is for trussed-rafter gables on masonry or timber
  frame, not a shed, and uses its own loads (wind to 1.35 kN/m2).
- Wikipedia, "Bargeboard": "vergeboard" is an obsolete synonym.
- I found no UK or EU source for the word "fly rafter" beyond forum posts
  (not cited). Treat "fly rafter" and "verge" as common trade usage, not
  from a standard.
- TRADA's own guides were not read (search found only a third-party copy
  of an introduction). Eurocode 5 and national timber-frame guides were
  not read.

## Fixings: nails and structural screws

**In plain words.** The frame, sheets and cladding are nailed, as a builder
does at this quantity; nails are bought by weight (kg, or lb in the US).
Structural screws are used on two joints only, where they are stronger:
the **rafter to the wall plate** (one long screw per rafter and plate against
wind uplift, plus two toe nails to hold it while screwing; in the US a
hurricane tie is the usual answer) and the **corner stud** (the wall panels
are stood up separately and pulled together with screws every ~500 mm).

**Rule of thumb.** Studs to plates: 2 end nails. Doubled top plate: face nails
every 16 in. (400 mm). Corner lap: 2 face nails. Header to king or jack: 4 toe
nails. Floor joist to rim, blocking to rafter: 3 end nails. Sheathing: every
6 in. (150 mm). Cladding: 2 nails per stud crossing. Sizes: framing nail
3.1 x 90 (US 16d), small toe nail 2.8 x 65 (US 8d), sheathing ring-shank
2.8 x 50, cladding ring-shank 2.8 x 60 (US 8d siding).

**Source.** IRC 2021 Table R602.3(1), read 2026-11-12 second-hand (a
distributor's chart and ICC's 2012/13 proposal text; the code site refused
access). Per-joint counts, EU nail counts per kg and the structural screw sizes
are workbench rules: all `unverified`. Details and the full table:
`docs/research/timber-structures.md`, "Nails and structural screws".

## Where the workbench differs

From `docs/research/framing-details.md`:

- **No birdsmouth.** Rafters bear on the inner edge of the front plate and
  the outer edge of the back plate without a notch, so the model shows less
  than the 38 mm bearing above. On site, cut a shallow birdsmouth at each
  plate so the rafter sits flat on it. Notching is a later option.
- **Square-to-slope blocking.** Rafter blocking is cut square to the slope,
  flush with the rafters top and bottom, its outer face on the frame's
  outer face. At the front plate there is a small gap (up to wall depth
  x tan(pitch), about 14 mm on the examples) between block and plate; on
  site it is bevelled or packed.
- **Side overhang limit of 300 mm.** `overhang_side` is 0, or rafter
  thickness + 50 mm, up to 300 mm. More needs lookouts running back to the
  second rafter, which are not built. The figure matches the common 12 in.
  practical limit for ladders (BASC, Simpson, above), not a code limit.
- **Fixing counts are unverified.** Joint types `blocking-rafter`,
  `fascia-rafter` (2 nails), `barge-rafter` (every 400 mm), `king-jack`,
  `jack-header`, `plate-lap` and `corner-stud` carry unverified nail or screw
  counts in the library (`joint_rules._meta` says so); the shopping list
  does not flag them yet, so say so when handing it over.
- **Header on the frame section** (two plies on edge), not the rafter
  section, so a standard door fits under a double plate.
- **Double plate laps only at the back corners:** the side walls are lower
  than the front wall in a mono-pitch shed, so at the front they butt its
  corner framing.
- **1.5 m unblocked joist span** is the workbench's own rule, not from a
  source.
- **Fascia on the rafter section** (`fascia_item`), not a 25 mm board; a
  50 mm fascia is common on sheds.
