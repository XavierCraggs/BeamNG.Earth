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
        with mock.patch.object(tm, "SMOOTH_MAPPED_M", 0.0):                 # (as mapped: the vertices exactly)
            got = tm.strokes([feats(runway((-1000, 0), (1000, 0)), taxiway((0, 100), (0, 400), (200, 400)))])
        centre = of(got, tm.CENTRE_KIND)
        self.assertEqual(len(centre), 2, "one stroke a segment of the line")
        for s in centre:
            self.assertEqual((s[4], s[5], s[6]), (tm.CENTRE_W_M, tm.CENTRE_KIND, "yellow"))
        want = [(0, 100, 0, 400), (0, 400, 200, 400)]
        for s, w in zip(sorted(centre, key=lambda s: metres(s)[2]), want):
            np.testing.assert_allclose(metres(s), w, atol=0.05)

    def test_a_mapped_corner_is_painted_as_an_arc_of_the_radius(self):
        got = tm.strokes([feats(runway((-1000, 0), (1000, 0)), taxiway((0, 100), (0, 400), (200, 400)))])
        chain = [metres(s) for s in sorted(of(got, tm.CENTRE_KIND), key=lambda s: metres(s)[1] + metres(s)[0])]
        P = np.array([chain[0][:2]] + [m[2:] for m in chain])
        np.testing.assert_allclose(P[0], (0, 100), atol=0.05)                # (the ends as mapped ...)
        np.testing.assert_allclose(P[-1], (200, 400), atol=0.05)
        self.assertGreater(len(P), 10)                                       # (... the corner an arc, no vertex turning over 6 degrees)
        self.assertGreaterEqual(tm._min_radius(P), tm.MIN_RADIUS_M - 0.5)
        self.assertLess(float(np.min(np.hypot(*(P - [0, 400]).T))), tm.MIN_RADIUS_M * 0.5)       # (cut inside the mapped corner)

    def test_a_t_junction_of_mapped_ways_is_tangent_and_an_end_in_an_apron_reaches_its_edge(self):
        main = taxiway((-200, 0), (200, 0))
        branch = taxiway((0, 150), (0, 0))
        got = tm.network([feats(main, branch)])
        self.assertEqual(got.audit().counts(), {"gaps": 0, "opens": 0, "kinks": 0, "sbends": 0})
        stub = taxiway((300, 200), (300, 300), cls="taxilane")              # a lane that ends 10 m short of an apron's edge
        apron = (mapgeom.POLYGON, [[lonlat([250, 350, 350, 250, 250], [50, 50, 310, 310, 50])]])
        f = feats(stub, (apron, "apron", "airport", {"aeroway": "apron"}, None))
        with mock.patch.object(tm, "_pavement_rings", lambda sc, fl: (tm._apron_rings(sc, fl), [])):       # (the apron's edge alone)
            nw = tm.network([f])
        la, lo, _ = nw.frame.enu_to_geodetic(*np.vstack([x[0] for x in nw.lines]).T, np.zeros(sum(len(x[0]) for x in nw.lines)))
        north = FRAME.geodetic_to_enu(la, lo, np.zeros(len(la)))[1]
        self.assertAlmostEqual(float(north.max()), 310.0, delta=0.3)         # (the lane's end carried on to the apron's edge)
        self.assertEqual(nw.audit().counts(), {"gaps": 0, "opens": 1, "kinks": 0, "sbends": 0})      # (its other end: in the apron, on nothing)

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
        smooth = mock.patch.object(tm, "SMOOTH_MAPPED_M", 0.0)                             # (the tiles cut the lines as mapped)
        smooth.start()
        self.addCleanup(smooth.stop)

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
        P = np.array([[s[0], s[1]] for s in segs] + [[segs[-1][2], segs[-1][3]]])
        self.assertGreaterEqual(tm.final_straight(P), tm.lead_straight(self.NARROW[0]) - 0.05)       # ... the straight run to the nose
        self.assertGreaterEqual(tm._min_radius(P), tm.MIN_RADIUS_M - 0.5)                          # (the nose is 38.8 m on: no room for the
        self.assertAlmostEqual(P[-1][1], 20.0 + self.NARROW[0] / 2.0, 2)                            # straight and a 15 m arc beside the lane's end)

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
        far = self.painted(f, craft("narrow", 0.0, 75.0, 0.0, 1.0))[0]                     # (nose 93.8 m on: past it: still to the lane)
        self.assertTrue(any(abs(m[1]) < 0.1 for m in far), "a line past the cap runs on to the lane, never ends on the apron")
        self.assertTrue(any(abs(m[3] - (75.0 + self.NARROW[0] / 2.0)) < 0.1 for m in far), "... and reaches the nose")
        self.assertLessEqual(self.length(far), tm.LEAD_FAR_M)

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
        both = feats(self.LANE, taxiway((-120, 30), (100, 30)))             # the taxiway nearer: no room for the straight run and the arc
        self.assertAlmostEqual(self.painted(both, stand)[0][0][1], 0.0, 1)       # (the nose is 58.8 m on, 28.8 from it): the farther lane

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
        wings = [metres(s) for s in tm.strokes([f], st) if s[5] == tm.STAND_KIND]       # (the wing-tip lines are as wide now)
        want = sum(float(np.hypot(m[2] - m[0], m[3] - m[1])) for m in self.painted(f, *st)[0] + wings)
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
        for s in under:                                                             # (the wing-tip lines have theirs: the same 0.3 m)
            self.assertEqual((round(s[4], 3), s[6]), (round(tm.LEAD_W_M + 2 * tm.BORDER_M, 3), "black"))   # 0.15 m wider each side
        self.assertEqual(tm.CENTRE_W_M, tm.LEAD_W_M)
        self.assertEqual(len(under), len([s for s in raw if s[5] == tm.CENTRE_KIND and s[4] == tm.LEAD_W_M])
                         + len([s for s in raw if s[5] == tm.STAND_KIND]))

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

    @staticmethod
    def back(kinds=("narrow",)):
        """How far behind the tails the spine runs: the largest half wingspan of the row and SPINE_CLEAR_M (ICAO's taxilane clearance)."""
        return max(pa.SPECS[k][1] for k in kinds) / 2.0 + tm.SPINE_CLEAR_M

    def test_stands_along_a_wall_have_one_spine_and_short_parallel_branches_that_do_not_cross(self):
        lane = taxiway((-250, 100), (250, 100), cls="taxilane")                # (47 m off: the spine is made, not the mapped lane)
        got = self.painted(feats(lane), self.stands())
        spine_y = self.NOSE_Y + self.NARROW[0] + self.back()                  # half a span and 7.5 m behind the tails
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
        spine_y = self.NOSE_Y + self.NARROW[0] + self.back()
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
        spine_y = self.NOSE_Y + self.NARROW[0] + self.back()
        for lane_y, kinds in ((100.0, ("narrow",) * 5), (140.0, ("narrow", "wide", "narrow", "turboprop", "narrow")), (52.0, ("narrow",) * 5)):
            xs = self.XS
            stands = [craft(k, x, self.NOSE_Y + pa.SPECS[k][0] / 2.0, 0.0, -1.0) for k, x in zip(kinds, xs)]
            f = feats(taxiway((-250, lane_y), (250, lane_y), cls="taxilane"))
            got = self.painted(f, stands)
            for k, x in zip(kinds, xs):
                tail_y = self.NOSE_Y + pa.SPECS[k][0] + self.back(kinds)
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
        spine_y = self.NOSE_Y + self.NARROW[0] + self.back()
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
        r = 75.0 + self.NARROW[0] / 2.0 + self.back()                           # (the tails: 75 + half a length + the clearance)
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
        self.assertGreaterEqual(len(edges), 2)                       # (both edges: straight, so one stroke each)
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


