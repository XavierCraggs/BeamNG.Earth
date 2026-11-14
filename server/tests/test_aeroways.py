"""aeroways: an airport's aprons and taxiways as paved pads (GitHub #607), kept off unpaved ones, widened by the width
tag and by an international airport, and painted through surface.paint_lots / lot_pads like the parking lots; the
Features of anywhere else give nothing and change no paint."""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import aeroways  # noqa: E402
import geodesy  # noqa: E402
import mapgeom  # noqa: E402
import polygon  # noqa: E402
import surface as sf  # noqa: E402

FRAME = geodesy.EnuFrame(40.0, -76.0)


def lonlat(e, n):
    la, lo, _ = FRAME.enu_to_geodetic(np.asarray(e, np.float64), np.asarray(n, np.float64), 0.0)
    return np.stack([lo, la], 1)


def line(*pts):
    return (mapgeom.LINE, [[lonlat([p[0] for p in pts], [p[1] for p in pts])]])


def poly(*pts):
    pts = list(pts) + [pts[0]]
    return (mapgeom.POLYGON, [[lonlat([p[0] for p in pts], [p[1] for p in pts])]])


def feats(*rows):
    """Infrastructure Features of (geometry, class, subtype, tags dict, surface) rows."""
    ids = np.array([f"f{i:03d}" for i in range(len(rows))])
    f = mapgeom.build("infrastructure", ids, [r[0] for r in rows])
    f.attrs = {"class": mapgeom.text_column([r[1] for r in rows]),
               "subtype": mapgeom.text_column([r[2] for r in rows]),
               "tags": mapgeom.text_column([json.dumps(r[3]) for r in rows]),
               "surface": mapgeom.text_column([r[4] for r in rows])}
    return f


def taxiway(*pts, tags=None, surface=None, cls="taxiway"):
    return (line(*pts), cls, "airport", tags or {}, surface)


def intl_field():
    return (poly((-900, -900), (900, -900), (900, 900), (-900, 900)), "international_airport", "airport", {}, None)


def covered(pad_list, e, n):
    """Is the point (e, n) m east / north of the frame's origin inside any of the pads?"""
    la, lo, _ = FRAME.enu_to_geodetic(np.array([float(e)]), np.array([float(n)]), 0.0)
    for pla, plo in pad_list:
        ring = np.stack([plo, pla], 1)
        if polygon.contains_points(ring, np.array([[lo[0], la[0]]]))[0]:
            return True
    return False


