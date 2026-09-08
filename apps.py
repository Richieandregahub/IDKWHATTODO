"""App profiles, window helpers and clipboard chat I/O for Richie Jarvis.

Everything the core needs to know about *which app it is talking through*:

* window title patterns for WhatsApp / Discord / Telegram / Zoom / Meet / Teams
* best-effort "is a call live?" detection
* clipboard read/write (ctypes, no extra packages)
* read-a-conversation / send-a-message driving via the mouse + keyboard

The Windows-only pieces are behind injectable providers
(:func:`set_driver`, :func:`set_windows_provider`) so the whole module can be
tested on any machine with fakes.
"""

from __future__ import annotations

import ctypes
import os
import re
import time
from typing import Callable, Dict, List, Optional, Sequence

__all__ = [
    "APP_PROFILES", "profile", "match_app", "detect_calls", "CALL_HINTS",
    "set_driver", "driver", "set_windows_provider", "windows",
    "find_window", "focus_window", "window_rect",
    "clipboard_get", "clipboard_set", "clipboard_swap",
    "read_chat", "send_chat_text", "active_app",
]

IS_WINDOWS = os.name == "nt"

# --------------------------------------------------------------------------
# app profiles
# --------------------------------------------------------------------------

APP_PROFILES: Dict[str, dict] = {
    "whatsapp": {
        "label": "WhatsApp",
        "titles": ["whatsapp"],
        "procs": ["whatsapp.exe", "applicationframehost.exe"],
        "open": "whatsapp:",
        # WhatsApp shows a duration-style title or these words while calling
        "call": ["incoming call", "ongoing call", "ringing", "calling",
                 "voice call", "video call", "panggilan"],
        "chat_click": 0.35,     # where to click to reach the message list
        "input_click": 0.94,    # where the compose box usually is
    },
    "discord": {
        "label": "Discord",
        "titles": ["discord"],
        "procs": ["discord.exe"],
        "open": "discord",
        "call": ["voice", "🔊"],
        "chat_click": 0.45,
        "input_click": 0.93,
    },
    "telegram": {
        "label": "Telegram",
        "titles": ["telegram"],
        "procs": ["telegram.exe"],
        "open": "telegram",
        "call": ["call", "voice chat"],
        "chat_click": 0.40,
        "input_click": 0.94,
    },
    "zoom": {
        "label": "Zoom",
        "titles": ["zoom"],
        "procs": ["zoom.exe"],
        "open": "zoommtg:",
        "call": ["meeting", "zoom meeting"],
        "chat_click": 0.50,
        "input_click": 0.90,
    },
    "meet": {
        "label": "Google Meet",
        "titles": ["meet", "google meet"],
        "procs": ["chrome.exe", "msedge.exe"],
        "open": "https://meet.google.com",
        "call": ["meet", "meet - "],
        "chat_click": 0.50,
        "input_click": 0.88,
    },
    "teams": {
        "label": "Microsoft Teams",
        "titles": ["microsoft teams", "teams"],
        "procs": ["teams.exe", "ms-teams.exe"],
        "open": "msteams:",
        "call": ["meeting", "call"],
        "chat_click": 0.45,
        "input_click": 0.93,
    },
    "messenger": {
        "label": "Messenger",
        "titles": ["messenger"],
        "procs": ["messenger.exe"],
        "open": "https://www.messenger.com",
        "call": ["call", "video"],
        "chat_click": 0.45,
        "input_click": 0.93,
    },
}

# generic hints, applied to any window when no profile matched
CALL_HINTS = (
    "incoming call", "ongoing call", "call in progress", "in a call",
    "video call", "voice call", "voice connected", "zoom meeting",
    "meet -", "ringing", "panggilan", "panggilan masuk",
)


def profile(app: str) -> dict:
    """Profile for an app key, or ``{}`` if unknown."""
    return APP_PROFILES.get(str(app or "").strip().lower(), {})


def match_app(text: str) -> Optional[str]:
    """Best-effort app key from a window title or a spoken name."""
    t = str(text or "").strip().lower()
    if not t:
        return None
    for key, prof in APP_PROFILES.items():
        if key in t:
            return key
        for title in prof.get("titles", []):
            if title in t:
                return key
    return None


