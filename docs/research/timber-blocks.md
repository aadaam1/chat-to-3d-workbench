# Timber building blocks

Status: done (B1-B5 shipped; the lean-to and the open questions below remain)
Last updated: 2026-11-13

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
B3 done (2026-11-13): `foundations.py` (`Footings`: a body and a post base
per point, bought by number, layer `foundations`, kinds `ground-screw`,
`pier`, `footing`, `post-base`), `posts.py` (`Posts`: a grid or points, each
joined to its base), `beam.py` (`Beam`: 1 or 2 plies, `on_top` or `sandwich`,
spans and tributary width recorded per beam), `platform.BoardPlatform` (joists
bearing on beams, deck boards with a gap, staggered, cut on joists) and the
`terrace` recipe (`recipes.terrace`), plus `foundation` on both sheds. New
joints `post-base`, `beam-post`, `beam-cap`, `beam-ply`, `joist-beam`,
`deck-board`; new checks `post-footing`, `beam-bearing`, the board span and
a railing note above 600 mm (the terrace has its own check list, since it has
no walls or roof). The 26 oracle hashes did not move; the two terrace
fixtures are new cases. Library sizes for ground screws, blocks and piers are
typical figures marked unverified (the maker's page was not readable). Knee
braces (`open-bracing`) are left for B4.
B4 done (2026-11-13): `"type": "pergola"` (`recipes.pergola`, `timber/pergola.py` with
`Axes`, `Rafters`, `Slats`, `KneeBraces`). Footings, posts and `Beam` are reused as they
are; the beams sit on the posts (`on_top`, post caps) so a brace has an underside to meet;
`beam_axis` turns the structure. `width` x `depth` is the whole roofed area, rafter tails
and beam ends included. New kind `slat` (`brace` already existed), new joints `brace-post`,
`brace-beam`, `rafter-beam`, `slat-rafter`, new checks `span-rafters` and `span-beams` for
a pergola (snow only), `open-bracing` (a `fix` naming the post), and the existing
`post-footing` and `beam-bearing` (beam ends up to 500 mm past the last post). The oracle's
30 hashes: the 26 old ones did not move, the two pergola fixtures are new cases. Decisions:
knee braces at 45 degrees with centreline legs of 600 mm (24 in. in `us`) in a 75 x 75 mm
(4x4) section, cut plumb against the post and level against the beam, one bolt through the
post and two screws per beam ply; one on each side of a post where at least 700 mm of beam
runs on (end posts: inward only; a 300 mm beam tail has no room). Rafters sit on the beams
without a notch (a notch weakens a beam that already carries the span) and are skew-screwed
into each ply; a hurricane tie is the upgrade for windy sites. Across the beams a rafter is centred over every post and a cross brace runs from each
post's inner face up to it (ripped to the rafter's thickness, rafters at least 38 mm; no tie
beam was needed); `open-bracing` checks both directions and names the post and direction;
joint `brace-rafter`. Not done: sandwich beams, decorative rafter tails, wind and uplift. The 45 degree rule and the leg
length are builders' rules of thumb; no page was read to confirm them (marked unverified in
the libraries, source `pergola-practice`).

