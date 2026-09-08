"""Dev-only: rasterize shapes/meshes to PNG so the geometry can be eyeballed.

Nothing in the app uses this - it exists so the drawing and 3D code can be
verified visually on any machine (no Pillow, no numpy, just zlib).

    python3 tools/preview.py            # writes everything into tools/out/
    python3 tools/preview.py robot gear # only those models
"""

from __future__ import annotations

import math
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import draw as D            # noqa: E402
import model3d as M         # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


# --------------------------------------------------------------------------
# minimal PNG encoder
# --------------------------------------------------------------------------

def _chunk(tag: bytes, data: bytes) -> bytes:
    return (len(data).to_bytes(4, "big") + tag + data
            + (zlib.crc32(tag + data) & 0xFFFFFFFF).to_bytes(4, "big"))


def write_png(path: str, w: int, h: int, pixels: bytearray) -> str:
    """``pixels`` is raw RGB, ``w * h * 3`` bytes."""
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)  # filter type 0
        raw.extend(pixels[y * stride:(y + 1) * stride])
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", w.to_bytes(4, "big") + h.to_bytes(4, "big")
                    + bytes([8, 2, 0, 0, 0]))
           + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return path


class Canvas:
    def __init__(self, w: int, h: int, bg=(8, 12, 20)):
        self.w, self.h = w, h
        self.px = bytearray(bg * (w * h))

    def set(self, x: int, y: int, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(c)

    def line(self, p0, p1, c, width=2):
        (x0, y0), (x1, y1) = p0, p1
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        if steps > 6000:
            steps = 6000
        r = width // 2
        for i in range(steps + 1):
            f = i / steps
            x = x0 + (x1 - x0) * f
            y = y0 + (y1 - y0) * f
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    self.set(int(x) + dx, int(y) + dy, c)

    def triangle(self, p0, p1, p2, c):
        """Flat-filled triangle via the edge function (no z-buffer)."""
        xs = [p0[0], p1[0], p2[0]]
        ys = [p0[1], p1[1], p2[1]]
        minx, maxx = int(max(0, min(xs))), int(min(self.w - 1, max(xs)))
        miny, maxy = int(max(0, min(ys))), int(min(self.h - 1, max(ys)))
        if minx > maxx or miny > maxy:
            return
        (ax, ay), (bx, by), (cx, cy) = p0, p1, p2
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-9:
            return
        for y in range(miny, maxy + 1):
            for x in range(minx, maxx + 1):
                px, py = x + 0.5, y + 0.5
                w0 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
                w1 = (cx - bx) * (py - by) - (cy - by) * (px - bx)
                w2 = (ax - cx) * (py - cy) - (ay - cy) * (px - cx)
                if area > 0:
                    if w0 >= 0 and w1 >= 0 and w2 >= 0:
                        self.set(x, y, c)
                else:
                    if w0 <= 0 and w1 <= 0 and w2 <= 0:
                        self.set(x, y, c)

    def save(self, path):
        return write_png(path, self.w, self.h, self.px)


# --------------------------------------------------------------------------
# renderers
# --------------------------------------------------------------------------

def render_drawing(strokes, path, size=360, pad=26, color=(111, 255, 224)):
    fitted = D.fit_strokes(strokes, (pad, pad, size - 2 * pad, size - 2 * pad))
    cv = Canvas(size, size)
    for s in fitted:
        for i in range(1, len(s)):
            cv.line(s[i - 1], s[i], color, width=2)
        if len(s) == 1:
            cv.set(int(s[0][0]), int(s[0][1]), color)
    return cv.save(path)


def render_mesh(mesh, path, size=360, yaw=35.0, pitch=18.0, color=(111, 255, 224)):
    (x0, y0, z0), (x1, y1, z1) = mesh.bbox()
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    pts = [(x - cx, y - cy, z - cz) for (x, y, z) in mesh.verts]
    pts = [M._rotate(p, math.radians(yaw), math.radians(pitch)) for p in pts]
    radius = max(math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2) for p in pts) or 1.0
    dist, focal = radius * 3.4, size * 0.42
    proj = []
    for (x, y, z) in pts:
        s = focal / max(dist - z, 1e-6)
        proj.append((size / 2 + x * s, size / 2 - y * s, z))
    light = (-0.45, 0.72, 0.52)
    tris = []
    for (a, b, c) in mesh.faces:
        va, vb, vc = pts[a], pts[b], pts[c]
        ux, uy, uz = (vb[0] - va[0], vb[1] - va[1], vb[2] - va[2])
        vx, vy, vz = (vc[0] - va[0], vc[1] - va[1], vc[2] - va[2])
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nx, ny, nz = M._rotate((nx / ln, ny / ln, nz / ln), math.radians(yaw), math.radians(pitch))
        if nz <= 0:
            continue
        lam = max(0.0, nx * light[0] + ny * light[1] + nz * light[2])
        k = min(max(0.22 + 0.78 * lam, 0.12), 1.15)
        col = tuple(min(255, int(v * k)) for v in color)
        tris.append(((proj[a][2] + proj[b][2] + proj[c][2]) / 3.0,
                     proj[a], proj[b], proj[c], col))
    tris.sort(key=lambda t: t[0])
    cv = Canvas(size, size)
    for (_d, pa, pb, pc, col) in tris:
        cv.triangle((pa[0], pa[1]), (pb[0], pb[1]), (pc[0], pc[1]), col)
    return cv.save(path)


