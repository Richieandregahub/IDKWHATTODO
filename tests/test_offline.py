"""Offline tests: geometry, file formats, tool schema and the command parser.

These run anywhere - no Windows, no pyautogui, no API key - because the mouse
driver is stubbed out. Run with:

    python -m unittest discover -s tests -v
"""

import io
import json
import math
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error

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
        cfg["provider"] = "gemini"
        self.assertIn("gemini-2.5-flash", self.server.candidate_models(cfg))
        cfg["provider"] = "puter"
        self.assertIn("gpt-5-nano", self.server.candidate_models(cfg))

    def test_retired_zen_config_migrates_to_puter(self):
        """An old config.json still on 'zen' must not brick the brain."""
        self.server.save_config({"provider": "zen", "model": "big-pickle"})
        cfg = self.server.load_config()
        self.assertEqual(cfg["provider"], "puter")
        self.assertEqual(self.server.cfg_provider({"provider": "zen"}), "puter")

    def test_each_provider_keeps_its_own_key(self):
        self.server.save_config({"api_key": "sk-or-secret",
                                 "gemini_api_key": "AIza-secret"})
        cfg = self.server.load_config()
        self.assertEqual(self.server.cfg_api_key(dict(cfg, provider="openrouter")),
                         "sk-or-secret")
        self.assertEqual(self.server.cfg_api_key(dict(cfg, provider="gemini")),
                         "AIza-secret")
        self.assertNotIn("AIza-secret", open(self.server.CONFIG_FILE,
                                             encoding="utf-8").read())
        self.assertEqual(self.server.key_field({"provider": "gemini"}), "gemini_api_key")
        self.assertEqual(self.server.key_field({"provider": "openrouter"}), "api_key")

    def test_puter_needs_no_key_but_openrouter_does(self):
        blank = dict(self.server.DEFAULT_CONFIG, api_key="", gemini_api_key="")
        self.assertFalse(self.server.brain_ready(dict(blank, provider="openrouter")))
        self.assertFalse(self.server.brain_ready(dict(blank, provider="gemini")))
        self.assertTrue(self.server.brain_ready(dict(blank, provider="puter")))
        self.assertFalse(self.server.needs_key({"provider": "puter"}))
        self.assertTrue(self.server.needs_key({"provider": "gemini"}))

    def test_env_gemini_key_wins(self):
        os.environ["GEMINI_API_KEY"] = "AIza-from-env"
        try:
            cfg = self.server.load_config()
            self.assertEqual(cfg["gemini_api_key"], "AIza-from-env")
            self.assertEqual(self.server.cfg_api_key(dict(cfg, provider="gemini")),
                             "AIza-from-env")
        finally:
            del os.environ["GEMINI_API_KEY"]

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


