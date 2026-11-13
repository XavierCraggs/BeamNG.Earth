"""Parked aircraft: airliners nose-in at an airport's terminal gates and light aircraft in rows along a general-aviation
apron, as forest rows of the mod's static prop groups ac_light / ac_turboprop / ac_narrow / ac_wide (origin on the ground
under the aircraft's centre, nose toward local +Y, scale 1, the row's height the tail's top: CATALOG). Pure: lat / lon
points (tile_rows takes the ground and the frame).

stands(feats, buildings) -> [Craft]: from the infrastructure Features (Overture subtype "airport") of a cell and its
buildings, kept on the Features (and the buildings it was asked with).
Gates: class "airport_gate" or "parking_position" points (also a tag aeroway=gate / parking_position). A gate lies just
inside the terminal's facade (or in a pier drawn into the terminal's polygon: then the nearest ways out of the polygon are tried, a wall or a finger's tip first, to the first that clears), so the terminal is the nearest building of at least TERMINAL_MIN_M2 within NEAR_M (the
gate's own building when it stands inside one: its cell's and its neighbours' buildings), the facade's direction that of the
building edge nearest the gate (an edge of at least EDGE_MIN_M; a shorter one: the length-weighted principal direction of
the edges within FACADE_R_M of it), and the aircraft parks nose-in, its axis along the facade's normal (so perpendicular to
the wall): nose NOSE_GAP_M off the facade, centre on from there by half its length, the tail toward the open apron. A
numeric tag direction / heading / bearing on the gate (the nose's compass bearing) is preferred where it points
within HEADING_MAX_DEG of the facade's normal. A jet bridge (a small building touching the
gate: under BRIDGE_MAX_M2, within ATTACH_M, reaching BRIDGE_MIN_M or more out) fixes the nose BACK_M (the door's setback
from the nose, by type) short of its tip and the aircraft beside it (the door on its left, the bridge on the aircraft's
left side clear of the fuselage); such buildings are no obstacle. No terminal within NEAR_M (a remote stand): a gate
with such a tag is placed on its point (nose wheel stop) by it; otherwise it lines up with the nearest taxiway or taxilane
within REMOTE_LANE_M (across it, the tail toward the line, where the aircraft is pushed back onto it; along it, nose
toward its end, where the line ends within REMOTE_END_M of the stand), a parking_position without one nose toward the
nearest edge of the apron it stands in, any other gate nose toward the nearest terminal within REMOTE_M, else none.
Type by the aerodrome's class (the polygon around the gate, else the nearest aerodrome feature, else regional):
international_airport -> narrow, a wide one a quarter of the gates (by hash) where it fits, else a narrow, else a turboprop;
regional / domestic / plain airport -> turboprop (3 in 5) or narrow (the other as the fallback); military, heliports, seaplane bases and the like -> none; the rest (airstrips,
private, other) -> light. Occupancy: a gate's id's crc32 under OCCUPIED_PCT (never random: a rebuilt tile is the same).
General aviation: each apron (a polygon of at least APRON_MIN_M2) of an aerodrome that is neither international nor
military, or named / tagged general aviation (GA, aero club ...), gets ac_light every GA_SPACING_M along its edge, nose
to the edge, each slot kept by hash (GA_PCT), at most GA_MAX per apron (the lowest hashes), inside the apron.
Clearance (whole aircraft, fuselage + wing + tailplane rectangles, not a disc): dropped where it meets any building or
building part (the buildings Features and the building_parts Features alike: canopies and covered walkways count whatever
their height; OBSTACLE_MIN_M2 skips slivers; BUILDING_CLEAR_M margin; the gate's own jet bridges excepted); a gate's
aircraft that meets one is pulled back along its axis (tail-ward, PULL_BACK_STEP_M at a time up to PULL_BACK_MAX_M) before
it is dropped; a runway or
stopway (half its width + RUNWAY_CLEAR_M), a taxiway (its half width), a taxilane's centreline (one the nose points along is the stand's lead-in: none), or
another placed aircraft (AIRCRAFT_CLEAR_M), then a final pass (drop_overlaps) drops any aircraft whose footprint
overlaps one kept already, the longer kinds kept first. Gates are placed first (in position order, so closely mapped gates keep every
other one), then the aprons' rows; tile_rows drops an aircraft of one cell that overlaps another cell's. STATS counts why
gates got none (debug).

kept_stands(keys, infra_fn, buildings_fn) -> [Craft]: the stands of those cells after the cross-cell pass: what tile_rows
places, for the painted lead-in lines of taxiwaymarks (a Craft's mode "gate" / "remote" / "ga").

tile_rows(frame, box, infra_fn, buildings_fn, elev) -> forest rows [group, x, y, z, yaw, 1, H, 0] of the aircraft a tile
(box: x0, y0, x1, y1 in frame, or a geotile's OwnedBox) owns (each by its centre in one tile). infra_fn(key) -> the
cell's infrastructure Features (or None), buildings_fn(key) -> its buildings Features, or a list of Features (the building_parts
as well; or None; called only for a cell with gates or aprons), elev(lat, lon) -> the (graded) ground in metres (arrays). Yaw: the server's (counter-clockwise
from +x; the shape's +Y at yaw 0 is north), as windsocks'. A cell without airport gates or aprons costs one test.
"""
import collections
import math
import re
import zlib

