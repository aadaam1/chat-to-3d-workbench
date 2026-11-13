# Timber building blocks

Status: in progress (B1 and B2 done; B3-B5 decided 2026-11-13)
Last updated: 2026-11-12

## The question

Today `tools/frame.py` makes one building: a mono-pitch shed on a timber
floor. People want garden structures of many shapes: a gable-roof shed, a
deck, a pergola, a summer kitchen, a lean-to, a bench. How do we build
those from shared blocks instead of writing a new generator for each, and
keep the short description ("a 3 x 2 m shed, door at the front") working?

## What is general already, and what isn't

General: everything after the generator. A frame is a list of members
(a timber section or a sheet, placed in 3D, with an optional cut outline)
and joints between them. The checks, the shopping list and cut list, the
fixings, the preview, the versions and the one-piece edits all read only
that list. Joints can already be found by contact (`frame_edits.contact`,
`joint_for`), which is what lets blocks meet without knowing each other.

Not general: `Builder` in `frame.py` (1,300 lines). Its floor, wall, roof,
skin and corner methods share one shed-shaped state (W, D, the two wall
heights, the rafter line). The span checks in `framecheck.py` read the
shed's spacings from the spec (`joist_spacing`, `rafter_spacing`), so
they too assume one floor and one roof.

## The model

**A structure is a list of assemblies placed on a site.** An assembly is
one buildable unit with its own rules. It takes a few parameters, a place
(an origin and a direction, or a line it runs along) and what it bears on,
and makes members, joints and three things the others can use:

- **Bearings**: named lines or surfaces other assemblies sit on or fix to
  ("top of the platform", "top plate of the front wall", "top of beam 2").
- **Spans**: for each member role, the span, spacing and load it carries,
  so the span checks read these instead of the spec.
- **Outlines**: the shapes it fills (a wall's outline under the roof
  line), so sheathing and cladding cut to them.

**Joints between assemblies** come from contact, with the existing
`joint_for` table deciding the type (a wall's bottom plate on a platform
is `plate-floor`, a rafter on a top plate is `rafter-plate`, a beam on a
post is `beam-post`).

**Order.** Assemblies are laid out first (where they go, what bears on
what), then built: the roof's underside is known before a wall fills up to
it, and the wall corners are settled before the cladding wraps them.

## The blocks

| Block | Makes | Parameters | Bears on |
|---|---|---|---|
| `platform` | joists, rims, blocking, deck (sheets or boards) | footprint, joist size and spacing, deck | ground screws, posts, skids or beams |
| `posts` | posts with their footings (ground screw, concrete, post base) | grid or list of points, height, section | ground |
| `beam` | single or doubled beam, its joints to posts | line, section, plies | posts or walls |
| `wall` | framed panel: plates, studs, openings (king, jack, header, cripples, sill), corner pieces, sheathing, cladding | line, height (or a sloped top from the roof), openings, corner role | platform or slab |
| `roof` | rafters, ridge, blocking, outriggers, fascia, bargeboards, deck, roofing | shape (mono-pitch, gable, flat), pitch, overhangs | two or three bearing lines |
| `slats` | pergola top: rafters or slats on beams, no deck | spacing, section, overhang | beams |
| `rail` (later) | posts, top rail, balusters | line, height | platform |
| `steps` (later) | stringers, treads | rise, run, width | platform and ground |
| `bench` (later) | legs, rails, seat boards | length, height, depth | ground or platform |

## Recipes keep the short description

A **recipe** turns a short description into assemblies, so nobody has to
write assemblies by hand:

