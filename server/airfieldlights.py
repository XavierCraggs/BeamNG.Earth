"""Airfield lights: a lit runway's edge, threshold and end lights and an airport's blue taxiway edge lights, as points
of light for the mod's glow items (the street lamps' lampglow mechanism: one forest item per light, a glowing ball,
night only; GROUPS names the group of each colour). Pure: lat / lon points, no heights (tile_rows takes the ground).

runway_lights(rw) -> Lights: only a runway with lighted set and not closed (nor on water). In the runway's frame
(runwaygeom: s along it from the low-numbered end, t across): white edge lights every EDGE_SPACING_M (a whole number of
equal steps, a light at each end) EDGE_OUT_M outside the edge both sides, the last min(CAUTION_M, a third) of each end
yellow (ICAO Annex 14's caution zone); a green threshold bar across the runway at each threshold (the
displaced one, when the data has it) and a red end bar BAR_OUT_M beyond each end, a light every BAR_SPACING_M across.
taxiway_lights(feats, runways) -> Lights: blue lights TAXI_SPACING_M apart along both edges (TAXI_OUT_M outside) of the
paved taxiways (infrastructure Features: subtype "airport", class "taxiway"; the width, the unpaved test and the
defaults are aeroways') at airports whose nearest open runway (within TAXI_REACH_M) is lighted; none inside an apron,
inside a runway's half width + RUNWAY_CLEAR_M, nor within another taxiway's or taxilane's pavement (a junction's, the
inner side of a tight bend) nor on a way tagged lit=no.
tile_rows(frame, box, infra_fn, runways_fn, elev) -> forest rows [group, x, y, z, yaw, scale, height, rank] of the
lights a road tile owns (the group's shape is 1 m high: height 1), as areaprops' rows.

Every light is a pure function of its runway's data or its Features, kept: a runway's by its data's signature (a bounded
module cache), a Features' on the Features by the runways it was asked with (so every tile of a cell shares them). A
cell with no airport costs one membership test; a Features of anywhere else gives nothing.
"""
import math

import numpy as np

import aeroways
import geotiles
import polygon
import runwaygeom

WHITE, GREEN, RED, BLUE, YELLOW = "white", "green", "red", "blue", "yellow"
COLOURS = (WHITE, GREEN, RED, BLUE, YELLOW)
EDGE, THRESHOLD, END, TAXI = "edge", "threshold", "end", "taxi"
KINDS = (EDGE, THRESHOLD, END, TAXI)
# The mod's group per colour: one glow ball shape + tinted night materials each (tools/build_lamp_glow.py's balls in the
# colour: nightlights.lua MATERIALS / trees.lua CATALOG, GROUP_MAX_M, groupOff, setGroupEnabled at dusk).
GROUPS = {c: "afl_" + c for c in COLOURS}
GROUP_H = 1.0                   # m: the catalog height of the glow shapes (a row's height over it is its scale)
LIFT_M = 0.3                    # m: a light's centre over the ground

EDGE_SPACING_M = 60.0           # runway edge lights (FAA AC 150/5340-30 / ICAO: at most 60 m)
EDGE_OUT_M = 1.0                # m outside the runway edge
CAUTION_M = 600.0               # the yellow end zone of the edge lights (or a third of the runway: the shorter)
BAR_SPACING_M = 4.0             # across the threshold and end bars
BAR_OUT_M = 1.0                 # the end bar this far beyond the runway end
DISPLACED_MAX = 1.0 / 3.0       # a displaced threshold past this share of the runway is a data error: none
TAXI_SPACING_M = 30.0           # taxiway edge lights (straight parts; ICAO 5.3.18: at most 60 m, 7.5 m on curves)
TAXI_OUT_M = 1.0                # m outside the taxiway's edge
TAXI_REACH_M = 5000.0           # the nearest open runway is further than this: no airport here
RUNWAY_CLEAR_M = 3.0            # m beyond a runway's half width / ends where a taxiway's lights are left out
PAVEMENT_CLEAR_M = 0.5          # m beyond another way's half width
CACHE_MAX = 512                 # runway cache entries
_KEY = "_airfield_lights"
_CELL_M = 150.0                 # m: the squares the pavement test groups candidates in
_RUNWAYS = {}


