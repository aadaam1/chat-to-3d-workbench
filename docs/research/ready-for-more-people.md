# Ready for more people

Status: R1 done; R5 done (2026-11-12); a public-release checklist below
Last updated: 2026-11-12

## The question

What has to be true before someone who isn't the author can clone this and
get to a first preview without help, and before changes can be accepted
from other people without breaking it?

## Decisions

- **Tests are scripts, not AI.** A change is safe when the example project
  rebuilds to the same numbers. Nothing in the test run calls a model.
- **A pull request from a build session is not merged by that session.**
  It is reviewed first.
- **The copy-paste prompt stays the main way in.** A plugin is a second
  door for people who already use Claude Code plugins.

## Packages

| | Package | Depends on | Suited to |
|---|---|---|---|
| R1 | Regression tests and CI | none | a smaller model |
| R2 | Plugin install | R1 | a smaller model, after checking the current plugin format |
| R3 | Windows through WSL | R1 | a smaller model; needs a person with Windows to confirm |
| R4 | First-run test | R1 | a person |
| R5 | Contributing guide (licence decided: MIT) | R1 | the planning session |

#### R1. Regression tests and CI

Files: `tests/`, `tests/baseline/tap-aerator.json`, `tools/test.sh`,
`.github/workflows/test.yml`, `tools/setup.sh` (adds `pytest`).

- `tools/test.sh` runs everything below and prints `PASS` or what failed.
- **Example project:** run `examples/tap-aerator/build.sh`, then for every
  STL it makes compare with the baseline: volume and overall size within
  0.5%, closed solid, number of bodies, and the check verdict per process.
  `tools/test.sh --update-baseline` rewrites the baseline on purpose.
- **Tools:** `tools/timber.py` on a real request against the committed
  snapshot; `tools/make_viewer.py --inline` on one STL produces a page;
  the page's script passes `node --check` (extract the module the way the
  repo routine describes).
- **Self-test:** `tools/selftest.sh` prints READY.
- **CI:** one workflow on `ubuntu-latest`, on every push and pull request:
  `tools/setup.sh`, then `tools/test.sh`. Cache the Python environment.
  This is also the proof that Linux works. Add a macOS job only if the
  Linux one is green and fast.
- Update the repo routine skill: "checks" becomes `tools/test.sh`.
- Progress (2026-11-11): built on branch `claude/tests-ci-587601`; the
  aerator rebuild is about 4 minutes on a Mac, so the whole run is ~5.

#### R2. Plugin install

- Read the current Claude Code plugin and marketplace documentation first
  and record the format and date here.
- A plugin manifest that exposes the skills, and a note in the README. The
  tools still need the repository on disk, so the plugin's first step is
  the same setup script.

#### R3. Windows through WSL

- `tools/setup.sh` recognises WSL and installs the Linux way; the README
  says what to install first (WSL, the Claude desktop app's Code tab or
  the CLI inside WSL).
- Untested until someone with Windows runs the first-run test; say so in
  the README until then.

#### R4. First-run test

- A one-page checklist: a fresh Mac user account, the copy-paste prompt,
  a stopwatch from prompt to first preview, and where they got stuck.
- Run it once with a person who has not seen the project.

#### R5. Contributing guide

- **Decided 2026-11-11: the licence stays MIT.** AGPL-3.0 was considered,
  to keep hosted services open, and not chosen: simpler, and more welcoming
  to contributors.
- `CONTRIBUTING.md`: how to set up, how to run the tests, how a change is
  proposed, and under what terms contributions are accepted.

## First public release

Decided 2026-11-12: publish from a fresh repository with one first commit
(the earlier private history stays private), the changelog keeping its
history from 0.1.0; first public release 0.6.0, after the gable-roof shed.

Before publishing, the tree was audited: no secrets, private links,
personal details, downloaded models or print files; every relative link
and image resolves; CI uses no secrets and runs on pull requests from
forks. Personal projects live in the ignored `projects/` folder.

Done: contributing guide, disclaimer and safety notes, the projects /
examples split, a shorter changelog, the README with the shed GIFs, the
gable-roof shed, private vulnerability reporting, automatic deletion of
merged branches, and approval before CI runs for first-time contributors.

Still to do:

- R4, the first-run test with someone who has not seen the project,
  before announcing it widely.
- R2 plugin install and R3 Windows, as above.

## Open questions

- Whether the CI should also build the timber examples (today it runs
  the unit tests, which build every fixture shed).
