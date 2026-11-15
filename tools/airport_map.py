#!/usr/bin/env python
"""A top-down picture of an airport's buildings by role, to judge server/airportroles.py's rules without the game.

    python tools/airport_map.py <lat> <lon> [--km 2] [--out path.png] [--name X] [--lines]

Loads the map cells round (lat, lon) as the server does (mapdata.MapData: the cache, else the network), classifies the
buildings and parts (airportroles.classify) and draws, ~1600 px: the runways, taxiways and aprons in greys, the buildings
filled by role (legend), the gate points (a ring where the gate has a jet bridge, a cross where it has none), the jet
bridges' outer ends with an arrow out of the terminal, airside parking hatched, the CURRENT parked aircraft as outlines
(parkedaircraft.kept_stands, read only), the empty stands (parkedaircraft.lead_stands: dashed), the apron masts
(airsideprops) and the stands' lead-in lines and stand details (taxiwaymarks). Prints the count per role and, per gate in
the picture: has a bridge, has an aircraft, has a stand, and the stands whose nose no lead-in reaches (ringed in red).

The painted yellow network is audited (taxiwaymarks.audit): gaps (an end within 8 m of a line but not on it), opens (an end in the
open touching nothing), kinks (a turn of over 20 degrees within 3 m, or a join that is neither tangent nor straight through) and
S-bends tighter than the minimum radius are marked and counted (those inside the picture), and the stands whose lead-in has a
final straight shorter than taxiwaymarks.lead_straight are listed. --lines draws only that network: the pads in light grey, the
mapped centrelines, spines, connectors and lead-ins each in a colour, the stops as dots with the start of each stand's final
straight (a cross), and the audit markers (give --out a name ending _lines.png).

--km is the side of the square picture (default 2); data is loaded 300 m beyond it. Needs matplotlib (pip install matplotlib).
"""
import argparse
import math
import os
import site
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "server"))

import numpy as np  # noqa: E402

try:
    import matplotlib
except ImportError:                                 # (the venv has none: the user's site-packages, after everything else)
    sys.path.append(site.getusersitepackages())
    try:
        import matplotlib
    except ImportError:
        sys.exit("matplotlib is needed: pip install matplotlib")
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Polygon  # noqa: E402

import aeroways  # noqa: E402
import airportroles as ar  # noqa: E402
import airsideprops  # noqa: E402
import geodesy  # noqa: E402
import mapcells  # noqa: E402
import mapdata  # noqa: E402
import netfetch  # noqa: E402
import parkedaircraft as pa  # noqa: E402
import taxiwaymarks  # noqa: E402

COLOURS = {ar.TERMINAL: "#1f77b4", ar.PIER: "#17becf", ar.JET_BRIDGE: "#d62728", ar.WALKWAY: "#ff7f0e",
           ar.RAISED_BLOCK: "#9467bd", ar.TOWER: "#e377c2", ar.HANGAR: "#8c564b", ar.CANOPY: "#bcbd22",
           ar.LANDSIDE: "#98df8a", ar.OTHER: "#f2c94c"}
LAYERS = ("buildings", "building_parts", "infrastructure", "land_use")
LOAD_PAD_M = 300.0
M_PER_DEG = aeroways.M_PER_DEG


def load(lat, lon, km):
    """(frame, keys, {layer: [Features]}, {key: {layer: Features}}) of the cells under the km square and 300 m round it."""
    half = km * 500.0 + LOAD_PAD_M
    dlat = half / M_PER_DEG
    dlon = half / (M_PER_DEG * math.cos(math.radians(lat)))
    keys = mapcells.cells_for_bbox(lat - dlat, lon - dlon, lat + dlat, lon + dlon)
    md = mapdata.MapData(fetcher=netfetch.Fetcher(offline=False))
    out, per = {k: [] for k in LAYERS}, {}
    for key in keys:
        layers = md.cell(key, layers=LAYERS).layers
        per[str(key)] = layers
        for name in LAYERS:
            f = layers.get(name)
            if f is not None and len(f):
                out[name].append(f)
    return geodesy.EnuFrame(lat, lon, 0.0), keys, out, per, md


