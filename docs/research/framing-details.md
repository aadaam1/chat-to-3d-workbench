# Framing details

Status: F1-F7 done; F8 (the owner's second trial) to do
Last updated: 2026-11-12

## Why

The first trial of the example shed (2026-11-11) left six comments, all
carpentry conventions the generator does not follow:

1. Floor blocking sits off-centre (it follows the staggered deck seams).
2. Corners are two end studs butted together.
3. The window has no king studs, jack studs or proper cripples.
4. The top plate is single.
5. The door header is screwed between studs instead of resting on jacks.
6. Rafter bays are open over the walls, there is no fascia, and the roof
   has no overhang at the sides.

A second trial saw the same, plus short pieces floating outside the left
wall. The cause is the build plan: T2 was specified with simplified
framing and listed these details as out of scope, and the checks (T4) only
cover spans and sheet layout, not conventions.

## Approach (decided)

1. **Conventions are code.** A details library in the generator, each
   convention a named detail with options. The shed description picks
   options; regional defaults fill the rest. A first-try shed comes out
   conventionally framed.
2. **Convention checks** in `tools/framecheck.py` guard every frame,
   whoever or whatever produced it.
3. **Edits by piece.** The description carries a list of edits (move,
   resize, remove, add a member by id), applied after the rules and checked
   again. A comment on a piece becomes one recorded edit that survives
   rebuilds.
4. **Claude's part:** choose options, turn a comment into an option change
   (a rule) or an edit (a one-off), and when a comment shows a missing rule,
   add the rule to the library so the next shed gets it first time.
5. **A framing reference** next to the skill, with sources, so Claude can
   explain each piece and judge unusual requests.

## Defaults (decided, both regions; the owner can change them)

- **Corners:** three-stud corner (`corner: "three-stud"`; also
  `"california"` and `"two-stud"`). Both walls and the inside lining get a
  face to fix to.
- **Top plate:** double, the upper plate lapped over the corner to tie the
  walls (`top_plate: "double"`; also `"single"`).
- **Openings** (`opening: "king-jack"`): a king stud each side, full height;
  a jack stud inside it carrying the header; the header resting on the
  jacks; window sill on cripples; cripples above the header and below the
  sill on the stud layout. Header: two pieces of the rafter section on edge
  (eu two 50x150 = 100 wide, flush with a 100 wall; us two 2x6 with a 12 mm
  spacer to 89 mm), sized by the span check.
- **Floor:** one row of blocking at mid-span of the joists when the span is
  over 1.5 m, centred; deck sheets laid so seams across the joists land on
  that row or on the rims, symmetric about the centre.
- **Roof:** blocking between rafters over the front and back top plates;
  fascia on the rafter ends front and back; a side overhang
  (`overhang_side`, default 150 mm) on outriggers with a flying rafter and
  a bargeboard.

## Steps

Each step is its own branch and pull request, with tests, `tools/test.sh`
PASS, and review by the planning session before merging (repo routine).

| | Step | Depends on | Built by |
|---|---|---|---|
| F1 | Wall details: corners, double plate, openings | none | planning session |
| F2 | Floor and roof details; the floating-pieces bug | F1 | planning session |
| F3 | Edits by piece | F1 | planning session |
| F4 | Convention checks | F1, F2 | smaller model |
| F5 | Shopping list and preview follow-ups | F1, F2 | smaller model |
| F6 | Framing reference and skill update | F1 | smaller model with web |
| F7 | Rebuild the example, answer the six comments | F1-F6 | planning session |
| F8 | Second trial | F7 | owner |

Order: F1, then F2, then F3-F6 at the same time, then F7, then F8.

#### F1. Wall details

Done 2026-11-12: `tools/framing.py`, the wall code in `tools/frame.py`, new
spec fields `corner`, `top_plate` and `header_item`, joint rules for
`king-jack`, `jack-header`, `plate-lap` and `corner-stud` (unverified), and
`tests/test_framing.py`. Decided while building: the header is two plies of
the frame section on edge (100 mm deep in eu, 89 in us), not the rafter
section, so a standard door still fits under a double plate; a 1950 mm door
then needs a 2350 mm front wall, so the eu fixtures, the garden shed and
the tool shed were raised by 50 mm. The double plate laps only at the back
corners: in a mono-pitch shed the side walls are lower than the front wall,
so at the front they butt its corner framing. Raked side walls (a sloped
top plate instead of infill above a level one) are a possible later option.


Files: new `tools/framing.py` (the details library), `tools/frame.py` (uses
it for walls), library `defaults.details` in `eu.json` and `us.json`,
`tests/test_framing.py`.

- New member kinds: `king`, `jack`, `cripple`, `sill`, `plate` with
  `"course": 1 | 2` for double plates. Header becomes two members (or two
  plus a spacer).
- New joint types: `jack-header`, `king-jack`, `cripple-sill`,
  `cripple-header`, `plate-lap`, `corner-stud`.
- Tests, per detail, on both regions: a door and a window each have 2
  kings, 2 jacks, a header whose underside touches both jacks' tops,
  cripples no further apart than the stud spacing, each cripple touching
  the sill or header and a plate; a window sill rests on cripples; every
  corner offers a fixing face for the adjoining wall inside and out; with
  `top_plate: "double"` the upper plates overlap at every corner by the
  wall thickness; `"single"` and `"two-stud"` still generate. Existing
  T2 rules (no overlaps, studs on plates, sheet edges backed) still pass.
- The frame file format is unchanged apart from new kinds and joint
  types; ids of unchanged members stay the same where possible.

#### F2. Floor and roof details; the floating-pieces bug

Done 2026-11-12. Decided while building:

- **Floor:** the deck rows are symmetric about mid-span (a seam on the
  centre line for an even number of rows, a whole sheet centred for an odd
  number), so no row is under half a sheet; blocking goes under every seam
  across the joists, plus mid-span only if a joist would still run over
  1.5 m unblocked. With 1250 or 1219 mm sheets that extra row never comes
  up, so a 3 m deep floor has two rows, mirrored, not three.
- **Rafter ends** are plumb cut on the fascia lines (y = -overhang and
  depth + overhang), drawn with an outline, so the fascia sits flat on them.
- **Eave blocking** is the rafter section, square to the slope like the
  rafters and flush with them top and bottom, its outer face on the frame's
  outer face. The rafters have no birdsmouth in the model (they bear on the
  inner edge of the front plate and the outer edge of the back plate), so a
  front block sits up to `wall depth x tan(pitch)` (about 14 mm on the
  examples) above the plate; on site it is bevelled or packed. Same for the
  rafters themselves. A birdsmouth is a later option.
- **Side overhang** (`overhang_side`, default 150 mm eu, 152.4 mm us): a
  flying rafter of the rafter section at the overhang's edge, outriggers of
  the rafter section between it and the end rafter at both ends, over both
  walls, under every roof deck seam, and no more than the rafter spacing
  apart; a bargeboard on the outside. Allowed: 0, or rafter thickness +
  50 mm up to 300 mm; more needs lookouts running back to the second rafter
  (not built). With 0, the bargeboard goes on the end rafter.
- **Fascia and bargeboard** default to the rafter section (`fascia_item`);
  the eu library has no 25 mm board deep enough, and a 50 mm fascia is
  common on sheds. Fascia runs past the bargeboards to cover their ends.
- New kinds `outrigger`, `fascia`, `bargeboard` (flying rafters are kind
  `rafter`, id `roof/flying-rafter-left|right`); new joint types
  `blocking-rafter`, `fascia-rafter` (2 screws) and `barge-rafter` (every
  400 mm), unverified like the rest. Roof deck seam blocking now uses
  `blocking-rafter` too.
- **Floating pieces:** the trial's frame data has nothing floating and
  nothing outside the footprint (checked on the published page's members).
  What the generator did get wrong: the top cladding boards on the side
  walls were square boxes, so above the back wall height they stepped up
  past the rafter line, sticking out beyond the sheathing. That is the
  likeliest match for "short pieces floating outside the left wall"; they
  are now cut along the rafter line (an outline). To confirm with the owner
  in F7/F8 against their screenshot.
- Tests: the overlap helper now tests the real (outlined) shapes; new tests
  for the symmetric floor, closed rafter bays, fascia on every rafter end,
  the ladder, overhang limits, side cladding under the roof line, and on
  all four example sheds: every member touches another and none lies
  outside the footprint plus overhangs, fascia and wall skins.

Plan as written:

Files: `tools/framing.py`, `tools/frame.py`, `tests/test_framing.py`.

- Floor blocking row at mid-span, centred; deck seams symmetric and landing
  on blocking or rims.
- Rafter blocking over both plates; fascia front and back; side overhang
  with outriggers, flying rafter and bargeboard; roof deck and felt area
  include the side overhang.
- Find the pieces floating outside the left wall in the trial and fix the
  cause. Test: every member touches at least one other member, and none
  lies outside the footprint plus overhangs and cladding thickness.

#### F3. Edits by piece

Done 2026-11-12: `tools/frame_edits.py`, wired into `tools/frame.py`
(`edits` in the description, applied after the rules), and
`tests/test_frame_edits.py`. Decided while building: `resize` takes a full
`size` or just a `length`, and `keep` (`start`, `centre`, `end`) says which
end stays put; a piece with an outline (plumb-cut rafter, notched sheet,
cut board) can't be resized, only removed and replaced. Joints follow
contact (1 mm), typed by the two kinds: an upright on a plate, sill or
header is `stud-plate`, blocking on joists `joist-rim`, blocking or
outriggers on rafters `blocking-rafter`, a sheet on timber `sheet-frame`,
a board `board-frame`, anything else timber to timber `plate-plate`. An
optional `note` keeps the comment the edit came from. The viewer already
names the piece in every comment it copies to the chat.

Plan as written:

Files: `tools/frame.py`, `tests/test_frame_edits.py`, the T2 notes on the
description format.

- Description field `edits`: a list of `{ "op": "move" | "resize" | "remove"
  | "add", "id": ..., ... }` (`move` by `[dx, dy, dz]` mm, `resize` a new
  `size`, `add` a full member with an id under `edit/`). Applied after the
  rules, in order; joints of removed members dropped, joints of added
  members found by contact.
- An edit naming an id that no longer exists is an error naming the edit,
  so a rule change that renames pieces is noticed, not silently ignored.
- The result goes through the same checks as any frame.

#### F4. Convention checks

Files: `tools/framecheck.py`, `tests/test_framecheck.py`.

Done 2026-11-12: seven checks in `tools/framecheck.py`, each its own
function called from `run()`: `opening-frame` (extended: every header
piece must rest on two jacks, read from `jack-header` joints, and each
jack must be fixed to a king by a `king-jack` joint), `corner-fixing`,
`plate-lap`, `roof-bay-blocking`, `roof-edges`, `floating-piece`,
`floor-blocking-symmetry`. Decided: they read piece names and joints, so
an edit that removes or moves a piece trips them; the corner check
expects the corner style's own piece (`corner-NN-stud` for three-stud,
`corner-NN-flat` for california, none for two-stud) joined to a side-wall
stud; a bay is closed by a roof `blocking` member that spans it and whose
centre lies over the wall's plates (the first row of deck-seam blocking
counts when it replaces an eave block). Levels: `fix` for a corner not
fixed, an opening not framed and a floating piece; `check` for the lap,
open bays, missing fascia or bargeboard, and asymmetric floor blocking
(the plan names only the last two). Bargeboards are asked for on every
roof, fascia only when `overhang` > 0. Floating means touching no other
member (1 mm tolerance, separating-axis test from `frame_edits`), not
"connected to the frame".

