# Printing the aerator in metal

The aerator's ASA version costs a few dollars of filament and works. A metal
one is for when you want it to outlast the tap. Two builds:

| File | Height | Volume | Flow path |
|---|---|---|---|
| `aerator_G1_metal` | 51 mm | 29.3 cm³ | the proven one, as printed in ASA |
| `aerator_G1_metal_compact` | 42 mm | 23.1 cm³ | shorter chamber — only once the ASA compact has proved itself |

Metal print services price roughly by volume. As a guide, JLC3DP quoted the
38 cm³ ASA design at $67 in SLM 316L and $41 in aluminium; scale from there,
or upload the STEP for an exact figure.

## Order it as

**SLM (laser-melted), 316L stainless steel.**

- **Not aluminium.** The tap is nickel-plated brass. Aluminium threaded into
  it and kept wet is a galvanic pair, with the aluminium as the sacrificial side:
  it pits, and the thread can seize within a few seasons.
- **Not binder jetting (BJ).** Its own guidelines rule this part out: holes no
  deeper than 3× their diameter (the channels are 5–6×), no threads, and ±1.3 %
  shrinkage on parts over 50 mm. Sintered parts can also weep under pressure.
- 316L is the food-equipment alloy: no rust, no galling against brass, and it
  does not mind chlorine or frost. It is still not a certified drinking-water
  fitting — the printed internal surfaces are rough (Ra 3–12 µm).

## What differs from the ASA build

All of it lives in the `METAL` preset in `build.sh`.

| | ASA | Metal | Why |
|---|---|---|---|
| Body diameter | 42 mm | 38.5 mm | steel is 10–20× stronger; walls ≈ 2 mm instead of ≈ 4 |
| Nose diameter | 32 mm | 29.5 mm | same |
| Grip | 14 flutes, full height | 14 flutes, stopped below the washer seat | around the thread the wall is ≈ 2 mm and a flute would cut through; below the seat it is 6 mm. Nothing sticks out |
| Rim notches | 14 | none | no room in a 2 mm rim; the sloped top drains on its own |
| Top slope | 1.5 mm | 0.8 mm | a steep slope on a slim rim thins the lip at the mouth |
| Thread clearance | 0.30 mm | 0.45 mm | SLM holds ±0.3 mm with a rough surface — print loose, then chase |
| Hole compensation | +0.15 mm | 0 | an FDM correction; SLM holes are drawn at nominal size |

Everything that does the water's work is identical: the swirl blades, the spine,
the 36 × Ø2.0 channels on three rings, the 5 mm thread with its Higbee start,
and the washer recess.

## How it prints, and why this shape works

SLM spreads a layer of steel powder 20–50 µm thick, melts the part's cross-section
into it with a laser, lowers the plate and repeats. The loose powder around
the part comes out afterwards through any opening, and this part is open
everywhere water flows, so nothing is trapped inside. What it cannot do is
build a flat ceiling over empty space: a downward face flatter than about 45°
needs a support, and a support inside a 2 mm channel could never be removed.

Measured on `aerator_G1_metal`, printed nose down:

- **The bore steps out going up** and the channels are vertical, so neither
  has a ceiling.
- **The swirl-breaker blades** had a flat 2.4 mm underside (97 mm² of ceiling).
  They now have a 45° ridge underneath, like the one on top.
- **The thread's downward flanks** sit at 27.5° (241 mm²). Each is only 0.8 mm
  long, so it prints unsupported but rough. That is what the pass with a G1 tap
  cleans up.

Nothing else overhangs.

## After it arrives

1. **Run a G1 (BSP 1") tap through the thread once.** SLM leaves the downward
   thread flanks rough; one pass of a tap cleans them. A plumber or machinist
   will do it in a minute if you don't own a G1 tap.
2. Blow the powder out of the channels and the bore; flush with water.
3. Fit the same 1" flat washer as the ASA one — it is what seals.

## Thin walls

`../../tools/thinwall.py <file.stl>` measures wall thickness the way JLC3DP's
heatmap does — from every face, straight into the material — and reports any
area under 0.5 mm (rejected) and under 1.2 mm (warned).

| Build | Under 0.5 mm | 0.5–1.2 mm |
|---|---|---|
| Before these fixes (what JLC flagged) | 68.9 mm² | 247 mm² |
| `aerator_G1` (ASA) | 0.01 mm² | 77 mm² |
| `aerator_G1_metal` | 0.00 mm² | 16 mm² |

What remains under 0.5 mm is a few single triangles at edge corners, not a
feature. The 0.5–1.2 mm warnings are the walls between outlet holes in the ASA
build (1.14 mm, they printed fine) and the tips of the thread teeth (inherent
to a G1 thread).

The fixes, in both builds:

- **Higbee start on the thread.** Where a helical thread runs out through the
  top face, its last tooth tapers to a knife edge — that was the red ring in
  JLC's heatmap, down to 0.05 mm. A helical counterbore now removes the partial
  turn, so the thread starts with a full-height tooth ending in a square face.
  The cut is set as high as it can go before the knife edge comes back
  (`HIGBEE_DROP = 0`): it takes 12 % of the tooth material, all of it from the
  turn that was tapering away anyway. Set 0.8 mm lower, as first built, it took
  28 %.
- **Grip flutes run out through the top** instead of stopping 0.5 mm under it.
- **Rim notches moved to the outer edge**, 1.6 mm clear of the mouth chamfer
  instead of 0.2 mm.
- **Spine tip blunted** to Ø1.6 instead of a 0.4 mm point.
- **G3/4 washer recess sized for a 3/4" washer** (24 × 17 mm). It had borrowed
  the 1" one, wider than its own thread.
