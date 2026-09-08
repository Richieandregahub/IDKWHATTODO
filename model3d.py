"""Tiny dependency-free 3D modelling kit for Richie Jarvis.

Meshes are built from primitives and composed with transforms, then written
out as OBJ (for viewers/editors) or binary STL (for 3D printing).  Everything
is stdlib-only so it runs anywhere, and :func:`mesh_to_svg` renders a shaded
preview that the web UI can show without a 3D library.

Convention: models are built Y-up sitting on the ``y = 0`` ground plane.
STL export flips to Z-up, which is what slicers expect.
"""

from __future__ import annotations

import math
import struct
from typing import Dict, Iterable, List, Sequence, Tuple

__all__ = [
    "Mesh",
    "box", "sphere", "cylinder", "cone", "torus", "pyramid", "prism",
    "revolve", "vase", "mug", "pawn", "goblet", "gear", "gem",
    "robot", "house", "tree", "snowman", "rocket", "table", "chair",
    "MODELS", "make_model",
    "translate", "scale", "rotate_x", "rotate_y", "rotate_z", "merge",
    "write_obj", "write_stl", "mesh_to_svg",
    "mesh_stats", "mesh_volume", "is_closed",
]

Point = Tuple[float, float, float]
Face = Tuple[int, int, int]


class Mesh:
    """Triangle soup with helper accessors. Vertices are 0-indexed."""

    __slots__ = ("verts", "faces", "name")

    def __init__(self, verts: Iterable[Point] = (), faces: Iterable[Face] = (),
                 name: str = "mesh"):
        self.verts: List[Point] = [tuple(map(float, v)) for v in verts]
        self.faces: List[Face] = [tuple(int(i) for i in f) for f in faces]
        self.name = name

    # -- builders ---------------------------------------------------------
    def add(self, other: "Mesh") -> "Mesh":
        """Append another mesh's geometry in place (used while composing)."""
        base = len(self.verts)
        self.verts.extend(other.verts)
        self.faces.extend((a + base, b + base, c + base) for (a, b, c) in other.faces)
        return self

    # -- info -------------------------------------------------------------
    @property
    def nverts(self) -> int:
        return len(self.verts)

    @property
    def nfaces(self) -> int:
        return len(self.faces)

    def bbox(self) -> Tuple[Point, Point]:
        if not self.verts:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        xs = [v[0] for v in self.verts]
        ys = [v[1] for v in self.verts]
        zs = [v[2] for v in self.verts]
        return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))

    def size(self) -> Point:
        (x0, y0, z0), (x1, y1, z1) = self.bbox()
        return (x1 - x0, y1 - y0, z1 - z0)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<Mesh %s verts=%d faces=%d>" % (self.name, self.nverts, self.nfaces)


# --------------------------------------------------------------------------
# transforms (all return new meshes)
# --------------------------------------------------------------------------

