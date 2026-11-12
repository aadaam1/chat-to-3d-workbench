# chat-to-3d-workbench

Design real things in chat. Printed parts: a parametric OpenSCAD library,
per-process rules, checks, STEP export and an interactive preview; parts are
ordered from print services (resin prototypes, final parts in ASA or metal).
Small timber structures: a frame of real members generated from a short
description, with span and layout checks, a shopping list and the same
preview. Your own designs live in `projects/<name>/` (git-ignored); a few
curated examples are committed in `examples/`.

## Your projects vs the engine
Designing or changing a part or a structure is **not** a repo change. It lives
in `projects/<name>/` (gitignored) and gets no branch, no pull request, no
commit and no changelog line. Only changes to the engine (tools, lib, skills,
viewer, data, templates, docs) follow the repo routine. Promoting a project to
`examples/` happens only when the owner asks for it.

## Principles
- The chat is the CAD program: the user iterates by talking and looking at
  the preview, never in a CAD tool.
- The AI thinks, scripts make the files. Every output (STL, STEP, check,
  preview, print pack) comes from a script, so the same input gives the same
  files. Don't hand-edit outputs or generate geometry outside the `.scad`.

## Working on this repo
Several sessions often work here at once, and the repo is kept current as
work happens. For any change to the repo itself, follow the **repo-routine**
skill (`.claude/skills/repo-routine/`). In short:
- Every change on its own branch in its own worktree:
  `git worktree add -b feat/<name> .worktrees/<name> origin/main`. Never work
  in, or switch the branch of, the main checkout; it stays on `main`.
- Update `CHANGELOG.md` (Unreleased), `ROADMAP.md` and the direction's
  `docs/research/` note in the same commits as the change.
- Finish with `tools/test.sh` PASS (runs the self-test too), a pull request, and a merge
  (`gh pr merge --rebase --delete-branch`), then remove the worktree.
- When a session shipped something a user would notice, propose a release:
  `tools/release.py X.Y.Z --summary "..."`.

## Setting it up for someone
Many users never touch a terminal: they paste the README's setup prompt into
the Claude desktop app (Code tab). Do every step yourself, in plain words.
1. `tools/setup.sh`. Exit code 3 means it needs the person once (installing
   the OpenSCAD app, since Homebrew isn't there): relay the steps it printed,
   wait until they say it's done, then run it again. Don't ask them to
   install Homebrew or open a terminal.
2. `tools/selftest.sh` must print `READY`. If not, fix what it names.
3. Tell them it's ready and ask what they'd like to make, then follow the
   **print-part** skill. Explain jargon (STL, STEP, ASA) the first time.
Windows isn't supported yet; say so rather than improvising.

## Start here
- New part, change to a part, or "can this be made in X": use the
  **print-part** skill (`.claude/skills/print-part/`). It points to the
  tools, the process rules and the lessons from earlier parts.
- A shed or another small timber structure: use the **timber-build** skill
  (`.claude/skills/timber-build/`). One description file, then
  `tools/build_frame.sh <project>` makes the frame, checks and shopping list.
- Fresh machine or container (macOS or Linux): `tools/setup.sh` installs
  OpenSCAD, the Python packages and the OpenCASCADE bindings. Build scripts
  source `tools/env.sh` for `$PY`, `scad` (exports), `scad_view` and `headless`
  (renders); new scripts should too, and stay bash 3.2-safe (macOS).

## Examples
| Example | Folder | Build | Notes |
|---|---|---|---|
| Tap aerator (G1 garden tap; ASA + metal builds) | `examples/tap-aerator/` | `examples/tap-aerator/build.sh` | its `README.md` and `docs/` |
| Garden shed (example timber structure, European sizes) | `examples/garden-shed/` | `examples/garden-shed/build.sh` | its `README.md` |
| Your own project | `tools/newpart.sh <project> [part]` | `tools/build_part.sh <project>[/<part>] <process...>` | its `README.md` |

Your own projects are not listed here: they stay in `projects/`.

## Layout
- Framework (shared, keep project-neutral): `lib/` (threads, process presets,
  inlets), `templates/`, `tools/`, `.claude/skills/`, and `data/timber/`
  (the material libraries and dated price snapshots)
- `examples/<name>/`: curated, committed examples (`.scad` models, `README.md`,
  notes, `img/`, a `build.sh`). Read-only references.
- `projects/<name>/`: your own designs. **Gitignored**, never committed. A bare
  project name in the tools is looked up here first, then in `examples/`.
- `<project>/out/`: build output (STL, STEP, check reports, handover).
  **Gitignored.** Rebuild it; never commit it.
- `docs/img/`: images for the top-level README.

## Conventions
- Answer questions without changing files; change the design only when asked.
- Every design change: rebuild, run the checks, look at a render before calling it done.
- Deliver print files as a zip (`<project>-prints-v<N>.zip`), not by committing them.
- Project-specific code stays in its project folder. Promote something to
  `lib/` or `tools/` only when a second project needs it, and keep it general.
- Lessons that apply beyond one part go into `.claude/skills/print-part/lessons.md`.
- Every change worth telling a user about gets a line under "Unreleased" in
  `CHANGELOG.md`; `tools/release.py` turns that into a version, a tag and a
  GitHub release.
- Research for a roadmap direction goes in `docs/research/<direction>.md`
  (findings with sources and dates, decisions, open questions). Read the
  note before working on that direction; when it ships, move the lasting
  decisions to where they're used and delete the note.
- Third-party models (e.g. Printables downloads) are for measuring only: never commit them or derivatives.
- No personal details in committed files: no names, addresses, private
  links, or the user's own prices in prose. Dated supplier price snapshots
  in `data/` are fine: they're public prices, with their source and date.
