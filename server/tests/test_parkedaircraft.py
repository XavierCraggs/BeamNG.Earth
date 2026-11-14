"""parkedaircraft: an airliner parks nose-in at each occupied terminal gate (its axis across the facade, the nose
NOSE_GAP_M off it, the centre off the building) by a hash of the gate's id; its type follows the aerodrome's class; a
jet bridge sets the nose and moves the aircraft aside; none overlap each other, a building, a runway, a taxiway or a
taxilane's centreline; general-aviation aprons get rows of light aircraft; Features without gates or aprons, or a gate
without a terminal, give none; each aircraft is in exactly one tile."""
import json
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import geodesy  # noqa: E402
import mapgeom  # noqa: E402
import parkedaircraft as pa  # noqa: E402

FRAME = geodesy.EnuFrame(-27.39, 153.118)
TERMINAL = [(-200, -40), (200, -40), (200, 0), (-200, 0)]          # the facade is y = 0, outward +y
BOX = (-400.0, -300.0, 400.0, 300.0)
_IDS = iter(range(10 ** 6))


def lonlat(pts):
    la, lo, _ = FRAME.enu_to_geodetic(np.array([p[0] for p in pts], np.float64),
                                      np.array([p[1] for p in pts], np.float64), 0.0)
    return np.stack([lo, la], 1)


def poly(pts):
    return (mapgeom.POLYGON, [[lonlat(list(pts) + [pts[0]])]])


def line(*pts):
    return (mapgeom.LINE, [[lonlat(pts)]])


def point(x, y):
    return (mapgeom.POINT, [[lonlat([(x, y)])]])


def feats(*rows, occupied=None):
    """Infrastructure Features of (geometry, class, tags dict[, name]) rows, subtype airport; ids unique over the tests,
    in row order. occupied: the Features' ids are drawn until every row from index 1 on is (True) / is not (False) one
    the occupancy hash fills."""
    while True:
        base = next(_IDS)
        ids = np.array([f"{base:06d}{i:03d}" for i in range(len(rows))])
        if occupied is None or all((pa._crc(i) % 100 < pa.OCCUPIED_PCT) == occupied for i in ids[1:]):
            break
    f = mapgeom.build("infrastructure", ids, [r[0] for r in rows])
    f.attrs = {"class": mapgeom.text_column([r[1] for r in rows]), "subtype": mapgeom.text_column(["airport"] * len(rows)),
               "tags": mapgeom.text_column([json.dumps(r[2] if len(r) > 2 else {}) for r in rows]),
               "name": mapgeom.text_column([r[3] if len(r) > 3 else "" for r in rows]),
               "surface": mapgeom.text_column([None] * len(rows))}
    return f


def buildings(*polys, prefix="b"):
    return mapgeom.build("buildings", np.array([f"{prefix}{i:03d}" for i in range(len(polys))]), [poly(p) for p in polys])


def parts(*polys):
    """Building parts Features (canopies, covered walkways: the footprints of raised parts count the same)."""
    return mapgeom.build("building_parts", np.array([f"p{i:03d}" for i in range(len(polys))]), [poly(p) for p in polys])


def aerodrome(cls="international_airport"):
    return (poly([(-1500, -1500), (1500, -1500), (1500, 1500), (-1500, 1500)]), cls, {})


def gate(x, y=-1.5):
    return (point(x, y), "airport_gate", {"aeroway": "gate"})


def en(c):
    e, n, _ = FRAME.geodetic_to_enu(np.array([c.lat]), np.array([c.lon]), 0.0)
    return float(e[0]), float(n[0])


def ground(lat, lon):
    return np.full(np.shape(lat), 5.0)


def gates_row(n=6, gap=80.0, cls="international_airport", **kw):
    xs = [-160.0 + i * gap for i in range(n)]
    return feats(aerodrome(cls), *[gate(x) for x in xs], **kw), xs


