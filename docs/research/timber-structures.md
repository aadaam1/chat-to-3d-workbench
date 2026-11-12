# Small timber structures

Status: in progress (timber table, T1 library, T2 frame generator, T3 shopping list, T4 build checks and a first T5 preview done; packages T6, T7 below)
Next: framing conventions, see [framing-details.md](framing-details.md) (steps F1-F8).
Last updated: 2026-11-11

## The question

Can the workbench design a small timber structure (first: a garden storage
shed) in chat, show it in the review page, and produce what to buy: timber,
sheets, screws and nails, with a price that's roughly right?

## Findings

**No open dataset of timber sizes exists** (searched 2026-11-10). Sizes are
regional: EU sawn and planed sections, UK CLS (38×63, 38×89), US nominal
sizes where a 2×4 is really 38×89 mm. Retailers publish their own tables.

**Prior art** (cut lists and frames, none does shed design end to end):
- [compas_timber](https://gramaziokohler.github.io/compas_timber/2.1.2/):
  ETH Zurich, open-source Python, beams, joints and assemblies; no BOM yet.
- [kumiki](https://pypi.org/project/kumiki/): open-source (MPL 2.0) Python
  for timber joinery.
- [OpenCutList](https://github.imc.re/lairdubois/lairdubois-opencutlist-sketchup-extension/releases):
  SketchUp extension; cut lists exported to CSV for optimizers.
- [woodworkers-lib](https://www.skills.sh/dawiddutoit/custom-claude/openscad-cutlist-woodworkers)
  (OpenSCAD cut lists) and [dprojects/Woodworking](https://github.com/dprojects/Woodworking)
  (FreeCAD; cut lists to CSV, JSON, HTML, Markdown).
- [Rogue Engineer cut list optimizer](https://rogueengineer.com/cut-list-optimizer/):
  free, takes a CSV parts list, lays parts out on boards and sheets.

**What a real supplier's data looks like.** Example:
[Székely Fatelep, Budapest, Pallók page](https://szekelyfatelep.hu/fatelep/pallo/),
read 2026-11-10.
- Priced **per piece**: section in cm × length in running metres ("fm"),
  net and gross. Sections 5×10, 5×15, 5×20 cm; lengths 2-6 m, some to 9 m.
- Three variants of each: sawn, planed ("gyalult", about +18%) and
  impregnated against insects and fungus ("impregnált", about +6.5%).
- Converted to volume it's a flat rate up to 6 m: 5×10×2 m = 0.010 m³ for
  1,920 Ft gross and 5×15×2 m = 0.015 m³ for 2,880 Ft are both
  **192,000 Ft/m³ gross**. Longer pieces cost more per m³ (5×15×7 m is about
  210,000 Ft/m³).
- The page also gives the Hungarian naming by size: deszka (board) 12-40 mm
  thick; palló (plank) 43-108 mm thick and wider than twice its thickness;
  léc (batten) narrower than a board; zárléc/heveder 48-100 mm both ways;
  gerenda (beam) over 100×100 mm.
- The same supplier also sells OSB by thickness (6-22 mm), roofing battens,
  BSH glulam beams, cladding, roofing felt and screws: most of a shed's
  shopping list in one place.

## Decisions

- **Model a structure as a list of members, not an OpenSCAD shape.** Each
  member: section, length, position and orientation, kind (stud, plate,
  rafter, joist, board, sheet), layer (frame, floor, walls, roof, cladding,
  openings). Generated in Python from a few numbers (footprint, stud
  spacing, door and window positions). One list drives the preview, the
  cut list, the shopping list and the fastener count. OpenSCAD can't easily
  report where each board ended up, which is why it's not used here.
- **The timber table lives in this repo** as dated price snapshots,
  `data/timber/prices/<region>-<supplier>-<YYYY-MM-DD>.csv`, each built by
  `tools/timber_import.py` from the raw price list kept beside it. Section
  names come from size rules in `tools/timber.py`, so there's no separate
  sections file until a second supplier needs merging. (Done 2026-11-10;
  see `data/timber/README.md`.)
- **Prices: the AI looks them up, scripts do the maths.** At design time,
  Claude reads the user's local supplier pages (or the user pastes a price
  list) and records a dated snapshot. The scripts price the shopping list
  from that snapshot: per piece where the supplier sells by piece, per m³
  otherwise. The user can edit any price. No automated scraper of a
  specific vendor ships in the repo: suppliers' terms differ, and pages
  change.
- **Fasteners are counted from joints.** Nails (the bulk) are sold by
  weight, so the count becomes kg (EU) or lb (US) and is rounded up to box
  sizes (EU 1 / 2.5 / 5 kg, US 1 / 5 lb); structural screws, used only
  where they beat nails, are sold in packs. Rules per joint type (see
  "Nails and structural screws" below), with a spare margin the user can set.
- **A spare allowance on every timber count**, 10% by default, rounded up to
  whole pieces so a small order still gets one spare: knots, splits, twist
  and miscuts are normal. The user can set it per job. (Done 2026-11-10.)
- **Cut lists fit the stock lengths the supplier actually sells** (1D bin
  packing for timber, 2D layout for sheets), with offcuts shown, so the
  shopping list is "6 × 5×10×4 m", not "23.4 running metres".
- **The review page gets a second kind**, "build", next to "print": same
  versions, pins, Send to Claude and Looks good; printability checks
  replaced by dimensions and measuring, layers, an exploded view, a section
  cut and the shopping list.

## Nails and structural screws (read 2026-11-12)

The owner asked for a clear split: nails for the bulk, bought by weight, and
structural screws only where they are better.

**Sources.** (1) IRC 2021 Table R602.3(1) "Fastening schedule": codes.iccsafe.org
returned 403, so it was read second-hand, as a distributor's chart labelled
IRC 2021 (https://www.albanycountyfasteners.com/media/b2/9a/b9/1764612166/nailing-schedule-chart.pdf,
read 2026-11-12) and the ICC Building Code Action Committee proposal text for
the 2012/13 cycle (https://www.iccsafe.org/wp-content/uploads/bcac/IRC-TableR60231.pdf,
read 2026-11-12). The rows differ a little between editions and neither is the
2021 text itself, so every rule stays `unverified`. (2) Nails per lb: Admiral
Steel's list (https://www.admiralsteel.com/assets/pdf/products/nails.pdf: 16d
common 47, 8d common 101, 8d siding 189) and Mitek's table (https://mitek-us.com/wp-content/uploads/files/product/us/tables/Nails.pdf:
16d 48; 8d 94-126 by finish), read 2026-11-12. (3) European nails per kg: no
table found (supplier pages list pack weights, not counts), so they are
computed, `unverified`: pcs per kg = 1,000,000 mg / (7.85 mg/mm3 x pi/4 x d^2 x L
x 1.03), the 1.03 allowing for the head. The same formula gives 47 per lb for
16d and 102 for 8d, matching the published 47 and 101, so it is good to about
5-10%. Results: 3.1 x 90 = 182/kg (library: 180), 2.8 x 65 = 309 (310),
2.8 x 60 = 335, 2.8 x 50 = 402 (400). The US 8d ring-shank (0.113 in.) 137/lb is
computed the same way.

**Schedule read, and the rule used per joint** (EU uses the same counts with
the EU nails; the US spacing is the inch figure, EU its round millimetre):

| Joint | Schedule row | Rule |
|---|---|---|
| `stud-plate` | top or bottom plate to stud, end nail: 2-16d | 2 framing nails |
| `plate-plate` | top plates, laps at corners and intersections, face nail: 2-16d (2021 chart; 2-10d in 2012) | 2 framing nails |
| `plate-lap` | doubled top plates, face nail 16d at 16 in. | framing nail every 400 mm (US 16 in.) |
| `king-jack` | double studs, face nail 16d at 24 in. staggered | every 600 mm (US 24 in.) |
| `jack-header` | no row; the header bears on the jack, end nailed as stud to plate | 2 framing nails |
| `header-trimmer` | continuous header to stud, toe nail 4-8d | 4 toe nails |
| `joist-rim` | joist to band/rim joist, end nail (4-10d in 2012; 2-16d in the 2021 chart); blocking likewise | 3 framing nails |
| `blocking-rafter` | blocking to rafter, same reasoning | 3 framing nails |
| `rafter-plate` | rafter to top plate, toe nail 3-8d (2021 chart; 3-16d box or 3-10d common in 2012) | 2 toe nails and 1 structural screw |
| `fascia-rafter`, `barge-rafter` | no row (1x boards, 2-8d to each bearing in the sheathing rows) | 2 toe-size nails; every 400 mm along the rafter |
| `sheet-frame` | wood structural panel sheathing, 8d at 6 in. edge, 12 in. field | one spacing, 150 mm (6 in.), see below |
| `board-frame` | siding: not in R602.3(1) | 2 cladding nails per stud crossing |
| `corner-stud` | abutting studs at corners, face nail 16d at 12 in. | 1 structural screw every 500 mm (US 16 in.) |

**Sheets.** A `sheet-frame` joint carries only the length of the shared edge,
not whether it is a panel edge or a field line, so one spacing is used: the
6 in. edge spacing. That overcounts the field nails (12 in.) by roughly a
third on a typical shed; nails are cheap, the spare allowance is on top, and
the note in `joint_rules` says so. Splitting edge and field needs the
generator to record which it is.

**Structural screws: why only two joints.**
- *Rafter to plate.* The roof's job is to stay on in wind: a toe nail pulls
  out easily, and the IRC itself says uplift connectors are needed where wind
  or the design requires. One long screw (EU 8 x 160, fully threaded, driven
  at an angle through the rafter into the plate) per rafter and plate beats 3
  toe nails; 2 toe nails stay to hold the rafter in place while screwing. In
  the US a hurricane or rafter tie is the usual answer; a structural screw
  (1/4 x 6 in.) is shown so the rule works in both regions.
- *Corner stud.* The two walls are built flat and stood up separately, so at
  the corner the end studs have to be pulled tight to each other with the
  wall already standing. A screw draws the pieces together and can be driven
  in an awkward position; a nail cannot be set properly without a swing and
  loosens in the corner. EU 6 x 120 every ~500 mm (range 400-600 considered);
  US 1/4 x 5 in. every 16 in. Sizes and spacings are not from a load table.
- No other joint was given screws: the schedule is nails throughout, and a
  strong case was not found in a source (so no screws for headers or floor
  rim joists). Pack sizes of 50/100 are an assumption.

**Not found / unverified.** The official IRC 2021 text; any European supplier
table of nails per kg; manufacturer load data for the structural screws (their
spacing and diameter are judgement); the EU sheathing and cladding nail sizes
(2.8 x 50 and 2.8 x 60 ring-shank) are the common sizes for 15-18 mm OSB and
19 mm shiplap, not from a standard. Prices: the Hungarian snapshot has no
fastener rows, so fasteners stay unpriced.

## Done so far

- 2026-11-10: the timber table. A first snapshot of Székely Fatelep
  (295 products: planks, boards, beams, battens, OSB), the importer, and
  `tools/timber.py` (`classify`, `sections`, `buy`: cheapest stock length
  for a set of cuts). Example: 12 impregnated 5×10 studs at 2.4 m cost
  30,678 Ft as 6 × 5 m, against 36,816 Ft as 12 × 3 m.

- 2026-11-11: T1 built: `data/timber/library/{eu,us}.json` and
  `tools/timberlib.py`. Read and cited: PS 20-20 Tables 3 and 4 (US dressed
  sizes), NDS 2018 Supplement Table 4A (SPF No. 1/No. 2: Fb 875 psi, E
  1,400,000 psi, G 0.42), EN 338:2016 C24 (bending 24 MPa, E 11 GPa; via a
  published implementation of Table 1, not the standard itself). Left
  unverified and marked so: fastener sizes and packs, joint rules, shiplap
  cover width (eu), US OSB thicknesses and stock lengths, roof pitch limits,
  default loads, US density. For T4: the eu grade is a characteristic
  strength, the us grade an allowable-stress value, so the span formulas
  need a different safety factor for each; and sheet support-spacing limits
  are not in the library yet.

- 2026-11-11: T2 built: `tools/frame.py <spec.json> --out <frame.json>`, the
  fixtures `tests/fixtures/shed-eu.json` and `shed-us.json`, and
  `tests/test_frame.py`. The frame file follows the contract above (field
  names, units, axes, ids); nothing in it had to change. Fixtures give 211
  members and 391 joints (eu) and 220 and 488 (us). Where the plan left a
  choice, this is what was decided; T3-T5 should rely on it:
  - *Spec.* The `spec` in the frame file is the spec with every default
    filled in and lengths in mm, not the raw input. Two optional fields were
    added: `name` (default `garden-shed`) and `roofing` (default
    `roofing-felt`). Lengths may be written as text (`"10'"`, `"2.4 m"`).
    With no heights, the front is 2300 and the back 300 lower (the library
    has no height default). The library's `items.plate` is not used: plates
    are always the `frame_item`.
  - *Datums.* The floor frame sits at z 0. `height_front` and `height_back`
    are measured from z 0 to the top of the wall's top plate. An opening's
    `x` runs along the outer footprint from the front-left corner (X for
    front and back walls, Y for left and right). `sill` and `height` are
    measured from the top of the floor deck. The plan's example window
    (left wall, sill 1100, height 600, back height 2000) does not fit with a
    100 mm header; the fixture uses sill 1000.
  - *Walls.* A wall's depth is the frame section's wide side; studs stand on
    edge, plates lie flat. Sheathing and cladding sit outside the spec's
    width and depth, so the finished shed is wider by twice the sheet and
    board thickness each way; the side cladding wraps past the front and
    back skin. Skin starts at the floor deck top (the rim joists stay bare).
    Studs: flush at both ends, the rest centred on multiples of the spacing,
    a regular stud dropped if it would sit closer than one stud thickness to
    the end stud. At an opening: two full-height trimmers (no king studs), a
    header, short `cripple-NN` studs (kind `stud`) above and, for a window,
    below, left out when shorter than 50 mm. The header is the frame item on
    edge, flush with the outer face. The sill is the frame item flat, kind
    `blocking`. A door cuts the bottom plate into `plate-bottom-01/02`.
    A trimmer, header or sill needs 2 x stud thickness of room from a corner
    or a neighbouring opening.
  - *Side walls and roof.* Side walls are framed to the back height. The
    `infill-NN` studs (kind `stud`) run from their top plate to the rafter
    underside at the stud's front face (the long point), `cut_deg` `[0,
    slope]`; those under 50 mm are left out. A rafter's underside passes
    through the back edge of each wall's top plate, so it touches the plates
    along that edge only; the overhang is the horizontal run beyond the
    wall's outer face; `size[0]` is the longest edge (the top edge at the
    front, the underside at the back); `cut_deg` is `[slope, slope]`
    (plumb cuts). The first and last rafter stand over the side walls.
  - *Decks.* Floor sheets lie with the long side across the joists, rows
    along the depth, odd rows starting with a half sheet so the joints
    stagger; sheet edges land on joist centres, so sheets are cut narrower
    than a full sheet (1200 of 1250) and `size` is the cut size. Row joints
    run across the joists, so blocking (kind `blocking`, floor item) sits
    under them. The roof deck does the same on the rafters with sloped
    blocking. A last row under 300 mm shares the row before it.
  - *Sheathing.* One sheet high (a wall taller than the sheet's long side is
    refused), vertical edges on stud or trimmer centres. At a door: one sheet
    notched at its bottom (`outline`, 8 points). At a window: a strip under
    it and a notched sheet over it. Side walls follow the rafter line, so
    those sheets carry an `outline`. `outline` points are in the sheet's
    plane, u along `x` and v along `y` from `origin`. `sheet-frame` has one
    joint per sheet and member whose outer face it covers; `edge_mm` is the
    length of the member's centreline inside the sheet, so a stud in the
    field counts its full length.
  - *Cladding.* A board's box is the cover width (96 mm), not the profile's
    face width, so boards don't overlap in the model; the top course is
    shared with the one below it when it would be a sliver, and the course
    at the back wall height is two boards. Boards are cut at openings; on
    the raked part `cut_deg` is `[0, 90 - slope]`. `board-frame` has one
    joint per board with `b` the wall's top plate (standing for the frame)
    and `crossings` the number of studs it passes.
  - *Joints.* The contract has no type for bottom plate to floor, wall panel
    to wall panel, or blocking, so: `plate-plate` is used for the corners
    (top plates, and bottom plates where a side wall meets the front or back);
    floor blocking uses `joist-rim`, roof blocking `rafter-plate`, a sill
    `header-trimmer`; cripples and infill use `stud-plate` with `b` the
    header, sill, plate or end rafter they bear on. Bottom plate to floor is
    not recorded (T3 may want its own rule).
  - *Other.* Floor members are `treated` with variant `impregnated` when
    `treated_floor` is true (the snapshot's word), else `sawn`. `bought`
    also lists one `door` or `window` per opening. Unit vectors are rounded
    to 6 places, lengths to 0.1 mm. Members are sorted by id.
  - *Tests.* Overlaps are tested with oriented boxes, not axis-aligned ones
    (rafters are sloped, and so are the roof deck and blocking). Rafters are
    tested against the plates and the roof deck and blocking only, as the
    plan says; they are not tested against the infill studs because a
    square-cut stud box touches the rafter at its long point and the cut
    removes the wedge. The stud rule applies to full-height studs and
    trimmers; cripples and infill are checked against what they bear on.

- 2026-11-11: T3 built: `tools/bom.py <frame.json> [--snapshot csv] [--waste 10]
  [--kerf 4] --out <dir>`, `tests/fixtures/bom-small.json` (the hand-checked
  frame; the expected result is written out in `tests/test_bom.py`) and
  `tests/test_bom.py`. Output: `bom.json`, `bom.md`, `cutlist.csv`. What was
  decided where the plan left a choice; T5 and T6 should rely on it:
  - *Cuts.* A timber or cladding member is one cut of `size[0]` (T2: the
    longest edge); angled ends are not shortened, `cut_deg` is only copied to
    the cut list. Grouped by `item` and `variant`. A cut longer than the
    longest stock length is listed under `problems` (exit code 1) and left out.
  - *Stock lengths.* When a snapshot is given and sells the item in that
    variant (matched by `timberlib.price_for` at every length in the snapshot),
    only those lengths are used, each with its gross price. Otherwise the
    library's lengths are used and the line is unpriced: that is the case for
    the cladding (the snapshot has no 121 mm board) and for any variant the
    snapshot lacks. Prices are the gross column.
  - *Packing.* First-fit decreasing; a bin holds cuts while sum + kerf x
    (cuts - 1) fits, and the offcut is the length minus that (the same
    arithmetic as `timber.py buy`, the last cut's kerf is not subtracted).
    Plans: each single length that holds the longest cut, plus a "mix" (pack on
    the longest length, then each piece takes the cheapest priced length, or
    the shortest when unpriced, that still holds its cuts). Best plan: all
    pieces priced -> lowest cost, then least waste; otherwise least waste;
    ties: fewer pieces, then a single length over the mix. No search beyond
    FFD, so the plan is good, not provably optimal.
  - *Spare.* `--waste` is a percentage of the number of pieces the packing
    needs, rounded up with `timberlib.allowance`, per timber item/variant, per
    sheet item and per fastener count. Not spare cuts as in `timber.py buy`
    (that packs extra cuts): here the spare is whole pieces of the longest
    stock length bought (a spare can then remake any cut), whole sheets, and
    loose fasteners. Spare pieces are priced and shown in the buy line but
    have no member ids. A sheet spare of ceil(10%) is a lot for a shed (3 spare
    on 15 sheets on the eu fixture); the planning session may want sheets
    exempted.
  - *Sheets.* A sheet is `max(size_mm)` x `min(size_mm)`; x runs along the
    long side. Each part's bounding rectangle (`size[0]` x `size[1]`) is
    packed as drawn (turned only if it doesn't fit as drawn, and only when the
    library entry's `can_rotate` is true), and also with every part turned
    long side along the sheet; the layout with fewer sheets wins, a tie going
    to as drawn. FFD by height, shelves, the kerf between parts and shelves.
    A part with an `outline` takes its whole bounding rectangle. The shelf
    algorithm is not optimal: the eu fixture needs 15 sheets for 21 parts, many of them partly empty.
  - *Fasteners.* `per_joint` n per joint; `per_crossing` n times the joint's
    `crossings`; `every_mm` is `ceil(edge_mm / every_mm)` per joint (a joint
    with 0 mm edge gets none). Then the allowance, then the smallest total of
    whole packs at least that (fewest packs among equal totals). Not counted,
    and said so in `bom.md`: bottom plate to floor, panel to panel, fixings of
    bought items. The library has no price for fasteners, so they and the
    bought items are always unpriced, and a priced total is always partial.
  - *Output.* `bom.json` (`schema` 1): `timber` (timber and cladding lines;
    `kind` says which), `sheets`, `fasteners`, `bought`, `totals`, `problems`,
    `notes`; lengths in mm. `bom.md` shows lengths with `fmt_length` in the
    frame's `units` (library names such as "19 x 140 mm" stay as named).
    `cutlist.csv` is always in mm and has one row per member (timber and
    cladding with piece label and stock length; sheets with position and
    `rotated`), no spare rows. Files are deterministic.
  - *Not changed:* `tools/frame.py`, the libraries. Nothing in either needed
    a change.

- 2026-11-11: T5 built (first pass): `tools/make_viewer.py --build <frame.json | versions folder>`
  and build mode in `tools/viewer/viewer.html`. The page draws the members
  itself from the frame file (no mesh files): layers, the exploded view,
  click to name a member, units switch, sizes, comments stored with the
  member's id (`member` on the pin, coordinates in the unexploded model),
  "Before you build" from `checks.json` findings, and a parts list computed
  from the members. A versions folder is `v<N>/frame.json` with optional
  `bom.json`, `checks.json` and `meta.json` beside it; T6's pipeline should
  write that. Still to do once T3 is in: show the shopping list and its
  total in the side sheet (the page already carries `bom` in its data but
  doesn't draw it). Not done: the exploded view for printed projects with
  several parts, and the outline of the version before.
- 2026-11-11: T4 built: `tools/framecheck.py <frame.json> --out <checks.json>`
  and `tests/test_framecheck.py`. Output is `{schema, region, units, factors,
  findings}` (the findings are the shape in the plan; the plan did not say
  whether `checks.json` is a bare list, so T5 should read `findings`). Every
  rule gives one finding, `ok` when it passes, so the page can show what was
  checked. Ids: `span-joists`, `span-rafters`, `span-<header id>`,
  `sheet-spacing`, `sheet-edge`, `stock-length`, `opening-frame`,
  `ground-treated`, `roof-pitch`, `wall-bracing`, and always last
  `guidance-only`. All factors are in one table, `FACTORS`, at the top of the
  file, each with its source and a status (published, standard, assumption).
  Interpretations:
  - *Method.* A simply supported beam under an even load; the allowable span
    is the shorter of the bending span and the deflection span, solved in
    closed form. `eu`: design strength = k_mod * k_h * k_sys * f_m,k / gamma_M
    against 1.35 G + 1.5 Q, checked also against 1.35 G alone with k_mod
    permanent (0.6). `us`: F_b * C_D * C_F * C_r against unfactored D + Q, and
    D alone with C_D 0.9. C24 is characteristic, SPF No. 2 allowable-stress,
    so the two never share a safety factor. Deflection is the full
    characteristic load with the mean E, limit span / 360 (planning
    decision 2026-11-11, replacing the plan's 300), no creep. Service class 2, dry; no wet-service or temperature factors.
    Shear, bearing, lateral stability, wind and uplift are not checked.
  - *EU factor values are `standard` status:* the EN 1990 and EN 1995-1-1
    values (1.35, 1.5, 1.3, k_mod 0.6 / 0.8 / 0.9, k_h, k_sys 1.1) were not read
    from the standards; they are the values those standards give, as widely
    reproduced. The cross-check below is what vouches for them. Snow is taken
    as short-term (below 1000 m altitude). `us` C_D 1.0 / 1.15 and C_r 1.15
    are from the SFPA publication below; C_F (1.5 at 4 in. to 1.1 at 10 in.
    wide) from a search excerpt of NDS 2018 Supplement Table 4A, not the
    table itself; C_D permanent 0.9 is the NDS value, not read.
  - *Spans.* Joists: rim-joist centre to centre (member length plus the rim
    thickness), as if nothing holds them up between the rims; this is the
    conservative reading, because the frame does not model supports under
    the floor. Rafters: horizontal distance between the centres of the front
    and back top plates, load per metre of plan, own weight and roof deck
    converted from the slope; the overhang is ignored (safe side).
    Headers: the header's own length as the span, the roof strip above it as
    the load (front and back walls: half the rafter span plus the overhang;
    side walls: half a rafter spacing), no k_sys / C_r. Wall and cladding
    weight on a header is not counted. Deck sheets weigh 600 kg/m3 times
    thickness, coverings 0.05 (felt), 0.06 (metal) or 0.15 (shingle) kN/m2:
    assumptions, not read. Snow is a load per m2 of plan.
  - *Rules.* The roof pitch comes from the rafters' slope; the near-ground
    height is z 0 to 150 mm (the floor frame is the lowest thing and sits at
    z 0, so ground is taken as z 0). The sheet-edge rule samples each sheet's
    edge every 25 mm and asks whether a stud, plate, header, trimmer, joist,
    rim, rafter, blocking or brace is directly behind it; more than 75 mm
    without is a `fix`. A free edge of the roof deck that runs across the
    rafters (the eaves and the high edge) is exempt: the deck overhangs its
    last support. An opening needs one header and two trimmers inside its
    width plus 60 mm; the library has no brace member yet, so a wall passes
    with any `sheet` or `brace` member in its group.
  - *Sheet support limits*, new in both libraries as `sheet_spans`
    (`floor_mm`, `roof_mm`, `wall_mm` per sheet key), all marked unverified:
    `eu` osb-12: 300 / 400 / 600; osb-15: 400 / 600 / 600; osb-18 and
    osb-22: 600 everywhere. `us` 15/32 in.: 16 in. floor, 24 in. roof and
    wall; 23/32 in.: 24 in. Leads, not primary sources: NHBC Standards 6.4.19
    (OSB/3 15 mm at 400 and 450 mm centres, 18-19 mm at 600), read through a
    search excerpt; APA span ratings (24/16 on 24 in. roof supports,
    Sturd-I-Floor 19/32 rated 20 oc), through search summaries. The roof
    deck of the eu fixture (osb-12 on 600 mm rafters) is over its limit, so
    that fixture shows a `check`. The eu library default roof deck is
    osb-15 (since 2026-11-12), so a shed on the defaults passes.
  - *Cross-check against published span tables* (the engine is run with each
    table's own dead and imposed load; formulas and factors were fixed
    before the tables were read, nothing was tuned afterwards):
    - `eu`: Timber Development UK, *C24 Span Tables*, Timber Knowledge Sheet
      D.100.02-01, published 1 July 2023, read 2026-11-11 (a copy hosted by
      Taylor Maxwell, the same supplier whose strength sheet the library
      cites): [PDF](https://www.taylormaxwell.co.uk/uploads/files/D.100.02-01_C24-Span-Tables_Design_Span-Tables.pdf),
      floor joists for 1.5 kN/m2 (p. 6) and flat roof joists for 0.6 kN/m2
      (p. 4), maximum clear spans, dead load excluding the joist; the sheet
      says it is guidance and does not state its deflection limit. At
      span / 300 (first version) nine points ran +4.8 to +19.6% longer than the
      table, two of them outside 15%, on the unsafe side. The planning session
      then set span / 360 for both regions, a decision and not tuning: the
      published tables also cover a point load and vibration that this beam
      model leaves out, so the stricter limit stands in for them. At span / 360
      all nine points are within 15% (the test requires it), with these
      differences (formula against table, m):
      floor 45x145 at 600, 2.79 table, +0.2%; 45x195 at 600, 3.97, -1.3%;
      45x220 at 400, 4.19, +3.7%; 45x145 at 400, 3.07, +8.5%; 72x195 at 600,
      4.36, +0.0%; flat roof 45x145 at 400, 3.43, +12.5%; 45x195 at 600, 4.43,
      +2.5%; 45x220 at 400, 5.15, +5.7%; 72x170 at 600, 4.49, +2.5%. The
      warning threshold (a span above 85% of the allowable gets a `check`)
      keeps every `ok` span inside the table values.
    - `us`: 2012 International Residential Code Table R502.3.1(2), floor
      joist spans for common lumber species (40 psf live, L/360, Spruce-pine-fir
      #2), as printed in the 2012 Seattle Residential Code chapter 5
      (pp. 128-129), read 2026-11-11 from
      [seattle.gov](https://seattle.gov/documents/Departments/SDCI/Codes/SeattleResidentialCode/2012SRCChapter5.pdf).
      The table's own criteria (live-load deflection, L/360, the dead load
      including the joist). Eight points (2x6 to 2x12, 12, 16 and 19.2 in.,
      10 and 20 psf dead) all within -0.3 to +0.2%. Also read: SFPA, *Maximum
      Spans: Southern Pine Joists & Rafters*, 2013 ed., pp. 2 and 4 (read
      2026-11-11), for C_D, C_r and the stated method; a Fine Homebuilding
      SPF(S) chart derived from the AWC span calculator (floor joists 2x6 to
      2x12, No. 2 SPF(S), 40 psf live, 10 psf dead) was read as a second look;
      it is 6-8% shorter than the IRC table at 16 in. (2x6 8'-7" against
      9'-4", 2x10 14'-6" against 15'-5"), which fits the lower E of the
      southern SPF group, and it was not used in the tests. No rafter table
      for SPF was found that could be read, so the `us` rafter and header
      checks use the same engine verified on floors only.
  - *Found in T2's output.* The left wall's sheathing seam above the window
    trimmer had no infill stud behind it, so the sheet-edge rule gave a `fix`
    on both shed fixtures. T2 fixes that in its own pull request; the tests
    here exercise the rule only on frames built or edited inside the test.
  - *Closing finding.* `guidance-only` is level `ok`: it is information on
    every run, and as a `check` no structure could ever show as ready.

- 2026-11-11: T2 fixes, found by the T4 checks. (1) Sheathing seams on the
  side walls rose above the top plate with nothing behind them: infill studs
  now also stand over every trimmer (a seam lands on each), replacing any
  layout infill stud that overlaps one; a seam may
  land where the gap above the plate is under 50 mm (too small for an
  infill stud; the plate and the rafter cover it). New ids
  `wall-<side>/infill-NN` continue after the layout ones; no existing id
  moved. (2) No sheathing sheet is narrower than 150 mm: the seam before the
  last sheet moves back to a stud or trimmer centre that leaves it 150 mm,
  and a window or door that would leave a thinner strip at a corner or
  between openings is refused (`openings[i].x`); a window needs a sill of at
  least 150 mm and a width of at least 100 mm. Fixtures: 213 members and 400
  joints (eu), 222 and 497 (us).

- 2026-11-11: T6 built: `tools/build_frame.sh` (description to frame,
  checks, shopping list and a version, with `PRICES=<region>` picking the
  newest snapshot), `examples/garden-shed/`, the timber-build skill, and
  the shopping list in the preview. Two planning decisions changed T3's
  defaults: sheets get no spare unless asked (`--sheet-spare`), and every
  stock length keeps 20 mm for squaring its ends (`--trim`). The shed
  description stays exactly what `tools/frame.py` accepts; the title and
  price region are given to the script, not put in the description.
  Left for after the first trial: T7 (US prices, fasteners and sheet goods
  for the Hungarian list), T8 (gable roof), a trim allowance per cut for
  angled ends, and bottom plate to floor fixings in the count.
- 2026-11-12: building blocks, step B1 (no change in output). `Builder` in
  `tools/frame.py` is split into `tools/timber/`: `store.py` (the `Frame` that
  collects members, joints, bought items and assemblies, the shared `Layout`
  numbers, and the arithmetic and polygon helpers), `platform.py` (the floor),
  `wall.py` (a wall's framing, then its sheathing and cladding cut to an
  outline under the roof line; plus the joints between walls), `roof.py` (a
  `RoofLine`, the pure function of Y the walls fill up to, and the `MonoRoof`
  built on it) and `recipes.py` (`pent_shed`: layout, platform, four walls,
  roof, skins, corners, bought items, edits). `frame.py` keeps the spec rules,
  `generate`, `dumps` and the CLI. The frame file gains a top-level
  `assemblies` list, `{"id", "type", "spans": [{"role", "kind",
  "spacing_mm", "deck"...}]}`, and the span checks read spacings from it
  (falling back to the spec for older frames) with identical findings. The
  oracle is `tests/test_blocks_identical.py` with `tests/golden/frames.json`:
  sha256 of the frame file (without `assemblies`), the check findings and the
  shopping list for 24 descriptions. It was made before the move and must not
  be regenerated by a refactor; `tools/golden.py --update` rewrites it, only
  when output is meant to change (say why in the commit).

## Build plan

Written 2026-11-11. The work is cut into packages that one session can
finish and that can be checked by tests. Each package is its own branch and
pull request (repo routine). **A package's session opens the pull request
and stops; it does not merge.** The planning session reviews and merges.

### Scope of the first version

- One structure type: a **mono-pitch (pent) shed** on a timber floor frame.
  Gable roofs are package T8, after the first trial.
- **Two regions**, chosen per project: `eu` (metric sections, 600 mm
  spacing, 1250 × 2500 sheets) and `us` (nominal lumber, 16 in on centre,
  4 × 8 ft sheets). Everything is stored in millimetres; a `units` setting
  (`metric` or `imperial`) only changes how lengths are shown.
- Roofing (felt, sheet, shingles), windows, doors and hardware are **bought
  items on the list**, not modelled members.
- Every member is a square-cut box. Angled ends are recorded as a cut angle
  for the cut list; the geometry stays a box. Sheets may carry a 2D outline
  for raked edges.

### The frame file (the contract between all packages)

`projects/<name>/out/frame.json`, written by `tools/frame.py`, read by
everything else. Millimetres, Z up, origin at the front-left outer corner
of the floor frame, X = width, Y = depth.

```json
{
  "schema": 1,
  "name": "garden-shed",
  "region": "eu",
  "units": "metric",
  "spec": { "the input spec, copied in": true },
  "members": [
    { "id": "wall-front/stud-03", "kind": "stud", "group": "wall-front", "layer": "walls",
      "item": "50x100", "variant": "sawn", "treated": false,
      "size": [2300, 100, 50],
      "origin": [600, 0, 150], "x": [0, 0, 1], "y": [0, 1, 0],
      "cut_deg": [0, 0], "outline": null }
  ],
  "joints": [ { "type": "stud-plate", "a": "wall-front/stud-03", "b": "wall-front/plate-bottom" } ],
  "bought": [ { "item": "roofing-felt", "qty": 7.5, "unit": "m2", "note": "roof area plus 10% overlap" } ]
}
```

- `size` is `[length, width, thickness]`. `origin` is the member's corner;
  `x` is the unit vector along its length, `y` along its width; thickness
  runs along `x × y`.
- `kind`: `joist`, `rim`, `plate`, `stud`, `header`, `trimmer`, `rafter`,
  `blocking`, `brace`, `board` (cladding, floor boards), `sheet`; since the
  framing details (F1, F2) also `king`, `jack`, `cripple`, `sill`,
  `outrigger`, `fascia`, `bargeboard`.
- `layer`: `floor`, `walls`, `roof`, `sheathing`, `cladding`. `group`: one
  assembly a carpenter builds as a unit (`floor`, `wall-front`,
  `wall-back`, `wall-left`, `wall-right`, `roof`).
- `item` is a key in the region's library (T1). `outline` is a list of
  `[u, v]` points in the member's (length, width) plane when it isn't a
  rectangle (a notched sheet, a board or rafter cut on the slope); `size`
  is then its bounding box.
- `joints` list every fastened contact once, by type: `stud-plate`,
  `plate-plate`, `joist-rim`, `rafter-plate`, `header-trimmer`,
  `sheet-frame` (with `"edge_mm"`, the fastened edge length), `board-frame`
  (with `"crossings"`); since F1 and F2 also `king-jack`, `jack-header`,
  `plate-lap`, `corner-stud`, `blocking-rafter`, `fascia-rafter` and
  `barge-rafter` (the last with `"edge_mm"`).
- Ids are stable and readable; the same spec always gives the same file,
  byte for byte (sorted keys, fixed float rounding to 0.1 mm).

### The input spec

`projects/<name>/shed.json`, written by Claude from the conversation:

```json
{ "type": "pent-shed", "region": "eu", "units": "metric",
  "width": 3000, "depth": 2000, "height_front": 2300, "height_back": 2000,
  "stud_spacing": 600, "joist_spacing": 400, "rafter_spacing": 600, "overhang": 150,
  "frame_item": "50x100", "floor_item": "50x150", "rafter_item": "50x150",
  "sheathing": "osb-12", "floor_deck": "osb-18", "roof_deck": "osb-12",
  "cladding": "shiplap-19x121", "treated_floor": true,
  "openings": [ { "wall": "front", "kind": "door", "x": 1000, "width": 900, "height": 1950 },
                { "wall": "left", "kind": "window", "x": 600, "sill": 1100, "width": 600, "height": 600 } ],
  "loads": { "snow_kn_m2": 1.0, "floor_kn_m2": 1.5 } }
```

Every field except `type`, `width` and `depth` has a default from the
region's library. Since the framing details (F1-F3): `corner`,
`top_plate`, `header_item`, `overhang_side`, `fascia_item`, and `edits`,
one-off changes by piece applied after the rules (see
`tools/frame_edits.py`).

### Packages

| | Package | Depends on | Suited to |
|---|---|---|---|
| T1 | Material library and units | none | a smaller model |
| T2 | Frame generator (pent shed) | T1 | a smaller model, reviewed closely |
| T3 | Shopping list and cut list | T1, T2 | a smaller model |
| T4 | Build checks | T1, T2 | a smaller model, formulas reviewed closely |
| T5 | Preview for builds (layers, exploded view, parts list) | T2's file format | the planning session |
| T6 | Skill, pipeline script and the example shed | T1-T5 | the planning session |
| T7 | A US price snapshot, and fasteners for the Hungarian one | T1 | a smaller model with web access |
| T8 | Gable roof | after the first trial | later |

T1 comes first. Then T2. Then T3, T4 and T5 can run at the same time: they
touch different files. T7 can run any time after T1.

**Every package:** Python 3.12 standard library plus what `.venv` already
has (numpy, trimesh); no new dependencies without asking. A `tests/` file
run with `.venv/bin/python -m pytest tests/<file>`; add `pytest` to
`tools/setup.sh`'s package list in T1. Changelog line under Unreleased.
No personal details. Done means: tests pass, `tools/selftest.sh` prints
READY, pull request open, not merged.

#### T1. Material library and units

Files: `data/timber/library/eu.json`, `data/timber/library/us.json`,
`tools/timberlib.py`, `tests/test_timberlib.py`, `data/timber/README.md`.

- Each library file holds, for its region:
  - `sections`: key, actual `thickness_mm` and `width_mm`, the name people
    use ("2×4", "50×100"), `stock_lengths_mm`, and the usual uses.
    `eu`: 25×50, 25×100, 50×50, 50×75, 50×100, 50×150, 50×200, 75×75,
    100×100. `us`: 1×4, 2×2, 2×3, 2×4, 2×6, 2×8, 2×10, 4×4 with their real
    dressed sizes (a 2×4 is 38 × 89 mm) and stock lengths 8 to 16 ft.
  - `sheets`: key (`osb-12`), material, thickness, sheet size.
  - `cladding`: key, profile, board thickness, face width, cover width.
  - `fasteners`: key, what it is, size, pack sizes.
  - `joint_rules`: fasteners per joint type (see the frame file), for
    example `stud-plate`: 2 × `nail-framing`; `sheet-frame`: one
    `nail-sheathing` every 150 mm of fastened edge. A rule may carry an
    `also` list (`rafter-plate`: toe nails plus one `screw-rafter`). Nails have
    `weight_unit`, `pcs_per_kg`/`pcs_per_lb` and `box_kg`/`box_lb`.
  - `grades`: per structural grade (`C24` for eu, `SPF-No2` for us): bending
    strength, modulus of elasticity, density, with the source table named.
  - `defaults`: stud, joist and rafter spacing, default items for each
    role, default loads, minimum roof pitch per covering.
  - `bought`: roofing felt, drip edge, hinges, a latch: name and unit.
- Every number carries where it came from in a `sources` list in the file
  (standard or supplier page, with the date read). Dressed US sizes and EN
  338 grade values are published facts; cite them.
- `tools/timberlib.py`: `load(region)`, `item(lib, key)`,
  `fmt_length(mm, units)` (metric: `2400 mm`; imperial: feet, inches and
  sixteenths, `7' 10-1/2"`), `parse_length(text)` for both forms,
  `price_for(snapshot_rows, item, length_mm, variant)` that matches a
  library item to the price snapshot by actual size. Keep the existing
  `tools/timber.py` commands working; move shared code into `timberlib`.
- Tests: both libraries load and validate (every default points at an
  existing item; every joint rule names an existing fastener); length
  formatting round-trips for 20 values in both units; the Hungarian
  snapshot prices a 50×100 × 3 m piece.

#### T2. Frame generator

Files: `tools/frame.py`, `tests/test_frame.py`, a fixture spec in
`tests/fixtures/shed-eu.json` and `shed-us.json`.

- `tools/frame.py <spec.json> --out <frame.json>`: validates the spec,
  fills defaults from the library, writes the frame file above.
- Built the way a carpenter would:
  - **Floor:** two rim joists and joists at `joist_spacing` across the
    depth, a deck of sheets laid across the joists, staggered.
  - **Walls:** four framed panels. Bottom plate, top plate, studs at
    `stud_spacing` from one end plus a stud at the far end; corner studs so
    panels can be screwed together; front and back walls run the full
    width, side walls fit between them. Side walls are framed to the back
    height with shorter infill studs up to the rafter line (square cut,
    `cut_deg` recorded).
  - **Openings:** the studs in the opening are left out; a trimmer each
    side, a header on top, a sill under a window, short studs above and
    below.
  - **Roof:** rafters at `rafter_spacing` from front plate to back plate
    with `overhang` at both ends, a deck of sheets, and `bought` roofing
    by area.
  - **Sheathing and cladding:** sheets on the outside of each wall with
    the openings cut out (as an `outline`), then cladding boards laid
    horizontally at the cover width, cut at openings.
  - **Joints** recorded for every contact, as in the frame file.
- Rules the tests enforce: no two members of the frame overlap by more
  than 0.5 mm (axis-aligned boxes for all but rafters; test rafters
  against plates only); every stud touches a plate at both ends; every
  sheet edge that runs along the studs lands on a member; total wall width
  equals the spec; the same spec twice gives identical bytes; the eu
  fixture and the us fixture both generate.
- Not in this package: gable roofs, double top plates, birdsmouth cuts,
  bracing beyond sheathing.

#### T3. Shopping list and cut list

Files: `tools/bom.py`, `tests/test_bom.py`.

- `tools/bom.py <frame.json> [--snapshot <csv>] [--waste 10] [--kerf 4] --out <dir>`
  writes `bom.json`, `bom.md` (what to hand a timber yard) and
  `cutlist.csv`.
- **Timber:** members grouped by item and variant. Cuts are packed onto
  the stock lengths the library (or the snapshot, when given) offers:
  first-fit decreasing with the kerf between cuts, tried for every single
  stock length and for the mix, keeping the cheapest by price when prices
  exist and by least waste when not. Output per item: pieces to buy by
  length, which cuts come out of each piece, and the offcuts.
- **Sheets:** bounding rectangles packed onto sheets with a shelf
  algorithm; rotation allowed for OSB and plywood, not for cladding.
  Output: sheets to buy and a layout per sheet.
- **Cladding boards:** as timber, by cover width.
- **Fasteners:** counted from `joints` with the library's `joint_rules`,
  plus the spare margin. Nails by weight (kg or lb) rounded up to boxes;
  structural screws in packs.
- **Bought items** copied from the frame file.
- **Prices:** per line and in total when a snapshot covers the item; lines
  without a price say so and the total is marked partial.
- The spare allowance from `tools/timber.py` (`--waste`) applies to piece
  counts.
- `bom.md` uses the frame's `units` for every length.
- Tests: a hand-checked small frame (8 studs, 2 plates) gives the expected
  pieces; packing never exceeds a stock length; every cut appears exactly
  once; fastener counts match a hand count; the shed fixtures produce a
  list without errors in both regions.

#### T4. Build checks

Files: `tools/framecheck.py`, `tests/test_framecheck.py`, the sources in
this note.

- `tools/framecheck.py <frame.json> --out <checks.json>`. Each finding is
  `{ "id", "level": "ok" | "check" | "fix", "title", "text", "members": [ids], "at": [x, y, z] }`
  in plain words, the same shape the preview already shows for printed
  parts.
- **Spans, by formula, from the library's grade values:** joists, rafters
  and headers as simply supported beams under an even load (own weight
  plus the spec's snow or floor load times the spacing). Bending stress
  against the grade's strength with a stated safety factor, and deflection
  against span / 300. Say the numbers: "Rafters span 1.9 m; this section
  is good to about 3.1 m at this spacing and snow load."
- **The formulas are checked against published span tables** in the tests:
  at least three table values per region must agree within 15%. Record the
  table, the edition and the date read in this note. If a table can't be
  matched, stop and say so in the pull request instead of tuning numbers.
- **Layout rules:** spacing over the library's limit for the sheet
  thickness; a sheet edge with nothing behind it; a member longer than the
  longest stock length; an opening without a header or trimmers; timber
  within 150 mm of the ground that isn't marked treated; roof pitch under
  the minimum for the covering; a wall with neither sheathing nor a brace.
- Every run ends with the same closing finding: this is guidance from
  simple formulas, not structural engineering, and local rules may apply.
- Tests: each rule has one frame that passes and one that trips it.

#### T5. Preview for builds

Files: `tools/make_viewer.py`, `tools/viewer/viewer.html`.

- `make_viewer.py --build <frame.json> [--bom bom.json] [--checks checks.json]`
  puts the members into the page; versions work as for parts.
- The page draws each member as a box (or an extruded outline) in three.js,
  coloured by kind, in both layouts.
- **Layers:** floor, walls, roof, sheathing, cladding on and off.
- **Exploded view:** one slider. The first half moves the assemblies
  (`group`) apart from the centre; the second half moves the members of
  each assembly apart. Cut open stays.
- **Parts:** click a member to see what it is, its size and where it is on
  the cut list; the shopping list sits in the side sheet with its total.
- **Checks** from `checks.json` replace "Before you order", with "Show on
  the part" flying to `at`.
- **Units switch** (mm, or feet and inches) for sizes shown on the page.
- Comments work on members as they do on parts, and name the member.
- The exploded view also works for printed projects with several parts.

#### T6. Skill, pipeline and the example

Files: `.claude/skills/timber-build/SKILL.md`, `tools/build_frame.sh`,
`examples/garden-shed/`, `README.md`, `CLAUDE.md`, `ROADMAP.md`.

- `tools/build_frame.sh <project>`: spec to frame, checks, shopping list,
  a saved version, and the preview command.
- The skill: what to ask (footprint, heights, door and window, region,
  local supplier), when to look up prices, how to read the checks back in
  plain words, and what never to promise.
- The example shed, with its spec committed and its output rebuilt.

#### T7. More price data

- A US snapshot from one national retailer's public pages, through the
  same importer, with source and date; only what the `us` library names.
- Fasteners and sheet goods for the Hungarian snapshot.
- If a retailer's terms forbid copying prices, record that here and use a
  different source; do not work around it.

## Open questions

- Which US retailer to snapshot (T7), and which further European yards.
- Whether the first trial shows a need for double top plates, diagonal
  bracing or a birdsmouth in the model, or only in the instructions.
- The shed itself: footprint, height, door and window positions. That's the
  first project's intake, not research.
