"""airportbuildings: a control tower mapped as one footprint (named, or slender and tall by an apron) is drawn as a
concrete shaft, a glass cab and a dark cap; a terminal is told by the gate points at its outline (or its name) and takes
the terminal look at a height by its size; a building with parts of its own, and every building off an airport, is left
as it was."""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import airportbuildings as ab  # noqa: E402
import buildings as bld  # noqa: E402
import geodesy  # noqa: E402
import mapgeom  # noqa: E402

FRAME = geodesy.EnuFrame(-27.39, 153.118)
BOX = (0.0, 0.0, 256.0, 256.0)
ELEV = lambda la, lo: np.zeros(np.shape(la))        # noqa: E731
_IDS = iter(range(10 ** 6))


def lonlat(pts):
    la, lo, _ = FRAME.enu_to_geodetic(np.array([p[0] for p in pts], np.float64),
                                      np.array([p[1] for p in pts], np.float64), 0.0)
    return np.stack([lo, la], 1)


def rect(x, y, w, d):
    return [(x, y), (x + w, y), (x + w, y + d), (x, y + d), (x, y)]


class Feats:
    """Buildings (or parts) layer: rings in metres east / north of the frame's origin, attributes by column."""

    def __init__(self, ids, rings, **attrs):
        self.ids = np.array(ids, object)
        self.kind = np.full(len(ids), 3, np.uint8)
        self.rings = [lonlat(r) for r in rings]
        self.attrs = {k: np.array(v, object if isinstance(v[0], str) else np.float64) for k, v in attrs.items()}

    def parts(self, i):
        return [[self.rings[i]]]


def building(ring, **at):
    n = {"class": "", "height": np.nan, "num_floors": np.nan, "min_height": np.nan, "name": "", "has_parts": 0.0}
    n.update({k: v for k, v in at.items() if v is not None})
    return Feats(["b%d" % next(_IDS)], [ring], **{k: [v] for k, v in n.items()})


def infra(*rows):
    """Infrastructure Features of (kind, points, class[, subtype]) rows, subtype airport by default; points as lines / rings / one point."""
    base = next(_IDS)
    ids = np.array([f"{base:06d}{i:03d}" for i in range(len(rows))])
    geoms = [(r[0], [[lonlat(r[1])]]) for r in rows]
    f = mapgeom.build("infrastructure", ids, geoms)
    f.attrs = {"class": mapgeom.text_column([r[2] for r in rows]),
               "subtype": mapgeom.text_column([r[3] if len(r) > 3 else "airport" for r in rows]),
               "tags": mapgeom.text_column(["{}"] * len(rows)), "name": mapgeom.text_column([""] * len(rows)),
               "surface": mapgeom.text_column([None] * len(rows))}
    return f


def apron(x, y, w, d):
    return (mapgeom.POLYGON, rect(x, y, w, d), "apron")


def gate(x, y):
    return (mapgeom.POINT, [(x, y)], "airport_gate")


FIELD = (mapgeom.POLYGON, rect(-900, -900, 1800, 1800), "international_airport")


def items(layer, infra_layer=None, parts=(), airport=True):
    ctx = ab.context(FRAME, [infra_layer], *BOX[:2]) if airport and infra_layer is not None else None
    return bld.tile_buildings(FRAME, *BOX, [layer], ELEV, part_layers=list(parts), airport=ctx)


def tops(its):
    return sorted((round(s.min_h or 0.0, 2), round(s.height, 2)) for s, _, _ in its)


def material(spec):
    return spec.facade.split("|")[0]


