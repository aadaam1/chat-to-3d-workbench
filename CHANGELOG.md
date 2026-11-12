# Changelog

What changed in each version, newest first, one line per change. Where it's
going next is in the [roadmap](ROADMAP.md).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [semantic versioning](https://semver.org/). Until 1.0 the
workbench is a working prototype, and anything may still change.

## [Unreleased]

### Added
- A gable-roof shed (`"type": "gable-shed"`).
- Preview capture mode, and `tools/viewer_gif.py` to turn it into GIFs and stills.
- A disclaimer (`DISCLAIMER.md`), and a responsibility note under the checks in the preview, on shopping lists and in print packs.

### Changed
- Your own designs live in `projects/`, which git ignores; curated examples are in `examples/`.
- The timber generator is built from blocks (platform, wall, roof) and recipes; the shed comes out the same.
- Jewelry is off the roadmap; the workbench is about printed parts and garden structures.

### Fixed
- Gable shed: rafter ties are full-length ceiling joists on the wall plates.
- The README names the current version; the release script keeps it current.

## [0.5.0] - 2026-11-12

Sheds framed the way a carpenter frames them, with a shopping list to match.

### Added
- `tools/build_frame.sh`: a shed from a short description to a frame, checks, shopping list and cut list.
- Shed frame generator: floor, framed walls, roof, sheathing and cladding, in European or US sizes.
- Build checks: spans of joists, rafters and headers, sheet supports, treated timber, roof pitch, bracing.
- Convention checks: king and jack studs, corner fixing, lapped top plates, closed roof bays, fascia, floating pieces.
- Shopping list and cut list by stock length and sheet, priced from a dated timber-yard snapshot.
- Preview for timber structures: layers, pull-apart view, click a piece to see what it is.
- Edits by piece: move, resize, remove or add one piece, kept through rebuilds.
- Timber libraries for Europe and the US: sections, sheets, cladding, fixings, grades, with sources.
- A framing reference for Claude, with sources.
- Regression tests and CI (`tools/test.sh`).
- Contributing guide and safety notes for timber structures.

### Changed
- Walls framed with king and jack studs, two-ply headers, cripples, three-stud corners and a double top plate.
- Floor deck laid symmetric about the middle; roof edges closed with blocking, fascia and a side overhang.
- Nails bought by weight; structural screws only from rafter to plate and at the corners.
- The cut list names each piece (stud, king stud, rafter, ...).
- European roof deck defaults to 15 mm OSB.

### Fixed
- STEP export of stretched spheres.
- Sheathing seams without timber behind them, and slivers of sheet.
- Side cladding poking above the roof line; roof deck stopping short of the fascia.
- Lopsided cripples under and over windows.

## [0.4.0] - 2026-11-10

A calmer preview and a shorter front page.

### Changed
- Studio shows only the part and the bar for talking to Claude; checks, material and versions sit in a side sheet.
- Comments are written in a bubble at their pin.
- "Thin walls" and "Needs support" moved into the "Before you order" checklist.
- Prices shown only where they are worked out.
- A shorter README, with the tap aerator as the example.

### Removed
- The "What happens next" list on the preview.

## [0.3.0] - 2026-11-10

Timber table and the Studio and Advanced previews.

### Added
- Timber table: a dated price snapshot from a timber yard, an importer, and `tools/timber.py`.
- Spare allowance on timber counts (10% by default).
- Two preview layouts: Studio (the part in its material) and Advanced (a drawing sheet with sizes).
- A material switch on the preview, with a check and rough price per process.
- The version before shown as an outline over the current one.

### Changed
- The roadmap is a priority-ordered list of directions.
- Feedback on the preview is numbered comments, each with its own note.

## [0.2.0] - 2026-11-09

The review loop: look at the part, ask for the next version.

### Added
- Design versions, saved locally on every build that changes the shape.
- A version strip on the preview.
- Comments pinned to the model, sent to Claude in one click.
- "Looks good: get the print files" to approve a version.
- Checks that paint the part and cut it open where the problem is.
- A single-file preview that opens in any browser.
- A design review in the skill: fit, loads, environment, material, safety, cost.

### Changed
- Preview redesigned: feedback first, report folded away, keyboard and trackpad work.

## [0.1.0] - 2026-11-09

The first version.

### Added
- The print-part skill: talk it through, model, check, preview, hand over.
- Shared OpenSCAD library: pipe threads, process rules, hose inlets, a part template.
- Tools: per-process builds, a printability checker with a wall-thickness heatmap and rough price, STEP export, the preview page.
- The tap aerator example.
- Setup for macOS and Linux, a copy-paste setup prompt, and a self-test.
