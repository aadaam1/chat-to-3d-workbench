#!/usr/bin/env python3
"""
First-cut hydraulics for the aerator: how much water comes out, how fast the
jets run, whether the straightener is loose enough to let air in.

This is a lumped one-dimensional model -- every restriction is treated as an
orifice in series:

    dP_total = sum_i (rho/2) * ( Q / (Cd_i * A_i) )^2
    =>  Q = sqrt(2 * dP_total / rho) / sqrt( sum_i 1/(Cd_i*A_i)^2 )

It is good for sizing and for comparing options, and it is NOT a substitute for
measuring the real thing. Expect it to land within about +-25% of reality.

    python3 flow.py                      # the part as built: no jet plate
    python3 flow.py --jets 24 --jet-d 1.4   # with the optional jet plate
"""
import argparse, math

RHO = 998.0  # kg/m^3

def area(d_mm, n=1):
    return n * math.pi * (d_mm / 1000.0) ** 2 / 4.0

class R:
    """One restriction in the chain."""
    def __init__(self, name, a, cd):
        self.name, self.a, self.cd = name, a, cd
    @property
    def inv2(self):
        return 1.0 / (self.cd * self.a) ** 2

def solve(dp_pa, chain):
    return math.sqrt(2 * dp_pa / RHO) / math.sqrt(sum(r.inv2 for r in chain))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jet-d", type=float, default=1.4, help="jet diameter, mm")
    p.add_argument("--jets", type=int, default=0,
                   help="number of jets; 0 = no jet plate (the default build)")
    p.add_argument("--chan-d", type=float, default=2.0, help="straightener channel dia, mm")
    p.add_argument("--chan-n", type=int, default=36, help="number of channels")
    p.add_argument("--chan-l", type=float, default=12.0, help="channel length, mm")
    p.add_argument("--gap-d", type=float, default=23.0,
                   help="redistribution gap diameter, mm")
    p.add_argument("--tap-free", type=float, default=18.0,
                   help="what your tap delivers WIDE OPEN WITH NOTHING ON IT, "
                        "L/min. Measure it: bucket, stopwatch, 30 seconds. This "
                        "is the single number that makes the rest meaningful -- "
                        "a garden tap is limited by the supply pipe, not by its "
                        "own bore.")
    p.add_argument("--tap-bar", type=float, default=3.0,
                   help="supply pressure at which --tap-free was measured")
    a = p.parse_args()

    a_jet  = area(a.jet_d, a.jets)
    a_chan = area(a.chan_d, a.chan_n)
    a_gap  = area(a.gap_d)
    # Everything upstream -- pipe, valve, elbow -- collapsed into one effective
    # CdA derived from the free-flow measurement.
    cda_tap = (a.tap_free / 60000.0) / math.sqrt(2 * a.tap_bar * 1e5 / RHO)

    # Channel bundle: laminar friction over its length, folded into an
    # effective discharge coefficient. Short bundles are entrance-dominated.
    ld = a.chan_l / a.chan_d
    cd_chan = 1.0 / math.sqrt(1.0 + 0.5 + 0.06 * ld)

    chain = [R("tap + supply", cda_tap, 1.0), R("straightener", a_chan, cd_chan)]
    if a.jets:
        chain.insert(1, R("jet plate", a_jet, 0.62))

    print(f"tap wide open {a.tap_free:.1f} L/min at {a.tap_bar:.1f} bar"
          f"  -> effective CdA = {cda_tap*1e6:.1f} mm^2")
    if a.jets:
        print(f"jet plate     {a.jets:>3} x {a.jet_d:.2f} mm  = {a_jet*1e6:7.1f} mm^2")
    else:
        print("jet plate     none")
    print(f"straightener  {a.chan_n:>3} x {a.chan_d:.2f} mm  = {a_chan*1e6:7.1f} mm^2"
          f"   L/D = {ld:.1f}   Cd = {cd_chan:.2f}")
    if a.jets:
        print(f"open-area ratio straightener / jets = {a_chan/a_jet:.1f}x"
              f"   {'(good: jets spread across the gap before the channels)' if a_chan/a_jet > 3 else '(LOW: jets will punch straight through the channel field)'}")
    print()
    print("  supply     flow      jet vel   channel   stream")
    print("  ------------------------------------------------")
    for bar in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0):
        q = solve(bar * 1e5, chain)
        lpm = q * 60000
        v_exit = q / a_chan      # velocity IN the channels, which is what you feel
        soft = "gentle" if v_exit < 2.5 else "brisk" if v_exit < 4 else "hard"
        if a.jets:
            v_jet = q / a_jet
            note = "weak" if v_jet < 5 else "good" if v_jet < 25 else "very fast"
            print(f"  {bar:>4.1f} bar  {lpm:6.1f} L/min  {v_jet:6.1f} m/s  {v_exit:5.1f} m/s   {note}, {soft}")
        else:
            print(f"  {bar:>4.1f} bar  {lpm:6.1f} L/min       -     {v_exit:5.1f} m/s   {soft}")
    print()
    print("  A 10 L bucket at 3 bar: "
          f"{10.0 / (solve(3e5, chain) * 60000) * 60:.0f} s")
    print()
    print("Caveats: treats every restriction as a sharp orifice, ignores the")
    print("swirl breaker's loss. Measure with a bucket and a stopwatch, then")
    print("trust that over this.")

if __name__ == "__main__":
    main()
