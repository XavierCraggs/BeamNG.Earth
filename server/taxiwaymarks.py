"""Painted taxiway markings: the yellow centreline along every paved taxiway and taxilane, and the runway holding
position marking where a taxiway meets a runway (the ground of an airfield read as bare asphalt: only the runways
carried paint, runwaymarks).

strokes(feats_list) -> [(lat0, lon0, lat1, lon1, width, kind, color)]: the Overture "infrastructure" Features (subtype
"airport") of the cells around a block, as the strokes runwaymarks.to_world gives a runway's (AirportGrader._marks):
  * "taxi_centreline" (yellow, CENTRE_W_M): along each way's mapped line, cut away within the half width plus
    RUNWAY_GAP_M of a runway centreline the way ends on or crosses (a taxiway is mapped to the runway's centreline: the
    line must not run across the runway),
  * "hold_solid" / "hold_dashed" (yellow, HOLD_LINE_W_M): ICAO pattern A across the way's width where it enters a
    runway, four lines HOLD_LINE_W_M + HOLD_LINE_GAP_M apart, the two dashed nearer the runway (its first at HOLD_DIST_M
    from the runway's centreline, along the way) and the two solid ones on the taxiway side. A mapped
    aeroway=holding_position point on the way (class or tag) puts the marking there instead.
The widths are aeroways' (the width tag, else a default by class and aerodrome); a way or runway line is read as
aeroways reads it (airport subtype, class, unpaved surfaces skipped, kind-2 lines, JOIN_TOL_M). A feature is in the
Features of every cell it touches: those are read once (by id) and the strokes of a list of Features are memoized on its
first (bounded), so every tile of a block shares them. Pure: no ground, no frame.

Stand lead-ins (strokes / tile_chunks take `stands`, parkedaircraft's Craft list of the cells, parkedaircraft.kept_stands):
for each gate or remote stand (not a general-aviation row) a yellow line (CENTRE_KIND, CENTRE_W_M: the same paint) from the
taxiway or taxilane that the aircraft's axis (extended tail-ward) meets nearest: along that line, then a quadratic Bezier
arc (tangent length of a radius of half the wingspan: LEAD_RADIUS_K; tighter where the lane or the straight run is short)
into a straight run along the axis to the nose, and a stop bar STOP_BAR_M across the axis at the nose. A lane that ends
short of the axis is carried on straight (up to LEAD_EXT_M) to it; a lane's end the nose points along (the stand's own
mapped lead-in) is carried on to the nose. A stand with no lane gets nothing. The mapped lines are cut only at runways (not
at an apron's edge).

scene(feats_list) -> Scene: the same read (the ways with their `ref`, the runways with theirs, the runway holding
positions) in one local metre frame, for the airfield signs (airfieldsigns: a runway's signs stand at those positions).

tile_chunks(feats_list, frame, tx, ty, elev, tile_bbox) -> road chunks ({"m", "w", "tl", "p", "n"}) of the tile, as
AirportGrader.tile_chunks draws the runway markings (airportgrade.MARK_LOOK, MARK_PIECE_M, MARK_NODE_M): a centreline
is one polyline cut into pieces (so its bends are one road), each piece in the tile of its midpoint.
"""
import logging
import weakref

import numpy as np

import aeroways
import airportgrade
import dmath
import dnp
import geodesy
import geotiles
import parkedaircraft as pa

log = logging.getLogger(__name__)

CENTRE_W_M = 0.15           # m: the centreline's width (ICAO Annex 14: 0.15 m on a taxiway, 0.3 m on a runway's)
CENTRE_KIND = "taxi_centreline"
COLOR = "yellow"
RUNWAY_GAP_M = 1.0          # the centreline stops this far outside a runway's edge
HOLD_DIST_M = 60.0          # the holding position's distance from the runway centreline (ICAO code 3 / 4: 75 m to 90 m)
HOLD_LINE_W_M = 0.15        # pattern A: four lines this wide, this far apart (two solid, two dashed)
HOLD_LINE_GAP_M = 0.15
HOLD_DASH_M = 1.0           # the dashed lines' dash and gap
HOLD_DASH_GAP_M = 1.0
HOLD_SNAP_M = 4.0           # a holding_position point this far off a way's edge is on it
HOLD_MAX_M = 150.0          # ... and one further than this from the runway's centreline holds something else (an ILS)
HOLD_KIND = {True: "hold_solid", False: "hold_dashed"}
MIN_RUN_M = 0.5             # a centreline fragment shorter than this (a sliver beside a cut) is dropped
REACH_M = 150.0             # the margin round a tile whose cells the hook reads (a runway's and a way's join)
CACHE_MAX = 8               # strokes kept per first Features (one per list of cells asked)
HOLD_POINT = "holding_position"
LEAD_MODES = ("gate", "remote")     # the stands (parkedaircraft's Craft.mode) that get a lead-in
LEAD_RADIUS_K = 0.5                 # the lead-in's curve: the radius of this of the wingspan
LEAD_MAX_M = 150.0                  # a lane meeting the axis further than this behind the nose is none
LEAD_EXT_M = 80.0                   # a lane's end carried on to the axis by up to this far
LEAD_STRAIGHT_M = 2.0               # the straight run along the axis at least this long
LEAD_D_MIN_M = 2.0                  # the curve's tangent length at least this
LEAD_MIN_SIN = 0.17                 # a lane within 10 degrees of the axis (sine) is not crossed by it
ALONG_COS = 0.94                    # a lane end the nose points along (20 degrees) ...
ALONG_LAT_M = 2.0                   # ... within this of the axis, is the stand's own lead-in
STOP_BAR_M = 3.0                    # the stop bar's length across the axis
_RAW = "_taxiway_raw"
_MEMO = "_taxiway_marks"
_SCENE = "_taxiway_scene"
_EPS = 1e-9