class GlyphOverBox(unittest.TestCase):
    """The black lettering of the yellow boxes (the stand number, the type labels) is drawn over its box: its own material, listed
    after the yellow's, in a layer above the paint (in game the boxes were plain yellow: 0.6 mm over them, in the black border's
    material, drawn before the yellow)."""

    def setUp(self):
        patcher = mock.patch.object(tm, "_edge_lines", lambda sc, feats_list: [])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_layers_and_materials_put_the_glyphs_over_the_boxes(self):
        import roadmesh
        self.assertEqual(tm.LAYER_OF["glyph"], "glyph")
        lift = roadmesh.LIFT
        self.assertGreaterEqual(lift["glyph"] - lift["mark"], 0.001)             # (at least a millimetre over the paint)
        self.assertGreater(lift["mark"], lift["gutter"])
        self.assertGreater(lift["gutter"], lift["edge"])                          # (the borders under all)
        look = airportgrade.MARK_LOOK
        self.assertNotEqual(look["text"]["m"], look["yellow"]["m"])
        self.assertNotEqual(look["text"]["m"], look["black"]["m"])                # (not the borders' material, which draws first)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mod", "beamng_earth", "levels", "beamng_earth",
                            "art", "runway", "main.materials.json")
        with open(path, encoding="utf-8") as fh:
            self.assertIn(look["text"]["m"], json.load(fh))                       # (and the mod has it)

    def test_polygons_glyphs_lie_inside_a_yellow_box(self):
        f = feats(taxiway((-120, 0), (100, 0), cls="taxilane"))
        c = craft("narrow", 0.0, 60.0, 0.0, 1.0)._replace(ref="B13")
        got = filled(f, [c])
        glyphs = [p for p, colour, layer in got if layer == "glyph"]
        self.assertTrue(glyphs)
        self.assertEqual({colour for _p, colour, layer in got if layer == "glyph"}, {"text"})
        boxes = [p for p, colour, layer in got if colour == "yellow" and layer == "paint"]
        for g in glyphs:
            self.assertTrue(any(g[:, 0].min() >= b[:, 0].min() - 1e-6 and g[:, 0].max() <= b[:, 0].max() + 1e-6
                                and g[:, 1].min() >= b[:, 1].min() - 1e-6 and g[:, 1].max() <= b[:, 1].max() + 1e-6 for b in boxes))

    def test_a_tiles_chunks_list_the_lettering_after_the_yellow_and_higher(self):
        import roadmesh
        f = feats(taxiway((-120, 0), (300, 0), cls="taxilane"))
        c = craft("narrow", 100.0, 60.0, 0.0, 1.0)._replace(ref="B13")
        side = 256.0
        bbox = lambda tx, ty: (tx * side, ty * side, (tx + 1) * side, (ty + 1) * side)
        chunks = tm.tile_chunks([f], FRAME, 0, 0, lambda la, lo: np.full(len(la), 7.0), bbox, [c])
        text, yellow = airportgrade.MARK_LOOK["text"]["m"], airportgrade.MARK_LOOK["yellow"]["m"]
        order = []
        for ch in chunks:
            if ch["m"] not in order:
                order.append(ch["m"])
        self.assertIn(text, order)
        self.assertIn(yellow, order)
        self.assertGreater(order.index(text), order.index(yellow))                 # (the mesh draws the materials in this order)
        glyph = [ch for ch in chunks if ch["m"] == text]
        box = [ch for ch in chunks if ch["m"] == yellow and ch.get("poly")]
        self.assertTrue(glyph and box)
        self.assertEqual({roadmesh.layer_of(ch) for ch in glyph}, {"glyph"})
        self.assertEqual({roadmesh.layer_of(ch) for ch in box}, {"mark"})
        self.assertGreater(roadmesh.LIFT["glyph"], roadmesh.LIFT["mark"])
        # (the chunks of the polygons come in the layers' order: the border under, then the paint, then the lettering)
        layers = [ch["layer"] for ch in chunks if ch.get("poly")]
        self.assertEqual(layers, sorted(layers, key=lambda x: ["edge", "gutter", "mark", "glyph"].index(x)))


def circumradii(P, min_side=0.2):
    """The radius of the circle through each three consecutive points of the polyline P (k, 2) (inf for a straight run)."""
    out = []
    for a, b, c in zip(P[:-2], P[1:-1], P[2:]):
        ab, bc, ca = np.hypot(*(b - a)), np.hypot(*(c - b)), np.hypot(*(a - c))
        cr = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        if min(ab, bc) < min_side or cr < 1e-9:
            out.append(np.inf)
        else:
            out.append(ab * bc * ca / (2.0 * cr))
    return out


