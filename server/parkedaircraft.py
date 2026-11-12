"""Parked aircraft: airliners nose-in at an airport's terminal gates and light aircraft in rows along a general-aviation
apron, as forest rows of the mod's static prop groups ac_light / ac_turboprop / ac_narrow / ac_wide (origin on the ground
under the aircraft's centre, nose toward local +Y, scale 1, the row's height the tail's top: CATALOG). Pure: lat / lon
points (tile_rows takes the ground and the frame).

stands(feats, buildings) -> [Craft]: from the infrastructure Features (Overture subtype "airport") of a cell and its
buildings, kept on the Features (and the buildings it was asked with).
Gates: class "airport_gate" or "parking_position" points (also a tag aeroway=gate / parking_position). A gate lies just
inside the terminal's facade (or in a pier drawn into the terminal's polygon: then the nearest ways out of the polygon are tried, a wall or a finger's tip first, to the first that clears), so the terminal is the nearest building of at least TERMINAL_MIN_M2 within NEAR_M (the
gate's own building when it stands inside one: its cell's and its neighbours' buildings), the facade's direction the length-weighted principal direction of its
edges within FACADE_R_M of the gate's nearest point, and the aircraft parks nose-in, its axis along the facade's normal:
nose NOSE_GAP_M off the facade, centre on from there by half its length. A jet bridge (a small building touching the
gate: under BRIDGE_MAX_M2, within ATTACH_M, reaching BRIDGE_MIN_M or more out) fixes the nose BACK_M (the door's setback
from the nose, by type) short of its tip and the aircraft beside it (the door on its left, the bridge on the aircraft's
left side clear of the fuselage); such buildings are no obstacle. No terminal within NEAR_M: a parking_position with a
numeric tag direction / heading / bearing (the nose's compass bearing) is placed on its point (nose wheel stop) and
otherwise nose toward the nearest edge of the apron it stands in; any other gate nose toward the nearest terminal within
REMOTE_M (a remote stand), else none.
Type by the aerodrome's class (the polygon around the gate, else the nearest aerodrome feature, else regional):
international_airport -> narrow, a wide one a quarter of the gates (by hash) where it fits, else a narrow, else a turboprop;
regional / domestic / plain airport -> turboprop (3 in 5) or narrow (the other as the fallback); military, heliports, seaplane bases and the like -> none; the rest (airstrips,
private, other) -> light. Occupancy: a gate's id's crc32 under OCCUPIED_PCT (never random: a rebuilt tile is the same).
General aviation: each apron (a polygon of at least APRON_MIN_M2) of an aerodrome that is neither international nor
military, or named / tagged general aviation (GA, aero club ...), gets ac_light every GA_SPACING_M along its edge, nose
to the edge, each slot kept by hash (GA_PCT), at most GA_MAX per apron (the lowest hashes), inside the apron.
Clearance (whole aircraft, fuselage + wing + tailplane rectangles, not a disc): dropped where it meets a building of
OBSTACLE_MIN_M2 or more (BUILDING_CLEAR_M margin; jet bridges and small sheds touching a gate excepted), a runway or
stopway (half its width + RUNWAY_CLEAR_M), a taxiway (its half width), a taxilane's centreline (one the nose points along is the stand's lead-in: none), or
another placed aircraft (AIRCRAFT_CLEAR_M). Gates are placed first (in position order, so closely mapped gates keep every
other one), then the aprons' rows; tile_rows drops an aircraft of one cell that overlaps another cell's. STATS counts why
gates got none (debug).

tile_rows(frame, box, infra_fn, buildings_fn, elev) -> forest rows [group, x, y, z, yaw, 1, H, 0] of the aircraft a tile
(box: x0, y0, x1, y1 in frame, or a geotile's OwnedBox) owns (each by its centre in one tile). infra_fn(key) -> the
cell's infrastructure Features (or None), buildings_fn(key) -> its buildings Features (or None, called only for a cell
with gates or aprons), elev(lat, lon) -> the (graded) ground in metres (arrays). Yaw: the server's (counter-clockwise
from +x; the shape's +Y at yaw 0 is north), as windsocks'. A cell without airport gates or aprons costs one test.
"""
import collections
import math
import re
import zlib

import numpy as np

import aeroways
import geotiles

GROUPS = {"light": "ac_light", "turboprop": "ac_turboprop", "narrow": "ac_narrow", "wide": "ac_wide"}
# length, span, tail top (the CATALOG heights), fuselage width, wing chord, wing's centre ahead of the middle (m)
SPECS = {"light": (8.3, 11.0, 2.7, 1.3, 1.5, 0.3), "turboprop": (27.2, 27.1, 7.6, 2.8, 2.6, 1.0),
         "narrow": (37.6, 35.8, 11.8, 3.95, 4.5, 1.8), "wide": (63.7, 60.1, 17.5, 6.0, 7.5, 3.0)}
BACK_M = {"light": 2.0, "turboprop": 4.0, "narrow": 5.0, "wide": 6.5}      # a door's setback from the nose
TAIL_SPAN_K, TAIL_CHORD_K, TAIL_AT_K = 0.34, 0.55, 0.40                   # the tailplane: of the span, chord, and its
                                                                           # centre behind the middle in lengths
