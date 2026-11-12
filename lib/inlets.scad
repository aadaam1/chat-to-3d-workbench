// ---------------------------------------------------------------------------
// inlets.scad -- hose-side connections for the garden nozzles
//
//   "gardena" : a male Original-GARDENA-System click plug, printed in place.
//               Seals with the standard GARDENA O-ring, 11 x 2.5 mm
//               (spare part 5303), which you fit into the groove yourself.
//   "G1"      : a male G1" (33.3 mm) BSPP thread. Screw a real GARDENA tap
//               connector for 33.3 mm taps onto it and you get a factory click
//               plug that certainly fits -- the fallback if the printed plug
//               does not click or does not seal.
//
// Every inlet stands on z = 0 and points +z. The body it sits on must leave the
// bore open: subtract inlet_cut() from the body.
//
// GARDENA publishes no drawing. The stations below were checked against three
// independently made GARDENA-compatible plugs (a published set of hose
// connectors -- measured only, nothing copied into this repo), which agree
// with each other to 0.1-0.2 mm. Print the three gauges from
// a small gauge part first and click each into your hose connector before
// printing a whole nozzle.
// ---------------------------------------------------------------------------

include <threads.scad>

// ---- GARDENA plug ----------------------------------------------------------
// Diameters are what the part should MEASURE after printing. Positions are
// distances from the tip.
//
//      tip
//       _   lead-in
//      | |  nose            O15.8
//      |<   O-ring groove   floor O11.8, 2.5 .. 6.1
//      | |  land            O15.8
//      /  \ bead            O17.0, the coupling's fingers ride over this ...
//      \  /
//      |  | latch groove    O13.0 ... and snap in here, 12.9 .. 15.0
//      /  \ taper
//      |  | shoulder        O17.0, kept clear to 23.5 so the coupling's
//     /    \                sleeve can slide all the way on
//     |____| collar         O22
//
GP_NOSE_D     = 15.8;   // nose and land: what slides into the coupling
GP_ORING_ROOT = 11.8;   // O-ring groove floor -- THE number to calibrate
GP_ORING_AT   = 2.5;    // groove starts
GP_ORING_END  = 6.1;    // groove's body-side wall
GP_BEAD_D     = 17.0;
GP_BEAD_AT    = 8.5;    // land ends, bead begins
GP_BEAD_END   = 10.9;
GP_LATCH_D    = 13.0;   // where the coupling's fingers sit
GP_LATCH_END  = 15.0;
GP_SHOULDER_D = 17.0;
GP_CLEAR_L    = 23.5;   // nothing wider than the shoulder until here
GP_BORE_D     = 8.0;
GP_COLLAR_D   = 22.0;

// Profile in (r, distance-from-tip). Every wall that faces the tip -- downward,
// when the plug prints pointing up -- is a 45-degree chamfer, so nothing
// overhangs: the O-ring groove's tip side and the back of the bead. The
// coupling's sleeve locks its fingers radially, so a 45-degree face behind the
// bead still holds; the O-ring is pushed by the water onto the groove's square,
// body-side wall, which is where it has to seal anyway.
function _gp_profile() =
    let (
        rn = GP_NOSE_D / 2,
        ro = GP_ORING_ROOT / 2,
        rb = GP_BEAD_D / 2,
        rl = GP_LATCH_D / 2,
        rs = GP_SHOULDER_D / 2,
        rc = GP_COLLAR_D / 2,
        taper = (rs - rl) / tan(27)        // latch groove -> shoulder, 27 deg
    )
    [ [rn - 1.0, 0], [rn, 1.0],                                  // lead-in
      [rn, GP_ORING_AT], [ro, GP_ORING_AT + (rn - ro)],          // O-ring groove
      [ro, GP_ORING_END], [rn, GP_ORING_END],
      [rn, GP_BEAD_AT], [rb, GP_BEAD_AT + (rb - rn)],            // bead
      [rb, GP_BEAD_END], [rl, GP_BEAD_END + (rb - rl)],
      [rl, GP_LATCH_END], [rs, GP_LATCH_END + taper],            // latch groove
      [rs, GP_CLEAR_L], [rc, GP_CLEAR_L + (rc - rs)],            // shoulder, collar
      [rc, GP_CLEAR_L + (rc - rs) + 1.5] ];

function gardena_plug_len() = let (p = _gp_profile()) p[len(p) - 1][1];

module gardena_plug() {
    prof = _gp_profile();
    L    = gardena_plug_len();
    rotate_extrude($fn = 128)
        polygon(concat(
            [ [GP_BORE_D / 2, L - 0], [GP_BORE_D / 2, 0] ],
            [ for (i = [len(prof) - 1 : -1 : 0]) [ prof[i][0], L - prof[i][1] ] ]
        ));
}

// ---- G1" male thread for a GARDENA tap connector ---------------------------
G1_MALE_FIT = 0.25;     // radial undersize against a moulded female thread
G1_LEN      = 13;       // GARDENA 33.3 mm tap connectors take about 12 mm
G1_BORE_D   = 12;

module g1_inlet() {
    t = TH_G1();
    external_thread(t[1], t[0] - 2 * G1_MALE_FIT, t[2], G1_LEN, t[3],
                    segs = 96, ch_bottom = 0.01, ch_top = 1.0);
}

// ---- dispatch --------------------------------------------------------------
function inlet_len(kind) = kind == "G1" ? G1_LEN : gardena_plug_len();
function inlet_bore(kind) = kind == "G1" ? G1_BORE_D : GP_BORE_D;
// Footprint the body must offer under the inlet, as a diameter.
function inlet_foot(kind) = kind == "G1" ? 33.4 : GP_COLLAR_D;

module inlet(kind) {
    if (kind == "G1") g1_inlet();
    else gardena_plug();
}

// Bore through the inlet and `below` mm down into the body.
module inlet_cut(kind, below = 1) {
    translate([0, 0, -below])
        cylinder(d = inlet_bore(kind), h = inlet_len(kind) + below + 1, $fn = 48);
}
