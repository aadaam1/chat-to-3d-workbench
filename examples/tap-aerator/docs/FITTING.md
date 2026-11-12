# Fitting it to your tap

## Measure the thread. Don't trust the listing.

European garden taps use **BSPP (ISO 228, "G") parallel threads**. The number in
the product name refers to a nominal bore, not to any diameter you can measure,
so "1 inch" tells you nothing directly. What matters:

| Thread | Male OD across the crests | Pitch | Threads per inch |
|---|---|---|---|
| G1/2" | 20.96 mm | 1.814 mm | 14 |
| G3/4" | 26.44 mm | 1.814 mm | 14 |
| G1"   | 33.25 mm | 2.309 mm | 11 |

Put a caliper across the thread crests of the tap outlet. There is no ambiguity
— the three sizes are 6 mm apart.

A common trap: a tap sold as "3/4" inlet, 2 × 1" outlets" may well have G3/4"
outlets with a plastic hose adapter that *looks* bigger. Measure the metal.

If it turns out to be G3/4", use `out/stl/aerator_G34.stl` — same part, different
thread.

## Calibrate the clearance

Printed threads need radial clearance. How much depends on your printer, nozzle,
material and flow calibration — there is no universal number, which is why the
gauges exist.

Print `out/stl/gauge_G1_0.30.stl` (≈10 min, ≈6 g). Screw it onto the tap by hand.

| What happens | Do this |
|---|---|
| Won't start, or binds after a turn | print `0.35`, then `0.40` |
| Starts fine, runs to the bottom, stops square | **use this one** |
| Wobbles, or won't pull the gasket up tight | print `0.25`, then `0.20` |

The rim notches count the clearance: **one notch per 0.05 mm above 0.15 mm**, so
2 notches = 0.25, 3 = 0.30, 4 = 0.35. Print two or three at once and you can
still tell them apart afterwards.

Then edit `aerator.scad`:

```openscad
TAP_FIT = 0.30;     // <- your number
```

and re-run `build.sh`. The same value is used for the body-to-cap thread,
so the cap fit gets calibrated for free.

Note that ASA and PETG shrink differently. Calibrate in the material you'll
actually print the body in.

## Measure the male thread's LENGTH as well

Not just its diameter. The gasket sits at the bottom of the female thread, so
the spigot's end face has to reach that far down:

```
    TAP_THREAD_LEN  =  length of your tap's male thread  -  about 0.5 mm
         (5 mm)          (this tap ~5.5-6 mm; many others 12-14 mm)
```

If the female thread is deeper than the male thread is long, the spigot runs out
of thread before its end touches the gasket. Nothing is compressed, and it drips
no matter how hard you tighten — and tightening harder is exactly the wrong
instinct, because it strips printed threads.

Measure from the end face of the spigot back to where the thread stops.

Too long the other way is a problem too. If the female thread is much shorter
than the male one, fine — the extra male thread just doesn't engage. But if it
is *longer*, the part's top rides up past the end of the tap's thread and
leaves a ring-shaped cup between the two that fills with rain and spray. The
first print used 11 mm on a tap with about 2.5 turns and did exactly that.

Strength is not the limit. 5 mm is just over two turns; the Higbee cut at the
mouth (see `docs/METAL.md`) removes the turn that was tapering to a knife edge,
which leaves about 1¾ turns of full tooth in contact. Against that:

| | Load or capacity |
|---|---|
| Water on the washer, 4 bar (Ø26.5 mm seal line) | ≈ 220 N |
| Water on the washer, 6 bar, worst-case static | ≈ 330 N |
| Hand-tightening preload, ≈ 2 N·m | ≈ 300 N |
| **Worst case, together** | **≈ 630 N** |
| ASA thread stripping: ≈ 300 mm² shear area × 13 MPa (half of solid ASA's, for layer lines) | ≈ 3 900 N |
| 316L thread stripping | over 50 000 N |

So the ASA thread holds about 6× the worst case. Only hand-tighten it: a wrench
can put more load on the thread than the water ever will.

## The gasket does the sealing

**A G thread is parallel.** Unlike a tapered NPT/BSPT thread, it cannot seal on
its flanks no matter how hard you crank it. Every G fitting seals on a flat
washer at the bottom of the bore, and so does this one.

There is a seat in the part for one:

| | Default | Parameter |
|---|---|---|
| Washer OD | 30.0 mm | `GASKET_OD` |
| Washer ID | 23.0 mm | `GASKET_ID` |
| Thickness | 2.0 mm | `GASKET_T` |
| Compression | 0.6 mm (30%) | `GASKET_SQUASH` |

Use a standard 1" flat hose-fitting washer — the kind that comes in the bag with
every hose coupling — or cut one from 2 mm EPDM or nitrile sheet with a wad
punch. Silicone is too soft and extrudes out under pressure.

If yours is a different size, set the three numbers above and rebuild; the seat
depth follows automatically.

## Fitting it

1. Drop the gasket into the seat at the bottom of the threaded bore.
2. Screw the part onto the tap, **hand tight only**. If it drips, tighten a
   little more; if it still drips, your gasket is too thin or too hard, or the
   male thread is too short to reach it — see above. Don't reach for a wrench;
   you'll strip printed threads long before you improve the seal.

That's the whole assembly. There is nothing else to put together.

## Tighten it onto the gasket

Screw it down until you feel the gasket compress, not just until it feels snug.
The seal is a flat washer at the bottom of the thread, so a part that is only
half wound on is sealing against nothing — it will drip out of the thread, and
tightening a quarter turn more usually fixes it.

## Cleaning

Garden water carries grit, and the narrowest passages in the part are the 36
exit channels, Ø2.0 mm. Unscrew it and back-flush under a tap; turn a 2.0 mm
drill bit through any channel that stays blocked.
A vinegar soak every so often deals with the biofilm that layer lines attract.

## If the stream still isn't uniform

In order of likely payoff, all one-line changes in `aerator.scad`:

1. `EXIT_H` up (longer channels, higher L/D) — the single biggest lever.
2. `VANE_H` up, or `VANE_N` to 6 — more swirl removed.
3. `GAP_H` up — more settling length above the channel field.
4. `EXIT_D` down with `EXIT_PITCH` down to match — a finer bundle. Keep
   `EXIT_PITCH - EXIT_D` at 1.2 mm or more, or the walls between channels get
   too thin to print.