class Lights:
    """Light points: lat, lon (float64 (n,)), colour and kind (int8 (n,): indexes of COLOURS and KINDS)."""
    __slots__ = ("lat", "lon", "colour", "kind")

    def __init__(self, lat=(), lon=(), colour=(), kind=()):
        self.lat = np.asarray(lat, np.float64).reshape(-1)
        self.lon = np.asarray(lon, np.float64).reshape(-1)
        self.colour = np.asarray(colour, np.int8).reshape(-1)
        self.kind = np.asarray(kind, np.int8).reshape(-1)

    def __len__(self):
        return len(self.lat)

    def rows(self):
        """[(lat, lon, colour name, kind name)]."""
        return [(float(a), float(o), COLOURS[c], KINDS[k]) for a, o, c, k in
                zip(self.lat, self.lon, self.colour.tolist(), self.kind.tolist())]

    @staticmethod
    def join(parts):
        parts = [p for p in parts if len(p)]
        if not parts:
            return Lights()
        return Lights(*(np.concatenate([getattr(p, f) for p in parts]) for f in Lights.__slots__))


# ------------------------------------------------------------------------------------------------- the runways
def _signature(rw):
    return (rw.key, bool(rw.lighted), bool(rw.closed), rw.le.lat, rw.le.lon, rw.he.lat, rw.he.lon, float(rw.width_m),
            rw.le.displaced_m, rw.he.displaced_m)


def _on(rw):
    """Is the runway one with lights (lighted, open, on land)?"""
    return bool(rw.lighted) and not rw.closed and rw.surface != "water"


def _bar(s, width, colour, kind):
    """Lights across the runway at s: BAR_SPACING_M apart from edge to edge, as (s, t, colour, kind) lists."""
    t = np.linspace(-width / 2.0, width / 2.0, max(1, math.ceil(width / BAR_SPACING_M)) + 1)
    return np.full(len(t), s), t, np.full(len(t), COLOURS.index(colour)), np.full(len(t), KINDS.index(kind))


def _lights_of(rw):
    g = runwaygeom.geometry(rw)
    L, W = g.length, g.width
    n = max(1, math.ceil(L / EDGE_SPACING_M))
    s = np.linspace(0.0, L, n + 1)
    zone = min(CAUTION_M, L / 3.0)
    colour = np.where((s < zone - 1e-6) | (s > L - zone + 1e-6), COLOURS.index(YELLOW), COLOURS.index(WHITE))
    parts = [(np.r_[s, s], np.r_[np.full(len(s), -(W / 2.0 + EDGE_OUT_M)), np.full(len(s), W / 2.0 + EDGE_OUT_M)],
              np.r_[colour, colour], np.full(2 * len(s), KINDS.index(EDGE)))]
    for at_le, end in ((True, rw.le), (False, rw.he)):
        d = float(end.displaced_m or 0.0)
        d = d if 0.0 < d <= L * DISPLACED_MAX else 0.0
        sign = 1.0 if at_le else -1.0
        base = 0.0 if at_le else L
        parts.append(_bar(base + sign * d, W, GREEN, THRESHOLD))
        parts.append(_bar(base - sign * BAR_OUT_M, W, RED, END))
    ss, tt, cc, kk = (np.concatenate(p) for p in zip(*parts))
    lat, lon = g.latlon(ss, tt)
    return Lights(lat, lon, cc, kk)


def runway_lights(rw):
    """The Lights of a runway (airports.Runway), none unless lighted and open; memoised by its data."""
    if not _on(rw):
        return Lights()
    key = _signature(rw)
    got = _RUNWAYS.get(key)
    if got is None:
        if len(_RUNWAYS) >= CACHE_MAX:
            _RUNWAYS.clear()
        got = _RUNWAYS[key] = _lights_of(rw)
    return got


