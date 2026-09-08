"""Offline tests: geometry, file formats, tool schema and the command parser.

These run anywhere - no Windows, no pyautogui, no API key - because the mouse
driver is stubbed out. Run with:

    python -m unittest discover -s tests -v
"""

import json
import math
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import draw as D              # noqa: E402
import model3d as M           # noqa: E402


class FakeMouse:
    """Stands in for pyautogui so tests never touch a real pointer."""

    FAILSAFE = True
    PAUSE = 0

    def __init__(self, size=(1920, 1080)):
        self.size_ = size
        self.pos = (0, 0)
        self.moves = []
        self.downs = []
        self.ups = []
        self.clicks = []
        self.keys = []

    # -- pyautogui surface used by server.py ------------------------------
    def size(self):
        return self.size_

    def position(self):
        return self.pos

    def moveTo(self, x, y=None, duration=0):
        if y is None:
            x, y = x
        self.pos = (int(x), int(y))
        self.moves.append((int(x), int(y)))

    def mouseDown(self, button="left"):
        self.downs.append(button)

    def mouseUp(self, button="left"):
        self.ups.append(button)

    def click(self, button="left", clicks=1):
        self.clicks.append((button, clicks))

    def doubleClick(self):
        self.clicks.append(("double", 2))

    def rightClick(self):
        self.clicks.append(("right", 1))

    def middleClick(self):
        self.clicks.append(("middle", 1))

    def scroll(self, amount):
        self.keys.append(("scroll", amount))

    def press(self, key):
        self.keys.append(("press", key))

    def write(self, text, interval=0):
        self.keys.append(("write", text))

    def hotkey(self, *parts):
        self.keys.append(("hotkey", parts))

    def screenshot(self, path=None):
        self.keys.append(("screenshot", path))
        return path


class DrawTests(unittest.TestCase):
    def test_every_shape_produces_finite_points(self):
        for name, fn in list(D.SHAPES.items()) + list(D.PICTURES.items()):
            strokes = fn()
            self.assertTrue(strokes, "%s produced no strokes" % name)
            for stroke in strokes:
                self.assertGreaterEqual(len(stroke), 1, name)
                for (x, y) in stroke:
                    self.assertTrue(math.isfinite(x) and math.isfinite(y),
                                    "%s has a non-finite point" % name)

    def test_shapes_stay_inside_the_unit_square(self):
        # a little slack: composed pictures may overshoot slightly by design
        for name, fn in list(D.SHAPES.items()) + list(D.PICTURES.items()):
            x0, y0, x1, y1 = D.drawing_bounds(fn())
            self.assertGreaterEqual(x0, -0.05, name)
            self.assertGreaterEqual(y0, -0.05, name)
            self.assertLessEqual(x1, 1.05, name)
            self.assertLessEqual(y1, 1.05, name)

    def test_fit_strokes_lands_inside_the_box(self):
        for name in ("circle", "star", "house", "robot"):
            strokes = D.shape(name) if name in D.SHAPES else D.picture(name)
            box = (300, 200, 500, 400)
            fitted = D.fit_strokes(strokes, box)
            x0, y0, x1, y1 = D.drawing_bounds(fitted)
            self.assertGreaterEqual(x0, box[0] - 0.5)
            self.assertGreaterEqual(y0, box[1] - 0.5)
            self.assertLessEqual(x1, box[0] + box[2] + 0.5)
            self.assertLessEqual(y1, box[1] + box[3] + 0.5)
            # and it should actually fill one axis of the box
            self.assertGreater(max(x1 - x0, y1 - y0), min(box[2], box[3]) * 0.9)

    def test_fit_keeps_aspect_ratio(self):
        strokes = D.shape("circle")
        fitted = D.fit_strokes(strokes, (0, 0, 400, 100))
        x0, y0, x1, y1 = D.drawing_bounds(fitted)
        self.assertAlmostEqual(x1 - x0, 100, delta=1.5)   # limited by height
        self.assertAlmostEqual(y1 - y0, 100, delta=1.5)

    def test_resample_is_evenly_spaced(self):
        # resample works in pixel space, so fit the drawing into a box first
        stroke = D.fit_strokes(D.shape("circle"), (0, 0, 600, 600))[0]
        out = D.resample(stroke, 5.0)
        gaps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(out, out[1:])]
        self.assertGreater(len(out), 10)
        self.assertLess(max(gaps), 5.0 + 1e-6)
        # total length must be preserved
        orig = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                   for a, b in zip(stroke, stroke[1:]))
        self.assertAlmostEqual(sum(gaps), orig, delta=orig * 0.02)

    def test_svg_output(self):
        svg = D.strokes_to_svg(D.shape("star"))
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("<path", svg)
        self.assertTrue(svg.rstrip().endswith("</svg>"))

    def test_unknown_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            D.shape("banana")
        with self.assertRaises(ValueError):
            D.picture("banana")