import numpy as np

import aeroways
import dmath
import dnp
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
OBSTACLE_MIN_M2 = 1.0           # a building or part smaller than this is a sliver
BUILDING_CLEAR_M = 1.5
PULL_BACK_MAX_M = 15.0          # a gate's aircraft that meets a building moves tail-ward by up to this far
PULL_BACK_STEP_M = 1.5
EDGE_MIN_M = 6.0                # a facade edge shorter than this gives its normal to the smoothed one
HEADING_MAX_DEG = 60.0          # a tagged heading within this of the facade's normal is used
HEADING_COS = dmath.cos(math.radians(HEADING_MAX_DEG))
REMOTE_LANE_M = 150.0           # a remote stand lines up with a taxiway / taxilane this near
REMOTE_END_M = 30.0             # ... and along one that ends this near
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
LEAD_IN_COS = dmath.cos(math.radians(20.0))
RAY_MAX_M = 400.0
WALL_MIN_M = 8.0                # m of solid behind a wall (less the double of the way out) for a gate inside a terminal
FACADES_MAX, FACADE_SEP_DEG = 6, 25.0
GA_NAME = re.compile(r"general aviation|\bga\b|aero ?club|light aircraft|flying club|aeroclub", re.I)
_KEY = "_parked_aircraft"
_SHAPES = {}
STATS = collections.Counter()   # debug: why gates got no aircraft (cleared by the caller; see _gate_craft)


Craft = collections.namedtuple("Craft", "kind lat lon ne nn mode", defaults=("",))   # ne, nn: the nose's east / north direction;
                                                # mode: "gate" (nose to a terminal), "remote" (a stand off the terminals),
                                                # "ga" (a general-aviation row)


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
    t = np.clip(dnp.vecdot(ap, ab) / np.maximum(dnp.vecdot(ab, ab), 1e-12)[None], 0.0, 1.0)
    d = ap - t[..., None] * ab[None]
    return dnp.hypot(d[..., 0], d[..., 1])


def _area(ring):
    return 0.5 * abs(float(dnp.dot(ring[:, 0], np.roll(ring[:, 1], -1)) - dnp.dot(np.roll(ring[:, 0], -1), ring[:, 1])))


def _nearest_seg(a, b, p):
    """(distance, nearest point, index, parameter 0..1) of the segments a -> b (k, 2) to p."""
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0.0, 1.0)
    q = a + t[:, None] * ab
    d = dnp.hypot(*(q - p).T)
    j = int(np.argmin(d))
    return float(d[j]), q[j], j, float(t[j])