# ------------------------------------------------------------------------------------------------- the taxiways
def _width(tags, cls, intl):
    """A taxiway's or taxilane's width: the tag's, else aeroways' default by class and airport."""
    w = aeroways.width_tag(tags.get("width"))
    if w is not None:
        return w
    if cls == "taxiway":
        return aeroways.TAXIWAY_INTL_M if intl else aeroways.TAXIWAY_M
    return aeroways.TAXILANE_INTL_M if intl else aeroways.TAXILANE_M


def _seg_dist_min(p, a, b, margin):
    """The smallest (distance to a segment a->b (S, 2) - its margin (S,)) of each point p (m, 2): negative inside. Points
    in _CELL_M squares, each against the segments whose box reaches the square (a big airport is thousands of both)."""
    out = np.full(len(p), np.inf)
    lo, hi = np.minimum(a, b) - margin[:, None], np.maximum(a, b) + margin[:, None]
    cell = np.floor(p / _CELL_M).astype(np.int64)
    _, inv = np.unique(cell, axis=0, return_inverse=True)
    for c in range(int(inv.max()) + 1 if len(p) else 0):
        idx = np.flatnonzero(inv == c)
        q = p[idx]
        near = np.flatnonzero(((hi >= q.min(axis=0)) & (lo <= q.max(axis=0))).all(axis=1))
        if not len(near):
            continue
        sa, sb, sm = a[near], b[near], margin[near]
        ab = sb - sa
        ab2 = np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-12)
        qq = q[:, None, :]
        t = np.clip(np.einsum("mij,ij->mi", qq - sa, ab) / ab2, 0.0, 1.0)
        d = np.hypot(*(sa + t[..., None] * ab - qq).transpose(2, 0, 1))
        out[idx] = (d - sm).min(axis=1)
    return out


def _sig(runways):
    return tuple(sorted(_signature(rw) for rw in runways))


