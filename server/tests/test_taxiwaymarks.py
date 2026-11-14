"""taxiwaymarks: the yellow centreline along the paved taxiways and the runway holding position marking where one
meets a runway. The centreline follows the mapped line and stops short of a runway; a taxiway entering a runway has
ICAO pattern A across its width on the taxiway side (a mapped holding_position point moves it); Features of anywhere
else and unpaved ways draw nothing; the tile's chunks are the strokes, each in exactly one tile."""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import aeroways  # noqa: E402
import airportgrade  # noqa: E402
import geodesy  # noqa: E402
import mapgeom  # noqa: E402
import parkedaircraft as pa  # noqa: E402
import taxiwaymarks as tm  # noqa: E402

FRAME = geodesy.EnuFrame(-27.39, 153.118)
RUNWAY_W = 45.0
HALF = RUNWAY_W / 2


def lonlat(e, n):
    la, lo, _ = FRAME.enu_to_geodetic(np.asarray(e, np.float64), np.asarray(n, np.float64), 0.0)
    return np.stack([lo, la], 1)


def line(*pts):
    return (mapgeom.LINE, [[lonlat([p[0] for p in pts], [p[1] for p in pts])]])


_IDS = iter(range(10 ** 6))


def feats(*rows):
    """Infrastructure Features of (geometry, class, subtype, tags dict, surface) rows (ids unique over the tests: two
    cells' Features share an id only for one feature)."""
    ids = np.array([f"f{next(_IDS):06d}" for _ in rows])
    f = mapgeom.build("infrastructure", ids, [r[0] for r in rows])
    f.attrs = {"class": mapgeom.text_column([r[1] for r in rows]),
               "subtype": mapgeom.text_column([r[2] for r in rows]),
               "tags": mapgeom.text_column([json.dumps(r[3]) for r in rows]),
               "surface": mapgeom.text_column([r[4] for r in rows])}
    return f


def runway(*pts):
    return (line(*pts), "runway", "airport", {"width": str(RUNWAY_W)}, None)


def taxiway(*pts, tags=None, surface=None, cls="taxiway"):
    return (line(*pts), cls, "airport", tags or {}, surface)


def hold_point(e, n):
    return ((mapgeom.POINT, [[lonlat([e], [n])]]), "holding_position", "airport", {"aeroway": "holding_position"}, None)


def metres(stroke):
    """A stroke's (x0, y0, x1, y1) east / north of the frame's origin."""
    e, n, _ = FRAME.geodetic_to_enu(np.array([stroke[0], stroke[2]]), np.array([stroke[1], stroke[3]]), np.zeros(2))
    return float(e[0]), float(n[0]), float(e[1]), float(n[1])


def of(got, kind):
    return [s for s in got if s[5] == kind]


class Centreline(unittest.TestCase):
    def test_follows_the_mapped_line_in_yellow(self):
        got = tm.strokes([feats(runway((-1000, 0), (1000, 0)), taxiway((0, 100), (0, 400), (200, 400)))])
        centre = of(got, tm.CENTRE_KIND)
        self.assertEqual(len(centre), 2, "one stroke a segment of the line")
        for s in centre:
            self.assertEqual((s[4], s[5], s[6]), (tm.CENTRE_W_M, tm.CENTRE_KIND, "yellow"))
        want = [(0, 100, 0, 400), (0, 400, 200, 400)]
        for s, w in zip(sorted(centre, key=lambda s: metres(s)[2]), want):
            np.testing.assert_allclose(metres(s), w, atol=0.05)

    def test_taxilane_has_one_too(self):
        got = tm.strokes([feats(taxiway((0, 0), (80, 0), cls="taxilane"))])
        self.assertEqual(len(of(got, tm.CENTRE_KIND)), 1)

    def test_nothing_painted_inside_a_runways_width(self):
        # a taxiway ending on the runway's centreline and one crossing it
        got = tm.strokes([feats(runway((-1000, 0), (1000, 0)), taxiway((0, 300), (0, 0)),
                                taxiway((300, -300), (300, 300)))])
        centre = of(got, tm.CENTRE_KIND)
        self.assertTrue(centre)
        near = [abs(v) for s in centre for v in metres(s)[1::2]]
        self.assertGreaterEqual(min(near), HALF + tm.RUNWAY_GAP_M - 0.2, "the line stops short of the runway's edge")
        self.assertLess(min(near), HALF + tm.RUNWAY_GAP_M + 0.5, "... and only just")
        crossing = [metres(s) for s in centre if abs(metres(s)[0] - 300) < 0.1]
        self.assertTrue(any(min(m[1], m[3]) > 0 for m in crossing))
        self.assertTrue(any(max(m[1], m[3]) < 0 for m in crossing), "both sides of the crossing")

    def test_unpaved_and_other_features_draw_nothing(self):
        self.assertEqual(tm.strokes([feats(taxiway((0, 0), (100, 0), surface="grass"))]), [])
        self.assertEqual(tm.strokes([feats(taxiway((0, 0), (100, 0), tags={"surface": "dirt"}))]), [])
        self.assertEqual(tm.strokes([feats((line((0, 0), (100, 0)), "taxiway", "transit", {}, None))]), [])
        self.assertEqual(tm.strokes([feats((line((0, 0), (100, 0)), "footway", "airport", {}, None))]), [])
        self.assertEqual(tm.strokes([None]), [])
        self.assertEqual(tm.strokes([]), [])
        self.assertEqual(tm.tile_chunks([feats((line((0, 0), (100, 0)), "taxiway", "transit", {}, None))], FRAME, 0, 0,
                                        lambda la, lo: np.zeros(len(la)), lambda tx, ty: (0, 0, 256, 256)), [])

    def test_the_same_feature_in_two_cells_is_painted_once(self):
        a = feats(runway((-1000, 0), (1000, 0)), taxiway((0, 300), (0, 0)))
        b = feats(runway((-1000, 0), (1000, 0)), taxiway((0, 300), (0, 0)))
        b.ids = a.ids.copy()
        self.assertEqual(len(tm.strokes([a, b])), len(tm.strokes([a])))

    def test_a_runway_in_another_cell_still_cuts_it(self):
        taxi, rw = feats(taxiway((0, 300), (0, 0))), feats(runway((-1000, 0), (1000, 0)))
        alone = min(abs(v) for s in of(tm.strokes([taxi]), tm.CENTRE_KIND) for v in metres(s)[1::2])
        both = min(abs(v) for s in of(tm.strokes([taxi, rw]), tm.CENTRE_KIND) for v in metres(s)[1::2])
        self.assertLess(alone, 1.0)
        self.assertGreater(both, HALF)


