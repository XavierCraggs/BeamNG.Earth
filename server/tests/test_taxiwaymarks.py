"""taxiwaymarks: the yellow centreline along the paved taxiways and the runway holding position marking where one
meets a runway. The centreline follows the mapped line and stops short of a runway; a taxiway entering a runway has
ICAO pattern A across its width on the taxiway side (a mapped holding_position point moves it); Features of anywhere
else and unpaved ways draw nothing; the tile's chunks are the strokes, each in exactly one tile."""
import json
import os
import sys
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import aeroways  # noqa: E402
import airportgrade  # noqa: E402
import geodesy  # noqa: E402
import mapgeom  # noqa: E402
import parkedaircraft as pa  # noqa: E402
import standmarks  # noqa: E402
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


def filled(f, stands, site=None):
    """[(polygon (k, 2) m east / north of the frame's origin, colour, layer)] of the stands' filled marks."""
    out = []
    for la, lo, colour, layer in tm.polygons([f], list(stands), site):
        e, n, _ = FRAME.geodetic_to_enu(la, lo, np.zeros(len(la)))
        out.append((np.stack([e, n], 1), colour, layer))
    return out


def is_forest(segs):
    """Is the drawing of the segments (x0, y0, x1, y1) a forest: no closed loop? A segment's end that lies on another segment
    (within 0.02 m) splits it there; ends within 0.05 m are one point; a crossing without a shared point is none; then a
    union-find over the pieces finds no piece joining two points already joined."""
    segs = [np.array(g, np.float64) for g in segs if np.hypot(g[2] - g[0], g[3] - g[1]) > 1e-6]
    pts = [[g[:2], g[2:]] for g in segs]                                   # (per segment: its points in order along it)
    ends = [p for ps in pts for p in (ps[0], ps[-1])]
    for k, g in enumerate(segs):
        a, b = g[:2], g[2:]
        for e in ends:
            t = float((e - a) @ (b - a)) / float((b - a) @ (b - a))
            if 0.0 < t < 1.0 and np.hypot(*(a + t * (b - a) - e)) < 0.02:
                pts[k].append(e)
    parent = {}

    def key(p):
        return (round(float(p[0]) / 0.05), round(float(p[1]) / 0.05))

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for k, g in enumerate(segs):
        a, d = g[:2], g[2:] - g[:2]
        ordered = sorted(pts[k], key=lambda p: float((p - a) @ d))
        for p, q in zip(ordered[:-1], ordered[1:]):
            kp, kq = key(p), key(q)
            if kp == kq:
                continue
            ra, rb = find(kp), find(kq)
            if ra == rb:
                return False
            parent[ra] = rb
    return True


def of(got, kind):
    return [s for s in got if s[5] == kind]


