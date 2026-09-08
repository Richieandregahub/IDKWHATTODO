import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8765

_state = {"last_spoken": ""}


def _pyautogui():
    import pyautogui
    pyautogui.FAILSAFE = False
    return pyautogui


def _psutil():
    import psutil
    return psutil


APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "task manager": "taskmgr.exe",
    "settings": "ms-settings:",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "spotify": "spotify:",
    "whatsapp": "whatsapp:",
    "vs code": "code",
    "code": "code",
    "word": "winword",
    "excel": "excel",
}

CONTACTS_FILE = os.path.join(BASE_DIR, "contacts.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://opencode.ai/zen/v1",
    "model": "x-preview-f-free",
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    env_key = os.environ.get("OPENCODE_API_KEY")
    if not cfg.get("api_key") and env_key:
        cfg["api_key"] = env_key
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


SYSTEM_PROMPT = """You are Richie Jarvis, a witty AI butler running locally on the PC of your boss, {owner}.
You control the computer by returning actions. Reply with ONLY valid JSON, no markdown:
{"speak": "<short spoken reply, 1-2 sentences>", "action": null}
or
{"speak": "<short spoken confirmation>", "action": {"name": "...", "arg": "..."}}

Available actions:
{"name": "open_app", "arg": "<app like notepad, calculator, chrome, spotify, vs code>"}
{"name": "search_web", "arg": "<query>", "engine": "google|youtube|wikipedia"}
{"name": "screenshot"}
{"name": "press_key", "arg": "volumeup|volumedown|volumemute|playpause|nexttrack|prevtrack|enter"}
{"name": "type_text", "arg": "<text to type on the active window>"}
{"name": "send_chat", "arg": "<message to type AND send (press Enter) in the active, already-open chat window>"},
{"name": "whatsapp_message", "contact": "<phone number with country code OR a saved contact name like father, mother>", "message": "<the text to send>"}
{"name": "open_url", "arg": "<full url or domain like example.com>"}
{"name": "run_command", "arg": "<any Windows shell command, e.g. 'echo hi', 'dir', 'notepad file.txt'>"}
{"name": "mouse", "action": "click|double_click|right_click|move|scroll", "x": <int>, "y": <int>}
{"name": "whatsapp_call", "arg": "<phone number with country code or contact name>", "video": false}
{"name": "active_window", "arg": null}
{"name": "list_apps", "arg": null}
{"name": "say_aloud", "arg": "<text to speak through the speakers>"}

The PC owner's name is {owner}. If asked who they are or what their name is, answer "{owner}".
Family members are stored by relation: father, mother, etc.
Rules: If the user asks to do something on the computer, pick the matching action.
If asked to send a WhatsApp message to a SPECIFIC person (e.g. "message my father hello", "chat mother good night"), use whatsapp_message with the contact name/number and the message text. This opens their chat and sends it.
Only use send_chat when the user already has the right chat window open and focused and just wants text typed there.
If asked which app or window is currently focused/open, use active_window. To list running programs, use list_apps. You can detect ANY application this way, not only WhatsApp.
If asked to open a website, use open_url. If asked to run a program or shell task, use run_command.
If asked to click/move/scroll the mouse, use mouse with screen coordinates.
If asked to call someone (e.g. "call my father"), use whatsapp_call with the relation or name.
If it is a question or small talk, set action to null and answer briefly in speak.
run_command can do almost anything on this PC, so use it for tasks not covered by other actions.
Never output anything except the JSON object."""


def system_prompt():
    return SYSTEM_PROMPT.replace("{owner}", contact_owner())


FALLBACK_MODELS = ["mimo-v2.5-free", "hy3-free",
                   "nemotron-3.5-lightning-free", "laguna-s-2.1-free"]


def _candidate_models(cfg):
    models = []
    if cfg.get("model"):
        models.append(cfg["model"])
    for m in FALLBACK_MODELS:
        if m not in models:
            models.append(m)
    return models


def _call_brain(messages, max_tokens=300, temperature=0.5):
    """Send chat messages to the Zen brain. Returns (content, error)."""
    cfg = load_config()
    if not cfg.get("api_key"):
        return None, "no api key configured"
    last_err = "unknown error"
    for model in _candidate_models(cfg):
        for attempt in range(2):
            url = cfg["base_url"].rstrip("/") + "/chat/completions"
            payload = json.dumps({
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }).encode()
            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg['api_key']}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jarvis-local/1.0",
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8", "replace"))
                content = str(data["choices"][0]["message"]["content"] or "").strip()
                if not content:
                    last_err = f"model {model} returned empty content"
                    print(f"[jarvis] {last_err} - trying next...")
                    break
                return content, ""
            except urllib.error.HTTPError as e:
                try:
                    detail = json.loads(e.read().decode()).get("error", {}).get("message", "")
                except Exception:
                    detail = ""
                if e.code in (401, 403):
                    return None, "My brain rejected the API key. Open settings and paste a valid OpenCode Zen key."
                last_err = f"model {model} error {e.code}: {detail[:100]}"
                if e.code >= 500:
                    time.sleep(0.5)
                    continue
                break
            except Exception as e:
                last_err = str(e)
                time.sleep(0.5)
        print(f"[jarvis] model '{model}' failed ({last_err}) - trying fallback...")
    return None, last_err


