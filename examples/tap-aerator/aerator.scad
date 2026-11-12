// ===========================================================================
//  Garden tap aerator  --  single piece, parametric
//
//  Screws onto a male BSPP garden-tap outlet and turns the swirling
//  ball-valve jet into a uniform stream. ONE printed part, no assembly.
//
//  Water path, tap at the top, outlet at the bottom:
//
//      ___________________          G1" female thread
//     |  \\\\\\\\\\\\\\\  |         flat gasket seat
//     |___________________|
//     |        | |        |         settling chamber
//     |    ====+++====    |  <--    swirl breaker: 4 blades, kills the
//     |        | |        |         rotation the ball valve puts in
//     |___________________|
//     |__o___o___o___o____|  <--    jet plate: 12 holes, sets the flow rate
//     |___________________|  <--    redistribution gap, ribbed
//     |||||||||||||||||||||  <--    exit straightener: 70 parallel channels
//          uniform stream
//
//  Everything prints bottom-up with the outlet face on the bed. Every bore
//  steps OUTWARD going up, so there is no overhang anywhere; the only
//  downward-facing surface is the jet plate's underside, which bridges the
//  2.5 mm gap in spans of 9 mm or less because the gap is ribbed.
//
//  Units: millimetres. z = 0 is the outlet face, +z points at the tap.
// ===========================================================================

include <../../lib/threads.scad>

/* [What to render] */
// aerator | gauge | section | fluid
PART = "aerator";

// Coarse preview (fast) vs. export quality
FAST = false;

// ===========================================================================
//  PARAMETERS
// ===========================================================================

/* [Fit to your tap] -------------------------------------------------------- */
// MEASURE IT: caliper across the thread crests of the tap outlet.
// 33.2 mm -> "G1",  26.4 mm -> "G3/4".  Do not trust the product listing.
TAP_THREAD = "G1";

// Radial clearance on the tap thread -- THE number to calibrate. Print
// PART="gauge" first; 0.30 suits most 0.4 mm-nozzle printers.
TAP_FIT = 0.30;

// Depth of the female thread -- and therefore how far down the bore the gasket
// sits. It must be SHORTER than your tap's male thread, or the spigot's end
// face stops short of the gasket, nothing gets compressed, and it drips no
// matter how hard you tighten. But not much shorter either: whatever is left
// over sticks up past the tap's thread as a ring-shaped cup that holds water.
//
// So: measure the tap's male thread from its end face to where it stops, and
// use that minus about 0.5 mm. The first print used 11 mm, sized for the
// 12-14 mm most G1" spigots carry -- this tap has only about 2.5 turns
// (~5.5-6 mm, from photos), so ~5 mm of the part's thread stood proud of it
// and held water. 5 mm is still 2+ turns: the water pushes with ~200 N at
// 3 bar, and two turns of ASA thread carry several times that.
TAP_THREAD_LEN = 5;
// Countersink at the mouth. Kept small: on a short thread a big lead-in eats
// a whole turn of engagement.
TAP_LEAD = 0.6;
// Higbee cut: remove the incomplete first turn at the mouth, so the thread
// starts with a full tooth instead of a knife-edge sliver. JLC3DP's thin-wall
// check flagged that sliver (down to 0.05 mm) as an error. Costs no real
// engagement -- the sliver carried no load.
THREAD_START_CUT = true;
// Where the cut's helical floor tops out, measured down from the top face.
// 0.8 cut 28 % of the tooth material; 0 cuts 12 % and still leaves no wall
// under 0.8 mm at the mouth. Below 0 the knife edge starts to come back.
HIGBEE_DROP = 0.0;

/* [Gasket] ----------------------------------------------------------------- */
// A G thread is parallel: it seals on nothing. A flat washer does the work.
// Sized to the thread: a 1" hose washer is 30 x 22-23 mm, a 3/4" one about
// 24 x 17. The recess has to stay inside the thread's minor diameter, or the
// lowest thread turn hangs over it as a feather-thin lip -- which is what the
// G3/4 build did while it borrowed the 1" washer.
GASKET_OD = TAP_THREAD == "G1" ? 30.0 : 24.0;
GASKET_ID = TAP_THREAD == "G1" ? 23.0 : 17.0;
GASKET_T  = 2.0;
GASKET_SQUASH = 0.6;    // how much it is squashed hand-tight, 30% of 2 mm

