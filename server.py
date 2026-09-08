import ctypes
import json
import math
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("JARVIS_PORT", "8765"))
# Jarvis drives your mouse, so by default it only listens on this machine.
# Set JARVIS_HOST=0.0.0.0 if you deliberately want LAN access.
HOST = os.environ.get("JARVIS_HOST", "127.0.0.1")
VERSION = "2.0"

_state = {"last_spoken": "", "abort": False, "last_artifact": None,
          "pending_artifact": None, "last_model": "", "tools_ok": True}
_ACTION_LOG: list = []
_ACTION_LOG_LOCK = threading.Lock()

try:
    import draw as drawlib
except Exception as _e:            # pragma: no cover - only if files are missing
    drawlib = None
    print("[jarvis] draw.py unavailable:", _e)
try:
    import model3d as m3d
except Exception as _e:            # pragma: no cover
    m3d = None
    print("[jarvis] model3d.py unavailable:", _e)
try:
    import apps as appslib
except Exception as _e:            # pragma: no cover
    appslib = None
    print("[jarvis] apps.py unavailable:", _e)
try:
    import converse as converselib
except Exception as _e:            # pragma: no cover
    converselib = None
    print("[jarvis] converse.py unavailable:", _e)


def _pyautogui():
    import pyautogui
    # FAILSAFE: slam the mouse into a screen corner to kill any action.
    # It is on by default now that a language model is moving the pointer.
    pyautogui.FAILSAFE = bool(load_config().get("failsafe", True))
    pyautogui.PAUSE = 0.01
    return pyautogui


def _psutil():
    import psutil
    return psutil


APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "ms paint": "mspaint.exe",
    "paint 3d": "ms-paint:",
    "3d viewer": "ms-3dviewer:",
    "screenshot tool": "ms-screenclip:",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "task manager": "taskmgr.exe",
    "settings": "ms-settings:",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "firefox": "firefox",
    "spotify": "spotify:",
    "whatsapp": "whatsapp:",
    "discord": "discord",
    "steam": "steam",
    "telegram": "telegram",
    "vs code": "code",
    "code": "code",
    "visual studio code": "code",
    "notepad++": "notepad++",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "blender": "blender",
    "obs": "obs64",
}

# --------------------------------------------------------------------------
# providers / configuration
# --------------------------------------------------------------------------

PROVIDERS = {
    "openrouter": {
        "label": "OpenRouter (free models)",
        "base_url": "https://openrouter.ai/api/v1",
        "models_url": "https://openrouter.ai/api/v1/models",
        "model": "openrouter/free",
        "key_label": "OpenRouter API key",
        "key_hint": "sk-or-v1-… from openrouter.ai/keys",
        "key_url": "https://openrouter.ai/keys",
        "key_env": ("JARVIS_API_KEY", "OPENROUTER_API_KEY"),
        "api": "openai",
    },
    "gemini": {
        "label": "Google Gemini (free tier)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "model": "gemini-2.5-flash",
        "key_label": "Gemini API key",
        "key_hint": "AIza… from aistudio.google.com/apikey",
        "key_url": "https://aistudio.google.com/apikey",
        "key_env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "api": "gemini",
    },
    "puter": {
        # Puter.js runs in the browser ("user pays" model): no key, no bill.
        # The page acts as a relay, so the dashboard tab must stay open.
        "label": "Puter.js — free, no key",
        "base_url": "",
        "models_url": "",
        "model": "gpt-5-nano",
        "key_label": "",
        "key_hint": "no key needed — the browser talks to Puter.js for you",
        "key_url": "https://developer.puter.com/",
        "key_env": (),
        "api": "puter",
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)",
        "base_url": "",
        "models_url": "",
        "model": "",
        "key_label": "API key",
        "key_hint": "whatever your endpoint expects",
        "key_url": "",
        "key_env": ("JARVIS_API_KEY",),
        "api": "openai",
    },
}

# Providers that were dropped but may still sit in somebody's config.json.
# They are rewritten on load instead of silently breaking the brain.
LEGACY_PROVIDERS = {"zen": "puter", "opencode": "puter"}

# The out-of-the-box brain: free, keyless, and driven by the dashboard tab.
DEFAULT_PROVIDER = "puter"

# Used when the provider's live model list cannot be fetched. Free model IDs
# rotate constantly, so the UI always prefers the live list (GET /models).
FALLBACK_MODELS = [
    "qwen/qwen3-coder:free",
    "deepseek/deepseek-v4-flash:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "stepfun/step-3.5-flash:free",
    "z-ai/glm-4.5-air:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-120b:free",
]
# Gemini free tier is Flash-only these days (Pro needs billing), so the list
# stays on Flash / Flash-Lite, which all support function calling.
GEMINI_FALLBACKS = [
    "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite", "gemini-2.0-flash",
]
# Puter.js picks a vendor per model; these are the ones that are reliably free
# and accept OpenAI-style `tools`.
PUTER_FALLBACKS = [
    "gpt-5-nano", "gpt-5.6-luna", "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct", "deepseek-chat",
]
FALLBACK_POOLS = {
    "openrouter": FALLBACK_MODELS,
    "gemini": GEMINI_FALLBACKS,
    "puter": PUTER_FALLBACKS,
    "custom": FALLBACK_MODELS,
}

