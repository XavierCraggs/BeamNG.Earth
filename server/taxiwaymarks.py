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

Stand lead-ins (strokes / tile_chunks take `stands`, parkedaircraft's Craft list of the cells, parkedaircraft.lead_stands:
every valid stand, with or without an aircraft): for each gate or remote stand (not a general-aviation row) a yellow line (CENTRE_KIND, CENTRE_W_M: the same paint) from the
taxiway or taxilane that the aircraft's axis (extended tail-ward) meets nearest: along that line, then a quadratic Bezier
arc (tangent length of a radius of half the wingspan: LEAD_RADIUS_K; tighter where the lane or the straight run is short)
into a straight run along the axis to the nose, and a stop bar STOP_BAR_M across the axis at the nose. A lane that ends
short of the axis is carried on straight (up to LEAD_EXT_M) to it; a lane's end the nose points along (the stand's own
mapped lead-in) is carried on to the nose. A line over LEAD_LINE_MAX_M long or across the pad of a taxiway or runway that is not the lane it leaves is passed over
for the next lane; where none is left, the first lane whose line crosses taxiway pads only (never a runway's: an apron is
criss-crossed with mapped taxiways, a dense one lost most of its stands' lines) is used, and a stand still without a line
(no lane near, or only across a runway) gets a straight stub along its axis from LEAD_STUB_M behind the tail to the nose:
every stand has a line reaching its nose.
A stand that overlaps another of the list is passed over, and no line is painted twice (every tile reads the same list
of stands, and paints the parts of the lines inside its own box: see tile_chunks). The mapped lines are cut only at
runways (not at an apron's edge). A mapped way that already runs along a stand's axis near its nose is its lead-in: none is painted beside it.
Stand marks (_lead_lines; the paint is black, yellow, white and red: airportgrade.MARK_LOOK):
  * every yellow lead-in, spine and bar has a black border BORDER_M wider each side, painted underneath (roadmesh layer "edge");
  * stop bars across the axis (STOP_BAR_M x STOP_BAR_W_M) for the stand's own kind at the nose and the next smaller kinds that
    fit (_ladder: each at its own nose, LADDER_K times the door setback), joined by a STOP_BAR_W_M centreline, each with a
    type label beside it (LABEL: generic codes, never an airline): black segment text on a LABEL_BOX_M yellow box;
  * the stand number (the gate's `ref`: A-Z, 0-9, at most NUM_MAX characters; standmarks' stencil segment font, NUM_TEXT) black
    on a yellow box (about 4 x 2 m for "B13"), past the stop bars on the axis, upright for the approaching pilot;
  * two wing-tip clearance lines (WING_LINE_OFF_M outside the wing tips, WING_LINE_LEN_M long, ending level with the stop bar);
  * the red equipment restraint line (RESTRAINT_OFF_M outside the aircraft's envelope, round the sides and behind the tail);
  * with a Site (the terminals' walls and the jet bridges' ends: site_of): the red hatched box under each mapped bridge's cab
    (BRIDGE_BOX_M) at a stand, and, along each row of stands, the service road (_service_roads: two lanes ROAD_W_M wide, solid
    white edges, a dashed centre, ROAD_WALL_M from the wall, none where a nose is under ROAD_MIN_GAP_M from it; a row of white
    give-way triangles each side of every lead-in that crosses it; boxes for equipment, white outlines with a number, on its wall side).
Taxiway edges (_edge_lines): double yellow lines, two EDGE_W_M lines EDGE_GAP_M apart, along the outline of every taxiway pad
(aeroways.ways) except where it lies inside an apron, a runway's strip or another pad; in a tile they are quads (EDGE_QUAD_M).
The filled marks (boxes, lettering, hatching, dashes, triangles, the edge lines) are convex polygons (polygons(): [(lat, lon, colour,
layer)]): in a tile ONE chunk of quads a colour and layer (roadmesh's "poly" chunks with "quads"); layers "edge" (black borders),
"gutter" (red), "mark" (yellow, white) and "wline" (the black lettering) are the road mesh's heights, so what lies over what does
not rest on the order of the mesh.

Lead-ins as a tree (_spines): the stands that stand in a row (noses near each other, axes within 72 degrees) share a spine, a
taxilane along the frontage through the points SPINE_BACK_M behind each tail (a ring for a satellite), its corners rounded and
painted as a centreline; the rounded line is also what the lead-ins leave, so each lead-in ends exactly on the paint. The spine is
joined to the nearest mapped way at ONE end only (the nearer), by a curve that leaves the way along it and arrives along the spine
(none where the way is over SPINE_JOIN_MAX_M off: it stands alone); where a mapped way already runs within SPINE_LANE_M of
those points it is the spine and nothing is painted. Each stand's lead-in leaves the spine with a short curve onto its axis and
runs straight to the nose (every branch turning the same way); a stand of a row takes its lead-in from its row's spine only (one
that is longer than the aircraft plus LEAD_OVER_M is the straight run from the spine's nearest point), never also a line from another
lane; of two lead-ins that cross the longer is dropped. A stand that is in no row gets the nearest-lane line as before. Lane,
spine and lead-ins are a tree: no closed loop. The rows are made of the stand list alone, so every tile that reads the same stands
paints the same.

scene(feats_list) -> Scene: the same read (the ways with their `ref`, the runways with theirs, the runway holding
positions) in one local metre frame, for the airfield signs (airfieldsigns: a runway's signs stand at those positions).

tile_chunks(feats_list, frame, tx, ty, elev, tile_bbox) -> road chunks ({"m", "w", "tl", "p", "n"}) of the tile, as
AirportGrader.tile_chunks draws the runway markings (airportgrade.MARK_LOOK, MARK_PIECE_M, MARK_NODE_M): every line
(a mapped centreline, a lead-in, a stop bar, a hold marking) that meets the tile's box has its parts inside that box
painted, clipped to it (so a line across two tiles is painted by both, the two pieces ending at their shared edge and
joining there), each part cut into pieces (so its bends are one road).
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
import polygon
import standmarks

log = logging.getLogger(__name__)

CENTRE_W_M = 0.15           # m: the centreline's width (ICAO Annex 14: 0.15 m on a taxiway, 0.3 m on a runway's)
CENTRE_KIND = "taxi_centreline"
STAND_KIND = "stand_mark"   # the stand details' strokes (wing-tip clearance lines, stand numbers): the same paint
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
REACH_M = 280.0             # the margin round a tile whose cells the hook reads (a runway's and a way's join; a stand's lead-in,
                            # up to LEAD_LINE_MAX_M long, ends in the tile: its stand and lane are in the cells read)
CACHE_MAX = 8               # strokes kept per first Features (one per list of cells asked)
HOLD_POINT = "holding_position"
LEAD_MODES = ("gate", "remote")     # the stands (parkedaircraft's Craft.mode) that get a lead-in
LEAD_RADIUS_K = 0.5                 # the lead-in's curve: the radius of this of the wingspan
LEAD_MAX_M = 260.0                  # a lane meeting the axis further than this behind the nose is none
LEAD_LINE_MAX_M = 260.0             # a lead-in (the lane's carried-on end, the arc and the run to the nose) at most this long:
                                    # ~90 m from the lane to the tail and the aircraft's own length under it (at 90 m in all
                                    # nearly every stand lost its line, Heathrow 46 of 73)
LEAD_TRIES = 12                     # the lanes tried, nearest first, for one that is short enough and crosses no taxiway
PAD_EDGE_M = 0.5                    # a lead-in may graze a taxiway's or runway's pad this far in (a junction's corner)
SAMPLE_M = 1.0                      # the lead-in's sampling for the pads
LEAD_EXT_M = 80.0                   # a lane's end carried on to the axis by up to this far
LEAD_STRAIGHT_M = 2.0               # the straight run along the axis at least this long
LEAD_D_MIN_M = 2.0                  # the curve's tangent length at least this
LEAD_MIN_SIN = 0.17                 # a lane within 10 degrees of the axis (sine) is not crossed by it
ALONG_COS = 0.94                    # a lane end the nose points along (20 degrees) ...
ALONG_LAT_M = 2.0                   # ... within this of the axis, is the stand's own lead-in
LEAD_OVER_M = 40.0                  # a lead-in at most the aircraft's length and this long (a longer one is passed over)
SPINE_BACK_M = 10.0                 # a row's spine: through the points this far behind each stand's tail,
SPINE_LINK_M = 25.0                 # ... of the stands (noses within half the spans and this of each other, axes within 72 degrees)
SPINE_LINK_COS = 0.3                # that stand in a row,
SPINE_RING_MIN = 4                  # ... a ring round a satellite (at least this many stands, their mean heading under
SPINE_RING_MEAN = 0.5               # this long: they face every way),
SPINE_LANE_M = 25.0                 # a mapped lane within this of every one of those points is the spine,
SPINE_JOIN_MAX_M = 60.0             # a spine's one end joined to the nearest mapped way by a curve at most this long (none: it stands alone),
SPINE_ROUND_M = 6.0                 # its corners rounded this much (the painted line only)
LEAD_STUB_M = 25.0                  # a stand with no lane: a straight run from this far behind its tail to the nose
STOP_BAR_M = 3.6                    # the stop bars' length across the axis
WING_LINE_OFF_M = 3.0               # the wing-tip clearance lines: this far outside the wing tips,
WING_LINE_LEN_M = 20.0              # ... this long, ending at the stop bar's level
NUM_MAX = 4                         # a ref longer than this is not painted
NUM_TEXT = (1.5, 0.95, 0.22, 0.07, 0.2)     # the stand number's characters (standmarks.text_polys): h, cw, bar, gap, between
NUM_MARGIN = (0.4, 0.25)            # ... on a yellow box this much larger each side (across, along): "B13" in 4.05 x 2.0 m
NUM_AFTER_M = 1.2                   # ... its box this far past the front stop bar's far edge
LABEL_TEXT = (0.55, 0.36, 0.085, 0.03, 0.07)  # a stop bar's type label: black on a yellow box LABEL_BOX_M, beside the bar
LABEL_BOX_M = (2.2, 0.9)
LABEL_SIDE_M = 0.45                 # ... its box this far off the bar's end
LABEL = {"wide": "WIDE", "narrow": "A320", "turboprop": "AT72", "light": "C172"}    # generic type codes, never an airline's
LADDER_N = 3                        # the stop bars: the stand's own kind's and the next smaller ones' (at most this many)
LADDER_K = 2.0                      # ... each at its nose (the door setback, parkedaircraft.BACK_M) times this from the first's
STOP_BAR_W_M = 0.6                  # a stop bar's depth; the ladder's centreline this wide too (the lead-in 0.3 and the border
LEAD_W_M = 0.3                      # ... BORDER_M wider each side, black, under every yellow lead-in, spine and bar)
BORDER_M = 0.15
UNDER_KIND = "mark_border"
RESTRAINT_KIND = "equip_restraint"
RESTRAINT_OFF_M = 6.0               # the red equipment restraint legs: this far off the fuselage's side (about), each side
RESTRAINT_W_M = 0.2
BRIDGE_BOX_M = (6.0, 8.0)           # the red hatched box under a jet bridge's cab: across x along the bridge, centred this far
BRIDGE_BOX_AT_M = 1.0               # ... past its outer end
HATCH_PITCH_M, HATCH_W_M, BOX_LINE_W_M = 1.2, 0.35, 0.3
ROAD_W_M = 7.0                      # the service road along the terminal: two lanes between solid white edges, a dashed centre,
ROAD_MIN_GAP_M = 9.0                # ... where a stand's nose is at least this far from the wall (the road's centre 9.5 m from
ROAD_WALL_M = 9.5                   # ... the wall, nearer where the gap is short: 3.8 m from the nose), none where it is under
ROAD_NOSE_M = 3.8
ROAD_MAX_GAP_M = 70.0               # a wall further than this is none
ROAD_LINE_W_M = 0.15
ROAD_DASH_M, ROAD_DASH_GAP_M = 3.0, 6.0
ROAD_ROUND_M = 8.0
ROAD_KIND = "service_road"
GIVEWAY_N, GIVEWAY_BASE_M, GIVEWAY_H_M, GIVEWAY_AT_M = 6, 0.9, 0.75, 1.8    # the give-way triangles at a lead-in's crossing
EQUIP_BOX_M = (6.0, 3.0)            # the equipment parking boxes: along the road x deep, on the wall side of the road,
EQUIP_PITCH_M = 6.8                 # ... this far apart, up to EQUIP_MAX to a gap between two stands (clear of both axes by
EQUIP_CLEAR_M = 7.0                 # ... this much); only where the road is EQUIP_MIN_C_M or more from the wall
EQUIP_MAX = 3
EQUIP_MIN_C_M = 7.3
EQUIP_TEXT = (0.7, 0.45, 0.11, 0.04, 0.1)
EDGE_KIND = "taxi_edge"             # the taxiways' double yellow edge lines (two EDGE_W_M lines EDGE_GAP_M apart, EDGE_IN_M inside the pad's edge)
EDGE_W_M, EDGE_GAP_M, EDGE_IN_M = 0.15, 0.15, 0.45
EDGE_STEP_M = 1.0                   # (the outlines sampled this finely, simplified to EDGE_TOL_M)
EDGE_TOL_M = 0.05
EDGE_MIN_M = 3.0
EDGE_QUAD_M = 3.0                   # (in a tile the edge lines are quads of at most this long: one chunk, the corners draped)
PIECE_MIN_M = 0.05                  # a part of a line inside a tile shorter than this (a corner's sliver) is not painted
ALONG_CHECK_M = (2.0, 6.0, 10.0, 14.0, 18.0, 22.0)     # a mapped way along the axis (within ALONG_NEAR_M, ALONG_ALIGN of its
ALONG_NEAR_M, ALONG_ALIGN, ALONG_GAP = 2.5, 0.9, 2     # direction) at all but ALONG_GAP of these distances before the nose is the lead-in
BRIDGE_STAND_M = 45.0               # a jet bridge's red box only where a stand's nose is this near its outer end
EDGE_RUNWAY_M = 1.5                 # the taxiway edge lines stop this far outside a runway's edge
_SITE = "_taxiway_site"
_RAW = "_taxiway_raw"
_MEMO = "_taxiway_marks"
_SCENE = "_taxiway_scene"
_EPS = 1e-9


def _round(pts, cut, closed=False, steps=4):
    """The polyline pts (k, 2) with each corner rounded: a quadratic curve (steps chords) from `cut` before the corner to `cut`
    after it (less where a side is short: at most half of it, so that neighbouring corners do not meet). A closed polyline
    (closed, or its first point repeated at its end) is rounded at its first point too; its result ends where it began."""
    P = np.asarray(pts, np.float64)
    closed = bool(closed) or (len(P) > 2 and bool(np.all(P[0] == P[-1])))
    if closed and np.all(P[0] == P[-1]):
        P = P[:-1]
    n = len(P)
    if n < 3 and closed or n < 2:
        return P.copy()
    out = [] if closed else [P[0]]
    for i in (range(n) if closed else range(1, n - 1)):
        p0, p1, p2 = P[i - 1], P[i], P[(i + 1) % n]
        d0, d2 = float(dnp.hypot(*(p0 - p1))), float(dnp.hypot(*(p2 - p1)))
        c = min(cut, d0 / 2.0, d2 / 2.0)
        if c < 1e-9 or d0 < 1e-9 or d2 < 1e-9:
            out.append(p1)
            continue
        a, b = p1 + (p0 - p1) * (c / d0), p1 + (p2 - p1) * (c / d2)
        for k in range(steps + 1):
            q = k / steps
            out.append((1.0 - q) * (1.0 - q) * a + 2.0 * (1.0 - q) * q * p1 + q * q * b)
    out.append(out[0] if closed else P[-1])
    return np.array(out)


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
    and last (m,) of a way's, ends [(point, unit direction out of the way, way index)], the way's index of each segment (m,))."""
    got = sc.memo.get("lanes")
    if got is None:
        a, b, first, last, ends, owner = [np.zeros((0, 2))], [np.zeros((0, 2))], [np.zeros(0, bool)], [np.zeros(0, bool)], [], []
        for wi, (xy, *_) in enumerate(sc.ways):
            if len(xy) < 2:
                continue
            a.append(xy[:-1])
            b.append(xy[1:])
            f, l = np.zeros(len(xy) - 1, bool), np.zeros(len(xy) - 1, bool)
            f[0], l[-1] = True, True
            first.append(f)
            last.append(l)
            owner.append(np.full(len(xy) - 1, wi))
            for p, q in ((xy[0], xy[1]), (xy[-1], xy[-2])):
                e = p - q
                ends.append((p, e / max(float(dnp.hypot(*e)), _EPS), wi))
        a, b = np.concatenate(a), np.concatenate(b)
        ln = dnp.hypot(*(b - a).T)
        got = sc.memo["lanes"] = (a, (b - a) / np.maximum(ln, _EPS)[:, None], ln, np.concatenate(first),
                                  np.concatenate(last), ends, np.concatenate([np.zeros(0, np.int64)] + owner))
    return got


def _pads(sc):
    """The pads a lead-in must not cross, kept on the scene: (a (m, 2), b (m, 2), half width (m,), way index (m,): -1 for a
    runway) of the segments of its taxiways (not its taxilanes: those are the aprons' own) and runways."""
    got = sc.memo.get("pads")
    if got is None:
        a, b, h, w = [np.zeros((0, 2))], [np.zeros((0, 2))], [np.zeros(0)], [np.zeros(0, np.int64)]
        pads = [(xy, wd / 2.0, wi) for wi, (xy, wd, _ref, cls) in enumerate(sc.ways) if cls == "taxiway"]
        pads += [(xy, half, -1) for xy, half, _ref in sc.runways]
        for xy, half, wi in pads:
            if len(xy) >= 2:
                a.append(xy[:-1])
                b.append(xy[1:])
                h.append(np.full(len(xy) - 1, half))
                w.append(np.full(len(xy) - 1, wi))
        got = sc.memo["pads"] = (np.concatenate(a), np.concatenate(b), np.concatenate(h), np.concatenate(w))
    return got


def _runway_pads(pads):
    """The runways' part of _pads' (a, b, half width, way index): the segments of way index -1."""
    m = pads[3] == -1
    return tuple(x[m] for x in pads)


def _alongside(lanes, nose, u):
    """Does a mapped way run along the stand's axis in the last ALONG_CHECK_M before its nose (within ALONG_NEAR_M of it, within
    ~25 degrees of it, at most ALONG_GAP of the checks missed)? Its painted line is then the lead-in: a second beside it
    would be two."""
    a, t, ln = lanes[0], lanes[1], lanes[2]
    if not len(a):
        return False
    hit = 0
    for back in ALONG_CHECK_M:
        p = nose - u * back
        q = a + t * np.clip(dnp.vecdot(p - a, t), 0.0, ln)[:, None]
        d = dnp.hypot(*(q - p).T)
        hit += bool(((d <= ALONG_NEAR_M) & (np.abs(dnp.vecdot(t, u[None])) >= ALONG_ALIGN)).any())
    return hit >= len(ALONG_CHECK_M) - ALONG_GAP


def _stand_line(lanes, spine, nose, u, r, pads, length):
    """The lead-in of a stand (the polyline (k, 2), or None where a lane already reaches the nose or runs along its axis), at most
    length + LEAD_OVER_M long (`length`: the aircraft's), exactly one per stand: the stand's own mapped lead-in lane carried on to
    the nose; else, for a stand of a row (`spine`: (lanes, forward) of _spines), a branch off its row's spine and never a line
    from another lane (a branch that finds no room is the straight run from the spine's nearest point to the nose); else
    _lead_line's: the first that crosses no other pad; else one that crosses no runway's (pads' taxiway part only); else the
    stub of LEAD_STUB_M behind the tail to the nose. Every line starts on the polyline of the lane or spine it leaves."""
    cap = length + LEAD_OVER_M
    line, found = _lead_line(_empty_lanes(lanes[5]), nose, u, r, pads, cap)
    if found:
        return line
    if _alongside(lanes, nose, u):
        return None
    if spine is not None:
        line, found = _lead_line(spine[0], nose, u, r, pads, cap, spine[1])
        if found:
            return line
        a, t, ln = spine[0][:3]
        tail = nose - u * (length + SPINE_BACK_M)
        q = a + t * np.clip(dnp.vecdot(tail - a, t), 0.0, ln)[:, None]
        k = int(np.argmin(dnp.hypot(*(q - tail).T)))
        line = np.array([q[k], nose])
        return line if _length(line) <= cap else None
    line, found = _lead_line(lanes, nose, u, r, pads, cap)
    if not found:
        line, found = _lead_line(lanes, nose, u, r, _runway_pads(pads), cap)
    if not found:
        line = np.array([nose - u * (length + LEAD_STUB_M), nose])
    return line


def _crosses(pads, pts, own):
    """Does the polyline pts (k, 2) enter (by more than PAD_EDGE_M) the pad of a taxiway or runway other than the way `own`?"""
    a, b, half, way = pads
    if not len(a):
        return False
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    m = (np.maximum(a, b) >= lo - half[:, None]).all(axis=1) & (np.minimum(a, b) <= hi + half[:, None]).all(axis=1) & (way != own)
    if not m.any():
        return False
    seg = pts[1:] - pts[:-1]
    n = np.maximum(1, np.ceil(dnp.hypot(*seg.T) / SAMPLE_M).astype(int))
    smp = np.concatenate([pts[i] + seg[i] * (np.arange(k) / k)[:, None] for i, k in enumerate(n)] + [pts[-1:]])
    a, b, half = a[m], b[m], half[m]
    ab = b - a
    ap = smp[:, None, :] - a[None]
    t = np.clip(dnp.vecdot(ap, ab) / np.maximum(dnp.vecdot(ab, ab), 1e-12)[None], 0.0, 1.0)
    d = ap - t[..., None] * ab[None]
    return bool((dnp.hypot(d[..., 0], d[..., 1]) < (half - PAD_EDGE_M)[None]).any())


def _length(pts):
    d = pts[1:] - pts[:-1]
    return float(dnp.hypot(*d.T).sum())


def _lead_line(lanes, n, u, r, pads=None, cap=LEAD_LINE_MAX_M, forward=False):
    """(polyline (k, 2), True) of the lead-in of a stand whose nose is at n, the nose direction u (unit), the curve's
    radius r: from the lane the axis (tail-ward from n) meets nearest to n, along it, round the arc into the straight run
    to n; (None, True) where a lane already reaches n; (None, False) without a lane. A line longer than `cap`, or
    across the pad of a taxiway or runway that is not the lane it leaves (pads: _pads), is passed over for the next lane.
    forward: every lane is left along its own direction (a spine's: all the branches turn the same way)."""
    a, t, ln, first, last, ends, owner = lanes
    cands = []
    for p, e, wi in ends:                               # (a lane's end the nose points along: its own lead-in)
        v = n - p
        along = float(v[0] * e[0] + v[1] * e[1])
        lat = abs(float(v[0] * e[1] - v[1] * e[0]))
        if float(e[0] * u[0] + e[1] * u[1]) >= ALONG_COS and lat <= ALONG_LAT_M and -2.0 <= along <= LEAD_MAX_M:
            cands.append((along, wi, p))
    for along, wi, p in sorted(cands, key=lambda c: (c[0], c[1])):
        if along < 1.0:
            return None, True
        pts = np.array([p, n])
        if _length(pts) <= cap and not (pads is not None and _crosses(pads, pts, wi)):
            return pts, True
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
    fwd = np.where(np.abs(cos) < 0.02, tau >= l_ - tau, cos > 0.0) if not forward else np.ones(len(near), bool)
    tp = np.where(fwd, tau, l_ - tau)                               # the meeting along that sense from its start
    ext = np.where(fwd, last[near], first[near]) * LEAD_EXT_M       # (carried on past the way's end)
    ca, sa = np.abs(cos), np.abs(det)
    d = np.minimum(np.minimum(r * sa / (1.0 + ca), tp), s - LEAD_STRAIGHT_M)    # the arc's tangent length
    ok &= (s <= LEAD_MAX_M) & (tp <= l_ + ext) & (d >= LEAD_D_MIN_M)
    if not ok.any():
        return None, False
    cost = np.where(ok, s + np.maximum(tp - l_, 0.0), np.inf)
    for k in np.argsort(cost, kind="stable")[:LEAD_TRIES]:
        if not np.isfinite(cost[k]):
            break
        tt = t_[k] if fwd[k] else -t_[k]
        start = a_[k] if fwd[k] else a_[k] + t_[k] * l_[k]
        tpk, dk = float(tp[k]), float(d[k])
        x = start + tt * tpk                                        # where the lane's line meets the axis: the control point
        p0, p2 = x - tt * dk, x + u * dk
        pts = [start + tt * min(tpk - dk, float(l_[k]))]
        if float(dnp.hypot(*(p0 - pts[0]))) > 0.05:
            pts.append(p0)                                          # (the lane carried on to the arc)
        theta = dmath.atan2(float(sa[k]), float(ca[k]))
        arc = dk * (1.0 + float(ca[k])) / float(sa[k]) * theta
        m = min(40, max(6, int(arc / 1.5) + 1))
        for i in range(1, m):
            q = i / m
            pts.append((1.0 - q) * (1.0 - q) * p0 + 2.0 * (1.0 - q) * q * x + q * q * p2)
        pts += [p2, n]
        pts = np.array(pts)
        if _length(pts) <= cap and not (pads is not None and _crosses(pads, pts, int(owner[near[k]]))):
            return pts, True
    return None, False


def _empty_lanes(ends=()):
    """_lanes' form with no segments and the given ends: what _lead_line reads for a stand's own mapped lead-in only."""
    z = np.zeros((0, 2))
    return z, z, np.zeros(0), np.zeros(0, bool), np.zeros(0, bool), list(ends), np.zeros(0, np.int64)


def _poly_lanes(pts, closed=False, own=-2):
    """_lanes' form of the polyline pts (k, 2): its segments in order (a lead-in leaves along their direction), none carried on."""
    P = np.asarray(pts, np.float64)
    Q = np.vstack([P, P[:1]]) if closed else P
    a, b = Q[:-1], Q[1:]
    ln = dnp.hypot(*(b - a).T)
    keep = ln > 1e-6
    a, b, ln = a[keep], b[keep], ln[keep]
    n = len(a)
    return a, (b - a) / ln[:, None], ln, np.zeros(n, bool), np.zeros(n, bool), [], np.full(n, own, np.int64)


def _join(lanes, pads, p):
    """(q (2,), way index, unit direction (2,) of its segment, the segment's start (2,) and length) the nearest point q on a mapped way to p (within SPINE_JOIN_MAX_M)
    that a straight piece p-q reaches without entering another way's or a runway's pad; q is p itself where p is on a way
    already. None where there is none."""
    a, t, ln, _f, _l, _e, owner = lanes
    if not len(a):
        return None
    q = a + t * np.clip(dnp.vecdot(p - a, t), 0.0, ln)[:, None]
    d = dnp.hypot(*(q - p).T)
    for k in np.argsort(d, kind="stable")[:LEAD_TRIES]:
        if d[k] > SPINE_JOIN_MAX_M:
            break
        if d[k] < 0.5:
            return np.array(p, np.float64), int(owner[k]), t[k], a[k], float(ln[k])
        if not _crosses(pads, np.array([p, q[k]]), int(owner[k])):
            return q[k], int(owner[k]), t[k], a[k], float(ln[k])
    return None


def _project(pts, p):
    """(point, unit direction, distance) of the polyline pts (k, 2) nearest to p."""
    P = np.asarray(pts, np.float64)
    a, d = P[:-1], P[1:] - P[:-1]
    ln2 = np.maximum(dnp.vecdot(d, d), 1e-12)
    t = np.clip(dnp.vecdot(p - a, d) / ln2, 0.0, 1.0)
    q = a + d * t[:, None]
    dist = dnp.hypot(*(q - p).T)
    k = int(np.argmin(dist))
    return q[k], d[k] / max(float(dnp.hypot(*d[k])), _EPS), float(dist[k])


def _connector(q, tq, seg, p, sdir, pads, own):
    """The curve (k, 2) from a mapped way to p, the end of a spine (its direction sdir from p along it): it leaves the way along
    its direction tq (turned to the sense the spine goes on in) and arrives along the spine (a cubic Bezier, a third of the
    distance as its handles). q is the nearest point of the way's segment seg (start, length); where the way runs along the spine
    the curve starts further back on the segment (0.8 of the distance times the cosine between them: an S-curve, not a loop).
    The straight piece where the curve would enter another pad. None where p is on the way already."""
    v = p - q
    dist = float(dnp.hypot(*v))
    if dist < 0.5:
        return None
    sd = sdir / max(float(dnp.hypot(*sdir)), _EPS)
    t1 = sd if float(sd[0] * v[0] + sd[1] * v[1]) >= 0.0 else -sd         # (arrives going toward where the spine goes on)
    t0 = tq if float(tq[0] * t1[0] + tq[1] * t1[1]) >= 0.0 else -tq
    cos = abs(float(t0[0] * t1[0] + t0[1] * t1[1]))
    a, ln = seg
    s0 = float(tq[0] * (q[0] - a[0]) + tq[1] * (q[1] - a[1]))              # (q along the segment)
    sign = 1.0 if float(t0[0] * tq[0] + t0[1] * tq[1]) > 0.0 else -1.0     # (t0 along or against the segment)
    back = max(0.0, min(0.8 * dist * cos, s0 if sign > 0 else ln - s0))     # (what the segment has behind q for the slide)
    q = q - t0 * back
    v = p - q
    dist = float(dnp.hypot(*v))
    k = dist / 3.0
    c1, c2 = q + t0 * k, p - t1 * k
    f = np.linspace(0.0, 1.0, max(6, int(dist / 2.0) + 1))[:, None]
    g = 1.0 - f
    pts = g * g * g * q + 3.0 * g * g * f * c1 + 3.0 * g * f * f * c2 + f * f * f * p
    pts[0], pts[-1] = q, p
    if _crosses(pads, pts, own):
        return np.array([q, p])
    return pts


def _along(items, members, mu, mean):
    """The members of a row in order across its mean heading mu."""
    along = np.array([-mu[1], mu[0]]) / max(mean, _EPS)
    return sorted(members, key=lambda i: (round(float(items[i][0][0] * along[0] + items[i][0][1] * along[1]), 3), i))


def _spines(items, lanes, pads):
    """({item index: (lanes, forward)}, [polyline (k, 2) to paint], [(members in order along the row, kind)]) of the rows of
    stands in items [(nose (2,), unit direction (2,), length, span)], the tree the lead-ins branch off. Stands link (noses
    within half their spans plus SPINE_LINK_M, axes within 72 degrees) into rows; a row of two or more has one spine, through the
    points SPINE_BACK_M behind each tail, in order along the building (across the mean heading; by angle round the centroid for a
    satellite, a ring), its corners rounded (SPINE_ROUND_M): the rounded line is what is painted and what the lead-ins leave, so
    a lead-in ends on the paint. The spine joins the mapped ways at ONE end only, the nearer to a mapped way, by a curve that leaves
    the way along it and arrives along the spine (_connector; none where the way is further than SPINE_JOIN_MAX_M: the spine stands
    alone), so lane, spine and lead-ins are a tree and never a closed loop. Where a mapped way runs within SPINE_LANE_M of every
    one of those points it is the spine instead (nothing is painted). A row of one has none. The rows' kinds: "row", "ring"
    (a satellite), "lane" (a mapped way)."""
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            (ni, ui, _li, si), (nj, uj, _lj, sj) = items[i], items[j]
            if (float(dnp.hypot(*(ni - nj))) <= (si + sj) / 2.0 + SPINE_LINK_M
                    and float(ui[0] * uj[0] + ui[1] * uj[1]) >= SPINE_LINK_COS):
                ri, rj = find(i), find(j)
                parent[max(ri, rj)] = min(ri, rj)
    rows = {}
    for i in range(n):
        rows.setdefault(find(i), []).append(i)
    got, paint, listed = {}, [], []
    a, t, ln, first, last, _ends, owner = lanes
    for members in sorted(rows.values(), key=lambda m: m[0]):
        if len(members) < 2:
            continue
        tails = np.array([items[i][0] - items[i][1] * (items[i][2] + SPINE_BACK_M) for i in members])
        mu = np.array([items[i][1] for i in members]).mean(axis=0)
        mean = float(dnp.hypot(*mu))
        if len(a):                                      # (a mapped way along the tail points: it is the spine)
            v = tails[:, None, :] - a[None]
            q = a[None] + t[None] * np.clip(dnp.vecdot(v, t[None]), 0.0, ln[None])[..., None]
            d = dnp.hypot(q[..., 0] - tails[:, None, 0], q[..., 1] - tails[:, None, 1])
            best = d.argmin(axis=1)
            if bool((d[np.arange(len(members)), best] <= SPINE_LANE_M).all()):
                m = np.isin(owner, owner[best])
                sp = (a[m], t[m], ln[m], first[m], last[m], [], owner[m]), False
                got.update({i: sp for i in members})
                listed.append((_along(items, members, mu, mean), "lane"))
                continue
        if len(members) >= SPINE_RING_MIN and mean < SPINE_RING_MEAN:
            c = tails.mean(axis=0)
            ang = [dmath.atan2(float(y - c[1]), float(x - c[0])) for x, y in tails]
            order = sorted(range(len(members)), key=lambda k: (round(ang[k], 6), members[k]))
            ring = _round(tails[order], SPINE_ROUND_M, closed=True)
            join = []
            for p in tails[order]:
                j = _join(lanes, pads, _project(ring, p)[0])
                if j is not None:
                    join.append((float(dnp.hypot(*(j[0] - p))), p, j))
            if join:
                _d, p, (q, wi, tq, sa, sl) = min(join, key=lambda x: (round(x[0], 3), round(float(x[1][0]), 3), round(float(x[1][1]), 3)))
                pr, sd, _ = _project(ring, p)
                conn = _connector(q, tq, (sa, sl), pr, sd, pads, wi)
                if conn is not None:
                    paint.append(conn)
            paint.append(ring)
            sp = _poly_lanes(ring, closed=True), True
            kind = "ring"
        else:
            along = np.array([-mu[1], mu[0]]) / max(mean, _EPS)
            proj = dnp.vecdot(tails, along[None])
            order = sorted(range(len(members)), key=lambda k: (round(float(proj[k]), 3), members[k]))
            pts = tails[order]
            span0 = items[members[order[0]]][3]
            ja, jb = _join(lanes, pads, pts[0]), _join(lanes, pads, pts[-1])
            da = float(dnp.hypot(*(ja[0] - pts[0]))) if ja else np.inf
            db = float(dnp.hypot(*(jb[0] - pts[-1]))) if jb else np.inf
            if db < da:                                 # (the end nearer to a mapped way is the start: the only one joined)
                pts, ja, span0, order = pts[::-1], jb, items[members[order[-1]]][3], order[::-1]
            e = pts[0] - pts[1]
            start = pts[0] + e / max(float(dnp.hypot(*e)), _EPS) * (span0 / 2.0)    # (carried on: the first branch's arc)
            chain = _round(np.array([start] + list(pts)), SPINE_ROUND_M)
            if ja is not None:
                j = _join(lanes, pads, chain[0])        # (from the start itself: the curve ends on the painted line)
                if j is not None:
                    conn = _connector(j[0], j[2], (j[3], j[4]), chain[0], chain[1] - chain[0], pads, j[1])
                    if conn is not None:
                        paint.append(conn)
            paint.append(chain)
            sp = _poly_lanes(chain), True
            kind = "row"
        got.update({i: sp for i in members})
        listed.append(([members[k] for k in order], kind))
    return got, paint, listed


def _crossing(a, b, tol=0.02):
    """Does the polyline a (k, 2) cross the polyline b (m, 2): a segment of one strictly across a segment of the other (the
    ends clear of the other's line by more than tol m: a touch, a shared end or a run along it is no crossing)?"""
    p, q, r, w = a[:-1][:, None], a[1:][:, None], b[:-1][None], b[1:][None]
    d1, d2 = q - p, w - r
    n1 = np.maximum(dnp.hypot(d1[..., 0], d1[..., 1]), _EPS)
    n2 = np.maximum(dnp.hypot(d2[..., 0], d2[..., 1]), _EPS)
    cr = lambda u, v: u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]
    o1, o2 = cr(d1, r - p) / n1, cr(d1, w - p) / n1
    o3, o4 = cr(d2, p - r) / n2, cr(d2, q - r) / n2
    split = lambda x, y: ((x > tol) & (y < -tol)) | ((x < -tol) & (y > tol))
    return bool((split(o1, o2) & split(o3, o4)).any())


def _uncrossed(lines):
    """The indices of lines (polylines or None) kept: of two that cross, the longer is dropped."""
    idx = [i for i, ln in enumerate(lines) if ln is not None]
    size = {i: round(_length(lines[i]), 3) for i in idx}
    lo = {i: lines[i].min(axis=0) for i in idx}
    hi = {i: lines[i].max(axis=0) for i in idx}
    dropped = set()
    for x, i in enumerate(idx):
        for k in idx[x + 1:]:
            if i in dropped or k in dropped:
                continue
            if (lo[i] > hi[k]).any() or (lo[k] > hi[i]).any() or not _crossing(lines[i], lines[k]):
                continue
            dropped.add(i if size[i] > size[k] else k)
    return {i for i in idx if i not in dropped}


def stand_key(stands):
    """A hashable key of the stands' (parkedaircraft Craft) places, kinds and refs: what the memos of the lead-ins and the stand
    signs are kept by."""
    return tuple((c.kind, c.mode, c.ref, round(c.lat, 7), round(c.lon, 7), round(c.ne, 4), round(c.nn, 4)) for c in stands)


_NO_MARKS = ([], np.zeros((0, 4)), [], np.zeros((0, 4)))


def _ladder(kind):
    """[(kind, offset)] of the stop bars of a stand of `kind`: its own at the nose (offset 0) and the next smaller kinds' (the
    ones that fit), at most LADDER_N, each at its own nose, (the door's setback, parkedaircraft.BACK_M) times LADDER_K from it."""
    own = pa.SPECS[kind][0]
    fit = sorted((k for k in pa.SPECS if pa.SPECS[k][0] <= own), key=lambda k: -pa.SPECS[k][0])[:LADDER_N]
    return [(k, (pa.BACK_M[k] - pa.BACK_M[kind]) * LADDER_K) for k in fit]


def _wall_gap(nose, u, walls):
    """The distance from the nose along u to the first edge of the rings `walls` ([(k, 2)]): inf where there is none."""
    best = np.inf
    for ring in walls:
        d = np.roll(ring, -1, axis=0) - ring
        w = ring - nose
        den = u[0] * d[:, 1] - u[1] * d[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (w[:, 0] * d[:, 1] - w[:, 1] * d[:, 0]) / den
            s = (w[:, 0] * u[1] - w[:, 1] * u[0]) / den
        ok = (np.abs(den) > _EPS) & (t > 0.0) & (s >= 0.0) & (s <= 1.0)
        if ok.any():
            best = min(best, float(t[ok].min()))
    return best


def _station(poly, p):
    """The distance along the polyline poly (k, 2) of its point nearest to p."""
    P = np.asarray(poly, np.float64)
    d = P[1:] - P[:-1]
    ln = dnp.hypot(d[:, 0], d[:, 1])
    t = np.clip(dnp.vecdot(p - P[:-1], d) / np.maximum(ln * ln, 1e-12), 0.0, 1.0)
    q = P[:-1] + d * t[:, None]
    k = int(np.argmin(dnp.hypot(*(q - p).T)))
    return float(ln[:k].sum() + t[k] * ln[k])


def _service_roads(items, rows, walls, leads):
    """([(xy (k, 2), width, kind, colour)], [(polygon (k, 2), colour, layer)]) of the service roads of the rows of stands (items:
    [(nose, unit direction, length, span)]; rows: _spines'): along each row, between the noses and the terminal's wall (`walls`:
    [(k, 2)] rings), through the points ROAD_WALL_M from the wall (nearer, ROAD_NOSE_M clear of the nose, where the gap is short);
    none where a nose is under ROAD_MIN_GAP_M from the wall or more than ROAD_MAX_GAP_M. Two lanes ROAD_W_M wide in all: solid white
    edges, a dashed centre, a row of white give-way triangles each side of every lead-in (`leads`: polylines) that crosses it;
    and boxes for equipment (3 x 6 m, white outlines, numbered) on the wall side between two stands where the road is far enough
    from the wall."""
    ribbons, polys = [], []
    sm = standmarks
    for members, kind in rows:
        if kind == "ring" or len(members) < 2:
            continue
        gaps = {i: _wall_gap(items[i][0], items[i][1], walls) for i in members}
        runs, cur = [], []
        for i in members:
            if ROAD_MIN_GAP_M <= gaps[i] <= ROAD_MAX_GAP_M:
                cur.append(i)
            else:
                runs.append(cur)
                cur = []
        runs.append(cur)
        mean_u = np.array([items[i][1] for i in members]).mean(axis=0)
        mean_u = mean_u / max(float(dnp.hypot(*mean_u)), _EPS)
        number = 0
        for run in runs:
            if len(run) < 2:
                continue
            cs = {i: min(ROAD_WALL_M, gaps[i] - ROAD_NOSE_M) for i in run}
            pts = [items[i][0] + items[i][1] * (gaps[i] - cs[i]) for i in run]
            e0, e1 = pts[0] - pts[1], pts[-1] - pts[-2]
            pts.insert(0, pts[0] + e0 / max(float(dnp.hypot(*e0)), _EPS) * (items[run[0]][3] / 2.0))
            pts.append(pts[-1] + e1 / max(float(dnp.hypot(*e1)), _EPS) * (items[run[-1]][3] / 2.0))
            centre = _round(np.array(pts), ROAD_ROUND_M)
            if _length(centre) < 12.0:
                continue
            for side in (1.0, -1.0):
                ribbons.append((sm.offset(centre, side * ROAD_W_M / 2.0), ROAD_LINE_W_M, ROAD_KIND, "white"))
            polys += [(p, "white", "paint") for p in sm.dashes(centre, ROAD_DASH_M, ROAD_DASH_GAP_M, ROAD_LINE_W_M)]
            seen = []
            for lead in leads:
                for pt, _s, d in sm.crossings(centre, lead):
                    if any(float(dnp.hypot(*(pt - q))) < 1.0 for q in seen):
                        continue
                    seen.append(pt)
                    for sgn in (1.0, -1.0):
                        polys += [(p, "white", "paint") for p in sm.triangle_row(
                            pt + d * (sgn * (LEAD_W_M / 2.0 + GIVEWAY_AT_M)), d * sgn, ROAD_W_M - 1.0, GIVEWAY_N,
                            GIVEWAY_BASE_M, GIVEWAY_H_M)]
            stations = [_station(centre, items[i][0] + items[i][1] * (gaps[i] - cs[i])) for i in run]
            for (i, si), (k, sk) in zip(zip(run, stations), zip(run[1:], stations[1:])):
                span = sk - si - 2.0 * EQUIP_CLEAR_M
                if span < EQUIP_BOX_M[0] or (cs[i] + cs[k]) / 2.0 < EQUIP_MIN_C_M:
                    continue
                count = min(EQUIP_MAX, int((span + EQUIP_PITCH_M - EQUIP_BOX_M[0]) // EQUIP_PITCH_M))
                for j in range(count):
                    p, r = sm.at(centre, (si + sk) / 2.0 + (j - (count - 1) / 2.0) * EQUIP_PITCH_M)
                    nu = np.array([-r[1], r[0]])
                    nu = nu if float(nu[0] * mean_u[0] + nu[1] * mean_u[1]) > 0.0 else -nu
                    at = p + nu * (ROAD_W_M / 2.0 + 0.5 + EQUIP_BOX_M[1] / 2.0)
                    polys += [(q, "white", "paint") for q in sm.outline(at, nu, EQUIP_BOX_M[0], EQUIP_BOX_M[1], ROAD_LINE_W_M)]
                    number += 1
                    polys += [(q, "white", "paint") for q in sm.text_polys(str(number), at, mean_u, *EQUIP_TEXT)]
    return ribbons, polys


def _site_xy(sc, site):
    """(walls [(k, 2)], bridges [(point (2,), unit direction (2,))]) of a Site in the scene's plane, kept on the scene."""
    key = ("site", site.key)
    got = sc.memo.get(key)
    if got is None:
        def xy(la, lo):
            e, n, _ = sc.frame.geodetic_to_enu(np.asarray(la, np.float64), np.asarray(lo, np.float64), np.zeros(len(la)))
            return np.stack([np.asarray(e), np.asarray(n)], 1)
        walls = [xy(la, lo) for la, lo in site.walls if len(la) >= 3]
        bridges = []
        for la, lo, de, dn in site.bridges:
            bridges.append((xy([la], [lo])[0], _unit2(de, dn)))
        got = sc.memo[key] = (walls, bridges)
    return got


def _unit2(x, y):
    n = max(float(dnp.hypot(x, y)), _EPS)
    return np.array([x / n, y / n])


def _lead_lines(sc, stands, site=None):
    """(lines, boxes, polys, pboxes) of the lead-ins, stop bars and stand details (module docstring) of the stands (parkedaircraft
    Craft), memoized on the scene. lines: _build's form (lat, lon, width, kind, colour); polys: [(lat (k,), lon (k,), colour,
    layer)], convex polygons (the boxes, the lettering, the bars, the hatching, the dashes and the triangles: one chunk a
    colour and layer in a tile), layer "under" (the black borders, painted first), "paint" or "glyph" (the black lettering,
    painted last); boxes and pboxes their lat0, lat1, lon0, lon1 extents. A stand that overlaps a longer one (or one of the same
    kind) in the list is passed over (the list is parkedaircraft.lead_stands's: none do, but a stand twice over, from two lists
    of cells, paints one line): the lines are painted once whatever the tile, and only for a stand that is kept. site: the walls
    of the terminals and the jet bridges' outer ends (Site), for the service roads and the red boxes."""
    st = [c for c in stands if c.mode in LEAD_MODES]
    if not st:
        return _NO_MARKS
    key = ("lead", stand_key(st), None if site is None else site.key)
    got = sc.memo.get(key)
    if got is not None:
        return got
    lanes, pads = _lanes(sc), _pads(sc)
    e, nn, _ = sc.frame.geodetic_to_enu(np.array([c.lat for c in st]), np.array([c.lon for c in st]), np.zeros(len(st)))
    e, nn = np.asarray(e, np.float64), np.asarray(nn, np.float64)
    plane = [(c.kind, float(x), float(y), float(c.ne), float(c.nn)) for c, x, y in zip(st, e, nn)]
    out, polys, seen = [], [], set()                    # (xy (k, 2), width, kind, colour), (polygon (k, 2), colour, layer)
    sm = standmarks

    def add(xy, kind=CENTRE_KIND, width=LEAD_W_M, under=True):
        k = tuple(round(float(q) * 2.0) for q in (xy[0, 0], xy[0, 1], xy[-1, 0], xy[-1, 1]))
        if k not in seen:
            seen.add(k)
            if under:                                   # (the black border under every yellow lead-in and spine)
                out.append((xy, width + 2.0 * BORDER_M, UNDER_KIND, "black"))
            out.append((xy, width, kind, COLOR))

    def box(centre, up, w, h, colour="yellow", border=True):
        if border:
            polys.append((sm.box(centre, up, w + 2.0 * BORDER_M, h + 2.0 * BORDER_M), "black", "under"))
        polys.append((sm.box(centre, up, w, h), colour, "paint"))

    def lettered(text, centre, up, spec):
        polys.extend((p, "black", "glyph") for p in sm.text_polys(text, centre, up, *spec))

    stands_ = []                                        # (Craft, unit direction, length, span, nose) of the stands kept
    for j in pa.drop_overlaps(plane):
        c, ce, cn = st[j], float(e[j]), float(nn[j])
        u = np.array([c.ne, c.nn])
        u = u / max(float(dnp.hypot(*u)), _EPS)
        length, span = pa.SPECS[c.kind][0], pa.SPECS[c.kind][1]
        stands_.append((c, u, length, span, np.array([ce, cn]) + u * (length / 2.0)))
    items = [(x[4], x[1], x[2], x[3]) for x in stands_]
    spines, paint, rows = _spines(items, lanes, pads)
    leads = []
    for xy in paint:
        add(xy)
        leads.append(xy)
    found = [_stand_line(lanes, spines.get(i), nose, u, LEAD_RADIUS_K * span, pads, length)
             for i, (c, u, length, span, nose) in enumerate(stands_)]
    keep = _uncrossed(found)                            # (of two lead-ins that cross, the longer is dropped)
    for i, (c, u, length, span, nose) in enumerate(stands_):
        line = found[i] if i in keep else None
        left = np.array([-u[1], u[0]])
        if line is not None:
            add(line)
            leads.append(line)
        ladder = _ladder(c.kind)
        back = min(off for _k, off in ladder)
        if back < -0.5:                                 # (the thick centreline through the ladder)
            box(nose + u * (back / 2.0), u, STOP_BAR_W_M, -back + STOP_BAR_W_M)
        for kind, off in ladder:                        # (a stop bar for each kind, a type label beside it)
            at = nose + u * off
            box(at, u, STOP_BAR_M, STOP_BAR_W_M)
            lab = at - left * (STOP_BAR_M / 2.0 + LABEL_SIDE_M + LABEL_BOX_M[0] / 2.0)       # (the pilot's right: -left)
            box(lab, u, LABEL_BOX_M[0], LABEL_BOX_M[1])
            lettered(LABEL[kind], lab, u, LABEL_TEXT)
        for sgn in (-1.0, 1.0):                         # (the wing-tip clearance lines, ending level with the stop bar)
            side = left * sgn * (span / 2.0 + WING_LINE_OFF_M)
            add(np.array([nose + side - u * WING_LINE_LEN_M, nose + side]), STAND_KIND, CENTRE_W_M, under=False)
        text = str(c.ref or "").upper().replace(" ", "")
        if len(text) <= NUM_MAX and sm.supported(text):  # (the number: black on a yellow box past the stop bars)
            h, cw, _bar, _gap, cg = NUM_TEXT
            bw, bh = sm.text_width(len(text), cw, cg) + 2.0 * NUM_MARGIN[0], h + 2.0 * NUM_MARGIN[1]
            at = nose + u * (STOP_BAR_W_M / 2.0 + NUM_AFTER_M + bh / 2.0)
            box(at, u, bw, bh)
            lettered(text, at, u, NUM_TEXT)
        # (the equipment restraint line: two legs either side of the forward fuselage, RESTRAINT_OFF_M off its skin and
        # 0.4 of the length back; a U round the whole envelope crossed the next stands' at Brisbane)
        a = RESTRAINT_OFF_M + 0.06 * length
        back = 0.4 * length
        for s in (1.0, -1.0):
            out.append((np.array([nose + left * (s * a), nose + left * (s * a) - u * back]), RESTRAINT_W_M,
                        RESTRAINT_KIND, "red"))
    if site is not None:
        walls, bridges = _site_xy(sc, site)
        for pt, d in bridges:                           # (the red hatched box under each jet bridge's cab, at a stand)
            if not any(float(dnp.hypot(*(x[4] - pt))) < BRIDGE_STAND_M for x in stands_):
                continue
            centre = pt + d * BRIDGE_BOX_AT_M
            w, h = BRIDGE_BOX_M
            polys += [(p, "red", "red") for p in sm.hatch(centre, d, w, h, HATCH_PITCH_M, HATCH_W_M)]
            polys += [(p, "red", "red") for p in sm.outline(centre, d, w, h, BOX_LINE_W_M)]
        if walls:
            ribbons, more = _service_roads(items, rows, walls, leads)
            out += ribbons
            polys += more
    lines, boxes = [], []
    for xy, width, kind, colour in out:
        la, lo, _ = sc.frame.enu_to_geodetic(xy[:, 0], xy[:, 1], np.zeros(len(xy)))
        la, lo = np.asarray(la), np.asarray(lo)
        lines.append((la, lo, width, kind, colour))
        boxes.append((la.min(), la.max(), lo.min(), lo.max()))
    plist, pboxes = [], []
    for pts, colour, layer in polys:
        la, lo, _ = sc.frame.enu_to_geodetic(pts[:, 0], pts[:, 1], np.zeros(len(pts)))
        la, lo = np.asarray(la), np.asarray(lo)
        plist.append((la, lo, colour, layer))
        pboxes.append((la.min(), la.max(), lo.min(), lo.max()))
    got = sc.memo[key] = (lines, np.array(boxes, np.float64).reshape(-1, 4), plist, np.array(pboxes, np.float64).reshape(-1, 4))
    return got


def _all_marks(feats_list, stands, site=None):
    """(lines, boxes, polys, pboxes): _marks plus the stands' lead-ins and marks (_lead_lines)."""
    lines, boxes = _marks(feats_list)
    sc = scene(feats_list) if stands else None
    if sc is None:
        return lines, boxes, [], np.zeros((0, 4))
    extra, xboxes, polys, pboxes = _lead_lines(sc, stands, site)
    return (lines + extra, np.concatenate([boxes, xboxes]) if extra else boxes, polys, pboxes)


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


class Site:
    """What the stand marks read of the buildings of an airport: walls [(lat (k,), lon (k,))], the outlines of its terminals and
    piers (airportroles), and bridges [(lat, lon, east, north)], the outer end of each mapped jet bridge with its unit
    direction out of the terminal; key, a hashable summary of them (what the memos of the stands' marks are kept by)."""
    __slots__ = ("walls", "bridges", "key")

    def __init__(self, walls, bridges):
        self.walls, self.bridges = walls, bridges
        self.key = (tuple((len(la), round(float(np.mean(la)), 6), round(float(np.mean(lo)), 6)) for la, lo in walls),
                    tuple((round(float(b[0]), 6), round(float(b[1]), 6)) for b in bridges))


def _build_site(infra, blds, parts):
    import airportroles
    roles = airportroles.classify([f for f in blds if f is not None], [f for f in parts if f is not None],
                                  [f for f in infra if f is not None])
    if roles.frame is None or not len(roles.units):
        return None
    fr, (x0, y0) = roles.frame, roles.origin
    walls = []
    for uid, u in roles.units.items():
        if roles.get(uid) in (airportroles.TERMINAL, airportroles.PIER) and len(u.ring) >= 3:
            la, lo, _ = fr.enu_to_geodetic(u.ring[:, 0] + x0, u.ring[:, 1] + y0, np.zeros(len(u.ring)))
            walls.append((np.asarray(la, np.float64), np.asarray(lo, np.float64)))
    bridges, seen = [], set()
    for gid in sorted(roles.gates):
        g = roles.gates[gid]
        if g.get("end") is None or g["bridge"] in seen:
            continue
        seen.add(g["bridge"])
        la, lo, _ = fr.enu_to_geodetic(np.array([g["end"][0] + x0]), np.array([g["end"][1] + y0]), np.zeros(1))
        bridges.append((float(la[0]), float(lo[0]), float(g["dir"][0]), float(g["dir"][1])))
    return Site(walls, bridges) if walls or bridges else None


def site_of(infra, blds, parts):
    """The Site (the walls and the jet bridges' ends) of the airport in the Features of the cells (lists of infrastructure,
    buildings and building_parts Features), memoized on the first; None without a terminal or a bridge."""
    allf = [f for f in list(infra) + list(blds) + list(parts) if f is not None and len(f)]
    if not allf:
        return None
    return _cached(allf, _SITE, lambda _fl: _build_site(infra, blds, parts))


def _simplify(P, tol):
    """The polyline P (k, 2) without the vertices that lie within tol of the line between the kept ones (Douglas-Peucker)."""
    n = len(P)
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, d = P[i], P[j] - P[i]
        ln = max(float(dnp.hypot(*d)), _EPS)
        dist = np.abs((P[i + 1:j, 0] - a[0]) * d[1] - (P[i + 1:j, 1] - a[1]) * d[0]) / ln
        k = int(np.argmax(dist))
        if dist[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return P[keep]


def _edge_lines(sc, feats_list):
    """[(xy (k, 2), width, kind, colour)] of the taxiways' double yellow edge lines: along the outline of every taxiway pad
    (aeroways.ways: the buffered ways with their fillets), except where it lies inside an apron, a runway's strip or another
    pad (a junction), two EDGE_W_M lines EDGE_GAP_M apart, the nearer EDGE_IN_M inside the pad's edge."""
    ways = [r for r in aeroways.ways(feats_list) if len(r[0]) >= 4]
    if not ways:
        return []

    def xy(la, lo):
        e, n, _ = sc.frame.geodetic_to_enu(np.asarray(la, np.float64), np.asarray(lo, np.float64), np.zeros(len(la)))
        return np.stack([np.asarray(e), np.asarray(n)], 1)
    rings = [xy(la, lo) for la, lo in ways]
    rings = [r[:-1] if float(dnp.hypot(*(r[0] - r[-1]))) < 1e-6 else r for r in rings]
    aprons = [xy(la, lo) for la, lo in aeroways.aprons(feats_list) if len(la) >= 3]
    lo_hi = lambda rs: (np.array([r.min(axis=0) for r in rs]).reshape(-1, 2), np.array([r.max(axis=0) for r in rs]).reshape(-1, 2))
    wlo, whi = lo_hi(rings)
    alo, ahi = lo_hi(aprons)
    rsegs = [(np.stack([r[:-1], r[1:]], axis=1), half) for r, half, _ref in sc.runways if len(r) >= 2]
    out = []
    for i, ring in enumerate(rings):
        closed = np.vstack([ring, ring[:1]])
        seg = np.diff(closed, axis=0)
        ln = dnp.hypot(seg[:, 0], seg[:, 1])
        if float(ln.sum()) < EDGE_MIN_M:
            continue
        cnt = np.maximum(1, np.ceil(ln / EDGE_STEP_M).astype(np.int64))
        pts = np.concatenate([closed[j] + seg[j] * (np.arange(c) / c)[:, None] for j, c in enumerate(cnt)])
        drop = np.zeros(len(pts), bool)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        others = [(aprons[j], True) for j in np.flatnonzero(np.all((ahi >= lo) & (alo <= hi), axis=1))]
        others += [(rings[j], False) for j in np.flatnonzero(np.all((whi >= lo) & (wlo <= hi), axis=1)) if j != i]
        for r, _apron in others:
            m = np.all((pts >= r.min(axis=0)) & (pts <= r.max(axis=0)), axis=1) & ~drop
            if m.any():
                drop[np.flatnonzero(m)[polygon.contains_points(r, pts[m])]] = True
        for segs, half in rsegs:
            if (segs.min(axis=(0, 1)) - half - 2.0 <= hi).all() and (segs.max(axis=(0, 1)) + half + 2.0 >= lo).all():
                drop |= _pts_dist(pts, segs) < half + EDGE_RUNWAY_M
        keep = ~drop
        if keep.sum() < 2:
            continue
        area = float((ring[:, 0] * np.roll(ring[:, 1], -1) - np.roll(ring[:, 0], -1) * ring[:, 1]).sum())
        inward = 1.0 if area > 0.0 else -1.0                 # (counter-clockwise: the inside is on the left)
        if keep.all():
            runs = [np.vstack([pts, pts[:1]])]
        else:
            first = int(np.flatnonzero(drop)[0])
            rot = np.roll(np.arange(len(pts)), -first)
            runs, cur = [], []
            for k in rot:
                if keep[k]:
                    cur.append(pts[k])
                elif cur:
                    runs.append(np.array(cur))
                    cur = []
            if cur:
                runs.append(np.array(cur))
        for run in runs:
            if len(run) < 2 or _length(run) < EDGE_MIN_M:
                continue
            run = _simplify(run, EDGE_TOL_M)
            for k in (0, 1):
                out.append((standmarks.offset(run, inward * (EDGE_IN_M + k * (EDGE_W_M + EDGE_GAP_M))), EDGE_W_M,
                            EDGE_KIND, COLOR))
    return out


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
    try:                                        # (the taxiways' double edge lines)
        out += [(xy, w, kind) for xy, w, kind, _c in _edge_lines(sc, feats_list)]
    except Exception as ex:                     # (the centrelines are worth more than the edges)
        log.warning("taxiway edge lines: %s: %s", type(ex).__name__, ex)
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


def strokes(feats_list, stands=None, site=None):
    """The markings of the Features in feats_list (module docstring) as two-point strokes (lat0, lon0, lat1, lon1,
    width, kind, color), [] for Features with no airport way in them; with `stands` (parkedaircraft's Craft), their
    lead-ins too."""
    lines = _all_marks(feats_list, stands, site)[0]
    return [(float(la[i]), float(lo[i]), float(la[i + 1]), float(lo[i + 1]), w, kind, color)
            for la, lo, w, kind, color in lines for i in range(len(la) - 1)]


def _inside(ex, ey, box):
    """The parts of the polyline ex, ey inside the box (x0, y0, x1, y1), clipped to it (Liang-Barsky on each segment, the
    box's edges included): [(x (k,), y (k,))], a polyline that leaves and enters again in several parts; consecutive
    segments that both continue across a vertex stay one."""
    x0, y0, x1, y1 = box[:4]
    if len(ex) < 2:
        return []
    ax, ay = ex[:-1], ey[:-1]
    dx, dy = np.diff(ex), np.diff(ey)
    tx0, tx1 = _slab(ax, dx, x0, x1)
    ty0, ty1 = _slab(ay, dy, y0, y1)
    t0, t1 = np.maximum(np.maximum(tx0, ty0), 0.0), np.minimum(np.minimum(tx1, ty1), 1.0)
    out, cur, last, end = [], None, -2, 0.0
    for i in np.flatnonzero(t0 <= t1):
        a, b = float(t0[i]), float(t1[i])
        p, q = (float(ax[i] + dx[i] * a), float(ay[i] + dy[i] * a)), (float(ax[i] + dx[i] * b), float(ay[i] + dy[i] * b))
        if cur is not None and last == i - 1 and a <= 0.0 and end >= 1.0:           # (it did not leave: the same part)
            cur[0].append(q[0])
            cur[1].append(q[1])
        else:
            if cur is not None:
                out.append(cur)
            cur = ([p[0], q[0]], [p[1], q[1]])
        last, end = int(i), b
    if cur is not None:
        out.append(cur)
    return [(np.array(px, np.float64), np.array(py, np.float64)) for px, py in out]


def _pieces(ex, ey, box):
    """The pieces (x (k,), y (k,)) of the polyline ex, ey inside the tile box (clipped to it): each part cut into
    MARK_PIECE_M at most, nodes MARK_NODE_M apart and at the polyline's own vertices (so it follows its bends)."""
    out = []
    for px, py in _inside(np.asarray(ex, np.float64), np.asarray(ey, np.float64), box):
        s = np.r_[0.0, np.cumsum(dnp.hypot(np.diff(px), np.diff(py)))]
        total = float(s[-1])
        if total < PIECE_MIN_M:
            continue
        n = max(1, int(np.ceil(total / airportgrade.MARK_PIECE_M)))
        for i in range(n):
            a, b = total * i / n, total * (i + 1) / n
            k = max(1, int(np.ceil((b - a) / airportgrade.MARK_NODE_M)))
            at = np.unique(np.r_[np.linspace(a, b, k + 1), s[(s > a + 0.05) & (s < b - 0.05)]])
            at = at[np.r_[True, np.diff(at) > 0.05]]
            if len(at) < 2:
                continue
            out.append((np.interp(at, s, px), np.interp(at, s, py)))
    return out


def tile_chunks_md(md, keys, frame, tx, ty, elev, tile_bbox):
    """tile_chunks of the infrastructure Features of the map-data cells `keys` (mapdata.MapData md; the tile's cells
    with REACH_M round it, roads.cells_of_tile), with the lead-ins of the stands in them (parkedaircraft.lead_stands:
    the cells' buildings and building parts decide where an aircraft stands) and the stand marks that read the terminals
    (the service roads, the red boxes under the jet bridges: site_of)."""
    infra = lambda k: md.cell(k, layers=("infrastructure",), kind="demand").layers.get("infrastructure")
    feats = [infra(k) for k in keys]
    stands, site = [], None
    if any(pa.has_stands(f) for f in feats):
        try:
            bl = pa.building_layers_fn(md)
            stands = pa.lead_stands(keys, infra, bl)
        except Exception as ex:                 # (the centrelines are worth more than the lead-ins)
            log.warning("stand lead-ins: %s: %s", type(ex).__name__, ex)
        if stands:
            try:
                got = [bl(k) for k in keys]
                site = site_of(feats, [g[0] for g in got], [g[1] for g in got])
            except Exception as ex:             # (the stands' marks are worth more than the roads and the red boxes)
                log.warning("stand marks' site: %s: %s", type(ex).__name__, ex)
    return tile_chunks(feats, frame, tx, ty, elev, tile_bbox, stands, site)


# the layers a mark is drawn in (roadmesh.LIFT: the height over the road, so what is painted over what does not rest on the order
# of the mesh): the black borders first, the red marks, the yellow and white paint, the black lettering last
LAYER_OF = {"under": "edge", "red": "gutter", "paint": "mark", "glyph": "wline"}
RIBBON_LAYER = {"black": "under", "red": "red"}


def _quads(poly):
    """The 4-corner quads of a convex polygon (k, 2), k >= 3: itself for 4, else a fan of triangles each as a quad (a triangle's
    third side halved: no zero-area triangle)."""
    p = np.asarray(poly, np.float64)
    if len(p) == 4:
        return [p]
    return [np.array([p[0], p[i], (p[i] + p[i + 1]) / 2.0, p[i + 1]]) for i in range(1, len(p) - 1)]


def _strip(px, py, width):
    """The quads (4, 2) of the polyline px, py as a strip `width` wide: a rectangle for each piece of at most EDGE_QUAD_M of each
    segment (the road mesh drapes a quad by its corners only: short ones follow the ground)."""
    out = []
    for i in range(len(px) - 1):
        a, b = np.array([px[i], py[i]]), np.array([px[i + 1], py[i + 1]])
        ln = float(dnp.hypot(*(b - a)))
        if ln < 1e-6:
            continue
        nv = np.array([-(b[1] - a[1]), b[0] - a[0]]) / ln * (width / 2.0)
        n = max(1, int(np.ceil(ln / EDGE_QUAD_M)))
        for k in range(n):
            p, q = a + (b - a) * (k / n), a + (b - a) * ((k + 1) / n)
            out.append(np.array([p - nv, q - nv, q + nv, p + nv]))
    return out


def polygons(feats_list, stands=None, site=None):
    """The stands' filled marks of the Features in feats_list as [(lat (k,), lon (k,), colour, layer)] (convex polygons: the
    boxes, bars, lettering, hatching, dashes and triangles; layer "under", "red", "paint" or "glyph": _lead_lines); [] without
    stands."""
    return _all_marks(feats_list, stands, site)[2]


def tile_chunks(feats_list, frame, tx, ty, elev, tile_bbox, stands=None, site=None):
    """The taxiway markings (strokes, polygons) inside road tile (tx, ty) of `frame` as road chunks, as
    AirportGrader.tile_chunks does the runways': the parts of each line inside the tile's box, clipped to it, in pieces of
    MARK_PIECE_M at most ({"m", "w", "tl", "p", "n": [[x, y, z], ...]}: nodes MARK_NODE_M apart, z from elev (the graded ground);
    a black line is in the road mesh's "edge" layer, a red one in "gutter": under the yellow); the polygons that meet the box
    (cut to it by the road mesh) as ONE chunk of quads for each colour and layer ({"m", "w": 0, "tl", "p", "layer", "poly",
    "uvq", "quads": 1, "n": []}: roadmesh's filled polygons, the height at the corners). feats_list: the infrastructure
    Features of the cells around the tile (REACH_M); stands: the Craft of those cells (their lead-ins and marks are painted too);
    site: their terminals' walls and bridges (Site). tile_bbox(tx, ty) -> (x0, y0, x1, y1)."""
    lines, boxes, polys, pboxes = _all_marks(feats_list, stands, site)
    if not lines and not polys:
        return []
    box = tile_bbox(tx, ty)
    x0, y0, x1, y1 = box
    pad = airportgrade.MARK_PIECE_M
    la, lo, _ = frame.enu_to_geodetic(np.array([x0 - pad, x1 + pad, x0 - pad, x1 + pad]),
                                      np.array([y0 - pad, y0 - pad, y1 + pad, y1 + pad]), np.zeros(4))
    inside = lambda b: np.flatnonzero((b[:, 0] <= np.max(la)) & (b[:, 1] >= np.min(la)) &
                                      (b[:, 2] <= np.max(lo)) & (b[:, 3] >= np.min(lo)))
    near = inside(boxes) if len(lines) else []
    out = []
    if len(near):
        lat = np.concatenate([lines[i][0] for i in near])
        lon = np.concatenate([lines[i][1] for i in near])
        ex, ny, _ = frame.geodetic_to_enu(lat, lon, np.zeros(len(lat)))
        ex, ny = np.asarray(ex), np.asarray(ny)
        pieces, at = [], 0
        edge_quads = []                                 # (the taxiway edge lines: quads, a chunk a tile, not a chunk a piece)
        for i in near:
            m = len(lines[i][0])
            for px, py in _pieces(ex[at:at + m], ny[at:at + m], box):
                if lines[i][3] == EDGE_KIND:
                    edge_quads += _strip(px, py, lines[i][2])
                else:
                    pieces.append((px, py, lines[i]))
            at += m
        if pieces:
            xs = np.concatenate([p[0] for p in pieces])
            ys = np.concatenate([p[1] for p in pieces])
            nla, nlo, _ = frame.enu_to_geodetic(xs, ys, np.zeros_like(xs))
            _, _, zs = frame.geodetic_to_enu(nla, nlo, np.asarray(elev(nla, nlo), np.float64))
            i = 0
            for px, py, line in pieces:
                m = len(px)
                look = airportgrade.MARK_LOOK.get(line[4], airportgrade.MARK_LOOK["white"])
                c = {"m": look["m"], "w": round(float(line[2]), 2), "tl": look["tl"], "p": look["p"],
                     "n": [[round(float(x), 3), round(float(y), 3), round(float(z), 3)]
                           for x, y, z in zip(px, py, zs[i:i + m])]}
                if line[4] in RIBBON_LAYER:
                    c["layer"] = LAYER_OF[RIBBON_LAYER[line[4]]]
                out.append(c)
                i += m
    pnear = inside(pboxes) if len(polys) else []
    groups = {("yellow", "paint"): list(edge_quads)} if len(near) and edge_quads else {}
    if len(pnear) or groups:
        lat = np.concatenate([polys[i][0] for i in pnear] or [np.zeros(0)])
        lon = np.concatenate([polys[i][1] for i in pnear] or [np.zeros(0)])
        if len(lat):
            ex, ny, _ = frame.geodetic_to_enu(lat, lon, np.zeros(len(lat)))
            ex, ny = np.asarray(ex), np.asarray(ny)
        else:
            ex = ny = lat
        at = 0
        for i in pnear:
            m = len(polys[i][0])
            p = np.stack([ex[at:at + m], ny[at:at + m]], 1)
            at += m
            if (p[:, 0].max() < x0 or p[:, 0].min() > x1 or p[:, 1].max() < y0 or p[:, 1].min() > y1) or m < 3:
                continue
            groups.setdefault((polys[i][2], polys[i][3]), []).extend(_quads(p))
        for (colour, layer), quads in sorted(groups.items()):
            look = airportgrade.MARK_LOOK.get(colour, airportgrade.MARK_LOOK["white"])
            pts = np.concatenate(quads)
            out.append({"m": look["m"], "w": 0.0, "tl": look["tl"], "p": look["p"], "layer": LAYER_OF[layer],
                        "poly": [[round(float(x), 3), round(float(y), 3)] for x, y in pts],
                        "uvq": [[0.5, 0.5]] * len(pts), "quads": 1, "n": []})
    return out
