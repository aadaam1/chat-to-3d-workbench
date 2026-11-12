# Simulating it

If you want to run a flow simulation (CFD) on this, here's what's worth the
time and what isn't.

## What you already have

`out/stl/fluid_domain.stl` is the **water volume**, not the part. It's the negative
space through the part — inlet bore, settling chamber with the swirl-breaker
blades carved out of it, the open bore below them, the 36 exit channels — with a 30 mm inlet extension and a 45 mm outlet extension so the
boundary conditions sit away from the interesting part.

It is produced by subtracting the real geometry from an envelope, so it cannot
drift from the part.

It's watertight and single-volume. Regenerate it after any parameter change:

```bash
openscad --export-format binstl -D 'PART="fluid"' -o out/stl/fluid_domain.stl aerator.scad
```

Adjust the extensions with `fluid_domain(inlet_ext = 30, outlet_ext = 45)`.

## Boundary patches

The domain has four distinct boundary groups, which you'll need to split in the
mesher (by surface normal / feature angle, or by hand):

| Patch | Where | BC |
|---|---|---|
| inlet | top face of the inlet extension | `totalPressure` 2–3 bar, or `flowRateInletVelocity` |
| outlet | bottom face of the outlet extension | `totalPressure` 0 (gauge) |
| walls | everything else | no-slip |

## What's worth simulating

**Single-phase, steady, cheap, and it answers the actual design question.**
`simpleFoam` with k-ω SST:

- **Swirl number at the exit plane.** S = (axial flux of angular momentum) /
  (R · axial flux of axial momentum). This is *the* metric for your problem —
  the whirlpool you're seeing is a high-S flow. Compare S at the plenum inlet
  vs. at the exit. If the swirl breaker and the straightener are doing their
  job, S should drop by more than an order of magnitude.
- **Exit velocity uniformity.** Take axial velocity over the exit plane and
  compute the area-weighted coefficient of variation, σ/mean. Under ~0.15 is a
  visually uniform stream. This is the number to minimise when iterating.
- **Pressure drop vs. flow rate.** Sweep three or four flow rates and compare
  against `flow.py`. If they disagree by more than about 25%, trust the
  CFD and tell me — the 1D model's discharge coefficients are estimates.

That's maybe 1–3 M cells and runs in minutes on a desktop. Everything you'd
actually change in the design shows up here.

**The free jet, if you're curious — two-phase.** `interFoam` (VOF) with air and
water, to watch the stream leave the face and see whether it stays coherent.
Worth it only after the single-phase numbers are in: it's a few hours of setup,
overnight to run, and it won't change the geometry. A print and a bucket answers
the same question in ten minutes.

## Tools, in order of how fast he'll get a result

| Tool | Notes |
|---|---|
| **SimScale** | Browser-based, free community plan, OpenFOAM underneath. Upload the STL, it meshes internal flow reasonably well. Fastest path to a first answer. Community projects are public — fine for this. |
| **OpenFOAM** | `surfaceFeatureExtract` → `snappyHexMesh` → `simpleFoam`. Most control, and the swirl-number post-processing is a short `funkySetFields`/Python job on the exit plane. What he'll want if he's serious. |
| **Ansys Discovery (Student)** | Free, GPU solver, near-real-time. Excellent for sweeping a parameter and watching the answer move. Weaker on quantitative accuracy. |
| **SimFlow** | Free tier, OpenFOAM with a GUI. Good middle ground. **[Step-by-step walkthrough for this part](SIMFLOW.md).** |

## On the STL

It's a faceted mesh, not a CAD solid, which is fine for `snappyHexMesh` and
SimScale but will annoy anyone who wants a clean B-rep. Two options:

- **FreeCAD**: import the STL, Part → *Convert to shape*, then *Refine shape*,
  export STEP. Workable, ugly, fast.
- **Rebuild it properly.** Every dimension is a named parameter at the top of
  `aerator.scad`. Re-modelling the fluid domain in Fusion or FreeCAD from
  those numbers takes under an hour and gives a genuinely clean STEP with
  analytic faces, which meshes far better. Worth it if he's doing more than one
  run.

Bump the facet count before exporting if he sticks with the STL: `SEG` and
`SEGT` at the top of the model control it.

## What I'd actually change based on results

If the exit uniformity is poor, in order of likely payoff:

1. `EXIT_H` up (longer channels, higher L/D) — the biggest lever.
2. `EXIT_D` down with `EXIT_PITCH` down to match — a finer bundle. Keep at
   least 1.2 mm of wall between channels, or it stops printing cleanly.
3. `GAP_H` up — more settling length above the channel field.
4. `VANE_H` up, or `VANE_N` to 6.

All four are one-line changes in `aerator.scad` followed by
`build.sh`.
