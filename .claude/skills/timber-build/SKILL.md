---
name: timber-build
description: Design a small timber structure in chat in a chat-to-3d-workbench repo - a garden shed (mono-pitch or gable roof on a timber floor) - from a few questions to a frame of real members, checks on spans and layout, a shopping list with a cut list and prices, and a 3D preview with layers and an exploded view. Use when someone wants to build a shed, a store or a similar small timber building, wants to change one, or asks what to buy or whether a span is enough. Works in European metric sizes and US lumber sizes.
---

# Build a small timber structure

The same loop as a printed part: talk, look, comment, change. The result is
not a file to print but what to buy and how it goes together. Everything is
made by scripts from one small description, so the same description always
gives the same frame, checks and list. Background and decisions are in
`docs/research/timber-structures.md`; the materials are in
`data/timber/library/` and the prices in `data/timber/prices/`.

## Ground rules

- **This is guidance, not structural engineering.** Say so once, plainly,
  early: the workbench speeds up designing and counting materials; it
  doesn't replace knowing how to build, it can be wrong, and building it is
  the person's responsibility (`DISCLAIMER.md`). The checks are simple
  formulas checked against published span tables. Anything people stand
  under in snow, or that needs a permit, gets a qualified person's eyes.
  Remind them to check local rules on size, height and distance from the
  boundary before buying anything. When the checks say "Looks good",
  don't present it as an approval.
- **A question gets an answer, not a design change.**
- **Numbers come from the scripts.** Never work out a quantity, a span or a
  price yourself; run the tools and read the result back.
- **Explain as you go.** Stud, plate, rafter, joist, sheathing, cladding:
  say what each is the first time. Most people have never framed a wall.
- **Prices are a dated snapshot** from one supplier. Say the date and that
  the yard's current price wins.

## 1. Ask

Only what changes the design, a few questions at a time:

- **What is it for** (tools, bikes, a workshop) and what must fit inside.
- **Where it stands:** country (this picks European or US sizes and
  units), the space available, and what it sits on. The floor frame needs
  level, firm support: slabs, blocks or bearers. That is theirs to prepare.
- **Size:** width, depth, and the height at the front and the back. The
  roof falls from front to back; 300 mm over 2 m is a sensible fall.
- **Door and window:** which wall, how wide and tall, how far along.
- **Snow:** if they get real snow, ask how much or look up the local
  design snow load, and use it.
- **A local timber yard**, if they have one: a price list can be imported
  (`tools/timber_import.py`, see `data/timber/README.md`).

**Changing the rules themselves** (how a wall, the floor or the roof is
framed): the generator is in `tools/timber/` (`platform.py`, `wall.py`,
`roof.py`, put together by `recipes.py`). Run `tests/test_blocks_identical.py`
after: it fails if any frame, check or shopping list changed; regenerate its
hashes (`tools/golden.py --update`) only when the change is meant.

## 2. Describe it

One project folder, one description file:

```
projects/<name>/structure.json
```

```json
{ "type": "pent-shed", "name": "<name>", "region": "eu", "units": "metric",
  "width": 3000, "depth": 2000, "height_front": 2300, "height_back": 2000,
  "openings": [ { "wall": "front", "kind": "door", "x": 1000, "width": 900, "height": 1950 } ],
  "loads": { "snow_kn_m2": 1.0, "floor_kn_m2": 1.5 } }
```