B5 done (2026-11-13): `"type": "summer-kitchen"` (`recipes.summer_kitchen`, `timber/kitchen.py`
with `KitchenLayout`, `KitchenWall`, `BeamRoofLine` and `build_floor`). Posts, footings and `Beam` are the
pergola's; the roof blocks now bear on any member they are given: `MonoRoof` and `GableRoof` take a bearing
member or a list of them (the plies of a beam, joint `rafter-beam`) in place of a wall plate, a rafter
positions list (one centred over every post), the beams' inset from the footprint (`eave_inset`: the gable
line and the eave blocking follow the beam's outer face) and a range for the gable ties; a roof on beams
also ties the end pair on its inner side. The mono line is `BeamRoofLine` (through the front beam's inner
top edge and the back beam's outer top edge); the gable keeps `GableLine`. `Wall` got hooks (the ids' prefix
and group, the openings, where the sheathing strips end, the top plate's span, the cladding clip) so a panel
between two posts is a `KitchenWall`, built like a shed's side wall. The oracle: the 30 earlier hashes did not
move; the two kitchen fixtures are new cases. Decisions:
- **Footprint** `width` x `depth` is the outer faces of the posts; the roof overhangs past it as on a shed;
  the beam is centred on its posts and may be narrower (never wider), so its outer face is a few mm in.
- **Walls** are infill, one panel per bay between two posts, the inner face flush with the posts' inner
  faces (the frame must be no wider than a post), so no wall overlaps another or a post. The top plate's top
  is the underside of the beam (the lower beam on the ends); a back wall's plate touches the beam, an end wall's
  infill studs rise to the end rafter. The beams rest on the posts alone, so a **header carries no roof load**
  and is not checked (a note says so). Sheathing sticks out of the post plane by the skin's thickness less
  what the posts are wider than the frame; it is not recessed.
- **Sole plate** under the bottom plates: the wall's frame section lying flat, treated, fixed to the two posts,
  at the post feet without a floor and level with the deck with one.
- **Floor** `terrace`: a terrace platform (own footings, posts when tall enough, beams, joists, boards) filling
  the clear rectangle between the posts' and walls' inner faces, so the deck is built around the posts and
  touches none; the walls' sole plates lie in the strip the posts occupy. The default beams need a floor at
  least about 600 mm high; a lower floor needs joists straight on footings, not built. Footings that would
  overlap the posts' (pier blocks) are refused.
- **Knee braces** on open sides with the pergola's rules; the cross braces go up to the sloping rafter underside
  and are cut along it (`sloped_brace`); the corner posts of a walled end have none, a back line with a wall
  has no along-beam braces. `open-bracing` knows the exemptions.
- A mono roof's side walls taller than a sheet are sheathed in two rows, as a gable end is.
Not done: a front wall or a door-sized opening in the front, a hip roof, a lean-to against a host wall, chimney
and stove, a floor under 600 mm, sandwich beams, wind and uplift.

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

## Planning mechanics, 2026-11-13

An audit of the five recipes found that the defaults built structures with "fix" findings as
soon as the size grew (a 5 x 4 m pent shed: joists 50 x 150 over 3.95 m, rafters, and a roof
that slopes 4.4 degrees under felt that needs 5), and that the default eaves height (2000 mm)
refused any normal door. Decisions: (1) the span formulas move to `tools/timber/spans.py`,
read by the checks and by the planner (`tools/timber/planning.py`); (2) a section or spacing
the description does not name is chosen so its span is "ok" (within 85% of the allowable),
smallest section first, then closer spacing from the library's ladder, then the best with the
check reporting; a named value is never changed; (3) default heights are raised only as far as
the roofing's minimum pitch plus 2 degrees and the tallest opening need, in 50 mm steps; (4)
every choice is a `decisions` entry of the frame (left out when empty, and left out of the
oracle's frame hash like `assemblies`), listed in the shopping list and printed by the build;
(5) `tools/frame.py --types` and `--fields <type>` list what can be built, from one table per
recipe (`tools/timber/fields.py`) that the description's validation also uses. Cladding may now
carry `order_lengths_mm` (special-order lengths, used only when a board is longer than the
stocked ones: a 5 m wide shed's boards are 5.02 m). Open: beams are not resized (the posts get
closer instead; 2 plies of the deepest section is the limit of the library), and a wall taller
than one sheet is still refused.

## Low decks and long pieces, 2026-11-13

Two gaps found with the planner. (1) A terrace 15 to 30 cm up was refused ("use at least 398
mm"; a summer kitchen's floor needed 598 mm). Decision: `frame` is `stacked` or `flush`; the
planner takes stacked when the post base, beam, joist and board fit and otherwise flush: beams on
the post bases, joists hung between them (`joist-hanger` joint, hangers counted), tops level.
The beam is at least as deep as the joist (AWC DCA 6 note on hangers), and sections step down
(50x200, 150, 100) while the spans pass, with closer footings; the lowest height is about 250 mm
on ground screws and 290 mm on blocks and piers (eu). The kitchen floor defaults to that lowest
height. (2) A 6 m shed was flagged (cladding 6.02 m, plates, fascia). Decision: after the frame
is built, `tools/timber/joining.py` cuts a piece longer than its item's longest stock or order
length where a rule gives a sound joint (stud, joist, rafter, post, beam; see framing.md) with a
`butt` joint between pieces and the original's joints repeated for each piece that touches the
other member; floor joists, rafters and ties as long as their span stay flagged with advice.
The upper top plate's joint is 600 mm from the lower plate's (IRC R602.3.2, 24 in., read in the
2012 text). Open: a ridge splice plate is not drawn (the joint sits at a rafter pair), joints
carry no engineering check, and a floor joist longer than the longest stock needs a beam under
it (not built).

## Open questions

- Load capacity of ground screws and footings (needs a manufacturer's
  table that can be read).
- Railings and steps for a raised terrace (a terrace higher than about
  60 cm needs a rail in most places).
