"""Live conversation engine - "Jarvis, talk to them for me".

Holds a session for whatever conversation is happening (a voice/video call in
WhatsApp, Discord, Teams, Zoom, Meet, or a text chat) and turns anything the
other person says into a short reply from the brain, spoken or typed back.

The heavy lifting is injected: :class:`ConversationEngine` takes a ``brain``
callable, a ``speak`` callable and a ``send`` callable, so it can be driven
by the real LLM/TTS in the app and by fakes in the tests.

One subtlety worth knowing about: when Jarvis speaks through the speakers,
the loopback capture hears its own voice. :func:`looks_like_echo` stops that
from turning into an infinite loop of the AI answering itself.
"""

from __future__ import annotations

import difflib
import re
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "Session", "ConversationEngine", "looks_like_echo",
    "call_system", "chat_system", "normalise",
]

MAX_TURNS = 60          # hard stop, so a stuck loop can never run forever
ECHO_WINDOW = 12.0      # seconds
ECHO_RATIO = 0.82


def normalise(text: str) -> str:
    """Lowercase, strip punctuation - used for echo detection."""
    t = str(text or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def looks_like_echo(text: str, last_reply: str, since: float = 0.0,
                    window: float = ECHO_WINDOW) -> bool:
    """True when ``text`` is really Jarvis hearing itself speak."""
    if not text or not last_reply:
        return False
    if since and since > window:
        return False
    a, b = normalise(text), normalise(last_reply)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) > 18 and (a in b or b in a):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= ECHO_RATIO


def call_system(owner: str = "the boss", who: str = "the caller",
                medium: str = "phone", extra: str = "") -> str:
    return (
        "You are Richie Jarvis, the AI assistant of {owner}, and you are "
        "speaking on {owner}'s behalf in a live {medium} call with {who}.\n"
        "Reply with ONE or two short, natural, spoken sentences. Plain speech "
        "only - no markdown, no bullet points, no emoji, no JSON, no actions.\n"
        "Be warm and brief; this is read out loud, so write how people talk.\n"
        "Never invent facts about {owner}, their schedule or their files. "
        "If you do not know something, say you will have {owner} confirm and "
        "get back to them.\n"
        "If they ask for {owner} himself, say {owner} is not available right "
        "now and offer to take a message.{extra}"
    ).format(owner=owner, who=who or "the caller", medium=medium or "phone", extra=extra)


def chat_system(owner: str = "the boss", who: str = "them",
                app: str = "chat", extra: str = "") -> str:
    return (
        "You are Richie Jarvis, the AI assistant of {owner}, replying in a "
        "{app} conversation with {who}.\n"
        "Write one short, casual message (1-2 sentences) as if you were "
        "{owner}'s assistant typing. No markdown, no lists, no emoji spam, "
        "no JSON, no actions.\n"
        "Never invent facts about {owner}. If asked something you cannot "
        "know, say you will check with {owner} and get back to them.{extra}"
    ).format(owner=owner, who=who or "them", app=app or "chat", extra=extra)


class Session:
    """One live conversation (a call or a chat) with its transcript."""

    def __init__(self, kind: str = "call", app: str = "", who: str = "",
                 medium: str = ""):
        self.kind = str(kind or "call")
        self.app = str(app or "")
        self.who = str(who or "")
        self.medium = str(medium or ("call" if self.kind == "call" else "chat"))
        self.started = time.time()
        self.turns = 0
        self.muted = False
        self.auto = True          # reply on its own, or only when asked
        self.entries: List[dict] = []
        self.last_reply = ""
        self.last_reply_at = 0.0

    # -- bookkeeping ------------------------------------------------------
    def add(self, who: str, text: str, kind: str = "") -> dict:
        entry = {
            "t": round(time.time() - self.started, 1),
            "time": time.strftime("%H:%M:%S"),
            "who": who,
            "text": str(text or ""),
            "kind": kind or self.kind,
        }
        self.entries.append(entry)
        if len(self.entries) > 200:
            del self.entries[:-200]
        return entry

    @property
    def age(self) -> float:
        return time.time() - self.started

    def transcript(self, limit: int = 60) -> List[dict]:
        return list(self.entries[-limit:])

    def history(self, limit: int = 16) -> List[Tuple[str, str]]:
        """Recent turns as ``(speaker, text)`` for the brain prompt."""
        out = []
        for e in self.entries[-limit:]:
            out.append((e["who"], e["text"]))
        return out

    def status(self) -> dict:
        return {
            "kind": self.kind, "app": self.app, "who": self.who,
            "medium": self.medium, "muted": self.muted, "auto": self.auto,
            "turns": self.turns, "age": round(self.age, 1),
            "entries": len(self.entries),
        }