def detect_calls(windows_list: Sequence[dict]) -> List[dict]:
    """Guess which open windows are live calls.

    Titles are all we have without platform-specific APIs, so this is a
    heuristic: a call hint in the title is strong evidence, an app that is
    simply open is weak evidence. The UI shows the confidence so you can
    always pick manually.
    """
    found: List[dict] = []
    for w in windows_list or []:
        title = (w.get("title") or "").strip()
        if not title:
            continue
        low = title.lower()
        app = match_app(low) or "unknown"
        prof = profile(app)
        reasons = []
        for hint in prof.get("call", []) or []:
            if hint and hint in low:
                reasons.append("title matches %r" % hint)
        for hint in CALL_HINTS:
            if hint in low:
                r = "title matches %r" % hint
                if r not in reasons:
                    reasons.append(r)
        if re.search(r"\b\d{1,2}:\d{2}(:\d{2})?\b", title) and app in ("whatsapp", "discord", "teams"):
            reasons.append("looks like a call timer")
        if reasons:
            found.append({
                "app": app,
                "title": title,
                "confidence": "high" if len(reasons) > 1 else "medium",
                "reasons": reasons[:3],
                "rect": w.get("rect"),
            })
        elif prof:
            found.append({
                "app": app,
                "title": title,
                "confidence": "low",
                "reasons": ["%s is open" % prof.get("label", app)],
                "rect": w.get("rect"),
            })
    order = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda f: order.get(f["confidence"], 3))
    return found


# --------------------------------------------------------------------------
# injectable providers (tests swap these out)
# --------------------------------------------------------------------------

_DRIVER = None
_WINDOWS_PROVIDER = None


def set_driver(obj) -> None:
    global _DRIVER
    _DRIVER = obj


def driver():
    if _DRIVER is not None:
        return _DRIVER
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.01
    return pyautogui


def set_windows_provider(fn: Optional[Callable[[], List[dict]]]) -> None:
    global _WINDOWS_PROVIDER
    _WINDOWS_PROVIDER = fn


def windows() -> List[dict]:
    """Visible windows as ``[{'hwnd','title','rect'}]``. Empty off Windows."""
    if _WINDOWS_PROVIDER is not None:
        return _WINDOWS_PROVIDER()
    return _enum_windows_win32()


def _enum_windows_win32() -> List[dict]:
    if not IS_WINDOWS:
        return []
    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    out: List[dict] = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                r = RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                out.append({"hwnd": hwnd, "title": buf.value,
                            "rect": (r.left, r.top, max(0, r.right - r.left),
                                     max(0, r.bottom - r.top))})
        return True

    try:
        user32.EnumWindows(proto(cb), 0)
    except Exception:
        return []
    return out


def find_window(title: str):
    """First window whose title contains ``title`` (case-insensitive)."""
    needle = str(title or "").strip().lower()
    if not needle:
        return None
    for w in windows():
        if needle in (w.get("title") or "").lower():
            return w
    return None


def focus_window(title_or_win) -> bool:
    """Bring a window to the front. Returns True on Windows."""
    if not IS_WINDOWS:
        return False
    win = title_or_win if isinstance(title_or_win, dict) else find_window(title_or_win)
    if not win:
        return False
    try:
        user32 = ctypes.windll.user32
        hwnd = win.get("hwnd")
        user32.ShowWindow(hwnd, 9)           # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def window_rect(title_or_win):
    win = title_or_win if isinstance(title_or_win, dict) else find_window(title_or_win)
    return (win or {}).get("rect")


def active_app(windows_list=None):
    """Best guess at which messaging app is in front."""
    for w in (windows_list if windows_list is not None else windows()):
        key = match_app((w.get("title") or "").lower())
        if key:
            return key
    return None