CONTACTS_FILE = os.path.join(BASE_DIR, "contacts.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CONFIG_LOCAL_FILE = os.path.join(BASE_DIR, "config.local.json")

# Secrets live in config.local.json (git-ignored) so a key can never be
# committed by accident. config.json only ever holds harmless settings.
# One slot per provider, so switching OpenRouter <-> Gemini keeps both keys.
SECRET_KEYS = ("api_key", "gemini_api_key")

DEFAULT_CONFIG = {
    "provider": DEFAULT_PROVIDER,
    "api_key": "",
    "gemini_api_key": "",   # Google AI Studio key, used when provider == gemini
    "base_url": "",          # empty -> use the provider default
    "model": "",             # empty -> use the provider default
    "fallbacks": [],
    "listen": False,
    "secretary": False,
    "listen_threshold": 350,
    "answer_pos": [0, 0],
    "safe_mode": True,       # ask before destructive shell commands
    "failsafe": True,        # corner-of-screen mouse abort
    "speed": 1.0,            # mouse speed multiplier
    "max_actions": 6,        # cap on chained actions per command
    "voice_device": "",      # empty = default speakers; set a cable to be heard in calls
    "auto_converse": True,   # keep talking after secretary mode answers a call
    "chat_poll": 6.0,        # seconds between chat checks in chat mode
}


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(_read_json_file(CONFIG_FILE))
    cfg.update(_read_json_file(CONFIG_LOCAL_FILE))
    provider = str(cfg.get("provider") or "").strip().lower()
    if provider in LEGACY_PROVIDERS:      # e.g. the retired OpenCode Zen
        provider = LEGACY_PROVIDERS[provider]
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    cfg["provider"] = provider
    # env vars win, so keys can be injected without touching disk
    for name in ("JARVIS_API_KEY", "OPENROUTER_API_KEY", "OPENCODE_API_KEY"):
        if os.environ.get(name):
            cfg["api_key"] = os.environ[name]
            break
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(name):
            cfg["gemini_api_key"] = os.environ[name]
            break
    return cfg


def save_config(cfg):
    """Write settings to config.json and secrets to config.local.json."""
    public = _read_json_file(CONFIG_FILE)
    secret = _read_json_file(CONFIG_LOCAL_FILE)
    for k, v in cfg.items():
        if v is None:
            continue
        if k in SECRET_KEYS:
            secret[k] = v
            public.pop(k, None)      # never keep a key in the tracked file
        else:
            public[k] = v
    for path, data in ((CONFIG_FILE, public), (CONFIG_LOCAL_FILE, secret)):
        tmp = {}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("[jarvis] could not write %s: %s" % (path, e))
        del tmp
    return True


# --------------------------------------------------------------------------
# provider helpers
# --------------------------------------------------------------------------

def provider_info(cfg):
    return PROVIDERS.get(cfg_provider(cfg), PROVIDERS[DEFAULT_PROVIDER])


def cfg_provider(cfg):
    """The active provider id, with retired names mapped onto their successor."""
    p = str((cfg or {}).get("provider") or DEFAULT_PROVIDER).strip().lower()
    p = LEGACY_PROVIDERS.get(p, p)
    return p if p in PROVIDERS else DEFAULT_PROVIDER


def key_field(cfg):
    """Which secret slot this provider reads/writes."""
    return "gemini_api_key" if cfg_provider(cfg) == "gemini" else "api_key"


def cfg_api_key(cfg):
    """The key for the *active* provider (Gemini has its own slot)."""
    cfg = cfg or {}
    field = key_field(cfg)
    return str(cfg.get(field) or "").strip()


def needs_key(cfg):
    """Puter.js is keyless - the browser is the credential."""
    return cfg_provider(cfg) != "puter"


def brain_ready(cfg):
    """True when a brain call has any chance of succeeding."""
    if not needs_key(cfg):
        return True
    return bool(cfg_api_key(cfg))


def mask_key(key):
    key = str(key or "")
    if not key:
        return ""
    return (key[:6] + "..." + key[-4:]) if len(key) > 12 else "set"


def cfg_base_url(cfg):
    return (cfg.get("base_url") or "").strip() or \
        PROVIDERS.get(cfg_provider(cfg), {}).get("base_url", "")


def cfg_model(cfg):
    return (cfg.get("model") or "").strip() or \
        PROVIDERS.get(cfg_provider(cfg), {}).get("model", "")


def candidate_models(cfg):
    """Primary model first, then the provider's other free models.

    Free model IDs rotate and rate-limit constantly, so the provider pool is
    always queued behind the configured model - one dead model should cost a
    retry, not the whole command. ``custom`` endpoints get no pool: their model
    list is whatever the user typed.
    """
    provider = cfg_provider(cfg)
    models = []
    for m in [cfg_model(cfg)] + list(cfg.get("fallbacks") or []):
        m = str(m or "").strip()
        if m and m not in models:
            models.append(m)
    if provider != "custom":
        for m in FALLBACK_POOLS.get(provider, FALLBACK_MODELS):
            if m not in models:
                models.append(m)
    return models


def _screen_size():
    try:
        w, h = _pyautogui().size()
        return int(w), int(h)
    except Exception:
        return 0, 0


# --------------------------------------------------------------------------
# the action catalogue
#
# Defined once as OpenAI function-calling schemas. The same list is sent as
# native `tools` when the model supports it, and is rendered into the system
# prompt for models that can only reply with JSON - so both paths stay in sync.
# --------------------------------------------------------------------------

def _enum(values):
    return {"type": "string", "enum": sorted(values)}


def _tool(name, description, props, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


def _shape_enums():
    shapes = sorted(drawlib.SHAPES) if drawlib else ["circle", "rect", "star"]
    pictures = sorted(drawlib.PICTURES) if drawlib else ["house", "robot", "cat"]
    models = sorted(m3d.MODELS) if m3d else ["cube", "sphere"]
    return shapes, pictures, models


def build_tools():
    shapes, pictures, models = _shape_enums()
    return [
        _tool("open_app", "Open or launch a desktop app or Windows app.",
              {"name": {"type": "string", "description":
                        "app name, e.g. notepad, calculator, paint, chrome, spotify, vs code, blender"}},
              ["name"]),
        _tool("open_url", "Open a website in the default browser.",
              {"url": {"type": "string", "description": "full url or bare domain like example.com"}},
              ["url"]),
        _tool("search_web", "Search the web.",
              {"query": {"type": "string", "description": "what to search for"},
               "engine": _enum(["google", "youtube", "wikipedia"])},
              ["query"]),
        _tool("run_command", "Run a Windows shell command.",
              {"command": {"type": "string", "description": "shell command, e.g. 'dir' or 'echo hi'"}},
              ["command"]),
        _tool("mouse", "Move, click, drag or scroll the real mouse pointer.",
              {"op": _enum(["move", "click", "double_click", "right_click", "middle_click",
                            "drag", "scroll", "position"]),
               "x": {"type": "integer", "description": "target x in screen pixels"},
               "y": {"type": "integer", "description": "target y in screen pixels"},
               "x2": {"type": "integer", "description": "drag end x"},
               "y2": {"type": "integer", "description": "drag end y"},
               "clicks": {"type": "integer", "description": "number of clicks (default 1)"},
               "duration": {"type": "number", "description": "seconds the movement should take (default 0.4)"}},
              ["op"]),
        _tool("draw", "Draw a geometric shape by dragging the mouse in the active paint app.",
              {"shape": _enum(shapes),
               "x": {"type": "integer", "description": "left of the drawing box in pixels"},
               "y": {"type": "integer", "description": "top of the drawing box in pixels"},
               "w": {"type": "integer", "description": "box width in pixels"},
               "h": {"type": "integer", "description": "box height in pixels"},
               "sides": {"type": "integer", "description": "polygon sides (default 5)"},
               "points": {"type": "integer", "description": "star points (default 5)"},
               "inner": {"type": "number", "description": "star inner ratio 0-1 (default 0.42)"},
               "turns": {"type": "number", "description": "spiral turns (default 3)"},
               "cycles": {"type": "number", "description": "sine wave cycles (default 2)"},
               "rot": {"type": "number", "description": "rotation in degrees"},
               "sweep": {"type": "number", "description": "arc sweep in degrees (default 360)"},
               "stroke": {"type": "number", "description": "preview stroke width, unused"}}),
        _tool("picture", "Draw a composed picture (a little line drawing) with the mouse.",
              {"name": _enum(pictures),
               "x": {"type": "integer", "description": "left of the drawing box in pixels"},
               "y": {"type": "integer", "description": "top of the drawing box in pixels"},
               "w": {"type": "integer", "description": "box width in pixels"},
               "h": {"type": "integer", "description": "box height in pixels"}}),
        _tool("model3d", "Generate a real 3D model file (OBJ/STL) and open it on the desktop.",
              {"kind": _enum(models),
               "fmt": _enum(["obj", "stl", "both"]),
               "w": {"type": "number", "description": "width for box-like models"},
               "h": {"type": "number", "description": "height"},
               "d": {"type": "number", "description": "depth for box-like models"},
               "r": {"type": "number", "description": "radius for round models"},
               "R": {"type": "number", "description": "ring radius for torus/donut"},
               "base": {"type": "number", "description": "pyramid base width"},
               "sides": {"type": "number", "description": "number of sides/facets"},
               "teeth": {"type": "number", "description": "gear tooth count"},
               "open": {"type": "boolean", "description": "open the file when done (default true)"}}),
        _tool("keyboard", "Type text, press keys or press a hotkey combination.",
              {"op": _enum(["type", "press", "hotkey"]),
               "text": {"type": "string", "description": "text to type (op=type)"},
               "key": {"type": "string", "description": "single key (op=press), e.g. enter, esc, tab, space, volumeup"},
               "keys": {"type": "array", "items": {"type": "string"},
                        "description": "hotkey parts (op=hotkey), e.g. ['ctrl','c']"},
               "times": {"type": "integer", "description": "repeat count for op=press (default 1)"}},
              ["op"]),
        _tool("window", "Find, move, resize, focus, minimize, maximize or close a window.",
              {"op": _enum(["list", "active", "move", "resize", "focus", "close",
                            "minimize", "maximize"]),
               "title": {"type": "string", "description": "part of the window title to match"},
               "x": {"type": "integer", "description": "new left position"},
               "y": {"type": "integer", "description": "new top position"},
               "w": {"type": "integer", "description": "new width"},
               "h": {"type": "integer", "description": "new height"}},
              ["op"]),
        _tool("whatsapp", "Send a WhatsApp message or start a WhatsApp call.",
              {"op": _enum(["message", "call", "video_call"]),
               "contact": {"type": "string", "description": "contact name or number with country code"},
               "message": {"type": "string", "description": "message text (op=message)"}},
              ["op", "contact"]),
        _tool("clipboard", "Copy text to the Windows clipboard.",
              {"text": {"type": "string", "description": "text to copy"}}, ["text"]),
        _tool("wait", "Pause before the next action (lets apps finish opening).",
              {"seconds": {"type": "number", "description": "seconds to wait (max 10)"}}, ["seconds"]),
        _tool("call", "Start or stop talking for the user inside a live voice/video call "
                      "(WhatsApp, Discord, Teams, Zoom, Meet). Jarvis listens to the call "
                      "and answers out loud.",
              {"op": _enum(["start", "stop", "status", "say", "mute", "unmute"]),
               "app": _enum(["whatsapp", "discord", "telegram", "zoom", "meet",
                             "teams", "messenger"]),
               "who": {"type": "string", "description": "who is on the call, if known"},
               "text": {"type": "string", "description": "line to say (op=say)"}},
              ["op"]),
        _tool("chat", "Read or reply in the chat window that is open right now.",
              {"op": _enum(["read", "send", "auto"]),
               "app": _enum(["whatsapp", "discord", "telegram", "zoom", "meet",
                             "teams", "messenger"]),
               "text": {"type": "string", "description": "message to send (op=send)"},
               "on": {"type": "boolean", "description": "true to keep replying (op=auto)"}},
              ["op"]),
        _tool("audio", "List playback devices or pick the one Jarvis speaks through.",
              {"op": _enum(["list", "use"]),
               "device": {"type": "string",
                          "description": "device name, e.g. 'CABLE Input' (op=use)"}},
              ["op"]),
        _tool("screenshot", "Take a screenshot and save it to the desktop.", {}),
        _tool("system_info", "Report the time, date, CPU, memory and battery.", {}),
        _tool("say_aloud", "Speak a sentence through the PC speakers.",
              {"text": {"type": "string", "description": "what to say"}}, ["text"]),
    ]


TOOLS = build_tools()
TOOL_NAMES = [t["function"]["name"] for t in TOOLS]


def _tool_help_lines():
    lines = []
    for t in TOOLS:
        fn = t["function"]
        props = fn.get("parameters", {}).get("properties", {}) or {}
        required = set(fn.get("parameters", {}).get("required") or [])
        bits = []
        for k, v in props.items():
            desc = v.get("description", "")
            if v.get("enum"):
                desc = (desc + " one of: " + ", ".join(str(x) for x in v["enum"])).strip(" ")
            bits.append(k + ("" if k in required else "?") + ("=" + desc if desc else ""))
        lines.append("- %s(%s): %s" % (fn["name"], ", ".join(bits), fn.get("description", "")))
    return "\n".join(lines)


SYSTEM_PROMPT = """You are Richie Jarvis, a witty AI butler that really controls the Windows PC of your boss, {owner}.

Reply with ONE JSON object and nothing else - no markdown, no code fences:
{{"speak": "<1-2 short sentences to say out loud>", "actions": [{{"tool": "<action name>", ...its parameters}}]}}

Actions you can run:
{tools}

How to behave:
- Use "actions": [] when you are only chatting or answering a question.
- "tool" always names the action; every other key is one of that action's parameters
  (so opening Paint is {{"tool":"open_app","name":"paint"}} - "name" is the app, not the action).
- Chain actions when a job needs steps, for example drawing a circle:
  [{{"tool":"open_app","name":"paint"}},{{"tool":"wait","seconds":3}},{{"tool":"draw","shape":"circle"}}]
- For 3D models use model3d and pick a kind from the list; the file is written to the desktop and opened.
- {screen}
- Coordinates are screen pixels with 0,0 at the top-left. Pick sensible values.
- Never invent action names or parameters that are not listed.
- Keep "speak" short and in the same language the user spoke.{extra}"""


def system_prompt():
    w, h = _screen_size()
    screen = ("The screen is %dx%d pixels." % (w, h)) if w and h else \
        "Assume a 1920x1080 screen."
    extra = ""
    if load_config().get("safe_mode", True):
        extra = ("\n- Destructive shell commands are blocked, so do not try to delete or "
                 "format anything.")
    return SYSTEM_PROMPT.format(owner=contact_owner(), tools=_tool_help_lines(),
                                screen=screen, extra=extra)


# --------------------------------------------------------------------------
# talking to the brain
# --------------------------------------------------------------------------

TOOL_UNSUPPORTED = "__tools_unsupported__"


def _http_json(url, payload=None, cfg=None, headers=None, timeout=45):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _brain_headers(cfg):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jarvis-local/%s" % VERSION,
    }
    provider = cfg_provider(cfg)
    if provider == "gemini":
        # Gemini wants its own header; it also accepts ?key=, but a header
        # keeps the secret out of URLs (and therefore out of every log).
        headers["x-goog-api-key"] = cfg_api_key(cfg)
        return headers
    headers["Authorization"] = "Bearer %s" % cfg_api_key(cfg)
    if provider == "openrouter":
        # optional, but gets the app attributed on the OpenRouter leaderboards
        headers["HTTP-Referer"] = "http://localhost:%d" % PORT
        headers["X-OpenRouter-Title"] = "Richie Jarvis"
    return headers


def _call_brain(messages, cfg, max_tokens=400, temperature=0.4, tools=None):
    """Send a chat request. Returns ``(message_dict, error)``.

    ``message_dict`` is an OpenAI-shaped assistant message, so ``tool_calls``
    survive regardless of which provider actually produced it. Each backend
    retries 5xx once per model, then walks the fallback model list.
    """
    api = provider_info(cfg).get("api", "openai")
    if api == "gemini":
        return _call_brain_gemini(messages, cfg, max_tokens, temperature, tools)
    if api == "puter":
        msg, err = _call_brain_puter(messages, cfg, max_tokens, temperature, tools)
        if msg is not None or err == TOOL_UNSUPPORTED:
            return msg, err
        # The browser relay is the free brain, but if the tab is closed and a
        # real key is saved, keep working instead of going dumb.
        if str(cfg.get("api_key") or "").strip():
            key = cfg["api_key"].strip()
            alt = dict(cfg, provider="openrouter" if key.startswith("sk-or") else "custom")
            print("[jarvis] puter.js unavailable (%s) - falling back to the saved key"
                  % str(err or "")[:60])
            return _call_brain_openai(messages, alt, max_tokens, temperature, tools)
        if str(cfg.get("gemini_api_key") or "").strip():
            print("[jarvis] puter.js unavailable (%s) - falling back to the Gemini key"
                  % str(err or "")[:60])
            return _call_brain_gemini(messages, dict(cfg, provider="gemini"),
                                      max_tokens, temperature, tools)
        return None, err
    return _call_brain_openai(messages, cfg, max_tokens, temperature, tools)


def _call_brain_openai(messages, cfg, max_tokens=400, temperature=0.4, tools=None):
    """OpenAI-compatible ``/chat/completions`` (OpenRouter, custom endpoints)."""
    if not cfg_api_key(cfg):
        return None, "no api key configured"
    url = cfg_base_url(cfg).rstrip("/") + "/chat/completions"
    if not url.startswith("http"):
        return None, "no API base url configured"
    headers = _brain_headers(cfg)
    last_err = "unknown error"

    for model in candidate_models(cfg):
        for attempt in range(2):
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            try:
                data = _http_json(url, payload, cfg, headers)
            except urllib.error.HTTPError as e:
                try:
                    detail = json.loads(e.read().decode("utf-8", "replace")) \
                        .get("error", {}).get("message", "")
                except Exception:
                    detail = ""
                if e.code in (401, 403):
                    return None, ("the API key was rejected - open the gear icon and paste a valid key")
                if e.code == 402:
                    return None, ("out of credits on this provider - free models only need "
                                  "credits to lift the daily request cap")
                if e.code == 429:
                    last_err = ("rate limited (free tier is 50 requests/day, or 1,000/day "
                                "after buying $10 of credits)")
                    time.sleep(1.0)
                    continue
                if e.code in (400, 404) and tools and ("tool" in (detail or "").lower()):
                    return None, TOOL_UNSUPPORTED
                last_err = "model %s error %s: %s" % (model, e.code, (detail or "")[:120])
                if e.code >= 500:
                    time.sleep(0.6)
                    continue
                break
            except Exception as e:
                last_err = str(e)
                time.sleep(0.6)
                continue

            try:
                msg = data["choices"][0]["message"] or {}
            except Exception:
                last_err = "unexpected response from %s" % model
                break
            content = msg.get("content")
            if not content and not msg.get("tool_calls"):
                last_err = "model %s returned an empty reply" % model
                break
            _state["last_model"] = str(data.get("model") or model)
            return msg, ""

        print("[jarvis] model '%s' failed (%s) - trying the next one..." % (model, last_err))
    return None, last_err


# --------------------------------------------------------------------------
# Google Gemini
#
# Gemini is *not* OpenAI-compatible: the request is ``contents`` + parts and
# the reply comes back as ``candidates[0].content.parts``. These two helpers
# translate in both directions so the rest of Jarvis never notices.
# --------------------------------------------------------------------------

# Gemini rejects JSON-schema keys it does not implement, and chokes on empty
# ``properties`` - the OpenAI schemas above use both.
_GEMINI_SCHEMA_DROP = ("additionalProperties", "$schema", "default", "examples")


def _gemini_schema(schema):
    """Trim an OpenAI parameter schema down to what Gemini accepts."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    out = {}
    for k, v in schema.items():
        if k in _GEMINI_SCHEMA_DROP:
            continue
        if k in ("properties", "items") and isinstance(v, dict):
            if k == "properties":
                out["properties"] = {n: _gemini_schema(s) for n, s in v.items()}
            else:
                out["items"] = _gemini_schema(v)
        else:
            out[k] = v
    if out.get("type") == "object" and not out.get("properties"):
        out.pop("properties", None)   # Gemini rejects an empty properties map
    return out


def _gemini_tools(tools):
    decls = []
    for t in tools or []:
        fn = (t or {}).get("function") or {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        decls.append({
            "name": name,
            "description": str(fn.get("description") or ""),
            "parameters": _gemini_schema(fn.get("parameters") or {}),
        })
    return [{"functionDeclarations": decls}] if decls else None


def _gemini_payload(messages, max_tokens, temperature, tools):
    """OpenAI messages -> Gemini generateContent body."""
    system, contents = [], []
    for m in messages or []:
        role = str((m or {}).get("role") or "user")
        text = (m or {}).get("content")
        if isinstance(text, list):      # multimodal parts we do not send yet
            text = " ".join(str(p.get("text") or "") for p in text
                            if isinstance(p, dict))
        text = str(text or "")
        if role == "system":
            system.append(text)
        elif role in ("assistant", "model"):
            contents.append({"role": "model", "parts": [{"text": text}]})
        else:
            contents.append({"role": "user", "parts": [{"text": text}]})
    if not contents:
        # Gemini needs at least one turn; fold the system text into a user one.
        contents = [{"role": "user",
                     "parts": [{"text": "\n\n".join(system) if system else " "}]}]
        system = []
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": float(temperature),
            # Flash models spend output tokens *thinking*, so a 360-token cap
            # can come back empty. Give them room and trim on our side.
            "maxOutputTokens": max(1024, int(max_tokens) * 4),
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system)}]}
    decls = _gemini_tools(tools)
    if decls:
        payload["tools"] = decls
    return payload


def _gemini_message(data):
    """Gemini response -> OpenAI-shaped assistant message."""
    cands = (data or {}).get("candidates") or []
    if not cands:
        return {}, (data or {}).get("promptFeedback", {}).get("blockReason", "") \
            or "no candidates returned"
    cand = cands[0] or {}
    parts = ((cand.get("content") or {}).get("parts")) or []
    text, tool_calls = [], []
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("text"):
            text.append(str(p["text"]))
        fc = p.get("functionCall") or p.get("function_call")
        if isinstance(fc, dict) and fc.get("name"):
            args = fc.get("args")
            if args is None:
                args = fc.get("arguments") or {}
            tool_calls.append({
                "id": str(fc.get("id") or "call_%d" % len(tool_calls)),
                "type": "function",
                "function": {"name": str(fc["name"]),
                             "arguments": json.dumps(args if isinstance(args, dict) else {})},
            })
    msg = {"role": "assistant", "content": "".join(text)}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    finish = str(cand.get("finishReason") or "")
    if finish in ("MAX_TOKENS",) and not msg["content"] and not tool_calls:
        return msg, "the reply was cut off by the token limit"
    if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST") and not msg["content"]:
        return msg, "blocked by Google's safety filters (%s)" % finish
    return msg, ""


def _call_brain_gemini(messages, cfg, max_tokens=400, temperature=0.4, tools=None):
    key = cfg_api_key(cfg)
    if not key:
        return None, ("no Gemini API key configured - get a free one at "
                      "aistudio.google.com/apikey")
    base = cfg_base_url(cfg).rstrip("/")
    if not base.startswith("http"):
        base = PROVIDERS["gemini"]["base_url"]
    headers = _brain_headers(cfg)
    last_err = "unknown error"

    for model in candidate_models(cfg):
        model = model.replace("models/", "")
        url = "%s/models/%s:generateContent" % (base, urllib.parse.quote(model))
        payload = _gemini_payload(messages, max_tokens, temperature, tools)
        for attempt in range(2):
            try:
                data = _http_json(url, payload, cfg, headers, timeout=60)
            except urllib.error.HTTPError as e:
                detail, status = "", ""
                try:
                    body = json.loads(e.read().decode("utf-8", "replace"))
                    err = body.get("error") or {}
                    detail = str(err.get("message") or "")
                    status = str(err.get("status") or "")
                except Exception:
                    pass
                if e.code in (400, 403) and status in ("INVALID_ARGUMENT",) \
                        and tools and "function" in detail.lower():
                    return None, TOOL_UNSUPPORTED
                if e.code in (400, 403) and ("api key" in detail.lower()
                                             or status in ("PERMISSION_DENIED", "FAILED_PRECONDITION")
                                             and "key" in detail.lower()):
                    return None, ("Gemini rejected that API key - open the gear icon and "
                                  "paste a key from aistudio.google.com/apikey")
                if e.code == 429:
                    last_err = "Gemini free tier rate limit reached (%s)" % (detail[:80] or "429")
                    time.sleep(1.0)
                    break               # try the next model, not the same one
                if e.code == 404:
                    last_err = "model %s is not available on this key" % model
                    break
                last_err = "gemini %s error %s: %s" % (model, e.code, (detail or status)[:120])
                if e.code >= 500:
                    time.sleep(0.6)
                    continue
                break
            except Exception as e:
                last_err = str(e)
                time.sleep(0.6)
                continue

            msg, why = _gemini_message(data)
            if not msg.get("content") and not msg.get("tool_calls"):
                last_err = why or "model %s returned an empty reply" % model
                break
            _state["last_model"] = str(model)
            return msg, ""

        print("[jarvis] gemini model '%s' failed (%s) - trying the next one..." % (model, last_err))
    return None, last_err


# --------------------------------------------------------------------------
# Puter.js - a free brain with no API key
#
# Puter.js only exists in the browser, so the dashboard page acts as a relay:
# the server queues a job, the page picks it up with ``puter.ai.chat()``, and
# posts the answer back. The whole agent loop (tools, actions, chat) still
# runs in Python - only the HTTP hop to the model moves to the browser.
# --------------------------------------------------------------------------

PUTER_JOB_TTL = 90.0          # seconds a queued job waits for a browser
PUTER_STALE_AFTER = 45.0      # relay silence older than this = "page closed"

_PUTER = {
    "lock": threading.Lock(),
    "jobs": {},          # id -> job dict
    "queue": [],         # ids in arrival order
    "models": [],        # pushed up by the page from puter.ai.listModels()
    "models_at": 0.0,
    "last_seen": 0.0,    # last poll from a browser
    "version": "",
    "signed_in": None,
    "runs": 0,
    "failures": 0,
}


def puter_alive(max_age=PUTER_STALE_AFTER):
    with _PUTER["lock"]:
        return (time.time() - _PUTER["last_seen"]) < max_age if _PUTER["last_seen"] else False


def puter_status():
    with _PUTER["lock"]:
        seen = _PUTER["last_seen"]
        return {
            "provider": "puter",
            "relay": bool(seen and (time.time() - seen) < PUTER_STALE_AFTER),
            "last_seen": round(time.time() - seen, 1) if seen else None,
            "pending": len(_PUTER["queue"]),
            "models": len(_PUTER["models"]),
            "signed_in": _PUTER["signed_in"],
            "runs": _PUTER["runs"],
            "failures": _PUTER["failures"],
        }


def _puter_prune(now):
    """Drop jobs nobody collected (caller holds the lock)."""
    for jid in list(_PUTER["queue"]):
        job = _PUTER["jobs"].get(jid)
        if job and (now - job.get("created", now)) > PUTER_JOB_TTL:
            _PUTER["queue"].remove(jid)
            job["result"] = {"ok": False, "error": "no Puter.js relay answered in time"}
            job["done"] = True


def puter_claim(timeout=0.0):
    """Hand the oldest queued job to a browser. Blocks up to ``timeout``."""
    deadline = time.time() + max(0.0, float(timeout or 0.0))
    while True:
        with _PUTER["lock"]:
            _PUTER["last_seen"] = time.time()
            _puter_prune(time.time())
            while _PUTER["queue"]:
                jid = _PUTER["queue"].pop(0)
                job = _PUTER["jobs"].get(jid)
                if job and not job.get("claimed") and not job.get("done"):
                    job["claimed"] = time.time()
                    job["version"] += 1
                    return dict(job["request"], id=jid)
        if time.time() >= deadline:
            return None
        time.sleep(0.25)


def puter_complete(jid, result):
    with _PUTER["lock"]:
        job = _PUTER["jobs"].get(str(jid or ""))
        if not job:
            return False
        job["result"] = result if isinstance(result, dict) else {"ok": False, "error": str(result)}
        job["done"] = True
        if job["result"].get("ok"):
            _PUTER["runs"] += 1
        else:
            _PUTER["failures"] += 1
        return True


def puter_set_models(models, signed_in=None):
    out = []
    for m in models or []:
        if isinstance(m, str):
            m = {"id": m}
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or m.get("key") or m.get("model") or "").strip()
        if not mid or mid.startswith("puter/"):
            continue
        out.append({
            "id": mid,
            "name": str(m.get("name") or m.get("description") or mid)[:80],
            "context": int(m.get("max_input_tokens") or m.get("context_length") or 0),
            # Puter normalises every vendor to OpenAI tool calling.
            "tools": bool(m.get("supports_tools", True)),
            "free": True,
        })
    seen, uniq = set(), []
    for m in out:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        uniq.append(m)
    # Known-good free models first (in PUTER_FALLBACKS order), then the rest
    # alphabetically - the dropdown's top entry is what Jarvis will use.
    uniq.sort(key=lambda x: (PUTER_FALLBACKS.index(x["id"])
                             if x["id"] in PUTER_FALLBACKS else len(PUTER_FALLBACKS),
                             not x["tools"], x["id"]))
    with _PUTER["lock"]:
        _PUTER["models"] = uniq
        _PUTER["models_at"] = time.time()
        if signed_in is not None:
            _PUTER["signed_in"] = bool(signed_in)
    return uniq


def puter_models():
    with _PUTER["lock"]:
        return list(_PUTER["models"])


def _puter_wait(jid, timeout):
    """Block until the browser answers (or the job expires)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _PUTER["lock"]:
            job = _PUTER["jobs"].get(jid)
            if not job:
                return None
            if job.get("done"):
                return job.get("result")
        time.sleep(0.2)
    with _PUTER["lock"]:
        job = _PUTER["jobs"].pop(jid, None)
        if job and jid in _PUTER["queue"]:
            _PUTER["queue"].remove(jid)
    return None


def _call_brain_puter(messages, cfg, max_tokens=400, temperature=0.4, tools=None):
    if not puter_alive():
        return None, ("the Puter.js relay is not connected - open the Jarvis dashboard "
                      "page in a browser (that tab is the free brain) and keep it open")
    jid = "job-%d-%d" % (int(time.time() * 1000), len(_PUTER["jobs"]) + 1)
    request = {
        "messages": messages,
        "models": candidate_models(cfg),
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "tools": tools or [],
        "created": time.time(),
    }
    with _PUTER["lock"]:
        _puter_prune(time.time())
        _PUTER["jobs"][jid] = {"request": request, "result": None, "done": False,
                               "claimed": 0.0, "created": time.time(), "version": 0}
        _PUTER["queue"].append(jid)
        if len(_PUTER["jobs"]) > 40:                 # never grow without bound
            for old in sorted(_PUTER["jobs"], key=lambda k: _PUTER["jobs"][k]["created"])[:-20]:
                _PUTER["jobs"].pop(old, None)
                if old in _PUTER["queue"]:
                    _PUTER["queue"].remove(old)
    print("[jarvis] puter.js job %s queued (%s)" % (jid, request["models"][0]))
    result = _puter_wait(jid, PUTER_JOB_TTL)
    with _PUTER["lock"]:
        _PUTER["jobs"].pop(jid, None)
        if jid in _PUTER["queue"]:
            _PUTER["queue"].remove(jid)
    if result is None:
        return None, ("Puter.js did not answer in time - is the dashboard tab still open "
                      "and signed in to Puter?")
    if not result.get("ok"):
        err = str(result.get("error") or "unknown puter.js error")
        if "sign" in err.lower() or "auth" in err.lower():
            return None, "Puter.js wants you to sign in - open the dashboard and click CONNECT PUTER"
        if "tool" in err.lower() and tools:
            return None, TOOL_UNSUPPORTED
        return None, "puter.js: %s" % err[:160]
    msg = result.get("message") or {}
    if not isinstance(msg, dict):
        msg = {"content": str(msg)}
    msg.setdefault("role", "assistant")
    if result.get("model"):
        _state["last_model"] = "puter:%s" % result["model"]
    if not msg.get("content") and not msg.get("tool_calls"):
        return None, "puter.js returned an empty reply"
    return msg, ""


def _extract_json(content):
    """Pull the first JSON object out of a reply, tolerating prose/fences."""
    if not content:
        return {}
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else {}
        except Exception:
            pass
    return {}


def _split_action(raw):
    """Split one action dict into ``(tool_name, params)``.

    The tool name travels in ``tool`` (or the legacy ``name``) - but ``name``
    is *also* a real parameter of open_app/picture, so when both are present
    the parameter wins and the tool name is read from ``tool``/``__tool``.
    """
    if not isinstance(raw, dict):
        return "", {}
    for key in ("__tool", "tool"):
        if str(raw.get(key) or "").strip() in TOOL_NAMES:
            return str(raw[key]).strip(), \
                {k: v for k, v in raw.items() if k not in ("__tool", "tool")}
    name = str(raw.get("name") or "").strip()
    params = {k: v for k, v in raw.items() if k != "name"}
    if name in TOOL_NAMES:
        return name, params
    # Repair a model that answered {"name": "notepad"} while meaning open_app:
    # if some other value is a known tool name, that one is the discriminator.
    for key, value in list(params.items()):
        if str(value).strip() in TOOL_NAMES:
            params.pop(key)
            params["name"] = name
            return str(value).strip(), params
    return name, params


def _actions_from_message(msg):
    """Normalise either native tool_calls or a JSON reply into action dicts."""
    actions = []
    for tc in (msg.get("tool_calls") or []):
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        if not isinstance(args, dict):
            args = {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        if "name" in args:
            # keep the model's own "name" argument (open_app, picture, ...)
            actions.append(dict(args, tool=name))
        else:
            actions.append(dict(args, name=name))

    obj = _extract_json(msg.get("content") or "")
    if obj:
        one = obj.get("action")
        many = obj.get("actions")
        if isinstance(many, list):
            actions.extend([a for a in many
                            if isinstance(a, dict) and (a.get("tool") or a.get("name"))])
        elif isinstance(one, dict) and (one.get("tool") or one.get("name")):
            actions.append(one)
    return actions, obj


def _speak_from_message(msg, obj):
    """Pick the line to say out loud.

    When the model used native tool calls (Gemini ``functionCall`` parts,
    Puter.js ``tool_calls``), any prose next to them is deliberately *not*
    spoken: the executed actions report themselves, so saying both would give
    "Opening Notepad, sir. Opening notepad." Prose is only used when there
    were no actions and no JSON instruction blob.
    """
    content = (msg.get("content") or "").strip()
    speak = str(obj.get("speak") or "").strip()
    if not speak and content and not obj.get("action") and not obj.get("actions") \
            and not msg.get("tool_calls"):
        speak = content
    return speak


def _set_artifact(kind, title, detail="", svg="", path=""):
    _state["pending_artifact"] = {
        "kind": kind, "title": title, "detail": detail,
        "svg": svg, "path": path,
        "time": datetime.now().strftime("%H:%M:%S"),
    }


def log_action(name, params, result):
    with _ACTION_LOG_LOCK:
        _ACTION_LOG.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "name": name,
            "params": params,
            "result": str(result)[:300],
        })
        if len(_ACTION_LOG) > 60:
            del _ACTION_LOG[:-60]


