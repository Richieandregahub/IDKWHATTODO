"""Tests for the app profiles, chat driving and conversation engine.

Windows APIs are replaced with fakes (window provider, mouse driver,
clipboard and brain), so these run anywhere.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import apps                       # noqa: E402
import converse                   # noqa: E402

from test_offline import FakeMouse  # noqa: E402


FAKE_WINDOWS = [
    {"hwnd": 1, "title": "WhatsApp - 04:32", "rect": (0, 0, 1200, 800)},
    {"hwnd": 2, "title": "John Smith - WhatsApp", "rect": (40, 40, 1000, 700)},
    {"hwnd": 3, "title": "Discord | #general", "rect": (10, 10, 1400, 900)},
    {"hwnd": 4, "title": "Zoom Meeting", "rect": (0, 0, 1600, 900)},
    {"hwnd": 5, "title": "Meet - abc-defg-hij", "rect": (0, 0, 1500, 850)},
    {"hwnd": 6, "title": "Untitled - Notepad", "rect": (0, 0, 800, 600)},
]


class AppProfileTests(unittest.TestCase):
    def test_match_app(self):
        self.assertEqual(apps.match_app("WhatsApp - 04:32"), "whatsapp")
        self.assertEqual(apps.match_app("Discord | #general"), "discord")
        self.assertEqual(apps.match_app("Zoom Meeting"), "zoom")
        self.assertEqual(apps.match_app("Meet - abc-defg-hij"), "meet")
        self.assertEqual(apps.match_app("Microsoft Teams"), "teams")
        self.assertIsNone(apps.match_app("Untitled - Notepad"))
        self.assertIsNone(apps.match_app(""))

    def test_detect_calls_flags_likely_calls(self):
        calls = apps.detect_calls(FAKE_WINDOWS)
        titles = [c["title"] for c in calls]
        self.assertIn("Zoom Meeting", titles)
        self.assertIn("Meet - abc-defg-hij", titles)
        # an open app with no call hint is still offered, but as low confidence
        by_title = {c["title"]: c for c in calls}
        self.assertEqual(by_title["Discord | #general"]["confidence"], "low")
        # notepad is not a messaging app at all, so it must not appear
        self.assertNotIn("Untitled - Notepad", titles)

    def test_detect_calls_ranks_confidence_first(self):
        calls = apps.detect_calls(FAKE_WINDOWS)
        order = {"high": 0, "medium": 1, "low": 2}
        ranks = [order.get(c["confidence"], 3) for c in calls]
        self.assertEqual(ranks, sorted(ranks))

    def test_no_windows_no_calls(self):
        self.assertEqual(apps.detect_calls([]), [])
        self.assertEqual(apps.detect_calls(None), [])


class ChatDriveTests(unittest.TestCase):
    """Drives read_chat / send_chat_text with a fake mouse + clipboard."""

    def setUp(self):
        self.mouse = FakeMouse()
        apps.set_driver(self.mouse)
        apps.set_windows_provider(lambda: FAKE_WINDOWS)
        # clipboard with a queue: each read returns the next value, so we can
        # model "user had text -> app copies transcript"
        self._clip = []
        self._real_get, self._real_set = apps.clipboard_get, apps.clipboard_set
        apps.clipboard_get = lambda: self._clip.pop(0) if self._clip else ""
        apps.clipboard_set = self._set

    def _set(self, text):
        self._clip.append(str(text))
        return True

    def _prime(self, existing, transcript):
        """Next two clipboard reads return ``existing`` then ``transcript``."""
        self._clip = [existing, transcript]

    def tearDown(self):
        apps.clipboard_get, apps.clipboard_set = self._real_get, self._real_set
        apps.set_driver(None)
        apps.set_windows_provider(None)

    def test_read_chat_returns_the_transcript(self):
        transcript = "John: are you there?\nMe: yes\nJohn: can you send the file?"
        self._prime("", transcript)
        out = apps.read_chat(app="whatsapp")
        self.assertTrue(out["text"])
        self.assertEqual(out["app"], "whatsapp")
        # select-all + copy really happened
        keys = [k for k in self.mouse.keys]
        self.assertIn(("hotkey", ("ctrl", "a")), keys)
        self.assertIn(("hotkey", ("ctrl", "c")), keys)

    def test_read_chat_restores_the_clipboard(self):
        self._prime("something important", "chat text")
        apps.read_chat(app="discord")
        # the last thing written back to the clipboard is what was there before
        self.assertEqual(self._clip[-1], "something important")

    def test_read_chat_without_a_window(self):
        apps.set_windows_provider(lambda: [])
        out = apps.read_chat(app="whatsapp")
        self.assertFalse(out["ok"])
        self.assertIn("no chat window", out["error"])

    def test_send_chat_text_types_and_enters(self):
        out = apps.send_chat_text("hello there", app="whatsapp")
        self.assertTrue(out["ok"])
        self.assertIn(("write", "hello there"), self.mouse.keys)
        self.assertIn(("press", "enter"), self.mouse.keys)

    def test_send_chat_refuses_empty(self):
        self.assertFalse(apps.send_chat_text("", app="whatsapp")["ok"])


class EchoTests(unittest.TestCase):
    def test_identical_text_is_an_echo(self):
        self.assertTrue(converse.looks_like_echo("I can help with that",
                                                 "I can help with that", 1.0))
    def test_stale_reply_is_not_an_echo(self):
        self.assertFalse(converse.looks_like_echo("I can help with that",
                                                  "I can help with that", 99.0))
    def test_different_text_is_not_an_echo(self):
        self.assertFalse(converse.looks_like_echo("what time works for you",
                                                  "I can help with that", 1.0))
    def test_containment_counts_as_echo(self):
        self.assertTrue(converse.looks_like_echo("Sure, I can send that over to you now",
                                                 "Sure, I can send that over to you now please",
                                                 1.0))
    def test_empty_is_not_an_echo(self):
        self.assertFalse(converse.looks_like_echo("", "hello", 1.0))
        self.assertFalse(converse.looks_like_echo("hello", "", 1.0))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.spoken, self.sent = [], []
        self.calls = []

        def brain(system, history, prompt):
            self.calls.append((system, list(history), prompt))
            return "Yes, %s." % prompt.split()[0]

        self.engine = converse.ConversationEngine(
            brain=brain,
            speak=self.spoken.append,
            send=self.sent.append,
            owner="Richie")

    def test_call_session_speaks_the_reply(self):
        self.engine.start("call", app="discord", who="Sam")
        reply = self.engine.hear("are you there")
        self.assertIn("Yes," , reply)
        self.assertEqual(self.spoken, [reply])
        self.assertEqual(self.sent, [])
        st = self.engine.status()
        self.assertTrue(st["active"])
        self.assertEqual(st["app"], "discord")
        self.assertEqual(st["turns"], 1)

    def test_chat_session_sends_instead_of_speaking(self):
        self.engine.start("chat", app="whatsapp", who="Dad")
        reply = self.engine.hear("where are you")
        self.assertEqual(self.sent, [reply])
        self.assertEqual(self.spoken, [])

    def test_brain_receives_history_and_owner(self):
        self.engine.start("call", app="discord", who="Sam")
        self.engine.hear("hello")
        system, history, prompt = self.calls[0]
        self.assertIn("Richie", system)
        self.assertIn("Sam", system)
        self.assertEqual(history, [("them", "hello")])

    def test_echo_does_not_produce_a_reply(self):
        self.engine.start("call")
        first = self.engine.hear("can you hear me")
        second = self.engine.hear(first)          # loopback picked up our own voice
        self.assertTrue(first)
        self.assertEqual(second, "")
        self.assertEqual(len(self.spoken), 1)

    def test_muted_records_but_stays_silent(self):
        self.engine.start("call")
        self.engine.session.muted = True
        reply = self.engine.hear("hello?")
        self.assertTrue(reply)
        self.assertEqual(self.spoken, [])
        self.assertEqual(self.engine.session.entries[-1]["text"], reply)

    def test_manual_say(self):
        self.engine.start("call")
        self.engine.say("Richie will call you back.")
        self.assertEqual(self.spoken, ["Richie will call you back."])

    def test_turn_limit_stops_the_session(self):
        eng = converse.ConversationEngine(
            brain=lambda s, h, p: "reply %d" % len(h),
            speak=lambda t: None, send=lambda t: None,
            owner="Richie", max_turns=2)
        eng.start("call")
        eng.hear("one")
        eng.hear("two")
        self.assertTrue(eng.active)
        eng.hear("three")
        self.assertFalse(eng.active)   # limit hit -> session ended itself

    def test_stop_returns_the_session(self):
        self.engine.start("call")
        self.engine.hear("hi")
        old = self.engine.stop()
        self.assertEqual(old.turns, 1)
        self.assertFalse(self.engine.active)
        self.assertEqual(self.engine.hear("anyone there"), "")

    def test_transcript_is_recorded(self):
        self.engine.start("call", who="Sam")
        self.engine.hear("hi")
        t = self.engine.session.transcript()
        self.assertEqual([e["who"] for e in t], ["them", "jarvis"])
        self.assertEqual(t[0]["text"], "hi")


class ServerSessionTests(unittest.TestCase):
    """start_session / stop_session against the real server with fakes."""

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        import tempfile
        cls.tmp = tempfile.TemporaryDirectory()
        server.CONFIG_FILE = os.path.join(cls.tmp.name, "config.json")
        server.CONFIG_LOCAL_FILE = os.path.join(cls.tmp.name, "config.local.json")
        cls.mouse = FakeMouse()
        server._pyautogui = lambda: cls.mouse

        # a fake brain that echoes what it was told
        cls.brain_calls = []

        def fake_brain(messages, cfg, max_tokens=100, temperature=0.5, tools=None):
            cls.brain_calls.append(messages)
            prompt = messages[-1]["content"]
            return {"content": "I heard: %s" % prompt}, ""
        cls.real_brain = server._call_brain
        server._call_brain = fake_brain

        cls.spoken = []
        cls.real_guarded = server._talk_aloud_guarded
        server._talk_aloud_guarded = lambda text: cls.spoken.append(text)

        apps.set_driver(cls.mouse)
        apps.set_windows_provider(lambda: FAKE_WINDOWS)

    @classmethod
    def tearDownClass(cls):
        cls.server._call_brain = cls.real_brain
        cls.server._talk_aloud_guarded = cls.real_guarded
        apps.set_driver(None)
        apps.set_windows_provider(None)

    def setUp(self):
        self.server.stop_session()
        self.brain_calls.clear()
        self.spoken.clear()
        self.server._state["abort"] = False

    def test_start_and_stop(self):
        st, msg = self.server.start_session("call", app="discord")
        self.assertEqual(st["app"], "discord")
        self.assertIn("talk to them", msg)
        self.assertTrue(self.server.session_state()["active"])
        out = self.server.stop_session()
        self.assertTrue(out["stopped"])
        self.assertFalse(self.server.session_state()["active"])

    def test_session_replies_through_the_brain(self):
        self.server.start_session("call", app="discord", who="Sam")
        reply = self.server.engine().hear("are you there")
        self.assertIn("I heard", reply)
        self.assertIn(reply, self.spoken)
        # the system prompt is call-flavoured and mentions the owner + caller
        system = self.brain_calls[0][0]["content"]
        self.assertIn("Richie", system)
        self.assertIn("Sam", system)
        self.assertIn("call", system.lower())

    def test_guess_who_from_title(self):
        g = self.server._guess_who
        self.assertEqual(g("John Smith - WhatsApp"), "John Smith")
        self.assertEqual(g("WhatsApp - 04:32"), "")
        self.assertEqual(g("Zoom Meeting"), "")

    def test_tail_after(self):
        tail = self.server._tail_after
        self.assertEqual(tail("abc", "ab"), "c")
        self.assertEqual(tail("abc", ""), "abc")
        self.assertEqual(tail("hello world", "hello world"), "")
        # transcript scrolled: falls back to the last lines
        self.assertIn("third", tail("first\nsecond\nthird", "zzz"))

    def test_call_tool_roundtrip(self):
        out = self.server.run_action("call", {"op": "start", "app": "discord"})
        self.assertIn("I am on it", out)
        self.assertTrue(self.server.session_state()["active"])
        self.server.run_action("call", {"op": "say", "text": "be right there"})
        self.assertIn("be right there", self.spoken)
        out = self.server.run_action("call", {"op": "stop"})
        self.assertIn("stopped talking", out)
        self.assertFalse(self.server.session_state()["active"])

    def test_call_status_when_idle(self):
        self.assertEqual(self.server.run_action("call", {"op": "status"}),
                         "No call session.")

    def test_parse_command_starts_a_call(self):
        out = self.server.parse_command("call mode on discord")
        self.assertIn("I am on it", out)
        self.assertTrue(self.server.session_state()["active"])
        self.assertEqual(self.server.parse_command("stop talking"),
                         "Understood, I am out of the conversation.")
        self.assertFalse(self.server.session_state()["active"])

    def test_parse_command_talk_to_them(self):
        self.assertIn("I am on it", self.server.parse_command("talk to them"))
        self.server.stop_session()

    def test_stop_still_aborts_everything(self):
        self.server.parse_command("stop")
        self.assertTrue(self.server._state["abort"])

    def test_audio_list_without_portaudio(self):
        info = self.server.audio_devices()
        self.assertIn("devices", info)
        self.assertTrue(isinstance(info.get("error", ""), str))


if __name__ == "__main__":
    unittest.main(verbosity=2)
