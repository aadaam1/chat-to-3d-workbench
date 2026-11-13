# Roadmap

Where the workbench is going, most important first. What's already done is
in the [changelog](CHANGELOG.md).

This is a place to experiment with designing in chat: describe a thing,
look at it in the preview, ask for the next version. Two things hold for
everything here: it has to get someone from an idea to something they can
print, order or build, and scripts, not the AI, make every file.

## 1. Garden structures from building blocks

Sheds, decks, pergolas, summer kitchens, benches: designed in chat,
reviewed in the preview, and turned into a list of what to buy. Each
structure is put together from blocks (a platform, posts, beams, walls, a
roof) by a recipe, so a new shape reuses the rules, checks and shopping
list of the others. Plan in `docs/research/timber-blocks.md`.

- **Blocks:** today's shed is built from a platform, four walls and a
  mono-pitch roof (done).
- **Gable-roof shed** (done: a ridge board, rafter pairs, ties, gable
  walls), then a **pergola**, then a **summer kitchen** and
  a **lean-to**.
- **Foundations:** ground screws, pier blocks and concrete footings under
  a terrace or a shed's floor (done; capacity not checked), then skids.
- **Terrace** (done: footings, posts, beams, joists, deck boards), then
  railings and steps.
- **Ventilated cladding:** battens and an air gap behind the boards.
- **More prices:** a US snapshot, and nails, screws and sheet goods in the
  European one, so the total covers every line.
- **Building it:** the order of assembly, and which piece goes where.

## 2. Parts to print

Functional parts designed in OpenSCAD: brackets, caps, clips, adapters,
mounts, enclosures, hose and thread fittings.

- **Home printers:** material presets for PLA and PETG on a home FDM
  printer, next to the print-service ones.
- **Start from an existing file:** check and preview an STL or STEP made
  elsewhere, and make simple changes to it (holes, cuts, scale, combine).
- **Strength checks as formulas:** pressure in a wall, a thread, a bracket
  or a shelf in bending.

## 3. Ready for more people

- **The first public release** (checklist in
  `docs/research/ready-for-more-people.md`), after the gable-roof shed.
- **A first-run test** with someone who has never used a terminal.
- **A project library:** projects people want to share, kept apart from
  the engine and the curated examples.
- **Plugin install** for people who already use Claude Code plugins.
- **Windows.**

## 4. A sharper review loop

- **Before and after,** two versions side by side.
- **Last round's comments, faded,** on the new version, to check each one
  was dealt with.
- **Measuring** between two points on the model.
- **A photo or a drawing** as the starting point.

## 5. Later

- **Sheet metal:** flat patterns and bend tables for laser-cut-and-bend
  services.
- **Simple furniture joinery:** frames, shelves, benches with real joints.

## Not planned

- Sculpted, organic shapes: figurines, jewelry, filigree. Use a sculpting
  tool for those.
- Printer control and slicer profiles.
- Model marketplaces.
- Finite-element simulation.
- Competing with full CAD programs. This is for people who would rather
  talk than learn one.