class Pads(unittest.TestCase):
    def test_apron_gives_its_outer_ring(self):
        f = feats((poly((0, 0), (100, 0), (100, 60), (0, 60)), "apron", "airport", {"aeroway": "apron"}, None))
        got = aeroways.pads([f])
        self.assertEqual(len(got), 1)
        self.assertTrue(covered(got, 50, 30))
        self.assertFalse(covered(got, 150, 30))

    def test_taxiway_covers_its_line_and_half_width_only(self):
        f = feats(taxiway((0, 0), (200, 0), (200, 150)))
        got = aeroways.pads([f])
        width = aeroways.TAXIWAY_M
        for e, n in ((0, 0), (100, 0), (200, 0), (200, 75), (200, 150), (100, width * 0.45), (100, -width * 0.45),
                     (200 + width * 0.45, 75)):
            self.assertTrue(covered(got, e, n), (e, n))
        for e, n in ((100, 2 * width), (100, -2 * width), (200 + 2 * width, 75), (300, 0), (-3 * width, 0)):
            self.assertFalse(covered(got, e, n), (e, n))

    def test_bend_has_no_gap_on_its_outside(self):
        f = feats(taxiway((0, 0), (100, 0), (100, 100)))
        got = aeroways.pads([f])
        h = aeroways.TAXIWAY_M / 2
        self.assertTrue(covered(got, 100 + h * 0.9, -h * 0.5), "the outer corner is joined, not notched")

    def test_width_tag_widens_it(self):
        base = aeroways.pads([feats(taxiway((0, 0), (200, 0)))])
        wide_tag = {"width": "40"}
        wide = aeroways.pads([feats(taxiway((0, 0), (200, 0), tags=wide_tag))])
        y = (aeroways.TAXIWAY_M / 2 + 40 / 2) / 2           # (between the two half widths)
        self.assertFalse(covered(base, 100, y))
        self.assertTrue(covered(wide, 100, y))
        self.assertFalse(covered(wide, 100, 40 / 2 + 6))

    def test_width_tag_reads(self):
        self.assertEqual(aeroways.width_tag("23"), 23.0)
        self.assertEqual(aeroways.width_tag("23 m"), 23.0)
        self.assertEqual(aeroways.width_tag("23,5m"), 23.5)
        self.assertAlmostEqual(aeroways.width_tag("75 ft"), 22.86)
        for bad in (None, "", "wide", "2300", "0", "-5", "23 km"):
            self.assertIsNone(aeroways.width_tag(bad), bad)

    def test_unreadable_width_tag_falls_to_the_default(self):
        got = aeroways.pads([feats(taxiway((0, 0), (200, 0), tags={"width": "wide"}))])
        self.assertTrue(covered(got, 100, aeroways.TAXIWAY_M * 0.45))
        self.assertFalse(covered(got, 100, aeroways.TAXIWAY_M * 1.5))

    def test_taxilane_is_narrower_than_a_taxiway(self):
        lane = aeroways.pads([feats(taxiway((0, 0), (200, 0), cls="taxilane"))])
        way = aeroways.pads([feats(taxiway((0, 0), (200, 0)))])
        y = (aeroways.TAXILANE_M / 2 + aeroways.TAXIWAY_M / 2) / 2
        self.assertTrue(covered(lane, 100, 0))
        self.assertFalse(covered(lane, 100, y))
        self.assertTrue(covered(way, 100, y))

    def test_unpaved_ones_give_nothing(self):
        for surface in ("grass", "dirt", "gravel", "ground", "sand", "unpaved", "earth", "compacted", "fine_gravel",
                        "Grass"):
            self.assertEqual(aeroways.pads([feats(taxiway((0, 0), (200, 0), surface=surface))]), [], surface)
        self.assertEqual(aeroways.pads([feats(taxiway((0, 0), (200, 0), tags={"surface": "grass"}))]), [])
        self.assertEqual(aeroways.pads([feats((poly((0, 0), (100, 0), (100, 60)), "apron", "airport", {}, "gravel"))]),
                         [])
        self.assertTrue(aeroways.pads([feats(taxiway((0, 0), (200, 0), surface="asphalt"))]), "paved: kept")
        self.assertTrue(aeroways.pads([feats(taxiway((0, 0), (200, 0), tags={"surface": "concrete"}))]))

    def test_international_airport_widens_the_defaults(self):
        plain = aeroways.pads([feats(taxiway((0, 0), (200, 0)))])
        intl = aeroways.pads([feats(taxiway((0, 0), (200, 0)), intl_field())])
        y = (aeroways.TAXIWAY_M / 2 + aeroways.TAXIWAY_INTL_M / 2) / 2
        self.assertFalse(covered(plain, 100, y))
        self.assertTrue(covered(intl, 100, y))
        regional = (poly((-900, -900), (900, -900), (900, 900)), "regional_airport", "airport", {}, None)
        self.assertFalse(covered(aeroways.pads([feats(taxiway((0, 0), (200, 0)), regional)]), 100, y))
        lane = aeroways.pads([feats(taxiway((0, 0), (200, 0), cls="taxilane"), intl_field())])
        self.assertTrue(covered(lane, 100, (aeroways.TAXILANE_M / 2 + aeroways.TAXILANE_INTL_M / 2) / 2))

    def test_a_tag_width_beats_the_airport_default(self):
        got = aeroways.pads([feats(taxiway((0, 0), (200, 0), tags={"width": "12"}), intl_field())])
        self.assertFalse(covered(got, 100, 12 / 2 + 2))

    def test_only_airport_subtype_counts(self):
        f = feats((line((0, 0), (200, 0)), "taxiway", "recreation", {}, None),
                  (poly((0, 0), (50, 0), (50, 50)), "apron", "transit", {}, None),
                  (line((0, 0), (200, 0)), "service", "airport", {}, None))
        self.assertEqual(aeroways.pads([f]), [])

    def test_no_airport_features_give_nothing(self):
        lot = feats((poly((0, 0), (50, 0), (50, 50)), "parking", "transit", {}, None))
        self.assertEqual(aeroways.pads([lot]), [])
        self.assertEqual(aeroways.pads([None, mapgeom.empty("infrastructure")]), [])
        bare = feats(taxiway((0, 0), (10, 0)))
        bare.attrs.pop("subtype")
        self.assertEqual(aeroways.pads([bare]), [], "no subtype column")

    def test_kept_on_the_features(self):
        f = feats(taxiway((0, 0), (200, 0)))
        first = aeroways.pads([f])
        self.assertTrue(first)
        f.lonlat = f.lonlat + 1.0           # (what is kept is read, not built again)
        again = aeroways.pads([f])
        self.assertEqual(len(again), len(first))
        for a, b in zip(first, again):
            self.assertTrue(np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1]))

    def test_shallow_crossing_of_a_runway_is_filleted(self):
        # a taxiway crossing a runway at 25 degrees in one piece: the acute wedge between its edge and the runway's is
        # paved (Brisbane's dirt triangles), the obtuse side's grass is not, and a way along the runway gets no fillet
        a = np.radians(25.0)
        rw = (line((-500, 0), (500, 0)), "runway", "airport", {"width": "45"}, None)
        tw = taxiway((-300 * np.cos(a), -300 * np.sin(a)), (0, 0), (300 * np.cos(a), 300 * np.sin(a)))   # (OSM: a shared node)
        pads = aeroways.pads([feats(rw, tw)])
        self.assertTrue(covered(pads, 75, 24))
        self.assertFalse(covered(pads, -60, 30))
        along = aeroways.pads([feats(rw, taxiway((-200, 5), (200, 5)))])
        self.assertFalse(covered(along, 0, 25))

    def test_runway_and_stopway_lines_end_square_taxiways_keep_the_octagon(self):
        # the octagon's cap stuck out past a runway's end into the grass (Heathrow 27R): a runway or stopway line is
        # paved flat to its end, a taxiway's end still has its octagon, and a runway's sharp bend keeps its join
        for cls in ("runway", "stopway"):
            rw = (line((-500, 0), (500, 0)), cls, "airport", {"width": "45"}, None)
            pads = aeroways.pads([feats(rw, taxiway((0, 400), (50, 400)))])      # (a runway is paved with the ways)
            self.assertTrue(covered(pads, 499, 20), cls)
            self.assertFalse(covered(pads, 505, 0), cls)
            self.assertFalse(covered(pads, -505, 0), cls)
            self.assertFalse(covered(pads, 505, 20), cls)
        tw = aeroways.pads([feats(taxiway((-200, 0), (200, 0), tags={"width": "30"}))])
        self.assertTrue(covered(tw, 205, 0))
        bend = (line((-300, 0), (0, 0), (0, 300)), "runway", "airport", {"width": "45"}, None)
        pads = aeroways.pads([feats(bend, taxiway((600, 600), (650, 600)))])
        self.assertTrue(covered(pads, 12, -12))
        self.assertFalse(covered(pads, 0, 305))

    def test_degenerate_lines_are_skipped(self):
        got = aeroways.pads([feats(taxiway((0, 0), (0, 0)), taxiway((5, 5), (5, 5), (60, 5)))])
        self.assertTrue(covered(got, 30, 5))
        for la, lo in got:
            self.assertTrue(np.isfinite(la).all() and np.isfinite(lo).all())