def _nearest_on(ring, p):
    """(distance, nearest point, edge index) of the ring's edges to p."""
    d, q, j, _t = _nearest_seg(ring, np.roll(ring, -1, axis=0), p)
    return d, q, j


def _flat(items):
    """The Features (not None) of a Features or of nested lists of them, in order."""
    out = []
    for b in (items if isinstance(items, (list, tuple)) else [items]):
        if isinstance(b, (list, tuple)):
            out += _flat(b)
        elif b is not None:
            out.append(b)
    return out


def _snap_normal(ring, q, d):
    """The unit normal (out of the building) of the ring edge nearest the exit point q where that edge is at least
    EDGE_MIN_M long and within HEADING_MAX_DEG of the ray's direction d (a ray in 5 degree steps is not quite across
    the wall), else d."""
    _dist, _q, j = _nearest_on(ring, q)
    e = ring[(j + 1) % len(ring)] - ring[j]
    ln = float(dnp.hypot(*e))
    if ln < EDGE_MIN_M:
        return d
    n = np.array([-e[1], e[0]]) / ln
    if float(dnp.matmul(n, d)) < 0.0:
        n = -n
    return n if float(dnp.matmul(n, d)) >= HEADING_COS else d


def _facade(ring, p):
    """(point q on the facade nearest p, unit outward normal) of a building ring: the normal is across the length-weighted
    principal direction of the edges within FACADE_R_M of q (a doubled angle: an edge has no sense), pointing out."""
    d0, q, j0 = _nearest_on(ring, p)
    a, b = ring, np.roll(ring, -1, axis=0)
    ab = b - a
    ln = np.maximum(dnp.hypot(ab[:, 0], ab[:, 1]), 1e-9)
    near = dnp.hypot(*(((a + b) / 2.0) - q).T) <= FACADE_R_M + ln / 2.0
    w = np.minimum(ln, FACADE_R_M)[near]
    ang = dnp.arctan2(ab[near, 1], ab[near, 0])
    sy, sx = float((w * dnp.sin(2 * ang)).sum()), float((w * dnp.cos(2 * ang)).sum())
    if dnp.hypot(sx, sy) < 0.3 * float(w.sum()):          # (edges that cancel, a corner or a zig-zag: the nearest edge's)
        t = dmath.atan2(float(ab[j0, 1]), float(ab[j0, 0]))
    else:
        t = 0.5 * dmath.atan2(sy, sx)
    n = np.array([-dmath.sin(t), dmath.cos(t)])
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
        self.lanes = []                         # the taxiways' and taxilanes' lines (xy (n, 2))
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
    sc.kx = aeroways.M_PER_DEG * dmath.cos(math.radians(sc.lat0))
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
                        xy = sc.xy(line)
                        sc.lines.append((xy, half, mode))
                        if c in ("taxiway", "taxilane"):
                            sc.lanes.append(xy)
    return sc