def ring_xy(frame, ring):
    e, n, _ = frame.geodetic_to_enu(np.asarray(ring[:, 0], np.float64), np.asarray(ring[:, 1], np.float64), 0.0)
    return np.stack([np.asarray(e), np.asarray(n)], 1)


def pad_xy(frame, rings):
    """[(k, 2) m] of aeroways' (lat, lon) rings."""
    out = []
    for la, lo in rings:
        if len(la) >= 3:
            e, n, _ = frame.geodetic_to_enu(np.asarray(la, np.float64), np.asarray(lo, np.float64), 0.0)
            out.append(np.stack([np.asarray(e), np.asarray(n)], 1))
    return out


def aircraft_outline(c, frame):
    """([(4, 2) rectangles], (x, y), (nx, ny)) of a parkedaircraft Craft in the frame's metres."""
    e, n, _ = frame.geodetic_to_enu(np.array([c.lat]), np.array([c.lon]), 0.0)
    x, y = float(e[0]), float(n[0])
    nx, ny = float(c.ne), float(c.nn)
    r = math.hypot(nx, ny) or 1.0
    nx, ny = nx / r, ny / r
    rects = []
    for u0, u1, v0, v1 in pa._rects(c.kind):
        loc = np.array([[u0, v0], [u1, v0], [u1, v1], [u0, v1]])
        rects.append(pa._world(loc, x, y, nx, ny))
    return rects, (x, y), (nx, ny)


def to_view(nw, frame, xy):
    """The points xy (k, 2) of the network's plane in the picture's frame."""
    xy = np.asarray(xy, np.float64).reshape(-1, 2)
    la, lo, _ = nw.frame.enu_to_geodetic(xy[:, 0], xy[:, 1], np.zeros(len(xy)))
    e, n, _ = frame.geodetic_to_enu(np.asarray(la), np.asarray(lo), 0.0)
    return np.stack([np.asarray(e), np.asarray(n)], 1)


ROLE_COLOURS = {"mapped": "#1f5fbf", "spine": "#1a9a3a", "connector": "#f08a00", "lead": "#d62728"}
MARKERS = (("gaps", "v", "#d000d0"), ("opens", "^", "#d000d0"), ("kinks", "s", "#ff7f00"), ("sbends", "D", "#00a0c0"))


def audit_view(nw, frame, box):
    """({"gaps": [(x, y, ...)], "opens", "kinks", "sbends"} of nw.audit() in the picture's metres: only those inside box, {the same
    for the whole loaded area: counts only})."""
    got = nw.audit()
    shown, whole = {}, {}
    for key, marks in (("gaps", got.gaps), ("opens", got.opens), ("kinks", got.kinks), ("sbends", got.sbends)):
        pts = to_view(nw, frame, np.array([[m[0], m[1]] for m in marks])) if marks else np.zeros((0, 2))
        rows = [(float(p[0]), float(p[1])) + tuple(m[2:]) for p, m in zip(pts, marks)]
        whole[key] = len(rows)
        shown[key] = [m for m in rows if box[0] <= m[0] <= box[2] and box[1] <= m[1] <= box[3]]
    return shown, whole


def draw_audit(ax, shown, z=13):
    for key, marker, colour in MARKERS:
        if shown[key]:
            ax.scatter([m[0] for m in shown[key]], [m[1] for m in shown[key]], s=110, marker=marker, facecolor="none",
                       edgecolor=colour, linewidths=1.8, zorder=z)