def _taxiway_lights(feats, runways):
    sub, cls = feats.attrs.get("subtype"), feats.attrs.get("class")
    if sub is None or cls is None:
        return Lights()
    air = np.asarray(sub).astype(str) == aeroways.SUBTYPE
    if not air.any():
        return Lights()
    cls = np.asarray(cls).astype(str)
    intl = bool((air & (cls == aeroways.AERODROME)).any())
    land = [rw for rw in runways if rw.surface != "water"]
    open_ = [rw for rw in land if not rw.closed]
    if not open_:
        return Lights()
    lat0, lon0 = open_[0].le.lat, open_[0].le.lon
    kx = aeroways.M_PER_DEG * math.cos(math.radians(lat0))

    def local(ll):                          # (n, 2) lon / lat -> metres about the first runway's end
        return np.c_[(ll[:, 0] - lon0) * kx, (ll[:, 1] - lat0) * aeroways.M_PER_DEG]
    rend = [(local(np.array([[rw.le.lon, rw.le.lat], [rw.he.lon, rw.he.lat]])), rw) for rw in open_]
    ways = []                               # (xy (n, 2), half width, lit) of the paved taxiways and taxilanes
    for i in np.flatnonzero(air & np.isin(cls, aeroways.WAYS)):
        if int(feats.kind[i]) != 2:
            continue
        tags = aeroways._tags(feats, i)
        if aeroways._unpaved(feats, i, tags):
            continue
        half = _width(tags, cls[i], intl) / 2.0
        no_lit = str(tags.get("lit", "")).strip().lower() in ("no", "false", "0")
        for part in feats.parts(i):
            for line in part:
                if len(line) < 2:
                    continue
                xy = local(np.asarray(line, np.float64))
                xy = xy[np.r_[True, np.hypot(*np.diff(xy, axis=0).T) > 1e-3]]
                if len(xy) < 2:
                    continue
                lit = cls[i] == "taxiway" and not no_lit and _lit_at(xy, rend)
                ways.append((xy, half, bool(lit)))
    if not any(w[2] for w in ways):
        return Lights()
    cand, owner = [], []
    for xy, half, lit in ways:
        if not lit:
            continue
        d = np.diff(xy, axis=0)
        seg = np.hypot(d[:, 0], d[:, 1])
        cum = np.r_[0.0, np.cumsum(seg)]
        n = max(1, math.ceil(cum[-1] / TAXI_SPACING_M))
        st = np.linspace(0.0, cum[-1], n + 1)
        k = np.clip(np.searchsorted(cum, st, side="right") - 1, 0, len(seg) - 1)
        p = xy[k] + ((st - cum[k]) / seg[k])[:, None] * d[k]
        nrm = np.c_[-d[k, 1], d[k, 0]] / seg[k][:, None]
        off = nrm * (half + TAXI_OUT_M)
        cand += [p + off, p - off]
    pts = np.concatenate(cand)
    # not within any paved way's pavement (its own other segments at a tight bend, the ways it joins)
    a = np.concatenate([w[0][:-1] for w in ways])
    b = np.concatenate([w[0][1:] for w in ways])
    margin = np.concatenate([np.full(len(w[0]) - 1, w[1] + PAVEMENT_CLEAR_M) for w in ways])
    keep = _seg_dist_min(pts, a, b, margin) >= 0.0
    # nor on a runway (half width + RUNWAY_CLEAR_M, its length + the same at each end)
    for (e, rw) in ((local(np.array([[r.le.lon, r.le.lat], [r.he.lon, r.he.lat]])), r) for r in land):
        v = e[1] - e[0]
        length = float(np.hypot(*v))
        if length < 1.0:
            continue
        u = v / length
        q = pts - e[0]
        s, t = q @ u, q[:, 0] * -u[1] + q[:, 1] * u[0]
        keep &= ~((s > -RUNWAY_CLEAR_M) & (s < length + RUNWAY_CLEAR_M) & (np.abs(t) < rw.width_m / 2.0 + RUNWAY_CLEAR_M))
    pts = pts[keep]
    lat, lon = lat0 + pts[:, 1] / aeroways.M_PER_DEG, lon0 + pts[:, 0] / kx
    # nor inside an apron
    for i in np.flatnonzero(air & (cls == aeroways.APRON)):
        if int(feats.kind[i]) != 3 or not len(lat):
            continue
        for part in feats.parts(i):
            if not part or len(part[0]) < 3:
                continue
            ring = np.asarray(part[0], np.float64)
            inside = ((lon >= ring[:, 0].min()) & (lon <= ring[:, 0].max()) & (lat >= ring[:, 1].min())
                      & (lat <= ring[:, 1].max()))
            if inside.any():
                idx = np.flatnonzero(inside)
                hit = polygon.contains_points(ring[:, :2], np.c_[lon[idx], lat[idx]])
                inside[idx] = hit
                lat, lon = lat[~inside], lon[~inside]
    return Lights(lat, lon, np.full(len(lat), COLOURS.index(BLUE)), np.full(len(lat), KINDS.index(TAXI)))


def _lit_at(xy, rend):
    """Is the way's middle within TAXI_REACH_M of an open runway, the nearest one lighted?"""
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.r_[0.0, np.cumsum(seg)]
    k = min(int(np.searchsorted(cum, cum[-1] / 2.0, side="right")) - 1, len(seg) - 1)
    m = xy[k] + (cum[-1] / 2.0 - cum[k]) / max(seg[k], 1e-9) * (xy[k + 1] - xy[k])
    best, lit = np.inf, False
    for e, rw in rend:
        v = e[1] - e[0]
        t = float(np.clip((m - e[0]) @ v / max(float(v @ v), 1e-9), 0.0, 1.0))
        d = float(np.hypot(*(e[0] + t * v - m)))
        if d < best:
            best, lit = d, bool(rw.lighted)
    return lit and best <= TAXI_REACH_M