/* [Stage 1 -- swirl breaker] ----------------------------------------------- */
// Drag on a blade is under 1 N even at an absurd 4 m/s of swirl, so 1.6 mm was
// never going to break. 2.4 mm is for the other reasons: it slices as six solid
// perimeter passes rather than a thin shell, and it survives someone pushing a
// bottle brush down the bore.
VANE_N   = 4;           // blades, as a cross
VANE_T   = 2.4;
VANE_H   = 14;          // taller = more of the rotation removed
VANE_CLR = 5;           // clear settling space between the blades and the jets

/* [Stage 2 -- jet plate] --------------------------------------------------- */
// The flow regulator, and the part that catches debris first -- keep it the
// narrowest passage in the whole path. Offset from the blades above AND the
// channels below, so no jet is shadowed and none fires straight down a channel.
// Every jet must stay NARROWER than an exit channel (EXIT_D), so grit that
// clears a jet cannot jam further down. More, smaller jets beat fewer, larger
// ones: same total area, but they sit closer together and so merge in a
// shorter gap. Ring counts are multiples of 4 and each ring is phased by half
// its own spacing, which puts every jet as far as possible from the blades.
// OFF. The first print showed what docs/DESIGN-NOTES.md suspected: the plate
// is optional, and its 1.4 mm holes are the first thing garden grit blocks.
// The swirl breaker and the channel field do the job without it -- the tap,
// not the part, sets the flow either way. Kept as an option, not recommended.
JET_PLATE = false;

JET_D    = 1.4;
JET_RING = [[5.0, 4], [8.6, 8], [11.6, 12]];   // [ring radius, holes]
JET_H    = JET_PLATE ? 4.0 : 0;

/* [Stage 3 -- redistribution gap] ------------------------------------------ */
// The reason there are two hole layers rather than one: jets from the plate
// spread sideways in here and feed the channel field evenly, instead of each
// jet punching straight through.
//
// The jet plate's underside is the one downward-facing surface in the part. A
// centre post halves it, so the slicer bridges 9 mm, not 23 -- routine, and the
// surface is hidden. Radial ribs would shorten it further but each one would
// cap the mouths of the channels underneath it, so there are none.
// A free jet spreads at roughly 11 degrees per side. The 12 jets sit about
// 5 mm apart, so they need on the order of 13 mm of travel before neighbours
// merge. At 2.5 mm they arrived as 12 separate jets and fed whichever channels
// happened to be underneath -- which is exactly the pressure-chamber problem,
// only the other way round.
//
// That reasoning was for the jet plate, which is gone. With only the blades
// above it, the open bore below them (GAP_H + VANE_CLR) just has to let the
// four blade quadrants merge before the channel field. 12 mm stays the default
// because the first print with it gave a perfectly even stream; the compact
// build in build.sh tries GAP_H = 5 -- print both and compare.
GAP_H     = 12;
GAP_D     = 26;         // full bore: no point necking down before the channels
GAP_HUB_D = 6.0;        // the central spine runs through here

/* [Stage 4 -- exit straightener] ------------------------------------------- */
// Parallel channels, straight out of the bottom face. Length over diameter is
// what matters: 5 and up scrubs out anything still rotating or crossing.
// Three concentric rings, 18 + 12 + 6 = 36 x O2.0 -- the middle ground between
// the two earlier fields. v1 packed 54 x O1.8 on a 2.7 mm hex grid and left
// 0.75 mm walls between holes, under two extrusion lines, which slicers print
// ragged or drop. v2 went to 24 x O2.4 at 3.8 mm: printable, but sparse, with
// an empty ring round the spine. Rings follow the round bore instead of
// fighting it, so 36 holes fit with at least 1.14 mm of wall everywhere
// (hole to hole, ring to ring, and 0.47 mm to the rim). Each ring is phased by
// half its own spacing so no hole lines up with one in the next ring.
// Open area barely matters for flow: the tap's own bore is about ten times
// more restrictive than any of these fields.
EXIT_H     = 12;        // L/D = 6
EXIT_D     = 2.0;
EXIT_RINGS = [          // [radius, holes, phase deg] -- outside in
    [10.65, 18, 10.0],
    [ 7.45, 12, 15.0],
    [ 4.45,  6,  0.0] ];