def turns(P):
    """The turn (degrees) at each interior point of the polyline P."""
    out = []
    for a, b, c in zip(P[:-2], P[1:-1], P[2:]):
        d1, d2 = b - a, c - b
        if np.hypot(*d1) < 1e-9 or np.hypot(*d2) < 1e-9:
            continue
        out.append(float(np.degrees(np.arccos(np.clip(d1 @ d2 / np.hypot(*d1) / np.hypot(*d2), -1, 1)))))
    return out


class Routing(unittest.TestCase):
    """The painted yellow lead-ins, spines and connectors: no branch that leads nowhere, every curve a circular arc of at least 15 m
    (8 m for a light aircraft), the tightest smooth arc, never a dropped line, where none fits; no kink over 25 degrees."""

    def lines(self, lane, stands):
        """([polyline (k, 2) m of every painted lead-in, spine and connector], [nose (2,)], mapped lane segments)."""
        f = feats(*lane) if isinstance(lane, (list, tuple)) else feats(lane)
        sc = tm.scene([f])

        def to_frame(P):                                                            # (the scene's own frame: ours)
            la, lo, _ = sc.frame.enu_to_geodetic(P[:, 0], P[:, 1], np.zeros(len(P)))
            e, n, _ = FRAME.geodetic_to_enu(la, lo, np.zeros(len(P)))
            return np.stack([e, n], 1)
        out = []
        for la, lo, w, kind, _col in tm._lead_lines(sc, stands, None)[0]:
            if kind == tm.CENTRE_KIND and abs(w - tm.LEAD_W_M) < 1e-9:
                e, n, _ = FRAME.geodetic_to_enu(la, lo, np.zeros(len(la)))
                out.append(np.stack([e, n], 1))
        e0, n0, _ = FRAME.geodetic_to_enu(np.array([c.lat for c in stands]), np.array([c.lon for c in stands]), np.zeros(len(stands)))
        noses = [np.array([x, y]) + np.array([c.ne, c.nn]) / np.hypot(c.ne, c.nn) * pa.SPECS[c.kind][0] / 2.0
                 for c, x, y in zip(stands, e0, n0)]
        lanes = tm._lanes(sc)
        return out, noses, [(a, b) for a, b in zip(to_frame(lanes[0]), to_frame(lanes[0] + lanes[1] * lanes[2][:, None]))]

    @staticmethod
    def on(p, segs, tol=0.06):
        for a, b in segs:
            d = b - a
            t = min(max(float((p - a) @ d) / max(float(d @ d), 1e-12), 0.0), 1.0)
            if np.hypot(*(a + d * t - p)) <= tol:
                return True
        return False

    def dead_ends(self, lines, noses, lane_segs):
        """The ends of the painted polylines that are no stand's nose, on no other painted line and on no mapped lane."""
        segs = [(P[i], P[i + 1]) for P in lines for i in range(len(P) - 1)]
        out = []
        for k, P in enumerate(lines):
            own = [(Q[i], Q[i + 1]) for j, Q in enumerate(lines) if j != k for i in range(len(Q) - 1)]
            for p in (() if np.hypot(*(P[0] - P[-1])) < 0.01 else (P[0], P[-1])):      # (a ring closes on itself: no ends)
                if any(np.hypot(*(p - n)) < 0.6 for n in noses) or self.on(p, own) or self.on(p, lane_segs):
                    continue
                out.append(p)
        del segs
        return out

    ROW = tuple(float(x) for x in (-88, -44, 0, 44, 88))

    def row(self, kinds=("narrow",) * 5, xs=ROW, y=5.0):
        return [craft(k, x, y + pa.SPECS[k][0] / 2.0, 0.0, -1.0) for k, x in zip(kinds, xs)]

    def scenarios(self):
        """[(lane tuple, stands)]: rows with a lane far, near and mapped along them; rows of mixed kinds; a satellite ring; light stands."""
        lane = lambda y: taxiway((-250, y), (250, y), cls="taxilane")
        out = [((lane(100.0),), self.row()), ((lane(130.0),), self.row()), ((lane(70.0),), self.row(xs=(-22.0, 22.0, 66.0, 110.0, 154.0))),
               ((lane(100.0),), self.row(("narrow", "wide", "narrow", "turboprop", "narrow"))),
               ((lane(52.0),), self.row()), ((lane(100.0),), self.row(xs=(-22.0, 22.0))),
               ((lane(100.0),), self.row(("light",) * 4, xs=(-40.0, -20.0, 0.0, 20.0)))]
        ring = []
        for k in range(6):
            a = np.radians(60.0 * k)
            ring.append(craft("narrow", float(np.cos(a) * 75.0), float(np.sin(a) * 75.0), float(-np.cos(a)), float(-np.sin(a))))
        out.append(((taxiway((-250, -250), (-200, -250), cls="taxilane"),), ring))
        out.append(((taxiway((-120, 0), (100, 0), cls="taxilane"),), [craft("narrow", 0.0, 40.0, 0.0, 1.0)]))
        out.append(((taxiway((-120, 0), (100, 0), cls="taxilane"),), [craft("turboprop", 30.0, 40.0, 0.0, 1.0)]))
        out.append(((taxiway((-120, 0), (100, 0), cls="taxilane"),), [craft("light", 30.0, 25.0, 0.0, 1.0)]))
        return out

    def test_no_branch_leads_nowhere(self):
        for lane, stands in self.scenarios():
            lines, noses, lane_segs = self.lines(lane, stands)
            self.assertEqual([p.round(1).tolist() for p in self.dead_ends(lines, noses, lane_segs)], [], (lane, len(stands)))

    def test_a_spine_ends_at_its_first_and_last_lead_in(self):
        lane = (taxiway((-250, 130.0), (250, 130.0), cls="taxilane"),)           # (over 60 m off: the spine stands alone)
        stands = self.row()
        lines, noses, lane_segs = self.lines(lane, stands)
        spine_y = 5.0 + pa.SPECS["narrow"][0] + LeadSpine.back()
        spine = [P for P in lines if abs(P[0][1] - spine_y) < 0.05 and abs(P[-1][1] - spine_y) < 0.05 and abs(P[0][0] - P[-1][0]) > 50.0]
        self.assertEqual(len(spine), 1)
        starts = [P[0] for P in lines if abs(P[0][1] - spine_y) < 0.6 and abs(P[-1][0] - P[0][0]) < 20.0 and P[-1][1] < spine_y - 20.0]
        self.assertEqual(len(starts), len(stands))
        self.assertAlmostEqual(min(spine[0][0][0], spine[0][-1][0]), min(s[0] for s in starts), delta=0.1)     # (no branch past the first ...)
        self.assertAlmostEqual(max(spine[0][0][0], spine[0][-1][0]), max(s[0] for s in starts), delta=0.1)     # (... or the last)

    def test_every_stand_has_its_lead_in_to_the_nose(self):
        for lane, stands in self.scenarios():
            lines, noses, _segs = self.lines(lane, stands)
            for n in noses:
                self.assertTrue(any(np.hypot(*(P[-1] - n)) < 0.05 or np.hypot(*(P[0] - n)) < 0.05 for P in lines), (lane, n))

    def test_curves_are_arcs_of_at_least_the_minimum_radius_and_no_corner_over_25_degrees(self):
        for lane, stands in self.scenarios():
            lines, _noses, _segs = self.lines(lane, stands)
            light = all(c.kind == "light" for c in stands)
            floor = (tm.MIN_RADIUS_LIGHT_M if light else tm.MIN_RADIUS_M) * 0.97
            for P in lines:
                for r in circumradii(P):
                    self.assertGreaterEqual(r, floor, (lane, P[0].round(1), P[-1].round(1)))
                for t in turns(P):
                    self.assertLess(t, 25.0, (lane, P[0].round(1)))

    def test_the_connector_leaves_the_lane_and_meets_the_spine_tangentially_in_arcs(self):
        lane = taxiway((-250, 100.0), (250, 100.0), cls="taxilane")
        lines, _noses, _segs = self.lines((lane,), self.row())
        conn = [P for P in lines if abs(P[0][1] - 100.0) < 0.05 or abs(P[-1][1] - 100.0) < 0.05]
        self.assertEqual(len(conn), 1)
        P = conn[0] if abs(conn[0][0][1] - 100.0) < 0.05 else conn[0][::-1]
        d = P[1] - P[0]
        self.assertGreater(abs(d[0]) / np.hypot(*d), 0.97)                          # along the lane (it runs east - west)
        self.assertLessEqual(max(turns(P)), 6.0)                                    # (arcs in small chords)
        self.assertGreater(min(circumradii(P)), tm.MIN_RADIUS_M * 0.97)

    def test_the_tightest_arc_not_a_dropped_line_where_the_lane_has_no_room(self):
        lane = taxiway((-8, 0), (8, 0), cls="taxilane")                             # 8 m each side of the axis: a 15 m arc has no room
        sc = tm.scene([feats(lane)])
        la, lo, _ = FRAME.enu_to_geodetic(np.array([0.0]), np.array([40.0 + pa.SPECS["narrow"][0] / 2.0]), np.zeros(1))
        e, n, _ = sc.frame.geodetic_to_enu(la, lo, np.zeros(1))
        nose = np.array([float(e[0]), float(n[0])])                                 # (the scene's own frame)
        axis = np.array([0.0, 1.0])
        lanes, pads = tm._lanes(sc), tm._pads(sc)
        got = tm._stand_line(lanes, None, nose, axis, tm.MIN_RADIUS_M, pads, pa.SPECS["narrow"][0])
        self.assertGreater(len(got), 4)
        self.assertAlmostEqual(float(got[-1][0]), nose[0], 3)
        self.assertAlmostEqual(float(got[-1][1]), nose[1], 3)                       # (it reaches the nose, not a stub from nowhere)
        self.assertLess(abs(float(got[0][1]) - lanes[0][0][1]), 0.01)               # (from the lane)
        self.assertLess(max(turns(got)), 25.0)
        self.assertGreaterEqual(min(circumradii(got)), tm.TIGHT_RADIUS_M * 0.97)
        tight, found = tm._lead_line(lanes, nose, axis, tm.MIN_RADIUS_M, pads, 80.0, False, tm.TIGHT_RADIUS_M)
        self.assertTrue(found)
        self.assertAlmostEqual(min(circumradii(tight)), 8.0, delta=0.3)             # (the arc as big as the lane's 8 m allows)
        none, found = tm._lead_line(lanes, nose, axis, tm.MIN_RADIUS_M, pads, 80.0, False, tm.MIN_RADIUS_M)
        self.assertFalse(found)                                                      # (a 15 m single arc does not fit ...)
        slid, found = tm._lead_line(lanes, nose, axis, tm.MIN_RADIUS_M, pads, 80.0, False, tm.MIN_RADIUS_M, True)
        self.assertTrue(found)                                                       # (... an arc, a straight and an arc, from a slid join point, does)
        self.assertGreaterEqual(min(circumradii(slid)), tm.MIN_RADIUS_M * 0.97)

    def test_dubins_path_is_arcs_and_a_straight_between_two_poses(self):
        got = tm._dubins(np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([50.0, 30.0]), np.array([1.0, 0.0]), 15.0)
        self.assertIsNotNone(got)
        P = tm._dubins_pts(got)
        self.assertAlmostEqual(float(P[0][0]), 0.0, 6)
        self.assertAlmostEqual(float(P[-1][0]), 50.0, 6)
        self.assertAlmostEqual(float(P[-1][1]), 30.0, 6)
        self.assertAlmostEqual(tm._length(P), got[0], delta=0.1)
        self.assertGreaterEqual(min(circumradii(P)), 14.5)
        self.assertLess(max(turns(P)), 6.0)
        self.assertIsNone(tm._dubins(np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([-2.0, 0.5]), np.array([1.0, 0.0]), 15.0))   # (a loop: none)


