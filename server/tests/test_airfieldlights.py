"""airfieldlights: a lit, open runway's white edge lights both sides along its length (the end zones yellow), green
threshold and red end bars (a displaced threshold moves the green); none for an unlit, closed or water runway. Blue
taxiway edge lights both sides of a taxiway at an airport whose nearest runway is lit, none on the runway, in an apron,
for an unlit airport, without airport Features or on an unpaved way; the tile's forest rows split between the tiles."""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aeroways  # noqa: E402
import airfieldlights as al  # noqa: E402
import airportfixtures as af  # noqa: E402
import airports  # noqa: E402
import geodesy  # noqa: E402
import mapgeom  # noqa: E402

FRAME = geodesy.EnuFrame(40.0, -76.0)       # the runway's low end is its origin, the runway runs east
LENGTH, WIDTH = 1800.0, 45.72
BOX = (-200.0, -300.0, 2100.0, 300.0)


def runway(**kw):
    """A runway from (40, -76) due east, LENGTH m long (airports.Runway)."""
    ap = af.airport(1, "KTST", 40.0, -76.0, 100)
    row = af.runway(1, ap, 40.0, -76.0, 90.0, LENGTH, width_m=WIDTH, **kw)
    return airports.AirportDB.from_csv(af.to_csv([ap], af.AIRPORT_COLS), af.to_csv([row], af.RUNWAY_COLS)).runways[0]


def en(lights, kind=None, colour=None):
    """The lights' (east, north) in FRAME, optionally of a kind / colour."""
    e, n, _ = FRAME.geodetic_to_enu(lights.lat, lights.lon, 0.0)
    keep = np.ones(len(lights), bool)
    if kind is not None:
        keep &= lights.kind == al.KINDS.index(kind)
    if colour is not None:
        keep &= lights.colour == al.COLOURS.index(colour)
    return np.asarray(e)[keep], np.asarray(n)[keep]


def lonlat(pts):
    la, lo, _ = FRAME.enu_to_geodetic(np.array([p[0] for p in pts], np.float64),
                                      np.array([p[1] for p in pts], np.float64), 0.0)
    return np.stack([lo, la], 1)


def feats(*rows):
    """Infrastructure Features of (kind, points in FRAME, class, subtype, tags dict, surface) rows."""
    ids = np.array([f"f{i:03d}" for i in range(len(rows))])
    geoms = []
    for kind, pts, *_ in rows:
        pts = list(pts) + ([pts[0]] if kind == mapgeom.POLYGON else [])
        geoms.append((kind, [[lonlat(pts)]]))
    f = mapgeom.build("infrastructure", ids, geoms)
    f.attrs = {"class": mapgeom.text_column([r[2] for r in rows]), "subtype": mapgeom.text_column([r[3] for r in rows]),
               "tags": mapgeom.text_column([json.dumps(r[4]) for r in rows]),
               "surface": mapgeom.text_column([r[5] for r in rows])}
    return f


def way(pts, cls="taxiway", sub="airport", tags=None, surface=None):
    return (mapgeom.LINE, pts, cls, sub, tags or {}, surface)


def area(pts, cls="apron"):
    return (mapgeom.POLYGON, pts, cls, "airport", {}, None)


def half(intl):
    return (aeroways.TAXIWAY_INTL_M if intl else aeroways.TAXIWAY_M) / 2.0


PARALLEL = [(200.0, 150.0), (1600.0, 150.0)]
CROSSING = [(900.0, -120.0), (900.0, 120.0)]