def llm_reply(text):
    content, err = _call_brain([
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": text},
    ], max_tokens=220, temperature=0.4)
    if content is None:
        return f"I could not reach my brain. {err}"
    obj = {}
    m = re.search(r"\{.*\}", content, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
        except Exception:
            obj = {}
    elif content.startswith("{"):
        try:
            obj = json.loads(content)
        except Exception:
            obj = {}
    speak_text = str(obj.get("speak") or "").strip() or content.strip() or "Done."
    action = obj.get("action")
    if isinstance(action, dict) and action.get("name"):
        result = run_action(action)
        return result if result else speak_text
    return speak_text


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
    if not cfg.get("api_key"):
        return ("My brain isn't connected yet. Open the settings gear (top-right) and "
                "paste an OpenCode Zen API key, then I can chat with you.")
    with _CHAT_LOCK:
        hist = _CHAT_SESSIONS.setdefault(session, [])
        hist.append({"role": "user", "content": text})
        if len(hist) > 24:
            hist = hist[-24:]
            _CHAT_SESSIONS[session] = hist
        messages = [{"role": "system", "content": CHAT_SYSTEM}] + list(hist)
    content, err = _call_brain(messages, max_tokens=500, temperature=0.7)
    if content is None:
        return f"I couldn't reach my brain right now. {err}"
    reply = content.strip()
    if reply.startswith("```"):
        reply = re.sub(r"^```[a-zA-Z]*\n?", "", reply)
        reply = re.sub(r"\n?```$", "", reply).strip()
    with _CHAT_LOCK:
        hist.append({"role": "assistant", "content": reply})
        if len(hist) > 24:
            hist = hist[-24:]
            _CHAT_SESSIONS[session] = hist
    return reply


def run_action(action):
    name = action.get("name")
    arg = action.get("arg")
    try:
        if name == "open_app":
            return open_app(str(arg))
        if name == "search_web":
            return search_web(str(arg), action.get("engine", "google"))
        if name == "screenshot":
            return do_screenshot()
        if name == "press_key":
            return press_key(str(arg))
        if name == "type_text":
            return type_text(str(arg))
        if name == "send_chat":
            return send_chat(str(arg))
        if name == "open_url":
            return open_url(str(arg))
        if name == "run_command":
            return run_command(str(arg))
        if name == "mouse":
            return mouse_action(str(action.get("action", "click")),
                                action.get("x"), action.get("y"))
        if name == "whatsapp_call":
            return whatsapp_call(str(arg), video=bool(action.get("video")))
        if name == "whatsapp_message":
            return send_whatsapp_message(str(action.get("contact") or ""),
                                         str(action.get("message") or ""))
        if name == "active_window":
            info = get_active_window()
            app = info.get("app") or "unknown"
            title = info.get("title") or ""
            return f"Active window is {app} (title: {title or '(none)'})."
        if name == "list_apps":
            return "Running apps: " + ", ".join(list_running_apps())
        if name == "say_aloud":
            _speak_aloud(str(arg))
            return f"Speaking aloud: {arg}"
    except Exception as e:
        return f"Action failed. {e}"
    return None


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


def _speak_aloud(text):
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

    if re.search(r"^(?:listen(?:ing)? mode|call assis(?:tant|tance)|ear mode)(?:\s+(?:on|start|enable))?$", t):
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
                "Try: open notepad, search youtube lofi beats, screenshot, volume up, "
                "send chat hello there, open url google.com, run command dir, "
                "or call a number on whatsapp.")

    sent = handle_send_whatsapp(text)
    if sent is not None:
        return sent

    if re.search(r"\b(what(?:'s| is)?\s+(?:app|program|window|application)|active (?:window|app)|which (?:app|program|window|application)|currently (?:open|focused)|front (?:window|app))\b", t):
        info = get_active_window()
        return f"You are looking at {info.get('app') or '?'} — window title: {info.get('title') or '(none)'}."

    if re.search(r"\b(running apps|open (?:apps|programs|applications)|list (?:apps|programs|applications)|what(?:'s| is)?\s+running|task\s*list)\b", t):
        return "Running apps: " + ", ".join(list_running_apps())

    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[richie]", fmt % args)

    def _send(self, code, data, ctype="application/json"):
        if isinstance(data, dict):
            body = json.dumps(data).encode()
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(BASE_DIR, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html")
        elif path == "/health":
            cfg = load_config()
            self._send(200, {"status": "ok", "time": datetime.now().isoformat(timespec="seconds"),
                             "brain": bool(cfg.get("api_key")), "model": cfg.get("model", "")})
        elif path == "/config":
            cfg = load_config()
            key = cfg.get("api_key", "")
            masked = (key[:6] + "..." + key[-4:]) if len(key) > 12 else ("set" if key else "")
            self._send(200, {"has_key": bool(key), "key_masked": masked,
                             "model": cfg.get("model", ""), "base_url": cfg.get("base_url", "")})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            payload = {}
        if path == "/config":
            cfg = load_config()
            new_key = (payload.get("api_key") or "").strip()
            if new_key:
                cfg["api_key"] = new_key
            if payload.get("model", "").strip():
                cfg["model"] = payload["model"].strip()
            if payload.get("base_url", "").strip():
                cfg["base_url"] = payload["base_url"].strip()
            save_config(cfg)
            self._send(200, {"saved": True, "has_key": bool(cfg.get("api_key")), "model": cfg["model"]})
            return
        if path == "/chat":
            session = str(payload.get("session") or "default")[:64]
            text = (payload.get("text") or "").strip()
            if not text:
                self._send(200, {"reply": "Say something to chat."})
                return
            # commands typed in the chat box still run (open apps, whatsapp, etc.)
            try:
                cmd = parse_command(text)
            except Exception as e:
                cmd = None
                print("[jarvis] chat command parse error:", e)
            if cmd is not None:
                print(f"[jarvis] chat-command({session}): {text!r} -> {cmd!r}")
                self._send(200, {"reply": cmd})
                return
            reply = chat_reply(session, text)
            print(f"[jarvis] chat({session}): {text!r} -> {reply!r}")
            self._send(200, {"reply": reply})
            return
        if path != "/command":
            self._send(404, {"error": "not found"})
            return
        text = (payload.get("text") or "").strip()
        if not text:
            self._send(200, {"speak": "Say that again?"})
            return
        _state["last_text"] = text.lower()
        reply = parse_command(text)
        if reply is None:
            cfg = load_config()
            if cfg.get("api_key"):
                print("[jarvis] asking the Zen brain...")
                reply = llm_reply(text)
            if not reply:
                reply = ("I don't know how to do that yet. Connect my brain in settings, "
                         "or say help to hear what I can do.")
        print(f"[jarvis] heard: {text!r} -> {reply!r}")
        self._send(200, {"speak": reply})


class JarvisServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    try:
        server = JarvisServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"! ERROR: port {PORT} is already in use.")
        print("! Close the other Richie Jarvis window (or run: taskkill /f /im python.exe) and try again.")
        return
    print(f"* Richie Jarvis online -> http://localhost:{PORT}")
    print("* Open that address in Chrome/Edge, allow the microphone, and speak after saying 'Richie Jarvis'.")
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
