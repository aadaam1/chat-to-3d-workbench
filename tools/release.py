#!/usr/bin/env python3
"""Cut a release: changelog, commit, tag, push, GitHub release, in one go.

    tools/release.py 0.3.0 --summary "Timber table and the new viewer" [--dry-run]

Run on main, with nothing uncommitted and main in sync with GitHub. It:
  1. checks that, that "Unreleased" in CHANGELOG.md has entries, and that the
     version is new and higher than the last tag;
  2. turns "## [Unreleased]" into "## [0.3.0] - <today>" (with the summary as
     its first line), opens a fresh empty "Unreleased", and updates the
     comparison links at the bottom;
  3. commits "Release v0.3.0", tags it v0.3.0, pushes both, and creates the
     GitHub release from that changelog section.
--dry-run prints the new changelog section and the steps, and changes nothing.

Versions (before 1.0): the middle number for new capabilities (0.3.0), the
last for fixes and docs only (0.3.1).
"""
import argparse, datetime, re, subprocess, sys

CHANGELOG = "CHANGELOG.md"
README = "README.md"


def short(v):
    """0.5.0 -> 0.5, 0.5.1 -> 0.5.1: how the README names a version."""
    return v[:-2] if v.endswith(".0") else v


def git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def vtuple(v):
    return tuple(int(x) for x in v.split("."))


def repo_url():
    url = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        sys.exit(f"origin is not a GitHub remote: {url}")
    return f"https://github.com/{m.group(1)}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("version", help="X.Y.Z, without the v")
    ap.add_argument("--summary", default="", help="one line saying what this release is about")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    v = a.version.lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        sys.exit(f"version must look like 0.3.0, not {a.version!r}")
    problems = []
    if git("branch", "--show-current") != "main":
        problems.append("not on main: merge the feature branch first, then release from main")
    if git("status", "--porcelain"):
        problems.append("there are uncommitted changes")
    git("fetch", "-q", "origin")
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        problems.append("main is not in sync with origin/main: pull or push first")
    tags = [t for t in git("tag", "--list", "v*").split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    last = max(tags, key=lambda t: vtuple(t[1:])) if tags else None
    if f"v{v}" in tags:
        problems.append(f"v{v} already exists")
    elif last and vtuple(v) <= vtuple(last[1:]):
        problems.append(f"v{v} is not higher than the last release, {last}")

    text = open(CHANGELOG, encoding="utf-8").read()
    m = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", text, re.S | re.M)
    if not m:
        sys.exit("CHANGELOG.md has no '## [Unreleased]' section followed by a release")
    body = m.group(1).strip()
    if not re.search(r"^- ", body, re.M):
        problems.append("nothing under Unreleased in CHANGELOG.md")
    if problems:
        sys.exit("Not releasing:\n" + "\n".join(f"  - {p}" for p in problems))

    url = repo_url()
    section = f"## [{v}] - {a.date}\n\n" + (f"{a.summary}\n\n" if a.summary else "") + body + "\n\n"
    new = text[:m.start()] + "## [Unreleased]\n\n" + section + text[m.end():]
    link_old = re.search(r"^\[Unreleased\]: .*$", new, re.M)
    links = f"[Unreleased]: {url}/compare/v{v}...HEAD\n" + (
        f"[{v}]: {url}/compare/{last}...v{v}" if last else f"[{v}]: {url}/releases/tag/v{v}")
    new = (new[:link_old.start()] + links + new[link_old.end():]) if link_old else new.rstrip() + "\n\n" + links + "\n"
    notes = (f"{a.summary}\n\n" if a.summary else "") + body + \
        f"\n\nFull history: [CHANGELOG.md]({url}/blob/main/CHANGELOG.md)\n"
    title = f"{v}: {a.summary}" if a.summary else v

    if a.dry_run:
        print(section.rstrip())
        print(f"\nWould: update {CHANGELOG} and the README's version, commit 'Release v{v}', tag v{v}, push main and the tag,")
        print(f"and create the GitHub release '{title}' (previous: {last or 'none'}).")
        return
    open(CHANGELOG, "w", encoding="utf-8").write(new)
    git("add", CHANGELOG)
    # the README's status line names the version: "Version 0.5, a working prototype ..."
    readme = open(README, encoding="utf-8").read()
    bumped = re.sub(r"^Version \d+\.\d+(?:\.\d+)?,", f"Version {short(v)},", readme, count=1, flags=re.M)
    if bumped != readme:
        open(README, "w", encoding="utf-8").write(bumped)
        git("add", README)
    git("commit", "-q", "-m", f"Release v{v}" + (f": {a.summary}" if a.summary else ""))
    git("tag", "-a", f"v{v}", "-m", title)
    git("push", "-q", "origin", "main", f"v{v}")
    r = subprocess.run(["gh", "release", "create", f"v{v}", "--title", title, "--notes", notes, "--latest"],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"Tagged and pushed v{v}, but the GitHub release failed: {r.stderr.strip()}\n"
                 f"Create it by hand: gh release create v{v} --title \"{title}\" --notes-file <notes>")
    print(f"Released v{v}: {r.stdout.strip()}")


if __name__ == "__main__":
    main()
