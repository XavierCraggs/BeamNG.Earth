"""Airfield windsocks: a windsock beside each paved runway end (or the mapped one), as forest rows of the mod's static
prop group "windsock" (tools/build_windsock.py's shape: an ICAO-style orange / white sock on a 6 m pole, its mouth
facing local +Y, trees.lua CATALOG.windsock). Pure: lat / lon points (tile_rows takes the ground and the frame).

spots(runways) -> [Spot]: for each open runway on land and paved (airports.Runway; an unpaved strip, a water runway and a
closed one have none): at each end IN_M in from the threshold and OUT_BEYOND_M + half the runway's width off the runway
on the LEFT of a pilot at that end looking down the runway (the low-numbered end's is on the runway's +t side in
runwaygeom's frame, the high end's on its -t side: the two stand on opposite sides of the runway, 'on the left' for
each landing direction); a runway shorter than SHORT_M has one at its midpoint (the low end's left side). Dropped where
it would stand on another runway's pavement (CLEAR_M beyond its half width and ends) and where another one's is within
MERGE_M (the first by runway key keeps it: parallel and crossing runways at one airport share a sock rather than ring
the field with them). A Spot is (lat, lon, east, north of the way the sock points along the runway, runway key).
mapped(feats) -> [(lat, lon)]: the windsocks the infrastructure Features map (class "windsock", or the tag
aeroway=windsock; a point). A runway with a mapped windsock within MAPPED_NEAR_M of it has none generated (nor do
others within MERGE_M of a mapped one): the mapped one stands instead, as the data says.
tile_rows(frame, box, infra_fn, runways_fn, elev, wind_deg=None) -> forest rows [group, x, y, z, yaw, 1, H, 0] of the
windsocks a tile owns (each in one tile). Yaw (the server's: counter-clockwise from +x; the shape's +Y at yaw 0 is north):
the sock streams DOWNWIND of wind_deg (the meteorological direction the wind blows FROM, degrees clockwise from north:
the weather message's wind.fromDeg), else along its runway (a runway's two ends' socks point opposite ways: down the
runway of a landing at their end; a mapped one's, along the nearest runway's low-to-high direction).
wind_from(service, lat, lon) -> the fromDeg of the weather already cached for the place (weather.Service; no network:
None when there is none or the wind is calm), for a caller that has the server's weather.

Kept: a runway's candidate spots by its data's signature (a bounded module cache), the runway set's by the signatures of
its runways, a Features' mapped ones on the Features. A tile with no runway costs one membership test.
"""
import math

import numpy as np

import airfieldlights
import aeroways
import geotiles
import runwaygeom

GROUP = "windsock"
WINDSOCK_H = 6.47               # m: the catalogue height of the shape (tools/build_windsock.py height(): 1:1)
IN_M = 300.0                    # m in from the threshold
OUT_BEYOND_M = 75.0             # m: the sock stands this far beyond the runway's edge (the graded strip's half width)
SHORT_M = 800.0                 # a runway shorter than this has one sock, at its midpoint
CLEAR_M = 15.0                  # m beyond another runway's half width and ends where a sock is left out
MERGE_M = 200.0                 # two socks closer than this are one
MAPPED_NEAR_M = 400.0           # a mapped windsock this near a runway stands for its generated ones
CALM_MS = 1.0                   # a wind slower than this has no direction (wind_from)
CACHE_MAX = 512
SET_CACHE_MAX = 64
_KEY = "_windsocks_mapped"
_RUNWAYS = {}
_SETS = {}
M_PER_DEG = aeroways.M_PER_DEG


def _signature(rw):
    return (rw.key, rw.le.lat, rw.le.lon, rw.he.lat, rw.he.lon, float(rw.width_m), bool(rw.closed), bool(rw.paved),
            rw.surface)


def _usable(rw):
    """Does the runway get windsocks (open, on land, paved)?"""
    return not rw.closed and rw.surface != "water" and bool(rw.paved)


def _candidates(rw):
    """The runway's spots before the clash tests: [(lat, lon, east, north, key)], memoised by its data."""
    key = _signature(rw)
    got = _RUNWAYS.get(key)
    if got is None:
        if len(_RUNWAYS) >= CACHE_MAX:
            _RUNWAYS.clear()
        g = runwaygeom.geometry(rw)
        out = g.width / 2.0 + OUT_BEYOND_M
        if g.length < SHORT_M:
            at = [(g.length / 2.0, out, 1.0)]
        else:
            at = [(IN_M, out, 1.0), (g.length - IN_M, -out, -1.0)]
        lat, lon = g.latlon([a[0] for a in at], [a[1] for a in at])
        got = _RUNWAYS[key] = [(float(la), float(lo), a[2] * g.ue, a[2] * g.un, rw.key)
                               for la, lo, a in zip(lat, lon, at)]
    return got