class Holds(unittest.TestCase):
    def marking(self, rows):
        got = tm.strokes([feats(*rows)])
        return [s for s in got if s[5] in ("hold_solid", "hold_dashed")]

    def test_taxiway_entering_a_runway_has_pattern_a_across_its_width(self):
        hold = self.marking([runway((-1000, 0), (1000, 0)), taxiway((0, 300), (0, 0))])
        solid, dashed = of(hold, "hold_solid"), of(hold, "hold_dashed")
        self.assertEqual(len(solid), 2)
        self.assertGreaterEqual(len(dashed), 2 * 4)
        for s in hold:
            self.assertEqual((s[4], s[6]), (tm.HOLD_LINE_W_M, "yellow"))
        w = aeroways.TAXIWAY_M
        for s in solid:                                     # across the way's whole width
            x0, y0, x1, y1 = metres(s)
            self.assertAlmostEqual(abs(y1 - y0), 0.0, places=2)
            self.assertAlmostEqual(abs(x1 - x0), w, delta=0.05)
            self.assertAlmostEqual((x0 + x1) / 2, 0.0, delta=0.05)
        for s in dashed:
            x0, _, x1, _ = metres(s)
            self.assertLessEqual(max(abs(x0), abs(x1)), w / 2 + 0.05)

        def ys(ss):
            return [metres(s)[1] for s in ss]
        self.assertAlmostEqual(min(ys(dashed)), tm.HOLD_DIST_M, delta=0.1, msg="the nearest line is HOLD_DIST_M out")
        self.assertGreater(min(ys(solid)), max(ys(dashed)), "the solid lines are on the taxiway side")
        self.assertEqual(len(set(round(y, 2) for y in ys(dashed))), 2)
        self.assertEqual(len(set(round(y, 2) for y in ys(solid))), 2)

    def test_a_taxiway_across_a_runway_has_one_each_side(self):
        hold = self.marking([runway((-1000, 0), (1000, 0)), taxiway((0, -300), (0, 300))])
        solid = of(hold, "hold_solid")
        self.assertEqual(len(solid), 4)
        up = [s for s in solid if metres(s)[1] > 0]
        down = [s for s in solid if metres(s)[1] < 0]
        self.assertEqual((len(up), len(down)), (2, 2))
        dashed = of(hold, "hold_dashed")
        self.assertAlmostEqual(min(abs(metres(s)[1]) for s in dashed), tm.HOLD_DIST_M, delta=0.1)
        self.assertLess(max(metres(s)[1] for s in down), -tm.HOLD_DIST_M, "the solid lines are further out, below too")

    def test_the_width_tag_sets_the_length(self):
        hold = self.marking([runway((-1000, 0), (1000, 0)), taxiway((0, 300), (0, 0), tags={"width": "30"})])
        for s in of(hold, "hold_solid"):
            x0, _, x1, _ = metres(s)
            self.assertAlmostEqual(abs(x1 - x0), 30.0, delta=0.05)

    def test_a_mapped_holding_position_is_used(self):
        hold = self.marking([runway((-1000, 0), (1000, 0)), taxiway((0, 300), (0, 0)), hold_point(1.0, 85.0)])
        self.assertAlmostEqual(min(metres(s)[1] for s in of(hold, "hold_dashed")), 85.0, delta=0.1)
        far = self.marking([runway((-1000, 0), (1000, 0)), taxiway((0, 300), (0, 0)), hold_point(40.0, 85.0)])
        self.assertAlmostEqual(min(metres(s)[1] for s in of(far, "hold_dashed")), tm.HOLD_DIST_M, delta=0.1,
                               msg="a point off the taxiway is not its holding position")

    def test_none_without_a_runway_or_off_one(self):
        self.assertEqual(self.marking([taxiway((0, 300), (0, 0))]), [])
        self.assertEqual(self.marking([runway((-1000, 0), (1000, 0)), taxiway((0, 300), (0, 100))]), [], "ends short of it")
        self.assertEqual(self.marking([runway((-1000, 0), (1000, 0)), taxiway((0, 40), (0, 0))]), [],
                         "no room for it before the way ends")
        self.assertEqual(self.marking([runway((-1000, 0), (1000, 0)), taxiway((0, 300), (0, 0), surface="gravel")]), [])

    def test_a_non_airport_feature_set_draws_nothing(self):
        rows = [(line((-1000, 0), (1000, 0)), "runway", "transit", {}, None),
                (line((0, 300), (0, 0)), "taxiway", "transit", {}, None)]
        self.assertEqual(tm.strokes([feats(*rows)]), [])


