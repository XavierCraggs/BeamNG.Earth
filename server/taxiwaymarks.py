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
taxiway or taxilane that the aircraft's axis (extended tail-ward) meets nearest: along that line, then a circular arc (a radius
of half the wingspan: LEAD_RADIUS_K, never under MIN_RADIUS_M, 8 m for a light aircraft: the join point slides back along the lane
until it fits; else an arc, a straight and an arc from a point slid along the lane, _dubins; only where none fits the tightest
smooth arc, TIGHT_RADIUS_M, never a dropped line and no corner over 25 degrees) into a straight run along the axis to the nose, and a stop bar STOP_BAR_M across the axis at the nose. A lane that ends
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
  * two wing-tip clearance lines (WING_LINE_OFF_M outside the wing tips, WING_LINE_LEN_M long, ending level with the stop bar;
    _wing_lines: clipped where they would run under a neighbour's aircraft, dropped near another stand's lead-in, the later of two
    lines that come within WING_CLEAR_M of each other too), with the black border as every yellow line on an apron has, the mapped
    centrelines' parts on one (_build) included;
  * the red equipment restraint line (RESTRAINT_OFF_M outside the aircraft's envelope, round the sides and behind the tail);
  * with a Site (the terminals' walls and the jet bridges' ends: site_of): the red hatched box under each mapped bridge's cab
    (BRIDGE_BOX_M) at a stand, and, along each building's frontage, ONE service road (_service_roads: a ring round a satellite, else an arc along
    the wall, cut only where a jet bridge's footprint or another building is in the way; two lanes ROAD_W_M wide, solid
    white edges, a dashed centre, ROAD_WALL_M from the wall, none where a nose is under ROAD_MIN_GAP_M from it; a row of white
    give-way triangles each side of every lead-in that crosses it; boxes for equipment, white outlines with a number, on its wall side).