def _aerodrome(sc, x, y):
    """The tier of the aerodrome around (x, y): the polygon holding it, else the nearest feature within
    AERODROME_NEAR_M, else None."""
    p = np.array([[x, y]])
    best, bd = None, AERODROME_NEAR_M
    for tier, geom in sc.aerodromes:
        if len(geom) >= 3 and _pip(geom, p)[0]:
            return tier
        d = float(dnp.hypot(*(geom - (x, y)).T).min())
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

    def why(self, kind, x, y, nx, ny, inside=None, ignore=()):
        """None where an aircraft of `kind` at (x, y) heading (nx, ny) keeps clear (and lies in the ring `inside`), else
        the first thing it meets: "outside", "building", "taxiway" (runways, stopways, taxiways), "taxilane", "aircraft".
        ignore: indexes into self.rings of buildings that are no obstacle (a gate's own jet bridges)."""
        pts = _world(_local_points(kind), x, y, nx, ny)
        r = _radius(kind) + BUILDING_CLEAR_M
        if inside is not None and not _pip(inside, pts).all():
            return "outside"
        for oi, (ring, (x0, y0, x1, y1)) in enumerate(self.rings):
            if x0 - r > x or x1 + r < x or y0 - r > y or y1 + r < y or oi in ignore:
                continue
            if _pip(ring, pts).any() or _seg_dist(pts, ring, np.roll(ring, -1, axis=0)).min() < BUILDING_CLEAR_M:
                return "building"
        if len(self.a):
            lo, hi = np.minimum(self.a, self.b) - r, np.maximum(self.a, self.b) + r
            keep = (lo[:, 0] <= x) & (hi[:, 0] >= x) & (lo[:, 1] <= y) & (hi[:, 1] >= y)
            if keep.any():                      # (a taxilane the nose points along is the stand's own lead-in: no clash)
                ab = self.b[keep] - self.a[keep]
                along = np.abs(ab[:, 0] * nx + ab[:, 1] * ny) > LEAD_IN_COS * np.maximum(dnp.hypot(ab[:, 0], ab[:, 1]), 1e-9)
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
    """(obstacle rings [(ring, bbox)], small buildings [(ring, area, index in the obstacles)]) of the buildings and the
    building parts Features (one, or a list), in the plane: every footprint is an obstacle, whatever its height."""
    obstacles, small = [], []
    blds = [b for b in _flat(bld) if len(b)]
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
                if area < BRIDGE_MAX_M2:
                    small.append((r, area, len(obstacles)))
                obstacles.append((r, (float(r[:, 0].min()), float(r[:, 1].min()), float(r[:, 0].max()),
                                      float(r[:, 1].max()))))
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
    d = np.stack([dnp.cos(ang), dnp.sin(ang)], 1)
    pp = np.tile(p, (len(d), 1))
    fwd, back = _exit_out(ring, pp, d), _exit_out(ring, pp, -d)
    order = sorted(range(len(d)), key=lambda i: (back[i] - 2.0 * fwd[i] < WALL_MIN_M, fwd[i]))
    out, got = [], []
    for i in order:
        if fwd[i] >= RAY_MAX_M or any(float(dnp.matmul(d[i], d[j])) > dmath.cos(math.radians(FACADE_SEP_DEG)) for j in got):
            continue
        got.append(i)
        q = p + d[i] * fwd[i]
        out.append((q, _snap_normal(ring, q, d[i])))
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
        _d, q, j = _nearest_on(ring, p)
        e = np.roll(ring, -1, axis=0)[j] - ring[j]
        ln = max(float(dnp.hypot(*e)), 1e-9)
        n = np.array([-e[1], e[0]]) / ln
        if float(dnp.matmul(n, p - q)) < 0.0 or (float(dnp.matmul(n, p - q)) == 0.0 and bool(_pip(ring, (q + n * 2.0)[None])[0])):
            n = -n                                              # (toward the gate's side: out of the building)
        near, smooth = (q, n), _facade(ring, p)
        out = [near, smooth] if ln >= EDGE_MIN_M else [smooth, near]     # (the nearest edge's own normal first)
    return ring, out


def _bridge(small, gx, gy, out):
    """The jet bridge of a gate: (tip distance along `out` from the gate, lateral centre, half width, indexes of the
    obstacles that are its bridges) of the small building touching it that reaches farthest out (at least BRIDGE_MIN_M;
    every such one is no obstacle to the gate's aircraft), None without."""
    p = np.array([gx, gy])
    tan = np.array([-out[1], out[0]])
    best, ids = None, []
    for ring, _a, oi in small:
        if dnp.hypot(*(ring - p).T).min() > ATTACH_M:
            continue
        d = ring - p
        tip, lat = dnp.matmul(d, out), dnp.matmul(d, tan)
        if tip.max() >= BRIDGE_MIN_M:
            ids.append(oi)
            if best is None or tip.max() > best[0]:
                best = (float(min(tip.max(), BRIDGE_CAP_M)), float((lat.min() + lat.max()) / 2.0),
                        float((lat.max() - lat.min()) / 2.0))
    return None if best is None else best + (tuple(ids),)


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