class Painted(unittest.TestCase):
    def grid(self):
        e, n = np.meshgrid(np.arange(-100.0, 100.0, 2.0), np.arange(-100.0, 100.0, 2.0))
        la, lo, _ = FRAME.enu_to_geodetic(e, n, 0.0)
        return la, lo, e, n

    def test_ground_and_photo_paint_a_taxiway(self):
        la, lo, e, n = self.grid()
        f = feats(taxiway((-80, 0), (80, 0)))
        idx = np.full(la.shape, sf.DIRT, np.uint8)
        out = sf.paint_lots(idx, la, lo, [f])
        on = (np.abs(n) < 4) & (np.abs(e) < 60)
        self.assertTrue((out[on] == sf.ASPHALT).all())
        self.assertTrue((out[np.abs(n) > 30] == sf.DIRT).all())
        self.assertTrue((idx == sf.DIRT).all(), "the input untouched")
        rgb = np.full((64, 64, 3), 30, np.uint8)
        photo = sf.photo_lots(rgb, FRAME, -32.0, -32.0, 64.0, [feats(taxiway((-30, 0), (30, 0)))])
        self.assertGreater(int(photo[32, 32, 0]), 60, "the taxiway painted in the photo")
        self.assertEqual(int(photo[2, 2, 0]), 30)
        mask = sf.lots_mask(FRAME, -32.0, -32.0, 64.0, 64, [feats(taxiway((-30, 0), (30, 0)))])
        self.assertEqual(int(mask[32, 32]), 255, "and in the near tiles' asphalt mask")
        self.assertEqual(int(mask[2, 2]), 0)

    def test_nothing_changes_without_an_airport(self):
        la, lo, e, n = self.grid()
        lot = feats((poly((-20, -20), (20, -20), (20, 20), (-20, 20)), "parking", "transit", {}, None),
                    (line((-80, 0), (80, 0)), "taxiway", "recreation", {}, None))
        idx = np.full(la.shape, sf.GRASS, np.uint8)
        with_it = sf.paint_lots(idx, la, lo, [lot])
        real = aeroways.pads
        aeroways.pads = lambda feats_list: []
        try:
            without = sf.paint_lots(idx, la, lo, [lot])
            lots_without = sf.lot_pads([lot])
        finally:
            aeroways.pads = real
        self.assertTrue(np.array_equal(with_it, without))
        self.assertEqual(len(sf.lot_pads([lot])), len(lots_without))
        self.assertTrue((with_it == sf.ASPHALT).any(), "the lot still painted")
        self.assertIs(sf.paint_lots(idx, la, lo, [None]), idx)