class WingTipConflicts(unittest.TestCase):
    """Where stands are close the wing-tip lines would overlap or cross: clipped, or dropped."""
    N = pa.SPECS["narrow"]

    def stands(self, *xy):
        return [craft("narrow", x, y, 0.0, 1.0) for x, y in xy]

    def wings(self, stands):
        f = feats(taxiway((-250, -60), (250, -60), cls="taxilane"))
        got = [metres(s) for s in tm.strokes([f], stands) if s[5] == tm.STAND_KIND]
        return [(np.array(g[:2]), np.array(g[2:])) for g in got]

    @staticmethod
    def seg_dist(a, b, c, d):
        return tm._seg_dist(a, b, c, d)

    def test_apart_four_lines_and_close_the_shared_line_once(self):
        self.assertEqual(len(self.wings(self.stands((0.0, 40.0), (80.0, 40.0)))), 4)
        close = self.wings(self.stands((0.0, 40.0), (44.0, 40.0)))              # (their lines 2.2 m apart)
        self.assertEqual(len(close), 3)
        for i, (a, b) in enumerate(close):
            for c, d in close[i + 1:]:
                self.assertGreaterEqual(self.seg_dist(a, b, c, d), tm.WING_CLEAR_M - 1e-6)

    def test_a_line_is_clipped_where_it_would_run_under_an_adjacent_aircraft(self):
        s = self.stands((0.0, 40.0), (36.0, 80.0))                              # (the second's nose end 2.4 m beyond the first's line's end)
        nose0 = 40.0 + self.N[0] / 2.0
        got = self.wings(s)
        side = [(a, b) for a, b in got if abs(a[0] - (self.N[1] / 2.0 + tm.WING_LINE_OFF_M)) < 0.01]
        self.assertEqual(len(side), 1)
        top = max(side[0][0][1], side[0][1][1])
        env_low = 80.0 - self.N[0] / 2.0                                         # (the second's tail)
        self.assertAlmostEqual(top, env_low - tm.WING_CLEAR_M, delta=0.3)
        self.assertLess(top, nose0 - 0.3)                                        # (shorter than the 20 m line)
        for a, b in got:                                                         # (no line within 3 m of the other's aircraft)
            for k, (cx, cy) in enumerate(((0.0, 40.0), (36.0, 80.0))):
                for p in (a + (b - a) * q for q in np.linspace(0.0, 1.0, 40)):
                    dx = max(abs(p[0] - cx) - self.N[1] / 2.0, 0.0)
                    dy = max(abs(p[1] - cy) - self.N[0] / 2.0, 0.0)
                    own = abs(abs(p[0] - cx) - (self.N[1] / 2.0 + tm.WING_LINE_OFF_M)) < 0.01
                    if not own:
                        self.assertGreaterEqual(float(np.hypot(dx, dy)), tm.WING_CLEAR_M - 0.01)

    def test_a_line_under_its_neighbours_aircraft_is_none(self):
        got = self.wings(self.stands((0.0, 40.0), (36.0, 60.0)))                # (their envelopes overlap in length: the line is all under it)
        self.assertEqual([g for g in got if abs(g[0][0] - (self.N[1] / 2.0 + tm.WING_LINE_OFF_M)) < 0.01], [])

    def test_a_line_within_3_m_of_another_stands_lead_in_is_dropped(self):
        stands = [(craft("narrow", 0.0, 40.0, 0.0, 1.0), np.array([0.0, 1.0]), self.N[0], self.N[1], np.array([0.0, 40.0 + self.N[0] / 2.0])),
                  (craft("narrow", 80.0, 40.0, 0.0, 1.0), np.array([0.0, 1.0]), self.N[0], self.N[1], np.array([80.0, 40.0 + self.N[0] / 2.0]))]
        x = self.N[1] / 2.0 + tm.WING_LINE_OFF_M
        near = np.array([[x + 2.0, 30.0], [x + 2.0, 60.0]])                      # (2 m from the first's line)
        far = np.array([[x + 4.0, 30.0], [x + 4.0, 60.0]])
        for lead, count in ((None, 2), (near, 1), (far, 2), (np.array([[x - 5.0, 40.0], [x + 5.0, 40.0]]), 1)):    # (the last crosses it)
            got = tm._wing_lines(stands, [None, lead])
            self.assertEqual(len(got[0]), count, lead)


