---
name: print-part
description: Design, check and hand over a 3D-printed or metal-printed part in a chat-to-3d-workbench repo (one folder per project under projects/, which git ignores) - from measuring the mating part, through a parametric OpenSCAD model with per-process presets (resin prototype, ASA plastic, SLM 316L or aluminium, MJF nylon), to printability checks (wall thickness heatmap, overhangs, trapped cavities, rough price), renders, a shareable 3D preview page, STEP files for Fusion and a versioned print pack. Use for any new part, any change to an existing one, and any "can this be printed / ordered in X" question.
---

# Print a part

The workshop's way of taking a part from idea to an order. Tools are in
`tools/`, the CAD library in `lib/`, and each project in `projects/<name>/`
(your own designs: the whole folder is git-ignored, never committed). Do not
create a branch, commit, pull request or changelog entry for a design.
`examples/` holds read-only references (`examples/tap-aerator/`). Process rules are in
`processes.md` next to this file and lessons from past parts in `lessons.md`.
Read both before designing anything new. `design-review.md` holds the
questions to ask at intake and to check before making files.

## Ground rules

- **A question gets an answer, not a design change.** Change files only when
  the user asks for a change (or agrees to one you proposed).
- **Checkpoint with pictures.** After every design change, render it
  (`tools/render.sh`, section renders from `build_part.sh`) and look at the
  image before saying it is right. Compare before and after side by side when
  something visible changed.
- **Explain as you go.** Most users are new to this. Say why a question
  matters when you ask it, explain a term (STL, STEP, ASA, tolerance) the
  first time it comes up, and don't assume they know what to ask.
- **Numbers over adjectives.** "Enough", "thin", "strong" each come with a
  measured or calculated figure (thinnest wall, load vs. capacity, flow).
- **Third-party models are for measuring only.** Never commit or redistribute
  files under a no-remix licence, nor derivatives of them.
- Run Python with `-I` on files the user uploads or downloads.

## 1. Intake

Before modelling, read `design-review.md` and pick the questions that apply
to this part. Ask what's missing in **one** message, in plain words, saying
why each one matters; state sensible assumptions instead of asking about the
obvious. At minimum, know:

1. What the part does, and what would count as failure.
2. What it has to fit, if anything. **That thing gets measured**, not looked
   up: diameters, thread pitch *and length*, depths, with how each was
   measured. Photos straight on, with a ruler. For big things (garden,
   pergola), an iPhone LiDAR scan (Scaniverse, export OBJ) for layout, plus
   hand measurements for anything that must fit within millimetres.
3. Where it lives and what it takes: sun, frost, heat, water or pressure,
   chemicals, food contact, load and its direction, who handles it.
4. How many, and the route: usually **a cheap prototype first** (resin, or
   a test piece of the critical fit), then the final material. The model
   must export every process from one file.
5. Which project it belongs to. A change to an existing part goes in that
   part's folder; anything new gets its own `projects/<name>/` (next step).
   Read that project's `README.md` before touching it.

## 2. Model

- `tools/newpart.sh <project> [part]` copies `templates/part.scad` to
  `projects/<project>/<part>.scad` and starts the project's `README.md`
  (nothing to register: projects are not listed in the repo). Keep its structure: process, PART selector, measured
  values (with how they were measured), design values (with why), derived.
- `include <../../lib/process.scad>` gives the per-process numbers: `P_FIT()`
  (clearance), `P_HOLE_COMP()`, `P_MIN_WALL()`, `P_BED_CHAMFER()`,
  `P_TEARDROP()`, and helpers `hole_z`, `hole_x` (teardrop where needed),
  `chamfered_cylinder`, `chamfered_box`, `ring_of`.
- `include <../../lib/threads.scad>` for threads: `internal_thread_cutter`,
  `external_thread`, `thread_higbee_cut` (always on a female thread that runs
  out through a face), named standards `TH_G1()`, `TH_G34()`, `TH_G12()`.
- Design for the strictest process you will order: no flat ceilings
  (slope 45°), no closed hollows, walls ≥ `P_MIN_WALL()`, chamfer bed edges.
- No `hull`, `offset`, `minkowski` or `text`: they block STEP export.
- If the part needs a calibration step (a thread, a snap fit), make a small
  gauge part first (see the
  `gauge` PART in `examples/tap-aerator/aerator.scad`).

## 3. Build and check

```
tools/setup.sh                                   # once per machine (macOS or Linux)
tools/build_part.sh <project>[/<part>] resin_sla fdm_asa slm_316l
```

For each process this writes the STL, the STEP (Fusion-editable), a check
report and renders, all in `projects/<project>/out/<part>/`. It exits non-zero
if any process fails. One file by hand: `tools/partcheck.py part.stl --process slm_316l`.

A project with named variants (sizes, gauges, a handover folder) gets its own
`projects/<project>/build.sh` that writes into its `out/`; see
`examples/tap-aerator/build.sh`. Run `tools/partcheck.py` on its outputs too.

Read every report. What the verdicts mean:
- **FAIL**: a service would reject it, or it cannot be built (walls under
  the red limit, a trapped cavity, a ceiling in metal). Fix it.
- **CHECK**: printable; each finding says where (x y z). Decide per finding
  and say why it is fine (e.g. "0.5-1.2 mm: the thread tooth tips, inherent").
- Single red triangles on sharp edges (under 0.1 mm²) are mesh noise.