class Model3DTests(unittest.TestCase):
    def test_analytic_volumes(self):
        cases = [
            ("box", {}, 1.0),
            ("cylinder", {}, math.pi * 0.4 ** 2 * 1.0),
            ("cone", {}, math.pi * 0.5 ** 2 * 1.0 / 3.0),
            ("sphere", {}, 4.0 / 3.0 * math.pi * 0.5 ** 3),
        ]
        for kind, params, exact in cases:
            got = M.mesh_volume(M.make_model(kind, **params))
            self.assertGreater(got, 0, "%s has inverted normals" % kind)
            # tessellated meshes sit slightly under the true volume
            self.assertAlmostEqual(got, exact, delta=exact * 0.06,
                                   msg="%s volume off" % kind)

    def test_every_model_is_watertight_and_upright(self):
        # composed models bolt overlapping solids together, so a few are
        # intentionally open shells - everything else must be printable.
        open_shells = {"rocket"}
        for kind in M.MODELS:
            mesh = M.make_model(kind)
            self.assertGreater(M.mesh_volume(mesh), 0,
                               "%s normals point inwards" % kind)
            if kind in open_shells:
                continue
            self.assertTrue(M.is_closed(mesh), "%s is not watertight" % kind)

    def test_models_sit_on_the_ground(self):
        for kind in M.MODELS:
            (_x0, y0, _z0), _ = M.make_model(kind).bbox()
            self.assertGreaterEqual(y0, -1e-6, "%s sinks below y=0" % kind)

    def test_obj_roundtrip(self):
        mesh = M.make_model("robot")
        with tempfile.TemporaryDirectory() as tmp:
            path = M.write_obj(mesh, os.path.join(tmp, "r.obj"))
            text = open(path, encoding="utf-8").read()
        self.assertEqual(text.count("\nv "), mesh.nverts)
        self.assertEqual(text.count("\nf "), mesh.nfaces)
        first = mesh.faces[0]
        self.assertIn("f %d %d %d" % (first[0] + 1, first[1] + 1, first[2] + 1), text)
        # every index must be a valid 1-based vertex reference
        for line in text.splitlines():
            if line.startswith("f "):
                for idx in line[2:].split():
                    self.assertTrue(1 <= int(idx) <= mesh.nverts)

    def test_stl_binary_layout(self):
        mesh = M.make_model("cube")
        with tempfile.TemporaryDirectory() as tmp:
            path = M.write_stl(mesh, os.path.join(tmp, "c.stl"))
            raw = open(path, "rb").read()
        self.assertEqual(len(raw), 84 + 50 * mesh.nfaces)
        self.assertEqual(struct.unpack("<I", raw[80:84])[0], mesh.nfaces)
        for i in range(mesh.nfaces):
            off = 84 + 50 * i
            nx, ny, nz = struct.unpack("<3f", raw[off:off + 12])
            self.assertAlmostEqual(math.hypot(nx, ny, nz), 1.0, places=4)

    def test_stl_is_z_up(self):
        # y-up model -> STL exports with height along +z for slicers
        mesh = M.make_model("tree")
        with tempfile.TemporaryDirectory() as tmp:
            path = M.write_stl(mesh, os.path.join(tmp, "t.stl"))
            raw = open(path, "rb").read()
        zs = []
        for i in range(mesh.nfaces):
            off = 84 + 50 * i
            for v in range(3):
                _x, _y, z = struct.unpack("<3f", raw[off + 12 + 12 * v: off + 24 + 12 * v])
                zs.append(z)
        self.assertGreater(max(zs), 1.5)      # tall axis must be z
        self.assertGreaterEqual(min(zs), -1e-6)

    def test_stats_and_preview(self):
        mesh = M.make_model("gear", teeth=16)
        stats = M.mesh_stats(mesh)
        self.assertEqual(stats["name"], "gear")
        self.assertGreater(stats["faces"], 100)
        self.assertTrue(stats["watertight"])
        svg = M.mesh_to_svg(mesh, size=300)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("<polygon", svg)          # something survived culling

    def test_unknown_model(self):
        with self.assertRaises(ValueError):
            M.make_model("unobtainium")


