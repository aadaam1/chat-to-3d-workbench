#!/usr/bin/env bash
# Install the 3D toolchain. Safe to run again; skips what is already there.
#
#   Linux (cloud sessions)  openscad + xvfb from apt; Python packages with pip
#   macOS                   OpenSCAD development snapshot from Homebrew (fast
#                           Manifold engine); Python packages in .venv, made
#                           with uv on Python 3.12
#
#   Python packages: trimesh + rtree (checks), matplotlib (thinwall plots),
#   cadquery-ocp 7.7.2 (STEP export through tools/scad2step.py). OCP 7.7.2 has
#   wheels up to Python 3.12 only, hence the separate .venv on macOS.
set -e
cd "$(dirname "$0")/.."
PKGS="trimesh rtree matplotlib cadquery-ocp==7.7.2 pytest"

case "$(uname)" in
Linux)
  # apt's OpenSCAD is 2021.01 (Ubuntu 24.04): too old for these models (no
  # --export-format, no Manifold). Use the official development snapshot as an
  # AppImage, extracted so it needs no FUSE. Pinned to the same snapshot as
  # the Mac setup so numbers match; set OPENSCAD_SNAPSHOT to try another one
  # (files.openscad.org/snapshots/).
  SNAP="${OPENSCAD_SNAPSHOT:-2026.10.11}"
  BIN="$HOME/.local/bin"; export PATH="$BIN:$PATH"
  if ! openscad --help 2>&1 | grep -q -- '--backend'; then
    case "$(uname -m)" in x86_64|amd64) ARCH=x86_64 ;; aarch64|arm64) ARCH=aarch64 ;;
      *) echo "No OpenSCAD snapshot for $(uname -m): install a recent OpenSCAD yourself." >&2; exit 1 ;; esac
    DIR="$HOME/.local/opt/openscad-$SNAP"
    mkdir -p "$BIN" "$DIR"
    if [ ! -x "$DIR/squashfs-root/AppRun" ]; then
      curl -fL --retry 3 -o "$DIR/openscad.AppImage" \
        "https://files.openscad.org/snapshots/OpenSCAD-$SNAP-$ARCH.AppImage"
      chmod +x "$DIR/openscad.AppImage"
      (cd "$DIR" && ./openscad.AppImage --appimage-extract >/dev/null)
      rm -f "$DIR/openscad.AppImage"
    fi
    ln -sf "$DIR/squashfs-root/AppRun" "$BIN/openscad"
  fi
  # xvfb: a window-less GL context for the PNG renders. The rest are the
  # libraries the snapshot expects from the system (it bundles Qt only).
  apt_need=""
  command -v xvfb-run >/dev/null || apt_need="xvfb"
  for lib in libEGL.so.1 libGL.so.1 libGLU.so.1 libOpenGL.so.0 libxkbcommon.so.0 libfontconfig.so.1 libdbus-1.so.3; do
    ldconfig -p | grep -q "$lib" || missing=1
  done
  if [ -n "${missing:-}" ]; then
    apt_need="$apt_need libegl1 libgl1 libglu1-mesa libopengl0 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3 libgl1-mesa-dri"
  fi
  if [ -n "$apt_need" ]; then
    SUDO=$([ "$(id -u)" = 0 ] && echo "" || echo sudo)
    # retries: package mirrors drop out now and then, mostly on shared CI machines
    $SUDO apt-get -o Acquire::Retries=4 update -qq && $SUDO apt-get -o Acquire::Retries=4 install -y -qq $apt_need
  fi
  # say which libraries are still missing, if any, rather than failing later with a bare "error while loading"
  ldd "$(readlink -f "$BIN/openscad" | xargs dirname)"/usr/bin/openscad 2>/dev/null | grep "not found" >&2 || true
  python3 -c "import trimesh, rtree" 2>/dev/null || python3 -m pip install -q trimesh rtree
  python3 -c "import matplotlib" 2>/dev/null     || python3 -m pip install -q matplotlib
  python3 -c "import OCP" 2>/dev/null            || python3 -m pip install -q cadquery-ocp==7.7.2
  python3 -c "import pytest" 2>/dev/null         || python3 -m pip install -q pytest
  ;;
Darwin)
  # Homebrew is used when it's there, but not required: installing Homebrew
  # needs the Mac password typed into a terminal, which Claude can't do.
  export PATH="$HOME/.local/bin:$PATH"   # where uv's own installer puts it
  if ! command -v openscad >/dev/null && [ ! -x /Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD ]; then
    if command -v brew >/dev/null; then
      brew install --cask openscad@snapshot
    else
      cat >&2 <<'MSG'
NEEDS YOU (one time): OpenSCAD isn't installed, and installing it needs a person.
  1. Open https://openscad.org/downloads.html#snapshots
  2. Under "Development Snapshots", download the macOS version.
  3. Open the downloaded file and drag OpenSCAD into Applications.
  4. Open OpenSCAD once from Applications (if macOS warns about the developer,
     right-click it, choose Open, then Open again). You can close it straight away.
Then run tools/setup.sh again.
MSG
      exit 3
    fi
  fi
  if ! command -v uv >/dev/null; then
    if command -v brew >/dev/null; then
      brew install uv
    else
      # uv's official installer: no password needed, installs into ~/.local/bin
      curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
  fi
  [ -x .venv/bin/python ] || uv venv -q --python 3.12 .venv
  # shellcheck disable=SC2086
  uv pip install -q --python .venv/bin/python $PKGS
  ;;
*)
  echo "Not set up for $(uname). Install OpenSCAD, then: pip install $PKGS" >&2
  exit 1
  ;;
esac

. tools/env.sh
echo "toolchain: $("$OPENSCAD" --version 2>&1 | tail -1); exports ${SCAD_ENGINE:-CGAL}, renders ${SCAD_VIEW_ENGINE:-CGAL}"
echo "           $("$PY" --version), trimesh $("$PY" -c 'import trimesh; print(trimesh.__version__)'), OCP $("$PY" -c 'import OCP' && echo ok)"