# --------------------------------------------------------------------------
# clipboard (ctypes, no dependencies)
# --------------------------------------------------------------------------

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def clipboard_get() -> str:
    """Read text from the clipboard. Returns ``''`` off Windows."""
    if not IS_WINDOWS:
        return ""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    try:
        if not user32.OpenClipboard(0):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    except Exception:
        return ""
    finally:
        try:
            user32.CloseClipboard()
        except Exception:
            pass


def clipboard_set(text: str) -> bool:
    """Replace the clipboard contents with ``text``."""
    if not IS_WINDOWS:
        return False
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    data = str(text or "")
    try:
        if not user32.OpenClipboard(0):
            return False
        user32.EmptyClipboard()
        # +1 for the terminating null
        buf_size = (len(data) + 1) * ctypes.sizeof(ctypes.c_wchar)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, buf_size)
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return False
        try:
            ctypes.memmove(ptr, data, (len(data)) * ctypes.sizeof(ctypes.c_wchar))
        finally:
            kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, handle))
    except Exception:
        return False
    finally:
        try:
            user32.CloseClipboard()
        except Exception:
            pass


def clipboard_swap(new_text: str):
    """Context manager: sets the clipboard, restores it afterwards."""
    class _Swap:
        def __init__(self):
            self.old = clipboard_get()

        def __enter__(self):
            if new_text is not None:
                clipboard_set(new_text)
            return new_text

        def __exit__(self, *exc):
            if self.old:
                clipboard_set(self.old)
            return False
    return _Swap()


# --------------------------------------------------------------------------
# driving a chat window
# --------------------------------------------------------------------------

def _click_fraction(rect, frac_y: float):
    x, y, w, h = rect
    pag = driver()
    pag.click(int(x + w * 0.5), int(y + h * frac_y))


def read_chat(app: str = None, win: dict = None) -> dict:
    """Scrape the visible conversation via select-all + copy.

    Works in WhatsApp, Discord, Telegram, Messenger and similar because all
    of them put the transcript into the clipboard on Ctrl+A / Ctrl+C. The
    previous clipboard contents are restored afterwards.
    """
    win = win or find_window((profile(app).get("titles") or [app])[0] if app else "")
    if not win:
        # fall back to whatever app is in front
        cand = [w for w in windows() if match_app((w.get("title") or "").lower())]
        win = cand[0] if cand else None
    if not win:
        return {"ok": False, "app": app or "", "text": "",
                "error": "no chat window in front"}
    key = match_app((win.get("title") or "").lower()) or (app or "unknown")
    prof = profile(key) or profile(app or "")

    pag = driver()
    focus_window(win)
    time.sleep(0.35)
    rect = win.get("rect")
    if not rect:
        return {"ok": False, "app": key, "text": "", "error": "no window rectangle"}

    previous = clipboard_get()
    try:
        _click_fraction(rect, prof.get("chat_click", 0.45))
        time.sleep(0.15)
        pag.hotkey("ctrl", "a")
        time.sleep(0.12)
        pag.hotkey("ctrl", "c")
        time.sleep(0.30)
        text = clipboard_get()
    finally:
        if previous:
            clipboard_set(previous)
    # put the caret back in the compose box so a reply can be typed
    try:
        _click_fraction(rect, prof.get("input_click", 0.93))
    except Exception:
        pass
    return {"ok": bool(text), "app": key, "title": win.get("title", ""),
            "text": text or "", "error": "" if text else "clipboard came back empty"}


def send_chat_text(text: str, app: str = None, win: dict = None) -> dict:
    """Type ``text`` into the focused chat and press Enter."""
    if not text:
        return {"ok": False, "app": app or "", "error": "nothing to send"}
    win = win or find_window((profile(app).get("titles") or [app])[0] if app else "")
    key = match_app((win or {}).get("title", "").lower()) or (app or "unknown")
    if win:
        focus_window(win)
        time.sleep(0.3)
        prof = profile(key)
        rect = win.get("rect")
        if rect and prof:
            try:
                _click_fraction(rect, prof.get("input_click", 0.93))
                time.sleep(0.12)
            except Exception:
                pass
    pag = driver()
    pag.write(str(text), interval=0.01)
    time.sleep(0.15)
    pag.press("enter")
    return {"ok": True, "app": key, "sent": str(text)}