GATE_CLASSES = ("airport_gate", "parking_position")
APRON = aeroways.APRON
SUBTYPE = aeroways.SUBTYPE
NOSE_GAP_M = 6.0                # m from the facade to the nose
NEAR_M = 60.0                   # m: a terminal further than this from a gate is none
TERMINAL_MIN_M2 = 1000.0
REMOTE_M = 260.0                # a stand off the terminals (no gate-side building within NEAR_M): the nose to the nearest one this near
FACADE_R_M = 30.0
ATTACH_M = 6.0                  # a jet bridge's nearest vertex this near the gate
BRIDGE_MAX_M2 = 300.0
BRIDGE_MIN_M, BRIDGE_CAP_M = 12.0, 50.0
BRIDGE_SIDE_M = 1.5             # m between a bridge's side and the fuselage
OBSTACLE_MIN_M2 = 300.0
BUILDING_CLEAR_M = 3.0
RUNWAY_CLEAR_M = 5.0
AIRCRAFT_CLEAR_M = 2.0
CENTRE_HIT_M = 1.6              # a point this near a centreline touches it (the sampling's step)
STEP_M = 1.5                    # the sampling of an aircraft's rectangles
OCCUPIED_PCT = 65
GA_PCT = 50
GA_SPACING_M = 15.0
GA_MAX = 12
GA_INSET_M = 1.5                # the nose this far inside the apron's edge
APRON_MIN_M2 = 400.0
AERODROME_NEAR_M = 5000.0
NEIGHBOUR_M = 150.0            # m: a gate or apron this near a cell's edge asks the neighbour cell's buildings too
LEAD_IN_COS = math.cos(math.radians(20.0))
RAY_MAX_M = 400.0
WALL_MIN_M = 8.0                # m of solid behind a wall (less the double of the way out) for a gate inside a terminal
FACADES_MAX, FACADE_SEP_DEG = 6, 25.0
GA_NAME = re.compile(r"general aviation|\bga\b|aero ?club|light aircraft|flying club|aeroclub", re.I)
_KEY = "_parked_aircraft"
_SHAPES = {}
STATS = collections.Counter()   # debug: why gates got no aircraft (cleared by the caller; see _gate_craft)


Craft = collections.namedtuple("Craft", "kind lat lon ne nn")      # ne, nn: the nose's east / north direction


def _crc(text):
    return zlib.crc32(str(text).encode("utf-8", "replace"))


# ------------------------------------------------------------------------------------------------- shapes
def _rects(kind):
    """The aircraft's rectangles as (u0, u1, v0, v1): u along the nose from the centre, v to its left."""
    length, span, _h, fus, chord, wing_at = SPECS[kind]
    tail_at = -TAIL_AT_K * length
    return [(-length / 2.0, length / 2.0, -fus / 2.0, fus / 2.0),
            (wing_at - chord / 2.0, wing_at + chord / 2.0, -span / 2.0, span / 2.0),
            (tail_at - TAIL_CHORD_K * chord, tail_at + TAIL_CHORD_K * chord, -TAIL_SPAN_K * span / 2.0,
             TAIL_SPAN_K * span / 2.0)]


def _local_points(kind):
    """The (u, v) sample points (n, 2) of the aircraft's rectangles (edges included), kept."""
    got = _SHAPES.get(kind)
    if got is None:
        out = []
        for u0, u1, v0, v1 in _rects(kind):
            us = np.linspace(u0, u1, max(2, int(math.ceil((u1 - u0) / STEP_M)) + 1))
            vs = np.linspace(v0, v1, max(2, int(math.ceil((v1 - v0) / STEP_M)) + 1))
            out.append(np.stack(np.meshgrid(us, vs), -1).reshape(-1, 2))
        got = _SHAPES[kind] = np.concatenate(out)
    return got


def _world(pts, cx, cy, nx, ny):
    """Local (u, v) points in the plane: centre (cx, cy), nose direction (nx, ny), v to the left of it."""
    return np.stack([cx + pts[:, 0] * nx - pts[:, 1] * ny, cy + pts[:, 0] * ny + pts[:, 1] * nx], 1)


def _in_rects(kind, cx, cy, nx, ny, pts, margin):
    """Which plane points lie within `margin` of the aircraft's rectangles."""
    d = pts - (cx, cy)
    u = d[:, 0] * nx + d[:, 1] * ny
    v = -d[:, 0] * ny + d[:, 1] * nx
    hit = np.zeros(len(pts), bool)
    for u0, u1, v0, v1 in _rects(kind):
        hit |= (u >= u0 - margin) & (u <= u1 + margin) & (v >= v0 - margin) & (v <= v1 + margin)
    return hit


def _radius(kind):
    return math.hypot(SPECS[kind][0] / 2.0, SPECS[kind][1] / 2.0)


# ------------------------------------------------------------------------------------------------- geometry
def _pip(ring, pts):
    """Which of pts (m, 2) are inside the polygon ring (k, 2) (even-odd)."""
    a, b = ring, np.roll(ring, -1, axis=0)
    y = pts[:, 1:2]
    cross = (a[:, 1] <= y) != (b[:, 1] <= y)
    dy = np.where(b[:, 1] == a[:, 1], 1.0, b[:, 1] - a[:, 1])
    xi = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / dy
    return ((cross & (pts[:, 0:1] < xi)).sum(1) % 2) == 1