class TileChunks(unittest.TestCase):
    SIDE = 256.0

    def bbox(self, tx, ty):
        return (tx * self.SIDE, ty * self.SIDE, (tx + 1) * self.SIDE, (ty + 1) * self.SIDE)

    def chunks(self, f, tx, ty):
        return tm.tile_chunks([f], FRAME, tx, ty, lambda la, lo: np.full(len(la), 7.0), self.bbox)

    def test_chunks_are_yellow_decals_each_in_one_tile(self):
        f = feats(runway((-600, 0), (600, 0)), taxiway((50, 600), (50, 0), (300, 0)))
        per = {(tx, ty): self.chunks(f, tx, ty) for tx in range(-4, 4) for ty in range(-4, 4)}
        allc = [c for v in per.values() for c in v]
        self.assertTrue(allc)
        look = airportgrade.MARK_LOOK["yellow"]
        for c in allc:
            self.assertEqual((c["m"], c["tl"], c["p"]), (look["m"], look["tl"], look["p"]))
            self.assertIn(c["w"], (round(tm.CENTRE_W_M, 2), round(tm.HOLD_LINE_W_M, 2)))
            self.assertGreaterEqual(len(c["n"]), 2)
            self.assertAlmostEqual(c["n"][0][2], 7.0, places=1)
        # the pieces tile the strokes: the length painted is the strokes' whole length, once
        want = sum(float(np.hypot(metres(s)[2] - metres(s)[0], metres(s)[3] - metres(s)[1])) for s in tm.strokes([f]))
        got = sum(float(np.hypot(*np.diff(np.array(c["n"])[:, :2], axis=0).T).sum()) for c in allc)
        self.assertAlmostEqual(got, want, delta=want * 0.01)

    def test_pieces_are_short_and_far_tiles_empty(self):
        f = feats(taxiway((0, 100), (900, 100)))
        v = sum((self.chunks(f, tx, 0) for tx in range(4)), [])
        self.assertGreater(len(v), 3)
        for c in v:
            p = np.array(c["n"])
            self.assertLessEqual(float(np.hypot(*np.diff(p[:, :2], axis=0).T).sum()), airportgrade.MARK_PIECE_M + 1e-6)
        self.assertEqual(self.chunks(f, 0, 40), [])

    def border_points(self, f, stands=None, tx=0, edge=SIDE):
        """(the nodes of tile (tx, 0)'s chunks, the nodes of tile (tx + 1, 0)'s) lying on their shared edge x = edge."""
        run = lambda t: [c for c in tm.tile_chunks([f], FRAME, t, 0, lambda la, lo: np.full(len(la), 7.0), self.bbox, stands)]
        a, b = run(tx), run(tx + 1)
        for chunks, box in ((a, self.bbox(tx, 0)), (b, self.bbox(tx + 1, 0))):         # (nothing outside its own tile)
            for c in chunks:
                for x, y, _z in c["n"]:
                    self.assertTrue(box[0] - 1e-3 <= x <= box[2] + 1e-3 and box[1] - 1e-3 <= y <= box[3] + 1e-3, (x, y))
        on = lambda chunks: sorted((round(x, 2), round(y, 2)) for c in chunks for x, y, _z in c["n"] if abs(x - edge) < 1e-3)
        return on(a), on(b), a, b

    def test_a_line_across_two_tiles_is_painted_in_both_and_the_pieces_join(self):
        f = feats(taxiway((150, 100), (400, 100)))                  # across the edge x = 256
        left, right, a, b = self.border_points(f)
        self.assertTrue(a and b)
        self.assertEqual(left, right)
        self.assertEqual(left, [(256.0, 100.0)])                    # (the two pieces end and begin at the same point)
        length = lambda cs: sum(float(np.hypot(*np.diff(np.array(c["n"])[:, :2], axis=0).T).sum()) for c in cs)
        self.assertAlmostEqual(length(a), 256.0 - 150.0, delta=0.01)
        self.assertAlmostEqual(length(b), 400.0 - 256.0, delta=0.01)

    def test_a_line_that_leaves_a_tile_and_comes_back_is_painted_in_its_parts(self):
        f = feats(taxiway((150, 100), (300, 100), (300, 130), (150, 130)))      # out across x = 256 and back
        left, right, a, b = self.border_points(f)
        self.assertEqual(left, right)
        self.assertEqual(left, [(256.0, 100.0), (256.0, 130.0)])
        length = lambda cs: sum(float(np.hypot(*np.diff(np.array(c["n"])[:, :2], axis=0).T).sum()) for c in cs)
        self.assertAlmostEqual(length(a), 2 * (256.0 - 150.0), delta=0.01)      # (both parts in the first tile)
        self.assertAlmostEqual(length(b), 2 * (300.0 - 256.0) + 30.0, delta=0.01)       # (the bend, one part, in the next)

    def test_a_bend_on_the_edge_and_a_line_along_it_are_not_lost(self):
        f = feats(taxiway((256, 20), (256, 200)))                   # along the edge: painted (by both, at worst)
        _l, _r, a, b = self.border_points(f)
        self.assertTrue(a or b)

    def test_bends_are_one_polyline(self):
        f = feats(taxiway((10, 10), (10, 30), (30, 30)))
        v = self.chunks(f, 0, 0)
        self.assertEqual(len(v), 1)
        pts = np.array(v[0]["n"])[:, :2]
        self.assertTrue(np.any(np.hypot(*(pts - [10, 30]).T) < 0.1), "it passes the mapped vertex")