class Gates(unittest.TestCase):
    def test_nose_in_toward_the_facade_off_the_building(self):
        f, xs = gates_row(5, 80.0)
        got = pa.stands(f, buildings(TERMINAL))
        self.assertGreaterEqual(len(got), 2)
        for c in got:
            x, y = en(c)
            half = pa.SPECS[c.kind][0] / 2.0
            self.assertAlmostEqual(c.ne, 0.0, 2)
            self.assertAlmostEqual(c.nn, -1.0, 2)                       # the nose toward the terminal
            self.assertAlmostEqual(y, pa.NOSE_GAP_M + half, delta=0.6)   # the nose NOSE_GAP_M off the facade
            self.assertTrue(any(abs(x - gx) < 0.6 for gx in xs))
            self.assertGreater(y - half, 0.0)                           # off the building

    def test_occupancy_is_a_hash_of_the_id_and_deterministic(self):
        f, xs = gates_row(6, 80.0)
        a = pa.stands(f, buildings(TERMINAL))
        f2, _ = gates_row(6, 80.0)
        f2.ids = f.ids                                                  # (the same ids: the same hashes)
        self.assertEqual(a, pa.stands(f2, buildings(TERMINAL)))
        want = [x for gid, x in zip(f.ids[1:], xs) if pa._crc(str(gid)) % 100 < pa.OCCUPIED_PCT]
        self.assertEqual(sorted(round(en(c)[0]) for c in a), sorted(round(x) for x in want))
        full, _ = gates_row(6, 80.0, occupied=True)
        self.assertEqual(len(pa.stands(full, buildings(TERMINAL))), 6)
        empty, _ = gates_row(6, 80.0, occupied=False)
        self.assertEqual(pa.stands(empty, buildings(TERMINAL)), [])

    def test_no_overlaps_among_dense_gates(self):
        f = feats(aerodrome(), *[gate(-100.0 + i * 8.0) for i in range(20)])
        got = pa.stands(f, buildings(TERMINAL))
        self.assertGreater(len(got), 1)
        placed = [(c.kind,) + en(c) + (c.ne, c.nn) for c in got]
        for i, (k, x, y, nx, ny) in enumerate(placed):
            for k2, x2, y2, nx2, ny2 in placed[i + 1:]:
                pts = pa._world(pa._local_points(k2), x2, y2, nx2, ny2)
                self.assertFalse(pa._in_rects(k, x, y, nx, ny, pts, 0.0).any())

    def test_closely_mapped_gates_still_get_alternate_aircraft(self):
        f = feats(aerodrome(), *[gate(-60.0 + i * 12.0) for i in range(10)], occupied=True)
        got = pa.stands(f, buildings(TERMINAL))
        xs = sorted(en(c)[0] for c in got)
        self.assertGreaterEqual(len(got), 3)                            # (not only the first of a cluster)
        self.assertGreater(xs[-1] - xs[0], 60.0)
        self.assertLess(len(got), 10)                                   # (a wing span is wider than 12 m)

    def test_a_gate_in_a_pier_drawn_into_the_terminal_parks_beyond_its_tip(self):
        block = [(-200, -40), (200, -40), (200, 0), (6, 0), (6, 60), (-6, 60), (-6, 0), (-200, 0)]     # a 12 m pier, 60 m out
        f = feats(aerodrome("regional_airport"), gate(0.0, 55.0), occupied=True)
        got = pa.stands(f, buildings(block))
        self.assertEqual(len(got), 1)
        x, y = en(got[0])
        half = pa.SPECS[got[0].kind][0] / 2.0
        self.assertAlmostEqual(got[0].nn, -1.0, 2)                      # the nose toward the pier's tip
        self.assertAlmostEqual(y - half, 60.0 + pa.NOSE_GAP_M, delta=0.6)

    def test_a_gate_by_a_cell_edge_uses_the_neighbours_buildings(self):
        f, _ = gates_row(3, 100.0, occupied=True)
        self.assertEqual(pa.stands(f, buildings([(500, 500), (520, 500), (520, 520), (500, 520)])), [])
        f2, _ = gates_row(3, 100.0, occupied=True)
        self.assertEqual(len(pa.stands(f2, [None, buildings(TERMINAL)])), 3)       # (the cell's own: none; a neighbour's)

    def test_pavement_and_taxilane_centreline_drop_an_aircraft(self):
        rows = [aerodrome()] + [gate(x) for x in (-100.0, 0.0, 100.0)]
        base = feats(*rows, occupied=True)
        self.assertEqual(len(pa.stands(base, buildings(TERMINAL))), 3)
        for cls, tags in (("taxiway", {}), ("taxilane", {}), ("runway", {"width": "45"})):
            f = feats(*rows, (line((-300, 22), (300, 22)), cls, tags), occupied=True)     # through the fuselages
            self.assertEqual(pa.stands(f, buildings(TERMINAL)), [], cls)
        far = feats(*rows, (line((-300, 90), (300, 90)), "taxiway", {}), occupied=True)  # clear of the tails
        self.assertEqual(len(pa.stands(far, buildings(TERMINAL))), 3)

    def test_no_terminal_no_aircraft(self):
        f, _ = gates_row(5, occupied=True)
        self.assertEqual(pa.stands(f, None), [])
        self.assertEqual(pa.stands(f, buildings([(500, 500), (520, 500), (520, 520), (500, 520)])), [])

    def test_jet_bridge_sets_the_nose_and_the_side(self):
        f = feats(aerodrome("regional_airport"), gate(0.0), occupied=True)
        got = pa.stands(f, buildings(TERMINAL, [(-2, -3), (2, -3), (2, 30), (-2, 30)]))     # a bridge 30 m out
        self.assertEqual(len(got), 1)
        c = got[0]
        x, y = en(c)
        half = pa.SPECS[c.kind][0] / 2.0
        self.assertAlmostEqual(y - half, 30.0 - pa.BACK_M[c.kind], delta=0.6)    # the door at the bridge's tip
        self.assertAlmostEqual(abs(x), 2.0 + pa.SPECS[c.kind][3] / 2.0 + pa.BRIDGE_SIDE_M, delta=0.6)   # beside it
        self.assertAlmostEqual(c.nn, -1.0, 2)


