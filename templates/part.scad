// ===========================================================================
//  __NAME__.scad -- one line on what this part does and what it mates with
//
//  Build every process at once (STL + STEP + checks + renders), from the repo root:
//      tools/build_part.sh __PROJECT__/__NAME__ resin_sla fdm_asa slm_316l
//  One process by hand:
//      openscad --export-format binstl -D 'PROCESS="fdm_asa"' -o out.stl projects/__PROJECT__/__NAME__.scad
//
//  Units mm. +Z up as printed; z = 0 is the bed. Every number a person might
//  want to change is a named parameter below, with a comment saying why it
//  has that value (measured? standard? margin?).
//
//  The example geometry is a G3/4 threaded end cap with a lanyard hole. It
//  shows the pieces most parts need; replace it with the real part.
// ===========================================================================

// Paths are relative to projects/<project>/, where tools/newpart.sh puts the copy.
include <../../lib/threads.scad>

// ---- process ----------------------------------------------------------------
PROCESS = "fdm_asa";   // resin_sla | fdm_asa | slm_316l | slm_alsi10mg | mjf_pa12
include <../../lib/process.scad>

PART = "part";         // "part" | "section" (half cut away, for checking insides)
FAST = false;          // coarse facets for quick previews

// ---- measured: the mating part ------------------------------------------------
// Measure the real thing with calipers, not the listing. Record what and how.
THREAD     = TH_G34(); // [major, pitch, depth, flank]; G3/4 male: 26.4 mm across crests
THREAD_LEN = 8;        // male thread length on the mating part minus ~0.5 mm

// ---- design -------------------------------------------------------------------
WALL     = max(2.5, P_MIN_WALL() + 1);   // around the thread
FLOOR    = 7;          // thick enough to take the lanyard hole across it
OD       = THREAD[0] + 2 * WALL;
H        = FLOOR + THREAD_LEN;
LANYARD_D = 3;

// ---- derived ------------------------------------------------------------------
SEG  = FAST ? 48 : 120;
SEGT = FAST ? 48 : 96;

// ---- the part -----------------------------------------------------------------
module part() {
    difference() {
        chamfered_cylinder(OD, H, cb = P_BED_CHAMFER(), ct = 0.6, fn = SEG);

        translate([0, 0, FLOOR])
            internal_thread_cutter(THREAD[1], THREAD[0], THREAD[2], THREAD_LEN + 0.02,
                                   THREAD[3], segs = SEGT, clear = P_FIT(), lead_top = 0.6);
        // Remove the thread's knife-edge partial turn at the mouth (Higbee start):
        // metal services reject the sliver, and it prints badly in plastic.
        thread_higbee_cut(THREAD[1],
                          r_out = THREAD[0]/2 + P_FIT() + 0.1,
                          r_in  = THREAD[0]/2 + P_FIT() - THREAD[2] - 0.5,
                          z_origin = FLOOR - 0.01, limit = H, top = H + 1, segs = SEGT);

        // Horizontal hole across the floor: teardrop where the process needs it.
        // Its centre sits low so the pointed roof still leaves >1 mm under the bore.
        translate([0, 0, FLOOR / 2 - 0.5]) hole_x(LANYARD_D, OD + 2);
    }
}

if (PART == "part") part();
if (PART == "section") difference() { part(); translate([0, -OD, -1]) cube([OD, 2 * OD, H + 2]); }