def _seg_dist(pts, a, b):
    """(m, k) distances from pts (m, 2) to the segments a -> b (k, 2)."""
    ab = b - a
    ap = pts[:, None, :] - a[None]
    t = np.clip(np.einsum("mkj,kj->mk", ap, ab) / np.maximum(np.einsum("kj,kj->k", ab, ab), 1e-12)[None], 0.0, 1.0)
    d = ap - t[..., None] * ab[None]
    return np.hypot(d[..., 0], d[..., 1])


def _area(ring):
    return 0.5 * abs(float(np.dot(ring[:, 0], np.roll(ring[:, 1], -1)) - np.dot(np.roll(ring[:, 0], -1), ring[:, 1])))


def _nearest_on(ring, p):
    """(distance, nearest point, edge index) of the ring's edges to p."""
    a, b = ring, np.roll(ring, -1, axis=0)
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0.0, 1.0)
    q = a + t[:, None] * ab
    d = np.hypot(*(q - p).T)
    j = int(np.argmin(d))
    return float(d[j]), q[j], j


def _facade(ring, p):
    """(point q on the facade nearest p, unit outward normal) of a building ring: the normal is across the length-weighted
    principal direction of the edges within FACADE_R_M of q (a doubled angle: an edge has no sense), pointing out."""
    d0, q, _ = _nearest_on(ring, p)
    a, b = ring, np.roll(ring, -1, axis=0)
    ab = b - a
    ln = np.maximum(np.hypot(ab[:, 0], ab[:, 1]), 1e-9)
    near = np.hypot(*(((a + b) / 2.0) - q).T) <= FACADE_R_M + ln / 2.0
    w = np.minimum(ln, FACADE_R_M)[near]
    ang = np.arctan2(ab[near, 1], ab[near, 0])
    t = 0.5 * math.atan2(float((w * np.sin(2 * ang)).sum()), float((w * np.cos(2 * ang)).sum()))
    n = np.array([-math.sin(t), math.cos(t)])
    inside = bool(_pip(ring, (q + n * 2.0)[None])[0])
    if inside:
        n = -n
    return q, n


# ------------------------------------------------------------------------------------------------- the scene
class _Scene:
    """A Features' airport in a metre plane about (lat0, lon0): gates, aprons, aerodromes, pavement lines."""

    def __init__(self, feats):
        self.feats = feats
        self.lat0 = self.lon0 = None
        self.gates, self.aprons, self.aerodromes = [], [], []
        self.lines = []                         # (xy (n, 2), half width, mode): "pavement" or "centre"
        self.intl = False

    def xy(self, ring):
        ring = np.asarray(ring, np.float64)
        return np.stack([(ring[:, 0] - self.lon0) * self.kx, (ring[:, 1] - self.lat0) * aeroways.M_PER_DEG], 1)

    def latlon(self, x, y):
        return self.lat0 + y / aeroways.M_PER_DEG, self.lon0 + x / self.kx


def _tier(cls):
    """An aerodrome class's tier: intl / regional / light / military / none (None: not an aerodrome)."""
    c = str(cls)
    if c == aeroways.AERODROME:
        return "intl"
    if c in ("regional_airport", "domestic_airport", "airport", "public_airport", "medium_airport", "large_airport"):
        return "regional"
    if c in ("military_airport", "military", "military_airfield", "air_base"):
        return "military"
    if "heliport" in c or "seaplane" in c or "closed" in c:
        return "none"
    if c.endswith("airport") or c.endswith("airfield") or c.endswith("airstrip") or c in ("aerodrome", "airfield"):
        return "light"
    return None


