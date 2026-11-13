# Contributing

Thanks for wanting to help. The workbench is a working prototype, so
anything may still change, and small, focused changes are the easiest to
take in.

## Ways to help

- **Try it and say where you got stuck.** An issue that says what you asked
  for, what you expected and what you got is the most useful thing there
  is. A screenshot of the preview helps.
- **A part or a structure that didn't come out right**: attach the project's
  description (the `.scad` file or `structure.json`), not the output files.
- **Code, rules and data**: a pull request (see below).
- **Prices and sizes for your region**: a dated price snapshot from a
  public list, with its source (see `data/timber/README.md`).

## Setting up

macOS or Linux:

```bash
git clone https://github.com/aadaam1/chat-to-3d-workbench.git
```

```bash
cd chat-to-3d-workbench && tools/setup.sh && tools/selftest.sh
```

`selftest.sh` prints `READY` when everything works. Windows isn't
supported yet.

## Making a change

1. Branch from `main`, one change per branch.
2. Keep the principles in [CLAUDE.md](CLAUDE.md): scripts make every file
   (STL, STEP, checks, shopping lists), so the same input gives the same
   output; don't commit build output (`out/` folders).
3. Your own designs (`projects/`) are never committed here: that folder is
   ignored by git. Pull requests are for the engine (tools, library, skills,
   viewer, data, templates, docs) and the workflow. A curated example for
   `examples/` can be proposed in an issue or a pull request.
4. Say what changed in plain words under "Unreleased" in
   [CHANGELOG.md](CHANGELOG.md).
5. Run the tests and get `PASS`:

   ```bash
   tools/test.sh
   ```

   It rebuilds the examples and compares them with the recorded
   numbers (about 7 minutes). If your change moves those numbers on
   purpose, run `tools/test.sh --update-baseline` and say why in the pull
   request.
6. Open a pull request against `main` saying what changed and what you
   checked. CI runs the same tests.

Claude Code users: the `repo-routine` skill in `.claude/skills/` walks
through the same steps.

## Rules for content

- **No personal details** in committed files: no names, addresses, private
  links, or your own purchase prices.
- **No third-party models** (Printables, Thingiverse and similar
  downloads) or anything derived from them. Measure from them, don't commit
  them.
- **Sources for numbers.** A span, a load, a fastener count or a material
  property names its source and the date it was read, or is marked
  `"unverified": true`. Quote standards and books only in short phrases.

## Licence

Read the [disclaimer](DISCLAIMER.md): the workbench's output is guidance,
and nobody involved takes responsibility for what is built from it.

By contributing you agree that your contribution is licensed under the
[MIT licence](LICENSE) of this project.

## Security

If you find a security problem, please don't open a public issue: use
GitHub's "Report a vulnerability" on the Security tab of the repository.