class ApronPhoto(unittest.TestCase):
    """Brisbane's international apron: a taxiway across it a darker band, a pale haze past the paving onto the grass."""
    GRASS, CONCRETE, ASPHALT = (70, 110, 50), (185, 183, 178), (95, 95, 95)

    def scene(self):
        apron = (poly((-60, -60), (60, -60), (60, 60), (-60, 60)), "apron", "airport", {}, None)
        f = feats(intl_field(), apron, taxiway((-90, -20), (90, 20)))
        px, size = 256, 256.0
        e, n = np.meshgrid((np.arange(px) + 0.5) * size / px - 128, 128 - (np.arange(px) + 0.5) * size / px)
        inside = (np.abs(e) < 62) & (np.abs(n) < 62)
        lane = np.abs(n - 20 * e / 90) * np.cos(np.arctan(20 / 90)) < 11.5           # (the lane's 23 m, as the photo has it)
        rgb = np.empty((px, px, 3), np.uint8)
        rgb[:] = self.GRASS
        rgb[inside] = self.CONCRETE
        rgb[lane & (np.abs(e) < 90)] = self.ASPHALT         # (the aerial's real asphalt lane, across the apron and past it)
        rgb[lane & ~inside] = self.GRASS                    # ... where the lane runs over grass in the photo
        return f, rgb, inside, lane

    def test_ways_and_aprons_are_told_apart(self):
        f, _, _, _ = self.scene()
        self.assertEqual(len(aeroways.aprons([f])), 1)
        self.assertGreaterEqual(len(aeroways.ways([f])), 1)
        self.assertEqual(len(aeroways.aprons([f])) + len(aeroways.ways([f])), len(aeroways.pads([f], runways=False)))
        self.assertEqual(aeroways.aprons([None]), [])
        self.assertEqual(aeroways.ways([feats(taxiway((-30, 0), (30, 0), surface="grass"))]), [])

    def test_a_taxiway_across_an_apron_takes_the_aprons_tone(self):
        f, rgb, inside, lane = self.scene()
        was = sf.photo_pads(rgb, FRAME, -128.0, -128.0, 256.0, sf.lot_pads([f]))
        out = sf.photo_lots(rgb, FRAME, -128.0, -128.0, 256.0, [f])
        band, rest = inside & lane, inside & ~lane
        self.assertGreater(abs(float(was[band].mean()) - float(was[rest].mean())), 40.0, "(the band the aerial had)")
        self.assertLess(abs(float(np.median(out[band])) - float(np.median(out[rest]))), 3.0, "one surface")
        self.assertLess(float(out[band].std()), 8.0, "(a few joints, no asphalt band)")
        self.assertTrue((rgb == np.where(inside[..., None] & lane[..., None], np.array(self.ASPHALT, np.uint8),
                                         rgb)).all(), "the photo itself untouched")

    def test_the_grass_the_photo_shows_is_not_painted_over(self):
        f, rgb, inside, lane = self.scene()
        was = sf.photo_pads(rgb, FRAME, -128.0, -128.0, 256.0, sf.lot_pads([f]))
        out = sf.photo_lots(rgb, FRAME, -128.0, -128.0, 256.0, [f])
        cols = np.arange(256)[None, :] - 128
        grass = ~inside & lane & (np.abs(cols) > 66)           # (the lane's overshoot past the apron's edge)
        mown = sf._infield_grass(rgb, FRAME, -128.0, -128.0, 256.0, [f])      # (the infield's own pull to a mown green)
        self.assertGreater(int((was[grass] != rgb[grass]).any(axis=1).sum()), 100, "(painted before)")
        self.assertLessEqual(int((out[grass] != mown[grass]).any(axis=1).sum()), 4, "(the pad's overshoot left as grass)")
        core = ~lane & (np.abs(cols) < 56) & (np.abs(np.arange(256)[:, None] - 128) < 56)
        self.assertTrue((out[core] != rgb[core]).any(axis=1).all(), "the paving still painted")

    def test_parking_lots_are_painted_as_before(self):
        lot = feats((poly((-20, -20), (20, -20), (20, 20), (-20, 20)), "parking", "transit", {}, None))
        rgb = np.full((64, 64, 3), (70, 110, 50), np.uint8)       # (a lot over grass: still painted, no airport near)
        got = sf.photo_lots(rgb, FRAME, -32.0, -32.0, 64.0, [lot])
        self.assertTrue(np.array_equal(got, sf.photo_pads(rgb, FRAME, -32.0, -32.0, 64.0, sf.lot_pads([lot]))))
        self.assertTrue((got[32, 32] != rgb[32, 32]).any())