- One rule each, with a frame that passes and one that trips it: header
  bears on jacks; every opening has kings; every corner has fixing for
  both walls; double plates lap at corners when chosen; every rafter bay
  over a plate is closed; fascia present when there is an overhang; no
  member floats; floor blocking symmetric (`check` level).

#### F5. Shopping list and preview follow-ups

Files: `tools/bom.py`, `tools/viewer/viewer.html`, the libraries'
`joint_rules`.

Done 2026-11-12: `cutlist.csv` has a `what` column right after `kind`
(Stud, King stud, Jack stud, Cripple stud, Sill, Header, Plate, Floor
joist, Rim joist, Blocking, Rafter, Flying rafter, Outrigger, Fascia,
Bargeboard, Cladding board, Sheet; the viewer's names, flying rafters told
apart by id); other columns and their order are unchanged. `bom.md` has a
"Cuts:" line under each stock line's cut table ("33 studs, 6 king studs,
..."), and the fastener table a "Counted for" column that names each joint
type in words ("king stud to jack stud 28"); `bom.json` has `by_kind` per
timber line and `what` per cut. The libraries already had a rule for every
joint type, so they are unchanged. The viewer's names were complete; its
selection card now says "Flying rafter" too. Tool shed, timber
by kind (frame members): before, as the `kind` column showed them, board
127, blocking 45, stud 33, outrigger 18, plate 13, joist 10, rafter 9,
cripple 7, header 6, jack 6, king 6, rim 2, bargeboard 2, fascia 2, sill 2;
after, the same pieces with the roof's 9 rafters split into 7 rafters and
2 flying rafters. Shopping list unchanged: 99 timber pieces, 21 sheets,
4800 screws. Cut counts by stock line now read, for 50x100: 13 plates, 33
studs, 6 king studs, 6 jack studs, 7 cripple studs, 6 headers, 2 sills, 12
blocking pieces; for the floor: 10 floor joists, 2 rim joists, 9 blocking
pieces; for the roof: 7 rafters, 2 flying rafters, 24 blocking pieces, 18
outriggers, 2 fascias, 2 bargeboards.