Taxiway edges (_edge_lines): double yellow lines, two EDGE_W_M lines EDGE_GAP_M apart, along the outline of every taxiway pad
(aeroways.ways) except where it lies inside an apron, a runway's strip or another pad; in a tile they are quads (EDGE_QUAD_M).
The filled marks (boxes, lettering, hatching, dashes, triangles, the edge lines) are convex polygons (polygons(): [(lat, lon, colour,
layer)]): in a tile ONE chunk of quads a colour and layer (roadmesh's "poly" chunks with "quads"); layers "edge" (black borders),
"gutter" (red), "mark" (yellow, white) and "glyph" (the black lettering: its own material, line_runway_text, listed after the
yellow's, and 3.5 mm up: at the paint's 2 mm plus 0.6 mm the yellow box hid it in game) are the road mesh's heights, so what lies
over what does not rest on the order of the mesh alone.

Lead-ins as a tree (_spines): the stands that stand in a row (noses near each other, axes within 72 degrees) share a spine, a
taxilane along the frontage through the points behind each tail by the largest half wingspan and SPINE_CLEAR_M (a ring for a satellite), its corners rounded and
painted as a centreline; the rounded line is also what the lead-ins leave, so each lead-in ends exactly on the paint. The spine is
joined to every mapped way it comes within SPINE_JOIN_MAX_M of (up to SPINE_CONN_MAX: _spine_connectors), each by a curve that leaves
the way along it and arrives along the spine, tangent at both ends (none where no way is near: it stands alone; a line is never cut
short on the open apron: a lead-in too long for LEAD_OVER_M still runs on to its lane); where a mapped way already runs within SPINE_LANE_M of
those points it is the spine and nothing is painted. Each stand's lead-in leaves the spine with a short curve onto its axis and
runs straight to the nose (every branch turning the same way; the spine ends at its last branch: _trim_spines); a stand of a row takes its lead-in from its row's spine only (one
that is longer than the aircraft plus LEAD_OVER_M is the straight run from the spine's nearest point), never also a line from another
lane; of two lead-ins that cross the longer is dropped. A stand that is in no row gets the nearest-lane line as before. Lane,
spine and lead-ins are a tree: no closed loop. The rows are made of the stand list alone, so every tile that reads the same stands
paints the same. Each lead-in ends in a straight run along its axis to the stop bar of at least lead_straight(length) (the nose to the main
gear and a quarter of the length, 20 m at least: an aircraft is lined up straight before it stops) and its arc (the radius of the kind or
more) starts behind it: where the lane is too close the join slides along the lane or spine, or the spine sits further out (_push_spine);
the straight is never shortened.

The mapped centrelines are painted rounded (_mapped_runs: _smooth_ways; SMOOTH_MAPPED_M): a way that goes back on another is two ways
that end on it, every corner an arc, each join tangent (a fillet), an end in an apron carried on to its edge, a gap closed, and the lead-ins
leave exactly those polylines (_lanes). audit(lines) / network() find what is left that is wrong: dangling ends, kinks and S-bends
(tools/airport_map.py draws and counts them).

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

CENTRE_W_M = 0.3            # m: the centreline's width (ICAO Annex 14: 0.15 m on a taxiway; 0.3 m: 0.15 m is under a pixel at range and the line
                            # breaks into dashes, so every yellow centreline, spine and lead-in is 0.3 m, with a black border BORDER_M each side)
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
LEAD_STRAIGHT_M = 2.0               # the straight run along the axis at least this long (_lead_line's default; a stand's own: lead_straight)
LEAD_STRAIGHT_MIN_M = 20.0          # a stand's lead-in is lined up straight along its axis for at least this far before the stop bar,
LEAD_STRAIGHT_K = 0.25              # ... or, if more, the aircraft's nose-to-main-gear distance and this of its length
LEAD_D_MIN_M = 2.0                  # the curve's tangent length at least this
LEAD_MIN_SIN = 0.17                 # a lane within 10 degrees of the axis (sine) is not crossed by it
ALONG_COS = 0.94                    # a lane end the nose points along (20 degrees) ...
ALONG_LAT_M = 2.0                   # ... within this of the axis, is the stand's own lead-in
LEAD_OVER_M = 40.0                  # a lead-in at most the aircraft's length and this long (a longer one is tried last, below)
LEAD_FAR_M = 400.0                  # ... a line is cut short by no length cap under this: it runs on to a lane (never a dead end)
SPINE_CLEAR_M = 7.5                 # a row's spine: through the points behind each stand's tail by the row's largest half wingspan and this
SPINE_PUSH_M = (0.0, 4.0, 8.0, 12.0, 18.0, 25.0, 35.0, 50.0, 70.0)    # (ICAO taxilane clearance; pushed further back, in these steps, where its curve is tighter than the radius, or
#                                     # a stand has no room between the spine and its nose for a straight run (lead_straight) and the arc of the radius),
SPINE_LINK_M = 25.0                 # ... of the stands (noses within half the spans and this of each other, axes within 72 degrees)
SPINE_LINK_COS = 0.3                # that stand in a row,
SPINE_RING_MIN = 4                  # ... a ring round a satellite (at least this many stands, their mean heading under
SPINE_RING_MEAN = 0.5               # this long: they face every way),
SPINE_LANE_M = 25.0                 # a mapped lane within this of every one of those points is the spine,
SPINE_JOIN_MAX_M = 60.0             # a spine's one end joined to the nearest mapped way by a curve at most this long (none: it stands alone),
MIN_RADIUS_M = 15.0                 # every curve of the painted yellow lines (lane to spine, spine to lead-in, a spine's corners, a
MIN_RADIUS_LIGHT_M = 8.0            # ... connector) a circular arc of at least this radius (light aircraft: this), or, where nothing
TIGHT_RADIUS_M = 3.0                # ... fits, the tightest smooth arc, this at the least (a line is never dropped for its radius)
CONNECTOR_FALLBACK_M = (12.0, 10.0, 8.0, 6.0, 4.5)     # (the radii tried between: a connector's largest that fits)
ARC_STEP_RAD = 0.1                  # an arc is chords turning at most this (no kink: under 25 degrees)
TURN_MAX_RAD = 3.3                  # an arc, a straight and an arc (_dubins) turning more than this in all is a loop: none
DUBINS_SLIDE_M, DUBINS_STEP_M = 60.0, 2.0       # the join point slid along a lane this far each way (_connector), this often
DUBINS_POINTS = 60                  # _lead_dubins tries the points of the lanes nearest to the axis point, this many
APRON_STEP_M = 1.0                  # a mapped line's parts on an apron found at this step (their black border)
SPINE_TRIES = 8                     # ... each from the nearest of this many points of the spine,
SPINE_CONN_MAX = 4                  # a spine joins up to this many mapped ways (a connector to each: _spine_connectors)
JOIN_TRIES = 4                      # a spine's connector tried from this many different mapped ways (nearest first)
TRIM_TOL_M = 0.1                    # a lead-in starts on its spine within this
LEAD_STUB_M = 25.0                  # a stand with no lane: a straight run from this far behind its tail to the nose
STOP_BAR_M = 3.6                    # the stop bars' length across the axis
WING_LINE_OFF_M = 3.0               # the wing-tip clearance lines: this far outside the wing tips,
WING_LINE_LEN_M = 20.0              # ... this long, ending at the stop bar's level
WING_CLEAR_M = 3.0                  # ... none within this of another stand's lead-in or envelope or of another stand's line,
WING_MIN_M = 6.0                    # ... a piece left after clipping shorter than this is none (_wing_lines),
WING_NEAR_M, WING_STEP_M = 150.0, 0.25          # ... the stands looked at, the clipping's step
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
WALL_TIE_M = 1.5                    # (two walls' edges this near along a ray are one edge)
ROAD_STEP_M = 2.0                   # the road is walked along the wall's outline at this step,
ROAD_TAPER = 0.6                    # ... easing back to the full distance this much a metre along the wall from a stand that is near,
ROAD_RING_FRAC = 0.4                # ... a ring all round the building where no two neighbouring stands are further apart (of its perimeter),
ROAD_ROUND_MIN = 0.6                # ... or a round building (4 pi area / perimeter squared this or more: a circle is 1) with a ring of stands,
ROAD_BREAK_M = 120.0                # ... else an arc, split where two neighbours are further apart than this,
ROAD_MIN_RADIUS_M = 8.0             # ... cut where the offset path bends tighter than this (a concave corner of the wall),
ROAD_PIECE_MIN_M = 6.0             # ... a piece (between the bridges and the buildings that cut it) shorter than this is none,
BRIDGE_ROAD_CLEAR_M = 4.8           # ... cut this far from a jet bridge's axis (the road's half width and the bridge's 1.3 m), wall to cab
BRIDGE_FOOT_M, BRIDGE_FOOT_MAX_M = 30.0, 80.0   # (a bridge's length where no wall is behind its cab: this; at most that)
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
SMOOTH_MAPPED_M = MIN_RADIUS_M      # the mapped centrelines are painted rounded (corners, joins, ends: _smooth_ways) at this radius (0: as mapped)
RELAX_K, RELAX_MAX_M, RELAX_ITERS = 0.97, 2.5, 300  # (a mapped curve tighter than this of the radius is eased, by up to this much, in so many passes)
EXTEND_M = 16.0                     # (the mapped ways) an end that touches nothing is carried on this far to the edge of the pavement,
JOIN_NODE_M = 0.1                   # (the mapped ways) two ways share a node: a vertex of one this near the other
FILLET_STEPS_M = (2.0, 3.0, 4.5, 6.0, 8.0, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0)     # (a mapped join's fillet: how far back along each line it may start,
FILLET_CAP = 0.6                    # ... at most this of the line,
FILLET_RADII_M = (12.0, 10.0, 8.0)  # ... else at these smaller radii,
FILLET_EXTRA_RAD = 0.6              # ... turning no more than the lines' directions differ by and this
AUDIT_GAP_M = 8.0                   # (the network audit) an end within this of another line but not on it is a gap,
AUDIT_ON_M = 0.25                   # ... on it: within this,
AUDIT_FREE_M = 1.5                  # ... an end this near a stop bar, a runway hold or an apron's or taxiway's edge is meant to stop there,
AUDIT_KINK_RAD = dmath.radians(20.0)  # ... a direction change of more than 20 degrees
AUDIT_JOIN_RAD = AUDIT_KINK_RAD     # (at a join: a line meets another at more than this from tangent and not straight through it),
AUDIT_WINDOW_M = 3.0                # ... within 3 m along a line is a kink,
AUDIT_S_LINK_M = 30.0               # ... two curves of opposite sense within this are an S-bend
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


def lead_straight(length):
    """The least length (m) of a lead-in's final straight run along the stand's axis, ending at the stop bar, for an aircraft of
    `length` m: the nose gear to the main gear (parkedaircraft's gear positions) plus LEAD_STRAIGHT_K of its length, at least
    LEAD_STRAIGHT_MIN_M: the aircraft is lined up straight before it reaches its stop position."""
    return max(LEAD_STRAIGHT_MIN_M, (pa.MAIN_GEAR_K - pa.NOSE_GEAR_K + LEAD_STRAIGHT_K) * float(length))


def _rmin(kind):
    """The smallest radius of a painted line's curve (lane to spine, spine to lead-in, a spine's corners) for a stand of `kind`."""
    return MIN_RADIUS_LIGHT_M if kind == "light" else MIN_RADIUS_M


def _arc_pts(c, p0, sense, angle):
    """The points (m, 2) of the circular arc round c from p0, `angle` radians in the sense +1 (counter-clockwise) or -1, in chords
    of at most ARC_STEP_RAD (so no vertex turns by more than that); p0 first, the arc's end last."""
    v = np.asarray(p0, np.float64) - c
    m = max(1, int(np.ceil(angle / ARC_STEP_RAD)))
    out = []
    for k in range(m + 1):
        a = sense * angle * k / m
        ca, sa = dmath.cos(a), dmath.sin(a)
        out.append(c + np.array([ca * v[0] - sa * v[1], sa * v[0] + ca * v[1]]))
    return np.array(out)


def _fillet(x, tin, tout, tl):
    """The circular arc (m, 2) that turns a line travelling along the unit vector tin into one along tout round the corner x: its
    tangent length tl (a radius of tl / tan(half the turn)), from x - tin tl to x + tout tl."""
    cross = float(tin[0] * tout[1] - tin[1] * tout[0])
    ang = dmath.atan2(abs(cross), float(tin[0] * tout[0] + tin[1] * tout[1]))
    p0, p2 = x - tin * tl, x + tout * tl
    if ang < 1e-6 or tl < 1e-9:
        return np.array([p0, p2])
    radius = tl / dmath.tan(ang / 2.0)
    sense = 1.0 if cross > 0.0 else -1.0
    c = p0 + np.array([-tin[1], tin[0]]) * (sense * radius)
    pts = _arc_pts(c, p0, sense, ang)
    pts[-1] = p2
    return pts


def _round_arcs(pts, radius, closed=False):
    """The polyline pts (k, 2) with every corner a circular arc of `radius` (tangent length radius tan(half the turn); less, so a
    tighter arc, where a side is short: at most half of each side, so that neighbouring corners do not meet). A closed polyline is
    rounded at its first point too; its result ends where it began."""
    P = np.asarray(pts, np.float64)
    if len(P) > 2 and bool(np.all(P[0] == P[-1])):
        closed, P = True, P[:-1]
    n = len(P)
    if n < 3:
        return P.copy()
    out = [] if closed else [P[0]]
    for i in (range(n) if closed else range(1, n - 1)):
        p0, p1, p2 = P[i - 1], P[i], P[(i + 1) % n]
        d0, d2 = float(dnp.hypot(*(p1 - p0))), float(dnp.hypot(*(p2 - p1)))
        if d0 < 1e-9 or d2 < 1e-9:
            out.append(p1)
            continue
        tin, tout = (p1 - p0) / d0, (p2 - p1) / d2
        ang = dmath.atan2(abs(float(tin[0] * tout[1] - tin[1] * tout[0])), float(tin[0] * tout[0] + tin[1] * tout[1]))
        if ang < 0.02:
            out.append(p1)
            continue
        tl = min(radius * dmath.tan(ang / 2.0), d0 / 2.0, d2 / 2.0)
        out.extend(_fillet(p1, tin, tout, tl))
    out.append(out[0] if closed else P[-1])
    return np.array(out)


def _dubins(p0, h0, p1, h1, radius):
    """The shortest path from the pose (p0, unit heading h0) to (p1, h1) that is an arc of `radius`, a straight line and an arc
    (Dubins' CSC: LSL, RSR, LSR, RSL), as (length, plan) for _dubins_pts; None where no such path turns by at most TURN_MAX_RAD in
    all (a loop is none)."""
    best = None
    left = lambda h: np.array([-h[1], h[0]])
    a0, a1 = dmath.atan2(float(h0[1]), float(h0[0])), dmath.atan2(float(h1[1]), float(h1[0]))
    for s0 in (1.0, -1.0):
        for s1 in (1.0, -1.0):
            c0, c1 = p0 + left(h0) * (s0 * radius), p1 + left(h1) * (s1 * radius)
            v = c1 - c0
            dist = float(dnp.hypot(*v))
            if s0 == s1:
                if dist < 1e-9:
                    a, straight = a0, 0.0
                else:
                    a, straight = dmath.atan2(float(v[1]), float(v[0])), dist
            else:
                if dist < 2.0 * radius + 1e-9:
                    continue
                straight = dmath.sqrt(dist * dist - 4.0 * radius * radius)
                a = dmath.atan2(float(v[1]), float(v[0])) + s0 * dmath.atan2(2.0 * radius, straight)
            t0 = (s0 * (a - a0)) % dmath.tau            # (the first arc turns from h0 to the straight's heading a ...)
            t0 = 0.0 if t0 > dmath.tau - 1e-6 else t0
            t1 = (s1 * (a1 - a)) % dmath.tau            # (... the second from a to h1)
            t1 = 0.0 if t1 > dmath.tau - 1e-6 else t1
            if t0 + t1 > TURN_MAX_RAD:
                continue
            length = radius * (t0 + t1) + straight
            if best is None or length < best[0] - 1e-9:
                best = (length, (p0, c0, s0, t0, c1, s1, t1, p1, h0, a, radius, straight))
    return best


def _dubins_pts(plan):
    """The polyline (k, 2) of a _dubins result: from p0 round the first arc, along the straight, round the second arc to p1."""
    p0, c0, s0, t0, c1, s1, t1, p1, _h0, a, radius, straight = plan[1]
    d = np.array([dmath.cos(a), dmath.sin(a)])
    first = _arc_pts(c0, p0, s0, t0) if t0 > 1e-9 else np.array([p0])
    mid = first[-1]
    end = mid + d * straight
    second = _arc_pts(c1, end, s1, t1) if t1 > 1e-9 else np.array([end])
    pts = np.vstack([first, second])
    pts[0], pts[-1] = p0, p1
    keep = np.r_[True, dnp.hypot(*np.diff(pts, axis=0).T) > 1e-6]
    return pts[keep]


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
    sc = Scene(frame, [(xy, w, x[4], x[2]) for xy, w, x in zip(wxy, wwidth, ways)],
               [(xy, half, x[3]) for (xy, half), x in zip(rw, runways)], sites)
    sc.memo["apron_rings"], sc.memo["pad_rings"] = _pavement_rings(sc, feats_list)
    return sc


def _pavement_rings(sc, feats_list):
    """([apron outline (k, 2)], [taxiway pad outline (k, 2)]) of the Features in feats_list, in the scene's plane: the places a
    centreline may end (an apron's edge, a taxiway's)."""
    aprons, pads = [], []
    try:
        aprons = _apron_rings(sc, feats_list)
        for la, lo in (r for r in aeroways.ways(feats_list) if len(r[0]) >= 4):
            e, n, _ = sc.frame.geodetic_to_enu(np.asarray(la, np.float64), np.asarray(lo, np.float64), np.zeros(len(la)))
            pads.append(np.stack([np.asarray(e), np.asarray(n)], 1))
    except Exception as ex:                     # (no rings: no line is carried on to one)
        log.warning("pavement edges: %s: %s", type(ex).__name__, ex)
    return aprons, pads


def _lanes(sc):
    """The scene's way segments for the lead-ins, kept on it: (a (m, 2), unit direction t (m, 2), length (m,), first (m,)
    and last (m,) of a way's, ends [(point, unit direction out of the way, way index)], the way's index of each segment (m,)):
    the polylines that are painted (_mapped_runs: rounded, cut at runways), so a lead-in always leaves the line that is there."""
    got = sc.memo.get("lanes")
    if got is None:
        a, b, first, last, ends, owner = [np.zeros((0, 2))], [np.zeros((0, 2))], [np.zeros(0, bool)], [np.zeros(0, bool)], [], []
        for xy, _cls, wi, at_first, at_last in _mapped_runs(sc):
            if len(xy) < 2:
                continue
            a.append(xy[:-1])
            b.append(xy[1:])
            f, l = np.zeros(len(xy) - 1, bool), np.zeros(len(xy) - 1, bool)
            f[0], l[-1] = at_first, at_last
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


def _stand_line(lanes, spine, nose, u, r, pads, length, rmin=MIN_RADIUS_M, straight=None):
    """The lead-in of a stand (the polyline (k, 2), or None where a lane already reaches the nose or runs along its axis), at most
    length + LEAD_OVER_M long (`length`: the aircraft's), exactly one per stand: the stand's own mapped lead-in lane carried on to
    the nose; else, for a stand of a row (`spine`: (lanes, forward) of _spines), a branch off its row's spine and never a line
    from another lane; else _lead_line's: the first that crosses no other pad; else one that crosses no runway's (pads' taxiway
    part only). Each at the radius rmin or more (r preferred; _lead_line's arcs and, where a lane has no room, its arc, straight
    and arc); where none has room, the same with the tightest smooth arc (TIGHT_RADIUS_M): a stand is never left without its
    line. Only where no lane is in reach at all the stub of LEAD_STUB_M behind the tail to the nose (a row's: the straight run
    from the spine's nearest point). Every line starts on the polyline of the lane or spine it leaves."""
    cap = length + LEAD_OVER_M
    straight = lead_straight(length) if straight is None else straight
    line, found = _lead_line(_empty_lanes(lanes[5]), nose, u, r, pads, cap)
    if found:
        return line
    if _alongside(lanes, nose, u):
        return None
    if spine is not None:
        sources = [(spine[0], pads, spine[1])]
    else:
        sources = [(lanes, pads, False), (lanes, _runway_pads(pads), False)]
    # (the radius is kept before the pads: at the radius rmin the lane's pads, then across them, before the tightest smooth arc;
    # the length cap is the last thing a line is dropped for: then the lane is reached anyway)
    for modes in (((rmin, True, False), (rmin, False, True)), ((TIGHT_RADIUS_M, True, False),)):
        for relaxed in (False, True):
            for cap_ in ((LEAD_FAR_M,) if relaxed else (cap, LEAD_FAR_M)):
                for radius, arcs, dubins in modes:
                    for ls, pd, forward in ([(sources[0][0], _runway_pads(pads), sources[0][2])] if relaxed else sources):
                        line, found = _lead_line(ls, nose, u, r, pd, cap_, forward, radius, dubins, arcs, straight)
                        if found:
                            return line
    for radius, arcs, dubins in ((rmin, True, False), (rmin, False, True), (TIGHT_RADIUS_M, True, False)):
        line, found = _lead_line(spine[0] if spine is not None else lanes, nose, -u, r, _runway_pads(pads), LEAD_FAR_M,   # (a stand that faces
                                 spine is not None and spine[1], radius, dubins, arcs, straight)                        # away from every lane: from its front)
        if found:
            return line
    lane_set = spine[0] if spine is not None else lanes
    a, t, ln = lane_set[:3]
    if len(a):                                  # (no smooth route: a straight run from the nearest point of the lane, never a dead end)
        tail = nose - u * length
        q = a + t * np.clip(dnp.vecdot(tail - a, t), 0.0, ln)[:, None]
        k = int(np.argmin(dnp.hypot(*(q - tail).T)))
        line = np.array([q[k], nose])
        if _length(line) <= LEAD_FAR_M and (spine is not None or not _crosses(_runway_pads(pads), line, int(lane_set[6][k]))):
            return line
    return np.array([nose - u * (length + LEAD_STUB_M), nose])


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


def _lead_line(lanes, n, u, r, pads=None, cap=LEAD_LINE_MAX_M, forward=False, rmin=MIN_RADIUS_M, dubins=False,
               arcs=True, straight=LEAD_STRAIGHT_M):
    """(polyline (k, 2), True) of the lead-in of a stand whose nose is at n, the nose direction u (unit), the curve's
    preferred radius r: from the lane the axis (tail-ward from n) meets nearest to n, along it, round a circular arc into the
    straight run to n (the arc's radius the largest of at most r that the lane and the run have room for: the join point slides
    back along the lane, never under rmin); (None, True) where a lane already reaches n; (None, False) without a lane. A line
    longer than `cap`, or across the pad of a taxiway or runway that is not the lane it leaves (pads: _pads), is passed over for
    the next lane. forward: every lane is left along its own direction (a spine's: all the branches turn the same way). dubins:
    where no lane has room for the arc at rmin, a path of an arc, a straight and an arc (_dubins) from a point slid along a lane
    (a lane nearly along the axis, one the axis meets too near its end); arcs False: that only."""
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
    cs = np.where(fwd, cos, -cos)                                   # the cosine of the turn from the lane's sense onto the axis
    sa = np.abs(det)
    half = np.where(cs > -0.9, sa / (1.0 + np.maximum(cs, -0.9)), np.inf)      # tan of half the turn
    room = np.minimum(tp, s - straight)                      # the tangent length the lane and the run have room for
    radius = np.minimum(r, np.where(half > 1e-9, room / np.maximum(half, 1e-9), np.inf))
    ok &= (s <= LEAD_MAX_M) & (tp <= l_ + ext + 0.05) & (room > 0.0) & (radius >= rmin - 1e-6)     # (a stand at a spine's very end meets it there)
    if arcs and ok.any():
        cost = np.where(ok, s + np.maximum(tp - l_, 0.0), np.inf)
        for k in np.argsort(cost, kind="stable")[:LEAD_TRIES]:
            if not np.isfinite(cost[k]):
                break
            tt = t_[k] if fwd[k] else -t_[k]
            start = a_[k] if fwd[k] else a_[k] + t_[k] * l_[k]
            tpk, dk = float(tp[k]), float(radius[k] * half[k])      # (the arc's tangent length)
            x = start + tt * tpk                                    # where the lane's line meets the axis: the corner
            arc = _fillet(x, tt, u, dk)
            pts = [start + tt * min(tpk - dk, float(l_[k]))]
            if float(dnp.hypot(*(arc[0] - pts[0]))) > 0.05:
                pts.append(arc[0])                                  # (the lane carried on to the arc)
            pts = np.array(pts + list(arc[1:]) + [n])
            if _length(pts) <= cap and not (pads is not None and _crosses(pads, pts, int(owner[near[k]]))):
                return pts, True
    if dubins:
        return _lead_dubins(a_, t_, l_, owner[near], n, u, rmin, pads, cap, forward, straight)
    return None, False


def _lead_dubins(a_, t_, l_, owner, n, u, radius, pads, cap, forward, straight=LEAD_STRAIGHT_M):
    """(polyline, True) of the shortest path of an arc, a straight and an arc (radius at least `radius`) from a point slid along the
    lane segments (a_, t_, l_: start, unit direction, length; owner: their ways) onto the axis `straight` m before the nose n and on
    to it, within `cap` and across no other pad; (None, False) where there is none. The points tried: every DUBINS_STEP_M along the
    segments, the DUBINS_POINTS nearest to the axis point (a spine of short arcs has its long straights beyond its nearest
    segments); a lane is left either way along it (forward: only the way it runs, a spine's)."""
    target = n - u * straight
    pts_, dirs_, own_ = [], [], []
    for k in range(len(a_)):
        sl = np.unique(np.r_[np.arange(0.0, float(l_[k]), DUBINS_STEP_M), float(l_[k])])
        pts_.append(a_[k] + t_[k] * sl[:, None])
        dirs_.append(np.repeat(t_[k][None], len(sl), axis=0))
        own_.append(np.full(len(sl), int(owner[k])))
    if not pts_:
        return None, False
    pts_, dirs_, own_ = np.concatenate(pts_), np.concatenate(dirs_), np.concatenate(own_)
    cands = []
    for q in np.argsort(dnp.hypot(*(pts_ - target).T), kind="stable")[:DUBINS_POINTS]:
        along = float(dirs_[q][0] * u[0] + dirs_[q][1] * u[1]) >= 0.0
        for sense in (1.0,) if forward else (1.0 if along else -1.0, -1.0 if along else 1.0):
            plan = _dubins(pts_[q], dirs_[q] * sense, target, u, radius)
            if plan is not None and plan[0] + straight <= cap:
                cands.append((round(plan[0], 3), int(q), sense, plan))
    cands.sort(key=lambda c: c[:3])
    for _length_, q, _sense, plan in cands[:LEAD_TRIES]:
        pts = np.vstack([_dubins_pts(plan), n])
        if not (pads is not None and _crosses(pads, pts, int(own_[q]))):
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


def _connector(q, tq, seg, p, sdir, pads, own, rmin=MIN_RADIUS_M, lanes=None, radii=None):
    """The curve (k, 2) from a mapped way to p, the end of a spine (its direction sdir from p along it): it leaves the way along
    its direction tq (turned to the sense the spine goes on in) and arrives along the spine, an arc of radius rmin or more, a
    straight and an arc (_dubins), from the point of the way's segment seg (start, length) that makes the shortest one: the join
    point slides along the way (its segments within the path's reach of p, `lanes`: _lanes' form; else the segment alone: DUBINS_STEP_M
    apart, each leaving along its own direction) until the arcs fit. Where none is across no other pad at rmin the same at the largest smaller radius (down to TIGHT_RADIUS_M: the tightest
    smooth fillet); the straight piece only where nothing smooth is clear of the pads (none of it with `radii`, a tuple: those radii
    only, None where none fits). None where p is on the way already."""
    v = p - q
    dist = float(dnp.hypot(*v))
    if dist < 0.5:
        return None
    sd = sdir / max(float(dnp.hypot(*sdir)), _EPS)
    t1 = sd if float(sd[0] * v[0] + sd[1] * v[1]) >= 0.0 else -sd         # (arrives going toward where the spine goes on)
    reach = dist + 4.0 * rmin
    pieces = [(seg[0], tq, float(seg[1]))]                                   # (start, direction, length) of the way's segments
    if lanes is not None:
        a_, t_, l_, _f, _l, _e, owner = lanes
        near = np.flatnonzero(owner == own)
        if len(near):
            d = a_[near] + t_[near] * np.clip(dnp.vecdot(p - a_[near], t_[near]), 0.0, l_[near])[:, None] - p
            pieces = [(a_[k], t_[k], float(l_[k])) for k in near[dnp.hypot(d[:, 0], d[:, 1]) <= reach]] or pieces
    for radius in radii or [rmin] + [x for x in CONNECTOR_FALLBACK_M if x < rmin] + [TIGHT_RADIUS_M]:
        cands = []
        for pi, (a, tq_, ln) in enumerate(pieces):
            s0 = min(max(float(tq_[0] * (q[0] - a[0]) + tq_[1] * (q[1] - a[1])), 0.0), ln)     # (q along the segment)
            lo, hi = max(0.0, s0 - reach), min(ln, s0 + reach)
            h0 = tq_ if float(tq_[0] * t1[0] + tq_[1] * t1[1]) >= 0.0 else -tq_
            for sl in np.unique(np.r_[np.arange(lo, hi, DUBINS_STEP_M), s0, hi]):
                plan = _dubins(a + tq_ * float(sl), h0, p, t1, radius)
                if plan is not None:
                    cands.append((round(plan[0], 3), pi, round(float(sl), 3), plan))
        cands.sort(key=lambda c: c[:3])
        for _length_, _pi, _sl, plan in cands[:LEAD_TRIES]:
            pts = _dubins_pts(plan)
            if len(pts) >= 2 and not _crosses(pads, pts, own):
                return pts
    return None if radii else np.array([q, p])


def _way_joins(lanes, pads, p):
    """[(q (2,), way index, unit direction (2,), segment start (2,), segment length)] _join's, for up to JOIN_TRIES different ways
    nearest p (nearest first): the points of the mapped ways a straight piece from p reaches without entering another pad."""
    a, t, ln, _f, _l, _e, owner = lanes
    if not len(a):
        return []
    q = a + t * np.clip(dnp.vecdot(p - a, t), 0.0, ln)[:, None]
    d = dnp.hypot(*(q - p).T)
    out, seen = [], set()
    for k in np.argsort(d, kind="stable")[:LEAD_TRIES * 4]:
        if d[k] > SPINE_JOIN_MAX_M:
            break
        wk = int(owner[k])
        if wk in seen:
            continue
        if d[k] < 0.5:
            return [(np.array(p, np.float64), wk, t[k], a[k], float(ln[k]))]
        if not _crosses(pads, np.array([p, q[k]]), wk):
            seen.add(wk)
            out.append((q[k], wk, t[k], a[k], float(ln[k])))
            if len(out) >= JOIN_TRIES:
                break
    return out


def _connector_joins(joins, p, sdir, pads, rmin, lanes, smooth_only=False, radii=None):
    """_connector's curve from the first of the mapped ways' `joins` (_joins') that has room at the largest radius: rmin, then
    smaller down to TIGHT_RADIUS_M; the straight piece from the nearest only where none is smooth (smooth_only: None then). None
    where p is on a way."""
    if float(dnp.hypot(*(p - joins[0][0]))) < 0.5:
        return None
    for radius in radii or [rmin] + [x for x in CONNECTOR_FALLBACK_M if x < rmin] + [TIGHT_RADIUS_M]:
        for q, wi, tq, a, ln in joins:
            got = _connector(q, tq, (a, ln), p, sdir, pads, wi, rmin, lanes, (radius,))
            if got is not None:
                return got
    return None if smooth_only else np.array([joins[0][0], p])


def _min_radius(P, closed=False):
    """The smallest radius of curvature of the polyline P (k, 2) (a vertex's: half the two sides over the turn there; a closed one has
    its first point repeated at its end and turns there too): inf for a straight line."""
    P = np.asarray(P, np.float64)
    if closed:
        P = np.vstack([P, P[1:2]])
    d = np.diff(P, axis=0)
    ln = dnp.hypot(d[:, 0], d[:, 1])
    best = np.inf
    for i in range(1, len(d)):
        if ln[i - 1] < 1e-9 or ln[i] < 1e-9:
            continue
        ang = dmath.atan2(abs(float(d[i - 1][0] * d[i][1] - d[i - 1][1] * d[i][0])), float(d[i - 1][0] * d[i][0] + d[i - 1][1] * d[i][1]))
        if ang > 0.02:
            best = min(best, 0.5 * float(ln[i - 1] + ln[i]) / ang)
    return best


def _under_aircraft(pts, items, margin):
    """Does the polyline pts (k, 2) come within `margin` m of the envelope (its length by its wingspan) of an aircraft of `items`
    [(nose, unit direction, length, span)]?"""
    P = np.asarray(pts, np.float64)
    seg = np.diff(P, axis=0)
    cnt = np.maximum(1, np.ceil(dnp.hypot(seg[:, 0], seg[:, 1]) / 2.0).astype(np.int64))
    smp = np.concatenate([P[j] + seg[j] * (np.arange(c) / c)[:, None] for j, c in enumerate(cnt)] + [P[-1:]])
    for nose, u, length, span in items:
        v = smp - (nose - u * (length / 2.0))
        along = np.abs(v[:, 0] * u[0] + v[:, 1] * u[1]) - length / 2.0
        across = np.abs(v[:, 0] * -u[1] + v[:, 1] * u[0]) - span / 2.0
        if bool((dnp.hypot(np.maximum(along, 0.0), np.maximum(across, 0.0)) < margin).any()):
            return True
    return False


def _spine_connectors(attach, lanes, pads, rmin, spine_lines, items=()):
    """[(connector polyline (k, 2), the spine point it arrives at)] of a spine (several: one to each mapped way the spine comes within
    reach of): from each of the points `attach` ([(point (2,), unit direction along the spine)] of the spine, its ends and each
    stand's tail) to the nearest point of each mapped way (_way_joins: within SPINE_JOIN_MAX_M, none across another pad), by
    _connector_joins: leaving the way along it and arriving along the spine, tangent at both ends, an arc of rmin or more (the
    largest that has room) and a straight. The first (the shortest) is kept whatever its length; the others are kept to
    SPINE_JOIN_MAX_M, at most SPINE_CONN_MAX in all, none that crosses the spine (`spine_lines`) or one already kept or passes
    within WING_CLEAR_M of an aircraft (`items`: _spines'); of a way's attach points, the next nearest where one does. A way the
    spine already lies on needs none. The spine joins the network at each of them; stand lead-ins still branch off the spine
    alone (the tree of the lead-ins has no loop)."""
    free = _runway_pads(pads)                   # (a taxiway's pad may be crossed, a runway's never)
    for pd, radii, smooth in ((pads, (rmin,), True), (free, (rmin,), True), (pads, None, True), (free, None, False)):
        got = _spine_joins(attach, lanes, pd, rmin, spine_lines, items, smooth, radii)       # (the radius before the pads, as the lead-ins)
        if got:
            return got
    return []


def _spine_joins(attach, lanes, pads, rmin, spine_lines, items, smooth_only, radii=None):
    """_spine_connectors' search over `pads` (smooth_only: no connector that is not an arc, a straight and an arc: the next attach
    point is tried instead of a straight piece)."""
    cands, on = {}, set()
    for p, sd in attach:
        for q, wi, tq, sa, sl in _way_joins(lanes, pads, p):
            d = float(dnp.hypot(*(q - p)))
            if d < 0.5:
                on.add(wi)
            else:
                cands.setdefault(wi, []).append((round(d, 3), round(float(p[0]), 3), round(float(p[1]), 3), p, sd, (q, wi, tq, sa, sl)))
    ways = sorted((w for w in cands if w not in on), key=lambda w: (min(c[:3] for c in cands[w]), w))
    kept = []
    for wi in ways:
        for _d, _x, _y, p, sd, join in sorted(cands[wi], key=lambda c: c[:3])[:SPINE_TRIES]:
            conn = _connector_joins([join], p, sd, pads, rmin, lanes, smooth_only, radii)
            if conn is None or len(conn) < 2 or (kept and _length(conn) > SPINE_JOIN_MAX_M):
                continue
            if any(_crossing(conn, other) for other in list(spine_lines) + [c for c, _p in kept]):
                continue
            if _under_aircraft(conn, items, WING_CLEAR_M):
                continue
            kept.append((conn, p))
            break
        if len(kept) >= SPINE_CONN_MAX:
            break
    return kept


def _push_spine(build, round_ok, fits):
    """build(extra) for the first of SPINE_PUSH_M (the spine's distance behind the tails) whose result passes round_ok and fits; where
    none passes both, the first that passes round_ok, else the last."""
    first, got = None, None
    for extra in SPINE_PUSH_M:
        got = build(extra)
        if round_ok(got):
            if fits(got):
                return got
            first = first or got
    return first or got


def _row_fits(spine, items, members, kinds):
    """Does every stand of a row (items' indexes `members`) have room between its spine (_poly_lanes') and its nose for the straight
    run of lead_straight and an arc of at least its kind's radius, leaving the spine along it?"""
    for i in members:
        nose, u, length, span = items[i]
        rmin = _rmin(kinds[i]) if kinds else MIN_RADIUS_M
        if not _lead_line(spine, nose, u, max(rmin, LEAD_RADIUS_K * span), None, LEAD_FAR_M, True, rmin, False, True, lead_straight(length))[1]:
            return False
    return True


class _Lines(list):
    """The polylines a function paints, and `roles` [(role, rmin)] one each: "spine" or "connector" (the network's, audit)."""

    def __init__(self):
        super().__init__()
        self.roles = []

    def put(self, xy, role, rmin):
        self.append(xy)
        self.roles.append((role, rmin))


def _along(items, members, mu, mean):
    """The members of a row in order across its mean heading mu."""
    along = np.array([-mu[1], mu[0]]) / max(mean, _EPS)
    return sorted(members, key=lambda i: (round(float(items[i][0][0] * along[0] + items[i][0][1] * along[1]), 3), i))


def _spines(items, lanes, pads, kinds=None):
    """({item index: (lanes, forward)}, [polyline (k, 2) to paint], [(members in order along the row, kind)], [(members, index of
    the spine in the polylines, index of its connector or None)]) of the rows of stands in items [(nose (2,), unit direction (2,),
    length, span)] (kinds: their aircraft kinds, for the radius: _rmin), the tree the lead-ins branch off. Stands link (noses
    within half their spans plus SPINE_LINK_M, axes within 72 degrees) into rows; a row of two or more has one spine, through the
    points behind each tail (the row's largest half wingspan and SPINE_CLEAR_M: ICAO's taxilane clearance), in order along the building (across the mean heading; by angle round the centroid for a
    satellite, a ring), its corners circular arcs (at least the row's _rmin): the rounded line is what is painted and what the lead-ins leave, so
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
    got, paint, listed, trims = {}, _Lines(), [], []
    a, t, ln, first, last, _ends, owner = lanes
    for members in sorted(rows.values(), key=lambda m: m[0]):
        if len(members) < 2:
            continue
        back = max(items[i][3] for i in members) / 2.0 + SPINE_CLEAR_M
        tails_at = lambda extra: np.array([items[i][0] - items[i][1] * (items[i][2] + back + extra) for i in members])
        tails = tails_at(0.0)
        rrow = max(_rmin(kinds[i]) for i in members) if kinds else MIN_RADIUS_M
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
            def build_ring(extra):
                tails = tails_at(extra)
                c = tails.mean(axis=0)
                ang = [dmath.atan2(float(y - c[1]), float(x - c[0])) for x, y in tails]
                order = sorted(range(len(members)), key=lambda k: (round(ang[k], 6), members[k]))
                return tails, order, _round_arcs(tails[order], rrow, closed=True)

            # (further out until the ring's corners are arcs of the radius and every stand has the room for its straight run and arc)
            tails, order, ring = _push_spine(build_ring, lambda b: _min_radius(b[2], True) >= rrow - 0.5,
                                             lambda b: _row_fits(_poly_lanes(b[2], closed=True), items, members, kinds))
            for c, _p in _spine_connectors([_project(ring, p)[:2] for p in tails[order]], lanes, pads, rrow, [ring], items):
                paint.put(c, "connector", rrow)
            paint.put(ring, "spine", rrow)
            sp = _poly_lanes(ring, closed=True), True
            kind = "ring"
        else:
            along = np.array([-mu[1], mu[0]]) / max(mean, _EPS)
            def build_chain(extra):
                tails = tails_at(extra)
                proj = dnp.vecdot(tails, along[None])
                order = sorted(range(len(members)), key=lambda k: (round(float(proj[k]), 3), members[k]))
                pts = tails[order]
                ja, jb = _join(lanes, pads, pts[0]), _join(lanes, pads, pts[-1])
                da = float(dnp.hypot(*(ja[0] - pts[0]))) if ja else np.inf
                db = float(dnp.hypot(*(jb[0] - pts[-1]))) if jb else np.inf
                if db < da:                             # (the end nearer to a mapped way is the start)
                    pts, order = pts[::-1], order[::-1]
                head = members[order[0]]
                ahead = max(_rmin(kinds[head]) if kinds else MIN_RADIUS_M, LEAD_RADIUS_K * items[head][3])
                e = pts[0] - pts[1]
                start = pts[0] + e / max(float(dnp.hypot(*e)), _EPS) * ahead        # (carried on: the first branch's arc)
                return pts, order, _round_arcs(np.array([start] + list(pts)), rrow)

            # (further out until the chain's corners are arcs of the radius and every stand has the room for its straight run and arc)
            pts, order, chain = _push_spine(build_chain, lambda b: _min_radius(b[2]) >= rrow - 0.5,
                                            lambda b: _row_fits(_poly_lanes(b[2]), items, members, kinds))
            # (the curves end on the painted line: at its start, its end and beside each tail)
            attach = [(chain[0], chain[1] - chain[0]), (chain[-1], chain[-2] - chain[-1])] + [_project(chain, p)[:2] for p in pts]
            conns = []
            for conn, at in _spine_connectors(attach, lanes, pads, rrow, [chain], items):
                conns.append((len(paint), _station(chain, at)))
                paint.put(conn, "connector", rrow)
            trims.append(([members[k] for k in order], len(paint), conns))
            paint.put(chain, "spine", rrow)
            sp = _poly_lanes(chain), True
            kind = "row"
        got.update({i: sp for i in members})
        listed.append(([members[k] for k in order], kind))
    return got, paint, listed, trims


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


def _pt_segs(p, s, e):
    """The distance from the point p to each of the segments s -> e (m, 2): (m,)."""
    d = e - s
    t = np.clip(dnp.vecdot(p - s, d) / np.maximum(dnp.vecdot(d, d), 1e-12), 0.0, 1.0)
    q = s + d * t[:, None]
    return dnp.hypot(q[:, 0] - p[0], q[:, 1] - p[1])


def _poly_seg_dist(P, a, b):
    """The distance between the polyline P (m, 2) and the segment a -> b (0 where they cross)."""
    s, e = P[:-1], P[1:]
    if not len(s):
        return float(_pt_segs(P[0], a[None], b[None])[0])
    cr = lambda o, p, q: (p[..., 0] - o[..., 0]) * (q[..., 1] - o[..., 1]) - (p[..., 1] - o[..., 1]) * (q[..., 0] - o[..., 0])
    d1, d2 = cr(a, b, s), cr(a, b, e)
    d3, d4 = cr(s, e, a), cr(s, e, b)
    if bool(((d1 * d2 < 0.0) & (d3 * d4 < 0.0)).any()):
        return 0.0
    ab = b - a
    t = np.clip(dnp.vecdot(P - a, ab[None]) / max(float(ab[0] * ab[0] + ab[1] * ab[1]), 1e-12), 0.0, 1.0)
    q = a + ab * t[:, None]
    near = float(dnp.hypot(P[:, 0] - q[:, 0], P[:, 1] - q[:, 1]).min())
    return min(near, float(_pt_segs(a, s, e).min()), float(_pt_segs(b, s, e).min()))


def _wing_lines(stands_, leads):
    """{stand index: [(a (2,), b (2,))]} of the wing-tip clearance lines of the stands (_lead_lines' tuples (Craft, unit direction,
    length, span, nose); leads: each stand's kept lead-in or None): WING_LINE_OFF_M outside the wing tips, WING_LINE_LEN_M long,
    ending level with the nose; where stands are close they would overlap or cross: a line is clipped so that nothing of it is
    within WING_CLEAR_M of another stand's envelope (the aircraft's rectangle: it does not run under an adjacent aircraft; a
    piece under WING_MIN_M is none), dropped where it comes within WING_CLEAR_M of another stand's lead-in, and of two lines that
    come within WING_CLEAR_M of each other (or cross) the one of the later stand is dropped (the earlier keeps the line they
    share)."""
    n = len(stands_)
    out = {i: [] for i in range(n)}
    if not n:
        return out
    noses = np.array([x[4] for x in stands_])
    raw = {}
    for i, (_c, u, _length, span, nose) in enumerate(stands_):
        left = np.array([-u[1], u[0]])
        for sgn in (-1.0, 1.0):
            side = left * sgn * (span / 2.0 + WING_LINE_OFF_M)
            raw[(i, sgn)] = (nose + side - u * WING_LINE_LEN_M, nose + side)
    for i in range(n):
        near = [j for j in np.flatnonzero(dnp.hypot(*(noses - noses[i]).T) <= WING_NEAR_M) if j != i]
        for sgn in (-1.0, 1.0):
            a, b = raw[(i, sgn)]
            k = max(2, int(np.ceil(WING_LINE_LEN_M / WING_STEP_M)) + 1)
            f = np.linspace(0.0, 1.0, k)[:, None]
            smp = a + (b - a) * f
            free = np.ones(k, bool)
            for j in near:                                  # (not under an adjacent aircraft: its envelope's distance)
                _cj, uj, lj, sj, nj = stands_[j]
                v = smp - (nj - uj * (lj / 2.0))
                along = np.abs(v[:, 0] * uj[0] + v[:, 1] * uj[1]) - lj / 2.0
                across = np.abs(v[:, 0] * -uj[1] + v[:, 1] * uj[0]) - sj / 2.0
                free &= dnp.hypot(np.maximum(along, 0.0), np.maximum(across, 0.0)) >= WING_CLEAR_M
            pieces, at = [], 0
            while at < k:
                if not free[at]:
                    at += 1
                    continue
                end = at
                while end + 1 < k and free[end + 1]:
                    end += 1
                if (end - at) * WING_LINE_LEN_M / (k - 1) >= WING_MIN_M:
                    pieces.append((smp[at], smp[end]))
                at = end + 1
            if not pieces:
                continue
            clash = False
            for j in near:
                if leads[j] is not None and any(_poly_seg_dist(leads[j], p, q) < WING_CLEAR_M for p, q in pieces):
                    clash = True
                for sg in (-1.0, 1.0):
                    if j < i and not clash:
                        c, d = raw[(j, sg)]
                        clash = _seg_dist(a, b, c, d) < WING_CLEAR_M
            if not clash:
                out[i] += pieces
    return out


def _seg_dist(a, b, c, d):
    """The distance between the segments a -> b and c -> d (0 where they cross)."""
    return _poly_seg_dist(np.array([c, d]), a, b)


def _subpath(P, lo, hi):
    """The part of the polyline P (k, 2) from `lo` to `hi` metres along it."""
    cum = standmarks.cumulative(P)
    inner = [P[i] for i in range(1, len(P) - 1) if lo + 1e-6 < cum[i] < hi - 1e-6]
    return np.array([standmarks.at(P, lo)[0]] + inner + [standmarks.at(P, hi)[0]])


def _trim_spines(paint, trims, found, keep):
    """`paint` (the spines and their connectors, _spines') without the branches that lead nowhere: a row's spine runs from its
    connector (or, with none, its first lead-in's start) to its last lead-in's start, and nothing beyond; with no lead-in of the
    row on it, neither the spine nor its connector is painted."""
    drop, cut = set(), {}
    for members, ci, conns in trims:
        chain = paint[ci]
        st = [_station(chain, found[i][0]) for i in members
              if i in keep and found[i] is not None and _project(chain, found[i][0])[2] < TRIM_TOL_M]
        if not st:
            drop.add(ci)
            drop.update(cj for cj, _s in conns)
            continue
        joined = st + [x for _cj, x in conns]       # (the spine runs from its first connector or branch to its last)
        lo, hi = min(joined), max(joined)
        if hi - lo < 0.3:
            drop.add(ci)
            drop.update(cj for cj, _s in conns)
        else:
            cut[ci] = _subpath(chain, lo, hi)
    out = _Lines()
    roles = getattr(paint, "roles", None) or [("spine", MIN_RADIUS_M)] * len(paint)
    for i, xy in enumerate(paint):
        if i not in drop:
            out.put(cut.get(i, xy), *roles[i])
    return out


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


def _wall_hit(nose, u, walls):
    """(distance, index) of the first edge of the rings `walls` ([(k, 2)]) the ray from the nose along u meets: (inf, -1) where it meets
    none. Where two rings' edges are within WALL_TIE_M along the ray (a satellite is part of its terminal's outline) the smaller ring."""
    best, which = np.inf, -1
    found = []
    for wi, ring in enumerate(walls):
        d = np.roll(ring, -1, axis=0) - ring
        w = ring - nose
        den = u[0] * d[:, 1] - u[1] * d[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (w[:, 0] * d[:, 1] - w[:, 1] * d[:, 0]) / den
            s = (w[:, 0] * u[1] - w[:, 1] * u[0]) / den
        ok = (np.abs(den) > _EPS) & (t > 0.0) & (s >= 0.0) & (s <= 1.0)
        if ok.any():
            found.append((float(t[ok].min()), wi))
    if found:
        best = min(t for t, _wi in found)
        size = lambda wi: float(np.prod(np.ptp(walls[wi], axis=0)))
        which = min((wi for t, wi in found if t <= best + WALL_TIE_M), key=lambda wi: (size(wi), wi))
        best = next(t for t, wi in found if wi == which)
    return best, which


def _wall_gap(nose, u, walls):
    """The distance from the nose along u to the first edge of the rings `walls` ([(k, 2)]): inf where there is none."""
    return _wall_hit(nose, u, walls)[0]


def _station(poly, p):
    """The distance along the polyline poly (k, 2) of its point nearest to p."""
    P = np.asarray(poly, np.float64)
    d = P[1:] - P[:-1]
    ln = dnp.hypot(d[:, 0], d[:, 1])
    t = np.clip(dnp.vecdot(p - P[:-1], d) / np.maximum(ln * ln, 1e-12), 0.0, 1.0)
    q = P[:-1] + d * t[:, None]
    k = int(np.argmin(dnp.hypot(*(q - p).T)))
    return float(ln[:k].sum() + t[k] * ln[k])


def _wall_samples(ring, step=ROAD_STEP_M):
    """(points (n, 2), outward unit normals (n, 2), stations (n,), perimeter) of the ring (k, 2) walked counter-clockwise, a point
    about every `step` m (the normals smoothed over the neighbours: a corner is rounded)."""
    P = np.asarray(ring, np.float64)
    if len(P) > 2 and float(dnp.hypot(*(P[0] - P[-1]))) < 1e-6:
        P = P[:-1]
    area = float((P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]).sum())
    if area < 0.0:
        P = P[::-1]
    seg = np.roll(P, -1, axis=0) - P
    ln = dnp.hypot(seg[:, 0], seg[:, 1])
    cnt = np.maximum(1, np.ceil(ln / step).astype(np.int64))
    pts = np.concatenate([P[j] + seg[j] * (np.arange(c) / c)[:, None] for j, c in enumerate(cnt)])
    tan = np.roll(pts, -2, axis=0) - np.roll(pts, 2, axis=0)
    tan = tan / np.maximum(dnp.hypot(tan[:, 0], tan[:, 1]), _EPS)[:, None]
    st = np.r_[0.0, np.cumsum(dnp.hypot(*np.diff(np.vstack([pts, pts[:1]]), axis=0).T))]
    return pts, np.stack([tan[:, 1], -tan[:, 0]], 1), st[:-1], float(st[-1])


def _offset_path(pts, d, closed):
    """standmarks.offset of the polyline pts (a closed one has its first point repeated at its end, and is mitred there too)."""
    if not closed:
        return standmarks.offset(pts, d)
    return standmarks.offset(np.vstack([pts[-2:-1], pts, pts[1:2]]), d)[1:-1]


def _runs(blocked, closed):
    """The runs of consecutive unblocked indices of the flags `blocked` (n,): [(indices, closed)]; a closed list's run goes on across
    its end; the whole list as one closed run where none is blocked."""
    n = len(blocked)
    if blocked.all():
        return []
    if not blocked.any():
        return [(np.arange(n), closed)]
    start = int(np.flatnonzero(blocked)[0]) + 1 if closed else 0
    order = [(start + k) % n for k in range(n)] if closed else list(range(n))
    out, cur = [], []
    for k in order:
        if blocked[k]:
            if cur:
                out.append(np.array(cur))
            cur = []
        else:
            cur.append(k)
    if cur:
        out.append(np.array(cur))
    return [(r, False) for r in out]


def _pt_segs_many(P, a, b):
    """The distance from each point of P (k, 2) to the segment a -> b: (k,)."""
    d = b - a
    t = np.clip(dnp.vecdot(P - a, d[None]) / max(float(d[0] * d[0] + d[1] * d[1]), 1e-12), 0.0, 1.0)
    q = a + d * t[:, None]
    return dnp.hypot(q[:, 0] - P[:, 0], q[:, 1] - P[:, 1])


def _service_roads(items, rows, walls, leads, bridges=()):
    """([(xy (k, 2), width, kind, colour)], [(polygon (k, 2), colour, layer)]) of the service roads of the stands (items:
    [(nose, unit direction, length, span)]; rows: _spines'; bridges: [(outer end (2,), unit direction out of the terminal)]):
    ONE path along each building's frontage, offset from its outline (`walls`: [(k, 2)] rings). The stands whose axis meets a
    wall (ROAD_MIN_GAP_M to ROAD_MAX_GAP_M from the nose: a nearer wall has none) set the road's distance from it, ROAD_WALL_M,
    nearer (ROAD_NOSE_M clear of the nose, the offset easing back ROAD_TAPER per metre along the wall) where the gap is short.
    A wall the stands stand all round (no two neighbours further apart than ROAD_RING_FRAC of its perimeter, or a satellite's
    ring of stands) has a ring all round it; any other wall the arc from its first stand to its last (half a span beyond each),
    split where two neighbours are over ROAD_BREAK_M apart. The path is cut only where a jet bridge's footprint (the bridge from
    its wall to its outer end, BRIDGE_ROAD_CLEAR_M clear), or a building that is not the wall it follows, is in the way, and goes on
    beyond. Two lanes ROAD_W_M wide in all: solid white edges, a dashed centre, a row of white give-way triangles each side of
    every lead-in (`leads`: polylines) that crosses it; and boxes for equipment (3 x 6 m, white outlines, numbered) on the wall
    side between two stands where the road is far enough from the wall."""
    ribbons, polys = [], []
    sm = standmarks
    ringed = set()
    for members, kind in rows:
        if kind == "ring":
            ringed.update(members)
    hits = {}                                           # wall index: [(item, wall point, road distance)]
    for i, (nose, u, _length_, _span) in enumerate(items):
        gap, wi = _wall_hit(nose, u, walls)
        if wi >= 0 and ROAD_MIN_GAP_M <= gap <= ROAD_MAX_GAP_M:
            hits.setdefault(wi, []).append((i, nose + u * gap, min(ROAD_WALL_M, gap - ROAD_NOSE_M)))
    feet = []                                           # the bridges' footprints: (a, b) from the wall to the cab
    for pt, d in bridges:
        back, _wi = _wall_hit(pt, -d, walls)
        feet.append((pt - d * (back if back <= BRIDGE_FOOT_MAX_M else BRIDGE_FOOT_M), pt))
    for wi in sorted(hits):
        mine = hits[wi]
        if len(mine) < 2:
            continue
        pts, nrm, st, perim = _wall_samples(walls[wi])
        n = len(pts)
        at = []                                         # (station, item, sample index, road distance) of each stand, in order
        for i, hp, cs in mine:
            k = int(np.argmin(dnp.hypot(pts[:, 0] - hp[0], pts[:, 1] - hp[1])))
            at.append((float(st[k]), i, k, cs))
        at.sort()
        stn = np.array([a[0] for a in at])
        dist = np.full(n, ROAD_WALL_M)
        for sa, _i, _k, cs in at:
            dd = np.abs(st - sa)
            dist = np.minimum(dist, cs + ROAD_TAPER * np.minimum(dd, perim - dd))
        gaps = np.diff(np.r_[stn, stn[0] + perim])      # (the gap after each stand, the last across the start)
        area = 0.5 * abs(float((pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1]).sum()))
        round_ = 4.0 * dmath.pi * area / max(perim * perim, _EPS) >= ROAD_ROUND_MIN and len(at) >= SPINE_RING_MIN   # (a satellite)
        closed = bool(gaps.max() <= ROAD_RING_FRAC * perim or round_ or sum(a[1] in ringed for a in at) >= SPINE_RING_MIN)
        centre = pts + nrm * dist[:, None]
        spans = []                                      # (sample indices, closed) of the paths along the wall
        if closed:
            spans.append((np.arange(n), True))
        else:
            cut = [j for j in range(len(at)) if gaps[j] > ROAD_BREAK_M]
            first = (cut[-1] + 1) % len(at) if cut else 0
            groups, cur = [], []
            for j in range(len(at)):
                cur.append((first + j) % len(at))
                if (first + j) % len(at) in cut:
                    groups.append(cur)
                    cur = []
            if cur:
                groups.append(cur)
            for g in groups:
                if len(g) < 2:
                    continue
                half0, half1 = items[at[g[0]][1]][3] / 2.0, items[at[g[-1]][1]][3] / 2.0
                lo = at[g[0]][0] - half0
                width = (at[g[-1]][0] - at[g[0]][0]) % perim + half0 + half1
                off = (st - lo) % perim
                idx = np.flatnonzero(off <= width)
                spans.append((idx[np.argsort(off[idx], kind="stable")], False))
        inner = pts - nrm                               # (a building that holds the wall: its outline has the wall's points just inside)
        others = [j for j in range(len(walls)) if j != wi and float(np.mean(polygon.contains_points(walls[j], inner))) < 0.5]
        number = 0
        for idx, loop in spans:
            c0, tg = centre[idx], np.stack([-nrm[idx][:, 1], nrm[idx][:, 0]], 1)
            keep = [0]                                  # (a concave corner folds the offset back on itself: those points go)
            for k in range(1, len(idx)):
                v = c0[k] - c0[keep[-1]]
                if float(v[0] * tg[k][0] + v[1] * tg[k][1]) > 0.3 * float(dnp.hypot(*v)) or (loop and k == len(idx) - 1):
                    keep.append(k)
            idx = idx[keep]
            c0 = centre[idx]
            blocked = np.zeros(len(idx), bool)
            if len(c0) > 2:                             # (a corner of the wall the road cannot follow: tighter than ROAD_MIN_RADIUS_M)
                v = np.diff(c0, axis=0)
                ln = np.maximum(dnp.hypot(v[:, 0], v[:, 1]), _EPS)
                for k in range(1, len(c0) - 1):
                    ang = dmath.atan2(abs(float(v[k - 1][0] * v[k][1] - v[k - 1][1] * v[k][0])), float(v[k - 1][0] * v[k][0] + v[k - 1][1] * v[k][1]))
                    if ang > 0.02 and 0.5 * float(ln[k - 1] + ln[k]) / ang < ROAD_MIN_RADIUS_M:
                        blocked[max(0, k - 1):k + 2] = True
            for a, b in feet:                           # (a jet bridge: its footprint)
                blocked |= _pt_segs_many(c0, a, b) < BRIDGE_ROAD_CLEAR_M
            for j in others:                            # (a building that is not the wall the road follows, nor one that holds it)
                lo_, hi_ = walls[j].min(axis=0), walls[j].max(axis=0)
                for side in (0.0, 1.0, -1.0):
                    q = c0 + nrm[idx] * (side * ROAD_W_M / 2.0)
                    m = np.all((q >= lo_) & (q <= hi_), axis=1) & ~blocked
                    if m.any():
                        blocked[np.flatnonzero(m)[polygon.contains_points(walls[j], q[m])]] = True
            for run, closed_run in _runs(blocked, loop):
                road = c0[run]
                if closed_run:
                    road = np.vstack([road, road[:1]])
                if _length(road) < ROAD_PIECE_MIN_M:
                    continue
                if closed_run:                          # (the walk's 2 m steps are only where the road bends; a ring in two halves)
                    m = len(road) // 2
                    road = np.vstack([_simplify(road[:m + 1], EDGE_TOL_M), _simplify(road[m:], EDGE_TOL_M)[1:]])
                else:
                    road = _simplify(road, EDGE_TOL_M)
                for side in (1.0, -1.0):
                    ribbons.append((_offset_path(road, side * ROAD_W_M / 2.0, closed_run), ROAD_LINE_W_M, ROAD_KIND, "white"))
                polys += [(p, "white", "paint") for p in sm.dashes(road, ROAD_DASH_M, ROAD_DASH_GAP_M, ROAD_LINE_W_M)]
                seen = []
                for lead in leads:
                    for pt, _s, d in sm.crossings(road, lead):
                        if any(float(dnp.hypot(*(pt - q))) < 1.0 for q in seen):
                            continue
                        seen.append(pt)
                        for sgn in (1.0, -1.0):
                            polys += [(p, "white", "paint") for p in sm.triangle_row(
                                pt + d * (sgn * (LEAD_W_M / 2.0 + GIVEWAY_AT_M)), d * sgn, ROAD_W_M - 1.0, GIVEWAY_N,
                                GIVEWAY_BASE_M, GIVEWAY_H_M)]
                here = []                               # (the stands whose road point is on this piece, in order along it)
                for _sa, i, k, cs in at:
                    if _project(road, centre[k])[2] < 1.0:
                        here.append((_station(road, centre[k]), i, k, cs))
                here.sort()
                mean_u = np.array([items[h[1]][1] for h in here]).mean(axis=0) if here else np.array([1.0, 0.0])
                mean_u = mean_u / max(float(dnp.hypot(*mean_u)), _EPS)
                for (si, _i, ki, ci), (sk, _k, _kk, ck) in zip(here, here[1:]):
                    span = sk - si - 2.0 * EQUIP_CLEAR_M
                    if span < EQUIP_BOX_M[0] or (ci + ck) / 2.0 < EQUIP_MIN_C_M:
                        continue
                    count = min(EQUIP_MAX, int((span + EQUIP_PITCH_M - EQUIP_BOX_M[0]) // EQUIP_PITCH_M))
                    for j in range(count):
                        p, _r = sm.at(road, (si + sk) / 2.0 + (j - (count - 1) / 2.0) * EQUIP_PITCH_M)
                        nu = -nrm[ki]                   # (towards the wall)
                        at_ = p + nu * (ROAD_W_M / 2.0 + 0.5 + EQUIP_BOX_M[1] / 2.0)
                        polys += [(q, "white", "paint") for q in sm.outline(at_, nu, EQUIP_BOX_M[0], EQUIP_BOX_M[1], ROAD_LINE_W_M)]
                        number += 1
                        polys += [(q, "white", "paint") for q in sm.text_polys(str(number), at_, mean_u, *EQUIP_TEXT)]
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
    net, stops = [], []                                 # the network's lines [(xy, role, rmin)] and the stops [(nose, unit direction, kind)]
    sm = standmarks

    def add(xy, kind=CENTRE_KIND, width=LEAD_W_M, under=True, role=None, rmin=MIN_RADIUS_M):
        k = tuple(round(float(q) * 2.0) for q in (xy[0, 0], xy[0, 1], xy[-1, 0], xy[-1, 1]))
        if k not in seen:
            seen.add(k)
            if role is not None:
                net.append((xy, role, rmin))
            if under:                                   # (the black border under every yellow lead-in and spine)
                out.append((xy, width + 2.0 * BORDER_M, UNDER_KIND, "black"))
            out.append((xy, width, kind, COLOR))

    def box(centre, up, w, h, colour="yellow", border=True):
        if border:
            polys.append((sm.box(centre, up, w + 2.0 * BORDER_M, h + 2.0 * BORDER_M), "black", "under"))
        polys.append((sm.box(centre, up, w, h), colour, "paint"))

    def lettered(text, centre, up, spec):
        polys.extend((p, "text", "glyph") for p in sm.text_polys(text, centre, up, *spec))

    stands_ = []                                        # (Craft, unit direction, length, span, nose) of the stands kept
    for j in pa.drop_overlaps(plane):
        c, ce, cn = st[j], float(e[j]), float(nn[j])
        u = np.array([c.ne, c.nn])
        u = u / max(float(dnp.hypot(*u)), _EPS)
        length, span = pa.SPECS[c.kind][0], pa.SPECS[c.kind][1]
        stands_.append((c, u, length, span, np.array([ce, cn]) + u * (length / 2.0)))
    items = [(x[4], x[1], x[2], x[3]) for x in stands_]
    spines, paint, rows, trims = _spines(items, lanes, pads, [x[0].kind for x in stands_])
    found = [_stand_line(lanes, spines.get(i), nose, u, max(_rmin(c.kind), LEAD_RADIUS_K * span), pads, length, _rmin(c.kind))
             for i, (c, u, length, span, nose) in enumerate(stands_)]
    stops = [(x[4], x[1], x[0].kind) for x in stands_]
    keep = _uncrossed(found)                            # (of two lead-ins that cross, the longer is dropped)
    leads = []
    trimmed = _trim_spines(paint, trims, found, keep)   # (the spines to their last lead-in: no branch that leads nowhere)
    for xy, (role, rm) in zip(trimmed, trimmed.roles):
        add(xy, role=role, rmin=rm)
        leads.append(xy)
    wings = _wing_lines(stands_, [found[i] if i in keep else None for i in range(len(stands_))])
    for i, (c, u, length, span, nose) in enumerate(stands_):
        line = found[i] if i in keep else None
        left = np.array([-u[1], u[0]])
        if line is not None:
            add(line, role="lead", rmin=_rmin(c.kind))
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
        for p, q in wings[i]:                           # (the wing-tip clearance lines, ending level with the stop bar)
            add(np.array([p, q]), STAND_KIND, CENTRE_W_M)
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
            ribbons, more = _service_roads(items, rows, walls, leads, bridges)
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
    sc.memo[("net", key)] = (net, stops)
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


def _apron_rings(sc, feats_list):
    """The aprons' outer rings of the Features in feats_list in the scene's plane: [(k, 2)]."""
    rings = []
    for la, lo in aeroways.aprons(feats_list):
        if len(la) >= 3:
            e, n, _ = sc.frame.geodetic_to_enu(np.asarray(la, np.float64), np.asarray(lo, np.float64), np.zeros(len(la)))
            rings.append(np.stack([np.asarray(e), np.asarray(n)], 1))
    return rings


def _inside_rings(xy, rings):
    """The parts of the polyline xy (k, 2) that lie inside one of the rings (sampled APRON_STEP_M apart, the polyline's own vertices
    kept): [(m, 2)] of at least two points, none for no rings."""
    if not rings:
        return []
    seg = np.diff(xy, axis=0)
    cnt = np.maximum(1, np.ceil(dnp.hypot(seg[:, 0], seg[:, 1]) / APRON_STEP_M).astype(np.int64))
    pts = np.concatenate([xy[j] + seg[j] * (np.arange(c) / c)[:, None] for j, c in enumerate(cnt)] + [xy[-1:]])
    inside = np.zeros(len(pts), bool)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    for r in rings:
        if (r.max(axis=0) < lo).any() or (r.min(axis=0) > hi).any():
            continue
        m = np.all((pts >= r.min(axis=0)) & (pts <= r.max(axis=0)), axis=1) & ~inside
        if m.any():
            inside[np.flatnonzero(m)[polygon.contains_points(r, pts[m])]] = True
    out, cur = [], []
    for p, ok in zip(pts, inside):
        if ok:
            cur.append(p)
        else:
            if len(cur) >= 2:
                out.append(np.array(cur))
            cur = []
    if len(cur) >= 2:
        out.append(np.array(cur))
    return out


def _branches(p, lines, lo, hi, skip, tol=AUDIT_ON_M):
    """[(unit direction leaving p, line index)] of every line but `skip` that passes through p or ends at it (within tol): a line
    through p leaves it both ways (at a vertex, along both sides)."""
    out = []
    for j in np.flatnonzero((lo <= p + tol).all(axis=1) & (hi >= p - tol).all(axis=1)):
        if j == skip:
            continue
        X = lines[j]
        d = X[1:] - X[:-1]
        sl = np.maximum(dnp.hypot(d[:, 0], d[:, 1]), _EPS)
        t = d / sl[:, None]
        for k in np.flatnonzero(_pt_segs(p, X[:-1], X[1:]) <= tol):
            s = float(dnp.vecdot(p - X[k], t[k]))
            if s > tol:                                 # (not at the segment's start: the way back along it)
                out.append((-t[k], int(j)))
            if sl[k] - s > tol:                         # (not at its end: the way on)
                out.append((t[k], int(j)))
    return out


def _ending(lines, j, p, tol=AUDIT_ON_M):
    """Does the line j end (start or finish) at p?"""
    return min(float(dnp.hypot(*(lines[j][0] - p))), float(dnp.hypot(*(lines[j][-1] - p)))) <= tol


def _fillet_ends(lines, radius):
    """`lines` ([polyline (k, 2)]) with the join of each line's end on another line made tangent: where a line ends on another line
    (or its end) at more than AUDIT_JOIN_RAD from along it, and no line of the join runs straight on from it, the line's last
    stretch is replaced by a circular arc (of `radius`; tighter where the line, or the one it joins, is short) that turns it onto the
    other line (the one it turns least onto) and meets it tangentially, a tangent length on from the junction. Where two lines
    only meet end to end (a corner), the second is cut back to where the arc meets it. The ends are taken in order (line, start then
    finish): each sees the changes before it."""
    L = [np.asarray(x, np.float64).copy() for x in lines]
    lo = np.array([x.min(axis=0) for x in L]).reshape(-1, 2)
    hi = np.array([x.max(axis=0) for x in L]).reshape(-1, 2)
    for i in range(len(L)):
        for end in (0, -1):
            X = L[i]
            if len(X) < 2 or float(dnp.hypot(*(X[0] - X[-1]))) < AUDIT_ON_M:
                continue
            p = X[end]
            br = _branches(p, L, lo, hi, i)
            if not br:
                continue
            Xf = X if end == 0 else X[::-1]                  # (leaving p)
            e = Xf[1] - Xf[0]
            mine = e / max(float(dnp.hypot(*e)), _EPS)
            ang = [_angle(mine, d) for d, _j in br]
            if min(ang) <= AUDIT_JOIN_RAD or max(ang) >= dmath.pi - AUDIT_JOIN_RAD:
                continue
            k = max(range(len(br)), key=lambda q: (round(ang[q], 9), -br[q][1]))
            db, j = br[k]
            turn = dmath.pi - ang[k]
            B = L[j]
            lenA, lenB = _length(Xf), _length(B)
            sig = _station(B, p)
            fwd = float(dnp.vecdot(standmarks.at(B, sig + 0.5 if sig + 0.5 <= lenB else sig - 0.5)[1], db)) >= 0.0     # (db's way along B)
            avail = (lenB - sig) if fwd else sig
            tl = min(radius * dmath.tan(turn / 2.0), 0.5 * lenA, 0.5 * avail)
            if tl < 0.5:
                continue
            pairs = [(tl, tl)] + sorted(((x, y) for x in FILLET_STEPS_M for y in FILLET_STEPS_M
                                         if x <= FILLET_CAP * lenA and y <= FILLET_CAP * avail), key=lambda c: (c[0] + c[1], c))
            got = None                  # (the first that is smooth: a round fillet where both lines are straight; further out where the
            for r in (radius,) + FILLET_RADII_M:        # line is already curving into the join)
                for ta, tb in pairs:
                    pa_, da = standmarks.at(Xf, ta)
                    pb_, db_ = standmarks.at(B, sig + tb if fwd else sig - tb)
                    hb = db_ if fwd else -db_
                    plan = _dubins(pa_, -da, pb_, hb, r if (ta, tb) != (tl, tl) else max(tl / dmath.tan(turn / 2.0), 1e-3))
                    if plan is not None and plan[1][3] + plan[1][6] <= _angle(-da, hb) + FILLET_EXTRA_RAD:
                        got = (plan, ta, tb)
                        break
                if got:
                    break
            if got is None:
                continue
            plan, tl, tb = got
            arc = _dubins_pts(plan)
            tail = _subpath(Xf, tl, lenA)
            new = np.vstack([arc[::-1], tail[1:]]) if len(tail) > 1 else arc[::-1]
            L[i] = new if end == 0 else new[::-1]
            if len(br) == 1 and _ending(L, j, p) and tb < lenB - 0.1:                 # (the corner's other line, cut back to the arc's end)
                L[j] = _subpath(B, tb, lenB) if fwd else _subpath(B, 0.0, lenB - tb)
            for q in (i, j):
                lo[q], hi[q] = L[q].min(axis=0), L[q].max(axis=0)
    return L


def _split_ways(ways):
    """[(polyline (k, 2), way index, starts the way, ends the way)] of `ways` ([(k, 2)]) split at each vertex where the way turns
    by more than AUDIT_JOIN_RAD and another way passes (a node they share): a way that touches another way there and goes back
    (a fillet drawn out and back, as one way) is two ways that end on it."""
    P = [np.asarray(x, np.float64) for x in ways]
    lo = np.array([x.min(axis=0) for x in P]).reshape(-1, 2) - JOIN_NODE_M
    hi = np.array([x.max(axis=0) for x in P]).reshape(-1, 2) + JOIN_NODE_M
    out = []
    for i, X in enumerate(P):
        cuts = [0]
        for k in range(1, len(X) - 1):
            d0, d1 = X[k] - X[k - 1], X[k + 1] - X[k]
            if min(float(dnp.hypot(*d0)), float(dnp.hypot(*d1))) < _EPS or _angle(d0, d1) <= AUDIT_JOIN_RAD:
                continue
            near = np.flatnonzero((lo <= X[k]).all(axis=1) & (hi >= X[k]).all(axis=1))
            if any(j != i and len(P[j]) >= 2 and float(_pt_segs(X[k], P[j][:-1], P[j][1:]).min()) <= JOIN_NODE_M for j in near):
                cuts.append(k)
        cuts.append(len(X) - 1)
        for m, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
            out.append((X[a:b + 1], i, m == 0, m == len(cuts) - 2))
    return out


def _relax(P, radius):
    """The polyline P (k, 2) with its curves tighter than RELAX_K times `radius` eased (each vertex there, and its neighbours, moved
    towards the middle of its neighbours, over and over: the bend spreads out and its radius grows), none more than RELAX_MAX_M from
    where it was and the ends where they were. Unchanged without such a curve."""
    P = np.asarray(P, np.float64)
    if len(P) < 3:
        return P
    cur, home = P.copy(), P.copy()
    for _ in range(RELAX_ITERS):
        d0, d1 = cur[1:-1] - cur[:-2], cur[2:] - cur[1:-1]
        l0, l1 = dnp.hypot(d0[:, 0], d0[:, 1]), dnp.hypot(d1[:, 0], d1[:, 1])
        ang = np.abs(dnp.arctan2(d0[:, 0] * d1[:, 1] - d0[:, 1] * d1[:, 0], d0[:, 0] * d1[:, 0] + d0[:, 1] * d1[:, 1]))
        with np.errstate(divide="ignore", invalid="ignore"):
            tight = (0.5 * (l0 + l1) / np.maximum(ang, 1e-9) < RELAX_K * radius) & (ang > 0.02)
        if not tight.any():
            break
        mask = tight.copy()
        mask[1:] |= tight[:-1]
        mask[:-1] |= tight[1:]
        mid = 0.25 * (cur[:-2] + cur[2:]) + 0.5 * cur[1:-1]
        new = np.where(mask[:, None], mid, cur[1:-1])
        off = new - home[1:-1]
        far = dnp.hypot(off[:, 0], off[:, 1])
        new = np.where((far > RELAX_MAX_M)[:, None], home[1:-1] + off * (RELAX_MAX_M / np.maximum(far, _EPS))[:, None], new)
        cur[1:-1] = new
    return cur


def _extend_ends(S, pieces, aprons, pads=()):
    """`S` ([polyline (k, 2)]: the smoothed pieces of mapped ways) with each way's end that touches nothing carried on, straight along
    its end, to the first thing it meets: within EXTEND_M the edge of an apron (`aprons`) that the end is inside, or of a taxiway's pad
    (`pads`: the pavement's end), a centreline that stopped short of the edge; or, within AUDIT_GAP_M and anywhere, another line (a
    gap). pieces: _split_ways' (the way's own ends are the ones)."""
    rings = list(aprons) + list(pads)
    out = [x.copy() for x in S]
    lo = np.array([x.min(axis=0) for x in out]).reshape(-1, 2)
    hi = np.array([x.max(axis=0) for x in out]).reshape(-1, 2)
    rlo = np.array([r.min(axis=0) for r in rings]).reshape(-1, 2)
    rhi = np.array([r.max(axis=0) for r in rings]).reshape(-1, 2)

    def hits(p, d, X, reach):
        """The nearest distance t in (0, reach] along p + t d where the polyline X crosses it (inf: none)."""
        a, e = X[:-1], X[1:] - X[:-1]
        den = d[0] * e[:, 1] - d[1] * e[:, 0]
        w = a - p
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (w[:, 0] * e[:, 1] - w[:, 1] * e[:, 0]) / den
            u = (w[:, 0] * d[1] - w[:, 1] * d[0]) / den
        ok = (np.abs(den) > 1e-9) & (t > 0.05) & (t <= reach) & (u >= 0.0) & (u <= 1.0)
        return float(t[ok].min()) if ok.any() else np.inf

    for i, X in enumerate(out):
        if len(X) < 2 or float(dnp.hypot(*(X[0] - X[-1]))) < AUDIT_ON_M:
            continue
        for end, own in ((0, pieces[i][2]), (-1, pieces[i][3])):
            p = X[end]
            if not own:
                continue
            others = [j for j in np.flatnonzero((lo <= p + EXTEND_M).all(axis=1) & (hi >= p - EXTEND_M).all(axis=1)) if j != i]
            if any(float(_pt_segs(p, out[j][:-1], out[j][1:]).min()) <= AUDIT_ON_M for j in others):
                continue                                # (on a line already)
            rnear = np.flatnonzero((rlo <= p + EXTEND_M).all(axis=1) & (rhi >= p - EXTEND_M).all(axis=1))
            if any(float(_pt_segs(p, rings[r][:-1], rings[r][1:]).min()) <= AUDIT_FREE_M for r in rnear):
                continue                                # (at an edge already)
            if not any(r < len(aprons) and len(rings[r]) >= 3 and bool(polygon.contains_points(rings[r], p[None])[0]) for r in rnear):
                rnear = rnear[:0]                       # (not in an apron: only a line it nearly meets)
            e = X[end] - X[1 if end == 0 else -2]
            n = float(dnp.hypot(*e))
            if n < _EPS:
                continue
            d = e / n
            t = min([hits(p, d, rings[r], EXTEND_M) for r in rnear] + [hits(p, d, out[j], AUDIT_GAP_M) for j in others] + [np.inf])
            if np.isfinite(t):
                q = p + d * t
                out[i] = np.vstack([X, q]) if end == -1 else np.vstack([q, X])
                X = out[i]
                lo[i], hi[i] = X.min(axis=0), X.max(axis=0)
    return out


def _smooth_ways(ways, radius=MIN_RADIUS_M, aprons=(), pads=()):
    """[(polyline (k, 2), way index, starts the way, ends the way)] of the polylines `ways` ([(k, 2)]: the mapped centrelines) as they
    are painted: split where a way goes back on another (_split_ways), every corner a circular arc (_round_arcs), the curves still
    tighter than the radius eased (_relax), each end that is on another way (within aeroways.JOIN_TOL_M: a node they share) moved
    onto that way's rounded line, each end that touches nothing carried on to the edge of the apron it is in or of a pad (`aprons`, `pads`:
    _pavement_rings) or the line it nearly meets (_extend_ends), and each join made tangent (_fillet_ends)."""
    pieces = _split_ways(ways)
    P = [x[0] for x in pieces]
    lo = np.array([x.min(axis=0) for x in P]).reshape(-1, 2) - aeroways.JOIN_TOL_M
    hi = np.array([x.max(axis=0) for x in P]).reshape(-1, 2) + aeroways.JOIN_TOL_M
    nodes = []                                      # (piece, end, the other piece): an end on another way
    for i, X in enumerate(P):
        if len(X) < 2 or float(dnp.hypot(*(X[0] - X[-1]))) < _EPS:
            continue
        for end in (0, -1):
            p = X[end]
            near = [(float(_pt_segs(p, P[j][:-1], P[j][1:]).min()), int(j)) for j in np.flatnonzero((lo <= p).all(axis=1) & (hi >= p).all(axis=1))
                    if j != i and len(P[j]) >= 2 and pieces[j][1] != pieces[i][1]]
            near = [c for c in near if c[0] <= aeroways.JOIN_TOL_M]
            if near:
                nodes.append((i, end, min(near)[1]))        # (on the nearest way only)
    S = [_relax(_round_arcs(X, radius), radius) if len(X) >= 3 else X.copy() for X in P]
    for i, end, j in nodes:
        q, _t, d = _project(S[j], P[i][end])
        if d <= 2.0 * aeroways.JOIN_TOL_M + radius:
            S[i][end] = q
    return [(xy,) + tuple(x[1:]) for xy, x in zip(_fillet_ends(_extend_ends(S, pieces, aprons, pads), radius), pieces)]


def _mapped_runs(sc):
    """[(xy (k, 2), class, way index, first, last)] of the mapped ways' centrelines as painted (_smooth_ways: rounded, the joins
    tangent), cut where they enter a runway (RUNWAY_GAP_M clear of its edge); first and last: the run's start / end is the way's
    own. In the scene's plane; kept on the scene: the lead-ins leave these polylines, the ones that are painted."""
    got = sc.memo.get("runs")
    if got is None:
        try:
            if SMOOTH_MAPPED_M <= 0.0:
                raise ValueError("not smoothed")
            pieces = _smooth_ways([w[0] for w in sc.ways], SMOOTH_MAPPED_M, sc.memo.get("apron_rings", ()), sc.memo.get("pad_rings", ()))
        except Exception as ex:                      # (the unsmoothed centrelines are worth more than none)
            if SMOOTH_MAPPED_M > 0.0:
                log.warning("smoothing the taxiways: %s: %s", type(ex).__name__, ex)
            pieces = [(w[0], i, True, True) for i, w in enumerate(sc.ways)]
        blocks = _runway_blocks([x[0] for x in pieces], [(r[0], r[1]) for r in sc.runways], RUNWAY_GAP_M)
        got = sc.memo["runs"] = []
        for (sm, wi, at_first, at_last), blk in zip(pieces, blocks):
            for run in (_free_runs(sm, blk) if blk else [sm]):
                got.append((run, sc.ways[wi][3], wi, at_first and bool(float(dnp.hypot(*(run[0] - sm[0]))) < _EPS),
                            at_last and bool(float(dnp.hypot(*(run[-1] - sm[-1]))) < _EPS)))
    return got