def translate(m: Mesh, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> Mesh:
    return Mesh([(x + dx, y + dy, z + dz) for (x, y, z) in m.verts], m.faces, m.name)


def scale(m: Mesh, sx: float = 1.0, sy: float = None, sz: float = None) -> Mesh:
    sy = sx if sy is None else sy
    sz = sx if sz is None else sz
    return Mesh([(x * sx, y * sy, z * sz) for (x, y, z) in m.verts], m.faces, m.name)


def rotate_y(m: Mesh, deg: float) -> Mesh:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return Mesh([(x * c + z * s, y, -x * s + z * c) for (x, y, z) in m.verts], m.faces, m.name)


def rotate_x(m: Mesh, deg: float) -> Mesh:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return Mesh([(x, y * c - z * s, y * s + z * c) for (x, y, z) in m.verts], m.faces, m.name)


def rotate_z(m: Mesh, deg: float) -> Mesh:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return Mesh([(x * c - y * s, x * s + y * c, z) for (x, y, z) in m.verts], m.faces, m.name)


def merge(meshes: Sequence[Mesh], name: str = "merged") -> Mesh:
    out = Mesh(name=name)
    for m in meshes:
        out.add(m)
    return out


def weld(m: Mesh, eps: float = 1e-6) -> Mesh:
    """Merge coincident vertices and drop degenerate triangles.

    Primitives like spheres and revolved profiles generate duplicate vertices
    at the poles (every point of a ring lands on the same spot).  Unwelded,
    those become non-manifold edges and slicers reject the STL - so every
    model passes through here before export.
    """
    lookup: Dict[Tuple[int, int, int], int] = {}
    remap: List[int] = []
    verts: List[Point] = []
    for (x, y, z) in m.verts:
        key = (int(round(x / eps)), int(round(y / eps)), int(round(z / eps)))
        idx = lookup.get(key)
        if idx is None:
            idx = len(verts)
            verts.append((x, y, z))
            lookup[key] = idx
        remap.append(idx)
    faces: List[Face] = []
    for (a, b, c) in m.faces:
        na, nb, nc = remap[a], remap[b], remap[c]
        if na != nb and nb != nc and na != nc:
            faces.append((na, nb, nc))
    return Mesh(verts, faces, m.name)


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------

def box(w: float = 1.0, h: float = 1.0, d: float = 1.0,
        cx: float = 0.0, cy: float = None, cz: float = 0.0) -> Mesh:
    """Axis-aligned box. By default it sits on the ground (``y`` from 0..h)."""
    cy = h / 2.0 if cy is None else cy
    x0, x1 = cx - w / 2.0, cx + w / 2.0
    y0, y1 = cy - h / 2.0, cy + h / 2.0
    z0, z1 = cz - d / 2.0, cz + d / 2.0
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 2, 1), (0, 3, 2),          # -z
         (4, 5, 6), (4, 6, 7),          # +z
         (0, 1, 5), (0, 5, 4),          # -y
         (3, 7, 6), (3, 6, 2),          # +y
         (0, 4, 7), (0, 7, 3),          # -x
         (1, 2, 6), (1, 6, 5)]          # +x
    return Mesh(v, f, "box")


def sphere(r: float = 0.5, seg: int = 24, rings: int = 16,
           cx: float = 0.0, cy: float = 0.0, cz: float = 0.0) -> Mesh:
    seg = max(6, int(seg))
    rings = max(4, int(rings))
    verts: List[Point] = []
    for j in range(rings + 1):
        phi = math.pi * j / rings
        for i in range(seg):
            theta = 2 * math.pi * i / seg
            x = cx + r * math.sin(phi) * math.cos(theta)
            y = cy + r * math.cos(phi)
            z = cz + r * math.sin(phi) * math.sin(theta)
            verts.append((x, y, z))
    faces: List[Face] = []
    for j in range(rings):
        for i in range(seg):
            a = j * seg + i
            b = j * seg + (i + 1) % seg
            c = (j + 1) * seg + (i + 1) % seg
            d = (j + 1) * seg + i
            if j == 0:
                faces.append((a, c, d))
            elif j == rings - 1:
                faces.append((a, b, d))
            else:
                faces.append((a, b, d))
                faces.append((b, c, d))
    return Mesh(verts, faces, "sphere")


def cylinder(r: float = 0.4, h: float = 1.0, seg: int = 28,
             r_top: float = None, cx: float = 0.0, cz: float = 0.0,
             y0: float = 0.0) -> Mesh:
    """Cylinder (or truncated cone when ``r_top`` differs from ``r``)."""
    r_top = r if r_top is None else r_top
    seg = max(3, int(seg))
    verts: List[Point] = []
    faces: List[Face] = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        verts.append((cx + r * math.cos(a), y0, cz + r * math.sin(a)))
    for i in range(seg):
        a = 2 * math.pi * i / seg
        verts.append((cx + r_top * math.cos(a), y0 + h, cz + r_top * math.sin(a)))
    # counter-clockwise seen from outside -> normals point away from the axis
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((i, seg + j, j))
        faces.append((i, seg + i, seg + j))
    if r_top > 1e-9:
        top = len(verts)
        verts.append((cx, y0 + h, cz))
        for i in range(seg):
            faces.append((seg + (i + 1) % seg, seg + i, top))
    if r > 1e-9:
        bot = len(verts)
        verts.append((cx, y0, cz))
        for i in range(seg):
            faces.append((i, (i + 1) % seg, bot))
    return Mesh(verts, faces, "cylinder")