class RunwayLights(unittest.TestCase):
    def setUp(self):
        self.lights = al.runway_lights(runway())

    def test_edge_lights_both_sides_the_runway_long(self):
        e, n = en(self.lights, al.EDGE)
        out = WIDTH / 2 + al.EDGE_OUT_M
        for side in (out, -out):
            east = np.sort(e[np.abs(n - side) < 0.5])
            self.assertAlmostEqual(east[0], 0.0, delta=1.0)
            self.assertAlmostEqual(east[-1], LENGTH, delta=1.0)
            self.assertLessEqual(float(np.diff(east).max()), al.EDGE_SPACING_M + 1.0)
        self.assertAlmostEqual(len(e), 2 * (LENGTH / al.EDGE_SPACING_M + 1), delta=2)      # (the length to a metre)

    def test_end_zones_yellow_the_rest_white(self):
        yellow, _ = en(self.lights, al.EDGE, al.YELLOW)
        white, _ = en(self.lights, al.EDGE, al.WHITE)
        self.assertTrue(len(yellow) and len(white))
        self.assertTrue(((yellow < al.CAUTION_M + 1) | (yellow > LENGTH - al.CAUTION_M - 1)).all())
        self.assertTrue(((white > al.CAUTION_M - 1) & (white < LENGTH - al.CAUTION_M + 1)).all())

    def test_green_threshold_and_red_end_bars_across_the_runway(self):
        for colour, kind, at in ((al.GREEN, al.THRESHOLD, (0.0, LENGTH)),
                                 (al.RED, al.END, (-al.BAR_OUT_M, LENGTH + al.BAR_OUT_M))):
            e, n = en(self.lights, kind, colour)
            for x in at:
                bar = n[np.abs(e - x) < 1.0]
                self.assertGreaterEqual(len(bar), int(WIDTH / al.BAR_SPACING_M))
                self.assertAlmostEqual(float(bar.min()), -WIDTH / 2, delta=1.0)
                self.assertAlmostEqual(float(bar.max()), WIDTH / 2, delta=1.0)
            self.assertEqual(len(e), 2 * len(bar))
        # each colour on its own kind only
        self.assertEqual(set(zip(self.lights.colour.tolist(), self.lights.kind.tolist())),
                         {(al.COLOURS.index(c), al.KINDS.index(k)) for c, k in
                          ((al.WHITE, al.EDGE), (al.YELLOW, al.EDGE), (al.GREEN, al.THRESHOLD), (al.RED, al.END))})

    def test_displaced_threshold_moves_the_green_bar(self):
        e, _ = en(al.runway_lights(runway(le_disp_ft=600)), al.THRESHOLD, al.GREEN)
        self.assertAlmostEqual(float(e.min()), 600 * airports.FT, delta=1.0)
        self.assertAlmostEqual(float(e.max()), LENGTH, delta=1.0)

    def test_unlit_closed_and_water_runways_have_none(self):
        self.assertEqual(len(al.runway_lights(runway(lighted=0))), 0)
        self.assertEqual(len(al.runway_lights(runway(closed=1))), 0)
        self.assertEqual(len(al.runway_lights(runway(surface="WATER"))), 0)

    def test_memoised(self):
        self.assertIs(al.runway_lights(runway()), al.runway_lights(runway()))
        self.assertIsNot(al.runway_lights(runway()), al.runway_lights(runway(lighted=0)))


