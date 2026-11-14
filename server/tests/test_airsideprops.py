"""airsideprops: the ground vehicles at the parked aircraft keep off every building and building part (a canopy or a
covered walkway, any height) by CLEAR_BUILDING_M, as the aircraft do; a gate's own jet bridge is no obstacle."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import airsideprops as ap  # noqa: E402
import parkedaircraft as pa  # noqa: E402
from test_parkedaircraft import FRAME, TERMINAL, aerodrome, buildings, feats, gate, line, parts, poly  # noqa: E402

VEHICLES = {g: k for k, g in ap.GROUPS.items() if k not in ("container", "cone")}


def vehicles(got):
    """[(kind, footprint points (n, 2) east / north of the test frame's origin)] of the vehicles in the Props."""
    out = []
    for p in got:
        if p.group not in VEHICLES:
            continue
        e, n, _ = FRAME.geodetic_to_enu(np.array([p.lat]), np.array([p.lon]), 0.0)
        out.append((VEHICLES[p.group], ap._box_pts(VEHICLES[p.group], float(e[0]), float(n[0]), p.he, p.hn)))
    return out


def stand_row():
    """One Features (the ids fix the hashes: the runs compared share it), with vehicles to test."""
    while True:
        f = feats(aerodrome("regional_airport"), *[gate(x) for x in (-90.0, -30.0, 30.0, 90.0)], occupied=True)
        if len(vehicles(ap.props(f, [buildings(TERMINAL)]))) > 3:
            return f


class Vehicles(unittest.TestCase):
    def test_vehicles_keep_off_small_buildings_and_parts(self):
        f = stand_row()
        base = vehicles(ap.props(f, [buildings(TERMINAL)]))
        self.assertGreater(len(base), 3)
        # a 3 m shed (building) and a 3 m canopy (part) on the first two vehicles' footprints
        rings = []
        for _k, pts in base[:2]:
            c = pts.mean(axis=0)
            rings.append([(c[0] - 1.5, c[1] - 1.5), (c[0] + 1.5, c[1] - 1.5), (c[0] + 1.5, c[1] + 1.5), (c[0] - 1.5, c[1] + 1.5)])
        got = vehicles(ap.props(f, [buildings(TERMINAL, rings[0]), parts(rings[1])]))
        self.assertTrue(got)
        for _k, pts in got:
            for r in rings:
                r = np.array(r, np.float64)
                self.assertFalse(pa._pip(r, pts).any())
                self.assertGreater(pa._seg_dist(pts, r, np.roll(r, -1, axis=0)).min(), ap.CLEAR_BUILDING_M - 0.4)

    def test_a_jet_bridge_is_no_obstacle_to_the_vehicles_of_its_gate(self):
        bridges = [[(x - 2, -3), (x + 2, -3), (x + 2, 30), (x - 2, 30)] for x in (-90.0, -30.0, 30.0, 90.0)]
        f = stand_row()                                                  # (each gate touches its bridge: it is no obstacle)
        for blds in ([buildings(TERMINAL), parts(*bridges)], [buildings(TERMINAL, *bridges)]):
            self.assertEqual(len(pa.stands(f, blds)), 4)
            self.assertTrue(vehicles(ap.props(f, blds)))


def masts(got):
    """[(x, y)] of the masts in the Props, east / north of the test frame's origin."""
    out = []
    for p in got:
        if p.group == ap.MAST_GROUP:
            e, n, _ = FRAME.geodetic_to_enu(np.array([p.lat]), np.array([p.lon]), 0.0)
            out.append((float(e[0]), float(n[0])))
    return out


class Masts(unittest.TestCase):
    APRON = [(-150, 0), (150, 0), (150, 200), (-150, 200)]
    TAXIWAY = (line((-300, 10), (300, 10)), "taxiway", {})
    RUNWAY = (line((-300, 250), (300, 250)), "runway", {})

    def rows(self, *extra):
        return feats(aerodrome("regional_airport"), (poly(self.APRON), "apron", {}), *extra)

    def test_masts_stand_in_the_apron_off_the_taxiways_and_runways(self):
        free = masts(ap.props(self.rows(), []))
        got = masts(ap.props(self.rows(self.TAXIWAY, self.RUNWAY), []))
        self.assertGreater(len(free), 3)
        self.assertGreater(len(got), 0)
        self.assertLess(len(got), len(free))                         # (the ones by the taxiway and the runway are gone)
        apron = np.array(self.APRON, np.float64)
        for x, y in got:
            self.assertTrue(pa._pip(apron, np.array([[x, y]]))[0])
            self.assertGreaterEqual(abs(y - 10.0), ap.MAST_TAXI_M)
            self.assertGreaterEqual(abs(y - 250.0), ap.MAST_RUNWAY_M)

    def test_no_mast_on_a_stand(self):
        f = feats(aerodrome("regional_airport"), (poly(self.APRON), "apron", {}), gate(-60.0, 1.5), gate(60.0, 1.5), occupied=True)
        for x, y in masts(ap.props(f, [])):
            for gx in (-60.0, 60.0):
                self.assertGreaterEqual(math.hypot(x - gx, y - 1.5), ap.MAST_GATE_M)


if __name__ == "__main__":
    unittest.main()