def taxiway_lights(feats, runways):
    """The Lights of the taxiways in Features feats (see the module docstring); runways: the airports.Runways around
    (their lighting and distance decide, closed ones are no airport's). Kept on the Features by the runways' data."""
    runways = list(runways or ())
    if feats is None or len(feats) == 0 or not runways:
        return Lights()
    cache = feats.__dict__.setdefault(_KEY, {})
    key = _sig(runways)
    got = cache.get(key)
    if got is None:
        if len(cache) >= 8:
            cache.clear()
        got = cache[key] = _taxiway_lights(feats, runways)
    return got


# ------------------------------------------------------------------------------------------------- the tile's rows
def _keys_of(frame, box):
    import mapcells
    x0, y0, x1, y1 = (float(v) for v in box[:4])
    la, lo, _ = frame.enu_to_geodetic(np.array([x0, x0, x1, x1]), np.array([y0, y1, y0, y1]), np.zeros(4))
    try:
        return mapcells.cells_for_points(la, lo, pad_lat=0.0005, pad_lon=0.0005, max_cells=64), (la, lo)
    except (ValueError, OverflowError):
        return [], (la, lo)


def tile_rows(frame, box, infra_fn, runways_fn, elev, keys=None):
    """Forest rows [group, x, y, z, yaw, 1, GROUP_H, 0] of the airfield lights a tile (box: x0, y0, x1, y1 in frame, or
    a geotile's OwnedBox) owns (each light in one tile). infra_fn(key) -> the cell's infrastructure Features (or None),
    runways_fn(key) -> the airports.Runways to light it by (AirportDB.in_cell(key, margin_m=TAXI_REACH_M)), elev(lat,
    lon) -> the (graded) ground in metres (arrays). keys: the box's cells (default: those under it)."""
    got = _keys_of(frame, box)
    if keys is None:
        keys = got[0]
    la, lo = got[1]
    parts, seen = [], {}
    for k in keys:
        runways = list(runways_fn(k) or ())
        if not runways:
            continue
        for rw in runways:
            if rw.key not in seen:
                seen[rw.key] = True
                parts.append(runway_lights(rw))
        parts.append(taxiway_lights(infra_fn(k), runways))
    lights = Lights.join(parts)
    if not len(lights):
        return []
    pad = 0.0005                            # (degrees: the box's corners' lat / lon, a little wider)
    near = np.flatnonzero((lights.lat >= la.min() - pad) & (lights.lat <= la.max() + pad)
                          & (lights.lon >= lo.min() - pad) & (lights.lon <= lo.max() + pad))
    if not len(near):
        return []
    lat, lon = lights.lat[near], lights.lon[near]
    e, n, _ = frame.geodetic_to_enu(lat, lon, 0.0)
    e, n = np.asarray(e, np.float64), np.asarray(n, np.float64)
    own = np.flatnonzero(np.asarray(geotiles.box_owns(box, e, n), bool))
    if not len(own):
        return []
    # (a Features cut at a cell's edge or listed in two cells gives a light twice: one per half metre)
    _, first = np.unique(np.round(np.c_[e[own], n[own]] * 2.0).astype(np.int64), axis=0, return_index=True)
    own = own[np.sort(first)]
    lat, lon, e, n, near = lat[own], lon[own], e[own], n[own], near[own]
    h = np.asarray(elev(lat, lon), np.float64)
    z = np.asarray(frame.geodetic_to_enu(lat, lon, h)[2], np.float64) + LIFT_M
    groups = [GROUPS[COLOURS[c]] for c in lights.colour[near].tolist()]
    return [[g, round(float(x), 2), round(float(y), 2), round(float(h_), 2), 0.0, 1.0, GROUP_H, 0.0]
            for g, x, y, h_ in zip(groups, e, n, z)]
