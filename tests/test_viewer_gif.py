"""tools/viewer_gif.py: shot-list parsing and URL building (no Chrome needed)."""
import os, sys
from urllib.parse import urlparse, parse_qs

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import viewer_gif as vg


def test_explicit_frames_get_defaults_and_size():
    frames, w, h, fps = vg.expand({"size": [400, 300], "fps": 8, "defaults": {"view": "3d"},
                                   "frames": [{"az": 10}, {"az": 20, "view": "top", "hold": 3}]})
    assert (w, h, fps) == (400, 300, 8.0)
    assert frames[0] == {"view": "3d", "az": 10} and frames[1]["view"] == "top"


def test_keys_interpolate_numbers_and_hold_text():
    shots = {"frames": 5, "keys": [{"at": 0, "az": 0, "layers": "a,b"}, {"at": 0.5, "layers": "a"}, {"at": 1, "az": 100}]}
    f, *_ = vg.expand(shots)
    assert [x["az"] for x in f] == [0, 25, 50, 75, 100]
    assert [x["layers"] for x in f] == ["a,b", "a,b", "a", "a", "a"]


def test_loop_stops_short_of_the_end():
    f, *_ = vg.expand({"frames": 4, "loop": True, "keys": [{"at": 0, "az": 0}, {"at": 1, "az": 360}]})
    assert [x["az"] for x in f] == [0, 90, 180, 270]


def test_frames_arg():
    f, *_ = vg.expand(vg.parse_frames_arg("3:az=0..90,layers=floor,walls,explode=0.5"))
    assert [x["az"] for x in f] == [0, 45, 90]
    assert f[1]["layers"] == "floor,walls" and f[1]["explode"] == 0.5


def test_bad_specs():
    with pytest.raises(ValueError):
        vg.parse_frames_arg("az=0..90")
    with pytest.raises(ValueError):
        vg.expand({"frames": 5})


def test_frame_url():
    u = vg.frame_url("/tmp/p.html", {"az": 12.5, "layers": ["floor", "walls"], "hold": 2, "view": "front"})
    p = urlparse(u)
    assert p.scheme == "file" and p.path == "/tmp/p.html"
    q = parse_qs(p.query)
    assert q == {"capture": ["1"], "az": ["12.5"], "layers": ["floor,walls"], "view": ["front"]}