EXIT_SPAN  = 24.4;      // envelope of the field; the CFD outlet uses it

// Small vertical holes print undersize. Added to every small hole diameter.
HOLE_COMP = 0.15;

/* [Weep holes] -- OFF, and staying off --------------------------------------- */
// These drained the thread cavity, the pocket between the tap's male thread and
// ours, which otherwise holds rain against the tap's steel. The argument for
// them was that the gasket seals at the BOTTOM of the thread, so everything
// above it is atmospheric and never sees mains pressure.
//
// That argument only holds when the gasket is actually seated. Screw the part
// on hand-tight but stop short of the gasket -- which is the normal way to get
// it wrong -- and the thread cavity becomes part of the pressurised path. Three
// holes through the wall then become three side jets, at head height.
//
// A trapped film of rainwater is a much smaller problem than a fitting that
// sprays when it is not quite tight. Set WEEP_N above 0 only if you are certain
// the gasket seats every time, which you are not.
WEEP_N = 0;
WEEP_D = 2.2;
WEEP_A = 45;            // degrees below horizontal

/* [Shell] ------------------------------------------------------------------ */
BODY_OD   = 42;
NOSE_OD   = 32;         // slimmer below the grip
PLENUM_D  = 26;         // main internal bore
CHAM_H    = 21;         // settling chamber
// "flutes":     cut into the wall, full height, out through the top. For
//               plastic, whose wall is thick enough even around the thread.
// "flutes_low": the same flutes, stopped below the washer seat with a 45-degree
//               run-out. For the slim metal build: around the thread its wall
//               is only ~2 mm and a flute would cut through to it, but below
//               the seat the wall is over 6 mm. Nothing sticks out.
// "ribs":       raised bars instead. "none": plain.
GRIP_STYLE = "flutes";
GRIP_N    = 14;
GRIP_R    = 2.6;
GRIP_BITE = 0.50;
RIB_N     = 8;
RIB_W     = 2.0;
RIB_H     = 1.0;

// The top face sits horizontal when the part hangs off a downward outlet, and
// a flat rim there ponds rain against the tap's steel threads. So the face
// slopes outwards, and drain scallops cut through the rim in every direction --
// it does not matter which way round the part goes on.
TOP_SLOPE  = 1.5;       // how much lower the outer edge sits
DRAIN_N    = 14;        // valleys, one per grip flute (0 for none)
DRAIN_R    = 1.8;
// Centred on the outer edge, in line with the flutes, which now run out
// through the top. Inner edge 19.2 mm radius: 1.6 mm clear of the mouth
// chamfer. At 20.0 / R2.3 it came within 0.2 mm of it -- a thin-wall warning.
DRAIN_POS  = BODY_OD / 2;
DRAIN_DEEP = 1.6;       // measured perpendicular to the sloped face

// ===========================================================================
//  DERIVED
// ===========================================================================

SEG  = FAST ? 48 : 120;
SEGT = FAST ? 48 : 96;
$fn  = SEG;

TAP = TAP_THREAD == "G1" ? TH_G1() : TH_G34();

Z_GAP  = EXIT_H;                        // 8.0   gap floor
Z_JET  = Z_GAP + GAP_H;                 // 10.5  jet plate underside
Z_CHAM = Z_JET + JET_H;                 // 14.0  chamber floor
Z_VANE = Z_CHAM + VANE_CLR;             // 19.0  blades start
Z_SEAT = Z_CHAM + CHAM_H;               // 34.0  gasket seat floor
SEAT_D = GASKET_T - GASKET_SQUASH;
Z_TAP  = Z_SEAT + SEAT_D;               // 35.4
BODY_H = Z_TAP + TAP_THREAD_LEN;

NOSE_H  = 12;                           // slim section height
FLARE_H = (BODY_OD - NOSE_OD) / 2;      // 45 degrees

TOP_R0      = TAP[0]/2 + TAP_FIT;              // sloped face starts at the bore
TOP_SLOPE_A = atan(TOP_SLOPE / (BODY_OD/2 - TOP_R0));

