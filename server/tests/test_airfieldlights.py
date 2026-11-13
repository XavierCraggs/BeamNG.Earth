"""airfieldlights: a lit, open runway's white edge lights both sides along its length (the end zones yellow), green
threshold and red end bars (a displaced threshold moves the green); none for an unlit, closed or water runway. Blue
taxiway edge lights both sides of a taxiway at an airport whose nearest runway is lit, none on the runway, in an apron,
for an unlit airport, without airport Features or on an unpaved way; the tile's forest rows split between the tiles.
Approach lights (a 900 m centreline row every 30 m before each end with a 300 m crossbar) on a runway over 1800 m or at a
large airport, PAPIs (two red, two white, 9 m apart, 15 m outside the edge on the landing aircraft's left, 300 m past the
threshold) on every lit paved runway; the ILS aerials (a localizer past each far end, a glide-slope mast at each
threshold) on a paved open runway over 1800 m, as forest rows facing the approach."""
import json
import os
import re
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
LENGTH, WIDTH = 1500.0, 45.72       # (under APPROACH_MIN_RUNWAY_M: no approach lights nor ILS aerials)
LONG = 3000.0
BOX = (-200.0, -300.0, 2100.0, 300.0)


def runway(length=LENGTH, type="medium_airport", **kw):
    """A runway from (40, -76) due east, `length` m long (airports.Runway)."""
    ap = af.airport(1, "KTST", 40.0, -76.0, 100, type=type)
    row = af.runway(1, ap, 40.0, -76.0, 90.0, length, width_m=WIDTH, **kw)
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
        zone = min(al.CAUTION_M, LENGTH / 3.0)
        yellow, _ = en(self.lights, al.EDGE, al.YELLOW)
        white, _ = en(self.lights, al.EDGE, al.WHITE)
        self.assertTrue(len(yellow) and len(white))
        self.assertTrue(((yellow < zone + 1) | (yellow > LENGTH - zone - 1)).all())
        self.assertTrue(((white > zone - 1) & (white < LENGTH - zone + 1)).all())

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
                          ((al.WHITE, al.EDGE), (al.YELLOW, al.EDGE), (al.GREEN, al.THRESHOLD), (al.RED, al.END),
                           (al.RED, al.PAPI), (al.WHITE, al.PAPI))})

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


class ApproachAndPapi(unittest.TestCase):
    def test_approach_row_900_m_before_each_end_with_a_crossbar(self):
        lights = al.runway_lights(runway(LONG))
        e, n = en(lights, al.APPROACH, al.WHITE)
        self.assertEqual(len(e), len(en(lights, al.APPROACH)[0]))          # (all white)
        centre = np.sort(e[np.abs(n) < 0.5])
        for row, edge in ((centre[centre < 0], 0.0), (centre[centre > LONG], LONG)):
            self.assertEqual(len(row), int(al.APPROACH_LEN_M / al.APPROACH_STEP_M))
            self.assertAlmostEqual(float(np.abs(row - edge).min()), al.APPROACH_STEP_M, delta=0.5)
            self.assertAlmostEqual(float(np.abs(row - edge).max()), al.APPROACH_LEN_M, delta=0.5)
            self.assertTrue(np.allclose(np.diff(row), al.APPROACH_STEP_M, atol=0.05))
        for edge, sign in ((0.0, -1.0), (LONG, 1.0)):
            bar = n[np.abs(e - (edge + sign * al.APPROACH_BAR_AT_M)) < 1.0]
            self.assertAlmostEqual(float(bar.min()), -al.APPROACH_BAR_W_M / 2, delta=0.3)
            self.assertAlmostEqual(float(bar.max()), al.APPROACH_BAR_W_M / 2, delta=0.3)
            self.assertEqual(len(bar), int(al.APPROACH_BAR_W_M / al.APPROACH_BAR_STEP_M) + 1)     # (the middle one once)
        self.assertEqual(len(e), 2 * (30 + 10))
        self.assertTrue(((e < 0) | (e > LONG)).all())                       # (none on the runway)

    def test_approach_lights_by_length_or_large_airport_and_paving(self):
        def has(rw):
            return len(en(al.runway_lights(rw), al.APPROACH)[0]) > 0
        self.assertTrue(has(runway(1900.0)))
        self.assertFalse(has(runway(1700.0)))
        self.assertFalse(has(runway(1700.0, surface="GRS")))
        self.assertTrue(has(runway(1500.0, type="large_airport")))
        self.assertFalse(has(runway(LONG, surface="GRS")))
        self.assertFalse(has(runway(LONG, lighted=0)))
        self.assertFalse(has(runway(LONG, closed=1)))

    def test_papi_four_units_left_of_the_landing_aircraft_two_red_two_white(self):
        lights = al.runway_lights(runway(LONG))
        out = WIDTH / 2 + al.PAPI_OFF_M
        for colour, want in ((al.RED, (0, 1)), (al.WHITE, (2, 3))):
            e, n = en(lights, al.PAPI, colour)
            self.assertEqual(len(e), 4)                                   # (two a landing end)
            for i in want:
                # landing toward the high end the left is north (+t) 300 m in; back the other way it is south
                for x, side in ((al.PAPI_AT_M, 1.0), (LONG - al.PAPI_AT_M, -1.0)):
                    hit = (np.abs(e - x) < 1.0) & (np.abs(n - side * (out + i * al.PAPI_STEP_M)) < 0.5)
                    self.assertEqual(int(hit.sum()), 1, (colour, i, x))
        self.assertEqual(len(en(lights, al.PAPI)[0]), 8)

    def test_papi_follows_the_displaced_threshold_and_needs_a_lit_paved_long_runway(self):
        e, _ = en(al.runway_lights(runway(LONG, le_disp_ft=600)), al.PAPI)
        self.assertAlmostEqual(float(e.min()), 600 * airports.FT + al.PAPI_AT_M, delta=1.0)

        def has(rw):
            return len(en(al.runway_lights(rw), al.PAPI)[0]) > 0
        self.assertTrue(has(runway(1000.0)))
        self.assertFalse(has(runway(800.0)))
        self.assertFalse(has(runway(1000.0, surface="GRS")))
        self.assertFalse(has(runway(1000.0, lighted=0)))