- `pent-shed` (today's shed) = platform + 4 walls + mono-pitch roof. Same
  description file as now, same frame as now.
- `gable-shed` = platform + 4 walls (two with gable tops) + gable roof.
- `deck` = posts + beams + platform (+ rail, steps later).
- `pergola` = posts + beams + slats.
- `summer-kitchen` = posts + beams + roof, with 0–3 walls and an optional
  platform.
- `lean-to` = 3 walls + mono-pitch roof bearing on a ledger at a host wall.

A description can also list assemblies directly for anything the recipes
don't cover; the recipe's output is that same list, so Claude can start
from a recipe and change one assembly.

## Decisions

- **Blocks are Python modules** (`tools/timber/<block>.py`), each with its
  own rules and tests, sharing the conventions in `framing.py`.
- **The first step changes no output.** Today's shed is rebuilt from blocks
  and must produce the same frame, member for member (the four example and
  fixture sheds are compared byte for byte). Only then do new blocks come.
- **Span checks move to per-assembly spans.** The convention checks (corner
  fixing, plate lap, roof edges) run per assembly of the matching kind.
- **The description stays a JSON file**, with `type` naming a recipe;
  `assemblies` is optional and overrides or extends it.
- **Edits by piece keep working.** Member ids get the assembly id as a
  prefix (`wall-front/stud-03` already does).

## Steps

| | Step | Proves |
|---|---|---|
| B1 | Split `Builder` into `platform`, `wall`, `roof` (mono-pitch) and the `pent-shed` recipe; spans per assembly | the same shed comes out of blocks |
| B2 | `gable-shed`: gable roof (ridge board, rafters in pairs, collar or ceiling ties) and walls with gable tops | a second roof shape reuses walls and platform |
| B3 | Foundations, `posts`, `beam`; `terrace` (a deck on posts and beams, board decking); optional foundations under the sheds | a structure with no walls or roof |
| B4 | `pergola`: posts, beams, rafters and slats, knee braces, open on every side | posts and beams reused, an open structure kept standing |
| B5 | `summer-kitchen`: posts, beams and a mono or gable roof on them, an optional terrace floor and 0–3 walls | blocks combine freely |

Each step is its own pull request with renders and the checks passing.

B1 done (2026-11-12): `tools/timber/` holds `store.py` (the frame store,
the shared layout and helpers), `platform.py`, `wall.py`, `roof.py`
(`RoofLine`, `MonoRoof`) and `recipes.py` (`pent_shed`); `tools/frame.py`
keeps the description rules and the command line. Each assembly records
its spans in the frame's `assemblies`, and the span checks read them. The
oracle (`tests/test_blocks_identical.py`, `tools/golden.py`) hashes the
frame, checks and shopping list of 24 descriptions; the hashes were made
before the split and still match.
B2 done (2026-11-12): `gable-shed` (`recipes.gable_shed`, `roof_gable.py`
with `GableLine` and `GableRoof`, which reuse `SlopeRoof`'s `slope_member`
and `slope_block`). The ridge runs along the width; the front and back
walls carry the rafters, the left and right walls are gable walls whose
studs are cut to the roof line. New kinds `ridge` and `tie`, new joints
`rafter-ridge` and `tie-rafter`, and the checks `ridge` and `rafter-ties`.
The two gable fixtures are in the oracle matrix (new hashes only; the pent
hashes did not move). The rules and sources are in `framing.md`.
The first public release (0.6.0) comes after B2 at the earliest; B3–B5 can
follow in public.

## Outdoor structures (B3–B5), decided 2026-11-13

The owner wants open structures next: a terrace, an open pergola, a
summer kitchen. They share three new blocks and one changed one.

**Foundations** (`footing` per post or per bearing point), one kind per
structure, chosen in the description:
- `ground_screw` (default): a steel screw, a size from the library
  (diameter, length, head plate or post bracket), its position marked.
- `pier_block`: a precast concrete block on compacted gravel, with an
  adjustable post base.
- `concrete_footing`: a poured pad or pier (size from the library), with a
  post base cast in or bolted on.
- `none`: today's sheds, unchanged by default; a shed may ask for any of
  the above under its floor frame.
Each is bought (shopping list) and drawn (preview layer `foundations`).
Load capacities are not checked yet: the library gives sizes and spacings
from manufacturers' guidance, marked unverified.

**Posts** (`posts` block): a grid or a list of points; section from the
library (EU 100x100, 120x120, 140x140; US 4x4, 6x6); height from the
footing to the underside of what they carry; a post base on every one.

**Beams** (`beam` block): along a line over posts, one or two plies, on top
of the posts (on a post cap) or as two plies either side of the post
(sandwich, bolted); span check between posts with the tributary width.

**Bracing:** an open structure has nothing like a sheathed wall to keep
it square, so every post-to-beam corner of an open side gets a **knee
brace** (45°, from post to beam), and a convention check
`open-bracing` says where one is missing. Sheds keep their sheathing.

**Platform with board decking:** the platform block gets a board deck
(deck boards with a gap, fixed with two stainless screws per joist) as
well as today's sheet deck; joists sit on beams instead of on the ground.

**Roofs on beams:** the mono and gable roof blocks bear on whatever
member they are given (a wall's top plate today, a beam in B5).

Recipes:
- `terrace`: footings, posts, beams in rows, joists on the beams, deck
  boards; `height` above the ground. Rails and steps later.
- `pergola`: footings, posts, two beams along the long sides, rafters
  across them with an overhang, optional slats on top, knee braces.
- `summer-kitchen`: footings, posts, beams, a mono or gable roof; an
  optional terrace floor; 0–3 walls (for example a back wall), each a
  framed wall from the wall block.

## Open questions

- Load capacity of ground screws and footings (needs a manufacturer's
  table that can be read).
- Railings and steps for a raised terrace (a terrace higher than about
  60 cm needs a rail in most places).