def run_action_list(actions):
    """Execute a chain of actions, honouring the abort flag between steps."""
    cfg = load_config()
    cap = max(1, min(12, int(cfg.get("max_actions", 6) or 6)))
    results = []
    for raw in actions[:cap]:
        if _state.get("abort"):
            results.append("Stopped.")
            break
        if not isinstance(raw, dict):
            continue
        name, params = _split_action(raw)
        if not name:
            continue
        try:
            out = run_action(name, params)      # run_action() logs each step
        except Exception as e:
            out = "%s failed: %s" % (name, e)
        if out:
            results.append(str(out))
    return results


def _no_brain_message(cfg=None):
    """What Jarvis says when the brain cannot be reached at all."""
    cfg = cfg if cfg is not None else load_config()
    if cfg_provider(cfg) == "puter":
        return ("My brain runs through Puter.js in the browser, so keep the Jarvis "
                "dashboard tab open - that is what does the thinking. Click CONNECT "
                "PUTER in the settings if it asks you to sign in.")
    return ("My brain is not connected. Open the gear icon, pick a provider, paste "
            "an API key and choose one of the free models.")


def llm_reply(text):
    """Ask the brain what to do, then do it. Returns the spoken reply."""
    cfg = load_config()
    if not brain_ready(cfg):
        return _no_brain_message(cfg)
    _state["pending_artifact"] = None
    messages = [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": text},
    ]
    use_tools = bool(_state.get("tools_ok", True))
    msg, err = _call_brain(messages, cfg, max_tokens=360, temperature=0.3,
                           tools=TOOLS if use_tools else None)
    if msg is None and err == TOOL_UNSUPPORTED:
        # some free endpoints reject `tools`; remember that and ask again in JSON mode
        print("[jarvis] this model refuses tool calls - falling back to JSON mode")
        _state["tools_ok"] = False
        msg, err = _call_brain(messages, cfg, max_tokens=360, temperature=0.3, tools=None)
    if msg is None:
        return "I could not reach my brain. %s" % err

    actions, obj = _actions_from_message(msg)
    speak = _speak_from_message(msg, obj)
    if not actions:
        return speak or "Done."
    results = run_action_list(actions)
    artifact = _state.get("pending_artifact")
    if artifact:
        _state["last_artifact"] = artifact
    if results:
        joined = " ".join(r for r in results if r)
        return (speak + " " + joined).strip() if speak else joined
    return speak or "Done."


# ---------- conversational chat ----------
_CHAT_SESSIONS = {}
_CHAT_LOCK = threading.Lock()

CHAT_SYSTEM = (
    "You are Richie Jarvis, a witty, friendly AI butler who lives on your boss's PC. "
    "Have a natural, casual conversation with the user. Reply in plain text only "
    "(never output JSON or code fences). Keep replies short and punchy (1-4 sentences) "
    "unless the user clearly wants more detail. You may mention you can control the PC, "
    "but do not perform actions here - the user has a separate command box for that."
)


def chat_reply(session, text):
    cfg = load_config()
    if not brain_ready(cfg):
        return _no_brain_message(cfg)
    with _CHAT_LOCK:
        hist = _CHAT_SESSIONS.setdefault(session, [])
        hist.append({"role": "user", "content": text})
        if len(hist) > 24:
            hist = hist[-24:]
            _CHAT_SESSIONS[session] = hist
        messages = [{"role": "system", "content": CHAT_SYSTEM}] + list(hist)
    msg, err = _call_brain(messages, cfg, max_tokens=500, temperature=0.7)
    if msg is None:
        return f"I couldn't reach my brain right now. {err}"
    reply = (msg.get("content") or "").strip()
    if not reply:
        return "My brain came back blank. Try that again."
    if reply.startswith("```"):
        reply = re.sub(r"^```[a-zA-Z]*\n?", "", reply)
        reply = re.sub(r"\n?```$", "", reply).strip()
    with _CHAT_LOCK:
        hist.append({"role": "assistant", "content": reply})
        if len(hist) > 24:
            hist = hist[-24:]
            _CHAT_SESSIONS[session] = hist
    return reply


# --------------------------------------------------------------------------
# mouse movement engine
#
# The model asks for a destination; this decides how the pointer gets there.
# Every loop checks the abort flag so the STOP button (or slamming the mouse
# into a corner) kills a runaway action immediately.
# --------------------------------------------------------------------------

def _ease(t: float) -> float:
    """Smoothstep: start and stop gently instead of snapping."""
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return t * t * (3 - 2 * t)


def _speed_factor() -> float:
    try:
        return max(0.25, min(4.0, float(load_config().get("speed", 1.0) or 1.0)))
    except Exception:
        return 1.0


def _aborted() -> bool:
    return bool(_state.get("abort"))


def mouse_move_to(x, y, duration=0.4):
    """Glide the pointer to (x, y). Returns False if the run was aborted."""
    pag = _pyautogui()
    sx, sy = pag.position()
    duration = max(0.0, float(duration or 0.0)) / _speed_factor()
    dist = math.hypot(x - sx, y - sy)
    steps = int(min(160, max(10, dist / 14.0)))
    for i in range(1, steps + 1):
        if _aborted():
            return False
        f = _ease(i / steps)
        pag.moveTo(int(sx + (x - sx) * f), int(sy + (y - sy) * f))
        if duration:
            time.sleep(duration / steps)
    pag.moveTo(int(x), int(y))
    return True


def mouse_follow(points, duration=None, button=None, spacing=6.0):
    """Walk the pointer through a list of points, optionally dragging."""
    pag = _pyautogui()
    pts = list(points)
    if len(pts) < 2:
        return True
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    if duration is None:
        duration = max(0.3, min(8.0, length / 850.0)) / _speed_factor()
    else:
        duration = max(0.0, float(duration)) / _speed_factor()
    dt = duration / max(1, len(pts) - 1)
    try:
        pag.moveTo(int(pts[0][0]), int(pts[0][1]))
        if button:
            pag.mouseDown(button=button)
        for (x, y) in pts[1:]:
            if _aborted():
                return False
            pag.moveTo(int(x), int(y))
            if dt:
                time.sleep(dt)
    finally:
        if button:
            try:
                pag.mouseUp(button=button)
            except Exception:
                pass
    return True