def _raw(feats):
    """What of feats' airport features the markings read, kept on it: [(id, lonlat (n, 2), class, width tag or None,
    ref)] of its way lines, [(id, lonlat, width tag or None, ref)] of the runway lines (ref: the `ref` tag, "" when
    none: the airfield signs' designators), [(id, lon, lat)] of the holding positions, and whether an international
    aerodrome is in it."""
    got = feats.__dict__.get(_RAW)
    if got is not None:
        return got
    ways, runways, holds, intl = [], [], [], False
    sub, cls = feats.attrs.get("subtype"), feats.attrs.get("class")
    if sub is not None and cls is not None and len(feats):
        air = np.asarray(sub).astype(str) == aeroways.SUBTYPE
        cls = np.asarray(cls).astype(str)
        intl = bool((air & (cls == aeroways.AERODROME)).any())
        kinds = np.asarray(feats.kind)
        for i in np.flatnonzero(air & (np.isin(cls, (aeroways.RUNWAY,) + aeroways.WAYS) | (kinds == 1))):
            tags = aeroways._tags(feats, i)
            kind = int(feats.kind[i])
            c = cls[i]
            if kind == 1 and (c == HOLD_POINT or tags.get("aeroway") == HOLD_POINT):
                if "runway" in str(tags.get("holding_position:type") or "runway"):       # (not an ILS or intermediate)
                    holds += [(str(feats.ids[i]), float(ln[0][0]), float(ln[0][1]))
                              for part in feats.parts(i) for ln in part if len(ln)]
            elif kind == 2 and c == aeroways.RUNWAY:
                w = aeroways.width_tag(tags.get("width"))
                runways += [(str(feats.ids[i]), np.asarray(ln, np.float64), w, str(tags.get("ref") or "").strip())
                            for part in feats.parts(i) for ln in part if len(ln) >= 2]
            elif kind == 2 and c in aeroways.WAYS and not aeroways._unpaved(feats, i, tags):
                w = aeroways.width_tag(tags.get("width"))
                ways += [(str(feats.ids[i]), np.asarray(ln, np.float64), c, w, str(tags.get("ref") or "").strip())
                         for part in feats.parts(i) for ln in part if len(ln) >= 2]
    got = feats.__dict__[_RAW] = (ways, runways, holds, intl)
    return got


def _pts_dist(pts, segs):
    """The distance from each point of pts (k, 2) to the nearest of the segments segs (m, 2, 2): (k,)."""
    a = segs[:, 0]
    ab = segs[:, 1] - a
    ap = pts[:, None, :] - a[None]
    t = np.clip((ap * ab[None]).sum(axis=2) / np.maximum((ab * ab).sum(axis=1), 1e-12)[None], 0.0, 1.0)
    d = ap - t[..., None] * ab[None]
    return np.sqrt((d * d).sum(axis=2)).min(axis=1)


def _slab(q, dq, lo, hi):
    """The parameters t where lo <= q + t dq <= hi, as arrays (t0, t1) (empty: t0 > t1): q, dq arrays."""
    flat = np.abs(dq) < _EPS
    with np.errstate(divide="ignore", invalid="ignore"):
        ta, tb = (lo - q) / dq, (hi - q) / dq
    t0, t1 = np.minimum(ta, tb), np.maximum(ta, tb)
    inside = (q >= lo) & (q <= hi)
    return (np.where(flat, np.where(inside, -np.inf, np.inf), t0), np.where(flat, np.where(inside, np.inf, -np.inf), t1))


