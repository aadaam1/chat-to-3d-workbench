# Running the aerator in SimFlow

A concrete walkthrough for `out/stl/fluid_domain.stl`. SimFlow is OpenFOAM with a
GUI, so everything here maps onto plain OpenFOAM if you'd rather script it.

**Do the single-phase run first.** It takes about 20 minutes of clicking and
answers the actual design question — is the swirl gone, and is the exit uniform.
The two-phase air-entrainment run is an overnight job that will not change the
geometry. Resist it until the first one is done.

---

## 0. What you're loading

`fluid_domain.stl` is the **water**, not the plastic. The outer surface of this
STL is the inner surface of the aerator. It is one closed volume with a 30 mm
inlet extension on top and 45 mm of outlet below, so the boundaries sit away
from the interesting flow.

Orientation: **+Z is upstream**, towards the tap. Water flows in the −Z
direction. The inlet is the circular face at the top (Ø23 mm) and the outlet is
the circular face at the bottom (Ø22 mm).

## 1. New case

`File → New Case` → **Multiphase: off**, solver **simpleFoam** (steady-state,
incompressible, turbulent). Single-phase water.

## 2. Geometry

`Geometry → Add → STL` and pick `fluid_domain.stl`.

Units: the STL is in **millimetres**. OpenFOAM works in metres. SimFlow asks on
import — set the scale to **0.001**. Get this wrong and every velocity you see
will be off by a thousand and nothing will converge.

## 3. Mesh

Use the snappyHexMesh workflow (SimFlow calls it *Hex Mesh*).

- **Base mesh**: bounding box with about 1 mm cells. That's roughly
  40 × 35 × 140 cells.
- **Surface refinement**: level 2 on the whole STL, level **4 on the 36 exit
  channels**. Those channels are 2.0 mm across — at 1 mm base cells you'd have
  two cells per channel, which resolves nothing. You need at
  least 6–8 cells across a channel.
- **Boundary layers**: 3 layers, expansion 1.2. Wall friction inside the
  channels is a real part of what makes this work.
- Expect **2–4 M cells**. If your machine struggles, cut the straightener to
  level 3 first and accept that the channel flow is under-resolved — the swirl
  result upstream is still meaningful.

**Check the mesh before solving.** `checkMesh` must report zero errors. Non-
orthogonality under 65 and max skewness under 4.

## 4. Split the boundaries

After meshing you'll have one patch called something like `fluid_domain`. Split
it by feature angle, then assign:

| Patch | How to spot it | Type |
|---|---|---|
| `inlet` | flat disc at max Z | patch |
| `outlet` | flat disc at min Z | patch |
| `walls` | everything else | wall |

## 5. Boundary conditions

| | inlet | outlet | walls |
|---|---|---|---|
| **U** | `flowRateInletVelocity`, volumetric, `0.000232` m³/s (= 13.9 L/min) | `zeroGradient` | `noSlip` |
| **p** | `zeroGradient` | `fixedValue` 0 | `zeroGradient` |
| **k** | `fixedValue` 0.0037 | `zeroGradient` | wall function |
| **omega** | `fixedValue` 45 | `zeroGradient` | wall function |

Fixing the **flow rate** rather than the pressure is deliberate: it converges
far more reliably, and it lets you compare runs at identical flow. 13.9 L/min is
what `flow.py` predicts for the default build on an 18 L/min tap at 3 bar.
The pressure drop is then an *output* — compare it against the model.

Turbulence: k-ω SST. The inlet k and omega above assume 5% turbulence intensity
on a 23 mm bore, which is about right downstream of a ball valve.

### Adding swirl — this is the important bit

**The default inlet is a straight, swirl-free flow, and that isn't your
problem.** Your tap delivers water that is already rotating; the whole point of
this part is to remove that. Simulating a clean inlet tests nothing.

So run it twice:

- **(a) no swirl** — baseline, tells you the pressure drop and the straightener's
  own performance.
- **(b) with swirl** — set the inlet velocity to a `codedFixedValue` or a
  cylindrical profile with a tangential component **equal to the axial one**
  (swirl number ≈ 0.5, a reasonable stand-in for a ball valve at partial
  opening). For axial 0.56 m/s, add 0.56 m/s tangential.

Case (b) is the one that matters. If the exit is uniform in (b), the design
works.

## 6. Solve

`simpleFoam`, 1500–3000 iterations. Watch the residuals; p should fall three
orders of magnitude. Relaxation 0.3 for p, 0.7 for U and turbulence if it
wobbles.

A 3 M cell steady run is minutes to tens of minutes on a normal desktop.

## 7. What to look at

Load the result in ParaView (SimFlow bundles it).

**1. Swirl number at three planes.** Slice just below the inlet extension, just
below the swirl breaker, and at the exit face. For each:

```
S = integral(r * Uz * Utheta dA) / (R * integral(Uz^2 dA))
```

In ParaView: slice → *Calculator* for `Utheta` and `r` → *Integrate Variables*.
You want S at the exit **below about 0.05**. If it's still high after the swirl
breaker, add blades (`VANE_T`, and a second cross rotated 45°) or make them
taller (`VANE_H`).

**2. Exit uniformity — the number to minimise.** Slice a few mm below the exit
face, plot Uz, then *Descriptive Statistics*:

```
CoV = stddev(Uz) / mean(Uz)
```

Under **0.15** looks like a uniform stream. Over 0.3 and you'll see structure in
the water. If it's high, the fixes in order of payoff are in `docs/CFD.md`.

**3. Pressure drop.** Area-averaged p at inlet minus at outlet, times ρ (SimFlow
reports kinematic pressure, so multiply by 998). Compare with
`python3 flow.py`. Within 25% means the 1D model is trustworthy for
iterating and you can stop running CFD for every change.

**4. Look at the chamber.** Velocity magnitude on a mid-plane slice. Below the
blades the flow should fill the bore evenly before it reaches the channel field.
A fast core running straight down the middle means some channels are being fed
much harder than others — that shows up directly in (2) — and `GAP_H` wants to
grow.

## 8. Only then: the free stream

Switch to `interFoam`, air and water, transient, Courant number under 0.5,
with the outlet extension widened so the jet has air around it. Overnight.

This shows whether the stream stays coherent after it leaves the face, which is
the one thing the internal run can't tell you. It's also the one thing a print
and thirty seconds under the tap tells you for free.

## If SimFlow's free tier gets in your way

The community edition caps cell count. Two outs: mesh only the lower half (from
the plenum down — the swirl breaker and everything after it), or use plain
OpenFOAM, where the same case runs unrestricted. SimScale's free plan is another
option with a more generous limit.