def footprint(c):
    """The sample points of an aircraft's rectangles in the plane."""
    x, y = en(c)
    return pa._world(pa._local_points(c.kind), x, y, c.ne, c.nn)


class Orientation(unittest.TestCase):
    def slanted(self, deg, tags=None):
        """The one aircraft at a gate just inside a terminal wall `deg` to the x axis, the wall's direction and normal."""
        a = math.radians(deg)
        rot = lambda x, y: (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))
        gx, gy = rot(0.0, -1.5)
        row = (point(gx, gy), "airport_gate", dict({"aeroway": "gate"}, **(tags or {})))
        f = feats(aerodrome("regional_airport"), row, occupied=True)
        got = pa.stands(f, buildings([rot(*p) for p in TERMINAL]))
        self.assertEqual(len(got), 1)
        return got[0], (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))

    def test_the_axis_is_perpendicular_to_the_wall_and_the_nose_at_it(self):
        for deg in (0.0, 33.0, 100.0, -57.0):
            c, w, nrm = self.slanted(deg)
            self.assertAlmostEqual(c.ne * w[0] + c.nn * w[1], 0.0, 2, deg)               # across the wall
            self.assertAlmostEqual(c.ne * nrm[0] + c.nn * nrm[1], -1.0, 2, deg)          # the nose toward it, the tail away
            x, y = en(c)
            half = pa.SPECS[c.kind][0] / 2.0
            self.assertGreater((x - c.ne * half) * nrm[0] + (y - c.nn * half) * nrm[1], 0.0)

    def test_a_corner_does_not_turn_the_aircraft_sideways(self):
        ring = np.array([(-200.0, -60.0), (60.0, -60.0), (60.0, -20.0), (0.0, -20.0), (0.0, 0.0), (-200.0, 0.0)])
        _q, smooth = pa._facade(ring, np.array([6.0, -12.0]))           # (the long edges outweigh a short wall in a notch)
        self.assertLess(abs(smooth[0]), 0.1)
        term = pa._terminal([(ring, (-200.0, -60.0, 60.0, 0.0))], 6.0, -12.0)
        self.assertGreater(term[1][0][1][0], 0.99)                      # the nearest wall's (x = 0) normal comes first

    def test_a_tagged_heading_is_preferred_where_it_points_at_the_wall(self):
        c, _w, _n = self.slanted(0.0, {"heading": "200"})
        b = math.radians(200.0)
        self.assertAlmostEqual(c.ne, math.sin(b), 2)
        self.assertAlmostEqual(c.nn, math.cos(b), 2)
        away, _w, _n = self.slanted(0.0, {"heading": "0"})              # (nose away from the wall: not used)
        self.assertAlmostEqual(away.nn, -1.0, 2)

    def test_remote_stand_lines_up_with_the_nearest_taxilane(self):
        lane = (line((-200, 60), (200, 60)), "taxilane", {})
        got = pa.stands(feats(aerodrome("regional_airport"), gate(0.0, 100.0), lane, occupied=True), None)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].mode, "remote")
        self.assertAlmostEqual(got[0].ne, 0.0, 2)                       # across the lane, the nose away from it
        self.assertAlmostEqual(got[0].nn, 1.0, 2)
        below = pa.stands(feats(aerodrome("regional_airport"), gate(0.0, 20.0), lane, occupied=True), None)
        self.assertAlmostEqual(below[0].nn, -1.0, 2)
        stub = (line((0, 40), (0, 70)), "taxilane", {})                 # (a lane ending at the stand: along it, on)
        c = pa.stands(feats(aerodrome("regional_airport"), gate(0.0, 90.0), stub, occupied=True), None)[0]
        self.assertAlmostEqual(c.nn, 1.0, 2)