def _scene(feats):
    sub, cls = feats.attrs.get("subtype"), feats.attrs.get("class")
    if sub is None or cls is None or not len(feats):
        return None
    air = np.asarray(sub).astype(str) == SUBTYPE
    cls = np.asarray(cls).astype(str)
    tags_col = feats.attrs.get("tags")
    name_col = feats.attrs.get("name")
    gate_like = air & np.isin(cls, GATE_CLASSES)
    if tags_col is not None:                                    # (a gate tagged only, under another class)
        tags_s = np.asarray(tags_col).astype(str)
        gate_like |= air & ((np.char.find(tags_s, '"gate"') >= 0) | (np.char.find(tags_s, "parking_position") >= 0))
    aprons = air & (cls == APRON) & (np.asarray(feats.kind) == 3)
    if not (gate_like.any() or aprons.any()):
        return None
    sc = _Scene(feats)
    first = int(np.flatnonzero(gate_like | aprons)[0])
    pt = np.asarray(feats.parts(first)[0][0], np.float64)[0]
    sc.lon0, sc.lat0 = float(pt[0]), float(pt[1])
    sc.kx = aeroways.M_PER_DEG * math.cos(math.radians(sc.lat0))
    sc.intl = bool((air & (cls == aeroways.AERODROME)).any())
    for i in np.flatnonzero(air):
        kind = int(feats.kind[i])
        tags = aeroways._tags(feats, i)
        c = cls[i]
        parts = feats.parts(int(i))
        if not parts or not parts[0] or not len(parts[0][0]):
            continue
        if gate_like[i] and kind == 1:
            x, y = sc.xy(parts[0][0][:1])[0]
            d = None
            for k in ("direction", "heading", "bearing"):
                try:
                    d = float(str(tags.get(k, "")).strip()) % 360.0
                    break
                except ValueError:
                    pass
            sc.gates.append((str(feats.ids[i]), float(x), float(y), d, c == "parking_position"
                             or tags.get("aeroway") == "parking_position"))
            continue
        tier = _tier(c) if c != APRON else None
        if tier is not None:
            for part in parts:
                if kind == 3 and len(part[0]) >= 3:
                    sc.aerodromes.append((tier, sc.xy(part[0])))
                elif kind == 1:
                    sc.aerodromes.append((tier, sc.xy(part[0][:1])))
            continue
        if c == APRON and kind == 3:
            name = str(name_col[i]) if name_col is not None else ""
            ga = bool(GA_NAME.search(name + " " + " ".join(str(v) for v in tags.values())))
            for p, part in enumerate(parts):
                if len(part[0]) >= 3:
                    sc.aprons.append((f"{feats.ids[i]}#{p}", sc.xy(part[0]), ga))
        elif c in ("runway", "stopway", "taxiway", "taxilane") and kind == 2 and not aeroways._unpaved(feats, i, tags):
            if c in ("runway", "stopway"):
                half = (aeroways.width_tag(tags.get("width")) or (
                    aeroways.RUNWAY_INTL_M if sc.intl else aeroways.RUNWAY_M)) / 2.0 + RUNWAY_CLEAR_M
                mode = "pavement"
            else:
                w = aeroways.width_tag(tags.get("width")) or (
                    (aeroways.TAXIWAY_INTL_M if sc.intl else aeroways.TAXIWAY_M) if c == "taxiway"
                    else (aeroways.TAXILANE_INTL_M if sc.intl else aeroways.TAXILANE_M))
                half, mode = (w / 2.0, "pavement") if c == "taxiway" else (CENTRE_HIT_M, "centre")
            for part in parts:
                for line in part:
                    if len(line) >= 2:
                        sc.lines.append((sc.xy(line), half, mode))
    return sc


def _aerodrome(sc, x, y):
    """The tier of the aerodrome around (x, y): the polygon holding it, else the nearest feature within
    AERODROME_NEAR_M, else None."""
    p = np.array([[x, y]])
    best, bd = None, AERODROME_NEAR_M
    for tier, geom in sc.aerodromes:
        if len(geom) >= 3 and _pip(geom, p)[0]:
            return tier
        d = float(np.hypot(*(geom - (x, y)).T).min())
        if d < bd:
            best, bd = tier, d
    return best


# ------------------------------------------------------------------------------------------------- clearance
class _World:
    """What an aircraft must keep off: buildings, pavement lines and the aircraft already placed."""

    def __init__(self, sc, rings):
        self.sc = sc
        self.rings = rings                      # obstacle buildings: (ring, (x0, y0, x1, y1))
        self.placed = []                        # (kind, x, y, nx, ny)
        segs = [(ln[:-1], ln[1:], np.full(len(ln) - 1, h), np.full(len(ln) - 1, m == "centre"))
                for ln, h, m in sc.lines]
        if segs:
            self.a, self.b = np.concatenate([s[0] for s in segs]), np.concatenate([s[1] for s in segs])
            self.half = np.concatenate([s[2] for s in segs])
            self.centre = np.concatenate([s[3] for s in segs])
        else:
            self.a = self.b = np.zeros((0, 2))
            self.half = np.zeros(0)
            self.centre = np.zeros(0, bool)

    def clear(self, kind, x, y, nx, ny, inside=None):
        """Does an aircraft of `kind` at (x, y) heading (nx, ny) keep clear (and, with `inside` (a ring), lie in it)?"""
        return self.why(kind, x, y, nx, ny, inside) is None

    def why(self, kind, x, y, nx, ny, inside=None):
        """None where an aircraft of `kind` at (x, y) heading (nx, ny) keeps clear (and lies in the ring `inside`), else
        the first thing it meets: "outside", "building", "taxiway" (runways, stopways, taxiways), "taxilane", "aircraft"."""
        pts = _world(_local_points(kind), x, y, nx, ny)
        r = _radius(kind) + BUILDING_CLEAR_M
        if inside is not None and not _pip(inside, pts).all():
            return "outside"
        for ring, (x0, y0, x1, y1) in self.rings:
            if x0 - r > x or x1 + r < x or y0 - r > y or y1 + r < y:
                continue
            if _pip(ring, pts).any() or _seg_dist(pts, ring, np.roll(ring, -1, axis=0)).min() < BUILDING_CLEAR_M:
                return "building"
        if len(self.a):
            lo, hi = np.minimum(self.a, self.b) - r, np.maximum(self.a, self.b) + r
            keep = (lo[:, 0] <= x) & (hi[:, 0] >= x) & (lo[:, 1] <= y) & (hi[:, 1] >= y)
            if keep.any():                      # (a taxilane the nose points along is the stand's own lead-in: no clash)
                ab = self.b[keep] - self.a[keep]
                along = np.abs(ab[:, 0] * nx + ab[:, 1] * ny) > LEAD_IN_COS * np.maximum(np.hypot(ab[:, 0], ab[:, 1]), 1e-9)
                keep[np.flatnonzero(keep)[along & self.centre[keep]]] = False
            if keep.any():
                hit = _seg_dist(pts, self.a[keep], self.b[keep]).min(0) < self.half[keep]
                if hit.any():
                    return "taxilane" if self.centre[keep][hit].any() else "taxiway"
        for k2, x2, y2, nx2, ny2 in self.placed:
            if math.hypot(x2 - x, y2 - y) > _radius(kind) + _radius(k2) + AIRCRAFT_CLEAR_M:
                continue
            if _in_rects(k2, x2, y2, nx2, ny2, pts, AIRCRAFT_CLEAR_M).any() or \
                    _in_rects(kind, x, y, nx, ny, _world(_local_points(k2), x2, y2, nx2, ny2), AIRCRAFT_CLEAR_M).any():
                return "aircraft"
        return None

    def add(self, kind, x, y, nx, ny):
        self.placed.append((kind, x, y, nx, ny))


