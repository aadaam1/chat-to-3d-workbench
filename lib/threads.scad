// ---------------------------------------------------------------------------
// threads.scad -- self-contained helical thread generator for OpenSCAD
//
// A thread is built as ONE watertight polyhedron: a helical ribbon whose
// radial cross-section is the tooth profile. Two rules keep CGAL happy:
//
//   1. Every face is a triangle. A helical sweep's quads are not planar, and
//      CGAL's exact arithmetic rejects them outright.
//   2. The tooth profile is convex and its axial width is one pitch minus the
//      root flat, so consecutive windings never touch. The root flat is then
//      supplied by the plain core cylinder the ribbon is unioned with -- which
//      is what a thread root physically is anyway.
//
// Profile: a symmetric truncated V, the printable stand-in for the rounded
// Whitworth / ISO forms.
//
//         <------ pitch p ------>
//          ___                ___     <- crest flat, r = dmaj/2
//         /   \              /   \
//     ___/     \____________/     \   <- root flat, r = dmaj/2 - depth
//              <- root flat ->            (supplied by the core cylinder)
//
// No external libraries. Verified against OpenSCAD 2021.01 + CGAL.
// ---------------------------------------------------------------------------

// Tooth cross-section in (z, r), crest centred on z = 0, convex by construction.
//   p     : pitch
//   dmaj  : major diameter
//   depth : radial thread depth (h)
//   flank : flank half-angle from the radial plane, deg (27.5 BSPP, 30 ISO)
//   sink  : how far the ribbon reaches below the root, to bury it in the core
function thread_profile(p, dmaj, depth, flank, sink = 0.6) =
    let (
        r_maj  = dmaj / 2,
        r_root = r_maj - depth,
        fl     = depth * tan(flank),      // axial run of one flank
        cf     = (p - 2 * fl) / 2,        // crest flat == root flat
        half   = cf / 2 + fl,             // ribbon half-width; root flat is the gap
        r_in   = r_root - sink
    )
    assert(cf > 0.05,
        "thread_profile: flanks overrun the pitch -- reduce depth or flank angle")
    assert(r_in > 0.5, "thread_profile: sink reaches the axis")
    [ [-half, r_in  ],
      [-half, r_root],
      [-cf/2, r_maj ],
      [ cf/2, r_maj ],
      [ half, r_root],
      [ half, r_in  ] ];

// The bare helical ribbon. Winds one pitch past each end; callers trim it.
module thread_ribbon(p, dmaj, depth, length, flank = 30, segs = 96,
                     sink = 0.6, starts = 1) {
    prof  = thread_profile(p, dmaj, depth, flank, sink);
    np    = len(prof);
    rings = ceil(((length + 2 * p) / p) * segs) + 1;
    dz    = p / segs;

    for (s = [0 : starts - 1]) rotate([0, 0, s * 360 / starts])
    polyhedron(
        points = [
            for (i = [0 : rings - 1])
                let (a = i * 360 / segs, zc = -p + i * dz)
                for (q = prof) [ q[1] * cos(a), q[1] * sin(a), zc + q[0] ]
        ],
        faces = concat(
            // side walls, as triangles
            [ for (i = [0 : rings - 2], j = [0 : np - 1])
                let (k = (j + 1) % np)
                each [ [ i*np + j, i*np + k, (i+1)*np + k ],
                       [ i*np + j, (i+1)*np + k, (i+1)*np + j ] ] ],
            // end caps, fanned -- valid because the profile is convex
            [ for (j = [1 : np - 2]) [ 0, j + 1, j ] ],
            [ for (j = [1 : np - 2])
                let (b = (rings - 1) * np) [ b, b + j, b + j + 1 ] ]
        ),
        convexity = 8
    );
}

// Radius that makes a segs-gon's INRADIUS equal r, so the faceted core never
// undercuts the thread root.
function _circumr(r, segs) = r / cos(180 / segs);

// Male thread, solid, spanning z = 0 .. length.
//   ch_bottom / ch_top : 45-degree lead-ins, so it starts square by hand
module external_thread(p, dmaj, depth, length, flank = 30, segs = 96,
                       starts = 1, sink = 0.6, ch_bottom = 0.8, ch_top = 0.8) {
    r_maj  = dmaj / 2;
    r_root = r_maj - depth;
    intersection() {
        union() {
            cylinder(h = length, r = _circumr(r_root, segs), $fn = segs);
            thread_ribbon(p, dmaj, depth, length, flank, segs, sink, starts);
        }
        rotate_extrude($fn = segs) polygon([
            [0, 0],
            [r_maj - ch_bottom, 0],
            [r_maj, ch_bottom],
            [r_maj, length - ch_top],
            [r_maj - ch_top, length],
            [0, length],
        ]);
    }
}