def _build(feats_list):
    """(lines, boxes): lines [(lat (k,), lon (k,), width, kind, color)], each a polyline (a hold marking's stroke is of
    two points), and boxes (n, 4) their lat0, lat1, lon0, lon1 extents."""
    sc = scene(feats_list)
    if sc is None:
        return [], np.zeros((0, 4))
    out = []                                    # (xy (k, 2), width, kind[, colour])
    try:                                        # (the aprons: a yellow line on one has its black border, as the lead-ins do)
        aprons = _apron_rings(sc, feats_list)
    except Exception as ex:
        log.warning("apron outlines: %s: %s", type(ex).__name__, ex)
        aprons = []
    for run, cls, _wi, _f, _l in _mapped_runs(sc):
        # (the black border under the parts on an apron; a taxilane is the aprons' own: its whole length)
        parts = [run] if cls != "taxiway" and len(run) >= 2 else _inside_rings(run, aprons)
        out += [(part, CENTRE_W_M + 2.0 * BORDER_M, UNDER_KIND, "black") for part in parts]
        out.append((run, CENTRE_W_M, CENTRE_KIND))
    for _ri, wi, site, u in sc.sites:
        for x0, y0, x1, y1, lw, kind in _hold_strokes(site, u, sc.ways[wi][1]):
            out.append((np.array([[x0, y0], [x1, y1]]), lw, kind))
    try:                                        # (the taxiways' double edge lines)
        out += [(xy, w, kind) for xy, w, kind, _c in _edge_lines(sc, feats_list)]
    except Exception as ex:                     # (the centrelines are worth more than the edges)
        log.warning("taxiway edge lines: %s: %s", type(ex).__name__, ex)
    lines, boxes = [], []
    for xy, w, kind, *colour in out:
        la, lo, _ = sc.frame.enu_to_geodetic(xy[:, 0], xy[:, 1], np.zeros(len(xy)))
        la, lo = np.asarray(la), np.asarray(lo)
        lines.append((la, lo, w, kind, colour[0] if colour else COLOR))
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