def cone(r: float = 0.5, h: float = 1.0, seg: int = 28, **kw) -> Mesh:
    m = cylinder(r=r, h=h, seg=seg, r_top=0.0, **kw)
    m.name = "cone"
    return m


def prism(r: float = 0.5, h: float = 1.0, sides: int = 6, **kw) -> Mesh:
    m = cylinder(r=r, h=h, seg=max(3, int(sides)), **kw)
    m.name = "prism"
    return m


def pyramid(base: float = 1.0, h: float = 1.0, sides: int = 4,
            cx: float = 0.0, cz: float = 0.0, y0: float = 0.0) -> Mesh:
    sides = max(3, int(sides))
    verts: List[Point] = []
    faces: List[Face] = []
    for i in range(sides):
        a = 2 * math.pi * i / sides - math.pi / 2
        verts.append((cx + base / 2 * math.cos(a), y0, cz + base / 2 * math.sin(a)))
    apex = len(verts)
    verts.append((cx, y0 + h, cz))
    base_c = len(verts)
    verts.append((cx, y0, cz))
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((i, apex, j))        # side
        faces.append((j, base_c, i))      # base
    return Mesh(verts, faces, "pyramid")


def torus(R: float = 0.6, r: float = 0.2, seg_u: int = 28, seg_v: int = 14,
          cy: float = 0.0) -> Mesh:
    seg_u = max(6, int(seg_u))
    seg_v = max(4, int(seg_v))
    verts: List[Point] = []
    for i in range(seg_u):
        u = 2 * math.pi * i / seg_u
        for j in range(seg_v):
            v = 2 * math.pi * j / seg_v
            x = (R + r * math.cos(v)) * math.cos(u)
            y = cy + r * math.sin(v)
            z = (R + r * math.cos(v)) * math.sin(u)
            verts.append((x, y, z))
    faces: List[Face] = []
    for i in range(seg_u):
        for j in range(seg_v):
            a = i * seg_v + j
            b = i * seg_v + (j + 1) % seg_v
            c = ((i + 1) % seg_u) * seg_v + (j + 1) % seg_v
            d = ((i + 1) % seg_u) * seg_v + j
            faces.append((a, b, c))
            faces.append((a, c, d))
    return Mesh(verts, faces, "torus")


def revolve(profile: Sequence[Tuple[float, float]], seg: int = 28,
            cap_bottom: bool = True, cap_top: bool = True,
            cy: float = 0.0) -> Mesh:
    """Surface of revolution from a ``(radius, height)`` profile (bottom → top)."""
    seg = max(6, int(seg))
    n = len(profile)
    if n < 2:
        raise ValueError("profile needs at least two (radius, height) points")
    verts: List[Point] = []
    for (r, y) in profile:
        for i in range(seg):
            a = 2 * math.pi * i / seg
            verts.append((r * math.cos(a), cy + y, r * math.sin(a)))
    faces: List[Face] = []
    for k in range(n - 1):
        r0, _ = profile[k]
        r1, _ = profile[k + 1]
        for i in range(seg):
            j = (i + 1) % seg
            a = k * seg + i
            b = k * seg + j
            c = (k + 1) * seg + j
            d = (k + 1) * seg + i
            if r0 > 1e-9:
                faces.append((a, c, b))
                faces.append((a, d, c))
            else:  # profile starts on the axis: fan instead of quad
                faces.append((a, d, c))
    # caps
    if cap_bottom and profile[0][0] > 1e-9:
        c = len(verts)
        verts.append((0.0, cy + profile[0][1], 0.0))
        for i in range(seg):
            faces.append((i, (i + 1) % seg, c))
    if cap_top and profile[-1][0] > 1e-9:
        c = len(verts)
        verts.append((0.0, cy + profile[-1][1], 0.0))
        base = (n - 1) * seg
        for i in range(seg):
            faces.append((base + (i + 1) % seg, base + i, c))
    return Mesh(verts, faces, "revolve")