def _stadium(a, b, r0, r1, d):
    """Where the segments a -> b (m, 2) are within d of the segment r0 -> r1: the parameter interval (lo, hi) of each
    (lo >= hi: nowhere). The stadium is convex: the hull of the parts (the rectangle along the segment, a disc at each
    end) is the whole."""
    dv = b - a
    r = r1 - r0
    length = float(dnp.hypot(*r))
    los, his = [], []
    for c in (r0, r1):                          # the discs: |a + t dv - c|^2 <= d^2
        ac = a - c
        qa = dnp.vecdot(dv, dv)
        qb = 2.0 * dnp.vecdot(dv, ac)
        qc = dnp.vecdot(ac, ac) - d * d
        disc = qb * qb - 4.0 * qa * qc
        ok = (disc >= 0) & (qa > _EPS)
        sq = np.sqrt(np.where(ok, disc, 0.0))
        with np.errstate(divide="ignore", invalid="ignore"):
            lo, hi = (-qb - sq) / (2.0 * qa), (-qb + sq) / (2.0 * qa)
        still = (qa <= _EPS) & (qc <= 0)        # (a point: inside or not)
        los.append(np.where(ok, lo, np.where(still, -np.inf, np.inf)))
        his.append(np.where(ok, hi, np.where(still, np.inf, -np.inf)))
    if length > _EPS:                           # the rectangle: along 0..length, across +-d
        ur = r / length
        nr = np.array([-ur[1], ur[0]])
        ua, du = dnp.matmul(a - r0, ur), dnp.matmul(dv, ur)
        va, dvv = dnp.matmul(a - r0, nr), dnp.matmul(dv, nr)
        s0, s1 = _slab(ua, du, 0.0, length)
        c0, c1 = _slab(va, dvv, -d, d)
        lo, hi = np.maximum(s0, c0), np.minimum(s1, c1)
        los.append(lo)
        his.append(hi)
    lo, hi = np.stack(los), np.stack(his)
    good = lo < hi
    lo = np.where(good, lo, np.inf).min(axis=0)
    hi = np.where(good, hi, -np.inf).max(axis=0)
    return np.maximum(lo, 0.0), np.minimum(hi, 1.0)


def _runway_blocks(xy_list, runways, gap):
    """Per way (xy (n, 2)) the blocked parameter intervals of each of its segments: [{segment: [(lo, hi)]}], the parts
    within a runway's half width + gap of its centreline. runways: [(xy, half)]. Only the way segments near a runway
    are looked at (a bounding box test), the rest of a cell's taxiways are not touched."""
    out = [dict() for _ in xy_list]
    if not runways or not xy_list:
        return out
    a = np.concatenate([xy[:-1] for xy in xy_list])
    b = np.concatenate([xy[1:] for xy in xy_list])
    owner = np.concatenate([np.full(len(xy) - 1, i) for i, xy in enumerate(xy_list)])
    first = np.concatenate([[0], np.cumsum([len(xy) - 1 for xy in xy_list])])
    lo_, hi_ = np.minimum(a, b), np.maximum(a, b)
    for rxy, half in runways:
        d = half + gap
        for r0, r1 in zip(rxy[:-1], rxy[1:]):
            near = np.flatnonzero(np.all((hi_ >= np.minimum(r0, r1) - d) & (lo_ <= np.maximum(r0, r1) + d), axis=1))
            if not len(near):
                continue
            lo, hi = _stadium(a[near], b[near], r0, r1, d)
            for j, l, h in zip(near[lo < hi], lo[lo < hi], hi[lo < hi]):
                out[owner[j]].setdefault(int(j - first[owner[j]]), []).append((float(l), float(h)))
    return out


def _free_runs(xy, blocked):
    """The polylines (k, 2) of the way xy with its blocked intervals ({segment: [(lo, hi)]}) cut out."""
    runs, cur = [], None
    for j in range(len(xy) - 1):
        a, d = xy[j], xy[j + 1] - xy[j]
        free, at = [], 0.0
        for lo, hi in sorted(blocked.get(j, ())):
            if lo > at + _EPS:
                free.append((at, lo))
            at = max(at, hi)
        if at < 1.0 - _EPS:
            free.append((at, 1.0))
        for lo, hi in free:
            if cur is not None and lo <= _EPS:
                cur.append(a + hi * d)
            else:
                if cur is not None:
                    runs.append(cur)
                cur = [a + lo * d, a + hi * d]
            if hi < 1.0 - _EPS:
                runs.append(cur)
                cur = None
        if not free and cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    out = []
    for r in runs:
        r = np.asarray(r)
        if float(dnp.hypot(*np.diff(r, axis=0).T).sum()) >= MIN_RUN_M:
            out.append(r)
    return out


