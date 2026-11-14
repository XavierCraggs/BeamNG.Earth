"""Stand marking shapes: the bold stencil segment font and the plane geometry of the painted boxes of an aircraft stand
(taxiwaymarks draws them: the stand number and the type labels on yellow boxes, the red hatched box under a jet bridge, the
service road, the equipment parking). Pure: metres in a plane, no ground; every shape is a convex polygon (k, 2), counter-clockwise
or not (the road mesh turns its triangles up), or a polyline.

Font: digits as seven segments, letters as fourteen (the usual display tables), every segment its own bar with a gap between
them, as a stencil: text_polys(text, centre, up, h, cw, t, g, cg) -> [(4, 2)], a block of characters h tall and cw wide (cg
apart), the bars t wide with g between them, centred on `centre`, upright as read looking along `up` (left to right across it).
"""
import numpy as np

import dnp

_EPS = 1e-9
# The segments of a character cell: a top, b upper right, c lower right, d bottom, e lower left, f upper left, g the middle
# bar (l and r its halves), j / m the top / bottom middle verticals, 1 2 3 4 the diagonals (upper left, upper right, lower left,
# lower right) to the centre.
_CODES = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abcdg", "4": "bcfg", "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg",
    "9": "abcdfg",
    "A": "abcefg", "B": "abcdrjm", "C": "adef", "D": "abcdjm", "E": "adefg", "F": "aefg", "G": "acdefr", "H": "bcefg",
    "I": "adjm", "J": "bcde", "K": "efl24", "L": "def", "M": "bcef12", "N": "bcef14", "O": "abcdef", "P": "abefg",
    "Q": "abcdef4", "R": "abefg4", "S": "acdfg", "T": "ajm", "U": "bcdef", "V": "ef32", "W": "bcef34", "X": "1234",
    "Y": "12m", "Z": "ad23",
}


def supported(text):
    """Can the font draw every character of text (A-Z, 0-9; a non-empty text)?"""
    return bool(text) and all(ch in _CODES for ch in text)


def _unit(v):
    v = np.asarray(v, np.float64)
    return v / max(float(dnp.hypot(v[0], v[1])), _EPS)


def _rect(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)


def _segment(s, w, h, t, g):
    """The polygon (4, 2) of segment s in a w x h cell (x right, y up from its lower left corner), bars t wide, gaps g."""
    x0, x1 = t + g, w - t - g                           # (the horizontals run between the verticals)
    lo, hi = h / 2.0 - t / 2.0, h / 2.0 + t / 2.0       # the middle bar's edges
    c0, c1 = w / 2.0 - t / 2.0, w / 2.0 + t / 2.0
    if s == "a":
        return _rect(x0, h - t, x1, h)
    if s == "d":
        return _rect(x0, 0.0, x1, t)
    if s == "g":
        return _rect(x0, lo, x1, hi)
    if s == "l":
        return _rect(x0, lo, w / 2.0 - g / 2.0, hi)
    if s == "r":
        return _rect(w / 2.0 + g / 2.0, lo, x1, hi)
    if s == "b":
        return _rect(w - t, hi + g, w, h)
    if s == "c":
        return _rect(w - t, 0.0, w, lo - g)
    if s == "e":
        return _rect(0.0, 0.0, t, lo - g)
    if s == "f":
        return _rect(0.0, hi + g, t, h)
    if s == "j":
        return _rect(c0, hi + g, c1, h - t - g)
    if s == "m":
        return _rect(c0, t + g, c1, lo - g)
    corner = {"1": (t, h - t), "2": (w - t, h - t), "3": (t, t), "4": (w - t, t)}[s]
    p, c = np.array(corner), np.array([w / 2.0, h / 2.0])
    d = _unit(c - p)
    gd = g + t * 0.6
    a, b = p + d * gd, c - d * gd
    n = np.array([-d[1], d[0]]) * (t / 2.0)
    return np.array([a + n, b + n, b - n, a - n])