class IlsMasts(unittest.TestCase):
    def setUp(self):
        self.masts = al.ils_masts(runway(LONG))

    def at(self, group):
        out = []
        for m in self.masts:
            if m.group == group:
                e, n, _ = FRAME.geodetic_to_enu(np.array([m.lat]), np.array([m.lon]), 0.0)
                e2, n2, _ = FRAME.geodetic_to_enu(np.array([m.lat_to]), np.array([m.lon_to]), 0.0)
                out.append((float(e[0]), float(n[0]), float(e2[0] - e[0]), float(n2[0] - n[0])))
        return sorted(out)

    def test_a_localizer_past_each_far_end_facing_down_the_runway(self):
        (xa, ya, dxa, _), (xb, yb, dxb, _) = self.at("ils_loc")
        self.assertAlmostEqual(xa, -al.LOC_AT_M, delta=0.5)
        self.assertAlmostEqual(xb, LONG + al.LOC_AT_M, delta=0.5)
        self.assertAlmostEqual(ya, 0.0, delta=0.5)
        self.assertAlmostEqual(yb, 0.0, delta=0.5)
        self.assertGreater(dxa, 9.0)                    # (its front toward the runway)
        self.assertLess(dxb, -9.0)
        # it stands between the approach lights' rows of the end it is past (clear of the crossbar's)
        rows = np.arange(al.APPROACH_STEP_M, al.APPROACH_LEN_M + 1, al.APPROACH_STEP_M)
        self.assertGreater(float(np.abs(rows - al.LOC_AT_M).min()), 10.0)

    def test_a_glide_slope_mast_at_each_threshold_off_the_side_opposite_the_papi(self):
        (xa, ya, dxa, _), (xb, yb, dxb, _) = self.at("ils_gs")
        self.assertAlmostEqual(xa, al.GS_AT_M, delta=0.5)
        self.assertAlmostEqual(ya, -al.GS_OFF_M, delta=0.5)       # (landing toward the high end the PAPI is at +t)
        self.assertAlmostEqual(xb, LONG - al.GS_AT_M, delta=0.5)
        self.assertAlmostEqual(yb, al.GS_OFF_M, delta=0.5)
        self.assertLess(dxa, -9.0)                      # (each faces the approach it serves)
        self.assertGreater(dxb, 9.0)

    def test_only_over_1800_m_paved_and_open(self):
        for rw in (runway(1700.0), runway(LONG, surface="GRS"), runway(LONG, closed=1), runway(LONG, surface="WATER")):
            self.assertEqual(al.ils_masts(rw), [])
        self.assertEqual(len(al.ils_masts(runway(LONG, lighted=0))), 4)          # (an ILS runway need not be lit)
        self.assertEqual(len(self.masts), 4)

    def test_memoised(self):
        self.assertIs(al.ils_masts(runway(LONG)), al.ils_masts(runway(LONG)))

    def test_rows_in_their_groups_on_the_ground_facing_the_approach(self):
        ground = lambda lat, lon: np.full(np.shape(lat), 12.0)

        def rows(box):
            return al.tile_rows(FRAME, box, lambda k: None, lambda k: [runway(LONG)], ground, keys=[0])
        whole = rows((-1500.0, -400.0, 4500.0, 400.0))
        masts = [r for r in whole if r[0] in al.ILS_H]
        self.assertEqual(sorted(r[0] for r in masts), ["ils_gs", "ils_gs", "ils_loc", "ils_loc"])
        for r in masts:
            self.assertEqual((len(r), r[5], r[6], r[7]), (8, 1.0, al.ILS_H[r[0]], 0.0))
            self.assertAlmostEqual(r[3], 12.0, delta=1.5)                     # (no lift; the frame's up falls with the curvature)
        yaw = {(r[0], r[1] < LONG / 2): r[4] for r in masts}
        # (the shape's +Y at yaw 0 is north, the yaw counter-clockwise: toward +x is 270, toward -x is 90)
        self.assertAlmostEqual(yaw[("ils_loc", True)], 270.0, delta=0.5)
        self.assertAlmostEqual(yaw[("ils_loc", False)], 90.0, delta=0.5)
        self.assertAlmostEqual(yaw[("ils_gs", True)], 90.0, delta=0.5)
        self.assertAlmostEqual(yaw[("ils_gs", False)], 270.0, delta=0.5)
        a, b = rows((-1500.0, -400.0, 1500.0, 400.0)), rows((1500.0, -400.0, 4500.0, 400.0))
        self.assertEqual(len(a) + len(b), len(whole))                         # (each in one tile)
        self.assertEqual(sum(r[0] in al.ILS_H for r in a + b), 4)
        self.assertTrue({r[0] for r in whole} - set(al.ILS_H) <= set(al.GROUPS.values()))       # (the rest glow rows)
        self.assertEqual(len(whole) - 4, len(al.runway_lights(runway(LONG))))