# --------------------------------------------------------------------------
# composed models
# --------------------------------------------------------------------------

def vase(h: float = 1.6, seg: int = 32) -> Mesh:
    prof = []
    steps = 24
    for i in range(steps + 1):
        f = i / steps
        y = h * f
        r = 0.16 + 0.34 * math.sin(math.pi * (0.15 + 0.85 * f)) ** 0.8
        prof.append((r, y))
    m = revolve(prof, seg=seg)
    m.name = "vase"
    return m


def mug(h: float = 0.9, r: float = 0.42, seg: int = 32) -> Mesh:
    wall = 0.05
    prof = [(0.0, 0.0), (r, 0.0), (r, h), (r - wall, h),
            (r - wall, wall), (0.0, wall)]
    body = revolve(prof, seg=seg, cap_top=False)
    handle = torus(R=r * 0.62, r=0.07, seg_u=22, seg_v=10, cy=h * 0.52)
    handle = translate(handle, r * 0.95, 0.0, 0.0)
    handle = rotate_z(handle, 90)
    handle = rotate_y(handle, 90)
    m = merge([body, handle], "mug")
    return m


def pawn(h: float = 1.5, seg: int = 28) -> Mesh:
    prof = [(0.0, 0.0), (0.42, 0.0), (0.42, 0.10), (0.30, 0.20),
            (0.20, 0.34), (0.20, 0.72), (0.30, 0.86), (0.22, 0.96),
            (0.26, 1.06), (0.16, 1.16), (0.0, 1.22)]
    prof = [(r, y * h / 1.22) for (r, y) in prof]
    m = revolve(prof, seg=seg, cap_top=False)
    m.name = "pawn"
    return m


def goblet(h: float = 1.5, seg: int = 28) -> Mesh:
    prof = [(0.0, 0.0), (0.38, 0.0), (0.34, 0.06), (0.10, 0.12),
            (0.08, 0.62), (0.26, 0.72), (0.34, 0.78), (0.34, 1.30),
            (0.30, 1.30), (0.30, 0.82), (0.20, 0.76), (0.05, 0.68),
            (0.05, 0.16), (0.28, 0.09), (0.0, 0.06)]
    prof = [(r, y * h / 1.30) for (r, y) in prof]
    m = revolve(prof, seg=seg, cap_top=False)
    m.name = "goblet"
    return m


def gear(teeth: int = 12, R: float = 0.7, r: float = 0.55, thick: float = 0.22,
         bore: float = 0.18) -> Mesh:
    """Spur gear: toothed outer ring extruded along Y, with a centre bore.

    The bore ring uses the same vertex count as the outer ring so the flat
    faces are a clean annulus (and the mesh stays watertight).
    """
    teeth = max(6, int(teeth))
    n = teeth * 4
    outer: List[Point] = []
    ring: List[Point] = []
    for i in range(n):
        k = i % 4
        a = 2 * math.pi * i / n
        rad = R if k in (1, 2) else r
        outer.append((rad * math.cos(a), rad * math.sin(a)))
        ring.append((bore * math.cos(a), bore * math.sin(a)))
    verts: List[Point] = []
    faces: List[Face] = []
    # two flat rings: outer[0..n) and bore[0..n), at y = -t/2 and y = +t/2
    for y in (-thick / 2, thick / 2):
        for p in outer:
            verts.append((p[0], y, p[1]))
        for p in ring:
            verts.append((p[0], y, p[1]))
    lo_out, lo_in, hi_out, hi_in = 0, n, 2 * n, 3 * n
    for i in range(n):
        j = (i + 1) % n
        # outer wall (normals point away from the axis)
        faces.append((lo_out + i, hi_out + j, lo_out + j))
        faces.append((lo_out + i, hi_out + i, hi_out + j))
        # bore wall: normals point into the hole, i.e. away from the material
        faces.append((hi_in + i, lo_in + i, lo_in + j))
        faces.append((hi_in + j, hi_in + i, lo_in + j))
        # bottom face (normal -Y)
        faces.append((lo_out + j, lo_in + i, lo_out + i))
        faces.append((lo_in + j, lo_in + i, lo_out + j))
        # top face (normal +Y)
        faces.append((hi_out + i, hi_in + j, hi_out + j))
        faces.append((hi_in + i, hi_in + j, hi_out + i))
    m = Mesh(verts, faces, "gear")
    m = rotate_x(m, 90)          # lay the wheel upright
    return translate(m, 0.0, R, 0.0)


