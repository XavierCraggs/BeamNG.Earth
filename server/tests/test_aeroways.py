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