class ConversationEngine:
    """Turns incoming speech/text into replies for the current session."""

    def __init__(self,
                 brain: Optional[Callable[[str, List[Tuple[str, str]]], str]] = None,
                 speak: Optional[Callable[[str], None]] = None,
                 send: Optional[Callable[[str], None]] = None,
                 owner: str = "the boss",
                 max_turns: int = MAX_TURNS,
                 log: Optional[Callable[[str], None]] = None):
        self.brain = brain or (lambda system, history, prompt: "")
        self.speak = speak or (lambda text: None)
        self.send = send or (lambda text: None)
        self.owner = owner
        self.max_turns = max_turns
        self.log = log or (lambda msg: None)
        self.session: Optional[Session] = None

    # -- lifecycle --------------------------------------------------------
    @property
    def active(self) -> bool:
        return self.session is not None

    def start(self, kind: str = "call", app: str = "", who: str = "",
              medium: str = "") -> Session:
        self.session = Session(kind=kind, app=app, who=who, medium=medium)
        self.log("session started: %s/%s" % (kind, app or "?"))
        return self.session

    def stop(self) -> Optional[Session]:
        s, self.session = self.session, None
        if s:
            self.log("session stopped after %d turns" % s.turns)
        return s

    def status(self) -> dict:
        if not self.session:
            return {"active": False}
        out = self.session.status()
        out["active"] = True
        return out

    # -- talking ----------------------------------------------------------
    def _system(self) -> str:
        s = self.session
        if not s:
            return ""
        if s.kind == "chat":
            return chat_system(self.owner, s.who or "them", s.app or "chat")
        return call_system(self.owner, s.who or "the caller", s.medium or "call")

    def hear(self, text: str, who: str = "them") -> str:
        """The other party said ``text``. Returns Jarvis's reply (or '')."""
        s = self.session
        text = str(text or "").strip()
        if not s or not text:
            return ""
        if looks_like_echo(text, s.last_reply, time.time() - s.last_reply_at):
            self.log("ignored echo of our own reply")
            return ""
        s.add(who or "them", text)
        if not s.auto:
            return ""
        if s.turns >= self.max_turns:
            s.add("jarvis", "(turn limit reached - stopping)", kind="system")
            self.stop()
            return ""
        reply = ""
        try:
            reply = (self.brain(self._system(), s.history(), text) or "").strip()
        except Exception as e:                     # pragma: no cover
            self.log("brain failed: %s" % e)
        if not reply:
            return ""
        s.turns += 1
        s.last_reply = reply
        s.last_reply_at = time.time()
        s.add("jarvis", reply)
        if s.muted:
            return reply
        try:
            if s.kind == "chat":
                self.send(reply)
            else:
                self.speak(reply)
        except Exception as e:                     # pragma: no cover
            self.log("delivery failed: %s" % e)
        return reply

    def say(self, text: str) -> str:
        """Push something into the conversation without being asked."""
        s = self.session
        text = str(text or "").strip()
        if not s or not text:
            return ""
        s.turns += 1
        s.last_reply = text
        s.last_reply_at = time.time()
        s.add("jarvis", text, kind="manual")
        if s.muted:
            return text
        try:
            if s.kind == "chat":
                self.send(text)
            else:
                self.speak(text)
        except Exception:
            pass
        return text