def _lane_nose(sc, x, y):
    """The unit nose direction of a remote stand at (x, y) lined up with the nearest taxiway or taxilane line within
    REMOTE_LANE_M, None without one: across the line, on the stand's side of it (the tail toward the line: the aircraft
    is pushed back onto it); along it, the nose toward its end, where the line ends within REMOTE_END_M of the stand
    (a stand's own lead-in)."""
    p = np.array([x, y])
    best = None
    for xy in sc.lanes:
        d, q, j, t = _nearest_seg(xy[:-1], xy[1:], p)
        if d <= REMOTE_LANE_M and (best is None or d < best[0] - 1e-6):
            best = (d, q, j, t, xy)
    if best is None:
        return None
    d, q, j, t, xy = best
    e = xy[j + 1] - xy[j]
    u = e / max(float(dnp.hypot(*e)), 1e-9)
    v = p - q
    if 1e-6 < d <= REMOTE_END_M:
        for end, out in ((j == 0 and t <= 1e-6, -u), (j == len(xy) - 2 and t >= 1.0 - 1e-6, u)):
            if end and float(dnp.matmul(v, out)) >= 0.5 * d:            # (beyond the line's end)
                return out
    n = np.array([-u[1], u[0]])
    return -n if float(dnp.matmul(n, v)) < 0.0 else n


def _gate_tries(kind, gx, gy, bearing, term, small):
    """[(centre x, y, nose direction x, y, ignored obstacles)] of a gate's aircraft of `kind` at its terminal's facades,
    the one by the gate's tagged heading first (where it points at the facade), then the facade's normal."""
    length = SPECS[kind][0]
    g = np.array([gx, gy])
    d = None
    if bearing is not None:
        d = np.array([dmath.sin(math.radians(bearing)), dmath.cos(math.radians(bearing))])
    tagged, tries = [], []
    for q, n in term[1]:
        base = float(dnp.matmul(q - g, n)) + NOSE_GAP_M
        br = _bridge(small, gx, gy, n)
        if br is not None:                                  # (the bridge fixes the door and the side)
            lat = br[1] + br[2] + SPECS[kind][3] / 2.0 + BRIDGE_SIDE_M
            c = g + n * (br[0] - BACK_M[kind] + length / 2.0) + np.array([-n[1], n[0]]) * lat
            tries.append((float(c[0]), float(c[1]), -float(n[0]), -float(n[1]), br[3]))
            continue
        c = g + n * (base + length / 2.0)
        tries.append((float(c[0]), float(c[1]), -float(n[0]), -float(n[1]), ()))
        if d is not None and base > 0.0:
            dn = float(dnp.matmul(d, n))
            if dn <= -HEADING_COS:                          # (the tag's nose line through the gate, NOSE_GAP_M off the wall)
                c = g - d * (base / -dn + length / 2.0)
                tagged.append((float(c[0]), float(c[1]), float(d[0]), float(d[1]), ()))
    return tagged + tries