def gem(sides: int = 8, R: float = 0.6, top: float = 0.55, bottom: float = 0.9) -> Mesh:
    sides = max(4, int(sides))
    girdle = R
    verts: List[Point] = []
    for i in range(sides):
        a = 2 * math.pi * i / sides
        verts.append((girdle * math.cos(a), 0.0, girdle * math.sin(a)))
    apex_t = len(verts)
    verts.append((0.0, top, 0.0))
    apex_b = len(verts)
    verts.append((0.0, -bottom, 0.0))
    faces: List[Face] = []
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((i, apex_t, j))
        faces.append((j, apex_b, i))
    m = Mesh(verts, faces, "gem")
    return translate(m, 0.0, bottom, 0.0)


def robot(h: float = 2.0) -> Mesh:
    s = h / 2.0
    parts = [
        translate(box(0.9 * s, 0.95 * s, 0.7 * s), 0.0, 0.60 * s, 0.0),      # torso
        translate(box(0.75 * s, 0.60 * s, 0.65 * s), 0.0, 1.35 * s, 0.0),   # head
        translate(sphere(0.13 * s, 14, 10), -0.19 * s, 1.42 * s, 0.32 * s),  # eyes
        translate(sphere(0.13 * s, 14, 10), 0.19 * s, 1.42 * s, 0.32 * s),
        translate(cylinder(0.10 * s, 0.42 * s, 12), 0.0, 1.65 * s, 0.0),    # antenna
        translate(sphere(0.11 * s, 12, 8), 0.0, 2.10 * s, 0.0),
        translate(cylinder(0.14 * s, 0.75 * s, 12), -0.58 * s, 0.55 * s, 0.0),  # arms
        translate(cylinder(0.14 * s, 0.75 * s, 12), 0.58 * s, 0.55 * s, 0.0),
        translate(cylinder(0.18 * s, 0.60 * s, 12), -0.24 * s, 0.0, 0.0),   # legs
        translate(cylinder(0.18 * s, 0.60 * s, 12), 0.24 * s, 0.0, 0.0),
        translate(box(0.42 * s, 0.16 * s, 0.34 * s), -0.24 * s, 0.0, 0.06 * s),  # feet
        translate(box(0.42 * s, 0.16 * s, 0.34 * s), 0.24 * s, 0.0, 0.06 * s),
    ]
    return merge(parts, "robot")


def house(w: float = 1.6, d: float = 1.4, wall_h: float = 1.0, roof_h: float = 0.7) -> Mesh:
    body = box(w, wall_h, d, cy=wall_h / 2)
    roof = pyramid(base=max(w, d) * 1.32, h=roof_h, sides=4)
    roof = rotate_y(roof, 45)
    roof = translate(roof, 0.0, wall_h, 0.0)
    door = box(w * 0.22, wall_h * 0.62, 0.06, cy=wall_h * 0.31, cz=d / 2)
    chimney = box(0.18, roof_h * 1.05, 0.18, cx=w * 0.30, cy=wall_h + roof_h * 0.5, cz=-d * 0.22)
    return merge([body, roof, door, chimney], "house")


def tree(h: float = 2.0) -> Mesh:
    trunk = cylinder(0.11, h * 0.42, 14)
    c1 = translate(cone(0.52, h * 0.46, 18), 0.0, h * 0.34, 0.0)
    c2 = translate(cone(0.42, h * 0.40, 18), 0.0, h * 0.56, 0.0)
    c3 = translate(cone(0.30, h * 0.34, 18), 0.0, h * 0.76, 0.0)
    return merge([trunk, c1, c2, c3], "tree")