def contact_sheet(path, names, cols=4, tile=200, kind="mesh"):
    """Grid of several models/drawings in one PNG - handy for eyeballing."""
    rows = (len(names) + cols - 1) // cols
    sheet = Canvas(tile * cols, tile * rows)
    for idx, name in enumerate(names):
        r, c = divmod(idx, cols)
        tile_canvas = Canvas(tile, tile)
        if kind == "mesh":
            _draw_mesh_into(tile_canvas, make_mesh(name), tile)
        else:
            strokes = D.picture(name) if name in D.PICTURES else D.shape(name)
            fit = D.fit_strokes(strokes, (14, 14, tile - 28, tile - 28))
            for s in fit:
                for i in range(1, len(s)):
                    tile_canvas.line(s[i - 1], s[i], (111, 255, 224), width=2)
                if len(s) == 1:
                    tile_canvas.set(int(s[0][0]), int(s[0][1]), (111, 255, 224))
        for y in range(tile):
            for x in range(tile):
                i = (y * tile + x) * 3
                sheet.set(c * tile + x, r * tile + y, tuple(tile_canvas.px[i:i + 3]))
    return sheet.save(path)


def make_mesh(name):
    return M.make_model(name)


def _draw_mesh_into(canvas, mesh, size, yaw=35.0, pitch=18.0, color=(111, 255, 224)):
    (x0, y0, z0), (x1, y1, z1) = mesh.bbox()
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    pts = [(x - cx, y - cy, z - cz) for (x, y, z) in mesh.verts]
    pts = [M._rotate(p, math.radians(yaw), math.radians(pitch)) for p in pts]
    radius = max(math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2) for p in pts) or 1.0
    dist, focal = radius * 3.4, size * 0.42
    proj = [(size / 2 + x * focal / max(dist - z, 1e-6),
             size / 2 - y * focal / max(dist - z, 1e-6), z) for (x, y, z) in pts]
    light = (-0.45, 0.72, 0.52)
    tris = []
    for (a, b, c) in mesh.faces:
        va, vb, vc = pts[a], pts[b], pts[c]
        ux, uy, uz = (vb[0] - va[0], vb[1] - va[1], vb[2] - va[2])
        vx, vy, vz = (vc[0] - va[0], vc[1] - va[1], vc[2] - va[2])
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nx, ny, nz = M._rotate((nx / ln, ny / ln, nz / ln),
                               math.radians(yaw), math.radians(pitch))
        if nz <= 0:
            continue
        lam = max(0.0, nx * light[0] + ny * light[1] + nz * light[2])
        k = min(max(0.22 + 0.78 * lam, 0.12), 1.15)
        col = tuple(min(255, int(v * k)) for v in color)
        tris.append(((proj[a][2] + proj[b][2] + proj[c][2]) / 3.0,
                     proj[a], proj[b], proj[c], col))
    tris.sort(key=lambda t: t[0])
    for (_d, pa, pb, pc, col) in tris:
        canvas.triangle((pa[0], pa[1]), (pb[0], pb[1]), (pc[0], pc[1]), col)


def main(argv):
    os.makedirs(OUT_DIR, exist_ok=True)
    want = [a.lower() for a in argv[1:]]
    if want == ["sheets"]:
        contact_sheet(os.path.join(OUT_DIR, "sheet_models.png"),
                      ["robot", "house", "tree", "mug", "gear", "vase",
                       "snowman", "rocket", "gem", "pawn", "chair", "table"])
        contact_sheet(os.path.join(OUT_DIR, "sheet_draw.png"),
                      ["house", "robot", "cat", "tree", "boat", "sun",
                       "car", "star", "heart", "spiral", "sine", "fish"],
                      kind="draw")
        print("wrote sheet_models.png + sheet_draw.png to %s" % OUT_DIR)
        return 0
    models = list(M.MODELS)
    written = []
    for name in models:
        if want and name not in want:
            continue
        try:
            mesh = M.make_model(name)
        except Exception as e:  # pragma: no cover - dev aid
            print("skip %-9s %s" % (name, e))
            continue
        render_mesh(mesh, os.path.join(OUT_DIR, "model_%s.png" % name))
        written.append(name)
    if not want:
        for name in ("circle", "star", "heart", "spiral", "sine"):
            render_drawing(D.shape(name), os.path.join(OUT_DIR, "shape_%s.png" % name))
        for name in ("house", "robot", "cat", "tree", "boat", "sun", "car"):
            render_drawing(D.picture(name), os.path.join(OUT_DIR, "pic_%s.png" % name))
    print("wrote %d model previews (+ shape/drawing previews) to %s" % (len(written), OUT_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