class GeminiBrainTests(unittest.TestCase):
    """Gemini speaks a different dialect - these pin the translation down."""

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.cfg = dict(server.DEFAULT_CONFIG, provider="gemini",
                       gemini_api_key="AIza-test", model="gemini-2.5-flash")

    def test_headers_use_the_google_key_header(self):
        h = self.server._brain_headers(self.cfg)
        self.assertEqual(h["x-goog-api-key"], "AIza-test")
        self.assertNotIn("Authorization", h)          # the key must not be sent twice
        self.assertNotIn("AIza-test", h.get("Authorization", ""))

    def test_openrouter_still_uses_bearer(self):
        h = self.server._brain_headers(dict(self.cfg, provider="openrouter",
                                            api_key="sk-or-1"))
        self.assertEqual(h["Authorization"], "Bearer sk-or-1")
        self.assertNotIn("x-goog-api-key", h)

    def test_payload_maps_roles_and_system_instruction(self):
        p = self.server._gemini_payload([
            {"role": "system", "content": "You are Jarvis."},
            {"role": "user", "content": "open notepad"},
            {"role": "assistant", "content": "Done."},
        ], max_tokens=200, temperature=0.3, tools=None)
        self.assertEqual(p["systemInstruction"]["parts"][0]["text"], "You are Jarvis.")
        self.assertEqual([c["role"] for c in p["contents"]], ["user", "model"])
        self.assertEqual(p["contents"][0]["parts"][0]["text"], "open notepad")
        # Flash models burn output tokens thinking, so the cap is raised
        self.assertGreaterEqual(p["generationConfig"]["maxOutputTokens"], 1024)
        self.assertEqual(p["generationConfig"]["temperature"], 0.3)
        self.assertNotIn("tools", p)

    def test_payload_never_sends_an_empty_conversation(self):
        p = self.server._gemini_payload([{"role": "system", "content": "hi"}],
                                        100, 0.2, None)
        self.assertTrue(p["contents"])
        self.assertNotIn("systemInstruction", p)

    def test_tools_become_function_declarations(self):
        p = self.server._gemini_payload(
            [{"role": "user", "content": "draw a circle"}], 200, 0.2,
            self.server.TOOLS)
        decls = p["tools"][0]["functionDeclarations"]
        self.assertEqual(len(decls), len(self.server.TOOLS))
        by_name = {d["name"]: d for d in decls}
        self.assertIn("open_app", by_name)
        self.assertEqual(by_name["open_app"]["parameters"]["properties"]["name"]["type"],
                         "string")
        self.assertEqual(by_name["draw"]["parameters"]["properties"]["shape"]["enum"],
                         sorted(self.server.drawlib.SHAPES))
        # Gemini rejects these JSON-schema extras
        blob = json.dumps(p["tools"])
        self.assertNotIn("additionalProperties", blob)
        self.assertIn("functionDeclarations", blob)

    def test_response_with_a_function_call_becomes_tool_calls(self):
        msg, err = self.server._gemini_message({
            "candidates": [{"content": {"role": "model", "parts": [
                {"text": "Opening Notepad, sir."},
                {"functionCall": {"name": "open_app", "args": {"name": "notepad"}}},
            ]}, "finishReason": "STOP"}],
            "modelVersion": "gemini-2.5-flash",
        })
        self.assertEqual(err, "")
        self.assertEqual(msg["content"], "Opening Notepad, sir.")
        self.assertEqual(msg["tool_calls"][0]["function"]["name"], "open_app")
        self.assertEqual(json.loads(msg["tool_calls"][0]["function"]["arguments"]),
                         {"name": "notepad"})

    def test_plain_text_response(self):
        msg, err = self.server._gemini_message({
            "candidates": [{"content": {"parts": [{"text": "Hello"}]},
                            "finishReason": "STOP"}]})
        self.assertEqual((msg["content"], err), ("Hello", ""))
        self.assertNotIn("tool_calls", msg)

    def test_empty_and_blocked_responses_explain_themselves(self):
        msg, err = self.server._gemini_message({"candidates": []})
        self.assertEqual(msg, {})
        self.assertTrue(err)
        msg, err = self.server._gemini_message({
            "candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]})
        self.assertIn("safety", err.lower())

    def test_call_brain_dispatches_on_provider(self):
        seen = {}

        def fake(messages, cfg, max_tokens, temperature, tools):
            seen["api"] = self.server.provider_info(cfg)["api"]
            return {"role": "assistant", "content": "ok"}, ""

        real = (self.server._call_brain_gemini, self.server._call_brain_puter,
                self.server._call_brain_openai)
        self.server._call_brain_gemini = fake
        self.server._call_brain_puter = fake
        self.server._call_brain_openai = fake
        try:
            for provider, api in (("gemini", "gemini"), ("puter", "puter"),
                                  ("openrouter", "openai"), ("custom", "openai")):
                self.server._call_brain([], dict(self.cfg, provider=provider))
                self.assertEqual(seen["api"], api, provider)
        finally:
            (self.server._call_brain_gemini, self.server._call_brain_puter,
             self.server._call_brain_openai) = real

    def test_model_ranking_prefers_free_flash(self):
        ids = ["gemini-3.1-pro-preview", "gemini-2.5-flash-lite", "gemini-3.5-flash",
               "gemini-2.0-flash"]
        ordered = sorted(ids, key=self.server._gemini_model_rank)
        self.assertEqual(ordered[0], "gemini-2.5-flash-lite")
        self.assertEqual(ordered[-1], "gemini-3.1-pro-preview")

    def test_missing_key_is_explained(self):
        msg, err = self.server._call_brain_gemini(
            [], dict(self.cfg, gemini_api_key="", api_key=""))
        self.assertIsNone(msg)
        self.assertIn("aistudio.google.com", err)

    def test_request_url_headers_and_response_round_trip(self):
        """Pin exactly what Google receives, and what comes back out."""
        calls = []

        def fake_http(url, payload=None, cfg=None, headers=None, timeout=45):
            calls.append((url, payload, headers))
            return {"candidates": [{"content": {"role": "model", "parts": [
                        {"text": "Opening Notepad, sir."},
                        {"functionCall": {"name": "open_app",
                                          "args": {"name": "notepad"}}}]},
                        "finishReason": "STOP"}]}

        real = self.server._http_json
        self.server._http_json = fake_http
        try:
            msg, err = self.server._call_brain(
                [{"role": "system", "content": "You are Jarvis."},
                 {"role": "user", "content": "open notepad"}],
                self.cfg, max_tokens=300, temperature=0.3, tools=self.server.TOOLS)
        finally:
            self.server._http_json = real

        self.assertEqual(len(calls), 1)
        url, payload, headers = calls[0]
        self.assertEqual(url, "https://generativelanguage.googleapis.com/v1beta"
                              "/models/gemini-2.5-flash:generateContent")
        self.assertEqual(headers["x-goog-api-key"], "AIza-test")
        self.assertNotIn("Authorization", headers)
        self.assertIn("functionDeclarations", payload["tools"][0])
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"],
                         "You are Jarvis.")
        self.assertEqual(err, "")
        self.assertEqual(self.server._state["last_model"], "gemini-2.5-flash")
        actions, _ = self.server._actions_from_message(msg)
        self.assertEqual(self.server._split_action(actions[0]),
                         ("open_app", {"name": "notepad"}))
        # prose next to a tool call stays quiet - the action reports itself
        self.assertEqual(self.server._speak_from_message(msg, {}), "")
        text_only = {"content": "All done, sir."}
        self.assertEqual(self.server._speak_from_message(text_only, {}), "All done, sir.")

    def test_a_dead_model_falls_through_to_the_next_one(self):
        """Free tiers 404/429 constantly - the fallback list has to work."""
        attempted = []

        def fake_http(url, payload=None, cfg=None, headers=None, timeout=45):
            attempted.append(url.rsplit("/models/", 1)[-1].split(":")[0])
            if len(attempted) == 1:
                raise urllib.error.HTTPError(
                    url, 404, "Not Found", {},
                    io.BytesIO(b'{"error":{"code":404,"message":"model not found",'
                               b'"status":"NOT_FOUND"}}'))
            return {"candidates": [{"content": {"parts": [{"text": "ready"}]},
                                    "finishReason": "STOP"}]}

        real = self.server._http_json
        self.server._http_json = fake_http
        try:
            cfg = dict(self.cfg, model="", fallbacks=[])
            msg, err = self.server._call_brain(
                [{"role": "user", "content": "hi"}], cfg, max_tokens=8)
        finally:
            self.server._http_json = real
        self.assertEqual(err, "")
        self.assertEqual(msg["content"], "ready")
        self.assertEqual(attempted[0], self.server.GEMINI_FALLBACKS[0])
        self.assertEqual(len(attempted), 2)

    def test_a_rejected_key_is_not_retried_against_every_model(self):
        def fake_http(url, payload=None, cfg=None, headers=None, timeout=45):
            raise urllib.error.HTTPError(
                url, 400, "Bad Request", {},
                io.BytesIO(b'{"error":{"code":400,"message":"API key not valid",'
                           b'"status":"INVALID_ARGUMENT"}}'))

        real = self.server._http_json
        self.server._http_json = fake_http
        try:
            msg, err = self.server._call_brain(
                [{"role": "user", "content": "hi"}], dict(self.cfg, model=""),
                max_tokens=8)
        finally:
            self.server._http_json = real
        self.assertIsNone(msg)
        self.assertIn("rejected that API key", err)
        self.assertIn("aistudio.google.com", err)


class PuterRelayTests(unittest.TestCase):
    """Puter.js is keyless: the browser tab answers jobs the server queues."""

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.cfg = dict(server.DEFAULT_CONFIG, provider="puter", model="")

    def setUp(self):
        s = self.server
        with s._PUTER["lock"]:
            s._PUTER["jobs"].clear()
            s._PUTER["queue"].clear()
            s._PUTER["models"] = []
            s._PUTER["last_seen"] = 0.0
            s._PUTER["signed_in"] = None

    def test_no_relay_gives_a_helpful_error(self):
        msg, err = self.server._call_brain_puter(
            [{"role": "user", "content": "hi"}], self.cfg)
        self.assertIsNone(msg)
        self.assertIn("dashboard", err)

    def test_job_round_trip(self):
        """Queue a job, have a 'browser' claim and answer it."""
        s = self.server
        with s._PUTER["lock"]:
            s._PUTER["last_seen"] = time.time()      # the tab is polling

        def browser():
            job = s.puter_claim(timeout=5)
            assert job, "no job was handed to the browser"
            assert job["messages"][0]["content"] == "open paint"
            assert "gpt-5-nano" in job["models"]
            s.puter_complete(job["id"], {
                "ok": True, "model": "gpt-5-nano",
                "message": {"role": "assistant", "content": "On it.",
                            "tool_calls": [{"id": "c1", "type": "function",
                                            "function": {"name": "open_app",
                                                         "arguments": '{"name":"paint"}'}}]},
            })

        t = threading.Thread(target=browser, daemon=True)
        t.start()
        msg, err = s._call_brain_puter(
            [{"role": "user", "content": "open paint"}], self.cfg,
            max_tokens=200, temperature=0.3, tools=s.TOOLS)
        t.join(timeout=10)
        self.assertEqual(err, "")
        self.assertEqual(msg["content"], "On it.")
        self.assertEqual(msg["tool_calls"][0]["function"]["name"], "open_app")
        self.assertEqual(s._state["last_model"], "puter:gpt-5-nano")

    def test_browser_errors_are_reported_back(self):
        s = self.server
        with s._PUTER["lock"]:
            s._PUTER["last_seen"] = time.time()

        def browser():
            job = s.puter_claim(timeout=5)
            s.puter_complete(job["id"], {"ok": False, "error": "model not found"})

        t = threading.Thread(target=browser, daemon=True)
        t.start()
        msg, err = s._call_brain_puter([{"role": "user", "content": "hi"}], self.cfg)
        t.join(timeout=10)
        self.assertIsNone(msg)
        self.assertIn("model not found", err)

    def test_sign_in_errors_are_actionable(self):
        s = self.server
        with s._PUTER["lock"]:
            s._PUTER["last_seen"] = time.time()

        def browser():
            job = s.puter_claim(timeout=5)
            s.puter_complete(job["id"], {"ok": False, "error": "authentication required"})

        t = threading.Thread(target=browser, daemon=True)
        t.start()
        msg, err = s._call_brain_puter([{"role": "user", "content": "hi"}], self.cfg)
        t.join(timeout=10)
        self.assertIsNone(msg)
        self.assertIn("CONNECT PUTER", err)

    def test_expired_job_does_not_hang_forever(self):
        s = self.server
        s.PUTER_JOB_TTL = 0.4
        try:
            with s._PUTER["lock"]:
                s._PUTER["last_seen"] = time.time()
            started = time.time()
            msg, err = s._call_brain_puter([{"role": "user", "content": "hi"}], self.cfg)
            self.assertIsNone(msg)
            self.assertLess(time.time() - started, 5.0)
            self.assertTrue(err)
        finally:
            s.PUTER_JOB_TTL = 90.0

    def test_models_pushed_by_the_page_are_deduped_and_sorted(self):
        models = self.server.puter_set_models([
            {"id": "deepseek-chat", "name": "DeepSeek"},
            {"id": "gpt-5-nano", "name": "GPT-5 Nano", "max_input_tokens": 400000},
            {"id": "gpt-5-nano"},
            "claude-sonnet-4",
            {"id": "puter/foo"},                    # internal, not a chat model
            {"nonsense": True},
        ], signed_in=True)
        ids = [m["id"] for m in models]
        self.assertEqual(ids.count("gpt-5-nano"), 1)
        self.assertEqual(ids[0], "gpt-5-nano")      # known-good free model first
        self.assertNotIn("puter/foo", ids)
        self.assertIn("claude-sonnet-4", ids)
        self.assertEqual(models[0]["context"], 400000)
        self.assertTrue(all(m["free"] for m in models))
        st = self.server.puter_status()
        self.assertTrue(st["signed_in"])
        self.assertEqual(st["models"], len(ids))

    def test_status_reports_a_dead_relay(self):
        st = self.server.puter_status()
        self.assertFalse(st["relay"])
        self.assertFalse(self.server.puter_alive())

    def test_brain_ready_without_any_key(self):
        self.assertTrue(self.server.brain_ready(self.cfg))
        self.assertTrue(self.server.verify_key.__doc__)

    def test_a_closed_tab_falls_back_to_a_saved_key(self):
        """No relay, but a key in the drawer -> Jarvis keeps working."""
        s = self.server
        routed = []

        def fake_openai(messages, cfg, max_tokens=400, temperature=0.4, tools=None):
            routed.append(("openai", cfg["provider"]))
            return {"role": "assistant", "content": "via key"}, ""

        def fake_gemini(messages, cfg, max_tokens=400, temperature=0.4, tools=None):
            routed.append(("gemini", cfg["provider"]))
            return {"role": "assistant", "content": "via gemini"}, ""

        real = (s._call_brain_openai, s._call_brain_gemini)
        s._call_brain_openai, s._call_brain_gemini = fake_openai, fake_gemini
        try:
            # no relay, no key -> the honest error
            msg, err = s._call_brain([{"role": "user", "content": "hi"}], self.cfg)
            self.assertIsNone(msg)
            self.assertIn("relay is not connected", err)

            # an OpenRouter-shaped key takes over
            msg, err = s._call_brain([{"role": "user", "content": "hi"}],
                                     dict(self.cfg, api_key="sk-or-v1-abc"))
            self.assertEqual(msg["content"], "via key")
            self.assertEqual(routed[-1], ("openai", "openrouter"))

            # some other endpoint's key goes through the custom path
            msg, err = s._call_brain([{"role": "user", "content": "hi"}],
                                     dict(self.cfg, api_key="abc123"))
            self.assertEqual(routed[-1], ("openai", "custom"))

            # only a Gemini key saved -> Gemini takes over
            msg, err = s._call_brain([{"role": "user", "content": "hi"}],
                                     dict(self.cfg, gemini_api_key="AIza-x"))
            self.assertEqual(msg["content"], "via gemini")
            self.assertEqual(routed[-1], ("gemini", "gemini"))
        finally:
            s._call_brain_openai, s._call_brain_gemini = real


class ActionDispatchTests(unittest.TestCase):
    """The tool name and a tool's own "name" parameter must not collide.

    Gemini answers with functionCall parts and Puter.js with tool_calls, so
    this path is now the common case, not an edge case.
    """

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server

    def test_native_tool_call_keeps_the_name_argument(self):
        actions, _ = self.server._actions_from_message({
            "content": "",
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "open_app",
                                         "arguments": '{"name": "notepad"}'}}]})
        self.assertEqual(len(actions), 1)
        self.assertEqual(self.server._split_action(actions[0]),
                         ("open_app", {"name": "notepad"}))

    def test_native_tool_call_without_a_name_argument(self):
        actions, _ = self.server._actions_from_message({
            "tool_calls": [{"function": {"name": "screenshot", "arguments": "{}"}}]})
        self.assertEqual(self.server._split_action(actions[0]), ("screenshot", {}))

    def test_json_actions_use_the_tool_key(self):
        actions, obj = self.server._actions_from_message({"content": json.dumps({
            "speak": "On it.",
            "actions": [{"tool": "open_app", "name": "paint"},
                        {"tool": "wait", "seconds": 3},
                        {"tool": "draw", "shape": "circle"}]})})
        self.assertEqual(obj["speak"], "On it.")
        self.assertEqual([self.server._split_action(a) for a in actions],
                         [("open_app", {"name": "paint"}),
                          ("wait", {"seconds": 3}),
                          ("draw", {"shape": "circle"})])

    def test_legacy_name_discriminator_still_works(self):
        self.assertEqual(self.server._split_action({"name": "draw", "shape": "star"}),
                         ("draw", {"shape": "star"}))
        self.assertEqual(self.server._split_action({"name": "open_app", "arg": "notepad"}),
                         ("open_app", {"arg": "notepad"}))

    def test_run_action_opens_the_app_it_was_told_to(self):
        """Regression: this used to run open_app("") and search the web."""
        out = self.server.run_action({"tool": "open_app", "name": "notepad"})
        self.assertIn("notepad", out.lower())
        self.assertNotIn("searched the web", out)

    def test_prompt_no_longer_teaches_a_duplicate_key(self):
        prompt = self.server.SYSTEM_PROMPT
        self.assertIn('"tool": "<action name>"', prompt)
        self.assertNotIn('{"name":"open_app","name":"paint"}', prompt)
        # and the JSON it teaches must actually parse
        example = '[{"tool":"open_app","name":"paint"},{"tool":"wait","seconds":3},' \
                  '{"tool":"draw","shape":"circle"}]'
        parsed = json.loads(example)
        self.assertEqual([self.server._split_action(a)[0] for a in parsed],
                         ["open_app", "wait", "draw"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