# ---- the network audit: what a driver of the painted centrelines would see wrong ---------------------------------------------

def _angle(a, b):
    """The angle (radians, 0 to pi) between the vectors a and b."""
    return dmath.atan2(abs(float(a[0] * b[1] - a[1] * b[0])), float(a[0] * b[0] + a[1] * b[1]))


def _turns(P):
    """(vertex indices (m,), signed turn at each (m,) radians, station of each (m,) m along P, radius estimate of each (m,) m) of the
    vertices of the polyline P (k, 2) where it turns (a vertex's radius: half its two sides over its turn)."""
    P = np.asarray(P, np.float64)
    d = np.diff(P, axis=0)
    ln = dnp.hypot(d[:, 0], d[:, 1])
    idx = np.flatnonzero(ln > 1e-9)
    d, ln = d[idx], ln[idx]
    cum = np.r_[0.0, np.cumsum(ln)]
    out = []
    for j in range(1, len(d)):
        ang = dmath.atan2(float(d[j - 1][0] * d[j][1] - d[j - 1][1] * d[j][0]), float(d[j - 1][0] * d[j][0] + d[j - 1][1] * d[j][1]))
        if abs(ang) >= 1e-6:
            out.append((int(idx[j]), ang, float(cum[j]), 0.5 * float(ln[j - 1] + ln[j]) / abs(ang)))
    return tuple(np.array(c) for c in zip(*out)) if out else (np.zeros(0, np.int64), np.zeros(0), np.zeros(0), np.zeros(0))


