// ---------------------------------------------------------------------------
// process.scad -- per-process allowances and print-friendly primitives.
//
// The model sets PROCESS before including this file (or the build passes it
// with -D PROCESS="slm_316l"); every helper below reads it. One .scad file
// then exports a resin prototype, an ASA part and a metal part, each with the
// right clearances, without copies drifting apart.
//
//   PROCESS = "fdm_asa";         // resin_sla | fdm_asa | slm_316l | slm_alsi10mg | mjf_pa12
//   include <lib/process.scad>
//
// Keep the numbers in step with tools/processes.json, which the checker uses.
// Everything here exports to STEP through tools/scad2step.py: no hull, offset,
// minkowski or text.
// ---------------------------------------------------------------------------

//              fit   hole_comp  min_wall  bed_chamfer  teardrop
_PROC = [
  ["resin_sla",    [0.20, 0.05,      0.8,      0.3,         false]],
  ["fdm_asa",      [0.30, 0.15,      1.2,      0.8,         true ]],
  ["slm_316l",     [0.45, 0.00,      1.2,      0.5,         true ]],
  ["slm_alsi10mg", [0.45, 0.00,      1.2,      0.5,         true ]],
  ["mjf_pa12",     [0.30, 0.10,      1.0,      0.3,         false]],
];

function _proc() =
    let (hit = [for (r = _PROC) if (r[0] == PROCESS) r[1]])
    assert(len(hit) == 1, str("process.scad: unknown PROCESS \"", PROCESS, "\""))
    hit[0];

// Radial clearance for mating parts and threads (per side).
function P_FIT()       = _proc()[0];
// Added to a hole's diameter: FDM prints holes undersize, metal does not.
function P_HOLE_COMP() = _proc()[1];
// Thinnest wall to design to; the checker warns below it.
function P_MIN_WALL()  = _proc()[2];
// 45-degree chamfer for edges on the bed (elephant foot, support contact).
function P_BED_CHAMFER() = _proc()[3];
// True where a horizontal hole needs a pointed roof to print without support.
function P_TEARDROP()  = _proc()[4];
function P_IS_METAL()  = PROCESS == "slm_316l" || PROCESS == "slm_alsi10mg";

// ---- holes ------------------------------------------------------------------

// Vertical hole of nominal diameter d, compensated for the process, z = 0..h.
// Cut it a little long on both ends yourself if it goes through.
module hole_z(d, h, fn = 48) {
    cylinder(h = h, d = d + P_HOLE_COMP(), $fn = fn);
}

// Horizontal hole along X, centred on the origin, length l. Where the process
// cannot build a round ceiling (FDM over ~6 mm, any metal), the top becomes a
// 45-degree point: the "teardrop". The round part keeps the nominal size.
module hole_x(d, l, fn = 48) {
    r = (d + P_HOLE_COMP()) / 2;
    rotate([0, 90, 0]) rotate([0, 0, 90])
        linear_extrude(height = l, center = true)
            if (P_TEARDROP()) teardrop_2d(r, fn);
            else circle(r = r, $fn = fn);
}

// Circle of radius r with its top replaced by two 45-degree tangents meeting
// in a point. +Y is up once hole_x has rotated it into place.
module teardrop_2d(r, fn = 48) {
    polygon(concat(
        [[0, r * sqrt(2)]],
        [for (i = [0 : fn]) let (a = 135 + i * 270 / fn) [r * cos(a), r * sin(a)]]
    ));
}

// ---- solids -------------------------------------------------------------------

// Cylinder with 45-degree chamfers; cb on the bottom edge, ct on the top.
// Use cb = P_BED_CHAMFER() for an edge that sits on the bed.
module chamfered_cylinder(d, h, cb = 0, ct = 0, fn = 96) {
    r = d / 2;
    rotate_extrude($fn = fn)
        polygon([[0, 0], [r - cb, 0], [r, cb], [r, h - ct], [r - ct, h], [0, h]]);
}

// Box with all bottom edges chamfered by cb, standing on z = 0, centred in XY.
module chamfered_box(size, cb = 0) {
    x = size[0]; y = size[1]; z = size[2];
    intersection() {
        translate([-x/2, -y/2, 0]) cube(size);
        // a pyramid frustum: footprint shrunk by cb at z = 0, full size at cb
        polyhedron(
            points = [[-x/2 + cb, -y/2 + cb, 0], [x/2 - cb, -y/2 + cb, 0],
                      [x/2 - cb, y/2 - cb, 0], [-x/2 + cb, y/2 - cb, 0],
                      [-x/2 - z, -y/2 - z, z + cb], [x/2 + z, -y/2 - z, z + cb],
                      [x/2 + z, y/2 + z, z + cb], [-x/2 - z, y/2 + z, z + cb]],
            faces = [[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [1, 5, 6, 2],
                     [2, 6, 7, 3], [3, 7, 4, 0]]);
    }
}

// Ring of n features around Z at radius r: ring_of(6, 10) child();
module ring_of(n, r, phase = 0) {
    for (i = [0 : n - 1]) rotate([0, 0, phase + i * 360 / n]) translate([r, 0, 0]) children();
}