def text_width(n, cw, cg):
    """The width of n characters."""
    return n * cw + (n - 1) * cg


def text_polys(text, centre, up, h, cw, t, g, cg):
    """The bars (4, 2) of `text` (supported()), as the module docstring says; [] for a text the font lacks."""
    if not supported(text):
        return []
    up = _unit(up)
    right = np.array([up[1], -up[0]])
    c = np.asarray(centre, np.float64)
    left0 = -text_width(len(text), cw, cg) / 2.0
    out = []
    for i, ch in enumerate(text):
        x0 = left0 + i * (cw + cg)
        for s in _CODES[ch]:
            p = _segment(s, cw, h, t, g)
            out.append(c + right[None] * (x0 + p[:, 0:1]) + up[None] * (p[:, 1:2] - h / 2.0))
    return out


def box(centre, up, w, h):
    """The rectangle (4, 2) w across and h along `up`, centred on `centre`."""
    up = _unit(up)
    right = np.array([up[1], -up[0]])
    c = np.asarray(centre, np.float64)
    a, b = right * (w / 2.0), up * (h / 2.0)
    return np.array([c - a - b, c + a - b, c + a + b, c - a + b])


def outline(centre, up, w, h, lw):
    """The four bars (4, 2) of a rectangle's outline lw wide, inside the rectangle w x h."""
    up = _unit(up)
    right = np.array([up[1], -up[0]])
    c = np.asarray(centre, np.float64)
    out = []
    for sx, sy, ww, hh in ((0, -1, w, lw), (0, 1, w, lw), (-1, 0, lw, h - 2 * lw), (1, 0, lw, h - 2 * lw)):
        at = c + right * (sx * (w - lw) / 2.0) + up * (sy * (h - lw) / 2.0)
        out.append(box(at, up, ww, hh))
    return out


def clip(poly, normal, offset):
    """The part of the convex polygon (k, 2) where normal . p <= offset (Sutherland-Hodgman); (0, 2) where nothing is left."""
    pts = np.asarray(poly, np.float64)
    out = []
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        dp, dq = float(normal[0] * p[0] + normal[1] * p[1]) - offset, float(normal[0] * q[0] + normal[1] * q[1]) - offset
        if dp <= 0.0:
            out.append(p)
        if (dp < 0.0 < dq) or (dq < 0.0 < dp):
            out.append(p + (q - p) * (dp / (dp - dq)))
    return np.array(out, np.float64).reshape(-1, 2)


def hatch(centre, up, w, h, pitch, lw):
    """The 45 degree hatching of the rectangle w across and h along `up`: strips lw wide, pitch apart (across them), each
    clipped to the rectangle, [(k, 2) convex polygons]."""
    up = _unit(up)
    right = np.array([up[1], -up[0]])
    rect = box(centre, up, w, h)
    c = np.asarray(centre, np.float64)
    d = _unit(right + up)                               # the strips run along d, are spread across n
    n = np.array([-d[1], d[0]])
    reach = (w + h) / 2.0
    out = []
    k = -int(reach / pitch)
    while k * pitch <= reach:
        off = float((c[0] * n[0] + c[1] * n[1])) + k * pitch
        p = clip(clip(rect, n, off + lw / 2.0), -n, -(off - lw / 2.0))
        if len(p) >= 3:
            out.append(p)
        k += 1
    return out


def offset(pts, d):
    """The polyline pts (k, 2) moved d to its left (mitred, the miter at most 2 d long), (k, 2)."""
    P = np.asarray(pts, np.float64)
    seg = P[1:] - P[:-1]
    ln = np.maximum(dnp.hypot(seg[:, 0], seg[:, 1]), _EPS)
    nrm = np.stack([-seg[:, 1], seg[:, 0]], 1) / ln[:, None]
    out = np.empty_like(P)
    out[0] = P[0] + nrm[0] * d
    out[-1] = P[-1] + nrm[-1] * d
    for i in range(1, len(P) - 1):
        m = nrm[i - 1] + nrm[i]
        mm = float(m[0] * m[0] + m[1] * m[1])
        k = 2.0 / max(mm, 1.0) if mm > _EPS else 1.0    # (1 / cos of half the bend: capped at 2)
        out[i] = P[i] + m * (d * k)
    return out