class Audit:
    """What audit found: gaps [(x, y, distance to the line it nearly meets)], opens [(x, y)] (ends in the open, touching nothing),
    kinks [(x, y, degrees)] (a turn along a line, or at a join), sbends [(x, y, radius)]."""
    __slots__ = ("gaps", "opens", "kinks", "sbends")

    def __init__(self):
        self.gaps, self.opens, self.kinks, self.sbends = [], [], [], []

    def counts(self):
        return {"gaps": len(self.gaps), "opens": len(self.opens), "kinks": len(self.kinks), "sbends": len(self.sbends)}

    def __len__(self):
        return len(self.gaps) + len(self.opens) + len(self.kinks) + len(self.sbends)


def _unique_marks(marks, tol=1.0):
    """marks [(x, y, ...)] without any within tol of an earlier one."""
    out = []
    for m in marks:
        if not any(abs(m[0] - o[0]) <= tol and abs(m[1] - o[1]) <= tol for o in out):
            out.append(m)
    return out


def audit(lines, stops=(), edges=(), runways=(), rmin=MIN_RADIUS_M, rmins=None, aprons=None):
    """The Audit of the painted centreline network `lines` ([polyline (k, 2) m]):
    gaps: an end of a line within AUDIT_GAP_M of another line but not on it (AUDIT_ON_M): two lines that nearly meet;
    opens: an end in the open apron (inside one of `aprons`, [ring (m, 2)]; None: every end is) further than that from every other
        line: touching nothing. Neither is reported where the end is a place a line is meant to stop: within AUDIT_FREE_M of one of `stops` ([(x, y)]: stand stop bars, runway holds) or of an
        edge of `edges` ([polyline or ring (m, 2)]: an apron's or a taxiway's), or at a runway (`runways`: [(centreline (m, 2),
        half width)]: its edge and RUNWAY_GAP_M); a closed line (its first point its last) has no ends;
    kinks: along a line, a direction change of over AUDIT_KINK_DEG within AUDIT_WINDOW_M (more where the line's `rmin`, the
        smallest radius of its curves, allows it: a tight arc turns by the window over its radius); and at a join, a line's end
        on another line (or on its end) that leaves it neither along it (within AUDIT_JOIN_DEG) nor straight through it (another
        line of the join opposite to it, the same): a crossing straight through is none;
    sbends: two curves of opposite sense within AUDIT_S_LINK_M of each other, the tighter of radius under rmin.
    rmins: the lines' own rmin (default `rmin` each); aprons: see opens."""
    P = [np.asarray(x, np.float64) for x in lines if x is not None and len(x) >= 2]
    rm = list(rmins) if rmins is not None else [rmin] * len(P)
    res = Audit()
    if not P:
        return res
    a = np.concatenate([x[:-1] for x in P])
    b = np.concatenate([x[1:] for x in P])
    lid = np.concatenate([np.full(len(x) - 1, i) for i, x in enumerate(P)])
    sl = np.maximum(dnp.hypot(*(b - a).T), _EPS)
    tt = (b - a) / sl[:, None]
    marks = [np.asarray(p, np.float64) for p in stops]
    rings = [np.asarray(e, np.float64) for e in edges if len(e) >= 2]
    rways = [(np.asarray(r, np.float64), float(h)) for r, h in runways if len(r) >= 2]

    def is_free(p):
        if any(float(dnp.hypot(*(p - q))) <= AUDIT_FREE_M for q in marks):
            return True
        for ring in rings:
            if (p >= ring.min(axis=0) - AUDIT_FREE_M).all() and (p <= ring.max(axis=0) + AUDIT_FREE_M).all():
                if float(_pt_segs(p, ring[:-1], ring[1:]).min()) <= AUDIT_FREE_M:
                    return True
        return any(float(_pt_segs(p, r[:-1], r[1:]).min()) <= h + RUNWAY_GAP_M + AUDIT_FREE_M for r, h in rways)

    def in_apron(p):
        return aprons is None or any((p >= r.min(axis=0)).all() and (p <= r.max(axis=0)).all()
                                     and bool(polygon.contains_points(r, p[None])[0]) for r in aprons if len(r) >= 3)

    def leaving(p, skip):
        """The unit directions leaving p along the lines other than `skip` that pass through or end at p."""
        out = []
        for k in np.flatnonzero((_pt_segs(p, a, b) <= AUDIT_ON_M) & (lid != skip)):
            s = float(dnp.vecdot(p - a[k], tt[k]))
            if s > AUDIT_ON_M:                      # (not at the segment's start: the way back along it)
                out.append(-tt[k])
            if sl[k] - s > AUDIT_ON_M:              # (not at its end: the way on)
                out.append(tt[k])
        return out

    gaps, opens, kinks = [], [], []
    for i, x in enumerate(P):
        if len(x) > 2 and float(dnp.hypot(*(x[0] - x[-1]))) < AUDIT_ON_M:
            ends = ()
        else:
            ends = (0, -1)
        for end in ends:
            p = x[end]
            other = lid != i
            near = float(_pt_segs(p, a[other], b[other]).min()) if other.any() else np.inf
            if near <= AUDIT_ON_M:
                mine = (x[1] - x[0]) if end == 0 else (x[-2] - x[-1])
                mine = mine / max(float(dnp.hypot(*mine)), _EPS)
                dirs = leaving(p, i)
                if not dirs:
                    continue
                ang = [_angle(mine, d) for d in dirs]
                dev = min(min(g, dmath.pi - g) for g in ang)
                if dev > AUDIT_JOIN_RAD and max(ang) < dmath.pi - AUDIT_JOIN_RAD:
                    kinks.append((float(p[0]), float(p[1]), dmath.degrees(dev)))
            elif not is_free(p):
                if near <= AUDIT_GAP_M:
                    gaps.append((float(p[0]), float(p[1]), near))
                elif in_apron(p):
                    opens.append((float(p[0]), float(p[1])))
        idx, tn, st, rd = _turns(x)
        if not len(idx):
            continue
        allowed = max(AUDIT_KINK_RAD, AUDIT_WINDOW_M / max(rm[i], _EPS) * 1.05)
        until = -1.0
        for j in range(len(idx)):                   # (turns along the line: the direction change within the window)
            if st[j] < until:
                continue
            tot = abs(float(tn[(st >= st[j] - 1e-6) & (st < st[j] + AUDIT_WINDOW_M)].sum()))
            if tot > allowed + 1e-6:
                kinks.append((float(x[idx[j]][0]), float(x[idx[j]][1]), dmath.degrees(tot)))
                until = st[j] + AUDIT_WINDOW_M
        runs, cur = [], [0]                         # (the curves: runs of turns the same way; the S of two the other way)
        for j in range(1, len(idx)):
            if tn[j] * tn[cur[-1]] > 0.0 and st[j] - st[cur[-1]] <= 3.0 * AUDIT_WINDOW_M:
                cur.append(j)
            else:
                runs.append(cur)
                cur = [j]
        runs.append(cur)
        for u, v in zip(runs, runs[1:]):
            if tn[u[0]] * tn[v[0]] < 0.0 and st[v[0]] - st[u[-1]] <= AUDIT_S_LINK_M:
                tight = min(float(rd[u].min()), float(rd[v].min()))
                if tight < rm[i] - 0.5:
                    res.sbends.append((float(x[idx[v[0]]][0]), float(x[idx[v[0]]][1]), tight))
                    break
    res.gaps = _unique_marks(sorted(gaps, key=lambda m: m[2]))
    res.opens = _unique_marks(opens)
    res.kinks = _unique_marks(sorted(kinks, key=lambda m: -m[2]))
    return res