def snowman(h: float = 1.8) -> Mesh:
    r1 = h * 0.24
    r2 = h * 0.17
    r3 = h * 0.12
    b = translate(sphere(r1, 20, 14), 0.0, r1, 0.0)
    m = translate(sphere(r2, 20, 14), 0.0, r1 * 2 + r2 * 0.86, 0.0)
    hd = translate(sphere(r3, 20, 14), 0.0, r1 * 2 + r2 * 1.72 + r3 * 0.86, 0.0)
    # rotate first (about the origin), then move: rotating after translating
    # would swing the carrot down through the floor
    nose = rotate_x(cone(0.05, 0.22, 10), 90)
    nose = translate(nose, 0.0, r1 * 2 + r2 * 1.72 + r3 * 0.9, r3 * 0.95)
    return merge([b, m, hd, nose], "snowman")


def rocket(h: float = 2.2) -> Mesh:
    body = cylinder(0.22, h * 0.58, 20)
    body = translate(body, 0.0, h * 0.22, 0.0)
    nose = translate(cone(0.22, h * 0.30, 20), 0.0, h * 0.80, 0.0)
    fins = []
    for i in range(4):
        f = translate(box(0.30, 0.36, 0.04), 0.0, h * 0.28, 0.0)
        f = translate(f, 0.0, 0.0, 0.26)
        f = rotate_y(f, 90 * i)
        fins.append(f)
    bell = translate(cylinder(0.16, 0.18, 20, r_top=0.26), 0.0, h * 0.04, 0.0)
    return merge([body, nose, bell] + fins, "rocket")


def table(w: float = 1.6, d: float = 0.9, h: float = 0.75) -> Mesh:
    top = box(w, 0.06, d, cy=h)
    legs = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            legs.append(translate(box(0.08, h, 0.08, cy=h / 2),
                                  sx * (w / 2 - 0.10), 0.0, sz * (d / 2 - 0.10)))
    return merge([top] + legs, "table")


def chair(h: float = 1.0) -> Mesh:
    seat = box(0.5, 0.06, 0.5, cy=h * 0.45)
    back = box(0.5, h * 0.5, 0.06, cy=h * 0.70, cz=-0.22)
    legs = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            legs.append(translate(box(0.06, h * 0.45, 0.06, cy=h * 0.225),
                                  sx * 0.20, 0.0, sz * 0.20))
    return merge([seat, back] + legs, "chair")


MODELS: Dict[str, callable] = {
    "box": lambda **kw: box(**kw),
    "cube": lambda **kw: box(**kw),
    "sphere": lambda **kw: translate(sphere(**kw), 0.0, kw.get("r", 0.5), 0.0),
    "ball": lambda **kw: translate(sphere(**kw), 0.0, kw.get("r", 0.5), 0.0),
    "cylinder": lambda **kw: cylinder(**kw),
    "cone": lambda **kw: cone(**kw),
    "pyramid": lambda **kw: pyramid(**kw),
    "prism": lambda **kw: prism(**kw),
    "torus": lambda **kw: translate(torus(**kw), 0.0, kw.get("r", 0.2), 0.0),
    "donut": lambda **kw: translate(torus(**kw), 0.0, kw.get("r", 0.2), 0.0),
    "gear": lambda **kw: gear(**kw),
    "gem": lambda **kw: gem(**kw),
    "vase": lambda **kw: vase(**kw),
    "mug": lambda **kw: mug(**kw),
    "cup": lambda **kw: mug(**kw),
    "pawn": lambda **kw: pawn(**kw),
    "goblet": lambda **kw: goblet(**kw),
    "robot": lambda **kw: robot(**kw),
    "house": lambda **kw: house(**kw),
    "tree": lambda **kw: tree(**kw),
    "snowman": lambda **kw: snowman(**kw),
    "rocket": lambda **kw: rocket(**kw),
    "table": lambda **kw: table(**kw),
    "chair": lambda **kw: chair(**kw),
}

