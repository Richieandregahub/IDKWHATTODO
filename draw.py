"""Pure-geometry drawing library for Richie Jarvis.

Everything here is stdlib-only and OS-independent: shapes are generated in a
normalized unit square (0..1, y grows downward like a screen) and are only
converted to real screen pixels by :func:`fit_strokes`.  That split is what
makes the whole thing testable on any machine - the mouse driver just replays
the points it is given.

A *stroke* is a list of ``(x, y)`` points; pen-down at the first point, the
whole stroke is drawn in one go.  A *drawing* is a list of strokes; the pen
lifts between strokes.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Sequence, Tuple

__all__ = [
    "Stroke", "Drawing",
    "circle", "ellipse", "rect", "square", "line", "polygon", "star",
    "heart", "spiral", "sine", "arc", "cross", "smiley", "wave",
    "house", "robot", "cat", "tree", "sun", "flower", "boat", "mountain",
    "car", "rocket", "fish", "mushroom", "cup", "diamond", "arrow",
    "SHAPES", "PICTURES", "shape", "picture",
    "drawing_bounds", "fit_strokes", "resample", "strokes_to_svg",
    "point_count",
]

Stroke = List[Tuple[float, float]]
Drawing = List[Stroke]

TAU = math.tau


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _steps_for(radius: float, quality: str = "normal") -> int:
    """How many points a curve of this size needs to look smooth."""
    base = {"draft": 18, "normal": 40, "fine": 90}.get(quality, 40)
    return max(base, int(radius * 260))


def _pt(cx: float, cy: float, r: float, ang: float, squash: float = 1.0) -> Tuple[float, float]:
    return (cx + math.cos(ang) * r, cy + math.sin(ang) * r * squash)


# --------------------------------------------------------------------------
# primitives  (all centred on 0.5, 0.5 inside the unit square)
# --------------------------------------------------------------------------

def circle(steps: int = 0, sweep: float = 360.0, rot: float = 0.0, **_) -> Drawing:
    """Full circle (or an arc when ``sweep`` < 360)."""
    r = 0.5
    steps = steps or _steps_for(r)
    a0 = math.radians(rot)
    a1 = a0 + math.radians(sweep)
    closed = abs(sweep - 360.0) < 0.001
    n = steps if closed else steps + 1
    pts = [_pt(0.5, 0.5, r, a0 + (a1 - a0) * i / (n - (0 if closed else 1)))
           for i in range(n)]
    if closed:
        pts.append(pts[0])
    return [pts]


def ellipse(steps: int = 0, rx: float = 0.5, ry: float = 0.35, rot: float = 0.0, **_) -> Drawing:
    rx = min(abs(rx), 0.5)
    ry = min(abs(ry), 0.5)
    steps = steps or _steps_for(max(rx, ry))
    a0 = math.radians(rot)
    pts = []
    for i in range(steps + 1):
        a = a0 + TAU * i / steps
        x = 0.5 + math.cos(a) * rx
        y = 0.5 + math.sin(a) * ry
        # rotate the whole ellipse
        xr = 0.5 + (x - 0.5) * math.cos(a0) - (y - 0.5) * math.sin(a0)
        yr = 0.5 + (x - 0.5) * math.sin(a0) + (y - 0.5) * math.cos(a0)
        pts.append((xr, yr))
    return [pts]


def rect(steps: int = 0, inset: float = 0.0, **_) -> Drawing:
    x0 = y0 = inset
    x1 = y1 = 1.0 - inset
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]


def square(**kw) -> Drawing:
    return rect(**kw)


def line(steps: int = 0, angle: float = 0.0, **_) -> Drawing:
    a = math.radians(angle)
    dx, dy = math.cos(a) * 0.5, math.sin(a) * 0.5
    return [[(0.5 - dx, 0.5 - dy), (0.5 + dx, 0.5 + dy)]]


def polygon(steps: int = 0, sides: int = 5, rot: float = -90.0, **_) -> Drawing:
    sides = max(3, int(sides))
    pts = [_pt(0.5, 0.5, 0.5, math.radians(rot) + TAU * i / sides) for i in range(sides)]
    pts.append(pts[0])
    return [pts]


def star(steps: int = 0, points: int = 5, inner: float = 0.42, rot: float = -90.0, **_) -> Drawing:
    points = max(3, int(points))
    inner = min(max(float(inner), 0.05), 0.95)
    pts = []
    for i in range(points * 2):
        r = 0.5 if i % 2 == 0 else 0.5 * inner
        pts.append(_pt(0.5, 0.5, r, math.radians(rot) + math.pi * i / points))
    pts.append(pts[0])
    return [pts]


def heart(steps: int = 0, **_) -> Drawing:
    steps = steps or 120
    pts = []
    for i in range(steps + 1):
        t = TAU * i / steps
        # classic heart parametric curve, flipped for screen coords
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((0.5 + x / 34.0, 0.5 + y / 32.0))
    return [pts]


def spiral(steps: int = 0, turns: float = 3.0, rot: float = 0.0, **_) -> Drawing:
    steps = steps or int(turns * 60)
    pts = []
    for i in range(steps + 1):
        f = i / steps
        r = 0.5 * f
        pts.append(_pt(0.5, 0.5, r, math.radians(rot) + TAU * turns * f))
    return [pts]


def sine(steps: int = 0, cycles: float = 2.0, amp: float = 0.3, **_) -> Drawing:
    steps = steps or int(120 * max(cycles, 1))
    pts = []
    for i in range(steps + 1):
        f = i / steps
        pts.append((f, 0.5 + math.sin(TAU * cycles * f) * amp))
    return [pts]


def wave(**kw) -> Drawing:
    return sine(**kw)


def arc(steps: int = 0, sweep: float = 180.0, rot: float = 180.0, **_) -> Drawing:
    return circle(steps=steps, sweep=sweep, rot=rot)


def cross(steps: int = 0, **_) -> Drawing:
    return [[(0.15, 0.15), (0.85, 0.85)], [(0.85, 0.15), (0.15, 0.85)]]


def diamond(steps: int = 0, **_) -> Drawing:
    return [[(0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5), (0.5, 0.0)]]


def arrow(steps: int = 0, **_) -> Drawing:
    return [
        [(0.1, 0.5), (0.85, 0.5)],
        [(0.6, 0.28), (0.85, 0.5), (0.6, 0.72)],
    ]


# --------------------------------------------------------------------------
# composed pictures
# --------------------------------------------------------------------------

def _shift(strokes: Drawing, dx: float, dy: float, scale: float = 1.0,
           about: Tuple[float, float] = (0.5, 0.5)) -> Drawing:
    out = []
    for s in strokes:
        pts = []
        for (x, y) in s:
            x = about[0] + (x - about[0]) * scale + dx
            y = about[1] + (y - about[1]) * scale + dy
            pts.append((x, y))
        out.append(pts)
    return out


def smiley(steps: int = 0, **_) -> Drawing:
    return (
        circle(steps=steps)
        + [circle(steps=18, sweep=359.99)[0]]  # keep the face as one stroke
        + _shift(circle(steps=14), -0.16, -0.14, 0.14)
        + _shift(circle(steps=14), 0.16, -0.14, 0.14)
        + [arc(sweep=140.0, rot=20.0, steps=26)[0]]
    )


def house(steps: int = 0, **_) -> Drawing:
    body = rect(inset=0.28)
    roof = [[(0.22, 0.30), (0.5, 0.08), (0.78, 0.30)]]
    door = [[(0.44, 0.72), (0.44, 0.48), (0.56, 0.48), (0.56, 0.72)]]
    window = _shift(rect(inset=0.0), 0.22, 0.10, 0.14)
    handle = [[(0.52, 0.60), (0.52, 0.60)]]
    return body + roof + door + window + handle


def robot(steps: int = 0, **_) -> Drawing:
    head = _shift(rect(inset=0.0), 0.0, -0.18, 0.42, about=(0.5, 0.5))
    eyes = _shift(circle(steps=12), -0.09, -0.22, 0.09) + _shift(circle(steps=12), 0.09, -0.22, 0.09)
    mouth = [[(0.40, -0.04), (0.60, -0.04)]]
    antenna = [[(0.5, 0.10), (0.5, 0.02)], _shift(circle(steps=12), 0.0, -0.30, 0.06)[0]]
    body = [[(0.30, 0.16), (0.70, 0.16), (0.70, 0.62), (0.30, 0.62), (0.30, 0.16)]]
    arms = [[(0.30, 0.26), (0.14, 0.40)], [(0.70, 0.26), (0.86, 0.40)]]
    legs = [[(0.40, 0.62), (0.40, 0.84)], [(0.60, 0.62), (0.60, 0.84)]]
    return head + eyes + mouth + antenna + body + arms + legs


def cat(steps: int = 0, **_) -> Drawing:
    head = circle(steps=steps)
    ears = [[(0.26, 0.30), (0.22, 0.06), (0.44, 0.18)],
            [(0.74, 0.30), (0.78, 0.06), (0.56, 0.18)]]
    eyes = _shift(circle(steps=12), -0.15, -0.05, 0.09) + _shift(circle(steps=12), 0.15, -0.05, 0.09)
    nose = [[(0.46, 0.56), (0.54, 0.56), (0.50, 0.62), (0.46, 0.56)]]
    whisk = [[(0.10, 0.54), (0.32, 0.58)], [(0.10, 0.66), (0.32, 0.62)],
             [(0.90, 0.54), (0.68, 0.58)], [(0.90, 0.66), (0.68, 0.62)]]
    return head + ears + eyes + nose + whisk


def tree(steps: int = 0, **_) -> Drawing:
    trunk = [[(0.44, 0.95), (0.44, 0.56), (0.56, 0.56), (0.56, 0.95)]]
    trunk += [[(0.50, 0.70), (0.34, 0.56)], [(0.50, 0.74), (0.66, 0.60)]]
    crown = _shift(circle(steps=steps), 0.0, -0.18, 0.62)
    crown += _shift(circle(steps=steps), -0.20, 0.02, 0.40)
    crown += _shift(circle(steps=steps), 0.20, 0.02, 0.40)
    return trunk + crown


def sun(steps: int = 0, rays: int = 12, **_) -> Drawing:
    out = _shift(circle(steps=steps), 0.0, 0.0, 0.44)
    rays = max(4, int(rays))
    for i in range(rays):
        a = TAU * i / rays
        x0 = 0.5 + math.cos(a) * 0.28
        y0 = 0.5 + math.sin(a) * 0.28
        x1 = 0.5 + math.cos(a) * 0.48
        y1 = 0.5 + math.sin(a) * 0.48
        out.append([(x0, y0), (x1, y1)])
    return out


def flower(steps: int = 0, petals: int = 6, **_) -> Drawing:
    out = []
    petals = max(3, int(petals))
    for i in range(petals):
        a = TAU * i / petals
        cx = 0.5 + math.cos(a) * 0.28
        cy = 0.5 + math.sin(a) * 0.28
        out += _shift(circle(steps=steps or 24), cx - 0.5, cy - 0.5, 0.42)
    out += _shift(circle(steps=18), 0.0, 0.0, 0.30)
    stem = [[(0.5, 0.66), (0.5, 0.98)]]
    leaf = [[(0.5, 0.82), (0.70, 0.74), (0.5, 0.88)]]
    return out + stem + leaf


def boat(steps: int = 0, **_) -> Drawing:
    hull = [[(0.12, 0.62), (0.88, 0.62), (0.74, 0.86), (0.26, 0.86), (0.12, 0.62)]]
    mast = [[(0.5, 0.62), (0.5, 0.14)]]
    sail = [[(0.52, 0.18), (0.84, 0.56), (0.52, 0.56), (0.52, 0.18)]]
    sail2 = [[(0.48, 0.22), (0.20, 0.56), (0.48, 0.56), (0.48, 0.22)]]
    water = sine(cycles=2.5, amp=0.04, steps=90)
    return hull + mast + sail + sail2 + [_shift(water, 0.0, 0.36)[0]]


def mountain(steps: int = 0, **_) -> Drawing:
    peaks = [[(0.02, 0.80), (0.34, 0.24), (0.62, 0.80)]]
    peaks += [[(0.46, 0.80), (0.72, 0.34), (0.98, 0.80)]]
    snow = [[(0.28, 0.34), (0.34, 0.24), (0.40, 0.34)]]
    ground = [[(0.0, 0.80), (1.0, 0.80)]]
    sun = _shift(circle(steps=steps or 30), 0.32, -0.28, 0.26)
    return peaks + snow + ground + sun


def car(steps: int = 0, **_) -> Drawing:
    body = [[(0.08, 0.62), (0.20, 0.40), (0.72, 0.40), (0.86, 0.62)]]
    body += [[(0.08, 0.62), (0.86, 0.62)]]
    cabin = [[(0.30, 0.40), (0.38, 0.24), (0.62, 0.24), (0.70, 0.40)]]
    wheels = _shift(circle(steps=steps or 26), -0.22, 0.20, 0.26) \
        + _shift(circle(steps=steps or 26), 0.24, 0.20, 0.26)
    return body + cabin + wheels


def rocket(steps: int = 0, **_) -> Drawing:
    body = [[(0.5, 0.04), (0.62, 0.30), (0.62, 0.66), (0.38, 0.66), (0.38, 0.30), (0.5, 0.04)]]
    fins = [[(0.38, 0.50), (0.22, 0.72), (0.38, 0.66)],
            [(0.62, 0.50), (0.78, 0.72), (0.62, 0.66)]]
    window = _shift(circle(steps=18), 0.0, 0.04, 0.16)
    flame = [[(0.44, 0.68), (0.5, 0.92), (0.56, 0.68)]]
    return body + fins + window + flame


def fish(steps: int = 0, **_) -> Drawing:
    body = [[(0.16, 0.5), (0.42, 0.28), (0.66, 0.28), (0.66, 0.72), (0.42, 0.72), (0.16, 0.5)]]
    tail = [[(0.66, 0.5), (0.92, 0.28), (0.86, 0.5), (0.92, 0.72), (0.66, 0.5)]]
    eye = _shift(circle(steps=12), -0.20, -0.06, 0.10)
    return body + tail + eye


def mushroom(steps: int = 0, **_) -> Drawing:
    cap = [arc(sweep=180.0, rot=180.0, steps=steps or 40)[0]]
    cap = _shift(cap, 0.0, 0.02, 0.9)
    stem = [[(0.38, 0.52), (0.38, 0.86), (0.62, 0.86), (0.62, 0.52)]]
    dots = _shift(circle(steps=12), -0.14, -0.08, 0.16) \
        + _shift(circle(steps=12), 0.14, -0.04, 0.12)
    return cap + stem + dots


def cup(steps: int = 0, **_) -> Drawing:
    body = [[(0.24, 0.28), (0.24, 0.78), (0.44, 0.92), (0.66, 0.78), (0.66, 0.28)]]
    rim = _shift(ellipse(steps=steps or 34, rx=0.21, ry=0.07), 0.0, -0.22)
    handle = [arc(sweep=200.0, rot=-40.0, steps=26)[0]]
    handle = _shift(handle, 0.24, 0.06, 0.30)
    steam = sine(cycles=1.5, amp=0.06, steps=50)
    return body + rim + handle + [_shift(steam, 0.04, -0.10)[0]]


# --------------------------------------------------------------------------
# registries
# --------------------------------------------------------------------------

SHAPES: Dict[str, Callable[..., Drawing]] = {
    "circle": circle, "ellipse": ellipse, "rect": rect, "square": square,
    "line": line, "polygon": polygon, "star": star, "heart": heart,
    "spiral": spiral, "sine": sine, "wave": wave, "arc": arc, "cross": cross,
    "diamond": diamond, "arrow": arrow,
}

PICTURES: Dict[str, Callable[..., Drawing]] = {
    "house": house, "robot": robot, "cat": cat, "tree": tree, "sun": sun,
    "flower": flower, "boat": boat, "mountain": mountain, "car": car,
    "rocket": rocket, "fish": fish, "mushroom": mushroom, "cup": cup,
    "smiley": smiley,
}


def shape(name: str, **params) -> Drawing:
    """Build one of :data:`SHAPES` by name. Raises ``ValueError`` if unknown."""
    key = str(name or "").strip().lower()
    if key not in SHAPES:
        raise ValueError("unknown shape '%s' (try: %s)"
                         % (name, ", ".join(sorted(SHAPES))))
    return SHAPES[key](**params)


def picture(name: str, **params) -> Drawing:
    """Build one of :data:`PICTURES` by name. Raises ``ValueError`` if unknown."""
    key = str(name or "").strip().lower()
    if key not in PICTURES:
        raise ValueError("unknown picture '%s' (try: %s)"
                         % (name, ", ".join(sorted(PICTURES))))
    return PICTURES[key](**params)


# --------------------------------------------------------------------------
# geometry utilities
# --------------------------------------------------------------------------

def drawing_bounds(strokes: Drawing) -> Tuple[float, float, float, float]:
    """Return ``(min_x, min_y, max_x, max_y)`` over every point."""
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def fit_strokes(strokes: Drawing, box: Sequence[float],
                keep_aspect: bool = True) -> Drawing:
    """Scale/translate a unit-space drawing into a pixel box ``(x, y, w, h)``."""
    bx, by, bw, bh = box
    if bw <= 0 or bh <= 0:
        raise ValueError("box width/height must be positive")
    x0, y0, x1, y1 = drawing_bounds(strokes)
    sw, sh = (x1 - x0), (y1 - y0)
    sw = sw or 1e-9
    sh = sh or 1e-9
    sx, sy = bw / sw, bh / sh
    if keep_aspect:
        s = min(sx, sy)
        sx = sy = s
        # centre the drawing inside the box
        offx = bx + (bw - sw * s) / 2.0
        offy = by + (bh - sh * s) / 2.0
    else:
        offx, offy = bx, by
    out = []
    for s in strokes:
        out.append([(offx + (px - x0) * sx, offy + (py - y0) * sy) for (px, py) in s])
    return out


def resample(stroke: Stroke, spacing: float = 4.0) -> Stroke:
    """Re-space a polyline so consecutive points are ~``spacing`` apart.

    Keeps the mouse moving at an even pace instead of sprinting through long
    straight segments and crawling around tight curves.
    """
    if len(stroke) < 2 or spacing <= 0:
        return list(stroke)
    out = [stroke[0]]
    carry = 0.0
    for i in range(1, len(stroke)):
        (x0, y0), (x1, y1) = stroke[i - 1], stroke[i]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-9:
            continue
        d = spacing - carry
        while d <= seg:
            f = d / seg
            out.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
            d += spacing
        carry = (seg - (d - spacing))
    last = stroke[-1]
    if math.hypot(last[0] - out[-1][0], last[1] - out[-1][1]) > 1e-6:
        out.append(last)
    return out


def point_count(strokes: Drawing) -> int:
    return sum(len(s) for s in strokes)


# --------------------------------------------------------------------------
# SVG preview  (used by the web UI and by the offline tests)
# --------------------------------------------------------------------------

def strokes_to_svg(strokes: Drawing, width: int = 480, height: int = 480,
                   color: str = "#6fffe0", bg: str = "none",
                   stroke_width: float = 2.0, pad: float = 0.06) -> str:
    """Render strokes as an SVG string in the drawing's own coordinate space."""
    x0, y0, x1, y1 = drawing_bounds(strokes)
    w = (x1 - x0) or 1.0
    h = (y1 - y0) or 1.0
    scale = min(width / w, height / h) * (1.0 - 2 * pad)
    ox = (width - w * scale) / 2.0 - x0 * scale
    oy = (height - h * scale) / 2.0 - y0 * scale
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">'
        % (width, height, width, height),
        '<rect width="100%%" height="100%%" fill="%s"/>' % bg,
        '<g fill="none" stroke="%s" stroke-width="%.2f" stroke-linecap="round" '
        'stroke-linejoin="round">' % (color, stroke_width),
    ]
    for s in strokes:
        if len(s) == 1:
            p = s[0]
            parts.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s" stroke="none"/>'
                         % (p[0] * scale + ox, p[1] * scale + oy, stroke_width, color))
            continue
        d = "M " + " L ".join("%.2f %.2f" % (p[0] * scale + ox, p[1] * scale + oy) for p in s)
        parts.append('<path d="%s"/>' % d)
    parts.append("</g></svg>")
    return "".join(parts)