def _buildings(sc, bld):
    """(obstacle rings [(ring, bbox)], small buildings [(ring, area)]) of a buildings Features, in the plane."""
    obstacles, small = [], []
    blds = [b for b in (bld if isinstance(bld, (list, tuple)) else [bld]) if b is not None and len(b)]
    if not blds:
        return obstacles, small
    # (only the rings near the airport's features)
    xs = [g[1] for g in sc.gates]
    ys = [g[2] for g in sc.gates]
    for _i, ring, _a in sc.aprons:
        xs += [float(ring[:, 0].min()), float(ring[:, 0].max())]
        ys += [float(ring[:, 1].min()), float(ring[:, 1].max())]
    if not xs:
        return obstacles, small
    box = (min(xs) - 200.0, min(ys) - 200.0, max(xs) + 200.0, max(ys) + 200.0)
    seen = set()                                # (a building spanning cells is in each)
    for bld, i in ((b, i) for b in blds for i in range(len(b))):
        under = bld.attrs.get("is_underground")
        if int(bld.kind[i]) != 3 or (under is not None and bool(under[i])):
            continue
        for pi, part in enumerate(bld.parts(i)):
            if not part or len(part[0]) < 3:
                continue
            ring = part[0]
            if (str(bld.ids[i]), pi) in seen:
                continue
            seen.add((str(bld.ids[i]), pi))
            if ring[:, 0].max() < sc.lon0 + box[0] / sc.kx or ring[:, 0].min() > sc.lon0 + box[2] / sc.kx or \
                    ring[:, 1].max() < sc.lat0 + box[1] / aeroways.M_PER_DEG or \
                    ring[:, 1].min() > sc.lat0 + box[3] / aeroways.M_PER_DEG:
                continue
            r = sc.xy(ring)
            area = _area(r)
            if area >= OBSTACLE_MIN_M2:
                obstacles.append((r, (float(r[:, 0].min()), float(r[:, 1].min()), float(r[:, 0].max()),
                                      float(r[:, 1].max()))))
            if area < BRIDGE_MAX_M2:
                small.append((r, area))
    return obstacles, small


# ------------------------------------------------------------------------------------------------- the stands
def _exit_out(ring, pts, d):
    """The distances along the unit directions d (k, 2) from the points pts (k, 2), inside the ring, to its first edge
    (RAY_MAX_M where none)."""
    a, b = ring, np.roll(ring, -1, axis=0)
    e = b - a
    w = a[None] - pts[:, None, :]                                    # (k, m, 2)
    den = d[:, 0:1] * e[None, :, 1] - d[:, 1:2] * e[None, :, 0]      # d x e, (k, m)
    ok = np.abs(den) > 1e-9
    den = np.where(ok, den, 1.0)
    t = (w[..., 0] * e[None, :, 1] - w[..., 1] * e[None, :, 0]) / den
    u = (w[..., 0] * d[:, 1:2] - w[..., 1] * d[:, 0:1]) / den
    hit = ok & (t > 1e-6) & (u >= 0.0) & (u <= 1.0)
    return np.where(hit, t, RAY_MAX_M).min(1)


def _inside_facades(ring, p):
    """[(point, outward normal)] ways out for a gate inside its terminal's polygon, where the nearest edge is no facade
    (a jet bridge or a pier drawn into the building, a gate at a finger's root): the directions whose ray leaves the polygon
    soonest, the ones with solid behind them (a wall; a finger's tip along its axis) first, at most FACADES_MAX apart by
    FACADE_SEP_DEG."""
    ang = np.radians(np.arange(0.0, 360.0, 5.0))
    d = np.stack([np.cos(ang), np.sin(ang)], 1)
    pp = np.tile(p, (len(d), 1))
    fwd, back = _exit_out(ring, pp, d), _exit_out(ring, pp, -d)
    order = sorted(range(len(d)), key=lambda i: (back[i] - 2.0 * fwd[i] < WALL_MIN_M, fwd[i]))
    out, got = [], []
    for i in order:
        if fwd[i] >= RAY_MAX_M or any(float(d[i] @ d[j]) > math.cos(math.radians(FACADE_SEP_DEG)) for j in got):
            continue
        got.append(i)
        out.append((p + d[i] * fwd[i], d[i]))
        if len(out) >= FACADES_MAX:
            break
    return out