// Height of the sloped top face at a given radius.
function top_face_z(r) = BODY_H - TOP_SLOPE * (r - TOP_R0) / (BODY_OD/2 - TOP_R0);

function hc(d) = d + HOLE_COMP;

// ===========================================================================
//  SHARED
// ===========================================================================

// Parallel channels on concentric rings, z = z0 .. z0 + h.
module channel_rings(d, h, rings, z0 = 0) {
    for (ring = rings, i = [0 : ring[1] - 1])
        rotate([0, 0, ring[2] + i * 360 / ring[1]])
            translate([ring[0], 0, z0 - 0.01]) cylinder(h = h + 0.02, d = d, $fn = 24);
}

// Raised grip bars from z to z_top on a body of diameter od. Their lower ends
// are 45-degree ramps, so they print without support in plastic or metal.
module grip_ribs(z, z_top, od) {
    for (i = [0 : RIB_N - 1]) rotate([0, 0, i * 360 / RIB_N])
        rotate([90, 0, 0]) linear_extrude(RIB_W, center = true)
            polygon([[od/2 - 0.5, z], [od/2 + RIB_H, z + RIB_H + 0.5],
                     [od/2 + RIB_H, z_top], [od/2 - 0.5, z_top]]);
}

module grip_cut(z, h, od, runout = false) {
    for (i = [0 : GRIP_N - 1]) rotate([0, 0, i * 360 / GRIP_N])
        translate([od/2 + GRIP_R * (1 - GRIP_BITE), 0, z - 0.01]) {
            cylinder(h = h + 0.02, r = GRIP_R, $fn = 24);
            // 45-degree cone closing the flute: no flat ceiling to print
            if (runout) translate([0, 0, h + 0.01])
                cylinder(h = GRIP_R, r1 = GRIP_R, r2 = 0, $fn = 24);
        }
}

// 45-degree chamfer on the outer edge of a face at height z; top = true for a
// face with the part below it, false for the bed face with the part above.
// What survives is a cone that is the full diameter c away from the face and
// c narrower (radius) at the face. It starts a hair outside the diameter, so
// it crosses the wall at 45 degrees instead of touching it tangentially --
// tangent cuts break the solid.
//
// The first version had this cone upside down: it left the full diameter AT
// the face and undercut the wall 1 mm above it, printing a thin flange on the
// bed with a groove over it -- the opposite of a chamfer.
module edge_chamfer_cut(z, c, od, top = true) {
    translate([0, 0, z]) mirror([0, 0, top ? 0 : 1])
        difference() {
            translate([0, 0, -c - 0.01]) cylinder(h = c + 0.31, d = od + 6, $fn = SEG);
            translate([0, 0, -c - 0.01])
                cylinder(h = c + 0.31, d1 = od + 0.02, d2 = od - 2*c - 0.6, $fn = SEG);
        }
}

// One swirl-breaker blade: length along Y, thickness along X, ridged top and
// bottom. The 45-degree underside is what lets a metal (SLM) print build it
// without support: a flat 2.4 mm underside is a ceiling over the open chamber,
// which a filament printer bridges but a laser-melted print would sag on. It
// also gives the blade a sharp trailing edge, so less wake.
module vane_blade(len) {
    rotate([90, 0, 0]) translate([0, 0, -len/2])
        linear_extrude(height = len)
            polygon([[0, 0], [VANE_T/2, VANE_T/2], [VANE_T/2, VANE_H - VANE_T/2],
                     [0, VANE_H], [-VANE_T/2, VANE_H - VANE_T/2], [-VANE_T/2, VANE_T/2]]);
}

// ===========================================================================
//  THE PART
// ===========================================================================