def audit_handles(shown):
    return [Line2D([], [], marker="v", mfc="none", mec="#d000d0", ls="", label=f"gap, under 8 m from a line ({len(shown['gaps'])})"),
            Line2D([], [], marker="^", mfc="none", mec="#d000d0", ls="", label=f"open end ({len(shown['opens'])})"),
            Line2D([], [], marker="s", mfc="none", mec="#ff7f00", ls="", label=f"kink ({len(shown['kinks'])})"),
            Line2D([], [], marker="D", mfc="none", mec="#00a0c0", ls="", label=f"S-bend under the radius ({len(shown['sbends'])})")]


def lines_picture(a, out, frame, infra, nw, shown, box, name):
    """The --lines picture: the pads, the network's lines by role (~2 px), the stops, the starts of the final straights, the audit."""
    fig = plt.figure(figsize=(16, 16), dpi=100)
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.94])
    ax.set_facecolor("#ffffff")
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_aspect("equal")
    ax.tick_params(labelsize=8)
    ax.grid(True, color="#eeeeee", lw=0.5)
    for rings, colour in ((pad_xy(frame, aeroways.pads(infra, runways=True)), "#d0d0d0"),
                          (pad_xy(frame, aeroways.ways(infra)), "#dcdcdc"), (pad_xy(frame, aeroways.aprons(infra)), "#ebebeb")):
        ax.add_collection(PatchCollection([Polygon(r, closed=True) for r in rings], facecolor=colour, edgecolor="none", zorder=1))
    for xy, role, _rm in nw.lines:
        v = to_view(nw, frame, xy)
        ax.plot(v[:, 0], v[:, 1], color=ROLE_COLOURS[role], lw=1.45, zorder=3 + (role == "lead"), solid_capstyle="butt")
    shorts = to_view(nw, frame, np.array([s[0] for s in nw.short])) if nw.short else np.zeros((0, 2))
    if nw.stops:
        stops = to_view(nw, frame, np.array([s[0] for s in nw.stops]))
        starts = to_view(nw, frame, np.array([s[0] - s[1] * taxiwaymarks.lead_straight(pa.SPECS[s[2]][0]) for s in nw.stops]))
        ax.scatter(stops[:, 0], stops[:, 1], s=26, c="#000000", zorder=9)
        ax.scatter(starts[:, 0], starts[:, 1], s=40, marker="x", c="#008b8b", linewidths=1.2, zorder=9)
    if len(shorts):
        ax.scatter(shorts[:, 0], shorts[:, 1], s=150, marker="o", facecolor="none", edgecolor="#e60000", linewidths=1.6, zorder=12)
    draw_audit(ax, shown)
    handles = [Line2D([], [], color=c, lw=2, label=r) for r, c in ROLE_COLOURS.items()]
    handles += [Line2D([], [], marker="o", color="k", ls="", label=f"stop bar ({len(nw.stops)})"),
                Line2D([], [], marker="x", color="#008b8b", ls="", label="start of the final straight"),
                Line2D([], [], marker="o", mfc="none", mec="#e60000", ls="", label=f"final straight too short ({len(shorts)})")]
    ax.legend(handles=handles + audit_handles(shown), loc="upper left", fontsize=9, framealpha=0.9)
    fig.suptitle(f"{name}  ({a.lat:.4f}, {a.lon:.4f})  {a.km:g} km square: the painted network and its audit", fontsize=13, y=0.985)
    fig.savefig(out, dpi=100)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("lat", type=float)
    ap.add_argument("lon", type=float)
    ap.add_argument("--km", type=float, default=2.0, help="side of the picture (default 2)")
    ap.add_argument("--out", default=None, help="PNG path (default airport_map_<lat>_<lon>.png)")
    ap.add_argument("--name", default="", help="a name for the title")
    ap.add_argument("--lines", action="store_true", help="draw only the painted yellow network and its audit")
    a = ap.parse_args()
    out = a.out or f"airport_map_{a.lat:.4f}_{a.lon:.4f}.png"
    frame, keys, layers, per, md = load(a.lat, a.lon, a.km)
    infra = layers["infrastructure"]
    half = a.km * 500.0
    box = (-half, -half, half, half)
    res = None if a.lines else ar.classify(layers["buildings"], layers["building_parts"], infra, frame, 0.0, 0.0, landuse=layers["land_use"])
    print(f"{a.name or 'airport'} at {a.lat}, {a.lon}: {len(keys)} cells" + ("" if res is None else
          f", {len(res)} airport footprints, {len(res.gates)} gates"))

    # the parked aircraft, masts and lead-ins as the game places them now (read only)
    infra_fn = lambda k: per[str(k)].get("infrastructure") if str(k) in per else \
        md.cell(k, layers=("infrastructure",)).layers.get("infrastructure")
    stands, every = [], []
    try:
        stands = pa.kept_stands(keys, infra_fn, pa.building_layers_fn(md))
        every = pa.lead_stands(keys, infra_fn, pa.building_layers_fn(md))
    except Exception as ex:                          # noqa: BLE001 (the picture without them)
        print("aircraft:", type(ex).__name__, ex)
    masts, leads, unreached, base, nw = [], [], [], set(), None
    try:
        for k in () if a.lines else keys:
            f = infra_fn(k)
            if f is not None and pa.has_stands(f):
                blds = pa._flat([pa.building_layers_fn(md)(k)])
                for p in airsideprops.props(f, blds):
                    if p.group == airsideprops.MAST_GROUP:
                        e, n, _ = frame.geodetic_to_enu(np.array([p.lat]), np.array([p.lon]), 0.0)
                        masts.append((float(e[0]), float(n[0])))
        feats = [f for f in infra if pa.has_stands(f)]
        if every and feats:
            base = set(taxiwaymarks.strokes(feats))
            site = taxiwaymarks.site_of(infra, layers["buildings"], layers["building_parts"])
            leads = [s for s in taxiwaymarks.strokes(feats, every, site) if s not in base]
            nw = taxiwaymarks.network(feats, every, site)
    except Exception as ex:                          # noqa: BLE001
        print("masts / lead-ins:", type(ex).__name__, ex)

    shown, whole = audit_view(nw, frame, box) if nw is not None else ({k: [] for k, _m, _c in MARKERS}, {k: 0 for k, _m, _c in MARKERS})
    print(f"audit (inside the picture; the whole loaded area): gaps {len(shown['gaps'])} ({whole['gaps']}), opens {len(shown['opens'])} "
          f"({whole['opens']}), kinks {len(shown['kinks'])} ({whole['kinks']}), S-bends {len(shown['sbends'])} ({whole['sbends']}); "
          f"final straight too short: {0 if nw is None else len(nw.short)}")
    for key, _m, _c in MARKERS:
        if shown[key]:
            print(f"  {key}: " + ", ".join("(" + ", ".join(f"{v:.0f}" if i < 2 else f"{v:.1f}" for i, v in enumerate(m)) + ")" for m in shown[key][:40]))
    if a.lines:
        if nw is None:
            sys.exit("no airport network here")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        lines_picture(a, out, frame, infra, nw, shown, box, a.name or "airport")
        print("saved", out)
        return

    fig = plt.figure(figsize=(16, 16), dpi=100)
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.94])
    ax.set_facecolor("#e9efe3")
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_aspect("equal")
    ax.tick_params(labelsize=8)
    ax.grid(True, color="#ffffff", alpha=0.5, lw=0.5)

    def fill(rings, colour, z, **kw):
        ax.add_collection(PatchCollection([Polygon(r, closed=True) for r in rings], facecolor=colour, zorder=z, **kw))

    fill(pad_xy(frame, aeroways.pads(infra, runways=True)), "#6b6b6b", 1, edgecolor="none")     # runways (and all pads)
    fill(pad_xy(frame, aeroways.ways(infra)), "#9a9a9a", 2, edgecolor="none")
    fill(pad_xy(frame, aeroways.aprons(infra)), "#c3c3c3", 3, edgecolor="#8a8a8a", linewidth=0.6)

    units = sorted(res.units.values(), key=lambda u: (u.part, -u.area, u.id))     # (parents under their parts)
    for u in units:
        ax.add_patch(Polygon(u.ring, closed=True, facecolor=COLOURS[u.role], edgecolor="#222222" if u.part else "#555555",
                             linewidth=0.5 if u.part else 0.9, alpha=0.55 if (u.has_parts and not u.part) else 0.92,
                             zorder=4 if not u.part else 5))
    for p in res.airside_parking:
        ax.add_patch(Polygon(p["ring"], closed=True, facecolor="none", edgecolor="#7b2d9c", hatch="////", linewidth=0.8,
                             zorder=6))

    ends = []                                        # (the lead-ins' ends in metres: a stand's nose is reached by one)
    for s in leads:
        (la0, lo0, la1, lo1, _w, kind, _col) = s
        e, n, _ = frame.geodetic_to_enu(np.array([la0, la1]), np.array([lo0, lo1]), 0.0)
        if kind == taxiwaymarks.UNDER_KIND:                     # (the black borders: not drawn)
            continue
        ax.plot(e, n, color="#ffffff" if kind == taxiwaymarks.CENTRE_KIND else "#2b6cb0" if kind == taxiwaymarks.ROAD_KIND
                else "#ffe066", lw=0.9, zorder=7)
        if kind == taxiwaymarks.CENTRE_KIND:
            ends += [(float(e[0]), float(n[0])), (float(e[1]), float(n[1]))]
    kept = {(c.kind, round(c.lat, 7), round(c.lon, 7)) for c in stands}
    for c in every:
        rects, (cx, cy), (nx, ny) = aircraft_outline(c, frame)
        has = (c.kind, round(c.lat, 7), round(c.lon, 7)) in kept
        for r in rects:
            ax.add_patch(Polygon(r, closed=True, facecolor="none", edgecolor="#111111" if has else "#555555",
                                 linestyle="-" if has else (0, (3, 2)), linewidth=0.9, zorder=8))
        if c.mode in taxiwaymarks.LEAD_MODES:
            half = pa.SPECS[c.kind][0] / 2.0
            nose = (cx + nx * half, cy + ny * half)
            if not any(math.hypot(nose[0] - x, nose[1] - y) < 0.6 for x, y in ends):
                ax.scatter([nose[0]], [nose[1]], s=60, marker="o", facecolor="none", edgecolor="#e60000", linewidths=1.4,
                           zorder=12)
                unreached.append((c.kind, round(nose[0]), round(nose[1])))
    draw_audit(ax, shown)
    if masts:
        ax.scatter([m[0] for m in masts], [m[1] for m in masts], marker="*", s=40, c="#ff00ff", edgecolor="k",
                   linewidths=0.3, zorder=9)

    # the gates and their jet bridges
    ac = [(c, aircraft_outline(c, frame)) for c in stands]
    st_all = [(c, aircraft_outline(c, frame)) for c in every if c.mode in taxiwaymarks.LEAD_MODES]
    rows = []
    for gid, g in sorted(res.gates.items()):
        x, y = g["xy"]
        if not (box[0] <= x <= box[2] and box[1] <= y <= box[3]):
            continue
        px, py, reach = (x, y, 15.0) if g["bridge"] is None else (*g["end"], 8.0)     # (a bridged gate: the aircraft beside its end)

        def covers(lst):
            for c, (_r, (cx, cy), (nx, ny)) in lst:
                if math.hypot(px - cx, py - cy) <= pa._radius(c.kind) + reach and bool(
                        pa._in_rects(c.kind, cx, cy, nx, ny, np.array([[px, py]]), reach)[0]):
                    return True
            return False
        has_ac, has_st = covers(ac), covers(st_all)
        rows.append((gid, g["bridge"] is not None, has_ac, has_st))
        if g["bridge"] is not None:
            ax.scatter([x], [y], s=34, facecolor="none", edgecolor="#006400", linewidths=1.5, zorder=10)
            ex, ey = g["end"]
            dx, dy = g["dir"]
            ax.annotate("", xy=(ex, ey), xytext=(ex - dx * 14.0, ey - dy * 14.0), zorder=11,
                        arrowprops=dict(arrowstyle="-|>", color="#8b0000", lw=1.6, mutation_scale=12))
        else:
            ax.scatter([x], [y], s=26, marker="x", c="#000000", linewidths=1.2, zorder=10)

    n_by = res.counts()
    handles = [Patch(facecolor=COLOURS[r], edgecolor="#333333", label=f"{r} ({n_by[r]})") for r in ar.ROLES]
    handles += [Patch(facecolor="#6b6b6b", label="runway / pads"), Patch(facecolor="#9a9a9a", label="taxiway"),
                Patch(facecolor="#c3c3c3", edgecolor="#8a8a8a", label="apron"),
                Patch(facecolor="none", edgecolor="#7b2d9c", hatch="////", label=f"airside parking ({len(res.airside_parking)})"),
                Line2D([], [], marker="o", mfc="none", mec="#006400", ls="", label="gate with jet bridge"),
                Line2D([], [], marker="x", mec="k", ls="", label="gate, no bridge"),
                Line2D([], [], marker=">", color="#8b0000", ls="", label="bridge outer end, arrow out"),
                Patch(facecolor="none", edgecolor="#111111", label=f"parked aircraft now ({len(stands)})"),
                Patch(facecolor="none", edgecolor="#555555", linestyle="--", label=f"empty stand ({len(every) - len(stands)})"),
                Line2D([], [], marker="o", mfc="none", mec="#e60000", ls="", label=f"no lead-in at the nose ({len(unreached)})"),
                Line2D([], [], marker="*", mfc="#ff00ff", mec="k", ls="", label=f"apron mast ({len(masts)})"),
                Line2D([], [], color="#ffffff", lw=1.2, label=f"stand lead-in ({len(leads)})"),
                *audit_handles(shown)]
    ax.legend(handles=handles, loc="upper left", fontsize=9, framealpha=0.9)
    nb = sum(1 for r in rows if r[1])
    na = sum(1 for r in rows if r[2])
    ns = sum(1 for r in rows if r[3])
    fig.suptitle(f"{a.name or 'airport'}  ({a.lat:.4f}, {a.lon:.4f})  {a.km:g} km square, north up   gates {len(rows)}: "
                 f"{nb} with a bridge, {na} with an aircraft, {ns} with a stand", fontsize=13, y=0.985)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    fig.savefig(out, dpi=100)
    print("roles:", ", ".join(f"{r} {n_by[r]}" for r in ar.ROLES))
    print(f"airside parking: {len(res.airside_parking)}; aircraft now: {len(stands)}; stands: {len(every)}; masts: {len(masts)}; "
          f"lead-in strokes: {len(leads)}; stands whose nose no lead-in reaches: {len(unreached)} {unreached}")
    print(f"gates in the picture: {len(rows)}, with a jet bridge {nb}, with an aircraft {na}, "
          f"with a stand {ns}, with both {sum(1 for r in rows if r[1] and r[2])}, "
          f"with neither {sum(1 for r in rows if not r[1] and not r[2])}")
    for gid, hb, hc, hs in rows:
        print(f"  gate {gid[:8]}: bridge {'yes' if hb else 'no '} aircraft {'yes' if hc else 'no '} stand {'yes' if hs else 'no'}"
              + (f"  [{res.gates[gid]['bridge'][:8]}, {res.gates[gid]['dist']:.0f} m]" if hb else ""))
    print("saved", out)


if __name__ == "__main__":
    main()