def poly_rows(*pts):
    return (mapgeom.POLYGON, [[lonlat([p[0] for p in pts], [p[1] for p in pts])]])



def polyline_samples(segs, step=0.5):
    """Points every `step` m along the segments (x0, y0, x1, y1): (n, 2)."""
    out = []
    for g in segs:
        a, b = np.array(g[:2]), np.array(g[2:])
        n = max(1, int(np.hypot(*(b - a)) / step))
        out += [a + (b - a) * k / n for k in range(n + 1)]
    return np.array(out).reshape(-1, 2)


def dist_to_segments(p, segs):
    best = 1e9
    for g in segs:
        a, b = np.array(g[:2]), np.array(g[2:])
        t = np.clip((p - a) @ (b - a) / max((b - a) @ (b - a), 1e-12), 0.0, 1.0)
        best = min(best, float(np.hypot(*(a + t * (b - a) - p))))
    return best


class Connectors(unittest.TestCase):
    """Every painted yellow line ends on a mapped centreline (within 0.1 m), on the line it branches off, or at a stand's nose:
    none is cut short on the open apron."""
    NARROW = pa.SPECS["narrow"]
    XS = (-88.0, -44.0, 0.0, 44.0, 88.0)

    def check(self, f, stands, mapped, label):
        base = tm.strokes([f])
        got = [metres(s) for s in tm.strokes([f], stands)[len(base):] if s[5] == tm.CENTRE_KIND]
        noses = []
        for c in stands:
            e, n, _ = FRAME.geodetic_to_enu(np.array([c.lat]), np.array([c.lon]), np.zeros(1))
            u = np.array([c.ne, c.nn]) / np.hypot(c.ne, c.nn)
            noses.append(np.array([float(e[0]), float(n[0])]) + u * pa.SPECS[c.kind][0] / 2.0)
        deg = {}
        for g in got:
            for p in (g[:2], g[2:]):
                deg.setdefault((round(p[0] / 0.05), round(p[1] / 0.05)), [np.array(p), 0])[1] += 1
        for p, d in deg.values():
            if d != 1:
                continue
            ok = (any(float(np.hypot(*(p - n))) < 0.1 for n in noses) or dist_to_segments(p, mapped) < 0.1
                  or dist_to_segments(p, [g for g in got if not (np.allclose(g[:2], p) or np.allclose(g[2:], p))]) < 0.1)
            self.assertTrue(ok, (label, p.round(1).tolist()))
        return got

    def test_a_stand_beyond_the_length_cap_still_runs_to_the_lane(self):
        lane = taxiway((-120, 0), (100, 0), cls="taxilane")
        got = self.check(feats(lane), [craft("narrow", 0.0, 75.0, 0.0, 1.0)], [(-120.0, 0.0, 100.0, 0.0)], "far stand")
        self.assertTrue(any(abs(g[1]) < 0.1 or abs(g[3]) < 0.1 for g in got), "it starts on the lane")

    def test_rows_and_a_ring_join_the_lanes_and_end_nowhere_else(self):
        for lane_y in (100.0, 130.0, 70.0):
            lane = taxiway((-250, lane_y), (250, lane_y), cls="taxilane")
            stands = [craft("narrow", x, 5.0 + self.NARROW[0] / 2.0, 0.0, -1.0) for x in self.XS]
            self.check(feats(lane), stands, [(-250.0, lane_y, 250.0, lane_y)], ("row", lane_y))
        ring = []
        for k in range(6):
            a = np.radians(60.0 * k)
            c = np.array([np.cos(a), np.sin(a)]) * 75.0
            ring.append(craft("narrow", float(c[0]), float(c[1]), float(-np.cos(a)), float(-np.sin(a))))
        self.check(feats(taxiway((-300, -150), (300, -150), cls="taxilane")), ring, [(-300.0, -150.0, 300.0, -150.0)], "ring")

    def test_a_spine_near_two_lanes_joins_each_of_them(self):
        a = taxiway((-250, 110), (250, 110), cls="taxilane")
        b = taxiway((130, -20), (130, 150), cls="taxilane")
        stands = [craft("narrow", x, 5.0 + self.NARROW[0] / 2.0, 0.0, -1.0) for x in self.XS]
        got = self.check(feats(a, b), stands, [(-250.0, 110.0, 250.0, 110.0), (130.0, -20.0, 130.0, 150.0)], "two lanes")
        self.assertTrue(any(abs(g[1] - 110.0) < 0.1 or abs(g[3] - 110.0) < 0.1 for g in got), "a connector on the first lane")
        self.assertTrue(any(abs(g[0] - 130.0) < 0.1 or abs(g[2] - 130.0) < 0.1 for g in got), "... and one on the second")