class Buildings(unittest.TestCase):
    CANOPY = [(-12, 6), (12, 6), (12, 12), (-12, 12)]

    def gate_with(self, *blds, f=None):
        f = f or feats(aerodrome("regional_airport"), gate(0.0), occupied=True)
        return pa.stands(f, [buildings(TERMINAL)] + list(blds))

    def test_a_canopy_or_walkway_part_pulls_the_aircraft_back(self):
        base = self.gate_with()
        self.assertEqual(len(base), 1)
        for blds in ([parts(self.CANOPY)], [buildings(self.CANOPY, prefix="c")]):
            got = self.gate_with(*blds)
            self.assertEqual(len(got), 1)
            c = got[0]
            x, y = en(c)
            half = pa.SPECS[c.kind][0] / 2.0
            self.assertGreaterEqual(y - half, 12.0 + pa.BUILDING_CLEAR_M - 0.05)        # the nose clear of the canopy
            self.assertLessEqual(y, en(base[0])[1] + pa.PULL_BACK_MAX_M + 0.05)
            self.assertAlmostEqual(c.nn, -1.0, 2)                                       # the same axis, moved tail-ward
            self.assertAlmostEqual(x, en(base[0])[0], 1)

    def test_no_aircraft_overlaps_any_building_or_part(self):
        sheds = [[(-30, 20), (-26, 20), (-26, 24), (-30, 24)], [(25, 30), (28, 30), (28, 33), (25, 33)]]   # (under 300 m2)
        f = feats(aerodrome("regional_airport"), *[gate(x) for x in (-60.0, 0.0, 60.0)], occupied=True)
        got = pa.stands(f, [buildings(TERMINAL, *sheds), parts(self.CANOPY)])
        self.assertTrue(got)
        for c in got:
            pts = footprint(c)
            for r in sheds + [self.CANOPY]:
                r = np.array(r, np.float64)
                self.assertFalse(pa._pip(r, pts).any())
                self.assertGreater(pa._seg_dist(pts, r, np.roll(r, -1, axis=0)).min(), pa.BUILDING_CLEAR_M - 0.05)

    def test_too_deep_to_pull_back_drops_it(self):
        self.assertEqual(self.gate_with(parts([(-12, 6), (12, 6), (12, 40), (-12, 40)])), [])

    def test_the_gates_own_bridge_is_no_obstacle_but_a_neighbours_is(self):
        f = feats(aerodrome("regional_airport"), gate(0.0), occupied=True)
        bridge = [(-2, -3), (2, -3), (2, 30), (-2, 30)]
        self.assertEqual(len(pa.stands(f, [buildings(TERMINAL), parts(bridge)])), 1)
        f2 = feats(aerodrome("regional_airport"), gate(0.0), occupied=True)       # (a long walkway by the wing tips: a wall)
        self.assertEqual(pa.stands(f2, buildings(TERMINAL, [(14, -3), (18, -3), (18, 80), (14, 80)])), [])

    def test_a_small_shed_on_the_apron_is_kept_off(self):
        apron = [(-150, 100), (150, 100), (150, 200), (-150, 200)]
        f = feats(aerodrome("regional_airport"), (poly(apron), "apron", {}))
        free = pa.stands(f, None)
        sheds = []
        for c in free[::2]:
            x, y = en(c)
            sheds.append([(x - 1.5, y - 1.5), (x + 1.5, y - 1.5), (x + 1.5, y + 1.5), (x - 1.5, y + 1.5)])
        got = pa.stands(f, buildings(*sheds))
        self.assertLess(len(got), len(free))
        for c in got:
            for r in sheds:
                self.assertFalse(pa._pip(np.array(r), footprint(c)).any())

    def test_a_narrow_bridge_by_the_gate_is_no_obstacle_to_its_aircraft(self):
        f = feats(aerodrome("regional_airport"), gate(0.0), occupied=True)         # (the ids fix the type: the same one)
        base = self.gate_with(f=f)
        bridge = [(8, 20), (12, 20), (12, 32), (8, 32)]                    # (4 x 12 m, off the gate: by the wing)
        shed = [(8, 20), (16, 20), (16, 26), (8, 26)]                      # (8 x 6 m: a building)
        got = self.gate_with(buildings(bridge, prefix="n"), f=f)
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(en(got[0])[1], en(base[0])[1], 1)           # (where it stood without it)
        moved = self.gate_with(buildings(shed, prefix="s"), f=f)
        self.assertEqual(len(moved), 1)
        self.assertGreater(en(moved[0])[1], en(base[0])[1] + 1.0)          # (pulled back from the shed)
        far = [(8 + 60, 20), (12 + 60, 20), (12 + 60, 32), (8 + 60, 32)]
        sc = pa._scene(feats(aerodrome("regional_airport"), gate(0.0)))
        obstacles, _small = pa._buildings(sc, buildings(bridge, shed, far))
        self.assertEqual(sorted(obstacles.narrow), [0, 2])                 # (the shed is not narrow)

    def test_a_raised_part_is_no_obstacle_to_the_wings_but_to_the_fuselage(self):
        f = feats(aerodrome("regional_airport"), gate(0.0), occupied=True)
        base = self.gate_with(f=f)
        c = en(base[0])
        wing = [(8, c[1] - 3), (16, c[1] - 3), (16, c[1] + 3), (8, c[1] + 3)]          # over a wing, beside the fuselage
        body = [(-3, c[1] - 3), (3, c[1] - 3), (3, c[1] + 3), (-3, c[1] + 3)]          # over the fuselage

        def raised(ring, height):
            p = parts(ring)
            p.attrs["min_height"] = np.array([height])
            return p
        self.assertAlmostEqual(en(self.gate_with(raised(wing, 4.0), f=f)[0])[1], c[1], 1)
        self.assertGreater(en(self.gate_with(raised(wing, 0.0), f=f)[0])[1], c[1] + 1.0)
        got = self.gate_with(raised(body, 4.0), f=f)
        self.assertTrue(not got or en(got[0])[1] > c[1] + 1.0)             # (the fuselage still meets it)

    def test_kept_stands_is_what_tile_rows_places(self):
        f, _ = gates_row(4, 80.0, occupied=True)
        got = pa.kept_stands([0], lambda k: f, lambda k: [buildings(TERMINAL), None])
        self.assertEqual(len(got), 4)
        self.assertEqual(len(pa.tile_rows(FRAME, BOX, lambda k: f, lambda k: buildings(TERMINAL), ground, keys=[0])), 4)