def final_straight(P, tol=0.01):
    """The length (m) of the straight run that ends the polyline P (k, 2): back from its last point to the first vertex that turns
    by more than tol radians (an arc's chord turns by ARC_STEP_RAD / 2 at the most at its end: the arc is not the straight)."""
    P = np.asarray(P, np.float64)
    d = np.diff(P, axis=0)
    ln = dnp.hypot(d[:, 0], d[:, 1])
    total = 0.0
    for j in range(len(d) - 1, -1, -1):
        total += float(ln[j])
        if j and ln[j - 1] > 1e-9 and _angle(d[j - 1], d[j]) > tol:
            break
    return total


class Network:
    """The painted yellow centreline network of the Features and stands, in the scene's plane: lines [(xy (k, 2), role, rmin)] (role
    "mapped", "spine", "connector" or "lead"), stops [(nose (2,), unit direction (2,), kind)] (the stands' stop bars), holds [(2,)]
    (the runway holding positions), edges [(k, 2)] (the aprons' and taxiways' outlines), runways [(centreline, half width)], short
    [(nose, final straight, least straight)] (the lead-ins whose final straight is shorter than lead_straight asks), frame."""
    __slots__ = ("frame", "lines", "stops", "holds", "edges", "aprons", "runways", "short")

    def audit(self):
        return audit([x[0] for x in self.lines], [s[0] for s in self.stops] + list(self.holds), self.edges, self.runways,
                     rmins=[x[2] for x in self.lines], aprons=self.aprons)