class Shapes(unittest.TestCase):
    """The generated shapes (tools/build_ils.py) are the ones the rows are made for."""
    SHAPES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mod", "beamng_earth", "levels",
                          "beamng_earth", "art", "shapes", "beamngEarth")

    def read(self, kind):
        with open(os.path.join(self.SHAPES, f"bne_ils_{kind}.dae"), encoding="utf-8") as f:
            text = f.read()
        geoms = {m.group(1): np.array(m.group(2).split(), np.float64).reshape(-1, 3)
                 for m in re.finditer(r'<float_array id="([^"]*-p-a)"[^>]*>([^<]*)<', text)}
        return text, geoms

    def test_heights_widths_two_lods_the_front_toward_plus_y(self):
        for kind, group in (("loc", "ils_loc"), ("gs", "ils_gs")):
            text, geoms = self.read(kind)
            self.assertEqual(sorted(re.findall(rf'<node id="(bne_ils_{kind}\d+)"', text)),
                             sorted([f"bne_ils_{kind}96", f"bne_ils_{kind}12"]), "two levels of detail")
            self.assertNotIn("Colmesh", text)
            self.assertEqual(len(geoms), 2)
            for v in geoms.values():
                self.assertAlmostEqual(float(v[:, 2].max()), al.ILS_H[group], delta=0.01)       # (the catalogue height)
                self.assertGreaterEqual(float(v[:, 2].min()), -0.03)                             # (on the ground)
                self.assertGreater(float(v[:, 1].max()), float(-v[:, 1].min()))                  # (the front is +Y)
            tris = sum(int(c) for c in re.findall(r'<triangles count="(\d+)"', text))
            self.assertLess(tris, 1500)
        loc = max(self.read("loc")[1].values(), key=len)
        self.assertAlmostEqual(float(loc[:, 0].max() - loc[:, 0].min()), 30.0, delta=0.5)       # about 30 m wide, 3 m tall

    def test_the_materials_are_there(self):
        with open(os.path.join(self.SHAPES, "ils.materials.json"), encoding="utf-8") as f:
            mats = json.load(f)
        names = set()
        for kind in ("loc", "gs"):
            names |= set(re.findall(r'target="#([^"]+)-mat"', self.read(kind)[0]))
        self.assertTrue(names and names <= set(mats), names)


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