class TowerTest(unittest.TestCase):
    def test_a_named_tower_with_no_parts(self):
        """Brisbane's "Air Traffic Control Tower": 75 m, 219 m2, one footprint, no parts: a shaft, a cab and a cap."""
        b = building(rect(100, 100, 15, 14.6), name="Brisbane Airport - Air Traffic Control Tower", height=75.0)
        its = items(b, infra(FIELD, apron(0, 0, 90, 90)))
        self.assertEqual(len(its), 3)
        self.assertEqual(tops(its), [(0.0, 66.0), (66.0, 5.0), (71.0, 4.0)], "shaft to h-9, cab to h-4, cap to h")
        shaft, cab, cap = sorted((s for s, _, _ in its), key=lambda s: s.min_h)
        areas = [abs(bld._area2(s.ring)) / 2 for s in (shaft, cab, cap)]
        self.assertAlmostEqual(areas[0] / areas[1], ab.SHAFT_SHARE ** 2, delta=0.02, msg="the footprint shrunk to 55 %")
        self.assertAlmostEqual(areas[2] / areas[1], ab.CAP_SHARE ** 2, delta=0.02, msg="the cap a little smaller")
        self.assertEqual(material(cab), bld.OFFICE, "a glass cab")
        self.assertEqual(material(shaft), bld.CONCRETE)
        self.assertNotEqual(shaft.cls, "mast", "(66 m2 and 66 m tall: a mast by the slenderness rule)")
        self.assertFalse(shaft.windows)
        self.assertEqual(len({s.seed for s, _, _ in its}), 1, "one look")
        P = bld.build(its)[0]
        self.assertAlmostEqual(float(P[:, 2].max()), 75.0, delta=0.3, msg="to the mapped height (a flat roof's lip), no plant above")
        self.assertGreater(len(bld.build(its, lite=True)[0]), 0)

    def test_a_name_without_an_airport_context_is_left(self):
        b = building(rect(100, 100, 15, 14.6), name="Air Traffic Control Tower", height=75.0)
        self.assertEqual(len(items(b, None)), 1)
        self.assertEqual(len(items(b, infra((mapgeom.POLYGON, rect(0, 0, 9, 9), "parking", "transportation")))), 1)

    def test_a_height_by_the_airport_when_missing(self):
        b = building(rect(100, 100, 15, 15), name="Control Tower")
        self.assertEqual(tops(items(b, infra(FIELD, apron(0, 0, 90, 90))))[-1], (36.0, 4.0), "international: 40 m")
        small = infra((mapgeom.POLYGON, rect(-900, -900, 1800, 1800), "regional_airport"), apron(0, 0, 90, 90))
        self.assertEqual(tops(items(building(rect(100, 100, 15, 15), name="Control Tower"), small))[-1], (21.0, 4.0),
                         "elsewhere: 25 m")

    def test_a_tower_word_needs_an_airport_word(self):
        pads = infra(FIELD, apron(0, 0, 90, 90))
        self.assertEqual(len(items(building(rect(100, 100, 15, 15), name="Clock Tower Airport Hotel"), pads)), 1)
        self.assertEqual(len(items(building(rect(100, 100, 15, 15), name="Landmark Tower"), pads)), 1)
        self.assertEqual(len(items(building(rect(100, 100, 15, 15), name="Airport Tower", height=40.0), pads)), 3)

    def test_a_slender_unnamed_tower_by_an_apron(self):
        pads = infra(FIELD, apron(0, 0, 90, 90))
        its = items(building(rect(120, 120, 12, 12), height=32.0), pads)
        self.assertEqual(tops(its), [(0.0, 23.0), (23.0, 5.0), (28.0, 4.0)])
        self.assertEqual(len(items(building(rect(120, 120, 12, 12), num_floors=8.0), pads)), 3, "or its floors")

    def test_a_small_footprint_gets_an_octagonal_cab(self):
        its = items(building(rect(120, 120, 7, 7), height=30.0), infra(FIELD, apron(0, 0, 90, 90)))
        shaft, cab, cap = sorted((s for s, _, _ in its), key=lambda s: s.min_h)
        self.assertEqual(len(cab.ring), 8, "a regular octagon")
        across = np.ptp(cab.ring[:, 0]), np.ptp(cab.ring[:, 1])
        self.assertGreaterEqual(min(across), ab.CAB_SMALL_M - 0.5, "at least 10 m across")
        self.assertGreaterEqual(min(np.ptp(shaft.ring[:, 0]), np.ptp(shaft.ring[:, 1])), ab.SHAFT_MIN_M - 0.1)

    def test_not_a_tower(self):
        pads = infra(FIELD, apron(0, 0, 90, 90))
        for what, b in (("low", building(rect(120, 120, 12, 12), height=12.0)),
                        ("wide", building(rect(120, 120, 40, 40), height=30.0)),
                        ("long", building(rect(120, 120, 60, 8), height=30.0)),
                        ("a hotel", building(rect(120, 120, 12, 12), height=32.0, **{"class": "hotel"})),
                        ("far from a pad", building(rect(20, 20, 12, 12), height=32.0)),
                        ("raised", building(rect(120, 120, 12, 12), height=32.0, min_height=10.0))):
            far = infra(FIELD, apron(-2500, -2500, 90, 90)) if what == "far from a pad" else pads
            self.assertEqual(len(items(b, far)), 1, what)

    def test_a_building_with_parts_is_left_alone(self):
        """Heathrow's tower: a stack of OSM parts (has_parts), drawn from them as before, whatever its name."""
        b = building(rect(100, 100, 15, 15), name="Heathrow Airport Control Tower", height=87.0, has_parts=1.0)
        key = b.ids[0]
        parts = Feats(["p1", "p2"], [rect(100, 100, 15, 15), rect(104, 104, 7, 7)], building_id=[key, key],
                      height=[20.0, 87.0], min_height=[np.nan, 40.0], num_floors=[np.nan, np.nan],
                      min_floor=[np.nan, np.nan])
        pads = infra(FIELD, apron(0, 0, 90, 90))
        with_ctx, without = items(b, pads, [parts]), items(b, pads, [parts], airport=False)
        self.assertEqual(len(with_ctx), 2)
        self.assertEqual(tops(with_ctx), tops(without))
        self.assertEqual([s.facade for s, _, _ in with_ctx], [s.facade for s, _, _ in without])
        flagged = building(rect(100, 100, 15, 15), name="Control Tower", height=60.0, has_parts=1.0)
        self.assertEqual(len(items(flagged, pads)), 1, "(has_parts and its parts not loaded: not synthesised over)")