def _first_clear(world, kind, tries):
    """(None, (x, y, nx, ny)) of the first of the tries (centre, nose direction, ignored obstacles) that clears, one that
    meets a building tried again pulled back along its axis (not where a jet bridge fixes the door), else (why, None)."""
    why = "no_terminal"
    for cx, cy, nx, ny, ign in tries:
        for k in range(int(PULL_BACK_MAX_M / PULL_BACK_STEP_M + 1e-9) + 1):
            if k and ign:
                break
            x, y = cx - nx * k * PULL_BACK_STEP_M, cy - ny * k * PULL_BACK_STEP_M
            why = world.why(kind, x, y, nx, ny, ignore=ign)
            if why != "building":
                break
        if why is None:
            return None, (x, y, nx, ny)
    return why, None


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
        lane = _lane_nose(sc, gx, gy) if term is None and bearing is None else None
        remote = None
        if term is None and bearing is None and lane is None and not (is_pos and _apron_nose(sc, gx, gy) is not None):
            remote = _terminal(obstacles, gx, gy, REMOTE_M)
        why = "no_terminal"
        for kind in kinds:
            length = SPECS[kind][0]
            if term is not None:
                tries = _gate_tries(kind, gx, gy, bearing, term, small)
            else:                                       # (a stand off the terminals: the nose wheel stop on the gate's point)
                nose = None
                if bearing is not None:
                    nose = np.array([dmath.sin(math.radians(bearing)), dmath.cos(math.radians(bearing))])
                elif lane is not None:
                    nose = lane
                elif is_pos:
                    nose = _apron_nose(sc, gx, gy)
                elif remote is not None:                # (the nose toward the nearest facade)
                    v = remote[1][-1][0] - (gx, gy)
                    nose = v / max(float(dnp.hypot(*v)), 1e-6)
                tries = [] if nose is None else [(gx - float(nose[0]) * 0.4 * length, gy - float(nose[1]) * 0.4 * length,
                                                  float(nose[0]), float(nose[1]), ())]
            if not tries:
                why = "no_terminal"
                break
            why, got = _first_clear(world, kind, tries)
            if why is None:
                world.add(kind, *got)
                out.append((kind,) + tuple(float(v) for v in got) + ("gate" if term is not None else "remote",))
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
            n = float(dnp.hypot(*v))
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
        ln = dnp.hypot(seg[:, 0], seg[:, 1])
        cum = np.r_[0.0, np.cumsum(ln)]
        # the ring's sense: the inward normal of an edge is its left when it runs counter-clockwise
        sign = 1.0 if float(dnp.dot(closed[:-1, 0], closed[1:, 1]) - dnp.dot(closed[1:, 0], closed[:-1, 1])) > 0 else -1.0
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
                out.append(("light", float(cx), float(cy), float(nx), float(ny), "ga"))
                n_ok += 1
    return out


def stands(feats, buildings=None):
    """[Craft] of a cell's infrastructure Features (see the module docstring), kept on the Features (by the buildings
    it was asked with: a buildings Features, or a list of them, the cell's and its neighbours'); [] for Features
    without airport gates or aprons."""
    if feats is None or len(feats) == 0:
        return []
    buildings = _flat(buildings)
    same = lambda a, b: len(a) == len(b) and all(x is y for x, y in zip(a, b))
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
        placed = [placed[j] for j in drop_overlaps(placed)]     # (the final pass: none overlaps another)
        out = [Craft(k, *sc.latlon(x, y), nx, ny, mode) for k, x, y, nx, ny, mode in placed]
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
    return (math.degrees(dmath.atan2(north, east)) - 90.0) % 360.0


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
    dlon = NEIGHBOUR_M / (aeroways.M_PER_DEG * dmath.cos(math.radians(sc.lat0)))
    out = []
    for nk in key.neighbours():
        w, s, e, n = nk.bounds()
        if ((lon >= w - dlon) & (lon <= e + dlon) & (lat >= s - dlat) & (lat <= n + dlat)).any():
            out.append(nk)
    return out


def _overlap(a, b, margin=AIRCRAFT_CLEAR_M):
    """Do the aircraft a, b ((kind, x, y, nx, ny) in a plane) come within `margin` of each other (footprints: the oriented
    rectangles of their kinds' dimensions)?"""
    if math.hypot(a[1] - b[1], a[2] - b[2]) > _radius(a[0]) + _radius(b[0]) + margin:
        return False
    pa_, pb = _world(_local_points(a[0]), *a[1:5]), _world(_local_points(b[0]), *b[1:5])
    return bool(_in_rects(a[0], *a[1:5], pb, margin).any() or _in_rects(b[0], *b[1:5], pa_, margin).any())


def drop_overlaps(items):
    """The final pass: the indices (ascending) of the aircraft kept of items [(kind, x, y, nx, ny, ...)] (a plane in metres,
    nose direction (nx, ny)): the longer kinds first, then by position, each dropped where its footprint (its kind's
    dimensions, AIRCRAFT_CLEAR_M margin) overlaps one kept already. Deterministic whatever the order."""
    order = sorted(range(len(items)), key=lambda j: (-SPECS[items[j][0]][0], round(float(items[j][2]), 3),
                                                     round(float(items[j][1]), 3), items[j][0]))
    kept, placed = [], []
    for j in order:
        a = tuple(items[j][:5])
        if any(_overlap(a, b) for b in placed):
            continue
        kept.append(j)
        placed.append(a)
    return sorted(kept)


