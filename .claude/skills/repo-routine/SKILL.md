---
name: repo-routine
description: How to make any change to the chat-to-3d-workbench repository itself, so parallel sessions never collide and the repo stays current as you go - start every feature or fix on its own branch in its own worktree, keep CHANGELOG, ROADMAP and research notes up to date in the same commits, finish with checks, a pull request, merge and clean-up, and cut a versioned release when a working session shipped something. Use when starting any change to this repo (code, docs, data), when finishing or merging one, when the user asks for a release, and at the end of a working session.
---

# Repo routine

**Not for projects.** Designing or changing a part or a structure in
`projects/<name>/` is not a repo change: no branch, no worktree, no pull
request, no commit, no changelog line. This routine is for the engine only
(tools, lib, skills, viewer, data, templates, docs). Anything under
`examples/` changes only when the owner asks.

Several Claude sessions often work on this repository at once, and the user
wants it kept current while work happens, not tidied up afterwards. This is
how: every change on its own branch in its own folder, the docs updated in
the same commits as the change, merged when it passes its checks, and a
release when a session shipped something worth one.

## 1. Start: own branch, own folder

The main checkout (the repo folder itself) is shared by every session.
**Never work in it, and never switch its branch.** It stays on `main`.

```bash
git -C <repo> fetch -q origin
git -C <repo> worktree add -b <type>/<name> .worktrees/<name> origin/main
```

- `<type>`: `feat` (a new capability), `fix`, `docs`, `chore` (tooling,
  routine). `<name>`: two or three words, hyphenated (`feat/shed-frame`).
- Work only inside `.worktrees/<name>` (git-ignored in the main checkout).
  The Claude app's own "worktree" session option does the same job; use
  whichever the session already has.
- The tools find the main checkout's `.venv` from a worktree; nothing to
  install.
- Before starting a roadmap direction, read its `docs/research/` note.

## 2. While working: keep the repo current in the same commits

- **Changelog.** Anything a user would notice gets a line under
  `## [Unreleased]` in `CHANGELOG.md`, in the commit that makes the change,
  under `### Added`, `### Changed`, `### Fixed` or `### Removed`. Plain
  words: what someone can now do, not which function changed. One short
  line (a sentence, not a paragraph) per user-visible change. No lines for
  projects or examples, and none for fixing something built in the same
  unreleased version.
- **Roadmap.** When an item ships, take it out of `ROADMAP.md` (it now lives
  in the changelog); when a whole direction ships, remove its section and
  renumber. New ideas the user approves go in at their priority.
- **Research notes.** Record findings (with sources and dates), decisions
  and progress in the direction's `docs/research/` note as you go. When the
  direction ships, move the lasting decisions to where they're used (skill,
  docs, code comments) and delete the note.
- **Other docs** that the change makes wrong: `README.md`, the examples
  table in `CLAUDE.md`, `data/*/README.md`, the print-part skill.
- **Commits:** small, each one working; stage files by path, never
  `git add -A` blindly; the message says what changed and why. Run
  `git branch --show-current` before committing: if it isn't your branch,
  stop and find out why.
- **Stash** is shared with every other worktree: don't use a bare
  `git stash`; make a WIP commit instead.

## 3. Finish: checks, pull request, merge, clean up

1. Catch up with main: `git fetch -q origin && git rebase origin/main`.
   A changelog conflict is two lists of new lines: keep both.
2. Checks: `tools/test.sh` must print `PASS`. It rebuilds the tap aerator
   and compares every STL with `tests/baseline/tap-aerator.json`, runs the
   tools (timber list, preview page, `node --check` on the viewer script)
   and `tools/selftest.sh`. If a change moves the aerator's numbers on
   purpose, run `tools/test.sh --update-baseline` and explain it in the
   commit. CI runs the same script on every push and pull request.
3. Push and open a pull request:
   `git push -u origin <branch>` then `gh pr create --base main` with what
   changed and what was checked.
4. Merge it: `gh pr merge <n> --rebase --delete-branch`. The user wants
   finished work merged as it's done, so merge without asking once the
   checks pass, and say so in the reply. Ask first only when the change is
   risky, unfinished, or the user said they want to review it.
5. Clean up: `git -C <repo> worktree remove .worktrees/<name>`, delete the
   local branch, and if the main checkout is on `main` with nothing
   uncommitted, `git -C <repo> pull -q --ff-only`. `gh` stops before
   deleting the branches when `main` is checked out in another folder (it
   always is here), so always finish with
   `git push origin --delete <branch>` and check that
   `git ls-remote --heads origin` lists only `main` and branches with an
   open pull request. A session that started in its own app worktree
   (`.claude/worktrees/`) does the same for its `claude/...` branch.

## 4. Release: when a session shipped something

At the end of a working session that merged changes a user would notice,
propose a release in the wrap-up: the version and a one-line summary. Run
it when the user agrees, or straight away if they asked for one.

- **Version** (before 1.0): the middle number for new capabilities
  (0.3.0), the last for fixes and docs only (0.3.1).
- From the main checkout, on `main`, in sync, nothing uncommitted:

  ```bash
  python3 tools/release.py 0.3.0 --summary "Timber table and the new viewer" --dry-run
  ```

  ```bash
  python3 tools/release.py 0.3.0 --summary "Timber table and the new viewer"
  ```

  It moves Unreleased into the new version, commits, tags, pushes and
  creates the GitHub release; it refuses (and says why) if anything is off.
- Check the release page it prints.

## If something went wrong

- **Another session moved the main checkout off `main`.** Don't switch it
  back while that session may still be working. Do your work in your own
  worktree and tell the user; switch it back only once they say the other
  session is done, and only with nothing uncommitted.
- **A commit landed on the wrong branch.** Cherry-pick it onto a fresh
  branch from `origin/main` in a worktree and finish it there; leave the
  wrong branch for its owner.
- **Never** force-push `main`, rewrite published tags, or delete another
  session's branch while it may be in use.