class Types(unittest.TestCase):
    def kinds(self, cls, gap=9.0, n=40):
        f = feats(aerodrome(cls), *[gate(-190.0 + i * gap) for i in range(n)])
        return {c.kind for c in pa.stands(f, buildings(TERMINAL))}

    def test_by_aerodrome_class(self):
        intl = self.kinds("international_airport")
        self.assertIn("narrow", intl)                                           # (wide a quarter; a tight stand: smaller)
        self.assertLessEqual(intl, {"narrow", "wide", "turboprop"})
        self.assertEqual(self.kinds("regional_airport"), {"turboprop", "narrow"})
        self.assertEqual(self.kinds("private_airport"), {"light"})
        self.assertEqual(self.kinds("military_airport"), set())
        self.assertEqual(self.kinds("heliport"), set())

    def test_wide_a_quarter_by_hash_and_a_narrow_where_it_does_not_fit(self):
        found = set()
        for _ in range(6):
            f, _ = gates_row(4, 120.0)
            found |= {c.kind for c in pa.stands(f, buildings(TERMINAL))}
        self.assertLessEqual(found, {"narrow", "wide"})
        self.assertIn("wide", found)
        wide = [i for i in (f"{k:09d}" for k in range(2000)) if pa._kinds_for("intl", i)[0] == "wide"]
        self.assertAlmostEqual(len(wide) / 2000.0, 0.25, delta=0.04)
        tight = feats(aerodrome(), gate(0.0), occupied=True)
        tight.ids = np.array([tight.ids[0], wide[0]])                    # (a wide's gate: the terminal is 40 m deep)
        got = pa.stands(tight, buildings(TERMINAL, [(-45, 15), (45, 15), (45, 40), (-45, 40)]))
        self.assertTrue(all(c.kind != "wide" for c in got))