class TaxiwayLights(unittest.TestCase):
    def setUp(self):
        self.rw = runway()

    def lights(self, *rows, runways=None):
        return al.taxiway_lights(feats(*rows), [self.rw] if runways is None else runways)

    def test_blue_on_both_edges_of_a_taxiway(self):
        got = self.lights(way(PARALLEL))
        self.assertEqual(set(got.colour.tolist()), {al.COLOURS.index(al.BLUE)})
        e, n = en(got)
        out = half(False) + al.TAXI_OUT_M
        for side in (150.0 + out, 150.0 - out):
            east = np.sort(e[np.abs(n - side) < 0.5])
            self.assertAlmostEqual(east[0], 200.0, delta=1.0)
            self.assertAlmostEqual(east[-1], 1600.0, delta=1.0)
            self.assertLessEqual(float(np.diff(east).max()), al.TAXI_SPACING_M + 1.0)
        self.assertAlmostEqual(len(e), 2 * (1400.0 / al.TAXI_SPACING_M + 1), delta=2)

    def test_wider_at_an_international_airport_and_by_the_tag(self):
        intl = area([(-900, -900), (900, -900), (900, 900), (-900, 900)], "international_airport")
        _, n = en(self.lights(way(PARALLEL), intl))
        self.assertAlmostEqual(float(n.max()), 150.0 + half(True) + al.TAXI_OUT_M, delta=0.5)
        _, n = en(self.lights(way(PARALLEL, tags={"width": "30"})))
        self.assertAlmostEqual(float(n.max()), 150.0 + 15.0 + al.TAXI_OUT_M, delta=0.5)

    def test_none_on_the_runway(self):
        e, n = en(self.lights(way(CROSSING)))
        self.assertGreater(len(e), 0)
        self.assertFalse((np.abs(n) < WIDTH / 2 + al.RUNWAY_CLEAR_M - 0.01).any())

    def test_none_inside_an_apron_or_another_ways_pavement(self):
        ring = [(500.0, 100.0), (900.0, 100.0), (900.0, 200.0), (500.0, 200.0)]
        e, _ = en(self.lights(way(PARALLEL), area(ring)))
        self.assertFalse(((e > 500) & (e < 900)).any())
        self.assertTrue(((e < 500) | (e > 900)).any())
        # a spur ending on the parallel way: its lights inside that way's pavement are left out
        e, n = en(self.lights(way(PARALLEL), way([(900.0, 150.0), (900.0, 400.0)])))
        self.assertFalse(((np.abs(e - 900.0) < 9.0) & (np.abs(n - 150.0) < half(False) + al.PAVEMENT_CLEAR_M - 0.01)).any())
        self.assertTrue((n > 170.0).any())

    def test_only_where_the_nearest_runway_is_lit(self):
        self.assertEqual(len(self.lights(way(PARALLEL), runways=[runway(lighted=0)])), 0)
        self.assertEqual(len(self.lights(way(PARALLEL), runways=[runway(closed=1)])), 0)
        self.assertEqual(len(self.lights(way(PARALLEL), runways=[])), 0)
        self.assertEqual(len(self.lights(way([(20200.0, 150.0), (21600.0, 150.0)]))), 0)

    def test_not_unpaved_unlit_taxilane_or_other_features(self):
        self.assertEqual(len(self.lights(way(PARALLEL, surface="grass"))), 0)
        self.assertEqual(len(self.lights(way(PARALLEL, tags={"lit": "no"}))), 0)
        self.assertEqual(len(self.lights(way(PARALLEL, cls="taxilane"))), 0)
        self.assertEqual(len(self.lights(way(PARALLEL, sub="transit"))), 0)
        self.assertEqual(len(self.lights(way(PARALLEL, cls="road", sub="road"))), 0)
        self.assertEqual(len(al.taxiway_lights(None, [self.rw])), 0)

    def test_memoised_on_the_features(self):
        f = feats(way(PARALLEL))
        self.assertIs(al.taxiway_lights(f, [self.rw]), al.taxiway_lights(f, [self.rw]))
        self.assertEqual(len(al.taxiway_lights(f, [runway(lighted=0)])), 0)
        self.assertGreater(len(al.taxiway_lights(f, [self.rw])), 0)


class TileRows(unittest.TestCase):
    def setUp(self):
        self.rw = runway()
        self.f = feats(way(PARALLEL), way(CROSSING))
        self.ground = lambda lat, lon: np.full(np.shape(lat), 12.0)

    def rows(self, box):
        return al.tile_rows(FRAME, box, lambda k: self.f, lambda k: [self.rw], self.ground, keys=[0])

    def test_rows_in_the_colours_groups_on_the_ground(self):
        rows = self.rows(BOX)
        full = al.Lights.join([al.runway_lights(self.rw), al.taxiway_lights(self.f, [self.rw])])
        self.assertEqual(len(rows), len(full))
        self.assertEqual({r[0] for r in rows}, set(al.GROUPS.values()))
        for r in rows:
            self.assertEqual(len(r), 8)
            self.assertAlmostEqual(r[3], 12.0 + al.LIFT_M, delta=0.6)      # (the frame's up falls with the curvature)
            self.assertEqual(r[6], al.GROUP_H)

    def test_each_light_in_one_tile(self):
        whole = self.rows(BOX)
        a, b = self.rows((-200.0, -300.0, 900.0, 300.0)), self.rows((900.0, -300.0, 2100.0, 300.0))
        self.assertEqual(len(a) + len(b), len(whole))
        self.assertTrue(all(r[1] < 900.0 for r in a) and all(r[1] >= 900.0 for r in b))
        self.assertEqual(self.rows((5000.0, 5000.0, 5500.0, 5500.0)), [])

    def test_no_airport_no_rows(self):
        self.assertEqual(al.tile_rows(FRAME, BOX, lambda k: None, lambda k: [], self.ground, keys=[0]), [])
        plain = feats(way(PARALLEL, sub="transit"))
        self.assertEqual(al.tile_rows(FRAME, BOX, lambda k: plain, lambda k: [runway(lighted=0)], self.ground, keys=[0]), [])


if __name__ == "__main__":
    unittest.main()