- Names for the new kinds in the preview; joint rules for the new joint
  types (marked unverified); the cut list groups king, jack and cripple
  studs; the example's shopping list rebuilt in the pull request.

#### F6. Framing reference and skill update

Done 2026-11-12: `.claude/skills/timber-build/framing.md` and the section
"Turning a comment into a change" in `SKILL.md`. Sources read (all
2026-11-12): the 2021 IRC chapters 5, 6 and 8 on UpCodes' Colorado copy
(the ICC site refused automated access); Fine Homebuilding on top plates
and a 2005 forum thread on ladder overhangs; This Old House on corners;
Wikipedia on framing and bargeboards; NHBC Standards 2025 chapter 6.2 (a
hosted PDF copy); LABC Warranty Technical Manual v11 section 6; the
Trussed Rafter Association gable ladder card (12 March 2026); the DOE
Building America guide to gable overhangs (2020) and a Simpson Strong-Tie
blog (2016). Not read: the AWC Wood Frame Construction Manual, TRADA
guides, Eurocode 5, the IRC header table cells, IRC R502.8.1 notch limits.
Marked unverified in the reference: the 24 in. top-plate joint offset (seen
only in a search summary), the 24 in. cantilevered lookout limit (blog
only), the 1.5 m unblocked joist span (the workbench's own), fixing counts.
Open: no source found for panel staggering in the IRC pages read, nor a
UK/EU figure for a verge overhang on a fly rafter.

Plan as written:

Files: `.claude/skills/timber-build/framing.md`, `SKILL.md`.

- Each convention in plain words, with a source and the date read (for
  example the IRC wall framing section, TRADA or NHBC guidance).
- In the skill, "Turning a comment into a change": a rule becomes an
  option, a one-off becomes an edit, a missing rule becomes a library
  change in its own pull request; and always rebuild, read the checks, and
  look at the preview before replying.

#### F7. Rebuild the example and answer the comments

Done 2026-11-12: the garden shed (version 2, after the trial's version 1)
and the tool shed rebuilt and both preview pages republished at their old
links. Checks: nothing to fix on either; the garden shed keeps one "check"
(12 mm roof sheets on rafters 600 mm apart, a library default; the tool
shed uses 15 mm). Garden shed: 269 pieces, 92 timber lengths, 16 sheets.
Tool shed: 315 pieces, 108 timber lengths, 21 sheets. The six comments:
1 floor blocking centred (F2); 2 three-stud corners (F1); 3 window on
kings, jacks, a two-ply header and a sill on cripples (F1); 4 double top
plate, lapped at the back corners (F1); 5 door header on jack studs (F1);
6 rafter bays closed over both walls, fascia front and back, and a 150 mm
side overhang on a ladder with a bargeboard (F2). The floating pieces: the
stepped side cladding, now cut to the roof line (F2), to confirm in F8.

Plan as written:

- Rebuild `examples/garden-shed/`, compare before and after in renders,
  republish the page, and answer each of the six trial comments with what
  changed. Checks: nothing to fix.

#### F8. Second trial

- The owner tries the shed again, by looking and by asking for changes
  through comments, and the next round of rules comes from that.

Progress (2026-11-12): first round of comments back. Three small fixes:
cripples were on the stud layout, so they looked lopsided under and above
both windows: now evenly spaced and symmetric across each opening
(`framing.even_cripples`); the roof deck stopped at the inner face of the
fascia and bargeboards, leaving their tops bare: it now runs out to their
outer faces (the back fascia's top drops by its thickness times the
pitch's tangent so the deck clears it; the front one leaves the same gap
under the deck's outer edge, which the drip edge covers), and the roofing
is bought for that area; and fixings (nails by weight, structural screws
where they are stronger), on its own branch. The European default roof
deck is 15 mm, so the example shed has nothing left to check.

## Still out of scope

Gable roofs (T8), lean-to sheds, doors and windows drawn as objects, and
other structures (pergola, raised bed).