def craft(kind, x, y, ne, nn, mode="gate"):
    """A parked aircraft (parkedaircraft.Craft) centred at (x, y) east / north of the frame's origin."""
    la, lo, _ = FRAME.enu_to_geodetic(np.array([x], np.float64), np.array([y], np.float64), 0.0)
    return pa.Craft(kind, float(la[0]), float(lo[0]), ne, nn, mode)


class LeadIns(unittest.TestCase):
    """A stand's yellow lead-in: from the taxilane its axis meets, an arc into a straight run along the axis to the nose,
    and a stop bar across it at the nose."""
    LANE = taxiway((-120, 0), (100, 0), cls="taxilane")             # (more lane behind the axis than before it)
    NARROW = pa.SPECS["narrow"]

    def painted(self, f, *stands):
        base = tm.strokes([f])
        got = tm.strokes([f], list(stands))
        self.assertEqual(got[:len(base)], base)                         # (the mapped lines unchanged)
        got = [s for s in got[len(base):] if s[5] == tm.CENTRE_KIND]    # (the lead-in and the stop bar, not the stand details)
        return [metres(s) for s in got], got

    def test_lane_arc_straight_run_to_the_nose_and_a_stop_bar(self):
        f = feats(self.LANE)
        L, span = self.NARROW[0], self.NARROW[1]
        segs, raw = self.painted(f, craft("narrow", 0.0, 40.0, 0.0, 1.0))                # nose 40 + L/2 north, tail to the lane
        nose = 40.0 + L / 2.0
        for s in raw:
            self.assertEqual((s[4], s[5], s[6]), (tm.CENTRE_W_M, tm.CENTRE_KIND, "yellow"))      # the centreline's paint
        bar, line = segs[-1], segs[:-1]
        self.assertAlmostEqual(line[0][1], 0.0, 1)                                           # it starts on the lane ...
        self.assertAlmostEqual(line[0][0], -tm.LEAD_RADIUS_K * span, delta=0.5)              # ... a radius before the axis
        self.assertAlmostEqual(line[-1][2], 0.0, 2)
        self.assertAlmostEqual(line[-1][3], nose, 2)                                         # ... and ends at the nose
        for a, b in zip(line, line[1:]):                                                     # one connected polyline
            self.assertAlmostEqual(a[2], b[0], 2)
            self.assertAlmostEqual(a[3], b[1], 2)
        d0 = np.array([line[0][2] - line[0][0], line[0][3] - line[0][1]])
        self.assertGreater(d0[0] / np.hypot(*d0), 0.97)                                      # leaves along the lane (tangent)
        straight = [s for s in line if s[1] > tm.LEAD_RADIUS_K * span - 0.1]
        self.assertTrue(straight)
        for s in straight:
            self.assertAlmostEqual(s[0], 0.0, 2)                                             # the run is on the axis
            self.assertAlmostEqual(s[2], 0.0, 2)
        self.assertAlmostEqual(bar[1], nose, 2)                                              # the bar across the axis at the nose
        self.assertAlmostEqual(bar[3], nose, 2)
        self.assertAlmostEqual(abs(bar[2] - bar[0]), tm.STOP_BAR_M, 2)
        self.assertAlmostEqual(bar[0] + bar[2], 0.0, 2)

    def test_a_curve_not_a_corner_between_lane_and_axis(self):
        segs, _ = self.painted(feats(self.LANE), craft("turboprop", 30.0, 40.0, 0.0, 1.0))
        line = segs[:-1]
        turn = []
        for a, b in zip(line, line[1:]):
            da = np.array([a[2] - a[0], a[3] - a[1]])
            db = np.array([b[2] - b[0], b[3] - b[1]])
            turn.append(float(np.degrees(np.arccos(np.clip(da @ db / np.hypot(*da) / np.hypot(*db), -1, 1)))))
        self.assertLess(max(turn), 25.0)                                # (no vertex turns sharply: a 90 degree turn in steps)
        self.assertAlmostEqual(sum(turn), 90.0, delta=4.0)              # (a quarter turn in all, less the chords' ends)

    def test_a_lane_that_ends_short_is_carried_on(self):
        f = feats(taxiway((-120, 0), (-30, 0), cls="taxilane"))
        segs, _ = self.painted(f, craft("narrow", 0.0, 20.0, 0.0, 1.0))
        self.assertAlmostEqual(segs[0][0], -30.0, 1)                    # from the lane's end ...
        self.assertAlmostEqual(segs[0][1], 0.0, 1)
        self.assertAlmostEqual(segs[0][2], -tm.LEAD_RADIUS_K * self.NARROW[1], delta=0.5)   # ... straight on to where the curve starts
        self.assertAlmostEqual(segs[0][3], 0.0, 1)

    def test_a_stand_on_the_far_side_is_reached_from_its_own_side(self):
        segs, _ = self.painted(feats(self.LANE), craft("narrow", 0.0, -40.0, 0.0, -1.0))
        self.assertAlmostEqual(segs[0][1], 0.0, 1)
        self.assertAlmostEqual(segs[-2][3], -40.0 - self.NARROW[0] / 2.0, 2)

    def test_no_lead_in_for_a_ga_row_and_a_straight_stub_for_a_stand_without_a_lane(self):
        f = feats(self.LANE)
        self.assertEqual(self.painted(f, craft("light", 0.0, 30.0, 0.0, 1.0, "ga"))[0], [])
        segs = self.painted(f, craft("narrow", 600.0, 900.0, 0.0, 1.0))[0]                         # (a lane 1 km off)
        self.assertEqual(len(segs), 2)                                  # the stub along the axis and the bar
        nose = 900.0 + self.NARROW[0] / 2.0
        self.assertAlmostEqual(segs[0][3], nose, 2)
        self.assertAlmostEqual(segs[0][3] - segs[0][1], self.NARROW[0] + tm.LEAD_STUB_M, 2)
        self.assertAlmostEqual(segs[0][0], 600.0, 2)

    def test_a_lane_ending_at_the_nose_along_the_axis_is_carried_on_to_it(self):
        f = feats(taxiway((0, 0), (0, 40), cls="taxilane"))
        segs, _ = self.painted(f, craft("narrow", 0.0, 60.0, 0.0, 1.0))      # nose at 78.8: the lane's end 38.8 short of it
        self.assertEqual(len(segs), 2)                                  # a straight line and the bar
        self.assertAlmostEqual(segs[0][1], 40.0, 1)
        self.assertAlmostEqual(segs[0][3], 60.0 + self.NARROW[0] / 2.0, 2)

    @staticmethod
    def length(segs):
        return sum(float(np.hypot(s[2] - s[0], s[3] - s[1])) for s in segs)

    def test_no_lead_in_longer_than_the_aircraft_plus_the_cap(self):
        f = feats(self.LANE)
        cap = self.NARROW[0] + tm.LEAD_OVER_M
        near = self.painted(f, craft("narrow", 0.0, 40.0, 0.0, 1.0))[0]
        self.assertTrue(near)
        self.assertLessEqual(self.length(near[:-1]), cap)
        self.assertGreater(len(near), 2)                                                    # (a lane's line: a curve and a run)
        far = self.painted(f, craft("narrow", 0.0, 75.0, 0.0, 1.0))[0]                     # (nose 93.8 m on: past it: the stub)
        self.assertEqual(len(far), 2)
        self.assertAlmostEqual(far[0][3] - far[0][1], self.NARROW[0] + tm.LEAD_STUB_M, 2)

    def test_a_lane_across_a_taxiways_pad_is_the_last_resort_and_a_runways_is_never_crossed(self):
        stand = craft("narrow", 0.0, 40.0, 0.0, 1.0)
        lane = taxiway((-120, 0), (100, 0), cls="taxilane")
        across = feats(lane, taxiway((-4, 20), (-4, 45)))                   # a taxiway's pad (15 m wide) under the run
        got = self.painted(across, stand)[0]
        self.assertAlmostEqual(got[0][1], 0.0, 1)                           # (no other lane: the lane's line, across the pad)
        beside = feats(self.LANE, taxiway((-40, 20), (-40, 45)))
        self.assertAlmostEqual(self.painted(beside, stand)[0][0][1], 0.0, 1)
        stub = self.painted(feats(self.LANE, runway((-100, 40), (100, 40))), stand)[0]        # (a runway's is not to be crossed)
        self.assertEqual(len(stub), 2)
        self.assertAlmostEqual(stub[0][3] - stub[0][1], self.NARROW[0] + tm.LEAD_STUB_M, 2)   # (the stub, not a lane's line)

    def test_the_lane_it_leaves_may_be_a_taxiway_and_another_lane_is_tried_when_the_nearest_crosses_a_pad(self):
        stand = craft("narrow", 0.0, 40.0, 0.0, 1.0)
        own = feats(taxiway((-120, 0), (100, 0)))                           # a taxiway: its own lane
        segs = self.painted(own, stand)[0]
        self.assertAlmostEqual(segs[0][1], 0.0, 1)
        both = feats(self.LANE, taxiway((-120, 30), (100, 30)))             # the taxiway nearer: it is the lane it leaves
        self.assertAlmostEqual(self.painted(both, stand)[0][0][1], 30.0, 1)

    def test_a_stand_listed_twice_or_overlapped_paints_one_lead_in(self):
        f = feats(self.LANE)
        one = craft("narrow", 0.0, 60.0, 0.0, 1.0)
        twin = craft("narrow", 0.0, 60.0, 0.0, 1.0)
        got = tm.strokes([f], [one])
        self.assertEqual(tm.strokes([f], [one, twin]), got)
        self.assertEqual(tm.strokes([f], [one, craft("light", 0.0, 62.0, 0.0, 1.0)]), got)    # (a shorter kind on top: not kept)
        self.assertEqual(tm.strokes([f], [one, craft("light", 0.0, 62.0, 0.0, 1.0, "ga")]), got)

    def test_a_lead_in_and_its_stop_bar_across_two_tiles_are_painted_by_both_and_join(self):
        lane = taxiway((100, 0), (420, 0), cls="taxilane")
        f = feats(lane)
        st = [craft("narrow", 255.0, 40.0, 0.0, 1.0)]               # its stop bar and the lane's run cross x = 256
        tc = TileChunks()
        run = lambda t: tm.tile_chunks([f], FRAME, t, 0, lambda la, lo: np.full(len(la), 7.0), tc.bbox, st)
        base = lambda t: tm.tile_chunks([f], FRAME, t, 0, lambda la, lo: np.full(len(la), 7.0), tc.bbox)
        for t in (0, 1):
            self.assertGreater(len(run(t)), len(base(t)))           # (the lead-in is in both tiles)
        on = lambda cs: sorted((round(x, 2), round(y, 2)) for c in cs for x, y, _z in c["n"] if abs(x - tc.SIDE) < 1e-3)
        want = on(run(0))
        self.assertTrue(want)
        self.assertEqual(want, on(run(1)))                          # (every piece's end on the edge has its partner)
        self.assertGreater(len(want), len(on(base(0))))             # (more than the lane's: the stop bar's)

    def test_chunks_paint_a_listed_twice_stand_once_across_tiles(self):
        f = feats(self.LANE)
        tc = TileChunks()
        run = lambda stands: [c for tx in range(-2, 2) for ty in range(-2, 2) for c in
                              tm.tile_chunks([f], FRAME, tx, ty, lambda la, lo: np.full(len(la), 7.0), tc.bbox, stands)]
        length = lambda cs: sum(float(np.hypot(*np.diff(np.array(c["n"])[:, :2], axis=0).T).sum()) for c in cs)
        st = craft("narrow", 0.0, 40.0, 0.0, 1.0)
        self.assertAlmostEqual(length(run([st, st])), length(run([st])), places=3)

    def test_chunks_carry_the_lead_in_each_in_one_tile(self):
        f = feats(self.LANE)
        st = [craft("narrow", 0.0, 40.0, 0.0, 1.0)]
        tc = TileChunks()
        run = lambda stands: [c for tx in range(-2, 2) for ty in range(-2, 2) for c in
                              tm.tile_chunks([f], FRAME, tx, ty, lambda la, lo: np.full(len(la), 7.0), tc.bbox, stands)]
        plain, with_lead = run(None), run(st)
        length = lambda cs: sum(float(np.hypot(*np.diff(np.array(c["n"])[:, :2], axis=0).T).sum()) for c in cs)
        want = sum(float(np.hypot(m[2] - m[0], m[3] - m[1])) for m in self.painted(f, *st)[0])
        want += 2 * tm.WING_LINE_LEN_M                                  # (and the wing-tip clearance lines)
        self.assertAlmostEqual(length(with_lead) - length(plain), want, delta=want * 0.02)

    def test_wing_tip_lines_and_a_stand_number(self):
        f = feats(self.LANE)
        L, span = self.NARROW[0], self.NARROW[1]
        nose = 60.0 + L / 2.0
        c = craft("narrow", 0.0, 60.0, 0.0, 1.0)
        base = tm.strokes([f], [c])
        got = [s for s in base if s[5] == tm.STAND_KIND]
        self.assertEqual(len(got), 2, "no ref: the wing-tip lines only")
        for s in got:
            x0, y0, x1, y1 = metres(s)
            self.assertAlmostEqual(abs(x0), span / 2.0 + tm.WING_LINE_OFF_M, 1)
            self.assertAlmostEqual(x0, x1, 2)                                   # parallel to the axis ...
            self.assertAlmostEqual(y1 - y0, tm.WING_LINE_LEN_M, 2)              # ... 20 m long, ending level with the bar
            self.assertAlmostEqual(y1, nose, 2)
        numbered = tm.strokes([f], [c._replace(ref="12")])
        digits = [s for s in numbered if s[5] == tm.STAND_KIND and s[4] == tm.NUM_W_M]
        self.assertGreater(len(digits), 2)
        pts = np.array([p for s in digits for p in (metres(s)[:2], metres(s)[2:])])
        self.assertGreaterEqual(pts[:, 1].min(), nose + tm.NUM_AFTER_M - 0.01)      # past the stop bar ...
        self.assertAlmostEqual(pts[:, 1].max(), nose + tm.NUM_AFTER_M + tm.NUM_H_M, 2)
        half = (2 * tm.NUM_H_M * tm.NUM_W_K + tm.NUM_H_M * tm.NUM_GAP_K) / 2.0
        self.assertLessEqual(pts[:, 0].max(), half + 0.01)                          # ... in a box centred on the axis
        self.assertGreaterEqual(pts[:, 0].min(), -half - 0.01)
        self.assertAlmostEqual(pts[:, 0].max(), half, 2)                            # (the 2's right edge)
        self.assertEqual(len([s for s in tm.strokes([f], [c._replace(ref="12@")]) if s[5] == tm.STAND_KIND]), 2)  # (no font: none)

    def test_an_empty_valid_stand_gets_a_lead_in(self):
        import test_parkedaircraft as tpa
        f = tpa.feats(tpa.aerodrome(), tpa.gate(0.0), (tpa.line((-200, 60), (200, 60)), "taxilane", {}), occupied=False)
        bld = tpa.buildings(tpa.TERMINAL)
        self.assertEqual(pa.stands(f, bld), [])                         # (the occupancy hash leaves it empty: no aircraft)
        got = pa.lead_stands([0], lambda k: f, lambda k: bld)
        self.assertEqual([c.mode for c in got], ["gate"])               # ... but the stand is valid
        c = got[0]
        e, n, _ = FRAME.geodetic_to_enu(np.array([c.lat]), np.array([c.lon]), 0.0)
        nose = np.array([float(e[0]), float(n[0])]) + np.array([c.ne, c.nn]) * pa.SPECS[c.kind][0] / 2.0
        base = tm.strokes([f])
        lead = [metres(s) for s in tm.strokes([f], got)[len(base):] if s[5] == tm.CENTRE_KIND]
        self.assertGreater(len(lead), 3)                                # (a curve, a run and the stop bar)
        self.assertTrue(any(np.hypot(m[2] - nose[0], m[3] - nose[1]) < 0.1 for m in lead), "the line reaches the nose")
        self.assertTrue(any(abs(m[1] - 60.0) < 0.1 for m in lead), "... from the lane")