Lengths are millimetres, or text in feet and inches (`"10'"`) for a `us`
project. Every other field (spacings, timber sizes, sheets, cladding) has a
default from the region's library; set one only when the person asks or a
check calls for it. Framing details have defaults too: `corner`
(`three-stud`, `california` or `two-stud`), `top_plate` (`double` or
`single`), `header_item` (a section; two plies of it go over every
opening), `overhang_side` (0, or the rafter thickness + 50 mm up to 300 mm;
a flying rafter on outriggers carries it) and `fascia_item` (the section of
the fascia and bargeboards; the rafter section by default). `examples/garden-shed/` is a worked example (read-only). A gable-roof shed
is `"type": "gable-shed"` with `height_eaves` (to the top of the eave
walls' plates, both the same) instead of `height_front` and `height_back`,
and either `pitch_deg` (25 by default, at least the roofing's minimum) or
`height_ridge` (the top of the rafters at the ridge line, same datum as
`height_eaves`; not both); `ridge_item` and `tie_item` are optional (the
smallest deep-enough section and the rafter section). The ridge runs along
the width, the front and back walls carry the rafters, and the door
usually goes in a gable end (`left` or `right`). A terrace is `"type": "terrace"` with
`width`, `depth` and `height` (the top of the deck above the ground) and
`foundation` (`ground_screw` by default, `pier_block` or `concrete_footing`);
optional: `joist_spacing`, `deck_board`, `board_gap`, `post_item`, `beam_item`,
`beam_plies` and `beam_mount` (`sandwich` or `on_top`), `row_spacing` and
`post_spacing` (caps, otherwise worked out from the span formulas),
`footing_item`, `loads.floor_kn_m2`. Beams run along the width, joists across
them, boards along the width. A very low terrace puts the beams straight on
the post bases (see `framing.md`); above about 600 mm the check says a
railing is usually required (rails and steps are not built yet). Footings
are bought items and their load capacity is not checked: say so. A shed
sits on footings with `"foundation": "ground_screw"` (or `pier_block`,
`concrete_footing`), optionally `footing_spacing` and `footing_item`; they go
under the front and back rim joists. A pergola is `"type": "pergola"` with `width` and `depth` (the whole
roofed area, rafter tails included) and optionally `height` (the underside of the beams above
the ground, 2300 mm), `foundation`, `beam_axis` (`x` or `y`, default along the longer side),
`post_item`, `beam_item`, `beam_plies`, `rafter_item`, `rafter_spacing` (600 mm / 24 in.),
`overhang` (rafters past the beams, 300 mm), `beam_overhang` (beams past the end posts'
centres, 300 mm), `slats` (`"none"`, or `{"item": "25x50", "spacing": 150}`), `braces`
(true), `post_spacing` (a cap, otherwise worked out), `loads.snow_kn_m2`. It builds
footings, posts, two beams, rafters, slats and 45 degree knee braces (see `framing.md`) and
checks the spans and `open-bracing`; `braces: false` is allowed but the check then says to
add them. Bracing across the beams, wind and uplift are not covered: say so. A new shed goes in
`projects/<name>/`, which git ignores: do not create a branch, commit, pull
request or changelog entry for a design.

## 3. Build, check, look

```
PRICES=hu NOTE="what changed" tools/build_frame.sh <name>
```

This writes the frame, the checks, the shopping list (`out/bom.md`) and a
saved version. `PRICES` names the price snapshot's region; leave it out and
the list has quantities only. Then make the preview and publish it the way
the print-part skill describes (one page, no extra files):

```
$PY tools/make_viewer.py --title "<Title>" --build projects/<name>/out/versions --out projects/<name>/out/viewer
```

Read the checks before showing anything:

- **"fix"** findings are yours to resolve first: change the description and
  rebuild. A shed should not reach the person with a known fault.
- **"check"** findings are theirs to decide. Say each one in a sentence,
  with its number, and what the options are (a bigger section, closer
  spacing, a thicker sheet).
- A generator error names the field that cannot be built; fix the
  description, don't work around it.

In the preview the person can switch layers off to see the frame, pull the
structure apart, click a piece to see what it is, and put comments on
pieces. Comments arrive with the piece's id (`wall-front/stud-03`) and a
position in millimetres.

A comment about one piece that no rule should change ("move this stud
100 mm left for the shelf", "leave this block out") becomes an entry in the
description's `edits` list, applied after the rules on every rebuild:

```json
"edits": [
  { "op": "move", "id": "wall-back/stud-03", "by": [-100, 0, 0], "note": "comment 2: shelf" },
  { "op": "resize", "id": "wall-front/plate-top", "length": 3300, "keep": "centre" },
  { "op": "remove", "id": "floor/blocking-03" },
  { "op": "add", "member": { "id": "edit/shelf-stud", "kind": "stud", "group": "wall-back",
      "layer": "walls", "item": "50x100", "size": [1682, 100, 50],
      "origin": [1525, 2400, 218], "x": [0, 0, 1], "y": [0, 1, 0] } }
]
```

`by`, `size` and `origin` are millimetres in the frame's axes (x along the
width, y into the depth, z up); an added piece's id starts with `edit/` and
takes its axes from a similar piece in `out/frame.json`. Joints follow
contact, and the checks run on the result: moving a stud can leave a
sheet seam with nothing behind it, and the checks will say so. If a later
rule change removes or renames a piece an edit names,
the build stops with an error naming the edit: find the piece again in the
preview and update the edit. Anything that should happen to every shed is
a rule or an option, not an edit.

### Turning a comment into a change

Decide what kind of comment it is, then act:

- **It should hold for every shed** ("a header always rests on jacks"): a
  rule. Change a library default or the generator, in its own pull request
  (see the repo-routine skill), with a test. Don't patch one shed.
- **It is this person's choice** (corner style, a single top plate, a
  deeper header, a longer overhang): an option in their description:
  `corner`, `top_plate`, `header_item`, `overhang`, `overhang_side`,
  `fascia_item`, the spacings, or an item field (`frame_item`,
  `rafter_item`, `sheathing`, ...).
- **It is about one piece** and nothing else should follow: an edit, as
  above.
- **Not sure which?** Ask, in one short question.

Whichever it is: rebuild, read the checks, and look at the preview before
you reply. Answer each comment by its number, saying what changed (or why
nothing did). To explain a piece, or judge an unusual request, read
`framing.md` next to this file: each convention in plain words, with a
source and where the workbench differs. Say when a number there is marked
unverified.

## 4. Hand over

When they are happy: `out/bom.md` is the shopping list (what to buy by
stock length, sheet, nails by weight and structural screws by pack, with the cuts from each piece) and
`out/cutlist.csv` the same for a spreadsheet. Say what is **not** on it:
fixings for the base, the door and window themselves beyond a line item,
roofing beyond the felt area, paint or stain. Say which lines have no price.

## What it cannot do yet

Four building types: a mono-pitch shed, a gable-roof shed (both on a timber
floor, optionally on footings), a terrace and an open pergola. No hip roofs,
no lean-to against a house, no railings or steps, no doors or windows drawn as objects. If someone needs one of these, say so; don't bend the shed
description into something it isn't.