def mouse_now():
    try:
        x, y = _pyautogui().position()
        return "The mouse is at %d,%d." % (x, y)
    except Exception as e:
        return "I cannot read the mouse position. %s" % e


# --------------------------------------------------------------------------
# drawing
# --------------------------------------------------------------------------

_DRAW_NUM_KEYS = ("sides", "points", "inner", "turns", "cycles", "rot",
                  "sweep", "steps", "rx", "ry", "inset", "angle", "rays",
                  "petals", "amp", "stroke")


def drawing_box(params):
    """Work out where on screen a drawing should land."""
    w, h = _screen_size()
    if not w:
        w, h = 1920, 1080
    bw = int(params.get("w") or w * 0.46)
    bh = int(params.get("h") or h * 0.46)
    bx = int(params["x"]) if params.get("x") is not None else (w - bw) // 2
    by = int(params["y"]) if params.get("y") is not None else (h - bh) // 2
    return (bx, by, bw, bh)


def _num(params, key, default=None):
    v = params.get(key, None)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def draw_action(params):
    """Draw a shape or picture by dragging the mouse in whatever app is open."""
    if drawlib is None:
        return "My drawing engine is missing (draw.py next to server.py)."
    kind = str(params.get("shape") or params.get("name") or "").strip().lower()
    is_picture = False
    if not kind:
        kind = str(params.get("picture") or "").strip().lower()
        is_picture = True
    if not kind:
        return "Tell me what to draw."

    registry = drawlib.PICTURES if is_picture else drawlib.SHAPES
    if kind not in registry:
        near = [k for k in registry if kind and (kind in k or k in kind)]
        if near:
            kind = near[0]
        else:
            return ("I cannot draw '%s'. I know: %s"
                    % (kind, ", ".join(sorted(registry))))

    kwargs = {}
    for key in _DRAW_NUM_KEYS:
        v = _num(params, key)
        if v is not None:
            kwargs[key] = v
    try:
        strokes = registry[kind](**kwargs)
    except TypeError:
        strokes = registry[kind]()
    if not strokes:
        return "That shape produced no lines."

    box = drawing_box(params)
    paths = drawlib.fit_strokes(strokes, box)
    points = sum(len(p) for p in paths)
    svg = drawlib.strokes_to_svg(strokes, color="#6fffe0")
    _set_artifact("draw", "drawing · %s" % kind,
                  "%d strokes, %d mouse points, box %dx%d at %d,%d"
                  % (len(paths), points, box[2], box[3], box[0], box[1]),
                  svg=svg)

    try:
        for path in paths:
            if len(path) < 2:
                continue
            line = drawlib.resample(path, 5.0)
            if not mouse_follow(line, button="left"):
                return "Drawing stopped."
    except Exception as e:
        return "Drawing failed. Run setup.bat to install pyautogui. (%s)" % e
    return "Drew a %s with %d strokes." % (kind, len(paths))


# --------------------------------------------------------------------------
# 3D models
# --------------------------------------------------------------------------

def artifact_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    base = os.path.join(desktop, "Jarvis3D") if os.path.isdir(desktop) \
        else os.path.join(BASE_DIR, "models")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        base = BASE_DIR
    return base


def model3d_action(params):
    if m3d is None:
        return "My 3D engine is missing (model3d.py next to server.py)."
    kind = str(params.get("kind") or params.get("name") or "cube").strip().lower()
    if kind not in m3d.MODELS:
        return ("I cannot model '%s'. I can build: %s"
                % (kind, ", ".join(sorted(m3d.MODELS))))
    allowed = set(m3d.MODEL_PARAMS.get(kind, {}))
    kwargs = {}
    for k in allowed:
        v = _num(params, k)
        if v is not None:
            kwargs[k] = v
    try:
        mesh = m3d.make_model(kind, **kwargs)
    except Exception as e:
        return "That model failed to build. %s" % e

    fmt = str(params.get("fmt") or "obj").strip().lower()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = artifact_dir()
    written = []
    try:
        if fmt in ("obj", "both"):
            written.append(m3d.write_obj(mesh, os.path.join(folder, "%s-%s.obj" % (kind, stamp))))
        if fmt in ("stl", "both"):
            written.append(m3d.write_stl(mesh, os.path.join(folder, "%s-%s.stl" % (kind, stamp))))
        if not written:
            written.append(m3d.write_obj(mesh, os.path.join(folder, "%s-%s.obj" % (kind, stamp))))
    except Exception as e:
        return "I built the model but could not save it. %s" % e

    stats = m3d.mesh_stats(mesh)
    svg = m3d.mesh_to_svg(mesh, size=480)
    _set_artifact("model3d", "3D model · %s" % kind,
                  "%d triangles · %s · %.1f x %.1f x %.1f cm"
                  % (stats["faces"], "watertight" if stats["watertight"] else "open shell",
                     stats["width"], stats["height"], stats["depth"]),
                  svg=svg, path=written[-1])

    opened = ""
    if params.get("open", True):
        try:
            os.startfile(written[-1])
            opened = " Opened it for you."
        except Exception:
            opened = " Saved to %s." % written[-1]
    return ("Built a %s: %d triangles, %.1f by %.1f by %.1f units.%s"
            % (kind, stats["faces"], stats["width"], stats["height"],
               stats["depth"], opened))


# --------------------------------------------------------------------------
# windows
# --------------------------------------------------------------------------

class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def enum_windows():
    """All visible windows: ``[{'hwnd', 'title', 'rect'}]`` (rect = x,y,w,h)."""
    if appslib is not None:
        return appslib.windows()
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    out = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                r = _RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                out.append({"hwnd": hwnd, "title": buf.value,
                            "rect": (r.left, r.top, max(0, r.right - r.left),
                                     max(0, r.bottom - r.top))})
        return True

    user32.EnumWindows(proto(cb), 0)
    return out


def find_window(title):
    """Best-effort match of a window by (part of) its title."""
    if appslib is not None:
        return appslib.find_window(title)
    needle = str(title or "").strip().lower()
    wins = [w for w in enum_windows() if w["title"]]
    if not needle:
        return None
    for w in wins:
        if needle in w["title"].lower():
            return w
    for w in wins:
        if needle in w["title"].lower().replace("-", " ").replace("—", " "):
            return w
    return None


def window_action(op, title=None, x=None, y=None, w=None, h=None):
    op = str(op or "list").strip().lower()
    if op == "list":
        names = [w["title"] for w in enum_windows() if w["title"]]
        return "Open windows: " + (", ".join(names[:14]) if names else "(none found)")
    if op == "active":
        info = get_active_window()
        return "Active window is %s - %s." % (info.get("app") or "?",
                                              info.get("title") or "(untitled)")
    win = find_window(title)
    if not win:
        return "I cannot find a window called %s." % (title or "(nothing given)")
    try:
        user32 = ctypes.windll.user32
        hwnd = win["hwnd"]
        SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0004, 0x0040
        if op == "focus":
            user32.SetForegroundWindow(hwnd)
            return "Focused %s." % win["title"]
        if op == "move":
            cx, cy = win["rect"][0], win["rect"][1]
            user32.SetWindowPos(hwnd, 0, int(x if x is not None else cx),
                                int(y if y is not None else cy), 0, 0,
                                SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW)
            return "Moved %s to %d,%d." % (win["title"], int(x or cx), int(y or cy))
        if op == "resize":
            cw, ch = win["rect"][2], win["rect"][3]
            user32.SetWindowPos(hwnd, 0, 0, 0, int(w if w is not None else cw),
                                int(h if h is not None else ch),
                                SWP_NOMOVE | SWP_NOZORDER | SWP_SHOWWINDOW)
            return "Resized %s to %dx%d." % (win["title"],
                                             int(w or cw), int(h or ch))
        if op == "minimize":
            user32.ShowWindow(hwnd, 6)
            return "Minimized %s." % win["title"]
        if op == "maximize":
            user32.ShowWindow(hwnd, 3)
            return "Maximized %s." % win["title"]
        if op == "close":
            user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
            return "Closed %s." % win["title"]
    except Exception as e:
        return "Window action failed. %s" % e
    return "Unknown window operation %s." % op


# --------------------------------------------------------------------------
# keyboard + clipboard
# --------------------------------------------------------------------------

KEY_ALIASES = {
    "enter": "enter", "return": "enter", "esc": "esc", "escape": "esc",
    "tab": "tab", "space": "space", "backspace": "backspace",
    "delete": "delete", "up": "up", "down": "down", "left": "left",
    "right": "right", "home": "home", "end": "end", "pageup": "pageup",
    "pagedown": "pagedown", "win": "win", "super": "win", "menu": "apps",
    "volumeup": "volumeup", "volumedown": "volumedown", "volumemute": "volumemute",
    "playpause": "playpause", "nexttrack": "nexttrack", "prevtrack": "prevtrack",
    "f5": "f5", "f11": "f11",
}


def keyboard_action(op, text=None, key=None, keys=None, times=1):
    op = str(op or "").strip().lower()
    if op == "type":
        return type_text(str(text or ""))
    if op == "hotkey" or (key and "+" in str(key)):
        parts = keys or [p for p in re.split(r"[+\-]", str(key or "")) if p]
        if not parts:
            return "Give me the keys to press, like ctrl and c."
        try:
            pag = _pyautogui()
            pag.hotkey(*[p.strip().lower() for p in parts])
            return "Pressed %s." % "+".join(parts)
        except Exception as e:
            return "Hotkey failed. %s" % e
    if op == "press":
        k = KEY_ALIASES.get(str(key or "").strip().lower(), str(key or "").strip().lower())
        return press_key(k, times=times)
    return "Unknown keyboard operation %s." % op


def clipboard_action(text):
    try:
        proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE,
                                shell=True, creationflags=0)
        proc.communicate(str(text or "").encode("utf-16-le") if os.name == "nt"
                         else str(text or "").encode())
        return "Copied to the clipboard."
    except Exception as e:
        return "Clipboard failed. %s" % e


# --------------------------------------------------------------------------
# guarded shell
# --------------------------------------------------------------------------

DANGEROUS = (
    "format ", "del /", "del *", "rmdir /s", "rd /s", "rm -rf", "shutdown",
    "diskpart", "cipher /w", "taskkill /f /im system", "reg delete",
    "remove-item", "mkfs", "takeown", "bcdedit", "net user",
)


def run_command_safe(command):
    cmd = str(command or "").strip()
    if not cmd:
        return "Give me a command to run."
    low = cmd.lower()
    if load_config().get("safe_mode", True) and any(d in low for d in DANGEROUS):
        return ("That command looks destructive, so I am not running it. "
                "Turn off safe mode in settings if you really want it.")
    return run_command(cmd)


# --------------------------------------------------------------------------
# dispatcher
# --------------------------------------------------------------------------

def _dispatch(name, params):
    """Execute one action and return a short spoken result (or None)."""

    def s(key, default=""):
        v = params.get(key, default)
        return default if v is None else str(v)

    def n(key, default=None):
        return _num(params, key, default)

    try:
        if name == "open_app":
            return open_app(s("name") or s("arg"))
        if name == "search_web":
            return search_web(s("query") or s("arg"), s("engine", "google"))
        if name == "open_url":
            return open_url(s("url") or s("arg"))
        if name == "run_command":
            return run_command_safe(s("command") or s("arg"))
        if name == "screenshot":
            return do_screenshot()
        if name == "mouse":
            op = s("op") or s("action", "click")
            x, y = n("x"), n("y")
            x2, y2 = n("x2"), n("y2")
            dur = n("duration", 0.4)
            clicks = int(n("clicks", 1) or 1)
            if op == "position":
                return mouse_now()
            if op == "move":
                if x is None or y is None:
                    return "Give me x and y to move to."
                ok = mouse_move_to(x, y, dur if dur is not None else 0.4)
                return "Moved the mouse to %d,%d." % (x, y) if ok else "Move stopped."
            if op == "drag":
                if None in (x, y, x2, y2):
                    return "A drag needs x, y, x2 and y2."
                ok = mouse_follow([(x, y), (x2, y2)], duration=dur, button="left")
                return "Dragged from %d,%d to %d,%d." % (x, y, x2, y2) if ok else "Drag stopped."
            if op in ("click", "double_click", "right_click", "middle_click"):
                pag = _pyautogui()
                if x is not None and y is not None:
                    if not mouse_move_to(x, y, dur if dur is not None else 0.4):
                        return "Stopped."
                button = {"click": "left", "double_click": "left",
                          "right_click": "right", "middle_click": "middle"}[op]
                if op == "double_click":
                    pag.doubleClick()
                else:
                    pag.click(button=button, clicks=max(1, clicks))
                where = " at %d,%d" % (x, y) if x is not None and y is not None else ""
                return "Clicked%s." % where
            if op == "scroll":
                pag = _pyautogui()
                amount = int(n("y", 0) or n("x", 0) or -300)
                pag.scroll(amount)
                return "Scrolled %d." % amount
            return "Unknown mouse operation %s." % op
        if name in ("draw", "picture"):
            return draw_action(params)
        if name == "model3d":
            return model3d_action(params)
        if name == "keyboard":
            return keyboard_action(s("op"), text=s("text"), key=s("key"),
                                   keys=params.get("keys"),
                                   times=int(n("times", 1) or 1))
        if name == "window":
            return window_action(s("op"), title=s("title"),
                                 x=n("x"), y=n("y"), w=n("w"), h=n("h"))
        if name == "whatsapp":
            op = s("op", "message")
            if op == "call":
                return whatsapp_call(s("contact"), video=False)
            if op == "video_call":
                return whatsapp_call(s("contact"), video=True)
            return send_whatsapp_message(s("contact"), s("message"))
        if name == "clipboard":
            return clipboard_action(s("text"))
        if name == "call":
            op = s("op", "status")
            if op == "start":
                _state["abort"] = False
                return start_session("call", app=s("app"), who=s("who"))[1]
            if op == "stop":
                stop_session()
                return "I stopped talking. The call is yours again."
            if op == "say":
                text = s("text")
                if not text:
                    return "Tell me what to say."
                if not (_ENGINE and _ENGINE.active):
                    return "I am not in a call. Say 'call mode on' first."
                engine().say(text)
                return "Said: %s" % text
            if op in ("mute", "unmute"):
                if not (_ENGINE and _ENGINE.active):
                    return "There is no call to mute."
                engine().session.muted = (op == "mute")
                return "I will %s from now on." % ("stay quiet" if op == "mute" else "speak again")
            st = session_state()
            return ("No call session." if not st.get("active")
                    else "Talking in %s with %s, %d turns so far."
                         % (st.get("app") or "?", st.get("who") or "them", st.get("turns", 0)))
        if name == "chat":
            op = s("op", "read")
            app = s("app") or (appslib.active_app() if appslib else "") or ""
            if op == "read":
                res = appslib.read_chat(app=app) if appslib else {"ok": False, "text": ""}
                text = (res.get("text") or "").strip()
                if not text:
                    return "I could not read that chat. %s" % (res.get("error") or "")
                tail = "\n".join([l for l in text.splitlines() if l.strip()][-8:])
                return "Latest from %s:\n%s" % (res.get("app") or app or "the chat", tail[:900])
            if op == "send":
                text = s("text")
                if not text:
                    return "Give me a message to send."
                res = appslib.send_chat_text(text, app=app) if appslib else \
                    {"ok": True, "app": app}
                return "Sent to %s: %s" % (res.get("app") or app or "the chat", text)
            if op == "auto":
                on = params.get("on", True)
                if on:
                    _state["abort"] = False
                    return start_session("chat", app=app)[1]
                stop_session()
                return "I stopped watching the chat."
            return "Unknown chat operation."
        if name == "audio":
            if s("op", "list") == "use":
                dev = s("device")
                if not dev:
                    return "Name the device to use."
                idx, resolved = find_output_device(dev)
                if idx is None:
                    known = audio_devices().get("devices") or []
                    names = ", ".join(d["name"] for d in known[:6]) or "none found"
                    return "I cannot find an output device called %s. I see: %s" % (dev, names)
                cfg = load_config()
                cfg["voice_device"] = resolved
                save_config(cfg)
                return "Speaking through %s from now on." % resolved
            info = audio_devices()
            if info.get("error"):
                return "I could not list audio devices. %s" % info["error"]
            devs = info.get("devices") or []
            if not devs:
                return "No playback devices found."
            return "Playback devices: " + ", ".join(
                d["name"] + (" (virtual cable)" if d.get("virtual") else "")
                for d in devs[:8])
        if name == "wait":
            secs = max(0.0, min(10.0, float(n("seconds", 1) or 1)))
            if _aborted():
                return "Stopped."
            time.sleep(secs)
            return "Waited %.1f seconds." % secs
        if name == "system_info":
            return system_info()
        if name == "say_aloud":
            _speak_aloud(s("text") or s("arg"))
            return "Speaking aloud: %s" % (s("text") or s("arg"))
        # legacy action names kept for older prompt versions
        if name == "press_key":
            return press_key(s("arg") or s("key"), times=int(n("times", 1) or 1))
        if name == "type_text":
            return type_text(s("arg") or s("text"))
        if name == "send_chat":
            return send_chat(s("arg") or s("text"))
        if name == "active_window":
            info = get_active_window()
            return "Active window is %s (title: %s)." % (info.get("app") or "unknown",
                                                         info.get("title") or "(none)")
        if name == "list_apps":
            return "Running apps: " + ", ".join(list_running_apps())
        if name == "mouse_legacy":
            return mouse_action(s("action", "click"), n("x"), n("y"))
    except Exception as e:
        return "Action failed. %s" % e
    return None

