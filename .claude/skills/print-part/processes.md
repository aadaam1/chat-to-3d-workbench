# Processes and materials

The numbers the tools use are in `tools/processes.json` (checker) and
`lib/process.scad` (CAD). This page is the reasoning behind them and the
ordering advice.

| Process | Use it for | Clearance (per side) | Wall: rejected / flagged | Overhangs | Must avoid |
|---|---|---|---|---|---|
| Resin SLA (JLC3DP) | Prototypes: fit, feel, function; fine detail (nozzles, small channels) | 0.20 | 0.5 / 0.8 mm | service supports them | closed hollows (trap liquid resin); sun; overtightening (brittle) |
| FDM ASA | Final plastic parts outdoors, cheap | 0.30, holes +0.15 | 0.4 / 0.8 mm | 45°; flat bridges ≤ ~10 mm OK | load along layer lines; elephant foot (chamfer bed edges) |
| SLM 316L | Metal that lasts: water, brass fittings, frost | 0.45, then chase threads with a tap | 0.5 / 1.2 mm | 45°, **no bridging** | flat ceilings anywhere, closed hollows (powder) |
| SLM AlSi10Mg | Lighter, ~40 % cheaper metal | 0.45 | 0.5 / 1.2 mm | 45°, no bridging | bare contact with brass/steel in water (galvanic) |
| MJF/SLS PA12 | Tough nylon, outdoor-grade, no supports | 0.30 | 0.6 / 1.0 mm | any | closed hollows (powder) |
| Binder jetting (BJ) | Not for functional fluid parts | n/a | n/a | n/a | holes deeper than 3× diameter, threads, ±1.3 % shrink over 50 mm, can weep |

## Choosing

- **Prototype first in resin** when fit or flow is uncertain; it is accurate,
  so it tests the geometry the final part will have. It does not test life
  outdoors.
- **ASA** for most garden parts: UV-stable, a few dollars of filament per part.
  Not a drinking-water material (styrene-based; additives unknown).
- **316L** when it must outlast the tap: food-equipment alloy, no galling
  against brass. Still not a certified drinking-water fitting (rough inside,
  Ra 3-12 µm).
- **Aluminium** is fine with precautions: PTFE tape on threads against brass
  or steel, anodize if offered, take it off over winter. Worst case is a
  seized thread after a few seasons, not a sudden failure.

## Metal print rules (SLM), in short

Powder layers 20-50 µm, laser melts the slice, plate drops, repeat. Holes and
channels are free; what costs is **downward faces flatter than 45°** (they
sag or need supports that cannot be removed from inside) and **closed
hollows** (powder stays in). Threads: the downward flanks (27.5° on a BSP
thread) print rough but unsupported because they are short; print 0.45 mm
loose and chase with a tap. Walls ~2 mm are plenty (steel is 10-20× ASA).

## Prices and ordering (EU buyer, 2026)

- JLC3DP quotes, 38 cm³ part: 316L $67, aluminium $41 (≈ $1.76 / $1.06 per cm³).
  Resin parts a few dollars each. Price scales roughly with volume.
- **Shipping: choose DDP** (EuroPacket, or DHL Express DDP when in a hurry).
  Since 1 July / 1 November 2026, IOSS courier options leave the EU duty and
  handling fee to pay on delivery, plus the courier's own fee.
- Shipping and customs are per order, so bundle: add small test pieces
  (gauges, prototypes of other parts) to an order that ships anyway.
- Heavy steel (brackets, sheet metal): a local laser-cutting + bending shop
  plus hot-dip galvanising is usually cheaper than shipping from China.
  Send DXF (1:1, mm, closed contours) plus a bending drawing.
- ASA filament: about €35-40/kg (2026).
