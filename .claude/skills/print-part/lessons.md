# Lessons from earlier parts

Each of these cost a print, an order or a round of feedback. Check new designs
against them.

## Fit
- **Measure the mating thread's length, not only its diameter.** The tap
  aerator's first print had an 11 mm female thread on a ~5.5 mm tap thread:
  the part rode up past the tap's thread and left a ring-shaped cup that
  filled with water. Female thread = male thread length - 0.5 mm.
- **Print a gauge before the part.** Thread rings at 0.20-0.40 clearance, plug
  gauges for click connectors; pick the one that fits, then build.
- **A parallel (G/BSPP) thread does not seal**; the flat washer at the bottom
  of the bore does. Hand-tight is enough; a wrench strips printed threads.

## Printability
- **Thread run-out makes a knife edge** where the helix leaves a flat face
  (0.05 mm thick): metal services reject it as a thin wall. Fix with
  `thread_higbee_cut`, floor at the top face (`HIGBEE_DROP = 0` in the
  aerator): it removes only the tapering partial turn (12 % of tooth
  material; 0.8 mm lower took 28 %).
- **FDM bridges flat ceilings; metal cannot.** The aerator's swirl blades had
  a flat 2.4 mm underside that printed fine in ASA but would have needed
  unreachable supports in SLM. Ridge both ends of anything hanging in a cavity.
- **Features that stop just short of a face leave a thin ledge** (grip flutes
  ending 0.5 mm under the rim). Run them out through the face, or stop them
  well short with a 45° run-out.
- **Cut-in grip flutes only where the wall can take them**: check the wall at
  the flute's deepest point against what is behind it (a thread, a seat).
- **Verify chamfers in a section render.** One bed chamfer came out inverted
  (a thin flange with a groove above it) and only the user's eye caught it.
- **"Optional" features must really be gone from the export.** A disabled jet
  plate stayed in the STL once; check the section render of what you ship.
- Size every recess for its own hardware (the G3/4 build borrowed the 1"
  washer recess, wider than its own thread, and left a feather lip).

## Tooling
- Export **binary** STL (`--export-format binstl`); ASCII breaks the parsers.
- Pass `-D` string values through bash arrays, never `eval`:
  `-D 'GRIP_STYLE="ribs"'` loses its quotes otherwise.
- OpenSCAD renders need `xvfb-run` in a headless container.
- A fresh container loses installed tools: `tools/setup.sh`.
- **Export with CGAL, not Manifold.** OpenSCAD's fast Manifold engine kept the
  volume of a click-on nozzle exact but left 16-1,600 edges shared by four
  faces where pieces only touch (the bed chamfer at z 0.8, the G1 thread on
  its core). Services reject that as non-manifold. `tools/env.sh` exports with
  CGAL and renders with Manifold. Better still: overlap touching pieces by a
  small epsilon so either engine gives a clean mesh.

## Working with the user
- Answer questions; change the design only when asked.
- When files change after something was ordered or printed, say exactly what
  differs and whether it matters.
- Version print packs (`-v6`, `-v7` ...) and say which one replaces which.
- Flow and strength models are estimates: say so, and say how to test (bucket
  and stopwatch; full tap pressure, hand-tight).