class Centreline(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(tm, "_edge_lines", lambda sc, feats_list: [])         # (the edge lines: TaxiEdges)
        patcher.start()
        self.addCleanup(patcher.stop)

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
    def setUp(self):
        patcher = mock.patch.object(tm, "_edge_lines", lambda sc, feats_list: [])         # (the edge lines: TaxiEdges)
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def polys(self, f, *stands):
        """[(polygon (k, 2) m, colour, layer)] of the stands' filled marks."""
        return filled(f, stands)

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
            self.assertEqual((s[4], s[5], s[6]), (tm.LEAD_W_M, tm.CENTRE_KIND, "yellow"))      # the lead-in's paint
        line = segs
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
        bars = [p for p, colour, layer in self.polys(f, craft("narrow", 0.0, 40.0, 0.0, 1.0)) if colour == "yellow" and layer == "paint"
                and abs(p[:, 1].mean() - nose) < 0.01 and abs(p[:, 0].mean()) < 0.01]
        self.assertEqual(len(bars), 1)                                                       # the stop bar across the axis at the nose
        self.assertAlmostEqual(np.ptp(bars[0][:, 0]), tm.STOP_BAR_M, 2)
        self.assertAlmostEqual(np.ptp(bars[0][:, 1]), tm.STOP_BAR_W_M, 2)

    def test_a_curve_not_a_corner_between_lane_and_axis(self):
        segs, _ = self.painted(feats(self.LANE), craft("turboprop", 30.0, 40.0, 0.0, 1.0))
        line = segs
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
        self.assertAlmostEqual(segs[-1][3], -40.0 - self.NARROW[0] / 2.0, 2)

    def test_no_lead_in_for_a_ga_row_and_a_straight_stub_for_a_stand_without_a_lane(self):
        f = feats(self.LANE)
        self.assertEqual(self.painted(f, craft("light", 0.0, 30.0, 0.0, 1.0, "ga"))[0], [])
        segs = self.painted(f, craft("narrow", 600.0, 900.0, 0.0, 1.0))[0]                         # (a lane 1 km off)
        self.assertEqual(len(segs), 1)                                  # the stub along the axis
        nose = 900.0 + self.NARROW[0] / 2.0
        self.assertAlmostEqual(segs[0][3], nose, 2)
        self.assertAlmostEqual(segs[0][3] - segs[0][1], self.NARROW[0] + tm.LEAD_STUB_M, 2)
        self.assertAlmostEqual(segs[0][0], 600.0, 2)

    def test_a_lane_ending_at_the_nose_along_the_axis_is_carried_on_to_it(self):
        f = feats(taxiway((0, 0), (0, 40), cls="taxilane"))
        segs, _ = self.painted(f, craft("narrow", 0.0, 60.0, 0.0, 1.0))      # nose at 78.8: the lane's end 38.8 short of it
        self.assertEqual(len(segs), 1)                                  # a straight line
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
        self.assertLessEqual(self.length(near), cap)
        self.assertGreater(len(near), 1)                                                    # (a lane's line: a curve and a run)
        far = self.painted(f, craft("narrow", 0.0, 75.0, 0.0, 1.0))[0]                     # (nose 93.8 m on: past it: the stub)
        self.assertEqual(len(far), 1)
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
        self.assertEqual(len(stub), 1)
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
        length = lambda cs: sum(float(np.hypot(*np.diff(np.array(c["n"])[:, :2], axis=0).T).sum()) for c in cs if c["n"])
        st = craft("narrow", 0.0, 40.0, 0.0, 1.0)
        self.assertAlmostEqual(length(run([st, st])), length(run([st])), places=3)
        quads = lambda cs: sum(len(c["poly"]) for c in cs if c.get("poly"))
        self.assertEqual(quads(run([st, st])) // 4 > 0, True)                   # (the boxes and lettering are in the tiles too)

    def test_chunks_carry_the_lead_in_each_in_one_tile(self):
        f = feats(self.LANE)
        st = [craft("narrow", 0.0, 40.0, 0.0, 1.0)]
        tc = TileChunks()
        run = lambda stands: [c for tx in range(-2, 2) for ty in range(-2, 2) for c in
                              tm.tile_chunks([f], FRAME, tx, ty, lambda la, lo: np.full(len(la), 7.0), tc.bbox, stands)]
        plain, with_lead = run(None), run(st)
        length = lambda cs: sum(float(np.hypot(*np.diff(np.array(c["n"])[:, :2], axis=0).T).sum()) for c in cs
                                if c["n"] and c["w"] == tm.LEAD_W_M and "layer" not in c)
        want = sum(float(np.hypot(m[2] - m[0], m[3] - m[1])) for m in self.painted(f, *st)[0])
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
        number = lambda ref: [p for p, colour, layer in filled(f, [c._replace(ref=ref)])
                              if layer == "glyph" and p[:, 1].min() > nose + 1.0 and abs(p[:, 0].mean()) < 4.0]
        glyph = number("12")
        self.assertGreater(len(glyph), 6)                                           # (a 1 and a 2: their segments)
        pts = np.concatenate(glyph)
        h, cw, _bar, _gap, cg = tm.NUM_TEXT
        low = nose + tm.STOP_BAR_W_M / 2.0 + tm.NUM_AFTER_M + tm.NUM_MARGIN[1]
        self.assertAlmostEqual(pts[:, 1].min(), low, 2)                             # past the stop bar ...
        self.assertAlmostEqual(pts[:, 1].max(), low + h, 2)                         # ... 1.5 m tall characters ...
        half = (2 * cw + cg) / 2.0
        self.assertAlmostEqual(pts[:, 0].max(), half, 2)                            # ... centred on the axis (the 2's right edge)
        boxes = [p for p, colour, layer in filled(f, [c._replace(ref="12")]) if colour == "yellow" and layer == "paint"
                 and p[:, 1].min() > nose + 1.0 and abs(p[:, 0].mean()) < 0.01]
        self.assertEqual(len(boxes), 1)                                             # on one yellow box, the text's size and a margin
        self.assertAlmostEqual(np.ptp(boxes[0][:, 0]), 2 * cw + cg + 2 * tm.NUM_MARGIN[0], 2)
        self.assertAlmostEqual(np.ptp(boxes[0][:, 1]), h + 2 * tm.NUM_MARGIN[1], 2)
        black = [p for p, colour, layer in filled(f, [c._replace(ref="12")]) if layer == "under" and p[:, 1].min() > nose + 1.0
                 and abs(p[:, 0].mean()) < 0.01]
        self.assertEqual(len(black), 1)                                             # ... over a black one BORDER_M larger each side
        self.assertAlmostEqual(np.ptp(black[0][:, 0]) - np.ptp(boxes[0][:, 0]), 2 * tm.BORDER_M, 2)
        self.assertEqual(number("12@"), [])                                         # (no font for an @: none)

    def test_stop_bars_per_kind_with_generic_labels_and_a_border(self):
        f = feats(self.LANE)
        for kind, want in (("wide", ["WIDE", "A320", "AT72"]), ("narrow", ["A320", "AT72", "C172"]), ("turboprop", ["AT72", "C172"])):
            at = self.polys(f, craft(kind, 0.0, 60.0, 0.0, 1.0))
            nose = 60.0 + pa.SPECS[kind][0] / 2.0
            bars = sorted([p for p, colour, layer in at if colour == "yellow" and layer == "paint"
                           and abs(np.ptp(p[:, 0]) - tm.STOP_BAR_M) < 0.01 and abs(np.ptp(p[:, 1]) - tm.STOP_BAR_W_M) < 0.01],
                          key=lambda p: -p[:, 1].mean())
            self.assertEqual(len(bars), len(want), kind)                            # a bar for each kind that fits
            self.assertAlmostEqual(bars[0][:, 1].mean(), nose, 2)                   # (the stand's own at the nose, the others back)
            gaps = [bars[i][:, 1].mean() - bars[i + 1][:, 1].mean() for i in range(len(bars) - 1)]
            self.assertTrue(all(g > 1.9 for g in gaps), gaps)
            labels = [p for p, colour, layer in at if colour == "yellow" and layer == "paint"
                      and abs(np.ptp(p[:, 0]) - tm.LABEL_BOX_M[0]) < 0.01 and abs(np.ptp(p[:, 1]) - tm.LABEL_BOX_M[1]) < 0.01]
            self.assertEqual(len(labels), len(want))                                # a 2.2 x 0.9 box beside each, with its text
            for lab in labels:
                inner = [p for p, colour, layer in at if layer == "glyph" and abs(p[:, 0].mean() - lab[:, 0].mean()) < 1.0
                         and abs(p[:, 1].mean() - lab[:, 1].mean()) < 0.45]
                self.assertGreater(len(inner), 8)
                pts = np.concatenate(inner)
                self.assertLessEqual(pts[:, 1].max() - pts[:, 1].min(), tm.LABEL_TEXT[0] + 1e-3)
                self.assertGreaterEqual(pts[:, 0].min(), lab[:, 0].min())           # (the text is inside its box)
                self.assertLessEqual(pts[:, 0].max(), lab[:, 0].max())
            for p in bars:                                                          # every bar has its black border under it
                self.assertTrue(any(layer == "under" and abs(p[:, 1].mean() - q[:, 1].mean()) < 1e-3
                                    and abs(np.ptp(q[:, 0]) - np.ptp(p[:, 0]) - 2 * tm.BORDER_M) < 1e-3 for q, c_, layer in at))
        raw = tm.strokes([f], [craft("narrow", 0.0, 60.0, 0.0, 1.0)])
        under = [s for s in raw if s[5] == tm.UNDER_KIND]
        self.assertTrue(under)                                                      # the lead-in has a border under it too: black,
        for s in under:
            self.assertEqual((round(s[4], 3), s[6]), (round(tm.LEAD_W_M + 2 * tm.BORDER_M, 3), "black"))   # 0.15 m wider each side
        self.assertEqual(len(under), len([s for s in raw if s[5] == tm.CENTRE_KIND and s[4] == tm.LEAD_W_M]))

    def test_the_equipment_restraint_legs_are_red_and_stay_inside_the_wingspan(self):
        f = feats(self.LANE)
        c = craft("narrow", 0.0, 60.0, 0.0, 1.0)
        raw = [s for s in tm.strokes([f], [c]) if s[5] == tm.RESTRAINT_KIND]
        self.assertEqual(len(raw), 2)
        self.assertTrue(all(s[6] == "red" for s in raw))
        red = [metres(s) for s in raw]
        xs = np.array([x for m in red for x in (m[0], m[2])])
        self.assertLess(xs.max(), self.NARROW[1] / 2.0)                  # (inside the wings: never into the next stand)
        self.assertGreater(xs.max(), 0.0)
        self.assertLess(xs.min(), 0.0)

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
        lane = taxiway((-250, 100), (250, 100), cls="taxilane")                # (47 m off: the spine is made, not the mapped lane)
        got = self.painted(feats(lane), self.stands())
        spine_y = self.NOSE_Y + self.NARROW[0] + tm.SPINE_BACK_M                # 10 m behind the tails
        spine = [g for g in got if abs(g[1] - spine_y) < 0.05 and abs(g[3] - spine_y) < 0.05]
        self.assertTrue(spine)
        xs = [x for g in spine for x in (g[0], g[2])]
        self.assertGreater(max(xs) - min(xs), 150.0)                            # one line along the whole row ...
        touching = [g for g in got if abs(g[1] - 100.0) < 0.05 or abs(g[3] - 100.0) < 0.05]
        self.assertEqual(len(touching), 1, "... joined to the mapped lane at ONE point (its end), not at both ends")
        offsets = []
        for sx in self.XS[1:-1]:
            mine = [g for g in got if max(g[1], g[3]) < spine_y - 0.3 and abs(g[0] - sx) < 19.5 and abs(g[2] - sx) < 19.5
                    and abs(g[1] - g[3]) > 1e-6]                                # (a branch's pieces)
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

    def test_the_spine_joins_the_lane_tangentially_by_a_curve_and_not_when_it_is_over_60_m_away(self):
        got = self.painted(feats(taxiway((-250, 100), (250, 100), cls="taxilane")), self.stands())
        near = [g for g in got if abs(g[1] - 100.0) < 0.05 or abs(g[3] - 100.0) < 0.05][0]
        d = np.array([near[2] - near[0], near[3] - near[1]])
        self.assertGreater(abs(d[0]) / np.hypot(*d), 0.9)                       # leaves the lane along it (the lane runs east - west)
        curve = [g for g in got if max(g[1], g[3]) > 53.0 and abs(g[1] - g[3]) > 1e-3]
        self.assertGreater(len(curve), 4)                                       # a curve of several chords, not one straight stub
        lane_y = [100.0, 130.0]
        far = self.painted(feats(taxiway((-250, lane_y[1]), (250, lane_y[1]), cls="taxilane")), self.stands())
        self.assertFalse([g for g in far if max(g[1], g[3]) > 100.0], "a lane 77 m off: no connector (over 60 m)")
        spine_y = self.NOSE_Y + self.NARROW[0] + tm.SPINE_BACK_M
        self.assertTrue([g for g in far if abs(g[1] - spine_y) < 0.05], "... the spine and its branches stand alone")

    def test_a_row_and_its_lane_never_make_a_closed_loop(self):
        """The LAX fault: two stands' lines from a far lane and a spine across the top made a box. Lane, spine and every lead-in
        are a tree: one connection to the lane, one line per stand ending on the spine."""
        for lane_y in (70.0, 100.0, 40.0, 130.0):
            lane = taxiway((-250, lane_y), (250, lane_y), cls="taxilane")
            for xs in ((-22.0, 22.0), self.XS, (0.0, 44.0)):
                stands = self.stands(xs)
                got = self.painted(feats(lane), stands)
                self.assertTrue(is_forest(got + [(-250.0, lane_y, 250.0, lane_y)]), (lane_y, xs))

    def test_exactly_one_lead_in_per_stand_ending_on_its_spine_or_lane(self):
        spine_y = self.NOSE_Y + self.NARROW[0] + tm.SPINE_BACK_M
        for lane_y, kinds in ((100.0, ("narrow",) * 5), (100.0, ("narrow", "wide", "narrow", "turboprop", "narrow")), (52.0, ("narrow",) * 5)):
            xs = self.XS
            stands = [craft(k, x, self.NOSE_Y + pa.SPECS[k][0] / 2.0, 0.0, -1.0) for k, x in zip(kinds, xs)]
            f = feats(taxiway((-250, lane_y), (250, lane_y), cls="taxilane"))
            got = self.painted(f, stands)
            for k, x in zip(kinds, xs):
                tail_y = self.NOSE_Y + pa.SPECS[k][0] + tm.SPINE_BACK_M
                mine = [g for g in got if max(g[1], g[3]) < tail_y + 0.5 and abs(g[0] - x) < 19.5 and abs(g[2] - x) < 19.5
                        and abs(g[1] - g[3]) > 1e-6]
                self.assertTrue(mine, (lane_y, x))
                pts = np.array([p for g in mine for p in (g[:2], g[2:])])
                self.assertAlmostEqual(pts[:, 1].min(), self.NOSE_Y, 2)         # one line, to the nose
                top = pts[np.argmax(pts[:, 1])]
                if lane_y == 52.0:
                    self.assertLess(abs(top[1] - 52.0), 0.1)                    # (a mapped lane: its end lies on that lane)
                elif len(set(kinds)) == 1:                                      # (a straight spine: the paint the branch is not part of)
                    self.assertLess(self._dist_to_polyline(top, [g for g in got if g not in mine]), 0.1, (lane_y, x, top))   # (on the spine's paint)
                self.assertEqual(len(tm._uncrossed([np.array([g[:2], g[2:]]) for g in mine])), len(mine))
            self.assertTrue(is_forest(got + [(-250.0, lane_y, 250.0, lane_y)]), (lane_y, kinds))
        self.assertEqual(len(self.starts(self.XS, 100.0)), len(self.XS))        # (each stand has its one start: not two lines from two lanes)

    def starts(self, xs, lane_y):
        """The painted lines' ends nearest each stand's nose: one per stand."""
        got = self.painted(feats(taxiway((-250, lane_y), (250, lane_y), cls="taxilane")), self.stands(xs))
        return [x for x in xs if any(abs(g[0] - x) < 0.01 and abs(g[1] - self.NOSE_Y) < 0.01 or abs(g[2] - x) < 0.01
                                     and abs(g[3] - self.NOSE_Y) < 0.01 for g in got)]

    @staticmethod
    def _dist_to_polyline(p, others):
        """The distance from p to the nearest of the segments (x0, y0, x1, y1)."""
        best = 1e9
        for g in others:
            a, b = np.array(g[:2]), np.array(g[2:])
            t = np.clip((p - a) @ (b - a) / max((b - a) @ (b - a), 1e-12), 0, 1)
            best = min(best, float(np.hypot(*(a + t * (b - a) - p))))
        return best

    def test_a_mapped_lane_along_the_tails_is_the_spine(self):
        lane = taxiway((-250, 52.0), (250, 52.0), cls="taxilane")              # 0.6 m off the spine's line
        got = self.painted(feats(lane), self.stands())
        spine_y = self.NOSE_Y + self.NARROW[0] + tm.SPINE_BACK_M
        self.assertFalse([g for g in got if abs(g[1] - spine_y) < 3.0 and abs(g[3] - spine_y) < 3.0 and abs(g[0] - g[2]) > 10.0],
                         "no spine of its own is painted")
        bars = [p for p, colour, layer in filled(feats(lane), self.stands()) if colour == "yellow" and layer == "paint"
                and abs(np.ptp(p[:, 0]) - tm.STOP_BAR_M) < 0.01 and abs(p[:, 1].mean() - self.NOSE_Y) < 0.01]
        self.assertEqual(len(bars), len(self.XS))                               # (the stop bars at the noses)
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
    """The bold stencil segment font (standmarks)."""
    SPEC = tm.NUM_TEXT

    def bars(self, text, up=(0.0, 1.0)):
        h, cw, bar, gap, cg = self.SPEC
        return standmarks.text_polys(text, np.zeros(2), np.array(up), h, cw, bar, gap, cg)

    def test_every_character_is_inside_its_cell(self):
        h, cw, bar, gap, cg = self.SPEC
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
            got = self.bars(ch)
            self.assertTrue(got, ch)
            pts = np.concatenate(got)
            self.assertGreaterEqual(pts[:, 0].min(), -cw / 2.0 - 1e-9, ch)
            self.assertLessEqual(pts[:, 0].max(), cw / 2.0 + 1e-9, ch)
            self.assertGreaterEqual(pts[:, 1].min(), -h / 2.0 - 1e-9, ch)
            self.assertLessEqual(pts[:, 1].max(), h / 2.0 + 1e-9, ch)
            for p in got:
                self.assertEqual(p.shape, (4, 2))
        self.assertFalse(standmarks.supported("A@"))
        self.assertEqual(self.bars("a?"), [])

    def test_seven_segment_digits_and_their_stencil_gaps(self):
        h, cw, bar, gap, cg = self.SPEC
        self.assertEqual([len(self.bars(d)) for d in "0123456789"], [6, 2, 5, 5, 4, 5, 6, 3, 7, 6])
        for d in "0123456789":                              # (bars never touch: at least the gap between any two, axis-aligned)
            got = self.bars(d)
            for i, a in enumerate(got):
                for b in got[i + 1:]:
                    sep = max(b[:, 0].min() - a[:, 0].max(), a[:, 0].min() - b[:, 0].max(),
                              b[:, 1].min() - a[:, 1].max(), a[:, 1].min() - b[:, 1].max())
                    self.assertGreaterEqual(sep, gap - 1e-9, d)
        self.assertAlmostEqual(min(float(np.ptp(p[:, 0])) for p in self.bars("1")), bar, 6)       # (a vertical bar is one bar wide)

    def test_text_is_centred_upright_and_rotates_with_up(self):
        h, cw, bar, gap, cg = self.SPEC
        pts = np.concatenate(self.bars("H13"))
        half = standmarks.text_width(3, cw, cg) / 2.0
        self.assertAlmostEqual(pts[:, 0].max(), half, 6)
        self.assertAlmostEqual(pts[:, 0].min(), -half, 6)
        self.assertAlmostEqual(pts[:, 1].max(), h / 2.0, 6)
        up = np.array([-0.6, 0.8])
        right = np.array([up[1], -up[0]])
        q = np.concatenate(self.bars("H13", up=up))
        self.assertAlmostEqual((q @ right).max(), half, 6)                  # (left to right across up)
        self.assertAlmostEqual((q @ up).max(), h / 2.0, 6)

    def test_the_stand_number_box_is_about_4_by_2_m(self):
        h, cw, bar, gap, cg = self.SPEC
        w, hh = standmarks.text_width(3, cw, cg) + 2 * tm.NUM_MARGIN[0], h + 2 * tm.NUM_MARGIN[1]
        self.assertAlmostEqual(w, 4.05, 2)
        self.assertAlmostEqual(hh, 2.0, 2)


def site_of_metres(walls, bridges=()):
    """A taxiwaymarks.Site from rings (k, 2) and (point, unit direction) in metres of the test frame."""
    def ll(xy):
        la, lo, _ = FRAME.enu_to_geodetic(np.asarray(xy[:, 0], np.float64), np.asarray(xy[:, 1], np.float64), 0.0)
        return np.asarray(la), np.asarray(lo)
    br = []
    for pt, d in bridges:
        la, lo = ll(np.array([pt]))
        br.append((float(la[0]), float(lo[0]), float(d[0]), float(d[1])))
    return tm.Site([ll(np.array(w)) for w in walls], br)


class ServiceRoad(unittest.TestCase):
    """The service road along the terminal's wall, between the noses and the building, and what is on it."""
    NARROW = pa.SPECS["narrow"]
    XS = (-88.0, -44.0, 0.0, 44.0, 88.0)

    def stands(self, nose_y=5.0):
        return [craft("narrow", x, nose_y + self.NARROW[0] / 2.0, 0.0, -1.0) for x in self.XS]

    @staticmethod
    def wall(y):
        return [(-300.0, y), (300.0, y), (300.0, y - 25.0), (-300.0, y - 25.0)]

    def paint(self, wall_y, nose_y=5.0):
        f = feats(taxiway((-250, 130), (250, 130), cls="taxilane"))
        site = site_of_metres([self.wall(wall_y)])
        stands = self.stands(nose_y)
        raw = tm.strokes([f], stands, site)
        return [metres(s) for s in raw if s[5] == tm.ROAD_KIND], filled(f, stands, site), raw

    def test_two_lanes_white_edges_and_a_dashed_centre_7_m_wide_6_to_9_5_m_from_the_wall(self):
        edges, filled_, raw = self.paint(-15.0)                         # (the wall 15 m south of the facade: the nose 20 m from it)
        self.assertTrue(all(s[6] == "white" and s[4] == tm.ROAD_LINE_W_M for s in raw if s[5] == tm.ROAD_KIND))
        self.assertEqual(len(edges) > 4, True)
        ys = sorted({round(float(np.mean([m[1], m[3]])), 1) for m in edges if abs(m[0] - m[2]) > 3.0})
        self.assertAlmostEqual(max(ys) - min(ys), tm.ROAD_W_M, 1)     # two solid edges 7 m apart
        self.assertAlmostEqual((max(ys) + min(ys)) / 2.0, -15.0 + tm.ROAD_WALL_M, 1)   # the centre 9.5 m from the wall
        dashes = [p for p, colour, layer in filled_ if colour == "white" and layer == "paint" and 0.05 < np.ptp(p[:, 1]) < 0.3
                  and 2.0 < np.ptp(p[:, 0]) < 3.5]
        self.assertGreater(len(dashes), 10)                           # a dashed centre
        for p in dashes:
            self.assertAlmostEqual(p[:, 1].mean(), -15.0 + tm.ROAD_WALL_M, 1)

    def test_none_where_the_nose_is_under_9_m_from_the_wall(self):
        edges, filled_, raw = self.paint(-3.0)                          # (nose 8 m from the wall)
        self.assertEqual(edges, [])
        self.assertFalse([p for p, colour, layer in filled_ if colour == "white"])

    def test_give_way_triangles_each_side_of_a_lead_in_that_crosses(self):
        items = [(np.array([x, 5.0]), np.array([0.0, -1.0]), self.NARROW[0], self.NARROW[1]) for x in self.XS]
        walls = [np.array(self.wall(-15.0), np.float64)]
        lead = np.array([[10.0, 30.0], [10.0, -20.0]])                # a line across the road at x = 10
        ribbons, polys = tm._service_roads(items, [(list(range(5)), "row")], walls, [lead])
        tri = [p for p, colour, layer in polys if len(p) == 3]
        self.assertEqual(len(tri), 2 * tm.GIVEWAY_N)                  # a row each side of the crossing
        c = np.array([p.mean(axis=0) for p in tri])
        self.assertEqual(int((c[:, 0] > 10.0).sum()), tm.GIVEWAY_N)
        self.assertEqual(int((c[:, 0] < 10.0).sum()), tm.GIVEWAY_N)
        self.assertTrue(all(abs(abs(x - 10.0) - (tm.LEAD_W_M / 2 + tm.GIVEWAY_AT_M + tm.GIVEWAY_H_M / 3)) < 0.2 for x in c[:, 0]))
        self.assertLess(np.ptp(c[:, 1]), tm.ROAD_W_M)                 # across the road's width
        none = tm._service_roads(items, [(list(range(5)), "row")], walls, [np.array([[10.0, 30.0], [10.0, 20.0]])])[1]
        self.assertFalse([p for p, colour, layer in none if len(p) == 3])        # (a line that does not reach it: none)

    def test_equipment_boxes_between_stands_on_the_wall_side(self):
        items = [(np.array([x, 5.0]), np.array([0.0, -1.0]), self.NARROW[0], self.NARROW[1]) for x in self.XS]
        walls = [np.array(self.wall(-15.0), np.float64)]
        ribbons, polys = tm._service_roads(items, [(list(range(5)), "row")], walls, [])
        thin = [p for p, colour, layer in polys if colour == "white" and 0.1 < min(np.ptp(p[:, 0]), np.ptp(p[:, 1])) < 0.2
                and max(np.ptp(p[:, 0]), np.ptp(p[:, 1])) > 2.5]       # (the long outline bars of a box, not the dashes)
        self.assertGreater(len(thin), 8)
        pts = np.concatenate([p for p in thin if np.ptp(p[:, 1]) > 0.25 or np.ptp(p[:, 0]) > 5.0])
        centre = -15.0 + tm.ROAD_WALL_M
        self.assertGreater(pts[:, 1].min(), centre - tm.ROAD_W_M / 2.0 - 4.0)    # (south of the road: the wall side)
        self.assertLess(pts[:, 1].max(), centre - tm.ROAD_W_M / 2.0 + 1e-6)
        self.assertGreaterEqual(pts[:, 1].min(), -15.0 + 0.3)                     # (clear of the wall)
        xs = pts[:, 0]
        for ax in self.XS:
            self.assertFalse(((xs > ax - tm.EQUIP_CLEAR_M + 0.4) & (xs < ax + tm.EQUIP_CLEAR_M - 0.4)).any(), ax)   # (between stands)
        none = tm._service_roads(items, [(list(range(5)), "row")], [np.array(self.wall(0.0), np.float64)], [])[1]
        self.assertFalse([p for p in none if np.ptp(p[0][:, 0]) > 5.0 and 0.1 < np.ptp(p[0][:, 1]) < 0.2 and p[1] == "white"
                          and p[0][:, 1].max() < -4.0])               # (a wall too close: no room for a box beside the road)


class BridgeBox(unittest.TestCase):
    def test_a_red_hatched_box_under_each_mapped_jet_bridge_at_a_stand(self):
        f = feats(taxiway((-120, 0), (100, 0), cls="taxilane"))
        st = [craft("narrow", 0.0, 40.0, 0.0, 1.0)]
        nose = 40.0 + pa.SPECS["narrow"][0] / 2.0
        bridge = (np.array([0.0, nose + 8.0]), np.array([0.0, 1.0]))
        site = site_of_metres([], [bridge])
        red = [p for p, colour, layer in filled(f, st, site) if colour == "red" and layer == "red"]
        self.assertGreater(len(red), 8)                                       # the hatching and the outline
        pts = np.concatenate(red)
        w, h = tm.BRIDGE_BOX_M
        self.assertAlmostEqual(np.ptp(pts[:, 0]), w, 1)
        self.assertAlmostEqual(np.ptp(pts[:, 1]), h, 1)
        self.assertAlmostEqual(pts[:, 1].mean(), bridge[0][1] + tm.BRIDGE_BOX_AT_M, delta=0.6)
        diag = [p for p in red if np.ptp(p[:, 0]) > 0.5 and np.ptp(p[:, 1]) > 0.5]
        self.assertGreater(len(diag), 5)                                      # (diagonal strips: not boxes along the axes)
        far = site_of_metres([], [(np.array([0.0, nose + 300.0]), np.array([0.0, 1.0]))])
        self.assertFalse([p for p, colour, layer in filled(f, st, far) if colour == "red"])   # (a bridge with no stand by it: none)
        self.assertFalse([p for p, colour, layer in filled(f, st) if colour == "red"])


class TaxiEdges(unittest.TestCase):
    """Double yellow edge lines along the taxiways' pads, outside the aprons."""
    HALF = aeroways.TAXIWAY_M / 2.0

    def edges(self, *rows):
        return [metres(s) for s in tm.strokes([feats(*rows)]) if s[5] == tm.EDGE_KIND]

    def test_two_015_m_lines_015_m_apart_inside_each_edge(self):
        got = tm.strokes([feats(taxiway((0, 0), (300, 0), tags={"width": "15"}))])
        edge = [s for s in got if s[5] == tm.EDGE_KIND]
        self.assertTrue(edge)
        self.assertTrue(all(s[4] == tm.EDGE_W_M and s[6] == "yellow" for s in edge))
        m = [metres(s) for s in edge]
        ys = sorted({round(abs(float(np.mean([a[1], a[3]]))), 3) for a in m if abs(a[0] - a[2]) > 100.0 and abs(a[1] - a[3]) < 0.01 and abs(a[1]) > 5.0})
        want = sorted(round(self.HALF - tm.EDGE_IN_M - k * (tm.EDGE_W_M + tm.EDGE_GAP_M), 3) for k in (0, 1))
        self.assertEqual(len(ys), 2)                                          # (two lines each side)
        self.assertAlmostEqual(ys[0], want[0], delta=0.05)
        self.assertAlmostEqual(ys[1], want[1], delta=0.05)
        self.assertAlmostEqual(abs(ys[1] - ys[0]) - tm.EDGE_W_M, tm.EDGE_GAP_M, 2)    # 0.15 m lines 0.15 m apart
        for y in (-1.0, 1.0):
            self.assertTrue(any(abs(a[1] * y - want[1]) < 0.05 and abs(a[0] - a[2]) > 0.5 for a in m))

    def test_none_inside_an_apron_a_runway_or_another_pad(self):
        apron = (poly_rows((100, -50), (200, -50), (200, 50), (100, 50)), "apron", "airport", {}, None)
        lane = taxiway((0, 0), (300, 0), tags={"width": "15"})
        m = self.edges(lane, apron)
        mid = [a for a in m if 105 < a[0] < 195 and 105 < a[2] < 195 and abs(a[1] - a[3]) < 0.1 and abs(a[1]) < 8]
        self.assertEqual(mid, [])                                             # (the apron's paving: no edge lines on it)
        self.assertTrue([a for a in m if a[0] < 90 and a[2] < 95])            # ... and they are still there outside it
        rw = self.edges(lane, runway((150, -200), (150, 200)))
        self.assertEqual([a for a in rw if abs(a[0] - 150) < 20 and abs(a[2] - 150) < 20 and abs(a[1]) < 9 and abs(a[3]) < 9], [])
        cross = self.edges(lane, taxiway((150, -200), (150, 200), tags={"width": "15"}))
        self.assertEqual([a for a in cross if 143 < a[0] < 157 and 143 < a[2] < 157 and abs(a[1]) < 6 and abs(a[3]) < 6], [])


def poly_rows(*pts):
    return (mapgeom.POLYGON, [[lonlat([p[0] for p in pts], [p[1] for p in pts])]])


if __name__ == "__main__":
    unittest.main()