def cumulative(pts):
    """The distance along the polyline pts at each vertex."""
    P = np.asarray(pts, np.float64)
    return np.r_[0.0, np.cumsum(dnp.hypot(*np.diff(P, axis=0).T))]


def at(pts, s):
    """(point, unit direction) of the polyline pts a distance s along it (clamped to its ends)."""
    P = np.asarray(pts, np.float64)
    cum = cumulative(P)
    s = min(max(s, 0.0), float(cum[-1]))
    j = min(int(np.searchsorted(cum, s, side="right")) - 1, len(P) - 2)
    j = max(j, 0)
    d = P[j + 1] - P[j]
    ln = max(float(cum[j + 1] - cum[j]), _EPS)
    return P[j] + d * ((s - float(cum[j])) / ln), d / ln


def dashes(pts, dash, gap, width, start=0.0):
    """The dashes (4, 2) of width `width` along the polyline pts: dash long, gap apart, the first at `start`, the pattern
    centred so that both ends of the line end in a dash (a short line is one dash)."""
    P = np.asarray(pts, np.float64)
    total = float(cumulative(P)[-1])
    n = max(1, int((total + gap) // (dash + gap)))
    s0 = start + (total - (n * dash + (n - 1) * gap)) / 2.0
    out = []
    for i in range(n):
        a, b = s0 + i * (dash + gap), s0 + i * (dash + gap) + dash
        # (a dash across a bend is cut at the polyline's vertices: a quad per straight piece)
        cum = cumulative(P)
        cuts = [a] + [float(c) for c in cum[1:-1] if a + 1e-6 < c < b - 1e-6] + [b]
        for x, y in zip(cuts[:-1], cuts[1:]):
            (p, dp), (q, _dq) = at(P, x), at(P, y)
            nv = np.array([-dp[1], dp[0]]) * (width / 2.0)
            out.append(np.array([p - nv, q - nv, q + nv, p + nv]))
    return out


def crossings(a, b):
    """[(point, t_a along polyline a (metres), unit direction of a there)] where the polyline a (k, 2) crosses polyline b (m, 2)."""
    A, B = np.asarray(a, np.float64), np.asarray(b, np.float64)
    cum = cumulative(A)
    out = []
    for i in range(len(A) - 1):
        p, d = A[i], A[i + 1] - A[i]
        for j in range(len(B) - 1):
            q, e = B[j], B[j + 1] - B[j]
            den = d[0] * e[1] - d[1] * e[0]
            if abs(den) < _EPS:
                continue
            w = q - p
            t = (w[0] * e[1] - w[1] * e[0]) / den
            s = (w[0] * d[1] - w[1] * d[0]) / den
            if 0.0 <= t <= 1.0 and 0.0 <= s <= 1.0:
                ln = max(float(dnp.hypot(d[0], d[1])), _EPS)
                out.append((p + d * t, float(cum[i]) + t * ln, d / ln))
    return out


def triangle_row(centre, along, across_w, count, base, height):
    """A row of give-way triangles (3, 2) across a road: count of them spread over across_w, centred on `centre`, each `base`
    wide (across) and `height` long, the apex `height` along the unit vector `along` from its base."""
    along = _unit(along)
    right = np.array([along[1], -along[0]])
    c = np.asarray(centre, np.float64)
    out = []
    for i in range(count):
        x = (i + 0.5) * across_w / count - across_w / 2.0
        m = c + right * x
        out.append(np.array([m - right * (base / 2.0), m + right * (base / 2.0), m + along * height]))
    return out