def _joins(xy, rsegs):
    """Where the way xy meets the runway whose centreline segments are rsegs (m, 2, 2): [(point, [head, ...])], a head
    the way's line (k, 2) from the point away from the runway. The way's end within JOIN_TOL_M of the centreline
    (one head), a vertex there inside the way and a crossing of the centreline (two)."""
    dist = _pts_dist(xy, rsegs)
    out = []
    n = len(xy)
    for k in np.flatnonzero(dist <= aeroways.JOIN_TOL_M):
        if k == 0:
            out.append((xy[0], [xy]))
        elif k == n - 1:
            out.append((xy[-1], [xy[::-1]]))
        else:
            out.append((xy[k], [xy[k:], xy[k::-1]]))
    a, d = xy[:-1][:, None, :], np.diff(xy, axis=0)[:, None, :]          # (way segments, runway segments) crossings
    c, f = rsegs[:, 0][None], (rsegs[:, 1] - rsegs[:, 0])[None]
    den = d[..., 0] * f[..., 1] - d[..., 1] * f[..., 0]
    ac = c - a
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (ac[..., 0] * f[..., 1] - ac[..., 1] * f[..., 0]) / den
        s = (ac[..., 0] * d[..., 1] - ac[..., 1] * d[..., 0]) / den
    for j, r in zip(*np.nonzero((np.abs(den) > _EPS) & (t > 0) & (t < 1) & (s >= 0) & (s <= 1))):
        p = xy[j] + t[j, r] * (xy[j + 1] - xy[j])
        out.append((p, [np.r_[[p], xy[j + 1:]], np.r_[[p], xy[j::-1]]]))
    return out


def _walk(head, rsegs, target):
    """The point (2,) and the direction (2,) of the polyline head (k, 2) where it first gets target m from the runway
    centreline (rsegs), None if it never does."""
    dist = _pts_dist(head, rsegs)
    idx = np.flatnonzero(dist >= target)
    if not len(idx) or idx[0] == 0:
        return None
    a, b = head[idx[0] - 1], head[idx[0]]
    lo, hi = 0.0, 1.0
    for _ in range(16):                         # (a segment's 1/65536th: millimetres)
        mid = (lo + hi) / 2.0
        if _pts_dist((a + mid * (b - a))[None], rsegs)[0] < target:
            lo = mid
        else:
            hi = mid
    u = (b - a) / max(float(dnp.hypot(*(b - a))), _EPS)
    return a + hi * (b - a), u


def _mapped_hold(head, rsegs, half, holds):
    """The mapped holding position on the head (a way's line from the runway out, half its half width): the point of the
    line under the nearest one and the line's direction there, None when none lies on it (HOLD_SNAP_M, HOLD_MAX_M)."""
    best = None
    seg = np.stack([head[:-1], head[1:]], axis=1)
    cum = np.r_[0.0, np.cumsum(dnp.hypot(*np.diff(head, axis=0).T))]
    for hp in holds:
        a, b = seg[:, 0], seg[:, 1]
        ab = b - a
        t = np.clip(dnp.vecdot(hp - a, ab) / np.maximum(dnp.vecdot(ab, ab), 1e-12), 0.0, 1.0)
        pr = a + t[:, None] * ab
        dd = dnp.hypot(*(pr - hp).T)
        j = int(np.argmin(dd))
        if dd[j] > half + HOLD_SNAP_M:
            continue
        away = float(_pts_dist(pr[j][None], rsegs)[0])
        if not half < away <= HOLD_MAX_M:
            continue
        at = cum[j] + float(dnp.hypot(*(pr[j] - a[j])))
        if best is None or at < best[0]:
            best = (at, pr[j], ab[j] / max(float(dnp.hypot(*ab[j])), _EPS))
    return None if best is None else (best[1], best[2])