class SpineClearance(unittest.TestCase):
    """The spine runs half the largest wingspan and SPINE_CLEAR_M behind the tails, in arcs of at least the radius."""
    NONE = (np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0), np.zeros(0, np.int64))

    def items(self, kinds, xs, y=5.0):
        return [(np.array([x, y]), np.array([0.0, -1.0]), pa.SPECS[k][0], pa.SPECS[k][1]) for k, x in zip(kinds, xs)]

    @staticmethod
    def envelope_distance(P, item):
        nose, u, length, span = item
        smp = np.concatenate([P[i] + (P[i + 1] - P[i]) * (np.arange(20) / 20.0)[:, None] for i in range(len(P) - 1)])
        v = smp - (nose - u * length / 2.0)
        along = np.abs(v[:, 0] * u[0] + v[:, 1] * u[1]) - length / 2.0
        across = np.abs(v[:, 0] * -u[1] + v[:, 1] * u[0]) - span / 2.0
        return float(np.hypot(np.maximum(along, 0.0), np.maximum(across, 0.0)).min())

    def test_a_row_of_wide_stands_has_its_spine_half_a_wide_span_and_7_5_m_behind_the_tails(self):
        kinds = ("narrow", "wide", "narrow", "wide")
        items = self.items(kinds, (-90.0, -30.0, 30.0, 90.0))
        _got, paint, rows, _trims = tm._spines(items, tm._empty_lanes(), self.NONE, list(kinds))
        self.assertEqual(len(rows), 1)
        spine = paint[-1]
        back = pa.SPECS["wide"][1] / 2.0 + tm.SPINE_CLEAR_M
        for it in items:
            self.assertGreaterEqual(self.envelope_distance(spine, it), tm.SPINE_CLEAR_M)
        wide_tail = max(it[0][1] + it[2] for it in items)
        self.assertGreaterEqual(float(spine[:, 1].max()), wide_tail + back - 1.0)       # (behind the wide tails by their half span + 7.5 m)
        self.assertGreaterEqual(tm._min_radius(spine), tm.MIN_RADIUS_M - 0.5)

    def test_a_ring_clears_every_aircraft_and_keeps_the_radius(self):
        items = []
        for k in range(8):
            a = np.radians(45.0 * k)
            c = np.array([np.cos(a), np.sin(a)])
            items.append((c * 40.0, -c, pa.SPECS["narrow"][0], pa.SPECS["narrow"][1]))
        _got, paint, rows, _trims = tm._spines(items, tm._empty_lanes(), self.NONE, ["narrow"] * 8)
        self.assertEqual([k for _m, k in rows], ["ring"])
        for it in items:
            self.assertGreaterEqual(self.envelope_distance(paint[-1], it), tm.SPINE_CLEAR_M)
        self.assertGreaterEqual(tm._min_radius(paint[-1], True), tm.MIN_RADIUS_M - 0.5)

    def test_the_radius_of_a_polyline(self):
        pts = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
        self.assertLess(tm._min_radius(tm._round_arcs(pts, 15.0)), tm.MIN_RADIUS_M)      # (a 90 degree turn on 10 m sides: tight)
        self.assertEqual(tm._min_radius(np.array([[0.0, 0.0], [5.0, 0.0], [9.0, 0.0]])), np.inf)


class MarkWidths(unittest.TestCase):
    def test_yellow_centrelines_are_0_3_m_with_a_0_15_m_black_border_each_side(self):
        self.assertEqual((tm.CENTRE_W_M, tm.LEAD_W_M, tm.BORDER_M), (0.3, 0.3, 0.15))
        f = feats(taxiway((-100, 0), (100, 0), cls="taxilane"))
        raw = tm.strokes([f])
        yellow = [s for s in raw if s[5] == tm.CENTRE_KIND]
        under = [s for s in raw if s[5] == tm.UNDER_KIND]
        self.assertTrue(yellow and under, "a mapped taxilane has its border")
        self.assertTrue(all(abs(s[4] - 0.3) < 1e-9 for s in yellow))
        self.assertTrue(all(abs(s[4] - 0.6) < 1e-9 and s[6] == "black" for s in under))
        self.assertAlmostEqual(sum(float(np.hypot(*np.subtract(metres(s)[2:], metres(s)[:2]))) for s in under), 200.0, 0)