def _dedupe(items, lat, lon):
    """Indices of the items (Craft) kept: drop_overlaps in a local plane. An aircraft drops where it overlaps a kept one of
    another cell (the cells place their own gates' aircraft without each other's)."""
    if not items:
        return []
    kx = aeroways.M_PER_DEG * dnp.cos(np.radians(lat))
    j0 = min(range(len(items)), key=lambda j: (round(float(lat[j]), 6), round(float(lon[j]), 6), items[j].kind))
    plane = [(c.kind, float(lon[j] - lon[j0]) * float(kx[j]), float(lat[j] - lat[j0]) * aeroways.M_PER_DEG, c.ne, c.nn)
             for j, c in enumerate(items)]
    kept = drop_overlaps(plane)
    STATS["cross_cell"] += len(items) - len(kept)
    return kept


def building_layers_fn(md):
    """The buildings_fn of tile_rows / kept_stands for a MapData: a cell's buildings and building_parts Features (the
    parts hold the canopies and covered walkways an aircraft must keep off too)."""
    def fn(key):
        layers = md.cell(key, layers=("buildings", "building_parts"), kind="demand").layers
        return [layers.get("buildings"), layers.get("building_parts")]
    return fn


def _cells_of(frame, box):
    """The cells under a box (a gate's aircraft stands within ~70 m of it: padded 0.001 degrees), [] off the map."""
    import mapcells
    x0, y0, x1, y1 = (float(v) for v in box[:4])
    la, lo, _ = frame.enu_to_geodetic(np.array([x0, x0, x1, x1]), np.array([y0, y1, y0, y1]), np.zeros(4))
    try:
        return mapcells.cells_for_points(la, lo, pad_lat=0.001, pad_lon=0.001, max_cells=64)
    except (ValueError, OverflowError):
        return []


def kept_stands(keys, infra_fn, buildings_fn):
    """[Craft] of the cells `keys` (stands() of each, with its neighbours' buildings), the cross-cell pass applied: what
    tile_rows places (a gate near a cell's edge: its neighbour's aircraft on it). buildings_fn(key) -> a buildings
    Features, or a list of Features (buildings and building_parts), or None."""
    items = []
    for k in keys:
        feats = infra_fn(k)
        if not has_stands(feats):
            continue
        blds = _flat([buildings_fn(k)] + [buildings_fn(nk) for nk in _near_cells(k, feats)])
        items.extend(stands(feats, blds))
    if not items:
        return []
    lat = np.array([c.lat for c in items], np.float64)
    lon = np.array([c.lon for c in items], np.float64)
    return [items[j] for j in _dedupe(items, lat, lon)]


def tile_rows(frame, box, infra_fn, buildings_fn, elev, keys=None):
    """Forest rows [group, x, y, z, yaw, 1, H, 0] of the parked aircraft a tile owns (see the module docstring).
    keys: the box's cells (default: under it)."""
    if keys is None:
        keys = _cells_of(frame, box)
    items = kept_stands(keys, infra_fn, buildings_fn)
    if not items:
        return []
    lat = np.array([c.lat for c in items], np.float64)
    lon = np.array([c.lon for c in items], np.float64)
    e, n, _ = frame.geodetic_to_enu(lat, lon, 0.0)
    e, n = np.asarray(e, np.float64), np.asarray(n, np.float64)
    own = np.flatnonzero(np.asarray(geotiles.box_owns(box, e, n), bool))
    if not len(own):
        return []
    # (the nose direction in this frame: a point 10 m on, with the meridians' convergence)
    kx = aeroways.M_PER_DEG * dnp.cos(np.radians(lat[own]))
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