Then check **function**, with numbers: flow (`examples/tap-aerator/flow.py` pattern), thread
strength (load vs. stripping area × shear strength, see `examples/tap-aerator/docs/FITTING.md`),
fit against the measured mating part. Say what can only be proven by testing
the print (a bucket and a stopwatch beats any model).

Finally, **design review**: walk the whole of `design-review.md` against the
finished design and give the user a short report: what you checked, what
you assumed, what only a test print can answer, and the print orientation.
Raise anything open before making the files for an order.

## 4. Optimise material (when asked, or when the price matters)

Metal is priced by volume, so material is money there. Look for thick walls
away from the load path (`--md` report: volume; section render), and propose
slimming them with a figure ("−11 cm³, about −$19 in 316L"). Propose, then
build it only on a yes.

## 5. Preview, then iterate on pins

This is where most of the work happens: the user looks, pins what's wrong,
and you change it. Keep that loop short.

**Versions.** Every build whose files changed saves a design version locally
(`out/<part>/versions/v<N>/`, never committed); a rebuild with no change
saves nothing. Label it with what changed: `NOTE="thinner grip"
tools/build_part.sh ...`. A project's own `build.sh` calls
`tools/versions.py snapshot` for the parts people actually print.

```
$PY tools/make_viewer.py --title "<Part name>" --out projects/<project>/out/viewer \
    --process fdm_asa --versions projects/<project>/out/<part>/versions
```

Publish `out/viewer/index.html` with the Artifact tool, every
`v*/p*.b64.txt` in `files` (`contentType: "text/plain"`), and
`capabilities: {"db": {}, "comments": {}}`: `db` keeps the pins with the
page, `comments` lets its "Send to Claude" button post the pins into this
conversation (otherwise the button copies them for pasting). On the first
publish, write the artifact's URL to `projects/<project>/out/viewer/url.txt`;
after that, publish to that `url` (read it first from another conversation),
so the link and the pins stay the same. Files of older versions are kept by
the host, so pass at least the new version's.

The page has two layouts over the same functions, switched at the top right:
**Studio** (the default: just the part in its real material and the bar for
talking to Claude) and **Advanced** (a drawing sheet with sizes and lettered
check notes on the part). In both, a side sheet folds to a strip of icons
(folded at first in Studio): "Before you order" (thin walls, overhangs, one solid shape,
size; the first two paint the part when clicked), the material switch
(every process in `tools/processes.json` gets its own check for the same
shape, and a rough price where a rate is known), the comment list, and in
Studio the version history. The user's feedback is numbered comments
dropped on the part, each written in a bubble at its pin, plus one free
line about the whole part. They are still stored as "pins" (db collection
`pins`).

**When the pins arrive.** "Send to Claude" reaches you as an artifact
comment that lists every pin with its position and note and asks for the
next version. Treat it like the user saying it in the chat: read the pins
(below), say what you'll change, rebuild with a `NOTE=` that names the
change, republish, and reply in the comment thread with a one-line summary
of the new version.

**When it says "looks good".** The page's approve button sends "<part>,
version vN looks good. Please make the print files ... for: <parts>". That is
the go-ahead for step 6: build every process the parts are set up for, make
the print pack zip from that version, send it with SendUserFile, and reply
in the thread with what's in the pack and which earlier pack it replaces.

**Reading pins.** Load the `ArtifactData` tool and `list` the collection
`pins` for the artifact's URL. Each pin: `v` (version), `n` (number),
`part` (label), `x y z` (model millimetres, the same coordinates as the
`.scad`), `nx ny nz` (which way the surface faces there), `note`. "Pin 3"
means pin 3 on the newest version unless the user says otherwise. Before
changing anything, say which feature you think each pin is on (which
module, which parameter) and what you'll change; if a pin is ambiguous, ask.
A rebuild makes a new version, which starts with no pins.

**Without the Artifact tool** (a terminal without claude.ai, or a file to
send someone): add `--inline` for one self-contained HTML file. Pins are
then kept in that browser, and "Copy for chat" gives text to paste back.
To check it locally, cdn.jsdelivr.net may be blocked in the sandbox: serve the
folder over http and route the three.js URLs to an `npm i three@0.160.1` copy.

## 6. Hand over

- The source (scad, build script, README, docs, renders in `img/`) stays in
  `projects/<name>/`, which git ignores: a design is **never committed**, and
  gets no branch, pull request or changelog line. `out/` is rebuilt from the
  source.
- Print pack: a zip in the scratchpad named `<project>-prints-v<N>.zip`, built
  from `out/`, with
  folders per material (`asa/`, `metal/`, `resin/`), each part as STL and
  STEP, and a `READ-ME-FIRST.txt` that starts with: "Checks passed is not a
  guarantee: test the part before you rely on it. What you make, and how you
  use it, is your responsibility (DISCLAIMER.md in the workbench)." Say which
  earlier pack it replaces. Send it with SendUserFile.
- Ordering notes in the project's README or `docs/`: process and material to choose (and not to),
  post-processing (chase threads with a tap, flush powder), the washer or
  hardware to fit.
- When the change touched a part someone is already printing or ordering,
  say exactly what differs from what they have.

## 7. Feed the framework

Before closing, ask what this project taught that the next one should know:
- A new or corrected process number → `tools/processes.json` **and**
  `lib/process.scad` (keep the two in step), with the reason in `processes.md`.
- A mistake that cost a print or an order → `lessons.md`.
- A shape a second project now needs (a thread, an inlet, a clip) → move it
  into `lib/`, keep it general, and point both projects at it.
Keep anything that only one project uses in that project's folder.
