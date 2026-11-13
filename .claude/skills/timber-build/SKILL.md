---
name: timber-build
description: Design a small timber structure in chat in a chat-to-3d-workbench repo - a garden shed (mono-pitch or gable roof on a timber floor), a terrace, a pergola or a summer kitchen (a roof on posts and beams, with an optional floor and walls) - from a few questions to a frame of real members, checks on spans and layout, a shopping list with a cut list and prices, and a 3D preview with layers and an exploded view. Use when someone wants to build a shed, a store, a summer kitchen or a similar small timber building, wants to change one, or asks what to buy or whether a span is enough. Works in European metric sizes and US lumber sizes.
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

A few questions at a time, only what changes the design. Start with **what are
you building**, then the questions for that recipe, then the common ones.

| Recipe (`type`) | What it is | Use it when |
|---|---|---|
| `pent-shed` | A shed with a mono-pitch roof (one slope, front high) on a timber floor | Storage or a workshop against a fence or wall; the simplest shed |
| `gable-shed` | A shed with a ridge and two slopes on a timber floor | More headroom, a door in the gable end, a classic look |
| `terrace` | A raised deck on posts and beams with joists and boards | A deck or patio platform, no roof |
| `pergola` | An open roof of beams, rafters and optional slats on posts | Shade or a frame for climbing plants; free standing, no walls |
| `summer-kitchen` | A roof on posts and beams, optionally with a floor and up to three walls | A covered cooking or sitting place; not for a stove or flue |

`tools/frame.py --types` prints this list.

- **Shed:** what it is for and what must fit inside; width and depth; the height
  at the front and back (or the eaves); which wall has the door and window, how
  wide and tall, how far along; what it stands on (level, firm supports are
  theirs to prepare); snow. Leave the heights out if they have no preference: the
  planner raises them for the doors and so the roof drains.
- **Terrace:** width, depth, the height of the deck above the ground, and what the
  ground is like (firm soil or slope, clay, rock, an old slab): that picks the
  foundation: ground screws (the default; most soils), pier blocks (level, firm
  ground; low decks) or concrete footings (where they want it permanent).
- **Pergola:** the roofed width and depth, the clear height under the beams, slats
  across the top or open rafters, free standing (it always is: it has no walls).
- **Summer kitchen:** width and depth, the roof shape (mono: one slope; gable: a
  ridge), which sides are closed (back, left, right; the front stays open), a
  deck floor or existing paving, and anything **heavy or hot** (a stove, a flue, a
  wood oven): that is not covered; say so, and that it needs a qualified person.
- **Everyone:** the country (this picks European or US sizes and units), the
  space available and the distance to the boundary, snow (ask how much or look up
  the local design snow load), and a local timber yard if they have one (a price
  list can be imported: `tools/timber_import.py`, see `data/timber/README.md`).

**Changing the rules themselves** (how a wall, the floor or the roof is framed):
the generator is in `tools/timber/` (`platform.py`, `wall.py`, `roof.py`, put
together by `recipes.py`; `planning.py` and `spans.py` choose sizes). Run
`tests/test_blocks_identical.py` after: it fails if any frame, check or shopping
list changed; regenerate its hashes (`tools/golden.py --update`) only when the
change is meant.

## 2. Describe it

One project folder, one description file: `projects/<name>/structure.json`
(`projects/` is ignored by git: do not create a branch, commit, pull request or
changelog entry for a design). Lengths are millimetres, or text in feet and inches
(`"10'"`) for a `us` project. Set only what the person asked for; every other
field has a default from the region's library, and the planner sizes what is left
out. The smallest description for each recipe:

```json
{ "type": "pent-shed", "name": "<name>", "width": 3000, "depth": 2000,
  "openings": [ { "wall": "front", "kind": "door", "x": 1000, "width": 900, "height": 1950 } ] }
```

```json
{ "type": "gable-shed", "name": "<name>", "width": 3000, "depth": 2400,
  "openings": [ { "wall": "left", "kind": "door", "x": 700, "width": 900, "height": 1950 } ] }
```

```json
{ "type": "terrace", "name": "<name>", "width": 4000, "depth": 3000, "height": 600 }
```

```json
{ "type": "pergola", "name": "<name>", "width": 5000, "depth": 3000, "height": 2300 }
```

```json
{ "type": "summer-kitchen", "name": "<name>", "width": 4000, "depth": 3000, "roof": "gable",
  "walls": ["back", "right"] }
```

Add `"region": "us"` (and `"units": "imperial"`) for US sizes. **For every other
field run `tools/frame.py --fields <type> [--region eu|us]`**: it lists each setting
the recipe accepts, in plain words, with its default (in that region's units) and
the allowed values. Add one only when the person asks or a check calls for it.

Rules that matter:
- The file is `structure.json` (an older `shed.json` still works).
- A value the person sets is never overridden by the planner; the checks then report
  on it as they would on any description.
- Say what a recipe leaves out, and **don't bend a recipe into something it isn't**
  (see "What it cannot do yet").
- Footings are bought items and their load capacity is not checked: say so.
  Wind and uplift are not covered for the open structures.
- A terrace above about 600 mm needs a railing in most places (rails and steps
  are not built yet): the check says so.
- A summer kitchen's walls are infill (the posts carry the roof).
- `examples/garden-shed/` is a worked example (read-only).

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

The build prints **How it was planned**: the decisions the planner made (a deeper
joist, closer rafters, a taller wall, how many posts and rows). Before showing the
preview, tell the person each one in a sentence: what was chosen and why ("the floor
joists are 50 x 200 because 50 x 150 is only good for 3.66 m and the span is 3.95 m").
They are also in `out/frame.json` under `decisions` and at the top of `out/bom.md`.
If the person later sets one of those values themselves, the planner leaves it alone.

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

Five building types: a mono-pitch shed, a gable-roof shed (both on a timber
floor, optionally on footings), a terrace, an open pergola and a summer kitchen (a roof on
posts and beams, with a floor and walls if wanted). No hip roofs, no lean-to against a
house, no railings or steps, no doors or windows drawn as objects, no stove or flue, and
no wind or uplift checks on the open structures. The planner sizes joists, rafters and
headers and the layout of posts and rows, not beams (it adds posts instead) or footings. If someone
needs one of these, say so; don't bend a recipe into something it isn't.