class LeadSpine(unittest.TestCase):
    """A row of stands along a wall: one taxilane-like spine behind the tails, each lead-in a short curve off it onto its axis."""
    NARROW = pa.SPECS["narrow"]
    XS = (-88.0, -44.0, 0.0, 44.0, 88.0)
    NOSE_Y = 5.0

    def stands(self, xs=XS, kind="narrow"):
        # (the noses at y = 5 facing south, a facade at y = 0: the centres half a length north)
        return [craft(kind, x, self.NOSE_Y + pa.SPECS[kind][0] / 2.0, 0.0, -1.0) for x in xs]

    def painted(self, f, stands):
        base = tm.strokes([f])
        got = [metres(s) for s in tm.strokes([f], stands)[len(base):] if s[5] == tm.CENTRE_KIND]
        return got

    def test_stands_along_a_wall_have_one_spine_and_short_parallel_branches_that_do_not_cross(self):
        lane = taxiway((-250, 130), (250, 130), cls="taxilane")                # (far: the spine is made, not the mapped lane)
        got = self.painted(feats(lane), self.stands())
        spine_y = self.NOSE_Y + self.NARROW[0] + tm.SPINE_BACK_M                # 10 m behind the tails
        spine = [g for g in got if abs(g[1] - spine_y) < 0.05 and abs(g[3] - spine_y) < 0.05]
        self.assertTrue(spine)
        xs = [x for g in spine for x in (g[0], g[2])]
        self.assertGreater(max(xs) - min(xs), 150.0)                            # one line along the whole row ...
        for end in (min(self.XS), max(self.XS)):
            self.assertTrue(any(abs(g[0] - end) < 0.5 and abs(g[2] - end) < 0.5 and max(g[1], g[3]) > 129.9 for g in got),
                            "... each end joined to the lane by a straight piece")
        offsets = []
        for sx in self.XS[1:-1]:                                                 # (the end stands' axes are the joins' lines)
            mine = [g for g in got if max(g[1], g[3]) < spine_y - 0.3 and abs(g[0] - sx) < 19.5 and abs(g[2] - sx) < 19.5
                    and abs(g[1] - g[3]) > 1e-6]                                # (a branch's pieces; not the stop bar)
            self.assertTrue(mine, sx)
            pts = np.array([p for g in mine for p in (g[:2], g[2:])])
            self.assertAlmostEqual(pts[:, 1].min(), self.NOSE_Y, 2)             # reaches the nose, on the axis
            self.assertLessEqual(pts[:, 0].max() - pts[:, 0].min(), tm.LEAD_RADIUS_K * self.NARROW[1] + 0.5)   # short
            self.assertLessEqual(self.length(mine), self.NARROW[0] + tm.LEAD_OVER_M)
            top = pts[np.argmax(pts[:, 1])]
            self.assertLess(abs(top[1] - spine_y), 0.5)                         # leaves the spine
            offsets.append(float(top[0] - sx))
        self.assertLess(max(offsets) - min(offsets), 0.5)                       # (every branch the same: parallel)
        for i, a in enumerate(got):
            for b in got[i + 1:]:
                self.assertFalse(tm._crossing(np.array([a[:2], a[2:]]), np.array([b[:2], b[2:]])))

    length = staticmethod(LeadIns.length)

    def test_a_mapped_lane_along_the_tails_is_the_spine(self):
        lane = taxiway((-250, 52.0), (250, 52.0), cls="taxilane")              # 0.6 m off the spine's line
        got = self.painted(feats(lane), self.stands())
        spine_y = self.NOSE_Y + self.NARROW[0] + tm.SPINE_BACK_M
        self.assertFalse([g for g in got if abs(g[1] - spine_y) < 3.0 and abs(g[3] - spine_y) < 3.0 and abs(g[0] - g[2]) > 10.0],
                         "no spine of its own is painted")
        self.assertEqual(len([g for g in got if abs(g[1] - g[3]) < 1e-3 and abs(g[1] - self.NOSE_Y) < 1e-2]), len(self.XS))  # (the bars)
        for sx in self.XS:
            self.assertTrue(any(abs(g[2] - sx) < 0.01 and abs(g[3] - self.NOSE_Y) < 0.01 and abs(g[0] - sx) < 0.01 for g in got), sx)

    def test_a_ring_round_a_satellite(self):
        stands = []
        for k in range(6):                                                      # six stands round a satellite at the origin, noses in
            a = np.radians(60.0 * k)
            c = np.array([np.cos(a), np.sin(a)]) * 75.0
            stands.append(craft("narrow", float(c[0]), float(c[1]), float(-np.cos(a)), float(-np.sin(a))))
        got = self.painted(feats(taxiway((-250, -250), (-200, -250), cls="taxilane")), stands)
        r = 75.0 + self.NARROW[0] / 2.0 + tm.SPINE_BACK_M                       # (the tails 10 m beyond: 75 + 18.8 + 10)
        ends = np.array([p for g in got for p in (g[:2], g[2:])])
        ring = ends[(np.hypot(*ends.T) > r - 20.0) & (np.hypot(*ends.T) < r + 3.0)]
        self.assertGreater(len(ring), 12)                                       # one closed ring through the tails
        for k in range(6):
            tail = np.array([np.cos(np.radians(60.0 * k)), np.sin(np.radians(60.0 * k))]) * r
            self.assertLess(float(np.hypot(*(ring - tail).T).min()), 3.0, k)