module aerator() {
  union() {
    difference() {
        union() {
            // ---- outer shell
            cylinder(h = NOSE_H, d = NOSE_OD, $fn = SEG);
            translate([0, 0, NOSE_H])
                cylinder(h = FLARE_H, d1 = NOSE_OD, d2 = BODY_OD, $fn = SEG);
            translate([0, 0, NOSE_H + FLARE_H])
                cylinder(h = BODY_H - NOSE_H - FLARE_H, d = BODY_OD, $fn = SEG);
            if (GRIP_STYLE == "ribs")
                grip_ribs(NOSE_H + FLARE_H + 1, BODY_H - TOP_SLOPE - 2, BODY_OD);
        }

        // ---- internal bore. Every step opens outwards going up.
        translate([0, 0, Z_GAP])
            cylinder(h = GAP_H + 0.01, d = GAP_D, $fn = SEG);
        translate([0, 0, Z_CHAM])
            cylinder(h = CHAM_H + 0.01, d = PLENUM_D, $fn = SEG);
        translate([0, 0, Z_SEAT])
            cylinder(h = SEAT_D + 0.01, d = GASKET_OD + 0.6, $fn = SEG);
        translate([0, 0, Z_TAP - 0.01])
            internal_thread_cutter(TAP[1], TAP[0], TAP[2], TAP_THREAD_LEN + 0.02,
                                   TAP[3], segs = SEGT, clear = TAP_FIT,
                                   lead_top = TAP_LEAD);
        if (THREAD_START_CUT)
            thread_higbee_cut(TAP[1],
                              r_out = TAP[0]/2 + TAP_FIT + 0.1,
                              r_in  = TAP[0]/2 + TAP_FIT - TAP[2] - 0.5,
                              z_origin = Z_TAP - 0.01,
                              limit = BODY_H - HIGBEE_DROP,
                              top   = BODY_H + 1, segs = SEGT);

        // ---- exit straightener
        channel_rings(hc(EXIT_D), EXIT_H, EXIT_RINGS);

        // ---- jet plate
        if (JET_PLATE) for (ring = JET_RING)
            for (i = [0 : ring[1] - 1])
                rotate([0, 0, 180 / ring[1] + i * 360 / ring[1]])
                    translate([ring[0], 0, Z_JET - 0.01])
                        cylinder(h = JET_H + 0.02, d = hc(JET_D), $fn = 24);

        // ---- weep holes, disabled by default -- see the note above
        if (WEEP_N > 0) for (i = [0 : WEEP_N - 1]) rotate([0, 0, i * 360 / WEEP_N])
            translate([PLENUM_D/2 + 0.5, 0, Z_TAP + 1.0])
                rotate([0, 90 + WEEP_A, 0])
                    cylinder(h = 14, d = hc(WEEP_D), $fn = 24);

        // Flutes run out through the top. Stopped 2 mm short, as they were,
        // they left a 0.5 mm ledge under the sloped rim -- a thin-wall error.
        if (GRIP_STYLE == "flutes")
            grip_cut(NOSE_H + FLARE_H + 2, BODY_H - NOSE_H - FLARE_H, BODY_OD);
        // The run-out cone cuts no higher than GRIP_R * GRIP_BITE above the
        // straight part, so ending that far below the seat keeps it clear.
        if (GRIP_STYLE == "flutes_low")
            grip_cut(NOSE_H + FLARE_H + 2,
                     Z_SEAT - GRIP_R * GRIP_BITE - (NOSE_H + FLARE_H + 2),
                     BODY_OD, runout = true);
        edge_chamfer_cut(0, 1.0, NOSE_OD, top = false);

        // ---- top face slopes outwards, so water runs off rather than sitting
        // on the rim against the tap's threads
        rotate_extrude($fn = SEG) polygon([
            [TOP_R0,        BODY_H],
            [BODY_OD/2 + 3, BODY_H - TOP_SLOPE * (BODY_OD/2 + 3 - TOP_R0)
                                     / (BODY_OD/2 - TOP_R0)],
            [BODY_OD/2 + 3, BODY_H + 5],
            [TOP_R0,        BODY_H + 5],
        ]);
        // ---- valleys through the rim. Cut on an axis tilted to match the
        // face, so each one is a constant-depth channel running downhill and
        // out, not a flat-bottomed pocket that holds the water it collects.
        if (DRAIN_N > 0) for (i = [0 : DRAIN_N - 1]) rotate([0, 0, i * 360 / DRAIN_N])
            // sink DRAIN_DEEP along the face's own inward normal, then cut on
            // an axis perpendicular to the face
            translate([DRAIN_POS  - DRAIN_DEEP * sin(TOP_SLOPE_A), 0,
                       top_face_z(DRAIN_POS) - DRAIN_DEEP * cos(TOP_SLOPE_A)])
                rotate([0, TOP_SLOPE_A, 0])
                    cylinder(r = DRAIN_R, h = DRAIN_DEEP + 7, $fn = 28);
    }