def run_action(name, params=None):
    """Run one action and record it in the audit log the UI shows."""
    if isinstance(name, dict):          # legacy single-dict call style
        name, params = _split_action(name)
    params = params or {}
    try:
        out = _dispatch(name, params)
    except Exception as e:              # pragma: no cover - safety net
        out = "Action failed. %s" % e
    log_action(name, params, out or "")
    return out


def _logged(name, params, result):
    """Log actions triggered by the local (no-brain) command parser."""
    log_action(name, params, result or "")
    return result


def load_contacts():
    try:
        with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def contact_owner():
    owner = load_contacts().get("_owner")
    return str(owner).strip() if owner else "the boss"


RELATION_SYNONYMS = {
    "daddy": "father", "papa": "father",
    "mommy": "mother", "mum": "mother", "mama": "mother", "maa": "mother",
    "bro": "brother", "sis": "sister",
    "grandpa": "grandfather", "grandma": "grandmother",
}


def resolve_contact(query):
    name = str(query).strip().lower()
    name = re.sub(r"^(?:my|our)\s+", "", name)
    name = RELATION_SYNONYMS.get(name, name)
    contacts = {str(k).lower(): v for k, v in load_contacts().items()
                if not str(k).startswith("_")}
    if name in contacts:
        return name, contacts[name]
    for k, v in contacts.items():
        if k in name or name in k:
            return k, v
    return None, None


def open_app(name):
    key = name.strip().lower()
    target = APPS.get(key)
    if not target:
        for k, v in APPS.items():
            if k in key:
                target = v
                break
    try:
        if target is None:
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(name)}")
            return f"I couldn't find an app called {name}, so I searched the web for it."
        if target.endswith(":") and ":" in target:
            os.startfile(target)
        else:
            try:
                os.startfile(target)
            except Exception:
                subprocess.Popen([target], shell=True)
        return f"Opening {name}."
    except Exception as e:
        return f"Sorry, I failed to open {name}. {e}"


def search_web(query, engine="google"):
    q = urllib.parse.quote(query)
    urls = {
        "google": f"https://www.google.com/search?q={q}",
        "youtube": f"https://www.youtube.com/results?search_query={q}",
        "wikipedia": f"https://en.wikipedia.org/wiki/Special:Search?search={q}",
    }
    url = urls.get(engine, urls["google"])
    webbrowser.open(url)
    where = "YouTube" if engine == "youtube" else ("Wikipedia" if engine == "wikipedia" else "Google")
    return f"Searching {where} for {query}."


def _speak_aloud(text, device=None):
    # if an output device is configured (e.g. a virtual cable), speak into it
    # so the other side of a call can hear us; otherwise use the speakers
    try:
        if speak_through_device(text, device):
            return
    except Exception as e:
        print("[jarvis] routed speech failed, falling back:", e)
    try:
        esc = str(text).replace("'", "''")
        ps = (f"Add-Type -AssemblyName System.Speech; "
              f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.Rate = 0; $s.Speak('{esc}')")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-Command", ps], creationflags=flags)
    except Exception as e:
        print("[jarvis] speak-aloud failed:", e)


INCOMING_HINTS = ("incoming call", "incoming voice call", "incoming video call",
                  "panggilan masuk", "panggilan suara", "panggilan video masuk")


def _all_window_titles():
    import ctypes
    titles = []
    user32 = ctypes.windll.user32
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_bool
    user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                titles.append(buf.value)
        return True

    user32.EnumWindows(proto(cb), 0)
    return titles


def get_active_window():
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = ""
        try:
            app = _psutil().Process(pid.value).name()
        except Exception:
            app = ""
        return {"title": title, "app": app}
    except Exception as e:
        return {"title": "", "app": "", "error": str(e)}


def list_running_apps():
    try:
        ps = _psutil()
        counts = {}
        for p in ps.process_iter(["name"]):
            nm = p.info.get("name") or ""
            if nm:
                counts[nm] = counts.get(nm, 0) + 1
        top = sorted(counts.items(), key=lambda x: -x[1])[:30]
        return [f"{n} ({c})" for n, c in top]
    except Exception as e:
        return [f"error: {e}"]


def _secretary_loop():
    while True:
        time.sleep(2)
        if not _state.get("secretary"):
            continue
        try:
            hits = [t for t in _all_window_titles()
                    if any(h in t.lower() for h in INCOMING_HINTS)]
        except Exception:
            continue
        if not hits:
            continue
        print("[jarvis] incoming call detected:", hits)
        owner = contact_owner()
        try:
            pag = _pyautogui()
            pos = _state.get("answer_pos")
            if pos:
                pag.moveTo(pos[0], pos[1])
                time.sleep(0.3)
                pag.click()
                print("[jarvis] clicked the saved answer button")
            else:
                pag.press("enter")
        except Exception as e:
            print("[jarvis] auto-answer click failed:", e)
        time.sleep(4)
        _speak_aloud(f"Hello! You are talking with Richie Jarvis, {owner}'s AI assistant. "
                     f"{owner} is not available right now. Please leave your name and your message.")
        if load_config().get("auto_converse", True) and appslib is not None \
                and not (_ENGINE is not None and _ENGINE.active):
            title = hits[0] if hits else ""
            start_session("call", app=appslib.active_app() or appslib.match_app(title) or "",
                          who=_guess_who(title))
        time.sleep(25)


def ensure_secretary():
    t = threading.Thread(target=_secretary_loop, daemon=True)
    t.start()
    return t


def set_answer_button():
    def _capture():
        try:
            pag = _pyautogui()
            time.sleep(6)
            x, y = pag.position()
            _state["answer_pos"] = (x, y)
            cfg = load_config()
            cfg["answer_pos"] = [x, y]
            save_config(cfg)
            print(f"[jarvis] answer button saved at {x},{y}")
            _speak_aloud("Answer button position saved.")
        except Exception as e:
            print("[jarvis] answer capture failed:", e)
    threading.Thread(target=_capture, daemon=True).start()


STT_MODEL_DIR = os.path.join(BASE_DIR, "vosk-model-small-en-us-0.15")