def _hold_strokes(c, u, width):
    """The pattern A marking's strokes ((x0, y0, x1, y1, w, kind) in metres) across a way of `width` at c, u the unit
    direction away from the runway: the two dashed lines first (at c and one pitch on), then the two solid ones."""
    nv = np.array([-u[1], u[0]])
    half = width / 2.0
    pitch = HOLD_LINE_W_M + HOLD_LINE_GAP_M
    out = []
    for k in range(4):
        p = c + u * (k * pitch)
        solid = k >= 2
        if solid:
            spans = [(-half, half)]
        else:
            n = max(1, int((width + HOLD_DASH_GAP_M) // (HOLD_DASH_M + HOLD_DASH_GAP_M)))
            start = -(n * HOLD_DASH_M + (n - 1) * HOLD_DASH_GAP_M) / 2.0       # (the dashes centred on the way)
            spans = [(start + i * (HOLD_DASH_M + HOLD_DASH_GAP_M),) for i in range(n)]
            spans = [(t, t + HOLD_DASH_M) for t, in spans]
        for s0, s1 in spans:
            a, b = p + nv * s0, p + nv * s1
            out.append((a[0], a[1], b[0], b[1], HOLD_LINE_W_M, HOLD_KIND[solid]))
    return out


def _way_width(cls, tag, intl):
    """A way's width (aeroways' rule: the width tag, else the default of its class and aerodrome)."""
    if tag is not None:
        return tag
    if cls == "taxiway":
        return aeroways.TAXIWAY_INTL_M if intl else aeroways.TAXIWAY_M
    return aeroways.TAXILANE_INTL_M if intl else aeroways.TAXILANE_M


class Scene:
    """What the markings and the airfield signs (airfieldsigns) read of a list of Features, in one local metre frame:
    frame (geodesy.EnuFrame), ways [(xy (k, 2), width, ref, class)], runways [(xy, half width, ref)] and sites
    [(runway, way, point (2,), unit direction (2,))]: the runway holding positions (indexes into runways and ways;
    the direction runs along the way away from the runway). memo: a dict for what a reader keeps on the scene."""
    __slots__ = ("frame", "ways", "runways", "sites", "memo")

    def __init__(self, frame, ways, runways, sites):
        self.frame, self.ways, self.runways, self.sites, self.memo = frame, ways, runways, sites, {}


def _scene(feats_list):
    """The Scene of the Features in feats_list (None for Features with no airport way)."""
    seen, ways, runways, holds, intl = set(), [], [], [], False
    for f in feats_list:
        if f is None or len(f) == 0:
            continue
        w, r, h, i = _raw(f)
        intl = intl or i
        ways += [x for x in w if x[0] not in seen]
        runways += [x for x in r if x[0] not in seen]
        holds += [x for x in h if x[0] not in seen]
        seen.update(x[0] for x in w + r + h)
    if not ways:
        return None
    lon0, lat0 = ways[0][1][0]
    frame = geodesy.EnuFrame(float(lat0), float(lon0), 0.0)       # (metres: the tile's own ellipsoid, not a sphere's)

    def to_m(ln):
        e, n, _ = frame.geodetic_to_enu(ln[:, 1], ln[:, 0], np.zeros(len(ln)))
        return np.c_[e, n]
    cuts = np.cumsum([len(x[1]) for x in ways])[:-1]
    wxy = np.split(to_m(np.concatenate([x[1] for x in ways])), cuts)
    wwidth = [_way_width(x[2], x[3], intl) for x in ways]
    rw = [(to_m(x[1]), (x[2] or (aeroways.RUNWAY_INTL_M if intl else aeroways.RUNWAY_M)) / 2.0) for x in runways]
    hp = list(to_m(np.array([[x[1], x[2]] for x in holds]))) if holds else []
    # (the markings across a way where it enters a runway)
    starts = np.r_[0, cuts]
    allm = np.concatenate(wxy)
    wlo, whi = np.minimum.reduceat(allm, starts, axis=0), np.maximum.reduceat(allm, starts, axis=0)
    sites = []
    for ri, (rxy, half) in enumerate(rw):
        lo_, hi_ = rxy.min(axis=0) - aeroways.JOIN_TOL_M, rxy.max(axis=0) + aeroways.JOIN_TOL_M
        rsegs = np.stack([rxy[:-1], rxy[1:]], axis=1)
        found = []                              # (a way's end and its crossing find one site: one marking)
        for wi in np.flatnonzero(np.all((whi >= lo_) & (wlo <= hi_), axis=1)):
            xy, w = wxy[wi], wwidth[wi]
            for _p, heads in _joins(xy, rsegs):
                for head in heads:
                    site = _mapped_hold(head, rsegs, w / 2.0, hp) or _walk(head, rsegs, HOLD_DIST_M)
                    if site is None or any(float(dnp.hypot(*(site[0] - s))) < 3.0 for s in found):
                        continue
                    found.append(site[0])
                    sites.append((ri, int(wi), site[0], site[1]))
    return Scene(frame, [(xy, w, x[4], x[2]) for xy, w, x in zip(wxy, wwidth, ways)],
                 [(xy, half, x[3]) for (xy, half), x in zip(rw, runways)], sites)


def _lanes(sc):
    """The scene's way segments for the lead-ins, kept on it: (a (m, 2), unit direction t (m, 2), length (m,), first (m,)
    and last (m,) of a way's, ends [(point, unit direction out of the way)])."""
    got = sc.memo.get("lanes")
    if got is None:
        a, b, first, last, ends = [np.zeros((0, 2))], [np.zeros((0, 2))], [np.zeros(0, bool)], [np.zeros(0, bool)], []
        for xy, *_ in sc.ways:
            if len(xy) < 2:
                continue
            a.append(xy[:-1])
            b.append(xy[1:])
            f, l = np.zeros(len(xy) - 1, bool), np.zeros(len(xy) - 1, bool)
            f[0], l[-1] = True, True
            first.append(f)
            last.append(l)
            for p, q in ((xy[0], xy[1]), (xy[-1], xy[-2])):
                e = p - q
                ends.append((p, e / max(float(dnp.hypot(*e)), _EPS)))
        a, b = np.concatenate(a), np.concatenate(b)
        ln = dnp.hypot(*(b - a).T)
        got = sc.memo["lanes"] = (a, (b - a) / np.maximum(ln, _EPS)[:, None], ln, np.concatenate(first),
                                  np.concatenate(last), ends)
    return got


def _lead_line(lanes, n, u, r):
    """(polyline (k, 2), True) of the lead-in of a stand whose nose is at n, the nose direction u (unit), the curve's
    radius r: from the lane the axis (tail-ward from n) meets nearest to n, along it, round the arc into the straight run
    to n; (None, True) where a lane already reaches n; (None, False) without a lane."""
    a, t, ln, first, last, ends = lanes
    best = None
    for p, e in ends:                                   # (a lane's end the nose points along: its own lead-in)
        v = n - p
        along = float(v[0] * e[0] + v[1] * e[1])
        lat = abs(float(v[0] * e[1] - v[1] * e[0]))
        if float(e[0] * u[0] + e[1] * u[1]) >= ALONG_COS and lat <= ALONG_LAT_M and -2.0 <= along <= LEAD_MAX_M \
                and (best is None or along < best[0]):
            best = (along, p)
    if best is not None:
        return (None, True) if best[0] < 1.0 else (np.array([best[1], n]), True)
    if not len(a):
        return None, False
    mid = a + t * (ln / 2.0)[:, None]
    near = np.flatnonzero(dnp.hypot(*(mid - n).T) <= LEAD_MAX_M + ln / 2.0)
    if not len(near):
        return None, False
    a_, t_, l_ = a[near], t[near], ln[near]
    w = n - a_
    det = t_[:, 0] * u[1] - t_[:, 1] * u[0]
    ok = np.abs(det) >= LEAD_MIN_SIN
    det = np.where(ok, det, 1.0)
    tau = (w[:, 0] * u[1] - w[:, 1] * u[0]) / det                   # the axis (n - s u) meets the lane at a + tau t
    s = (t_[:, 0] * w[:, 1] - t_[:, 1] * w[:, 0]) / det
    cos = t_[:, 0] * u[0] + t_[:, 1] * u[1]
    # (the way's sense that turns into the stand: the one that bends less; across it, the one with more way behind the meeting)
    fwd = np.where(np.abs(cos) < 0.02, tau >= l_ - tau, cos > 0.0)
    tp = np.where(fwd, tau, l_ - tau)                               # the meeting along that sense from its start
    ext = np.where(fwd, last[near], first[near]) * LEAD_EXT_M       # (carried on past the way's end)
    ca, sa = np.abs(cos), np.abs(det)
    d = np.minimum(np.minimum(r * sa / (1.0 + ca), tp), s - LEAD_STRAIGHT_M)    # the arc's tangent length
    ok &= (s <= LEAD_MAX_M) & (tp <= l_ + ext) & (d >= LEAD_D_MIN_M)
    if not ok.any():
        return None, False
    k = int(np.argmin(np.where(ok, s + np.maximum(tp - l_, 0.0), np.inf)))
    tt = t_[k] if fwd[k] else -t_[k]
    start = a_[k] if fwd[k] else a_[k] + t_[k] * l_[k]
    tpk, dk = float(tp[k]), float(d[k])
    x = start + tt * tpk                                            # where the lane's line meets the axis: the control point
    p0, p2 = x - tt * dk, x + u * dk
    pts = [start + tt * min(tpk - dk, float(l_[k]))]
    if float(dnp.hypot(*(p0 - pts[0]))) > 0.05:
        pts.append(p0)                                              # (the lane carried on to the arc)
    theta = dmath.atan2(float(sa[k]), float(ca[k]))
    arc = dk * (1.0 + float(ca[k])) / float(sa[k]) * theta
    m = min(40, max(6, int(arc / 1.5) + 1))
    for i in range(1, m):
        q = i / m
        pts.append((1.0 - q) * (1.0 - q) * p0 + 2.0 * (1.0 - q) * q * x + q * q * p2)
    pts += [p2, n]
    return np.array(pts), True


def _lead_lines(sc, stands):
    """(lines, boxes) (_build's form) of the lead-ins and stop bars of the stands (parkedaircraft Craft), memoized on the
    scene."""
    st = [c for c in stands if c.mode in LEAD_MODES]
    if not st:
        return [], np.zeros((0, 4))
    key = ("lead", tuple((c.kind, round(c.lat, 7), round(c.lon, 7), round(c.ne, 4), round(c.nn, 4)) for c in st))
    got = sc.memo.get(key)
    if got is not None:
        return got
    lanes = _lanes(sc)
    e, nn, _ = sc.frame.geodetic_to_enu(np.array([c.lat for c in st]), np.array([c.lon for c in st]), np.zeros(len(st)))
    out = []                                            # (xy (k, 2), kind)
    for c, ce, cn in zip(st, np.asarray(e), np.asarray(nn)):
        u = np.array([c.ne, c.nn])
        u = u / max(float(dnp.hypot(*u)), _EPS)
        length, span = pa.SPECS[c.kind][0], pa.SPECS[c.kind][1]
        nose = np.array([ce, cn]) + u * (length / 2.0)
        line, found = _lead_line(lanes, nose, u, LEAD_RADIUS_K * span)
        if not found:
            continue
        if line is not None:
            out.append(line)
        v = np.array([-u[1], u[0]]) * (STOP_BAR_M / 2.0)
        out.append(np.array([nose - v, nose + v]))
    lines, boxes = [], []
    for xy in out:
        la, lo, _ = sc.frame.enu_to_geodetic(xy[:, 0], xy[:, 1], np.zeros(len(xy)))
        la, lo = np.asarray(la), np.asarray(lo)
        lines.append((la, lo, CENTRE_W_M, CENTRE_KIND, COLOR))
        boxes.append((la.min(), la.max(), lo.min(), lo.max()))
    got = sc.memo[key] = (lines, np.array(boxes, np.float64).reshape(-1, 4))
    return got


def _all_marks(feats_list, stands):
    """_marks plus the stands' lead-ins."""
    lines, boxes = _marks(feats_list)
    sc = scene(feats_list) if stands else None
    if sc is None:
        return lines, boxes
    extra, xboxes = _lead_lines(sc, stands)
    return (lines + extra, np.concatenate([boxes, xboxes])) if extra else (lines, boxes)


def _cached(feats, slot, build):
    """build(feats), memoized on the first of feats under `slot` (CACHE_MAX lists, each checked to still hold the same
    live Features)."""
    memo = feats[0].__dict__.setdefault(slot, {})
    key = tuple(id(f) for f in feats)
    got = memo.get(key)
    if got is not None and all(r() is f for r, f in zip(got[0], feats)):
        return got[1]
    if len(memo) >= CACHE_MAX:
        memo.clear()
    value = build(feats)
    memo[key] = ([weakref.ref(f) for f in feats], value)
    return value


def scene(feats_list):
    """The Scene of the airport Features in feats_list (the ways, the runways and the runway holding positions the
    markings are drawn from), memoized on the first Features; None for Features with no airport way in them."""
    feats = [f for f in feats_list if f is not None and len(f)]
    if not any(_raw(f)[0] for f in feats):
        return None
    return _cached(feats, _SCENE, _scene)


def _build(feats_list):
    """(lines, boxes): lines [(lat (k,), lon (k,), width, kind, color)], each a polyline (a hold marking's stroke is of
    two points), and boxes (n, 4) their lat0, lat1, lon0, lon1 extents."""
    sc = scene(feats_list)
    if sc is None:
        return [], np.zeros((0, 4))
    out = []                                    # (xy (k, 2), width, kind)
    blocks = _runway_blocks([w[0] for w in sc.ways], [(r[0], r[1]) for r in sc.runways], RUNWAY_GAP_M)
    for (xy, *_), blk in zip(sc.ways, blocks):
        out += [(run, CENTRE_W_M, CENTRE_KIND) for run in (_free_runs(xy, blk) if blk else [xy])]
    for _ri, wi, site, u in sc.sites:
        for x0, y0, x1, y1, lw, kind in _hold_strokes(site, u, sc.ways[wi][1]):
            out.append((np.array([[x0, y0], [x1, y1]]), lw, kind))
    lines, boxes = [], []
    for xy, w, kind in out:
        la, lo, _ = sc.frame.enu_to_geodetic(xy[:, 0], xy[:, 1], np.zeros(len(xy)))
        la, lo = np.asarray(la), np.asarray(lo)
        lines.append((la, lo, w, kind, COLOR))
        boxes.append((la.min(), la.max(), lo.min(), lo.max()))
    return lines, np.array(boxes, np.float64).reshape(-1, 4)


def _marks(feats_list):
    """(lines, boxes) of _build for the list, memoized on its first Features (CACHE_MAX lists, each checked to still
    hold the same live Features); ([], empty) for Features with no airport way in them."""
    feats = [f for f in feats_list if f is not None and len(f)]
    if not any(_raw(f)[0] for f in feats):
        return [], np.zeros((0, 4))
    return _cached(feats, _MEMO, _build)


def strokes(feats_list, stands=None):
    """The markings of the Features in feats_list (module docstring) as two-point strokes (lat0, lon0, lat1, lon1,
    width, kind, color), [] for Features with no airport way in them; with `stands` (parkedaircraft's Craft), their
    lead-ins too."""
    lines, _ = _all_marks(feats_list, stands)
    return [(float(la[i]), float(lo[i]), float(la[i + 1]), float(lo[i + 1]), w, kind, color)
            for la, lo, w, kind, color in lines for i in range(len(la) - 1)]


def _pieces(ex, ey, box):
    """The pieces (x (k,), y (k,)) of the polyline ex, ey owned by the tile box: cut into MARK_PIECE_M, each owned by
    the tile of its midpoint, nodes MARK_NODE_M apart and at the polyline's own vertices (so it follows its bends)."""
    s = np.r_[0.0, np.cumsum(dnp.hypot(np.diff(ex), np.diff(ey)))]
    total = float(s[-1])
    if total < 1e-6:
        return []
    n = max(1, int(np.ceil(total / airportgrade.MARK_PIECE_M)))
    out = []
    for i in range(n):
        a, b = total * i / n, total * (i + 1) / n
        if not geotiles.box_owns(box, float(np.interp((a + b) / 2, s, ex)), float(np.interp((a + b) / 2, s, ey))):
            continue
        k = max(1, int(np.ceil((b - a) / airportgrade.MARK_NODE_M)))
        at = np.unique(np.r_[np.linspace(a, b, k + 1), s[(s > a + 0.05) & (s < b - 0.05)]])
        at = at[np.r_[True, np.diff(at) > 0.05]]
        out.append((np.interp(at, s, ex), np.interp(at, s, ey)))
    return out


def tile_chunks_md(md, keys, frame, tx, ty, elev, tile_bbox):
    """tile_chunks of the infrastructure Features of the map-data cells `keys` (mapdata.MapData md; the tile's cells
    with REACH_M round it, roads.cells_of_tile), with the lead-ins of the stands in them (parkedaircraft.kept_stands:
    the cells' buildings and building parts decide where an aircraft stands)."""
    infra = lambda k: md.cell(k, layers=("infrastructure",), kind="demand").layers.get("infrastructure")
    feats = [infra(k) for k in keys]
    stands = []
    if any(pa.has_stands(f) for f in feats):
        try:
            stands = pa.kept_stands(keys, infra, pa.building_layers_fn(md))
        except Exception as ex:                 # (the centrelines are worth more than the lead-ins)
            log.warning("stand lead-ins: %s: %s", type(ex).__name__, ex)
    return tile_chunks(feats, frame, tx, ty, elev, tile_bbox, stands)


def tile_chunks(feats_list, frame, tx, ty, elev, tile_bbox, stands=None):
    """The taxiway markings (strokes) inside road tile (tx, ty) of `frame` as road chunks ({"m", "w", "tl", "p", "n":
    [[x, y, z], ...]}), as AirportGrader.tile_chunks does the runways': pieces of MARK_PIECE_M at most, each in the tile
    of its midpoint, nodes MARK_NODE_M apart, z from elev (the graded ground). feats_list: the infrastructure Features
    of the cells around the tile (REACH_M); stands: the Craft of those cells (their lead-ins are painted too).
    tile_bbox(tx, ty) -> (x0, y0, x1, y1)."""
    lines, boxes = _all_marks(feats_list, stands)
    if not lines:
        return []
    box = tile_bbox(tx, ty)
    x0, y0, x1, y1 = box
    pad = airportgrade.MARK_PIECE_M
    la, lo, _ = frame.enu_to_geodetic(np.array([x0 - pad, x1 + pad, x0 - pad, x1 + pad]),
                                      np.array([y0 - pad, y0 - pad, y1 + pad, y1 + pad]), np.zeros(4))
    near = np.flatnonzero((boxes[:, 0] <= np.max(la)) & (boxes[:, 1] >= np.min(la)) &
                          (boxes[:, 2] <= np.max(lo)) & (boxes[:, 3] >= np.min(lo)))
    if not len(near):
        return []
    lat = np.concatenate([lines[i][0] for i in near])
    lon = np.concatenate([lines[i][1] for i in near])
    ex, ny, _ = frame.geodetic_to_enu(lat, lon, np.zeros(len(lat)))
    ex, ny = np.asarray(ex), np.asarray(ny)
    pieces, at = [], 0
    for i in near:
        m = len(lines[i][0])
        for px, py in _pieces(ex[at:at + m], ny[at:at + m], box):
            pieces.append((px, py, lines[i]))
        at += m
    if not pieces:
        return []
    xs = np.concatenate([p[0] for p in pieces])
    ys = np.concatenate([p[1] for p in pieces])
    nla, nlo, _ = frame.enu_to_geodetic(xs, ys, np.zeros_like(xs))
    _, _, zs = frame.geodetic_to_enu(nla, nlo, np.asarray(elev(nla, nlo), np.float64))
    out, i = [], 0
    for px, py, line in pieces:
        m = len(px)
        look = airportgrade.MARK_LOOK.get(line[4], airportgrade.MARK_LOOK["white"])
        out.append({"m": look["m"], "w": round(float(line[2]), 2), "tl": look["tl"], "p": look["p"],
                    "n": [[round(float(x), 3), round(float(y), 3), round(float(z), 3)]
                          for x, y, z in zip(px, py, zs[i:i + m])]})
        i += m
    return out