class Apron(unittest.TestCase):
    APRON = [(-150, 100), (150, 100), (150, 200), (-150, 200)]

    def test_light_aircraft_in_rows_on_a_non_international_apron(self):
        f = feats(aerodrome("regional_airport"), (poly(self.APRON), "apron", {}))
        got = pa.stands(f, None)
        self.assertTrue(0 < len(got) <= pa.GA_MAX)
        self.assertEqual({c.kind for c in got}, {"light"})
        for c in got:
            x, y = en(c)
            self.assertTrue(-150 < x < 150 and 100 < y < 200)
            d = min(abs(x - 150), abs(x + 150), abs(y - 100), abs(y - 200))
            self.assertAlmostEqual(d, pa.SPECS["light"][0] / 2.0 + pa.GA_INSET_M, delta=0.6)    # the nose to the edge
        for i, a in enumerate(got):
            for b in got[i + 1:]:
                self.assertGreater(math.hypot(en(a)[0] - en(b)[0], en(a)[1] - en(b)[1]), 7.0)

    def test_international_apron_has_none_unless_tagged_general_aviation(self):
        plain = feats(aerodrome(), (poly(self.APRON), "apron", {}, "Domestic Apron"))
        self.assertEqual(pa.stands(plain, None), [])
        ga = feats(aerodrome(), (poly(self.APRON), "apron", {}, "General Aviation Apron"))
        self.assertTrue(0 < len(pa.stands(ga, None)) <= pa.GA_MAX)

    def test_a_gates_aircraft_stands_on_the_paving(self):
        def run(apron):
            f = feats(aerodrome("regional_airport"), (poly(apron), "apron", {}), gate(0.0), occupied=True)
            return [c for c in pa.stands(f, buildings(TERMINAL)) if c.mode == "gate"]
        free = pa.stands(feats(aerodrome("regional_airport"), gate(0.0), occupied=True), buildings(TERMINAL))
        self.assertEqual(len(free), 1)                                  # (a cell that maps no apron: not asked)
        self.assertEqual(len(run([(-60, 0), (60, 0), (60, 80), (-60, 80)])), 1)         # (the whole stand on it)
        self.assertEqual(run([(-60, 0), (60, 0), (60, 14), (-60, 14)]), [])             # (the main gear on the grass)
        self.assertEqual(run([(-60, 40), (60, 40), (60, 90), (-60, 90)]), [])           # (the nose gear on the grass)

    def test_a_hangar_on_the_apron_is_kept_off(self):
        hangar = [(-150, 100), (-60, 100), (-60, 140), (-150, 140)]
        f = feats(aerodrome("regional_airport"), (poly(self.APRON), "apron", {}))
        free = pa.stands(f, None)
        got = pa.stands(f, buildings(hangar))
        self.assertLess(len(got), len(free))
        for c in got:
            x, y = en(c)
            self.assertFalse(-155 < x < -55 and 95 < y < 145)