def _mono_from_frame(data, channels):
    import struct
    n = len(data) // 2 // channels
    if n <= 0:
        return b""
    shorts = struct.unpack("<%dh" % (n * channels), data[: n * channels * 2])
    if channels == 1:
        return struct.pack("<%dh" % n, *shorts)
    mono = [(shorts[i * 2] + shorts[i * 2 + 1]) // 2 for i in range(n)]
    return struct.pack("<%dh" % n, *mono)


def _frame_rms(mono):
    import struct
    n = len(mono) // 2
    if not n:
        return 0
    s = struct.unpack("<%dh" % n, mono)
    acc = 0
    for v in s:
        acc += v * v
    return (acc / n) ** 0.5


def _talk_aloud_guarded(text):
    _state["mute_capture"] = True
    try:
        _speak_aloud(text)
    finally:
        delay = 1.5 + len(str(text)) * 0.06
        threading.Timer(delay, lambda: _state.update(mute_capture=False)).start()


def _listen_loop():
    if not os.path.isdir(STT_MODEL_DIR):
        print("[jarvis] listen mode unavailable: STT model folder missing.")
        return
    from vosk import Model, KaldiRecognizer
    print("[jarvis] loading speech brain...")
    model = Model(STT_MODEL_DIR)
    print("[jarvis] speech brain ready.")
    import pyaudiowpatch as pw
    while True:
        time.sleep(0.5)
        if not _state.get("listen"):
            continue
        stream = None
        try:
            with pw.PyAudio() as pa:
                wasapi = pa.get_host_api_info_by_type(pw.paWASAPI)
                out = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
                if not out.get("isLoopbackDevice", False):
                    for lb in pa.get_loopback_device_info_generator():
                        if out["name"] in lb["name"]:
                            out = lb
                            break
                rate = int(out["defaultSampleRate"])
                ch = max(1, min(2, int(out.get("maxInputChannels", 2))))
                stream = pa.open(format=pw.paInt16, channels=ch, rate=rate,
                                 frames_per_buffer=rate // 10, input=True,
                                 input_device_index=out["index"])
                threshold = int(load_config().get("listen_threshold", 350))
                print(f"[jarvis] LISTEN MODE LIVE -> '{out['name']}' @ {rate}Hz "
                      f"(threshold {threshold})")
                rec = None
                talking = False
                silence = 0.0
                seg_frames = 0
                while _state.get("listen"):
                    raw = stream.read(rate // 10, exception_on_overflow=False)
                    if _state.get("mute_capture"):
                        talking = False
                        silence = 0.0
                        continue
                    mono = _mono_from_frame(raw, ch)
                    lvl = _frame_rms(mono)
                    if lvl > threshold:
                        if not talking:
                            talking = True
                            silence = 0.0
                            seg_frames = 0
                            rec = KaldiRecognizer(model, rate)
                        rec.AcceptWaveform(mono)
                        seg_frames += 1
                    elif talking:
                        rec.AcceptWaveform(mono)
                        silence += 0.1
                        if silence >= 1.0 or seg_frames > (rate * 14) // (rate // 10):
                            final = json.loads(rec.FinalResult() or "{}")
                            txt = str(final.get("text") or "").strip()
                            talking = False
                            if txt and len(txt.split()) >= 1:
                                print(f"[jarvis] SYSTEM AUDIO heard: {txt!r}")
                                if _ENGINE is not None and _ENGINE.active:
                                    # a live call/chat session owns the conversation
                                    # and speaks for itself
                                    engine().hear(txt)
                                else:
                                    reply = parse_command(txt)
                                    if reply is None:
                                        reply = llm_reply(txt)
                                    print(f"[jarvis] CALL ASSISTANT says: {reply!r}")
                                    if reply:
                                        _talk_aloud_guarded(reply)
                stream.stop_stream()
                stream.close()
                stream = None
        except Exception as e:
            print("[jarvis] listen loop error:", e)
            time.sleep(3)


def ensure_listener():
    t = threading.Thread(target=_listen_loop, daemon=True)
    t.start()
    return t


def whatsapp_call(number_or_name, video=False):
    number = re.sub(r"[^\d+]", "", str(number_or_name))
    resolved = str(number_or_name)
    if not number or len(re.sub(r"\D", "", number)) < 7:
        key, num = resolve_contact(number_or_name)
        if not num:
            return (f"I don't have a contact called {number_or_name}. "
                    "Add them to contacts.json first.")
        number = re.sub(r"\D", "", str(num))
        resolved = key
    owner = contact_owner()
    cfg = load_config()
    msg = f"Hello! This is Richie Jarvis, {owner}'s AI assistant. {owner} asked me to call you."
    text = urllib.parse.quote(msg)
    try:
        os.startfile(f"whatsapp://send?phone={number}&text={text}")
    except Exception:
        webbrowser.open(f"https://wa.me/{number}?text={text}")
        return (f"The WhatsApp app isn't installed, so I opened your {resolved} in the browser. "
                "Press Enter to send my message, then press the call button.")
    greet_delay = int(cfg.get("greet_delay", 3))

    def _send_then_greet():
        time.sleep(4)
        try:
            _pyautogui().press("enter")
            print("[jarvis] auto-sent the WhatsApp greeting message")
        except Exception as e:
            print("[jarvis] could not auto-send:", e)
        time.sleep(max(3, greet_delay))
        print("[jarvis] speaking the call greeting aloud")
        _speak_aloud(msg)

    threading.Thread(target=_send_then_greet, daemon=True).start()
    return (f"Calling your {resolved}. My greeting message was sent automatically. "
            f"Press the call button - once they answer, I will tell them that {owner} asked me to call.")


def send_whatsapp_message(number_or_name, message=""):
    raw = str(number_or_name)
    digits = re.sub(r"\D", "", raw)
    if not digits or len(digits) < 7:
        name, num = resolve_contact(raw)
        if num:
            digits = re.sub(r"\D", "", str(num))
        else:
            return (f"I don't have a contact called {raw}. "
                    "Add them to contacts.json first (e.g. \"father\": \"+62...\").")
    if not digits or len(digits) < 7:
        return f"That number for {raw} looks invalid."
    text = str(message or "").strip()
    try:
        url = f"whatsapp://send?phone={digits}"
        if text:
            url += "&text=" + urllib.parse.quote(text)
        os.startfile(url)
    except Exception:
        web = f"https://wa.me/{digits}" + (("?text=" + urllib.parse.quote(text)) if text else "")
        webbrowser.open(web)
        return (f"WhatsApp isn't installed, so I opened {raw} in the browser. "
                "Press Enter to send.")
    def _send():
        time.sleep(4)
        try:
            if text:
                _pyautogui().press("enter")
                print("[jarvis] auto-sent WhatsApp message")
        except Exception as e:
            print("[jarvis] whatsapp send failed:", e)
    threading.Thread(target=_send, daemon=True).start()
    if text:
        return f"Sent WhatsApp to {raw}: {text}"
    return f"Opened WhatsApp chat with {raw}."


def do_screenshot():
    try:
        pag = _pyautogui()
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        path = os.path.join(desktop, f"jarvis_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        pag.screenshot(path)
        return f"Screenshot saved to your desktop as {os.path.basename(path)}."
    except Exception as e:
        return f"Screenshot failed. Run setup.bat to install pyautogui. ({e})"


def press_key(key, times=1):
    try:
        pag = _pyautogui()
        mapping = {
            "volume up": "volumeup", "volume down": "volumedown", "mute": "volumemute",
            "play pause": "playpause", "next track": "nexttrack", "previous track": "prevtrack",
            "enter": "enter", "escape": "esc",
        }
        k = mapping.get(key, key)
        for _ in range(max(1, min(times, 30))):
            pag.press(k)
        return f"Pressed {key.replace('_', ' ')}."
    except Exception as e:
        return f"Key command failed. Run setup.bat to install pyautogui. ({e})"


def type_text(text):
    try:
        pag = _pyautogui()
        pag.write(text, interval=0.01)
        return f"Typed: {text}"
    except Exception as e:
        return f"Typing failed. Run setup.bat to install pyautogui. ({e})"


def send_chat(text):
    try:
        pag = _pyautogui()
        pag.write(text, interval=0.01)
        time.sleep(0.2)
        info = get_active_window()
        app = info.get("app") or "unknown window"
        pag.press("enter")
        return f"Typed and sent in {app}: {text}"
    except Exception as e:
        return f"Send chat failed. Run setup.bat to install pyautogui. ({e})"


def open_url(url):
    try:
        if not re.match(r"^https?://", url):
            url = "https://" + url
        webbrowser.open(url)
        return f"Opened {url} in your browser."
    except Exception as e:
        return f"Failed to open url: {e}"


def run_command(command):
    try:
        result = subprocess.run(str(command), shell=True, capture_output=True,
                                text=True, timeout=90)
        out = (result.stdout or "") + (result.stderr or "")
        out = out.strip()
        if not out:
            out = f"Command finished (exit code {result.returncode})."
        return f"Ran command. {out[:600]}"
    except subprocess.TimeoutExpired:
        return "Command timed out after 90 seconds."
    except Exception as e:
        return f"Command failed: {e}"


def mouse_action(action, x=None, y=None):
    try:
        pag = _pyautogui()
        if action == "move" and x is not None and y is not None:
            pag.moveTo(int(x), int(y), duration=0.2)
            return f"Moved mouse to {x},{y}."
        if action in ("click", "double_click", "right_click"):
            if x is not None and y is not None:
                pag.moveTo(int(x), int(y), duration=0.2)
            if action == "double_click":
                pag.doubleClick()
            elif action == "right_click":
                pag.rightClick()
            else:
                pag.click()
            return "Clicked."
        if action == "scroll":
            pag.scroll(int(x) if x is not None else -200)
            return "Scrolled."
        return "Unknown mouse action."
    except Exception as e:
        return f"Mouse action failed. Run setup.bat to install pyautogui. ({e})"


def system_info():
    lines = []
    lines.append(f"It is {datetime.now().strftime('%I:%M %p')} on {datetime.now().strftime('%A, %B %d')}.")
    try:
        ps = _psutil()
        cpu = ps.cpu_percent(interval=0.3)
        ram = ps.virtual_memory().percent
        lines.append(f"CPU is at {cpu:.0f} percent and memory at {ram:.0f} percent.")
        bat = ps.sensors_battery()
        if bat:
            plug = ", charging" if bat.power_plugged else ""
            lines.append(f"Battery is at {bat.percent:.0f} percent{plug}.")
    except Exception:
        pass
    return " ".join(l for l in lines if l)


def power_action(action):
    confirm_words = ("confirm", "yes", "do it", "sure")
    if _state.get("awaiting_" + action) and any(w in _state["last_text"] for w in confirm_words):
        cmds = {
            "shutdown": "shutdown /s /t 5",
            "restart": "shutdown /r /t 5",
        }
        if action == "sleep":
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        else:
            subprocess.Popen(cmds[action], shell=True)
        _state.pop("awaiting_" + action, None)
        return f"{action.capitalize()}ing now."
    if action in ("shutdown", "restart", "sleep"):
        _state["awaiting_" + action] = True
        return f"Are you sure you want me to {action}? Say confirm to proceed."
    try:
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], shell=True)
        return "Locking your PC."
    except Exception as e:
        return f"Failed: {e}"


def handle_send_whatsapp(text):
    t = " " + re.sub(r"^(?:jarvis|hey jarvis|richie|hey richie|richie jarvis|hey richie jarvis)[, ]*", "", text.strip().lower()) + " "
    if not re.search(r"\b(send|chat|message|text)\b", t):
        return None
    body = re.sub(r"^\s*(?:send(?:\s+(?:a\s+)?(?:chat|message|text|whatsapp))?|chat|message|text)\s+(?:to\s+)?",
                  "", t).strip()
    if not body:
        return None
    parts = re.split(r"\b(?:saying|that|message|:|-)\b", body, maxsplit=1)
    contact_part = parts[0].strip()
    msg = parts[1].strip() if len(parts) > 1 else ""
    name, num = resolve_contact(contact_part)
    if not num:
        words = contact_part.split()
        for i in (3, 2, 1):
            if len(words) >= i:
                name, num = resolve_contact(" ".join(words[:i]))
                if num:
                    if not msg:
                        msg = " ".join(words[i:]).strip()
                    break
    if not num:
        return send_chat((contact_part + (" " + msg if msg else "")).strip())
    return send_whatsapp_message(num, msg)


def parse_command(text):
    t = text.strip().lower()
    t = re.sub(r"\b(jarvis|hey jarvis|ok jarvis|richie|hey richie|richie jarvis|ok richie jarvis)\b", "", t).strip(" ,.!?")

    # ---- live conversation: calls and chats -----------------------------
    # These come before the generic "stop" rule so "stop talking" ends the
    # conversation instead of everything else.
    m = re.match(r"^(?:call|conversation|talk)(?:\s+mode)?\s+(on|off|start|stop)"
                 r"(?:\s+(?:on|in|for)?\s*(whatsapp|discord|telegram|zoom|meet|teams|messenger))?$", t)
    if m:
        if m.group(1) in ("on", "start"):
            _state["abort"] = False
            return start_session("call", app=m.group(2) or "")[1]
        stop_session()
        return "I stopped talking. The call is all yours again."

    if re.search(r"^(?:talk to (?:them|him|her|the person)|answer (?:it|for me|the call)|"
                 r"take (?:the|this) call|you (?:talk|speak|handle it|take over)|"
                 r"handle (?:this|the) call|speak for me)\b", t):
        _state["abort"] = False
        return start_session("call")[1]

    if re.search(r"^(?:stop talking|i(?:'ll| will| am gonna)? ?take (?:it|over|from here)|"
                 r"my turn|that's enough|thats enough)\b", t):
        stop_session()
        return "Understood, I am out of the conversation."

    if re.search(r"^(?:go quiet|stay quiet|mute yourself|stop answering)\b", t):
        if _ENGINE and _ENGINE.active:
            _ENGINE.session.muted = True
            return "I will stay quiet unless you ask me to say something."
        return "There is no call for me to go quiet in."

    if re.search(r"^(?:you can talk|speak again|unmute yourself|start answering)\b", t):
        if _ENGINE and _ENGINE.active:
            _ENGINE.session.muted = False
            return "I am back in the conversation."
        return "There is no call to rejoin. Say 'call mode on' first."

    m = re.match(r"^chat(?:\s+mode)?\s+(on|off|start|stop)"
                 r"(?:\s+(?:on|in|with)?\s*(whatsapp|discord|telegram|zoom|meet|teams|messenger|[a-z]+))?$", t)
    if m:
        if m.group(1) in ("on", "start"):
            app = m.group(2) or ""
            if app and app not in (appslib.APP_PROFILES if appslib else {}):
                # sounds like a person, not an app: open their chat first
                name, num = resolve_contact(app)
                if num:
                    send_whatsapp_message(num, "")
                    time.sleep(3)
                    app = "whatsapp"
            _state["abort"] = False
            return start_session("chat", app=app)[1]
        stop_session()
        return "I stopped watching the chat."

    if re.match(r"^(?:read|check)\s+(?:the\s+)?(?:chat|messages?|conversation|last messages?)$", t):
        res = appslib.read_chat() if appslib else {"ok": False, "text": "", "error": "apps.py missing"}
        text = (res.get("text") or "").strip()
        if not text:
            return "I could not read the chat. %s" % (res.get("error") or "")
        tail = "\n".join([l for l in text.splitlines() if l.strip()][-6:])
        _set_artifact("chat", "chat · %s" % (res.get("app") or "unknown"),
                      "%d characters read" % len(text),
                      svg="", path="")
        return "Latest from %s: %s" % (res.get("app") or "the chat", tail[:600])

    m = re.match(r"^(?:reply|respond|say back|answer)\s+(.+)$", t)
    if m:
        text = m.group(1).strip()
        res = appslib.send_chat_text(text) if appslib else {"ok": True, "app": ""}
        return "Replied in %s: %s" % (res.get("app") or "the chat", text)

    if re.search(r"^(?:what|which)\s+(?:call|calls?)(\s+is\s+(?:this|live|on))?$", t) or \
       re.search(r"^am i (?:in|on) a call$", t):
        if not appslib:
            return "Call detection is unavailable."
        calls = appslib.detect_calls(appslib.windows())
        if not calls:
            return "I cannot see a call right now."
        return "Looks like: " + ", ".join(
            "%s (%s) - %s" % (c["title"][:40], c["app"], c["confidence"]) for c in calls[:3])

    if re.search(r"^(?:list\s+)?(?:audio|sound)\s*devices?$", t):
        info = audio_devices()
        if info.get("error") or not info.get("devices"):
            return "I could not list audio devices. %s" % (info.get("error") or "")
        return "Playback devices: " + ", ".join(
            d["name"] + (" [cable]" if d.get("virtual") else "")
            for d in info["devices"][:8])

    m = re.match(r"^(?:use|speak (?:through|on|via)|set)\s+(?:the\s+)?(?:audio\s+)?device\s+(.+)$", t)
    if m:
        idx, resolved = find_output_device(m.group(1))
        if idx is None:
            known = audio_devices().get("devices") or []
            return "I cannot find a device called %s. I see: %s" % (
                m.group(1), ", ".join(d["name"] for d in known[:6]) or "nothing")
        cfg = load_config()
        cfg["voice_device"] = resolved
        save_config(cfg)
        return "Speaking through %s from now on." % resolved

    # ---- emergency stop -------------------------------------------------
    if re.search(r"^(?:stop|abort|halt|freeze|cancel|emergency)\b", t):
        _state["abort"] = True
        return "Stopped. I am not moving anything."

    # ---- draw / model / mouse shortcuts (work with no brain connected) ---
    m = re.match(r"^(?:draw|sketch|paint)\s+(?:me\s+)?(?:a|an|the)?\s*(.+)$", t)
    if m and drawlib:
        what = re.sub(r"\b(?:please|here|in\s+the\s+middle|centered?|centre|center)\b",
                      "", m.group(1)).strip(" .!?")
        for cand in (what, " ".join(what.split()[-2:]), what.split()[-1] if what.split() else ""):
            cand = cand.strip()
            if cand in drawlib.PICTURES:
                return _logged("picture", {"name": cand}, draw_action({"picture": cand}))
            if cand in drawlib.SHAPES:
                return _logged("draw", {"shape": cand}, draw_action({"shape": cand}))

    m = re.match(r"^(?:make|create|build|generate|model)\s+(?:me\s+)?(?:a|an|the)?\s*(.+?)(?:\s+model)?$", t)
    if m and m3d:
        what = m.group(1).strip()
        for cand in (what, " ".join(what.split()[-2:]), what.split()[-1] if what.split() else ""):
            cand = re.sub(r"^3d\s+", "", cand).strip()
            if cand in m3d.MODELS:
                return _logged("model3d", {"kind": cand}, model3d_action({"kind": cand}))

    m = re.match(r"^(?:move|put|slide)\s+(?:the\s+)?(?:mouse|cursor|pointer)\s+to\s+(\d+)\s*[, ]\s*(\d+)$", t)
    if m:
        x, y = int(m.group(1)), int(m.group(2))
        try:
            out = "Moved the mouse to %d,%d." % (x, y) if mouse_move_to(x, y, 0.5) else "Stopped."
        except Exception:
            out = "I cannot move the mouse. Run setup.bat to install pyautogui."
        return _logged("mouse", {"op": "move", "x": x, "y": y}, out)

    if re.match(r"^(?:move|put)\s+(?:the\s+)?(?:mouse|cursor|pointer)\s+to\s+the\s+(?:centre|center|middle)$", t):
        w, h = _screen_size()
        try:
            out = "Moved the mouse to the middle." if mouse_move_to(w // 2, h // 2, 0.5) else "Stopped."
        except Exception:
            out = "I cannot move the mouse. Run setup.bat to install pyautogui."
        return _logged("mouse", {"op": "move", "x": w // 2, "y": h // 2}, out)

    if re.search(r"^where(?:\s+i)?s?\s+(?:the\s+)?(?:mouse|cursor|pointer)\b", t):
        return mouse_now()

    m = re.match(r"^(?:(double|right|middle)\s+)?click(?:\s+at\s+(\d+)\s*[, ]\s*(\d+))?$", t)
    if m:
        kind, xs, ys = m.group(1), m.group(2), m.group(3)
        pos = (int(xs), int(ys)) if xs and ys else None
        try:
            pag = _pyautogui()
            if pos and not mouse_move_to(pos[0], pos[1], 0.35):
                return "Stopped."
            if kind == "double":
                pag.doubleClick()
            elif kind == "right":
                pag.rightClick()
            elif kind == "middle":
                pag.middleClick()
            else:
                pag.click()
            out = "Clicked%s." % (" at %d,%d" % pos if pos else "")
        except Exception:
            out = "I cannot click. Run setup.bat to install pyautogui."
        return _logged("mouse", {"op": (kind or "click"), "x": pos[0] if pos else None,
                                 "y": pos[1] if pos else None}, out)

    m = re.match(r"^(?:set\s+)?(?:mouse\s+)?speed\s+(slow|normal|fast|turbo)$", t)
    if m:
        value = {"slow": 0.5, "normal": 1.0, "fast": 1.8, "turbo": 3.0}[m.group(1)]
        cfg = load_config()
        cfg["speed"] = value
        save_config(cfg)
        return "Mouse speed set to %s." % m.group(1)

    if re.search(r"^(?:list|what are)\s+(?:the\s+)?(?:free\s+)?models\b", t):
        try:
            free = fetch_free_models(load_config(), force=True)[:12]
            return "Free models right now: " + ", ".join(m["id"] for m in free)
        except Exception as e:
            return "I could not reach the model list. %s" % e

    if re.search(r"^(listen(?:ing)? mode|call assis(?:tant|tance)|ear mode)(?:\s+(?:on|start|enable))?$", t):
        if not os.path.isdir(STT_MODEL_DIR):
            return "My speech brain is missing. Run setup.bat again."
        _state["listen"] = True
        cfg = load_config()
        cfg["listen"] = True
        save_config(cfg)
        ensure_listener()
        return ("Listen mode on. I am now hearing everything your PC plays - "
                "in a call, just talk normally and I will answer for you.")

    if re.search(r"^(?:listen(?:ing)? mode|call assis(?:tant|tance)|ear mode)\s+(?:off|stop|disable)$", t):
        _state["listen"] = False
        cfg = load_config()
        cfg["listen"] = False
        save_config(cfg)
        return "Listen mode off. I hear nothing anymore."

    if re.search(r"\b(my name|who am i)\b", t):
        return f"You are {contact_owner()}, sir. My boss."

    m = re.match(r"^(?:say|tell them|talk)\s+(.+)$", t)
    if m:
        _speak_aloud(m.group(1))
        return f"Speaking aloud: {m.group(1)}"

    if re.search(r"(secretary|auto answer|autoanswer)\s*(mode)?\s*(on|enable|start)$", t) \
            or t in ("secretary mode", "auto answer"):
        _state["secretary"] = True
        cfg = load_config()
        cfg["secretary"] = True
        save_config(cfg)
        ensure_secretary()
        return ("Secretary mode on. I will watch for incoming calls, answer them, "
                "and tell them you are unavailable. Tip: say set answer button so I "
                "click the right spot.")

    if re.search(r"(secretary|auto answer|autoanswer)\s*(mode)?\s*(off|disable|stop)$", t):
        _state["secretary"] = False
        cfg = load_config()
        cfg["secretary"] = False
        save_config(cfg)
        return "Secretary mode off. Calls are all yours again."

    if re.search(r"^set( the)? answer button$|^calibrate answer$", t):
        set_answer_button()
        return "Hover your mouse over the green answer button - I will memorize it in 6 seconds."

    m = re.match(r"^(?:open url|go to|visit)\s+(.+)$", t)
    if m:
        return open_url(m.group(1))

    m = re.match(r"^(?:run command|execute|shell)\s+(.+)$", t)
    if m:
        return run_command(m.group(1))

    m = re.match(r"^(?:open|launch|start|run)\s+(.+)$", t)
    if m:
        return open_app(m.group(1))

    m = re.match(r"^(?:call|ring|dial|phone)\s+(.+?)(?:\s+on\s+whatsapp)?$|^whatsapp\s+(?:call|video call)?\s*(.+)$", t)
    if m:
        who = m.group(1) or m.group(2)
        return whatsapp_call(who, video="video" in t)

    m = re.search(r"^(?:search(?: for)?|look up)\s+(youtube|wikipedia|google)\s+(.+)$", t)
    if m:
        return search_web(m.group(2), m.group(1))
    m = re.search(r"^(?:search(?: for)?|look up)\s+(.+?)\s+(?:on\s+)?(youtube|wikipedia)$", t)
    if m:
        return search_web(m.group(1), m.group(2))
    m = re.search(r"^(?:search(?: for)?|look up)\s+(.+)$", t)
    if m:
        return search_web(m.group(1), "google")
    m = re.search(r"^youtube\s+(.+)$", t)
    if m:
        return search_web(m.group(1), "youtube")

    if re.search(r"\bscreenshot\b", t):
        return do_screenshot()

    if re.match(r"^(type|write)\s+(.+)$", t):
        payload = re.match(r"^(type|write)\s+(.+)$", t).group(2)
        return type_text(payload)

    if re.search(r"press enter|hit enter", t):
        return press_key("enter")

    if re.search(r"volume up", t):
        n = len(re.findall(r"up", t))
        return press_key("volumeup", max(1, n))

    if re.search(r"volume down|turn it down|lower the volume", t):
        return press_key("volumedown")

    if re.search(r"\bmute\b|\bunmute\b", t):
        return press_key("volumemute")

    if re.search(r"play music|pause music|play pause|resume music|next song|skip song|previous song", t):
        if "next" in t:
            return press_key("nexttrack")
        if "previous" in t:
            return press_key("prevtrack")
        return press_key("playpause")

    if re.search(r"time|date|today|battery|cpu|ram|memory|system status|how are you", t):
        return system_info()

    if re.search(r"\block\b.*\bpc\b|\block\b.*\bcomputer\b|\block the pc\b|^lock$", t):
        return power_action("lock")

    if re.search(r"shut ?down", t):
        return power_action("shutdown")

    if re.search(r"restart|reboot", t):
        return power_action("restart")

    if re.search(r"\bsleep\b|\bgood night\b", t):
        return power_action("sleep")

    if re.match(r"^(hi|hello|hey|who are you|what can you do|help)\b", t):
        return ("Hello sir. I am Richie Jarvis, running locally on your machine. "
                "I can drive the mouse: say draw a circle, draw a cat, make a robot "
                "for a 3D model, move the mouse to 900 500, or click at 300 300. "
                "I also do open notepad, search youtube lofi beats, screenshot, "
                "volume up, open url google.com, run command dir, "
                "and call someone on whatsapp. Say stop at any time.")

    sent = handle_send_whatsapp(text)
    if sent is not None:
        return sent

    if re.search(r"\b(what(?:'s| is)?\s+(?:app|program|window|application)|active (?:window|app)|which (?:app|program|window|application)|currently (?:open|focused)|front (?:window|app))\b", t):
        info = get_active_window()
        return f"You are looking at {info.get('app') or '?'} — window title: {info.get('title') or '(none)'}."

    if re.search(r"\b(running apps|open (?:apps|programs|applications)|list (?:apps|programs|applications)|what(?:'s| is)?\s+running|task\s*list)\b", t):
        return "Running apps: " + ", ".join(list_running_apps())

    return None


# --------------------------------------------------------------------------
# audio routing
#
# To be heard inside a call, Jarvis has to speak into the app's microphone.
# On Windows that means a virtual audio cable (VB-CABLE / VoiceMeeter): the
# app uses "CABLE Output" as its mic, and Jarvis plays to "CABLE Input".
# System.Speech can only pick the default device, so we synthesise to a WAV
# and play it through the device we want with pyaudiowpatch.
# --------------------------------------------------------------------------

def audio_devices():
    """Playback devices, with virtual cables flagged."""
    try:
        import pyaudiowpatch as pw
    except Exception as e:
        return {"devices": [], "error": "pyaudiowpatch is not installed (%s)" % e}
    out = []
    try:
        with pw.PyAudio() as pa:
            default = -1
            try:
                wasapi = pa.get_host_api_info_by_type(pw.paWASAPI)
                default = int(wasapi.get("defaultOutputDevice", -1))
            except Exception:
                pass
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if int(info.get("maxOutputChannels", 0) or 0) <= 0:
                    continue
                name = str(info.get("name", "") or "")
                out.append({
                    "index": i,
                    "name": name,
                    "channels": int(info.get("maxOutputChannels", 0) or 0),
                    "rate": int(info.get("defaultSampleRate", 0) or 0),
                    "default": i == default,
                    "virtual": bool(re.search(r"cable|voicemeeter|virtual|vb-audio|mix",
                                              name, re.I)),
                })
    except Exception as e:
        return {"devices": out, "error": str(e)}
    return {"devices": out, "error": ""}


def find_output_device(want):
    """Resolve a device name (or substring) to ``(index, name)``."""
    want = str(want or "").strip().lower()
    if not want:
        return None, None
    info = audio_devices()
    devices = info.get("devices") or []
    for d in devices:
        if d["name"].lower() == want:
            return d["index"], d["name"]
    for d in devices:
        if want in d["name"].lower():
            return d["index"], d["name"]
    return None, None


def _tts_to_wav(text, path):
    """Synthesise speech into a WAV file using the Windows voice."""
    esc = str(text).replace("'", "''")
    ps = ("Add-Type -AssemblyName System.Speech; "
          "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "$s.Rate = 0; $s.SetOutputToWaveFile('%s'); $s.Speak('%s'); $s.Dispose()"
          % (path.replace("'", "''"), esc))
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", ps], creationflags=flags, timeout=120,
                       capture_output=True)
    except Exception as e:
        print("[jarvis] wav synth failed:", e)
        return False
    return os.path.isfile(path) and os.path.getsize(path) > 1024


def speak_through_device(text, device=None):
    """Speak into a specific output device. False = caller should fall back."""
    want = (device or load_config().get("voice_device") or "").strip()
    if not want:
        return False
    idx, name = find_output_device(want)
    if idx is None:
        print("[jarvis] audio device %r not found - using the default" % want)
        return False
    try:
        import pyaudiowpatch as pw
        import wave
    except Exception:
        return False
    tmp = os.path.join(tempfile.gettempdir(), "jarvis_say_%d.wav" % int(time.time() * 1000))
    try:
        if not _tts_to_wav(text, tmp):
            return False
        with wave.open(tmp, "rb") as wf:
            with pw.PyAudio() as pa:
                stream = pa.open(
                    format=pa.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True, output_device_index=idx)
                try:
                    data = wf.readframes(4096)
                    while data:
                        if _state.get("abort"):
                            break
                        stream.write(data)
                        data = wf.readframes(4096)
                finally:
                    stream.stop_stream()
                    stream.close()
        return True
    except Exception as e:
        print("[jarvis] device playback failed:", e)
        return False
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


# --------------------------------------------------------------------------
# live conversation sessions (calls and chats)
# --------------------------------------------------------------------------

_ENGINE = None
_CHAT_POLL = {"thread": None}


def _session_brain(system, history, prompt):
    """Ask the configured brain for the next line of the conversation."""
    cfg = load_config()
    messages = [{"role": "system", "content": system}]
    for who, text in history:
        role = "assistant" if str(who).lower().startswith("jarvis") else "user"
        if role == "user":
            messages.append({"role": "user", "content": text})
        else:
            messages.append({"role": "assistant", "content": text})
    messages.append({"role": "user", "content": prompt})
    msg, err = _call_brain(messages, cfg, max_tokens=140, temperature=0.75)
    if msg is None:
        raise RuntimeError(err or "brain unavailable")
    reply = (msg.get("content") or "").strip()
    # models sometimes wrap the line in quotes or fences
    reply = re.sub(r"^```[a-zA-Z]*\n?", "", reply)
    reply = re.sub(r"\n?```$", "", reply).strip().strip('"').strip()
    return reply.split("\n")[0].strip() or reply


def _session_speak(text):
    # guarded: it mutes the loopback while we talk so the mic does not
    # transcribe Jarvis's own voice and answer itself
    _talk_aloud_guarded(text)


def _session_send(text):
    app = (engine().session.app if engine().session else "") or ""
    if appslib:
        appslib.send_chat_text(text, app=app)
    else:                # pragma: no cover
        send_chat(text)


def engine():
    global _ENGINE
    if _ENGINE is None:
        if converselib is None:      # pragma: no cover
            raise RuntimeError("converse.py is missing")
        _ENGINE = converselib.ConversationEngine(
            brain=_session_brain, speak=_session_speak, send=_session_send,
            owner=contact_owner(), log=lambda m: print("[jarvis] session:", m))
    return _ENGINE


def start_session(kind="call", app="", who="", medium=""):
    """Begin talking for you. Returns (session_dict, spoken_confirmation)."""
    eng = engine()
    app = (app or appslib.active_app() if appslib else app) or ""
    if not who:
        calls = appslib.detect_calls(appslib.windows()) if appslib else []
        for c in calls:
            if not app or c["app"] == app:
                who = _guess_who(c.get("title") or "")
                break
    sess = eng.start(kind=kind, app=app, who=who, medium=medium or kind)
    _state["session"] = True
    if kind == "chat" and app:
        _start_chat_poll(app)
    label = (appslib.profile(app).get("label") if appslib else app) or app or "the call"
    return sess.status(), ("I am on it. I will talk to them in %s. "
                           "Say stop talking when you want me out." % label)


def stop_session():
    eng = engine()
    sess = eng.stop()
    _state["session"] = False
    turns = sess.turns if sess else 0
    return {"stopped": True, "turns": turns}


def _guess_who(title):
    """Pull a plausible person/channel name out of a call window title."""
    t = re.sub(r"\s*[-|]\s*(whatsapp|discord|zoom|meet|teams|telegram|messenger)\s*$",
               "", str(title or ""), flags=re.I)
    t = re.sub(r"^\s*(whatsapp|discord|zoom|meet|teams|telegram|messenger)\s*[-|]\s*",
               "", t, flags=re.I)
    # "Zoom Meeting" / "Teams meeting": the app name leads but has no separator
    t = re.sub(r"^\s*(whatsapp|discord|zoom|meet|teams|telegram|messenger)\b\s*",
               "", t, flags=re.I)
    t = re.sub(r"\b(\d{1,2}:\d{2}(:\d{2})?|incoming call|ongoing call|voice call|"
               r"video call|meeting|call|🔊)\b", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" -|:|—")
    return t[:48]


def _tail_after(text, previous):
    """New part of a scraped transcript since the last poll."""
    text = str(text or "")
    previous = str(previous or "")
    if not previous:
        return text
    if text.startswith(previous):
        return text[len(previous):]
    idx = text.find(previous)
    if idx >= 0:
        return text[idx + len(previous):]
    # transcript scrolled: fall back to the last few lines
    return "\n".join([l for l in text.splitlines() if l.strip()][-3:])


def _chat_poll_loop(app, interval=6.0):
    """Watch a chat window and reply when new text shows up."""
    import time as _t
    last = ""
    while engine().active and not _state.get("abort"):
        _t.sleep(interval)
        sess = engine().session
        if not sess or sess.kind != "chat" or not sess.auto:
            continue
        # never fire select-all/copy into an unrelated app: it would clobber
        # the clipboard and could disturb whatever the user is typing
        try:
            if app and appslib:
                front = appslib.active_app()
                if front and front != app:
                    continue
        except Exception:
            pass
        try:
            res = appslib.read_chat(app=app) if appslib else {"text": ""}
        except Exception as e:
            print("[jarvis] chat poll error:", e)
            continue
        text = (res or {}).get("text") or ""
        if not text or text == last:
            continue
        new = _tail_after(text, last).strip()
        last = text
        if len(new) < 2:
            continue
        try:
            reply = engine().hear(new)
        except Exception as e:
            print("[jarvis] chat reply failed:", e)
            continue
        if reply:
            print("[jarvis] chat reply: %r" % reply)


def _start_chat_poll(app):
    if _CHAT_POLL.get("thread") and _CHAT_POLL["thread"].is_alive():
        return
    t = threading.Thread(target=_chat_poll_loop, args=(app,), daemon=True)
    _CHAT_POLL["thread"] = t
    t.start()


def session_state():
    eng = _ENGINE
    if eng is None or not eng.active:
        return {"active": False, "transcript": []}
    st = eng.status()
    st["transcript"] = eng.session.transcript(40)
    return st
# Model lists are cached per provider, so flipping between OpenRouter, Gemini
# and Puter does not show a stale line-up.
_FREE_MODEL_CACHE = {"by_provider": {}, "lock": threading.Lock()}
_MODEL_CACHE_TTL = 900.0

# Gemini serves image/video/TTS/embedding models from the same endpoint; only
# text generators can drive Jarvis.
_GEMINI_SKIP = ("image", "imagen", "veo", "banana", "tts", "live", "transcribe",
                "embed", "aqa", "omni", "speech", "translate", "pro-preview")


def _gemini_model_rank(mid):
    """Free Flash models first, newest first, paid Pro models last."""
    low = mid.lower()
    if "flash-lite" in low or "lite" in low:
        tier = 0
    elif "flash" in low or low.startswith("gemma"):
        tier = 1
    else:
        tier = 2
    m = re.search(r"(\d+)(?:\.(\d+))?", low)
    ver = (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)
    return (tier, -ver[0], -ver[1], low)


def _fetch_gemini_models(cfg):
    base = cfg_base_url(cfg).rstrip("/") or PROVIDERS["gemini"]["base_url"]
    data = _http_json(base + "/models?pageSize=200", None, cfg, _brain_headers(cfg),
                      timeout=25)
    out = []
    for m in data.get("models") or []:
        name = str(m.get("name") or "").replace("models/", "").strip()
        if not name:
            continue
        methods = m.get("supportedGenerationMethods") or []
        if methods and "generateContent" not in methods:
            continue
        low = name.lower()
        if any(skip in low for skip in _GEMINI_SKIP):
            continue
        out.append({
            "id": name,
            "name": str(m.get("displayName") or name),
            "context": int(m.get("inputTokenLimit") or 0),
            "tools": True,          # every Gemini text model does function calling
            "free": ("flash" in low or "lite" in low or low.startswith("gemma")),
        })
    out.sort(key=lambda x: (not x["free"], _gemini_model_rank(x["id"])))
    return out


def _fetch_openai_models(cfg):
    provider = cfg_provider(cfg)
    url = cfg_base_url(cfg).rstrip("/") + "/models"
    if not url.startswith("http"):
        raise RuntimeError("no API base url configured")
    data = _http_json(url, None, cfg, _brain_headers(cfg), timeout=25)
    items = data.get("data") or []
    out = []
    for m in items:
        mid = str(m.get("id") or "").strip()
        if not mid:
            continue
        pricing = m.get("pricing") or {}
        try:
            cost = float(pricing.get("prompt") or 0)
        except (TypeError, ValueError):
            cost = 0.0
        free = mid.endswith(":free") or cost == 0.0
        if not free:
            continue
        sup = m.get("supported_parameters") or []
        out.append({
            "id": mid,
            "name": str(m.get("name") or mid),
            "context": int(m.get("context_length") or 0),
            "tools": bool((not sup) or ("tools" in sup) or provider != "openrouter"),
            "free": True,
        })
    out.sort(key=lambda x: (not x["tools"], -x["context"]))
    return out


def fetch_free_models(cfg, force=False):
    """Free models offered by the current provider, best first.

    Ranked so tool-capable models with the largest context come first, which
    is exactly what a PC-controlling assistant wants. Cached for 15 minutes.
    """
    provider = cfg_provider(cfg)
    with _FREE_MODEL_CACHE["lock"]:
        hit = _FREE_MODEL_CACHE["by_provider"].get(provider)
        if hit and not force and (time.time() - hit[1]) < _MODEL_CACHE_TTL:
            return list(hit[0])

    if provider == "puter":
        models = puter_models()
        if not models:
            if not puter_alive():
                raise RuntimeError("open the Jarvis dashboard so Puter.js can report "
                                   "its free model list")
            raise RuntimeError("Puter.js has not reported its models yet - wait a "
                               "moment and hit refresh")
    elif not cfg_api_key(cfg):
        raise RuntimeError("no API key saved yet"
                           + (" - get a free one at aistudio.google.com/apikey"
                              if provider == "gemini" else ""))
    elif provider == "gemini":
        models = _fetch_gemini_models(cfg)
    else:
        models = _fetch_openai_models(cfg)

    with _FREE_MODEL_CACHE["lock"]:
        _FREE_MODEL_CACHE["by_provider"][provider] = (list(models), time.time())
    return models


def clear_model_cache(provider=None):
    with _FREE_MODEL_CACHE["lock"]:
        if provider:
            _FREE_MODEL_CACHE["by_provider"].pop(provider, None)
        else:
            _FREE_MODEL_CACHE["by_provider"].clear()
    _state["free_models"] = None


def verify_key(cfg):
    """Tiny round trip to prove the key/model actually work."""
    if not brain_ready(cfg):
        return {"ok": False,
                "message": (_no_brain_message(cfg) if cfg_provider(cfg) == "puter"
                            else "no API key saved yet")}
    msg, err = _call_brain(
        [{"role": "user", "content": "Reply with the single word: ready"}],
        cfg, max_tokens=16, temperature=0.1)
    if msg is None:
        return {"ok": False, "message": err or "unknown error"}
    return {"ok": True,
            "message": (msg.get("content") or "").strip()[:120] or "ready",
            "model": _state.get("last_model", "")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[richie]", fmt % args)

    # ---- helpers --------------------------------------------------------
    def _cors(self):
        """Only allow pages served from this machine.

        A wildcard here would let any website you visit drive the mouse and
        run shell commands through localhost:8765.
        """
        origin = self.headers.get("Origin") or ""
        if re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", origin) or \
           origin.endswith(".e2b.app") or origin.endswith(".arena.ai"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, code, data, ctype="application/json"):
        if isinstance(data, dict):
            body = json.dumps(data).encode()
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The Puter.js relay long-polls /puter/jobs, so a tab being closed
            # or reloaded mid-reply is normal - not worth a traceback.
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return {}

    # ---- GET ------------------------------------------------------------
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(BASE_DIR, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html")
            return
        if path == "/health":
            cfg = load_config()
            w, h = _screen_size()
            self._send(200, {"status": "ok", "version": VERSION,
                             "time": datetime.now().isoformat(timespec="seconds"),
                             "brain": brain_ready(cfg),
                             "provider": cfg_provider(cfg),
                             "puter": puter_status()["relay"] if cfg_provider(cfg) == "puter" else None,
                             "model": cfg_model(cfg),
                             "last_model": _state.get("last_model", ""),
                             "screen": [w, h],
                             "tools": bool(_state.get("tools_ok", True))})
            return
        if path == "/providers":
            self._send(200, {"providers": [
                dict(id=pid, **{k: v for k, v in spec.items() if k != "key_env"})
                for pid, spec in PROVIDERS.items()],
                "puter": puter_status()})
            return
        if path == "/puter/status":
            self._send(200, puter_status())
            return
        if path == "/puter/jobs":
            # Long-poll: the dashboard tab parks here until there is work.
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                wait = min(55.0, max(0.0, float((qs.get("wait") or ["20"])[0])))
            except (TypeError, ValueError):
                wait = 20.0
            job = puter_claim(wait)
            self._send(200, {"job": job, "relay": True, "server_time": time.time()})
            return
        if path == "/config":
            cfg = load_config()
            provider = cfg_provider(cfg)
            key = cfg_api_key(cfg)
            models = []
            try:
                models = fetch_free_models(cfg)[:40]
            except Exception:
                models = []
            info = provider_info(cfg)
            self._send(200, {"has_key": bool(key), "key_masked": mask_key(key),
                             "needs_key": needs_key(cfg),
                             "brain": brain_ready(cfg),
                             "provider": provider,
                             "provider_label": info.get("label", ""),
                             "key_label": info.get("key_label", "API key"),
                             "key_hint": info.get("key_hint", ""),
                             "key_url": info.get("key_url", ""),
                             "base_url": cfg.get("base_url", ""),
                             "model": cfg.get("model", ""),
                             "model_default": cfg_model(cfg),
                             "fallbacks": cfg.get("fallbacks", []),
                             "models": models,
                             "puter": puter_status() if provider == "puter" else None,
                             "safe_mode": bool(cfg.get("safe_mode", True)),
                             "failsafe": bool(cfg.get("failsafe", True)),
                             "speed": cfg.get("speed", 1.0),
                             "max_actions": cfg.get("max_actions", 6)})
            return
        if path == "/models":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            cfg = load_config()
            want = str((qs.get("provider") or [""])[0]).strip().lower()
            if want in PROVIDERS and want != cfg_provider(cfg):
                # preview another provider's line-up without saving it yet
                cfg = dict(cfg, provider=want, model="", base_url="")
            try:
                models = fetch_free_models(cfg, force="refresh" in self.path)
                self._send(200, {"models": models, "count": len(models),
                                 "provider": cfg_provider(cfg)})
            except Exception as e:
                self._send(200, {"models": [], "count": 0, "error": str(e),
                                 "provider": cfg_provider(cfg)})
            return
        if path == "/artifact":
            self._send(200, {"artifact": _state.get("last_artifact")})
            return
        if path == "/actions":
            with _ACTION_LOG_LOCK:
                self._send(200, {"actions": list(_ACTION_LOG[-25:])})
            return
        if path == "/session":
            self._send(200, session_state())
            return
        if path == "/calls":
            calls = appslib.detect_calls(appslib.windows()) if appslib else []
            self._send(200, {"calls": calls, "count": len(calls)})
            return
        if path == "/audio/devices":
            info = audio_devices()
            info["current"] = load_config().get("voice_device", "")
            self._send(200, info)
            return
        self._send(404, {"error": "not found"})

    # ---- POST -----------------------------------------------------------
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        payload = self._body()

        if path == "/config":
            cfg = load_config()
            old_provider = cfg_provider(cfg)
            for key in ("provider", "model", "base_url"):
                val = payload.get(key, None)
                if isinstance(val, str):
                    cfg[key] = val.strip()
            # A key typed while a provider is selected lands in that provider's
            # own slot, so Gemini and OpenRouter keys survive a switch.
            for slot in SECRET_KEYS:
                val = payload.get(slot, None)
                if isinstance(val, str) and val.strip():
                    cfg[slot] = val.strip()
            typed = payload.get("api_key")
            if isinstance(typed, str) and typed.strip() and \
                    cfg_provider(cfg) == "gemini" and "gemini_api_key" not in payload:
                cfg["gemini_api_key"] = typed.strip()
            if isinstance(payload.get("fallbacks"), list):
                cfg["fallbacks"] = [str(x).strip() for x in payload["fallbacks"] if str(x).strip()]
            for key in ("safe_mode", "failsafe", "listen", "secretary"):
                if key in payload and isinstance(payload[key], bool):
                    cfg[key] = payload[key]
            for key in ("speed", "max_actions"):
                if key in payload:
                    try:
                        cfg[key] = float(payload[key]) if key == "speed" else int(payload[key])
                    except (TypeError, ValueError):
                        pass
            cfg["provider"] = cfg_provider(cfg)      # normalise legacy names
            save_config(cfg)
            _state["tools_ok"] = True          # new model may support tools
            clear_model_cache()                # provider may have changed
            if cfg_provider(cfg) != old_provider:
                _state["last_model"] = ""
            try:
                fetch_free_models(cfg, force=True)
            except Exception:
                pass
            provider = cfg_provider(cfg)
            self._send(200, {"saved": True, "has_key": bool(cfg_api_key(cfg)),
                             "needs_key": needs_key(cfg), "brain": brain_ready(cfg),
                             "model": cfg_model(cfg), "provider": provider,
                             "key_masked": mask_key(cfg_api_key(cfg)),
                             "puter": puter_status() if provider == "puter" else None})
            return

        # ---- Puter.js relay (the dashboard tab is the free brain) --------
        if path == "/puter/result":
            ok = puter_complete(payload.get("id"), {
                "ok": bool(payload.get("ok", True)),
                "message": payload.get("message") or {},
                "model": str(payload.get("model") or ""),
                "error": str(payload.get("error") or ""),
            })
            self._send(200, {"accepted": ok})
            return
        if path == "/puter/models":
            models = puter_set_models(payload.get("models") or [],
                                      payload.get("signed_in"))
            clear_model_cache("puter")
            self._send(200, {"saved": len(models), "models": models[:60]})
            return
        if path == "/puter/ping":
            with _PUTER["lock"]:
                _PUTER["last_seen"] = time.time()
                if payload.get("signed_in") is not None:
                    _PUTER["signed_in"] = bool(payload.get("signed_in"))
                if payload.get("version"):
                    _PUTER["version"] = str(payload.get("version"))[:20]
            self._send(200, puter_status())
            return

        if path == "/test":
            cfg = load_config()
            self._send(200, verify_key(cfg))
            return

        if path == "/abort":
            _state["abort"] = True
            released = False
            try:
                pag = _pyautogui()
                for button in ("left", "right", "middle"):
                    try:
                        pag.mouseUp(button=button)
                    except Exception:
                        pass
                released = True
            except Exception:
                pass
            print("[jarvis] ABORT - stopped everything")
            self._send(200, {"stopped": True, "released_mouse": released})
            return

        if path == "/chat":
            session = str(payload.get("session") or "default")[:64]
            text = (payload.get("text") or "").strip()
            if not text:
                self._send(200, {"reply": "Say something to chat."})
                return
            _state["abort"] = False
            _state["pending_artifact"] = None
            try:
                cmd = parse_command(text)
            except Exception as e:
                cmd = None
                print("[jarvis] chat command parse error:", e)
            if cmd is not None:
                print(f"[jarvis] chat-command({session}): {text!r} -> {cmd!r}")
                self._send(200, {"reply": cmd, "artifact": _state.get("pending_artifact")})
                return
            reply = chat_reply(session, text)
            print(f"[jarvis] chat({session}): {text!r} -> {reply!r}")
            self._send(200, {"reply": reply})
            return

        if path == "/session/start":
            _state["abort"] = False
            st, msg = start_session(
                str(payload.get("kind") or "call").strip().lower(),
                app=str(payload.get("app") or "").strip().lower(),
                who=str(payload.get("who") or "").strip())
            self._send(200, {"started": True, "session": st, "speak": msg})
            return
        if path == "/session/stop":
            self._send(200, stop_session())
            return
        if path == "/session/say":
            text = (payload.get("text") or "").strip()
            if not text:
                self._send(200, {"ok": False, "error": "nothing to say"})
                return
            if not (_ENGINE and _ENGINE.active):
                self._send(200, {"ok": False, "error": "no active session"})
                return
            engine().say(text)
            self._send(200, {"ok": True, "said": text})
            return
        if path == "/session/mute":
            muted = bool(payload.get("muted", True))
            if _ENGINE and _ENGINE.active:
                _ENGINE.session.muted = muted
            self._send(200, {"ok": True, "muted": muted})
            return
        if path == "/audio/use":
            idx, resolved = find_output_device(payload.get("device") or "")
            if idx is None:
                self._send(200, {"ok": False, "error": "device not found"})
                return
            cfg = load_config()
            cfg["voice_device"] = resolved
            save_config(cfg)
            self._send(200, {"ok": True, "device": resolved})
            return
        if path == "/chat/read":
            res = appslib.read_chat(app=str(payload.get("app") or "")) if appslib \
                else {"ok": False, "text": "", "error": "apps.py missing"}
            self._send(200, res)
            return

        if path != "/command":
            self._send(404, {"error": "not found"})
            return

        text = (payload.get("text") or "").strip()
        if not text:
            self._send(200, {"speak": "Say that again?"})
            return
        _state["last_text"] = text.lower()
        _state["abort"] = False
        _state["pending_artifact"] = None
        reply = parse_command(text)
        if reply is None:
            cfg = load_config()
            if brain_ready(cfg):
                print("[jarvis] asking the brain (%s/%s)..."
                      % (cfg_provider(cfg), cfg_model(cfg)))
                reply = llm_reply(text)
            if not reply:
                reply = ("I don't know how to do that yet. Connect my brain in settings, "
                         "or say help to hear what I can do.")
        print(f"[jarvis] heard: {text!r} -> {reply!r}")
        self._send(200, {"speak": reply,
                         "artifact": _state.get("pending_artifact"),
                         "model": _state.get("last_model", "")})


class JarvisServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    cfg = load_config()
    try:
        server = JarvisServer((HOST, PORT), Handler)
    except OSError:
        print(f"! ERROR: port {PORT} is already in use.")
        print("! Close the other Richie Jarvis window (or run: taskkill /f /im python.exe) and try again.")
        return
    print(f"* Richie Jarvis {VERSION} online -> http://localhost:{PORT}")
    print("* Open that address in Chrome/Edge, allow the microphone, and speak after saying 'Richie Jarvis'.")
    provider = cfg_provider(cfg)
    if provider == "puter":
        brain = "Puter.js relay (open the dashboard tab - no API key needed)"
    elif brain_ready(cfg):
        brain = "connected (%s)" % PROVIDERS[provider]["label"]
    else:
        brain = "NOT CONNECTED (open the gear icon)"
    print("* Provider: %s | model: %s | brain: %s"
          % (provider, cfg_model(cfg), brain))
    if HOST not in ("127.0.0.1", "localhost"):
        print(f"* WARNING: listening on {HOST} - anything on your network can drive this PC.")
    if load_config().get("secretary"):
        _state["secretary"] = True
    if load_config().get("listen"):
        _state["listen"] = True
    ap = load_config().get("answer_pos")
    if isinstance(ap, list) and len(ap) == 2:
        _state["answer_pos"] = tuple(ap)
    ensure_secretary()
    ensure_listener()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n* Richie Jarvis shutting down.")


if __name__ == "__main__":
    main()
