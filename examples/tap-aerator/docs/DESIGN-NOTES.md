# Is the jet plate earning its place?

> **Resolved: removed.** The first print confirmed the case below, and added a
> practical one — 1.4 mm holes are the first thing garden grit blocks. The part
> now ships without the plate (`JET_PLATE = false`), with the channel field
> re-sized for printing: 36 × Ø2.0 mm on three concentric rings (18 / 12 / 6),
> 12 mm long, leaving at least 1.14 mm of wall between holes instead of 0.75. The reasoning below is kept as
> the record of why; its channel figures (54 × Ø1.8) describe the old field.

Short answer: **probably not, on the grounds it was originally added for.**

## Where it came from

It was designed for the first, three-part version, where it had two clear jobs:
regulate the flow, and fire fast jets into a mixing chamber so they would drag
air in. **Aeration was then dropped** — at garden pressure the chamber will not
sit below atmospheric, so the air ports weep instead of breathing. That removed
the plate's second job, and nothing re-examined the first.

## What it still does, and what that is worth

### 1. Equalising the feed to the channels — the weak one

The argument was that the plate forces an even supply across the channel field.
But the channel bundle has substantial resistance of its own, and that is what
actually does the equalising:

| At 16 L/min | |
|---|---|
| Pressure drop across the channel bundle | **3294 Pa** |
| Dynamic pressure of the chamber flow | **195 Pa** |
| Ratio | **17 : 1** |

Each channel is driven by the local total pressure in the chamber minus
atmospheric. A non-uniform arrival perturbs that by at most the dynamic head —
195 Pa on a 3294 Pa drop, which is a **2.9% variation in channel velocity**. The
bundle self-corrects: any channel running fast develops more resistance and backs
itself off.

So the plate is buying a few per cent of uniformity that the straightener was
already providing.

### 2. Debris gate — the real one

At Ø1.4 the jets are the narrowest passage in the part, so grit stops there,
upstream, where you can see it through the threaded end and poke it out.

Without the plate, grit reaches the Ø1.8 channels instead. That is less bad than
it sounds — the channels are straight through and you can clear them with a
1.8 mm bit from the outlet face — but it is 54 small holes instead of 24 larger
ones, and it is on the face you look at.

### 3. What it costs

| | With plate | Without |
|---|---|---|
| Flow @ 2 bar | 12.9 L/min | 14.6 |
| Flow @ 3 bar | 15.8 L/min | **17.9** |
| Flow @ 4 bar | 18.2 L/min | 20.6 |
| 10 L can @ 3 bar | 38 s | **34 s** |

It takes **22% of the total pressure drop** and costs about **13% of the flow**.

It is also the only bridge in the part: its underside is the sole
downward-facing surface. Delete it and the part is completely overhang-free, and
4 mm shorter.

## What the model cannot tell you

All of the above is the same 1D orifice model as `flow.py`, and it assumes
the settling chamber behaves like a plenum — that total pressure is roughly even
across it. The failure mode it cannot see is the tap's incoming jet punching
straight down the middle and through the swirl breaker, arriving at the channel
field as a fast core. If that happens, the jet plate is genuinely doing
something and the numbers above understate it.

That is a question for CFD (`docs/SIMFLOW.md` — exit-velocity uniformity is
exactly the metric) or, far more cheaply, for a print.

## So: print both

```
out/stl/aerator_G1.stl         with the plate       ~16 L/min
out/stl/aerator_G1_nojet.stl   without it           ~18 L/min
```

One parameter, `JET_PLATE`, and about three hours of printer time for the pair.
Hold each one under the tap. If they look the same, keep the simpler, faster,
support-free one.