class TerminalTest(unittest.TestCase):
    def terminal(self, w=80, d=40, gates=((20, 98), (40, 98), (60, 98)), **at):
        b = building(rect(100, 100, w, d), **at)
        return items(b, infra(FIELD, apron(0, 0, 90, 90), *[gate(*g) for g in gates]))

    def test_two_gates_at_the_outline_make_a_terminal(self):
        (spec, _, _), = self.terminal(name="Bozeman Yellowstone Intl. Airport (BZN)", gates=((120, 98), (150, 98)))
        self.assertEqual(spec.facade, bld.OFFICE, "the terminal look")
        self.assertAlmostEqual(spec.height, float(np.clip(8 + np.sqrt(3200) / 12, 12, 20)), places=3)
        self.assertEqual(spec.floors, 2)

    def test_the_height_by_its_size(self):
        (huge, _, _), = self.terminal(w=300, d=120, gates=((200, 98), (250, 98)))
        self.assertAlmostEqual(huge.height, 20.0, places=3, msg="clamped")
        self.assertEqual(huge.floors, 3)
        (mid, _, _), = self.terminal(w=100, d=40, gates=((120, 98), (150, 98)))
        self.assertTrue(12.0 < mid.height < 20.0)

    def test_one_gate_or_far_gates_or_a_small_building_are_not(self):
        (one, _, _), = self.terminal(gates=((120, 98),))
        self.assertNotEqual(one.facade, bld.OFFICE)
        (far, _, _), = self.terminal(gates=((120, 20), (150, 20)))
        self.assertNotEqual(far.facade, bld.OFFICE)
        (small, _, _), = self.terminal(w=30, d=30, gates=((110, 98), (120, 98)))
        self.assertNotEqual(small.facade, bld.OFFICE, "under 1500 m2")
        (hangar, _, _), = self.terminal(name="Hangar 4", gates=((120, 98), (150, 98)))
        self.assertNotEqual(hangar.facade, bld.OFFICE)

    def test_a_named_terminal_at_an_airport_takes_the_new_height_elsewhere_the_old(self):
        at_airport, = items(building(rect(100, 100, 60, 30), name="Terminal 1"), infra(FIELD, apron(0, 0, 90, 90)))
        self.assertAlmostEqual(at_airport[0].height, float(np.clip(8 + np.sqrt(1800) / 12, 12, 20)), places=3)
        elsewhere, = items(building(rect(100, 100, 60, 30), name="Terminal 1"), None)
        self.assertEqual((elsewhere[0].height, elsewhere[0].floors), (13.0, 2), "(not at an airport: as before)")

    def test_a_mapped_height_is_kept(self):
        (spec, _, _), = self.terminal(height=9.0, gates=((120, 98), (150, 98)))
        self.assertEqual(spec.facade, bld.OFFICE)
        self.assertAlmostEqual(spec.height, 9.0, places=3)


class UnchangedTest(unittest.TestCase):
    def snapshot(self, its):
        return [(s.ring.tolist(), s.height, s.min_h, s.floors, s.facade, s.roof, s.roof_mat, s.windows) for s, _, _ in its]

    def test_buildings_off_an_airport_come_out_the_same(self):
        rows = [rect(20, 20, 12, 12), rect(60, 20, 90, 40), rect(20, 80, 10, 10), rect(200, 200, 15, 15)]
        ats = [dict(height=32.0), dict(), dict(), dict(name="Bus Terminal")]
        layer = Feats([f"b{k}" for k in range(len(rows))], rows, **{k: [a.get(k, d) for a in ats] for k, d in (
            ("class", ""), ("height", np.nan), ("num_floors", np.nan), ("min_height", np.nan), ("name", ""),
            ("has_parts", 0.0))})
        base = self.snapshot(bld.tile_buildings(FRAME, *BOX, [layer], ELEV))
        # (no airport in the cells: no context, nothing asked of the buildings)
        self.assertIsNone(ab.context(FRAME, [infra((mapgeom.POLYGON, rect(0, 0, 9, 9), "parking", "transportation")), None], 0, 0))
        self.assertEqual(base, self.snapshot(bld.tile_buildings(FRAME, *BOX, [layer], ELEV, airport=None)))
        # (an airport 2 km off, its pads and gates there: a slender tower, a hall and a house away from them are as
        # they were; a name's terminal is a terminal wherever it stands in an airport's cells)
        far = ab.context(FRAME, [infra(FIELD, apron(-2500, -2500, 90, 90), gate(-2500, -2500))], 0, 0)
        got = self.snapshot(bld.tile_buildings(FRAME, *BOX, [layer], ELEV, airport=far))
        self.assertEqual(base[:3], got[:3])
        self.assertEqual(len(got), len(base))


if __name__ == "__main__":
    unittest.main()