# Arguments each model accepts, used to build the LLM tool schema.
MODEL_PARAMS: Dict[str, Dict[str, str]] = {
    "box": {"w": "width", "h": "height", "d": "depth"},
    "cube": {"w": "size", "h": "height (optional)", "d": "depth (optional)"},
    "sphere": {"r": "radius"},
    "ball": {"r": "radius"},
    "cylinder": {"r": "radius", "h": "height"},
    "cone": {"r": "base radius", "h": "height"},
    "pyramid": {"base": "base width", "h": "height", "sides": "number of sides (default 4)"},
    "prism": {"r": "radius", "h": "height", "sides": "number of sides (default 6)"},
    "torus": {"R": "ring radius", "r": "tube radius"},
    "donut": {"R": "ring radius", "r": "tube radius"},
    "gear": {"teeth": "tooth count (default 12)"},
    "gem": {"sides": "number of facets (default 8)"},
    "vase": {"h": "height"},
    "mug": {"h": "height", "r": "radius"},
    "cup": {"h": "height", "r": "radius"},
    "pawn": {"h": "height"},
    "goblet": {"h": "height"},
    "robot": {"h": "height"},
    "house": {"w": "width", "d": "depth"},
    "tree": {"h": "height"},
    "snowman": {"h": "height"},
    "rocket": {"h": "height"},
    "table": {"w": "width", "d": "depth"},
    "chair": {"h": "height"},
}


def make_model(kind: str, **params) -> Mesh:
    """Build a model by name. Unknown names raise ``ValueError``."""
    key = str(kind or "").strip().lower()
    if key not in MODELS:
        raise ValueError("unknown model '%s' (try: %s)"
                         % (kind, ", ".join(sorted(MODELS))))
    allowed = MODEL_PARAMS.get(key, {})
    clean = {}
    for k, v in params.items():
        if k in allowed and v is not None:
            try:
                clean[k] = float(v)
            except (TypeError, ValueError):
                continue
    m = MODELS[key](**clean)
    m.name = key
    return weld(m)


# --------------------------------------------------------------------------
# mesh maths
# --------------------------------------------------------------------------

def mesh_volume(m: Mesh) -> float:
    """Signed volume via the divergence theorem (exact for closed meshes)."""
    total = 0.0
    for (a, b, c) in m.faces:
        ax, ay, az = m.verts[a]
        bx, by, bz = m.verts[b]
        cx, cy, cz = m.verts[c]
        total += (ax * (by * cz - bz * cy)
                  - ay * (bx * cz - bz * cx)
                  + az * (bx * cy - by * cx)) / 6.0
    return total


def is_closed(m: Mesh) -> bool:
    """True when every edge is shared by exactly two triangles (watertight).

    Watertight meshes are the only ones slicers accept, so this doubles as the
    quality gate for STL export.
    """
    edges: Dict[Tuple[int, int], int] = {}
    for (a, b, c) in m.faces:
        for (u, v) in ((a, b), (b, c), (c, a)):
            key = (min(u, v), max(u, v))
            edges[key] = edges.get(key, 0) + 1
    return all(v == 2 for v in edges.values()) if edges else False


def mesh_stats(m: Mesh) -> Dict[str, float]:
    (_, _, _), _ = m.bbox()
    w, h, d = m.size()
    return {
        "name": m.name,
        "verts": m.nverts,
        "faces": m.nfaces,
        "width": round(w, 3),
        "height": round(h, 3),
        "depth": round(d, 3),
        "volume": round(abs(mesh_volume(m)), 4),
        "watertight": bool(is_closed(m)),
    }


# --------------------------------------------------------------------------
# exporters
# --------------------------------------------------------------------------

