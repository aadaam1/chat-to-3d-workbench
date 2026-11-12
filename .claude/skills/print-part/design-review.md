# Design review

The questions an experienced designer asks without thinking, written down so
nobody has to know them in advance. Most users are new to making things:
they don't know what they don't know. This list is how they find out, one
plain question at a time.

Use it twice:

1. **At intake** (step 1 of the skill). Pick the questions that apply to
   *this* part, skip the obvious ones, and ask them together in one message,
   in plain words. A phone stand needs four questions, not forty. Where you
   can make a sensible assumption, state it instead of asking ("I'll assume
   it stays indoors").
2. **Before making files** (end of step 3). Walk the whole list against the
   finished design and report it briefly: what you checked, what you
   assumed, what only a test print can answer. Flag anything still open.

When you ask, say **why** it matters, in one short clause. That is how the
user learns: "How long is the thread on your tap? A printed thread that's
longer than the real one leaves a gap that won't seal." Explain a term the
first time it comes up (STL, STEP, ASA, overhang, tolerance); after that,
just use it.

## Purpose and use

- **What does it do, and what would make it a failure?** The failure mode
  ("it falls off", "it leaks", "it snaps when dropped") tells you what to
  design for.
- **How is it used, and how often?** Clicked on once, or opened every day?
  Repeated use wears snap fits and threads.
- **Who handles it?** Adults, children, someone with weak hands? This sets
  grip size, force and safety.
- **One of a kind, or several?** Several means a cheap test of one first.

## Fit: what it touches

- **Does it have to fit something?** Then that thing gets measured, not
  looked up: listings and "standard sizes" are often wrong. Calipers if they
  have them; a ruler and a photo taken straight on if not. Ask for the
  measurements that set the fit, and *how* they were measured.
- **How does it fit?** Each kind needs a different gap:
  - *slides or turns freely* (a lid, a hinge pin): a clear gap;
  - *pushes on and stays* (a cap, a plug): a slight interference or a
    gripping feature;
  - *screws on* (threads): pitch **and** thread length, and print a gauge
    first;
  - *clicks* (snap fit): a flexing arm about 5-10 times as long as it is
    thick, with a sloped lead-in, flexing along the layers, not across
    them; test piece first.
  - *bends* (a living hinge): PETG or TPU only; PLA cracks after a few
    bends.
  The per-process gaps are in `processes.md` (`P_FIT()` in the model).
- **Is a test piece worth it?** Anywhere the fit decides success: a ring of
  the thread, a slice of the socket. Minutes to print, saves the real part.
  Change one thing per set of test pieces, and mark each piece with its
  value (notches, raised numbers) so nobody mixes them up.

## Joining and assembly

- **One part, or several?** One part has no assembly to go wrong. Split only
  when one part can't be printed (too big, an impossible overhang) or must
  be made of two materials.
- **How do parts join?** Screws need a plan: self-tapping into plastic
  (undersized hole), a captive nut (a hex pocket), or a heat-set insert. Glue
  needs a flat contact face. Ask what hardware they have, and check each
  screw's length against the depth of its hole.
- **Cables?** Leave room for the plug to pass, not just the cable, and a
  way to lay the cable in rather than thread it through.
- **Can it be put together, and taken apart?** Check the order: can the
  screwdriver reach, does the last part fit past the first?

## Strength and loads

- **What pushes or pulls on it, how hard, and which way?** A shelf bracket,
  a hook, a handle. Get a number if it matters (kilograms, a person
  leaning).
- **Printed plastic is weakest between layers.** Decide the print
  orientation while designing, not afterwards: the main load runs along the
  layers, not across them, the biggest flat face sits on the bed, and no
  support touches a surface whose fit matters (the scars spoil the fit). Say
  which way up it must be printed.
- **Where would it break?** Sharp inside corners concentrate stress: round
  them. Thin sections next to thick ones crack at the change.
- Back load claims with a number (`tools/` or a formula), and say what only
  a test proves.

## Where it lives

- **Indoors or outdoors?** Sun breaks down many plastics (PLA, PETG over
  time); frost cracks parts that hold water.
- **Heat?** A car in summer reaches 70-80 °C on the dashboard. PLA softens
  near 55-60 °C, PETG near 75 °C, ASA near 95 °C.
- **Water, pressure, chemicals?** Pressure needs walls sized for it and a
  proper seal (a washer or O-ring, not the thread itself). Cleaning
  chemicals, oil and petrol attack some plastics.
- **Food or drinking water?** Printed parts aren't certified for either:
  layer lines hold bacteria and additives are unknown. Say so plainly; steel
  is better but still not certified.

## Material and process

- Recommend one, with the reason, in plain words. The build still exports
  every process the part is set up for, so the choice costs nothing to
  change.
- Rough guide:

  | Need | Good choice | Why |
  |---|---|---|
  | Check fit and shape cheaply | Resin (SLA) | Accurate, cheap; brittle, not for sun |
  | Indoor, low stress, cheapest | PLA (FDM) | Easy, cheap; soft in heat, poor outdoors |
  | Tougher, some heat, some outdoor | PETG (FDM) | Tough, seals well; chalks in sun over years |
  | Outdoors, sun, heat | ASA (FDM) | UV-stable, heat to ~95 °C |
  | Flexible: grips, bumpers, seals | TPU (FDM) | Rubbery; hard to print fine detail |
  | Tough, no supports needed | Nylon PA12 (MJF) | Strong, any overhang; grey, slightly porous |
  | Lasts forever, water, load | Steel 316L (SLM) | Strong, corrosion-proof; priced by volume |

  Only resin, ASA, nylon, 316L and aluminium have presets in
  `tools/processes.json`. For PLA, PETG or TPU, check against `fdm_asa`
  (the same printing rules) and say that's what you did.
- **How big is it?** Every service has a maximum size, and price rises with
  volume (metal and resin) or print time (FDM). Very large parts may need
  splitting.

## Safety

- **Small children:** anything small enough to swallow, or that can break
  into such pieces, is a choking hazard for under-3s (the usual test: it
  fits inside a 32 mm wide cylinder). Say so; don't design around it
  silently.
- **Sharp edges and points:** chamfer or round anything a hand touches.
- **Load that hurts if it fails** (a shelf over a bed, a step, a car part):
  recommend a big safety margin, a cheap test first, and a non-printed part
  if the risk is serious.
- **Heat, flame, electricity:** printed plastics burn and melt. Not for
  anything near a flame or mains power without proper ratings.

## Model hygiene (check yourself; don't ask the user)

- **Cutters pass right through.** Every hole or pocket cut extends past the
  faces it cuts through, or a paper-thin skin is left behind.
- **Pieces overlap; they never just touch.** Two solids that meet face to
  face or along an edge make a mesh that print services reject as
  non-manifold. Overlap them by a small amount (see the Manifold entry in
  `lessons.md`).
- **The section render shows what you meant:** bores go all the way
  through, threads engage, feature counts (holes, ribs, teeth) match.
- **Thin spots that only measuring finds:** the tip of a teardrop hole, the
  corners of a hex nut pocket, a wall between a hole and a groove. The
  checker's thinnest-wall figure and heatmap find them; look.
- **Fixes interact.** Loosening a fit thins the wall around it; a new
  chamfer can open a gap. Re-run the checks after every change, not only
  the first.
- **Every function claim has a number or says it's untested.**

## Cost and effort

- **Cheapest useful first print.** What's the smallest, cheapest thing that
  answers the biggest open question? Print that first.
- **Material is money** in metal and resin: hollow out or slim walls away
  from the load (step 4 of the skill).
- **A new material is a new design, not a new file.** Walls that are right
  in plastic are several times too thick in steel or aluminium, which is
  10-20 times stronger. When a part moves to metal (or between any two
  materials), question every thickness: is it there for strength, for
  printing, or only because the first material needed it? Propose the
  slimmer version with figures: the volume, the price, and the thinnest
  wall against the new process's limit ("38 to 29 cm³, about $67 to $52 in
  316L, thinnest wall still 0.4 mm over the limit").
- **Question the material itself.** Does it really need steel? A cheaper
  material that does the job (ASA outdoors, nylon for toughness) may beat a
  slimmed metal part. Say what the expensive one buys: life, strength,
  heat, looks.
- **Bundle small test pieces** into an order that ships anyway.

---

Several items here were sharpened by reading the design notes of other open
projects in this space, in particular
[wilsonwaters/3d-printing](https://github.com/wilsonwaters/3d-printing),
[nneves/openscad-part-design](https://github.com/nneves/openscad-part-design)
and [rahutchinson/3d-modeling-skill](https://github.com/rahutchinson/3d-modeling-skill).