class ServiceRoadFrontage(unittest.TestCase):
    """One road along a building's frontage: a ring round a satellite, an arc along a terminal, cut only by a bridge's footprint."""
    NARROW = pa.SPECS["narrow"]

    @staticmethod
    def circle(r, n=24):
        return [(r * np.cos(2 * np.pi * k / n), r * np.sin(2 * np.pi * k / n)) for k in range(n)]

    def road_points(self, stands, site):
        f = feats(taxiway((-400, -400), (-300, -400), cls="taxilane"))
        raw = [metres(s) for s in tm.strokes([f], stands, site) if s[5] == tm.ROAD_KIND]
        return polyline_samples(raw, 0.5)

    def satellite(self, bridges=()):
        stands = []
        for k in range(8):
            a = np.radians(45.0 * k + 22.5)
            c = np.array([np.cos(a), np.sin(a)]) * 75.0
            stands.append(craft("narrow", float(c[0]), float(c[1]), float(-np.cos(a)), float(-np.sin(a))))
        return stands, site_of_metres([self.circle(30.0)], bridges)

    def test_a_ring_all_the_way_round_a_satellite_where_nothing_is_in_the_way(self):
        stands, site = self.satellite()
        pts = self.road_points(stands, site)
        r = np.hypot(*pts.T)
        self.assertTrue(len(pts) > 100)
        self.assertTrue(((r > 30.0 + 9.5 - 4.2) & (r < 30.0 + 9.5 + 4.2)).all(), "offset from the outline: two edges 7 m apart")
        ang = np.degrees(np.arctan2(pts[:, 1], pts[:, 0])) % 360.0
        for a in range(0, 360, 4):
            self.assertTrue((np.abs(((ang - a + 180.0) % 360.0) - 180.0) < 3.0).any(), a)        # no part of the ring is missing

    def test_a_bridge_cuts_the_ring_only_where_its_footprint_is_and_the_road_resumes(self):
        d = np.array([np.cos(np.radians(20.0)), np.sin(np.radians(20.0))])
        stands, site = self.satellite([(d * 60.0, d)])                          # (a bridge from the wall out to 60 m at 20 degrees)
        pts = self.road_points(stands, site)
        ang = np.degrees(np.arctan2(pts[:, 1], pts[:, 0])) % 360.0
        near = lambda a: (np.abs(((ang - a + 180.0) % 360.0) - 180.0) < 2.0).any()
        self.assertFalse(near(20.0), "the road stops at the bridge")
        for a in (3.0, 8.0, 32.0, 40.0, 90.0, 200.0, 340.0):
            self.assertTrue(near(a), a)                                         # (and goes on, both sides)

    def test_a_row_along_a_terminal_is_one_road_across_a_stand_that_is_too_near(self):
        xs = (-88.0, -44.0, 0.0, 44.0, 88.0)
        ys = (5.0, 5.0, -8.0, 5.0, 5.0)                                         # (the middle nose 7 m from the wall: no road of its own)
        wall = [(-300.0, -15.0), (300.0, -15.0), (300.0, -40.0), (-300.0, -40.0)]
        stands = [craft("narrow", x, y + self.NARROW[0] / 2.0, 0.0, -1.0) for x, y in zip(xs, ys)]
        pts = self.road_points(stands, site_of_metres([wall]))
        for x in range(-90, 91, 6):
            self.assertTrue((np.abs(pts[:, 0] - x) < 3.0).any(), x)             # (not broken at the stand)
        self.assertGreater(pts[:, 0].max(), 88.0)


class LeadStraight(unittest.TestCase):
    """An aircraft is lined up straight before its stop position: the lead-in's last straight along the stand's axis, ending at the stop
    bar, is at least the nose-to-main-gear distance plus a quarter of the length, and at least 20 m; the arc that joins the lane or spine
    (the radius of its kind or more) starts behind it. Where the lane is too close, the join slides along it or the spine sits further
    out: the straight is never shortened."""
    LANE = taxiway((-300, 0), (300, 0), cls="taxilane")
    EXPECT = {"light": 20.0, "turboprop": 20.0, "narrow": 26.696, "wide": 45.227}      # (0.46 + 0.25) of the length, at least 20 m

    def test_the_least_straight_run_of_each_kind(self):
        for kind, want in self.EXPECT.items():
            length = pa.SPECS[kind][0]
            self.assertAlmostEqual(tm.lead_straight(length), want, 3, kind)
            self.assertGreaterEqual(tm.lead_straight(length), tm.LEAD_STRAIGHT_MIN_M)
            self.assertAlmostEqual(tm.lead_straight(length), max(20.0, (pa.MAIN_GEAR_K - pa.NOSE_GEAR_K + 0.25) * length), 6)

    def lead_of(self, lane, stand):
        nw = tm.network([feats(lane)], [stand])
        nose = nw.stops[0][0]
        got = [x for x in nw.lines if x[1] == "lead" and float(np.hypot(*(x[0][-1] - nose))) < 0.05]
        self.assertEqual(len(got), 1, "a stand has its lead-in")
        return nw, got[0]

    def test_every_kind_lines_up_straight_before_the_stop_bar_with_an_arc_of_its_radius(self):
        for kind in self.EXPECT:
            for gap in (45.0, 30.0, 14.0):                  # (the stand's centre this far from the lane: room, little, none)
                nw, (xy, _role, _rm) = self.lead_of(self.LANE, craft(kind, 0.0, gap, 0.0, 1.0))
                self.assertGreaterEqual(tm.final_straight(xy), tm.lead_straight(pa.SPECS[kind][0]) - 0.05, (kind, gap))
                self.assertGreaterEqual(tm._min_radius(xy), tm._rmin(kind) - 0.5, (kind, gap))
                self.assertEqual(nw.short, [])

    def test_a_close_lane_slides_the_join_and_a_row_has_its_spine_pushed_out(self):
        near = craft("narrow", 0.0, 30.0, 0.0, 1.0)         # (nose 48.8 m from the lane: 26.7 m straight and a 15 m arc do not fit beside it)
        _nw, (xy, _r, _m) = self.lead_of(self.LANE, near)
        self.assertGreaterEqual(tm.final_straight(xy), tm.lead_straight(pa.SPECS["narrow"][0]) - 0.05)
        row = [craft("light", x, 5.0 + 4.15, 0.0, -1.0) for x in (-40.0, -20.0, 0.0, 20.0)]
        lane = taxiway((-250, 100), (250, 100), cls="taxilane")
        nw = tm.network([feats(lane)], row)
        self.assertEqual(nw.short, [])
        spines = [x[0] for x in nw.lines if x[1] == "spine"]
        self.assertTrue(spines)
        for nose, _u, kind in nw.stops:                     # (the spine is at least the straight run and a radius from every nose)
            gap = min(float(tm._pt_segs(nose, P[:-1], P[1:]).min()) for P in spines)
            self.assertGreaterEqual(gap, tm.lead_straight(pa.SPECS[kind][0]) + tm._rmin(kind) - 0.5)