def _terminal(obstacles, x, y, near=None):
    """(ring, [(facade point, outward normal) ...]) of the terminal of a gate at (x, y): the nearest large building
    within NEAR_M (the one it stands in first), None without; the facades by preference."""
    near = NEAR_M if near is None else near
    p = np.array([x, y])
    best = None
    for ring, (x0, y0, x1, y1) in obstacles:
        if _area(ring) < TERMINAL_MIN_M2 or x0 - near > x or x1 + near < x or y0 - near > y or y1 + near < y:
            continue
        inside = bool(_pip(ring, p[None])[0])
        d = 0.0 if inside else _nearest_on(ring, p)[0]
        if d <= near and (best is None or d < best[0] - 1e-6):
            best = (d, ring, inside)
    if best is None:
        return None
    ring = best[1]
    if best[2]:
        out = _inside_facades(ring, p) + [_facade(ring, p)]
    else:
        out = [_facade(ring, p)]                                                          # (the nearest edge's own normal)
        _d, q, j = _nearest_on(ring, p)
        e = np.roll(ring, -1, axis=0)[j] - ring[j]
        n = np.array([-e[1], e[0]]) / max(float(np.hypot(*e)), 1e-9)
        if float(n @ (p - q)) < 0.0 or (float(n @ (p - q)) == 0.0 and bool(_pip(ring, (q + n * 2.0)[None])[0])):
            n = -n                                              # (toward the gate's side: out of the building)
        out.append((q, n))
    return ring, out


def _bridge(small, gx, gy, out):
    """The jet bridge of a gate: (tip distance along `out` from the gate, lateral centre, half width) of the small
    building touching it that reaches farthest out (at least BRIDGE_MIN_M), None without."""
    p = np.array([gx, gy])
    tan = np.array([-out[1], out[0]])
    best = None
    for ring, _a in small:
        if np.hypot(*(ring - p).T).min() > ATTACH_M:
            continue
        d = ring - p
        tip, lat = (d @ out), (d @ tan)
        if tip.max() >= BRIDGE_MIN_M and (best is None or tip.max() > best[0]):
            best = (float(min(tip.max(), BRIDGE_CAP_M)), float((lat.min() + lat.max()) / 2.0),
                    float((lat.max() - lat.min()) / 2.0))
    return best


def _kinds_for(tier, gid):
    """The types to try at a gate, first choice first, by its aerodrome's tier and the hash (): none for military and
    the like. A stand too tight for the first choice takes a smaller one."""
    h = _crc(gid + ":type")
    if tier == "intl":
        return ("wide", "narrow", "turboprop") if h % 4 == 0 else ("narrow", "turboprop")
    if tier in ("regional", None):
        return ("turboprop", "narrow") if h % 5 < 3 else ("narrow", "turboprop")
    if tier == "light":
        return ("light",)
    return ()


def _gate_craft(sc, world, small, obstacles):
    out = []
    gates = sorted(sc.gates, key=lambda g: (round(g[1], 1), round(g[2], 1), g[0]))   # (along a row: alternates stay)
    for gid, gx, gy, bearing, is_pos in gates:
        STATS["gates"] += 1
        if _crc(gid) % 100 >= OCCUPIED_PCT:
            STATS["not_occupied"] += 1
            continue
        tier = _aerodrome(sc, gx, gy)
        if tier in ("military", "none"):
            STATS["tier_none"] += 1
            continue
        kinds = _kinds_for(tier, gid)
        if not kinds:
            STATS["tier_none"] += 1
            continue
        term = _terminal(obstacles, gx, gy)
        remote = None
        if term is None and not (is_pos and (bearing is not None or _apron_nose(sc, gx, gy) is not None)):
            remote = _terminal(obstacles, gx, gy, REMOTE_M)
        why = "no_terminal"
        for kind in kinds:
            length = SPECS[kind][0]
            tries = []                                  # (centre x, y, nose direction x, y)
            if term is not None:
                for q, n in term[1]:
                    nose_d = float((q - (gx, gy)) @ n) + NOSE_GAP_M
                    lat = 0.0
                    br = _bridge(small, gx, gy, n)
                    if br is not None:
                        nose_d = br[0] - BACK_M[kind]
                        lat = br[1] + br[2] + SPECS[kind][3] / 2.0 + BRIDGE_SIDE_M
                    tan = np.array([-n[1], n[0]])
                    cx, cy = np.array([gx, gy]) + n * (nose_d + length / 2.0) + tan * lat
                    tries.append((cx, cy, -n[0], -n[1]))
            elif is_pos and bearing is not None:
                nx, ny = math.sin(math.radians(bearing)), math.cos(math.radians(bearing))
                tries.append((gx - nx * 0.4 * length, gy - ny * 0.4 * length, nx, ny))
            elif is_pos:
                got = _apron_nose(sc, gx, gy)
                if got is not None:
                    nx, ny = got
                    tries.append((gx - nx * 0.4 * length, gy - ny * 0.4 * length, nx, ny))
            elif remote is not None:                    # (a stand off the terminals: the nose toward the nearest facade)
                q = remote[1][-1][0]
                v = q - (gx, gy)
                nx, ny = v / max(float(np.hypot(*v)), 1e-6)
                tries.append((gx - nx * 0.4 * length, gy - ny * 0.4 * length, nx, ny))
            if not tries:
                why = "no_terminal"
                break
            for cx, cy, nx, ny in tries:
                why = world.why(kind, cx, cy, nx, ny)
                if why is None:
                    break
            if why is None:
                world.add(kind, cx, cy, nx, ny)
                out.append((kind, cx, cy, nx, ny))
                STATS["placed_" + kind] += 1
                break
        if why is not None:
            STATS["no_" + why] += 1
    return out