def write_obj(m: Mesh, path: str) -> str:
    lines = ["# generated by Richie Jarvis (model3d.py)", "o %s" % m.name]
    for (x, y, z) in m.verts:
        lines.append("v %.6f %.6f %.6f" % (x, y, z))
    for (a, b, c) in m.faces:
        lines.append("f %d %d %d" % (a + 1, b + 1, c + 1))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def write_stl(m: Mesh, path: str, binary: bool = True) -> str:
    """Write STL in Z-up orientation (y-up → z-up: y→z, z→-y)."""
    verts = [(x, -z, y) for (x, y, z) in m.verts]
    if not binary:
        out = ["solid %s" % m.name]
        for (a, b, c) in m.faces:
            p, q, r = verts[a], verts[b], verts[c]
            ux, uy, uz = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
            vx, vy, vz = (r[0] - p[0], r[1] - p[1], r[2] - p[2])
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            out.append(" facet normal %.6f %.6f %.6f" % (nx / ln, ny / ln, nz / ln))
            out.append("  outer loop")
            for pnt in (p, q, r):
                out.append("   vertex %.6f %.6f %.6f" % pnt)
            out.append("  endloop")
            out.append(" endfacet")
        out.append("endsolid %s" % m.name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        return path

    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(m.faces)))
        for (a, b, c) in m.faces:
            p, q, r = verts[a], verts[b], verts[c]
            ux, uy, uz = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
            vx, vy, vz = (r[0] - p[0], r[1] - p[1], r[2] - p[2])
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            f.write(struct.pack("<3f", nx / ln, ny / ln, nz / ln))
            for pnt in (p, q, r):
                f.write(struct.pack("<3f", *pnt))
            f.write(struct.pack("<H", 0))
    return path


# --------------------------------------------------------------------------
# shaded SVG preview
# --------------------------------------------------------------------------

def _rotate(pt: Point, yaw: float, pitch: float) -> Point:
    x, y, z = pt
    cy, sy = math.cos(yaw), math.sin(yaw)
    x, z = x * cy + z * sy, -x * sy + z * cy
    cp, sp = math.cos(pitch), math.sin(pitch)
    y, z = y * cp - z * sp, y * sp + z * cp
    return (x, y, z)


def mesh_to_svg(m: Mesh, size: int = 480, yaw: float = 35.0, pitch: float = 18.0,
                color: Tuple[int, int, int] = (111, 255, 224),
                bg: str = "none", shade: bool = True) -> str:
    """Painter's-algorithm render with simple Lambert shading."""
    # centre on the origin, then fit
    (x0, y0, z0), (x1, y1, z1) = m.bbox()
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    pts = [(x - cx, y - cy, z - cz) for (x, y, z) in m.verts]
    pts = [_rotate(p, math.radians(yaw), math.radians(pitch)) for p in pts]
    radius = max(math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2) for p in pts) or 1.0
    dist = radius * 3.4
    focal = size * 0.9
    proj = []
    for (x, y, z) in pts:
        denom = max(dist - z, 1e-6)
        s = focal / denom
        proj.append((size / 2 + x * s, size / 2 - y * s, z))

    light = (-0.45, 0.72, 0.52)
    tris = []
    for (a, b, c) in m.faces:
        pa, pb, pc = proj[a], proj[b], proj[c]
        va, vb, vc = pts[a], pts[b], pts[c]
        ux, uy, uz = (vb[0] - va[0], vb[1] - va[1], vb[2] - va[2])
        vx, vy, vz = (vc[0] - va[0], vc[1] - va[1], vc[2] - va[2])
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nx, ny, nz = nx / ln, ny / ln, nz / ln
        # rotate the normal the same way as the vertices
        nx, ny, nz = _rotate((nx, ny, nz), math.radians(yaw), math.radians(pitch))
        if nz <= 0.0:  # back-facing
            continue
        depth = (pa[2] + pb[2] + pc[2]) / 3.0
        if shade:
            lam = max(0.0, nx * light[0] + ny * light[1] + nz * light[2])
            k = 0.22 + 0.78 * lam
            k = min(max(k, 0.12), 1.15)
        else:
            k = 1.0
        r = min(255, int(color[0] * k))
        g = min(255, int(color[1] * k))
        bl = min(255, int(color[2] * k))
        tris.append((depth, pa, pb, pc, "#%02x%02x%02x" % (r, g, bl)))
    tris.sort(key=lambda t: t[0])  # far → near

    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
           'width="%d" height="%d">' % (size, size, size, size),
           '<rect width="100%%" height="100%%" fill="%s"/>' % bg]
    for (_d, pa, pb, pc, col) in tris:
        out.append('<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="%s" '
                   'stroke="%s" stroke-width="0.4"/>'
                   % (pa[0], pa[1], pb[0], pb[1], pc[0], pc[1], col, col))
    out.append("</svg>")
    return "".join(out)
