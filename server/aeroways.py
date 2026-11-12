"""Paved taxiways and aprons: the ground of an airport's apron and taxiway network painted as asphalt (GitHub #607:
only the runways were, so the rest of an airfield read as dirt in the ground layers and the photo).

pads(feats_list) -> [(lat (k,), lon (k,))]: the Overture "infrastructure" Features (subtype "airport") of the cells
around a block, as pads the way surface.lot_pads gives the parking lots: each apron's outer ring, and each taxiway
and taxilane (class "taxiway" / "taxilane", lines) buffered to its width, one mitred outline per run of gentle bends
and an octagon at each end and sharp bend (where it meets another way, an apron or a runway: no notch). A cell of a
big airport is a few hundred outlines, not one rectangle per segment (Brisbane: 4407 pads, 63 ms a 512² paint). The width is
the OSM `width` tag when it reads as a length (23, "23 m", "75 ft"), else a default by class: a taxiway of an
international airport (an "international_airport" aerodrome in the same cell's Features) is a code E strip, the rest
of the world's a code B or C one. A way or apron whose surface (the column, or the tags') is unpaved (grass, dirt,
gravel) is left to the land cover. Pure; each Features' pads are kept on it, so every tile of a cell shares them.
"""
import json
import math
import re

import numpy as np

SUBTYPE = "airport"
APRON = "apron"
WAYS = ("taxiway", "taxilane")
AERODROME = "international_airport"
TAXIWAY_M = 15.0            # m: a taxiway's default width (code B / C: ICAO's 15 m); the taxilane's below
TAXIWAY_INTL_M = 23.0       # an international airport's (code D / E: 23 m)
TAXILANE_M = 10.5           # a taxilane (apron taxiway, code B / C)
TAXILANE_INTL_M = 15.0
MIN_WIDTH_M = 3.0           # a width tag outside these is a typo (a "2300"), the default's instead
MAX_WIDTH_M = 80.0
JOIN_SIDES = 8              # the octagon at a way's end and at a sharp bend
RUNWAY = "runway"
RUNWAY_M = 30.0             # a runway's default width (OSM's runway line: only the fillets read it), code 3 / 4
RUNWAY_INTL_M = 45.0
JOIN_TOL_M = 2.0            # a way's end this near another way's or a runway's centreline joins it: a fillet there
FILLET_MIN_DEG = 10.0       # a way leaving the pavement it joins at less than this runs along it: no fillet
FILLET_RUN_K = 4.0          # a fillet runs this many of the way's half widths past where its edge leaves the other's
FILLET_MAX_K = 8.0          # and at most this many joined half widths along the way
SHARP_TURN_DEG = 60.0       # a bend sharper than this: the outline breaks there and an octagon holds the join
UNPAVED = {"grass", "dirt", "gravel", "ground", "sand", "unpaved", "earth", "compacted", "fine_gravel"}
M_PER_DEG = 6371008.8 * math.pi / 180.0
FOOT_M = 0.3048
_WIDTH = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*(m|ft|')?\s*$", re.I)
_KEY = "_aeroway_pads"


def width_tag(value):
    """A width tag's metres ("23", "23.5 m", "75 ft", "75'"), None when it is no length or an implausible one."""
    m = _WIDTH.match(str(value)) if value is not None else None
    if m is None:
        return None
    w = float(m.group(1).replace(",", ".")) * (FOOT_M if (m.group(2) or "m").lower() in ("ft", "'") else 1.0)
    return w if MIN_WIDTH_M <= w <= MAX_WIDTH_M else None


def _tags(feats, i):
    values = feats.attrs.get("tags")
    if values is None or not values[i]:
        return {}
    try:
        tags = json.loads(str(values[i]))
    except (ValueError, TypeError):
        return {}
    return tags if isinstance(tags, dict) else {}


def _unpaved(feats, i, tags):
    """Is feature i's surface (the column's, else the tags') a bare one?"""
    col = feats.attrs.get("surface")
    value = col[i] if col is not None else None
    if value is None or not str(value).strip():
        value = tags.get("surface")
    return str(value or "").strip().lower() in UNPAVED


def _buffer(lat, lon, width):
    """A line (lat, lon (n,)) buffered to width as [(lat, lon)] pads: a mitred outline per run of bends gentler than
    SHARP_TURN_DEG, an octagon (circumscribed on the half width) at each end and sharp bend. Metric frame: equirectangular about the
    first point (an airfield is a few km: millimetres)."""
    lat0, lon0 = float(lat[0]), float(lon[0])
    kx = M_PER_DEG * math.cos(math.radians(lat0))
    x = (np.asarray(lon, np.float64) - lon0) * kx
    y = (np.asarray(lat, np.float64) - lat0) * M_PER_DEG
    keep = np.r_[True, np.hypot(np.diff(x), np.diff(y)) > 1e-3]       # (a repeated vertex has no direction)
    x, y = x[keep], y[keep]
    if len(x) < 2:
        return []
    half = width / 2.0
    d = np.c_[np.diff(x), np.diff(y)]
    nrm = np.c_[-d[:, 1], d[:, 0]] / np.hypot(d[:, 0], d[:, 1])[:, None]      # each segment's left normal
    # one outline per run of gentle bends (left side out, right side back, mitred at each vertex); a run breaks at a
    # bend sharper than SHARP_TURN_DEG (its mitre would spike), where an octagon holds the join, as at both ends
    seg = np.hypot(d[:, 0], d[:, 1])
    cos_t = np.clip(np.einsum("ij,ij->i", nrm[:-1], nrm[1:]), -1.0, 1.0)      # each interior vertex's bend
    # how far the inner edge's mitre falls back along the segments at a vertex: half * tan(bend / 2)
    back = np.r_[0.0, half * np.sqrt((1.0 - cos_t) / (1.0 + cos_t + 1e-12)), 0.0]
    sharp = np.r_[False, cos_t < math.cos(math.radians(SHARP_TURN_DEG)), False]
    # a vertex also breaks the outline where the inner edge would fold over itself: its fall-back and the next
    # vertex's together longer than the segment between them (a tight bend drawn in short segments); a self-crossing
    # outline is filled even-odd, leaving holes (dirt triangles at Brisbane's runway joins)
    fold = back[:-1] + back[1:] > seg                   # per segment: it is drawn on its own, both its ends break
    brk = sharp | np.r_[fold, False] | np.r_[False, fold]
    rings, start = [], 0
    for k in range(1, len(x)):
        if k == len(x) - 1 or brk[k]:
            off = [nrm[start]]
            for j in range(start + 1, k):
                b = nrm[j - 1] + nrm[j]
                b = b / np.hypot(*b)
                off.append(b / float(np.dot(b, nrm[j])))       # the mitre: half / cos(the half bend) along the bisector
            off.append(nrm[k - 1])
            off = np.asarray(off) * half
            p = np.c_[x[start:k + 1], y[start:k + 1]]
            rings.append(np.r_[p + off, (p - off)[::-1]])
            start = k
    a = (np.arange(JOIN_SIDES) + 0.5) * 2.0 * math.pi / JOIN_SIDES
    ring = np.c_[np.cos(a), np.sin(a)] * (half / math.cos(math.pi / JOIN_SIDES))
    ends = [0, len(x) - 1] + [j for j in range(1, len(x) - 1) if brk[j]]
    rings += [ring + (x[j], y[j]) for j in ends]
    return [(lat0 + r[:, 1] / M_PER_DEG, lon0 + r[:, 0] / kx) for r in rings]


def _hull(pts):
    """The convex hull (counter-clockwise, (k, 2)) of points (n, 2): Andrew's monotone chain."""
    pts = np.unique(np.round(pts, 3), axis=0)
    if len(pts) < 3:
        return pts

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(p)
        return h[:-1]
    return np.asarray(half(pts) + half(pts[::-1]))


def _head(xy, length):
    """The first `length` m of a polyline xy (n, 2) (its last point cut there), and its segments' left normals."""
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.r_[0.0, np.cumsum(seg)]
    k = int(np.searchsorted(cum, length))
    if k >= len(xy):
        out = xy
    else:
        f = (length - cum[k - 1]) / max(seg[k - 1], 1e-9)
        out = np.r_[xy[:k], [xy[k - 1] + f * (xy[k] - xy[k - 1])]]
    d = np.diff(out, axis=0)
    n = np.c_[-d[:, 1], d[:, 0]] / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)[:, None]
    return out, n