def _apron_nose(sc, x, y):
    """The unit direction toward the nearest edge of the apron holding (x, y), None outside any."""
    p = np.array([[x, y]])
    for _i, ring, _ga in sc.aprons:
        if _pip(ring, p)[0]:
            _d, q, _j = _nearest_on(ring, p[0])
            v = q - p[0]
            n = float(np.hypot(*v))
            return (v / n) if n > 1e-6 else None
    return None


def _ga_craft(sc, world):
    out = []
    for aid, ring, tagged in sorted(sc.aprons, key=lambda a: a[0]):
        c = ring.mean(0)
        tier = _aerodrome(sc, float(c[0]), float(c[1]))
        if tier in ("military", "none") or _area(ring) < APRON_MIN_M2:
            continue
        if not (tagged or (tier != "intl" and not (tier is None and sc.intl))):
            continue
        closed = np.r_[ring, ring[:1]] if not np.allclose(ring[0], ring[-1]) else ring
        seg = np.diff(closed, axis=0)
        ln = np.hypot(seg[:, 0], seg[:, 1])
        cum = np.r_[0.0, np.cumsum(ln)]
        # the ring's sense: the inward normal of an edge is its left when it runs counter-clockwise
        sign = 1.0 if float(np.dot(closed[:-1, 0], closed[1:, 1]) - np.dot(closed[1:, 0], closed[:-1, 1])) > 0 else -1.0
        slots = []
        for k in range(int(cum[-1] // GA_SPACING_M)):
            h = _crc(f"{aid}:{k}")
            if h % 100 < GA_PCT:
                slots.append((h, k))
        keep = sorted(slots)[:GA_MAX]
        n_ok = 0
        for _h, k in sorted(keep, key=lambda t: t[1]):
            s = (k + 0.5) * GA_SPACING_M
            j = min(int(np.searchsorted(cum, s, side="right")) - 1, len(seg) - 1)
            if ln[j] < 1e-6:
                continue
            t = seg[j] / ln[j]
            edge = closed[j] + t * (s - cum[j])
            inward = sign * np.array([-t[1], t[0]])
            length = SPECS["light"][0]
            cx, cy = edge + inward * (length / 2.0 + GA_INSET_M)
            nx, ny = -inward[0], -inward[1]
            if n_ok < GA_MAX and world.clear("light", cx, cy, nx, ny, inside=ring):
                world.add("light", cx, cy, nx, ny)
                out.append(("light", float(cx), float(cy), float(nx), float(ny)))
                n_ok += 1
    return out


def stands(feats, buildings=None):
    """[Craft] of a cell's infrastructure Features (see the module docstring), kept on the Features (by the buildings
    it was asked with: a buildings Features, or a list of them, the cell's and its neighbours'); [] for Features
    without airport gates or aprons."""
    if feats is None or len(feats) == 0:
        return []
    same = lambda a, b: a is b or (isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b)
                                   and all(x is y for x, y in zip(a, b)))
    got = feats.__dict__.get(_KEY)
    if got is not None and same(got[0], buildings):
        return got[1]
    sc = feats.__dict__.get(_KEY + "_scene", False)
    if sc is False:
        sc = feats.__dict__[_KEY + "_scene"] = _scene(feats)
    out = []
    if sc is not None:
        obstacles, small = _buildings(sc, buildings)
        world = _World(sc, obstacles)
        placed = _gate_craft(sc, world, small, obstacles) + _ga_craft(sc, world)
        out = [Craft(k, *sc.latlon(x, y), nx, ny) for k, x, y, nx, ny in placed]
    feats.__dict__[_KEY] = (buildings, out)
    return out


def has_stands(feats):
    """Could the Features hold any (gates or aprons of an airport)? A test of the class column, kept."""
    if feats is None or len(feats) == 0:
        return False
    got = feats.__dict__.get(_KEY + "_scene", False)
    if got is False:
        got = feats.__dict__[_KEY + "_scene"] = _scene(feats)
    return got is not None


# ------------------------------------------------------------------------------------------------- the tile's rows
def _yaw(east, north):
    return (math.degrees(math.atan2(north, east)) - 90.0) % 360.0


def _near_cells(key, feats):
    """The neighbouring cells within NEIGHBOUR_M of the cell's gates and aprons (their buildings may hold a gate's terminal)."""
    sc = feats.__dict__.get(_KEY + "_scene")
    if sc is None or not hasattr(key, "bounds") or not hasattr(key, "neighbours"):
        return []
    pts = [np.array([[g[1], g[2]]]) for g in sc.gates] + [ring for _i, ring, _ga in sc.aprons]
    if not pts:
        return []
    xy = np.concatenate(pts)
    lon = sc.lon0 + xy[:, 0] / sc.kx
    lat = sc.lat0 + xy[:, 1] / aeroways.M_PER_DEG
    dlat = NEIGHBOUR_M / aeroways.M_PER_DEG
    dlon = NEIGHBOUR_M / (aeroways.M_PER_DEG * math.cos(math.radians(sc.lat0)))
    out = []
    for nk in key.neighbours():
        w, s, e, n = nk.bounds()
        if ((lon >= w - dlon) & (lon <= e + dlon) & (lat >= s - dlat) & (lat <= n + dlat)).any():
            out.append(nk)
    return out


def _dedupe(items, lat, lon):
    """Indices of the items kept, deterministic whatever the order (position order): an aircraft drops where it overlaps a
    kept one of another cell (the cells place their own gates' aircraft without each other's)."""
    order = sorted(range(len(items)), key=lambda j: (round(float(lat[j]), 6), round(float(lon[j]), 6), items[j].kind))
    kx = aeroways.M_PER_DEG * np.cos(np.radians(lat))
    kept, placed = [], []                           # placed: (kind, x, y, nx, ny) in a local plane
    for j in order:
        c = items[j]
        x, y = float(lon[j] - lon[order[0]]) * float(kx[j]), float(lat[j] - lat[order[0]]) * aeroways.M_PER_DEG
        hit = False
        for k2, x2, y2, nx2, ny2 in placed:
            if math.hypot(x2 - x, y2 - y) > _radius(c.kind) + _radius(k2) + AIRCRAFT_CLEAR_M:
                continue
            pts = _world(_local_points(k2), x2, y2, nx2, ny2)
            if _in_rects(c.kind, x, y, c.ne, c.nn, pts, AIRCRAFT_CLEAR_M).any() or                     _in_rects(k2, x2, y2, nx2, ny2, _world(_local_points(c.kind), x, y, c.ne, c.nn), AIRCRAFT_CLEAR_M).any():
                hit = True
                break
        if hit:
            STATS["cross_cell"] += 1
            continue
        kept.append(j)
        placed.append((c.kind, x, y, c.ne, c.nn))
    return sorted(kept)


def tile_rows(frame, box, infra_fn, buildings_fn, elev, keys=None):
    """Forest rows [group, x, y, z, yaw, 1, H, 0] of the parked aircraft a tile owns (see the module docstring).
    keys: the box's cells (default: under it, a gate's aircraft stands within ~70 m of it: padded 0.001 degrees)."""
    if keys is None:
        import mapcells
        x0, y0, x1, y1 = (float(v) for v in box[:4])
        la, lo, _ = frame.enu_to_geodetic(np.array([x0, x0, x1, x1]), np.array([y0, y1, y0, y1]), np.zeros(4))
        try:
            keys = mapcells.cells_for_points(la, lo, pad_lat=0.001, pad_lon=0.001, max_cells=64)
        except (ValueError, OverflowError):
            return []
    items = []
    for k in keys:
        feats = infra_fn(k)
        if not has_stands(feats):
            continue
        blds = [buildings_fn(k)] + [buildings_fn(nk) for nk in _near_cells(k, feats)]
        items.extend(stands(feats, blds))
    if not items:
        return []
    lat = np.array([c.lat for c in items], np.float64)
    lon = np.array([c.lon for c in items], np.float64)
    e, n, _ = frame.geodetic_to_enu(lat, lon, 0.0)
    e, n = np.asarray(e, np.float64), np.asarray(n, np.float64)
    keep = _dedupe(items, lat, lon)                 # (a gate near a cell's edge: its neighbour's aircraft on it)
    items = [items[j] for j in keep]
    lat, lon, e, n = lat[keep], lon[keep], e[keep], n[keep]
    own = np.flatnonzero(np.asarray(geotiles.box_owns(box, e, n), bool))
    if not len(own):
        return []
    # (the nose direction in this frame: a point 10 m on, with the meridians' convergence)
    kx = aeroways.M_PER_DEG * np.cos(np.radians(lat[own]))
    ne = np.array([items[j].ne for j in own], np.float64)
    nn = np.array([items[j].nn for j in own], np.float64)
    la2, lo2 = lat[own] + nn * 10.0 / aeroways.M_PER_DEG, lon[own] + ne * 10.0 / kx
    e2, n2, _ = frame.geodetic_to_enu(la2, lo2, 0.0)
    h = np.asarray(elev(lat[own], lon[own]), np.float64)
    z = np.asarray(frame.geodetic_to_enu(lat[own], lon[own], h)[2], np.float64)
    rows = []
    for j, x, y, zz, xe, yn in zip(own.tolist(), e[own], n[own], z, np.asarray(e2, np.float64), np.asarray(n2, np.float64)):
        kind = items[j].kind
        rows.append([GROUPS[kind], round(float(x), 2), round(float(y), 2), round(float(zz), 2),
                     round(_yaw(float(xe - x), float(yn - y)), 1), 1.0, SPECS[kind][2], 0.0])
    return rows
