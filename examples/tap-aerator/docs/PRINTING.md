# Printing

## Material

| | Verdict |
|---|---|
| **ASA** | **Use this.** UV-stable, weathers for years, dimensionally stable when wet. Needs an enclosed printer — the X1C/P1S is fine. |
| **PETG** | Good second choice. Excellent layer adhesion, so it seals well, and easy to print. Chalks and gets brittle after a couple of summers of direct sun. |
| **ASA-CF / PETG-CF** | Stiffer, but carbon-filled filaments print more porous and the fibres give water a path along layer lines. Avoid for a pressure part. |
| **PLA / PLA+** | No. Creeps under sustained pressure, softens in a sunlit garden, and UV-degrades in a season. |
| **PA / PA6-CF** | No. Absorbs water and swells — your thread fit will drift. |

The part sees about 3 MPa of hoop stress at 10 bar against ASA's ~45 MPa yield,
so strength is not the constraint. **Watertightness** is. That's what the
settings below are for.

## Orientation

**Outlet face flat on the bed, threaded end up. No supports.**

This is not an accident. The internal geometry was laid out so that every bore
steps *outward* going up, so nothing overhangs:

- the 36 exit channels are vertical holes starting on the first layer
- the chamber appears as the bore opens — material only disappears
- the swirl blades are vertical plates with a 45° ridge on top
- the tap thread prints mouth-up, which is the good way round

**There is no bridge and no downward-facing surface anywhere in the part.** The
first version had one — the underside of a jet plate — and the plate is gone.

The bottom edge carries a 1 mm 45° chamfer, so the first layer's squash-out
("elephant's foot") doesn't leave a lip.

The seven scallops in the top rim and the outward slope of the top face are cuts
into an upward-facing surface — nothing overhangs there either.

Do not "optimise" the orientation. On its side, the thread becomes an overhang
and the swirl blades need support inside a bore you can never reach.

## Settings

Starting point for a 0.4 mm nozzle:

```
layer height        0.16 mm   (0.20 works; 0.16 seals better)
first layer         0.20 mm
wall loops          5         <- the number that matters most
top/bottom layers   6
infill              30%  gyroid
```

Why 5 walls: at 0.42 mm line width that's 2.1 mm of solid perimeter. Water finds
its way through anything less. Most of this part is thick enough to come out
solid anyway, so the infill setting barely bites.

Also:

- **Slow down.** 40–50 mm/s on walls. Interlayer bonding is what keeps water in.
- **No ironing.**
- **Brim** if ASA lifts. The body's footprint is small relative to its height.
- **Do not scale the part.** The thread fit is calibrated, not nominal.

## On thin features

Two numbers in this part look thin, and they are thin for different reasons:

- **Swirl blades, 2.4 mm.** Free-standing, so they follow the usual rule of
  thumb. The hydraulic load on one is under 1 N even at an unrealistic 4 m/s of
  swirl — about 2.7 MPa of bending stress against ASA's ~45 MPa yield — so
  strength was never the constraint. 2.4 mm is so it slices as six solid
  perimeter passes instead of a thin shell, and so it shrugs off a bottle brush.
- **Walls between the exit channels, 1.14 mm at the thinnest.** The first
  version had 0.75 mm webs (54 × Ø1.8 on a hex grid) on the argument that they
  are braced on every side; the person with the printer judged them too fine,
  and he was right to — sub-two-line walls come out ragged or get dropped. The
  field is now 36 × Ø2.0 on three concentric rings, which keeps every wall
  printable while spreading the holes over the whole face.

## Hole sizes

Small vertical holes print undersize. The model compensates with
`HOLE_COMP = 0.15` mm, added to every channel before slicing.

To check your own printer: push a 2.0 mm drill bit through the exit channels. If
it won't pass, raise `HOLE_COMP` by 0.05 and rebuild. If the channels look
visibly oversized and ragged, lower it. It matters less than it used to: with no
jet plate, the tap sets the flow, not the holes.

## Post-processing

- **Deburr the channels.** A 2.0 mm drill bit turned by hand through each one.
  Blow it out with air before first use.
- **Don't sand the sealing face.** The flat at the bottom of the gasket seat
  should stay as printed.
- **Leak test at the sink first.** Screw it onto an indoor tap with the
  gasket, run it, look for weeping through the walls. Easier to spot indoors
  than in a garden.

## Print times and material

Rough, for ASA at 0.16 mm on a Bambu X1C:

| Part | Time | Filament |
|---|---|---|
| gauge | ~10 min | 6 g |
| insert | ~15 min | 6 g |
| cap_aerated | ~50 min | 22 g |
| body | ~1 h 10 | 25 g |

The whole working set is well under two hours and about 60 g.