def _seg_dist(p, segs):
    """The distance from point p (2,) to each segment (m, 2, 2)."""
    a, b = segs[:, 0], segs[:, 1]
    ab = b - a
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-12), 0.0, 1.0)
    return np.hypot(*(a + t[:, None] * ab - p).T)


def _fillet(v, head, half, r, t):
    """The fillet (local metres) where a way leaves the pavement it joins at v: head (n, 2) its line from v on, half its
    half width, r the joined pavement's half width, t (2,) the joined line's unit direction. None when it leaves
    along that line (no wedge: a hull there would paint the grass beside it). The way's near edge leaves the joined
    pavement's edge (r + half cos a) / sin a along it (a its angle to the line), and the acute wedge between the two
    edges opens from there: the convex hull of a polygon of radius r round v and the way's both edges to FILLET_RUN_K
    half widths past that point fills the wedge's first part with a straight fillet."""
    d = head[1] - head[0]
    u = d / max(float(np.hypot(*d)), 1e-9)
    sin_a = abs(float(u[0] * t[1] - u[1] * t[0]))
    if sin_a < math.sin(math.radians(FILLET_MIN_DEG)):
        return None
    cos_a = math.sqrt(max(0.0, 1.0 - sin_a * sin_a))
    length = min((r + half * cos_a) / sin_a + FILLET_RUN_K * half, FILLET_MAX_K * r)
    head, n = _head(head, length)
    nv = np.r_[n, n[-1:]]
    a = (np.arange(JOIN_SIDES) + 0.5) * 2.0 * math.pi / JOIN_SIDES
    disc = np.c_[np.cos(a), np.sin(a)] * (r / math.cos(math.pi / JOIN_SIDES)) + v
    return _hull(np.r_[head + nv * half, head - nv * half, disc])