// The solid you SUBTRACT to get a female thread. It is a male thread grown by
// `clear` on the radius, so both major and minor open up by that much.
//   lead_bottom / lead_top : conical countersinks at the mouths
module internal_thread_cutter(p, dmaj, depth, length, flank = 30, segs = 96,
                              clear = 0.30, starts = 1, sink = 0.6,
                              lead_bottom = 0, lead_top = 0) {
    r_maj  = dmaj / 2 + clear;
    r_root = r_maj - depth;
    union() {
        cylinder(h = length, r = _circumr(r_root, segs), $fn = segs);
        intersection() {
            thread_ribbon(p, dmaj + 2 * clear, depth, length, flank, segs, sink, starts);
            cylinder(h = length, r = r_maj + 1, $fn = segs);
        }
        if (lead_bottom > 0)
            cylinder(h = lead_bottom, r1 = r_maj + lead_bottom, r2 = r_maj, $fn = segs);
        if (lead_top > 0)
            translate([0, 0, length - lead_top])
                cylinder(h = lead_top, r1 = r_maj, r2 = r_maj + lead_top, $fn = segs);
    }
}

// Higbee cut for an internal thread: removes the incomplete turn at the mouth.
//
// Where a helical thread runs out through a flat face, the last tooth tapers
// to a knife edge: a sliver tens of microns thick, which prints badly in
// plastic and is rejected outright by metal print services' thin-wall checks.
// Machinists remove that partial turn so the thread starts with a full-height
// tooth ending in a square face. This is that cut, for internal_thread_cutter
// placed at z_origin.
//
// It removes everything between r_in and r_out that lies above a helical floor
// running along the groove centres, from `limit` - p up to `limit`, with one
// radial step. Along a groove centre the bore is open all the way out to the
// thread's major radius, so the floor itself cuts no tooth; only the tooth
// above it -- the partial one -- goes. r_out should sit just outside the major
// radius (it leaves a helical ledge that wide), r_in just inside the minor.
// Built as two half-turn polyhedra, so neither has to close on itself.
module thread_higbee_cut(p, r_out, r_in, z_origin, limit, top, segs = 96) {
    f    = (limit - z_origin) / p;
    phi0 = 360 * (f - floor(f));          // where a groove centre is at `limit`
    half = segs / 2;
    for (h = [0, 1]) {
        pts = [ for (j = [0 : half])
                  let (k = h * half + j, a = phi0 + k * 360 / segs,
                       z = limit - p + p * k / segs)
                  each [ [r_in  * cos(a), r_in  * sin(a), z],
                         [r_out * cos(a), r_out * sin(a), z],
                         [r_out * cos(a), r_out * sin(a), top],
                         [r_in  * cos(a), r_in  * sin(a), top] ] ];
        faces = concat(
            [[0, 3, 2, 1]],                                          // start cap
            [[4*half, 4*half + 1, 4*half + 2, 4*half + 3]],          // end cap
            [ for (j = [0 : half - 1]) let (a = 4*j, b = 4*(j + 1))  // helical floor
                each [[a, a + 1, b + 1], [a, b + 1, b]] ],
            [ for (j = [0 : half - 1]) let (a = 4*j, b = 4*(j + 1))  // top
                [a + 3, b + 3, b + 2, a + 2] ],
            [ for (j = [0 : half - 1]) let (a = 4*j, b = 4*(j + 1))  // outer wall
                [a + 1, a + 2, b + 2, b + 1] ],
            [ for (j = [0 : half - 1]) let (a = 4*j, b = 4*(j + 1))  // inner wall
                [a, b, b + 3, a + 3] ]);
        polyhedron(pts, faces, convexity = 4);
    }
}

// ---- named thread standards ------------------------------------------------
// [ major diameter, pitch, radial depth, flank half-angle ]
// BSPP / ISO 228-1 "G" threads: 55-deg included angle, h = 0.640327 * p.
// These are the parallel pipe threads on European garden taps. They do NOT
// seal on the flanks -- you need a flat gasket at the bottom of the bore.
function TH_G1()  = [33.249, 2.30909, 1.479, 27.5];   // G1"   - 11 TPI
function TH_G34() = [26.441, 1.81400, 1.162, 27.5];   // G3/4" - 14 TPI
function TH_G12() = [20.955, 1.81400, 1.162, 27.5];   // G1/2" - 14 TPI
// Coarse in-house thread for the body <-> cap joint: blunt, fast, prints clean.
function TH_CAP() = [36.0,   3.0,     1.2,   30.0];