class NetworkAudit(unittest.TestCase):
    """tm.audit: dangling ends (gaps under 8 m, ends in an open apron), kinks (along a line, and at a join that is neither tangent
    nor straight through) and S-bends tighter than the radius; the painted network of a small airport reports none."""
    NONE = {"gaps": 0, "opens": 0, "kinks": 0, "sbends": 0}

    def test_a_small_airport_reports_none(self):
        lane = taxiway((-250, 100), (250, 100), cls="taxilane")
        main = taxiway((-250, 400), (250, 400))
        link = taxiway((120, 400), (120, 100))                              # (a taxiway across the corner: a T at each end)
        row = [craft("narrow", x, 5.0 + pa.SPECS["narrow"][0] / 2.0, 0.0, -1.0) for x in (-90.0, -45.0, 0.0, 45.0)]
        row += [craft("turboprop", -10.0, 700.0, 0.0, 1.0)]                 # (a stand on the far side)
        nw = tm.network([feats(lane, main, link)], row)
        self.assertEqual(nw.audit().counts(), self.NONE)
        self.assertEqual(nw.short, [])
        self.assertEqual(len(nw.stops), len(row))

    def test_a_planted_gap_of_3_m_is_found_and_a_join_is_not(self):
        a = np.array([[0.0, 0.0], [100.0, 0.0]])
        b = np.array([[50.0, 3.0], [50.0, 60.0]])                           # ends 3 m short of a
        got = tm.audit([a, b])
        self.assertEqual(len(got.gaps), 1)
        self.assertAlmostEqual(got.gaps[0][2], 3.0, 3)
        self.assertEqual((got.gaps[0][0], got.gaps[0][1]), (50.0, 3.0))
        smooth = np.array([[100.0, 0.0], [160.0, 0.0]])                     # (a line end to end, straight on: nothing)
        self.assertEqual(len(tm.audit([a, smooth]).gaps), 0)
        far = tm.audit([a, np.array([[50.0, 12.0], [50.0, 60.0]])])
        self.assertEqual(len(far.gaps), 0)                                  # (12 m off: not a gap, an end in the open)
        self.assertIn((50.0, 12.0), [(o[0], o[1]) for o in far.opens])

    def test_ends_that_are_meant_to_stop_are_not_reported(self):
        a = np.array([[0.0, 0.0], [100.0, 0.0]])
        edge = np.array([[-5.0, -20.0], [-5.0, 20.0]])
        self.assertEqual(len(tm.audit([a]).opens), 2)                       # (a line alone: both ends in the open)
        self.assertEqual(len(tm.audit([a], stops=[(100.0, 0.0)], edges=[edge]).opens), 1)
        self.assertEqual(len(tm.audit([a], runways=[(np.array([[106.0, -50.0], [106.0, 50.0]]), 5.0)], stops=[(0.0, 0.0)]).opens), 0)
        self.assertEqual(len(tm.audit([a], aprons=[]).opens), 0)            # (not in an apron: the end of a taxiway)

    def test_a_planted_40_degree_kink_is_found_and_a_crossing_straight_through_is_not(self):
        c = np.radians(40.0)
        bent = np.array([[0.0, 0.0], [50.0, 0.0], [50.0 + 50.0 * np.cos(c), 50.0 * np.sin(c)]])
        got = tm.audit([bent])
        self.assertEqual(len(got.kinks), 1)
        self.assertAlmostEqual(got.kinks[0][2], 40.0, delta=0.5)
        self.assertEqual((round(got.kinks[0][0]), round(got.kinks[0][1])), (50, 0))
        self.assertEqual(len(tm.audit([tm._round_arcs(bent, tm.MIN_RADIUS_M)]).kinks), 0)       # (the same corner as an arc of the radius)
        across = [np.array([[0.0, 0.0], [100.0, 0.0]]), np.array([[50.0, -40.0], [50.0, 0.0]]), np.array([[50.0, 0.0], [50.0, 40.0]])]
        self.assertEqual(len(tm.audit(across).kinks), 0)                    # (one line straight across another, the other split there)
        self.assertEqual(len(tm.audit([across[0], across[2]]).kinks), 1)    # (a T that is neither tangent nor across)
        fork = [across[0], np.array([[50.0, 0.0], [90.0, 8.0]])]            # (a branch leaving 11 degrees off the line: tangent)
        self.assertEqual(len(tm.audit(fork).kinks), 0)

    def test_an_s_bend_tighter_than_the_radius_is_found(self):
        def s_curve(r, turn):                                               # a circular arc of radius r to the left, then one to the right
            t = np.linspace(0.0, turn, 40)
            left = np.stack([r * np.sin(t), r * (1.0 - np.cos(t))], 1)
            end, th = left[-1], turn
            right = np.stack([end[0] + r * (np.sin(th) - np.sin(th - t)), end[1] + r * (np.cos(th - t) - np.cos(th))], 1)
            return np.vstack([left, right[1:]])
        got = tm.audit([s_curve(8.0, 0.8)], rmin=15.0)
        self.assertEqual(len(got.sbends), 1)
        self.assertLess(got.sbends[0][2], 15.0)
        self.assertEqual(len(tm.audit([s_curve(40.0, 0.6)], rmin=15.0).sbends), 0)
        self.assertEqual(len(tm.audit([s_curve(8.0, 0.8)], rmin=8.0).sbends), 0)       # (the radius of a light aircraft: not tight)


if __name__ == "__main__":
    unittest.main()