    // ---- anything standing inside the bore goes here, AFTER the bore is cut.
    // Put it in the union above and the bore cut simply deletes it again.

    // Central spine. Runs from the top of the channel field, up through the
    // redistribution gap and the jet plate, to where the swirl blades cross.
    // Everything inside the bore is then one connected structure braced to the
    // wall at both the blades and the jet plate, instead of three separate
    // features. It also halves the jet plate's bridge.
    translate([0, 0, Z_GAP - 0.01])
        cylinder(h = Z_VANE + VANE_H - Z_GAP + 0.02, d = GAP_HUB_D, $fn = SEG);
    // 45-degree cap: the flow divides off it instead of stagnating on a flat
    // disc, and 45 degrees prints without support
    translate([0, 0, Z_VANE + VANE_H])
        cylinder(h = (GAP_HUB_D - 1.6)/2, d1 = GAP_HUB_D, d2 = 1.6, $fn = SEG);

    // swirl breaker, trimmed so the blades bite into the chamber wall
    intersection() {
        translate([0, 0, Z_VANE])
            cylinder(h = VANE_H + 1, d = PLENUM_D + 1.0, $fn = SEG);
        translate([0, 0, Z_VANE])
            for (i = [0 : VANE_N/2 - 1]) rotate([0, 0, i * 180 / (VANE_N/2)])
                vane_blade(PLENUM_D + 2);
    }
  }
}

// ===========================================================================
//  THREAD GAUGE -- print this first
// ===========================================================================

module gauge(clear = TAP_FIT) {
    h = 12;
    difference() {
        cylinder(h = h, d = BODY_OD, $fn = SEG);
        translate([0, 0, -0.01])
            internal_thread_cutter(TAP[1], TAP[0], TAP[2], h + 0.02, TAP[3],
                                   segs = SEGT, clear = clear,
                                   lead_top = 1.4, lead_bottom = 1.0);
        grip_cut(1, h - 2, BODY_OD);
        // One rim notch per 0.05 mm above 0.15, so a plateful stays tellable apart
        n = round((clear - 0.15) / 0.05);
        if (n > 0) for (i = [0 : n - 1])
            rotate([0, 0, i * 11])
                translate([BODY_OD/2 - 3.4, -0.7, h - 0.8]) cube([3.5, 1.4, 1.01]);
    }
}

// ===========================================================================
//  SECTION / CFD DOMAIN
// ===========================================================================

module section() {
    difference() {
        aerator();
        translate([0, -BODY_OD, -1]) cube([BODY_OD, 2*BODY_OD, BODY_H + 2]);
    }
}

// Internal water volume: the envelope of the flow path, minus the part itself.
// Carving with the real geometry means this can never disagree with it.
module fluid_domain(inlet_ext = 30, outlet_ext = 45) {
    difference() {
        union() {
            translate([0, 0, Z_SEAT])
                cylinder(h = BODY_H - Z_SEAT + inlet_ext, d = GASKET_ID, $fn = SEG);
            translate([0, 0, Z_JET])
                cylinder(h = Z_SEAT - Z_JET, d = PLENUM_D, $fn = SEG);
            translate([0, 0, Z_GAP - 0.01])
                cylinder(h = GAP_H + JET_H + 0.02, d = GAP_D, $fn = SEG);
            cylinder(h = EXIT_H + 0.01, d = EXIT_SPAN, $fn = SEG);
            translate([0, 0, -outlet_ext])
                cylinder(h = outlet_ext + 0.01, d = EXIT_SPAN, $fn = SEG);
        }
        aerator();
    }
}

// ===========================================================================
//  RENDER
// ===========================================================================

if      (PART == "aerator") aerator();
else if (PART == "gauge")   gauge();
else if (PART == "section") section();
else if (PART == "fluid")   fluid_domain();
else if (PART == "offsets")
    echo(str("STACK z_gap=", Z_GAP, " z_jet=", Z_JET, " z_cham=", Z_CHAM,
             " z_vane=", Z_VANE, " z_seat=", Z_SEAT, " z_tap=", Z_TAP,
             " height=", BODY_H));
else assert(false, str("unknown PART: ", PART));
