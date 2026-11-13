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
        return [metres(s) for s in got[len(base):]], got[len(base):]

    def test_lane_arc_straight_run_to_the_nose_and_a_stop_bar(self):
        f = feats(self.LANE)
        L, span = self.NARROW[0], self.NARROW[1]
        segs, raw = self.painted(f, craft("narrow", 0.0, 60.0, 0.0, 1.0))                # nose 60 + L/2 north, tail to the lane
        nose = 60.0 + L / 2.0
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
        segs, _ = self.painted(feats(self.LANE), craft("turboprop", 30.0, 50.0, 0.0, 1.0))
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
        segs, _ = self.painted(f, craft("narrow", 0.0, 60.0, 0.0, 1.0))
        self.assertAlmostEqual(segs[0][0], -30.0, 1)                    # from the lane's end ...
        self.assertAlmostEqual(segs[0][1], 0.0, 1)
        self.assertAlmostEqual(segs[0][2], -tm.LEAD_RADIUS_K * self.NARROW[1], delta=0.5)   # ... straight on to where the curve starts
        self.assertAlmostEqual(segs[0][3], 0.0, 1)

    def test_a_stand_on_the_far_side_is_reached_from_its_own_side(self):
        segs, _ = self.painted(feats(self.LANE), craft("narrow", 0.0, -60.0, 0.0, -1.0))
        self.assertAlmostEqual(segs[0][1], 0.0, 1)
        self.assertAlmostEqual(segs[-2][3], -60.0 - self.NARROW[0] / 2.0, 2)

    def test_no_lead_in_for_a_ga_row_or_a_stand_without_a_lane(self):
        f = feats(self.LANE)
        self.assertEqual(self.painted(f, craft("light", 0.0, 30.0, 0.0, 1.0, "ga"))[0], [])
        self.assertEqual(self.painted(f, craft("narrow", 600.0, 900.0, 0.0, 1.0))[0], [])          # (a lane 1 km off)

    def test_a_lane_ending_at_the_nose_along_the_axis_is_carried_on_to_it(self):
        f = feats(taxiway((0, 0), (0, 40), cls="taxilane"))
        segs, _ = self.painted(f, craft("narrow", 0.0, 60.0, 0.0, 1.0))      # nose at 78.8: the lane's end 38.8 short of it
        self.assertEqual(len(segs), 2)                                  # a straight line and the bar
        self.assertAlmostEqual(segs[0][1], 40.0, 1)
        self.assertAlmostEqual(segs[0][3], 60.0 + self.NARROW[0] / 2.0, 2)

    def test_chunks_carry_the_lead_in_each_in_one_tile(self):
        f = feats(self.LANE)
        st = [craft("narrow", 0.0, 60.0, 0.0, 1.0)]
        tc = TileChunks()
        run = lambda stands: [c for tx in range(-2, 2) for ty in range(-2, 2) for c in
                              tm.tile_chunks([f], FRAME, tx, ty, lambda la, lo: np.full(len(la), 7.0), tc.bbox, stands)]
        plain, with_lead = run(None), run(st)
        length = lambda cs: sum(float(np.hypot(*np.diff(np.array(c["n"])[:, :2], axis=0).T).sum()) for c in cs)
        want = sum(float(np.hypot(m[2] - m[0], m[3] - m[1])) for m in self.painted(f, *st)[0])
        self.assertAlmostEqual(length(with_lead) - length(plain), want, delta=want * 0.02)


if __name__ == "__main__":
    unittest.main()