def point(e, n):
    return (mapgeom.POINT, [[lonlat([e], [n])]])


class Boundaries(unittest.TestCase):
    """The airport's boundary for the infield (aeroways.boundaries) and the gates (aeroways.gates)."""

    def inside(self, ring_list, e, n):
        return covered(ring_list, e, n)

    def test_the_aerodrome_polygon_is_the_boundary(self):
        f = feats(intl_field(), (poly((0, 0), (100, 0), (100, 60), (0, 60)), "apron", "airport", {}, None))
        got = aeroways.boundaries([f])
        self.assertEqual(len(got), 1)
        self.assertTrue(self.inside(got, 800, 800))
        self.assertFalse(self.inside(got, 1000, 0))

    def test_other_aerodrome_classes_count_but_not_a_heliport_or_a_closed_field(self):
        box = poly((-300, -300), (300, -300), (300, 300), (-300, 300))
        for cls, n in (("airport", 1), ("regional_airport", 1), ("military_airfield", 1), ("private_airstrip", 1),
                       ("heliport", 0), ("seaplane_base", 0), ("closed_airport", 0), ("runway", 0)):
            f = feats((box, cls, "airport", {}, None))
            self.assertEqual(len(aeroways.boundaries([f])), n, cls)
        self.assertEqual(aeroways.boundaries([feats((box, "airport", "recreation", {}, None))]), [])

    def test_without_a_polygon_the_pads_hull_grown_150_m(self):
        f = feats(taxiway((0, 0), (400, 0)),
                  (poly((100, 100), (300, 100), (300, 200), (100, 200)), "apron", "airport", {}, None))
        got = aeroways.boundaries([f])
        self.assertEqual(len(got), 1)
        for e, n in ((200, 150), (0, 0), (400, 0), (-100, 0), (200, 330), (200, -100)):
            self.assertTrue(self.inside(got, e, n), (e, n))
        for e, n in ((-200, 0), (600, 0), (200, 400), (200, -200), (900, 900)):
            self.assertFalse(self.inside(got, e, n), (e, n))
        self.assertEqual(len(aeroways.boundaries([f])), 1, "kept: the same again")

    def test_none_for_anywhere_else(self):
        lot = feats((poly((-20, -20), (20, -20), (20, 20), (-20, 20)), "parking", "transit", {}, None))
        self.assertEqual(aeroways.boundaries([lot, None]), [])
        self.assertEqual(aeroways.gates([lot, None]), [])

    def test_gates_are_the_gate_and_parking_position_points(self):
        f = feats((point(5, 6), "airport_gate", "airport", {}, None),
                  (point(30, 6), "parking_position", "airport", {}, None),
                  (point(50, 6), "other", "airport", {"aeroway": "gate"}, None),
                  (point(70, 6), "other", "airport", {}, None),
                  (point(90, 6), "airport_gate", "recreation", {}, None))
        got = aeroways.gates([f])
        self.assertEqual(len(got), 3)
        la, lo, _ = FRAME.enu_to_geodetic(np.array([5.0, 30.0, 50.0]), np.array([6.0, 6.0, 6.0]), 0.0)
        for (a, b), x, y in zip(got, la, lo):
            self.assertAlmostEqual(a, float(x), 9)
            self.assertAlmostEqual(b, float(y), 9)


if __name__ == "__main__":
    unittest.main()


class RoadEdges(unittest.TestCase):
    def test_edge_strip_stops_on_the_pavement(self):
        # a service road crossing an apron: its edge strip (gravel / grass decal) is cut where it lies on the paving
        import roads
        fr = geodesy.EnuFrame(-27.0, 153.0)
        la, lo, _ = fr.enu_to_geodetic(np.array([-10.0, 10, 10, -10]), np.array([-10.0, -10, 10, 10]), np.zeros(4))
        pads = roads._pads_xy(fr, [(np.asarray(la), np.asarray(lo))], (-50, -50, 50, 50))
        pieces = roads.cut_in_pads(np.array([[-40.0, 0, 0], [40.0, 0, 0]]), pads)
        self.assertEqual(len(pieces), 2)
        self.assertTrue(all(abs(p[:, 0]).min() >= 9.0 for p in pieces))
        self.assertEqual(len(roads.cut_in_pads(np.array([[-40.0, 30, 0], [40.0, 30, 0]]), pads)), 1)