def _on_pavement(runways, lat, lon):
    """Is the point on one of the runways' pavements (their half width + CLEAR_M, their ends + CLEAR_M)?"""
    for rw in runways:
        g = runwaygeom.geometry(rw)
        s, t = g.st(np.array([lat]), np.array([lon]))
        if -CLEAR_M < s[0] < g.length + CLEAR_M and abs(t[0]) < g.width / 2.0 + CLEAR_M:
            return True
    return False


def _apart_m(a, b):
    """The distance between two (lat, lon, ...) points in metres (local plane)."""
    return math.hypot((a[1] - b[1]) * math.cos(math.radians(a[0])), a[0] - b[0]) * M_PER_DEG


def _seg_m(lat, lon, rw):
    """The distance in metres from a point to the runway's centreline segment (local plane)."""
    k = math.cos(math.radians(lat))
    ax, ay = (rw.le.lon - lon) * k * M_PER_DEG, (rw.le.lat - lat) * M_PER_DEG
    bx, by = (rw.he.lon - lon) * k * M_PER_DEG, (rw.he.lat - lat) * M_PER_DEG
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0.0 else min(1.0, max(0.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)


def _sig(runways):
    return tuple(sorted(_signature(rw) for rw in runways))


def _clear_spots(runways):
    """The candidate spots of the runways' open paved runways that are not on any runway's pavement (kept by the set)."""
    land = sorted((rw for rw in runways if rw.surface != "water"), key=lambda rw: rw.key)
    key = _sig(land)
    got = _SETS.get(key)
    if got is None:
        if len(_SETS) >= SET_CACHE_MAX:
            _SETS.clear()
        got = _SETS[key] = [sp for rw in land if _usable(rw) for sp in _candidates(rw)
                            if not _on_pavement(land, sp[0], sp[1])]
    return got


def spots(runways, mapped_points=()):
    """The windsocks of a set of runways (see the module docstring); mapped_points: the mapped windsocks' (lat, lon) that
    stand for their runways' own. Sorted by runway key (spots as (lat, lon, east, north, runway key))."""
    runways = list(runways or ())
    if not runways:
        return []
    near = {rw.key for rw in runways
            if any(_seg_m(p[0], p[1], rw) <= MAPPED_NEAR_M for p in mapped_points)}
    out = []
    for sp in _clear_spots(runways):
        if sp[4] in near or any(_apart_m(sp, p) < MERGE_M for p in mapped_points):
            continue
        if any(_apart_m(sp, o) < MERGE_M for o in out):
            continue
        out.append(sp)
    return out


# ------------------------------------------------------------------------------------------------- the mapped ones
def mapped(feats):
    """The mapped windsocks of infrastructure Features: [(lat, lon)] (class "windsock" or tags aeroway=windsock, points;
    one per half metre). Kept on the Features."""
    if feats is None or len(feats) == 0:
        return []
    got = feats.__dict__.get(_KEY)
    if got is None:
        got = feats.__dict__[_KEY] = _mapped(feats)
    return got


def _mapped(feats):
    import json
    cls, tags = feats.attrs.get("class"), feats.attrs.get("tags")
    hit = np.zeros(len(feats), bool)
    by_class = np.zeros(len(feats), bool)
    if cls is not None:
        by_class = np.asarray(cls).astype(str) == "windsock"
        hit |= by_class
    if tags is not None:
        hit |= np.char.find(np.asarray(tags).astype(str), "windsock") >= 0
    out, seen = [], set()
    for i in np.flatnonzero(hit & (np.asarray(feats.kind) == 1)):
        if not by_class[i]:
            try:
                ok = json.loads(str(tags[i])).get("aeroway") == "windsock"
            except (ValueError, TypeError, AttributeError):
                ok = False
            if not ok:
                continue
        parts = feats.parts(int(i))
        if not parts or not parts[0]:
            continue
        ring = np.asarray(parts[0][0], np.float64)
        if ring.ndim != 2 or not len(ring):
            continue
        lon, lat = float(ring[0][0]), float(ring[0][1])
        k = (round(lat * 2e5), round(lon * 2e5))        # (about half a metre)
        if k not in seen:
            seen.add(k)
            out.append((lat, lon))
    return out


# ------------------------------------------------------------------------------------------------- wind
def wind_from(service, lat, lon):
    """The meteorological wind direction (degrees the wind blows FROM, clockwise from north) of the weather a
    weather.Service already holds for (lat, lon) now: no fetch (the cache's, under its lock), None without one or when
    the wind is calm (under CALM_MS)."""
    if service is None:
        return None
    try:
        with service.lock:
            msg = service.cache.get(service.key(lat, lon, service.clock()))
        wind = (msg or {}).get("wind") or {}
        deg, ms = float(wind["fromDeg"]), float(wind.get("ms", 0.0))
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return deg % 360.0 if math.isfinite(deg) and ms >= CALM_MS else None


def _yaw_downwind(wind_deg):
    """The row yaw of a sock streaming with a wind blowing from wind_deg: it points at compass bearing wind + 180, i.e.
    counter-clockwise from +x 90 - bearing, and the shape's +Y is 90 degrees off +x."""
    return (180.0 - wind_deg) % 360.0


def _yaw_along(east, north):
    """The row yaw of a sock pointing along (east, north)."""
    return (math.degrees(math.atan2(north, east)) - 90.0) % 360.0


# ------------------------------------------------------------------------------------------------- the tile's rows
def tile_rows(frame, box, infra_fn, runways_fn, elev, wind_deg=None, keys=None):
    """Forest rows [group, x, y, z, yaw, 1, WINDSOCK_H, 0] of the windsocks a tile (box: x0, y0, x1, y1 in frame, or a
    geotile's OwnedBox) owns (each in one tile). infra_fn(key) -> the cell's infrastructure Features (or None),
    runways_fn(key) -> the airports.Runways around it (AirportDB.in_cell(key, margin_m=...): at least a runway's reach
    + MERGE_M; the airfield lights' TAXI_REACH_M one will do), elev(lat, lon) -> the (graded) ground in metres (arrays).
    wind_deg: the wind's meteorological direction (None: along the runways). keys: the box's cells (default: under it)."""
    got = airfieldlights._keys_of(frame, box)
    if keys is None:
        keys = got[0]
    runways, pts = {}, {}
    for k in keys:
        rws = list(runways_fn(k) or ())
        if not rws:
            continue
        for rw in rws:
            runways.setdefault(rw.key, rw)
        for p in mapped(infra_fn(k)):
            pts.setdefault((round(p[0] * 2e5), round(p[1] * 2e5)), p)
    if not runways:
        return []
    rws = [runways[k] for k in sorted(runways)]
    pts = list(pts.values())
    wind = None if wind_deg is None or not math.isfinite(float(wind_deg)) else float(wind_deg) % 360.0
    items = [(sp[0], sp[1], sp[2], sp[3]) for sp in spots(rws, pts)]
    for p in pts:                           # (a mapped one points along its nearest runway when no wind says)
        rw = min(rws, key=lambda r: _seg_m(p[0], p[1], r))
        items.append((p[0], p[1]) + _along(rw))
    if not items:
        return []
    lat, lon = (np.array([i[j] for i in items], np.float64) for j in (0, 1))
    e, n, _ = frame.geodetic_to_enu(lat, lon, 0.0)
    e, n = np.asarray(e, np.float64), np.asarray(n, np.float64)
    own = np.flatnonzero(np.asarray(geotiles.box_owns(box, e, n), bool))
    if not len(own):
        return []
    h = np.asarray(elev(lat[own], lon[own]), np.float64)
    z = np.asarray(frame.geodetic_to_enu(lat[own], lon[own], h)[2], np.float64)
    rows = []
    for j, x, y, zz in zip(own.tolist(), e[own], n[own], z):
        yaw = _yaw_downwind(wind) if wind is not None else _yaw_along(items[j][2], items[j][3])
        rows.append([GROUP, round(float(x), 2), round(float(y), 2), round(float(zz), 2), round(yaw, 1), 1.0,
                     WINDSOCK_H, 0.0])
    return rows


def _along(rw):
    """(east, north) of the runway's low-to-high direction (a local plane at its middle)."""
    k = math.cos(math.radians((rw.le.lat + rw.he.lat) / 2.0))
    return (rw.he.lon - rw.le.lon) * k, rw.he.lat - rw.le.lat