class StandFont(unittest.TestCase):
    def test_every_character_is_inside_its_box(self):
        for ch, strokes in tm._GLYPHS.items():
            pts = np.concatenate(strokes)
            self.assertGreaterEqual(pts.min(), -1e-9, ch)
            self.assertLessEqual(pts[:, 0].max(), 4.0 + 1e-9, ch)
            self.assertLessEqual(pts[:, 1].max(), 6.0 + 1e-9, ch)
            self.assertGreater(pts[:, 1].max() - pts[:, 1].min(), 5.5, ch)              # (a rounded apex a little under)
        for ch in "0123456789":
            self.assertIn(ch, tm._GLYPHS)

    def test_digits_are_upright_and_centred_past_the_stop_bar(self):
        for u in (np.array([0.0, 1.0]), np.array([1.0, 0.0]), np.array([-0.6, 0.8])):
            right = np.array([u[1], -u[0]])
            nose = np.array([10.0, -20.0])
            lines = tm._number("0123456789"[:tm.NUM_MAX], nose, u)
            self.assertTrue(lines)
            q = np.concatenate(lines) - nose
            up, across = q @ u, q @ right
            self.assertGreaterEqual(up.min(), tm.NUM_AFTER_M - 1e-6)
            self.assertAlmostEqual(up.max(), tm.NUM_AFTER_M + tm.NUM_H_M, 6)
            half = (tm.NUM_MAX * tm.NUM_H_M * tm.NUM_W_K + (tm.NUM_MAX - 1) * tm.NUM_H_M * tm.NUM_GAP_K) / 2.0
            self.assertAlmostEqual(across.min(), -half, 6)
            self.assertAlmostEqual(across.max(), half, 6)
        one = np.concatenate(tm._number("1", np.zeros(2), np.array([0.0, 1.0])))
        self.assertGreater(one[np.argmax(one[:, 1]), 1], 2.4)                            # (a 1's top is its tallest point)


if __name__ == "__main__":
    unittest.main()