class Rows(unittest.TestCase):
    def rows(self, f, bld, box=BOX):
        return pa.tile_rows(FRAME, box, lambda k: f, lambda k: bld, ground, keys=[0])

    def test_none_without_airport_features(self):
        other = mapgeom.build("infrastructure", np.array(["a", "b"]), [point(0, 0), line((0, 0), (10, 0))])
        other.attrs = {"class": mapgeom.text_column(["bench", "fence"]),
                       "subtype": mapgeom.text_column(["pedestrian", "barrier"])}
        self.assertEqual(self.rows(other, buildings(TERMINAL)), [])
        self.assertEqual(self.rows(None, None), [])
        self.assertFalse(pa.has_stands(other))

    def test_row_format_yaw_and_ground(self):
        f, _ = gates_row(5)
        rows = self.rows(f, buildings(TERMINAL))
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertIn(r[0], pa.GROUPS.values())
            kind = {v: k for k, v in pa.GROUPS.items()}[r[0]]
            self.assertEqual((r[5], r[6], r[7]), (1.0, pa.SPECS[kind][2], 0.0))
            a = math.radians(r[4] + 90.0)                               # the shape's +Y, pointing at the terminal (-y)
            self.assertAlmostEqual(math.cos(a), 0.0, 1)
            self.assertAlmostEqual(math.sin(a), -1.0, 1)
            self.assertAlmostEqual(r[3], 5.0, 1)

    def test_each_aircraft_is_in_one_tile(self):
        f, _ = gates_row(6, 70.0, occupied=True)
        bld = buildings(TERMINAL)
        whole = self.rows(f, bld)
        self.assertEqual(len(whole), 6)
        cut = sorted(r[1] for r in whole)[3] - 0.3
        west = self.rows(f, bld, (BOX[0], BOX[1], cut, BOX[3]))
        east = self.rows(f, bld, (cut, BOX[1], BOX[2], BOX[3]))
        self.assertEqual(sorted(map(tuple, west + east)), sorted(map(tuple, whole)))
        self.assertTrue(west and east)


if __name__ == "__main__":
    unittest.main()