def network(feats_list, stands=None, site=None):
    """The Network of the markings of the Features in feats_list and (with `stands`) their lead-ins: what _build and _lead_lines paint
    as the yellow centreline, before it is cut by tiles; None for Features with no airport way in them."""
    feats = [f for f in feats_list if f is not None and len(f)]
    sc = scene(feats)
    if sc is None:
        return None
    nw = Network()
    nw.frame = sc.frame
    nw.lines = [(x[0], "mapped", MIN_RADIUS_M) for x in _mapped_runs(sc)]
    nw.stops, nw.short = [], []
    nw.holds = [np.asarray(x[2], np.float64) for x in sc.sites]
    nw.runways = [(xy, half) for xy, half, _ref in sc.runways]
    nw.edges = sc.memo.get("apron_rings", []) + sc.memo.get("pad_rings", [])
    nw.aprons = sc.memo.get("apron_rings", [])
    st = [c for c in (stands or ()) if c.mode in LEAD_MODES]
    if st:
        _lead_lines(sc, stands, site)
        got = sc.memo.get(("net", ("lead", stand_key(st), None if site is None else site.key)))
        if got is not None:
            net, stops = got
            nw.lines += net
            nw.stops = stops
            for nose, u, kind in stops:
                need = lead_straight(pa.SPECS[kind][0])
                for xy, role, _rm in net:
                    if role == "lead" and float(dnp.hypot(*(xy[-1] - nose))) < 0.05:
                        f = final_straight(xy)
                        if f < need - 0.05:
                            nw.short.append((nose, f, need))
    return nw


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
LAYER_OF = {"under": "edge", "red": "gutter", "paint": "mark", "glyph": "glyph"}
LAYER_ORDER = ("under", "red", "paint", "glyph")     # (the order of the chunks: the road mesh draws a material's triangles in one primitive, in
                                                     # the order the materials first appear: the lettering's ("text") after the yellow's)
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
        for (colour, layer), quads in sorted(groups.items(), key=lambda kv: (LAYER_ORDER.index(kv[0][1]), kv[0][0])):
            look = airportgrade.MARK_LOOK.get(colour, airportgrade.MARK_LOOK["white"])
            pts = np.concatenate(quads)
            out.append({"m": look["m"], "w": 0.0, "tl": look["tl"], "p": look["p"], "layer": LAYER_OF[layer],
                        "poly": [[round(float(x), 3), round(float(y), 3)] for x, y in pts],
                        "uvq": [[0.5, 0.5]] * len(pts), "quads": 1, "n": []})
    return out