def _fillets(ways, runways):
    """The fillets (local metres) where the ways meet other pavement: a way's end on another way's or a runway's
    centreline (JOIN_TOL_M), and a way's vertex anywhere along it on a runway's (a taxiway mapped across the runway
    in one piece: the wedge between a shallow crossing and the runway edge, Brisbane's dirt triangles). One fillet for
    each direction the way leaves in (_fillet). ways, runways: [(xy (n, 2), half width)]."""
    others = ways + runways
    if not ways:
        return []
    segs = np.concatenate([np.stack([xy[:-1], xy[1:]], axis=1) for xy, _ in others])
    seg_half = np.concatenate([np.full(len(xy) - 1, h) for xy, h in others])
    seg_owner = np.concatenate([np.full(len(xy) - 1, i) for i, (xy, _) in enumerate(others)])
    on_runway = seg_owner >= len(ways)
    out = []
    for wi, (xy, half) in enumerate(ways):
        idx = range(len(xy)) if on_runway.any() else (0, len(xy) - 1)
        for k in idx:
            end = k in (0, len(xy) - 1)
            dist = _seg_dist(xy[k], segs)
            dist[seg_owner == wi] = np.inf          # (not the way itself)
            if not end:
                dist[~on_runway] = np.inf           # (inside a way: only where it meets a runway)
            j = int(np.argmin(dist))
            if not dist[j] <= JOIN_TOL_M:
                continue
            r = float(seg_half[j])
            if r < half:                            # (a wider way ending on a narrower one: its own end is enough)
                continue
            t = segs[j, 1] - segs[j, 0]
            t = t / max(float(np.hypot(*t)), 1e-9)
            for head in (xy[k:], xy[k::-1]):
                if len(head) >= 2:
                    f = _fillet(xy[k], head, half, r, t)
                    if f is not None:
                        out.append(f)
    return out


def _feats_pads(feats):
    sub = feats.attrs.get("subtype")
    cls = feats.attrs.get("class")
    if sub is None or cls is None:
        return []
    air = np.asarray(sub).astype(str) == SUBTYPE
    if not air.any():
        return []
    cls = np.asarray(cls).astype(str)
    want = air & np.isin(cls, (APRON,) + WAYS)
    if not want.any():
        return []
    intl = bool((air & (cls == AERODROME)).any())
    out = []
    ways, runways = [], []                  # (lon, lat (n, 2), half width): the fillets'
    for i in np.flatnonzero(air & np.isin(cls, (APRON, RUNWAY) + WAYS)):
        tags = _tags(feats, i)
        kind = int(feats.kind[i])
        if cls[i] == RUNWAY:
            if kind == 2:                       # (painted from OurAirports: only what a taxiway may end on)
                w = width_tag(tags.get("width")) or (RUNWAY_INTL_M if intl else RUNWAY_M)
                runways += [(np.asarray(ln, np.float64), w / 2.0) for part in feats.parts(i) for ln in part if len(ln) >= 2]
            continue
        if _unpaved(feats, i, tags):
            continue
        if cls[i] == APRON:
            if kind != 3:
                continue
            for part in feats.parts(i):
                if part and len(part[0]) >= 3:
                    ring = np.asarray(part[0], np.float64)
                    out.append((ring[:, 1], ring[:, 0]))
        elif kind == 2:
            width = width_tag(tags.get("width"))
            if width is None:
                if cls[i] == "taxiway":
                    width = TAXIWAY_INTL_M if intl else TAXIWAY_M
                else:
                    width = TAXILANE_INTL_M if intl else TAXILANE_M
            for part in feats.parts(i):
                for line in part:
                    if len(line) >= 2:
                        line = np.asarray(line, np.float64)
                        out += _buffer(line[:, 1], line[:, 0], width)
                        ways.append((line, width / 2.0))
    if ways:                                # the fillets, in one metric frame for the cell
        lon0, lat0 = ways[0][0][0]
        kx = M_PER_DEG * math.cos(math.radians(lat0))

        def to_m(ln):
            return np.c_[(ln[:, 0] - lon0) * kx, (ln[:, 1] - lat0) * M_PER_DEG]
        mw = [(to_m(ln), h) for ln, h in ways]
        for r in _fillets(mw, [(to_m(ln), h) for ln, h in runways]):
            out.append((lat0 + r[:, 1] / M_PER_DEG, lon0 + r[:, 0] / kx))
    return out


def pads(feats_list):
    """[(lat (k,), lon (k,))] of the aprons and taxiways of the Features in feats_list (see the module docstring),
    [] for Features with no airport in them (one vectorised test of the class column, kept on the Features)."""
    out = []
    for feats in feats_list:
        if feats is None or len(feats) == 0:
            continue
        got = feats.__dict__.get(_KEY)
        if got is None:
            got = feats.__dict__[_KEY] = _feats_pads(feats)
        out += got
    return out