class ServerOfflineTests(unittest.TestCase):
    """Exercises the command parser with a stubbed mouse and temp config."""

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.tmp = tempfile.TemporaryDirectory()
        server.CONFIG_FILE = os.path.join(cls.tmp.name, "config.json")
        server.CONFIG_LOCAL_FILE = os.path.join(cls.tmp.name, "config.local.json")
        server.MODELS_OUT = cls.tmp.name
        cls.mouse = FakeMouse()
        server._pyautogui = lambda: cls.mouse
        server.save_config({"provider": "openrouter", "api_key": "",
                            "model": "", "speed": 4.0, "safe_mode": True})

    def setUp(self):
        self.server._state["abort"] = False
        self.server._state["pending_artifact"] = None
        self.mouse.moves.clear()
        self.mouse.downs.clear()
        self.mouse.ups.clear()
        self.mouse.clicks.clear()

    # -- config ----------------------------------------------------------
    def test_secrets_never_land_in_the_tracked_file(self):
        self.server.save_config({"api_key": "sk-secret", "model": "x:free"})
        self.assertNotIn("sk-secret", open(self.server.CONFIG_FILE,
                                           encoding="utf-8").read())
        self.assertEqual(self.server.load_config()["api_key"], "sk-secret")
        self.assertEqual(self.server.load_config()["model"], "x:free")

    def test_candidate_models_falls_back(self):
        cfg = dict(self.server.DEFAULT_CONFIG)
        cfg["provider"] = "openrouter"
        cfg["model"] = ""
        self.assertTrue(self.server.candidate_models(cfg))
        cfg["provider"] = "zen"
        self.assertIn("big-pickle", self.server.candidate_models(cfg))

    # -- tool schema ------------------------------------------------------
    def test_tool_schema_is_valid(self):
        for tool in self.server.TOOLS:
            self.assertEqual(tool["type"], "function")
            fn = tool["function"]
            self.assertIn(fn["name"], self.server.TOOL_NAMES)
            self.assertTrue(fn["description"])
            params = fn["parameters"]
            self.assertEqual(params["type"], "object")
            for key in params.get("required", []):
                self.assertIn(key, params["properties"])

    def test_tool_enums_match_the_registries(self):
        by_name = {t["function"]["name"]: t["function"] for t in self.server.TOOLS}
        for tool, registry in (("draw", D.SHAPES), ("picture", D.PICTURES),
                               ("model3d", M.MODELS)):
            enum = by_name[tool]["parameters"]["properties"] \
                [("shape" if tool == "draw" else "name" if tool == "picture" else "kind")]["enum"]
            self.assertEqual(set(enum), set(registry), "%s enum drifted" % tool)

    def test_prompt_mentions_every_action(self):
        prompt = self.server.system_prompt()
        for name in self.server.TOOL_NAMES:
            self.assertIn(name, prompt)

    # -- offline commands -------------------------------------------------
    def test_stop_aborts(self):
        self.assertIn("Stopped", self.server.parse_command("stop"))
        self.assertTrue(self.server._state["abort"])

    def test_draw_drives_the_mouse(self):
        out = self.server.parse_command("draw a circle")
        self.assertIn("Drew a circle", out)
        self.assertEqual(len(self.mouse.downs), len(self.mouse.ups))
        self.assertGreater(len(self.mouse.moves), 20)
        # every point stayed inside the centred drawing box
        w, h = self.mouse.size()
        bw, bh = int(w * 0.46), int(h * 0.46)
        bx, by = (w - bw) // 2, (h - bh) // 2
        for (x, y) in self.mouse.moves:
            self.assertTrue(bx - 1 <= x <= bx + bw + 1, "x=%s escaped" % x)
            self.assertTrue(by - 1 <= y <= by + bh + 1, "y=%s escaped" % y)
        art = self.server._state["pending_artifact"]
        self.assertEqual(art["kind"], "draw")
        self.assertTrue(art["svg"].startswith("<svg"))

    def test_picture_shortcut(self):
        self.assertIn("Drew a house", self.server.parse_command("draw a house"))

    def test_mouse_shortcut_moves_the_pointer(self):
        self.server.parse_command("move the mouse to 640 360")
        self.assertEqual(self.mouse.pos, (640, 360))

    def test_click_shortcut(self):
        self.server.parse_command("click at 100 200")
        self.assertEqual(self.mouse.pos, (100, 200))
        self.assertEqual(self.mouse.clicks[-1], ("left", 1))
        self.server.parse_command("right click at 10 20")
        self.assertEqual(self.mouse.clicks[-1], ("right", 1))

    def test_drawing_box_default_is_centred_and_on_screen(self):
        box = self.server.drawing_box({})
        w, h = self.mouse.size()
        bw, bh = int(w * 0.46), int(h * 0.46)
        self.assertEqual(box, ((w - bw) // 2, (h - bh) // 2, bw, bh))
        self.assertTrue(0 <= box[0] and box[0] + box[2] <= w)
        self.assertTrue(0 <= box[1] and box[1] + box[3] <= h)

    # -- actions ----------------------------------------------------------
    def test_model3d_action_writes_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.server.artifact_dir = lambda: tmp
            out = self.server.run_action("model3d", {"kind": "cube", "open": False})
            self.assertIn("Built a cube", out)
            self.assertEqual(len([f for f in os.listdir(tmp) if f.endswith(".obj")]), 1)
            art = self.server._state["pending_artifact"]
            self.assertEqual(art["kind"], "model3d")
            self.assertTrue(art["path"].endswith(".obj"))
            self.assertTrue(os.path.getsize(art["path"]) > 0)

    def test_model3d_rejects_unknown(self):
        self.assertIn("cannot model", self.server.run_action("model3d",
                                                             {"kind": "unobtainium"}))

    def test_safe_mode_blocks_destructive_commands(self):
        out = self.server.run_action("run_command", {"command": "format C:"})
        self.assertIn("not running it", out)

    def test_safe_mode_allows_harmless_commands(self):
        out = self.server.run_action("run_command", {"command": "echo jarvis"})
        self.assertIn("jarvis", out)

    def test_wait_and_clipboard_do_not_crash(self):
        self.assertIn("Waited", self.server.run_action("wait", {"seconds": 0.01}))
        self.assertIsInstance(self.server.run_action("clipboard", {"text": "hi"}), str)

    def test_action_log_records(self):
        self.server._ACTION_LOG.clear()
        self.server.run_action("wait", {"seconds": 0.01})
        self.assertEqual(self.server._ACTION_LOG[-1]["name"], "wait")

    def test_legacy_dict_call_style(self):
        # old prompts called run_action({"name": ..., "arg": ...})
        self.assertIn("Opening notepad",
                      self.server.run_action({"name": "open_app", "arg": "notepad"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
