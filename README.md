# Richie Jarvis

A local AI butler for Windows. It runs a small Python server on
`localhost:8765`, serves one self-contained HTML page (animated "bit face",
voice input, chat panel), and lets a language model drive your PC: open apps,
move/click/drag the **real mouse**, draw pictures, generate 3D model files,
control windows, send WhatsApp messages and run shell commands.

Everything runs on your machine. The only thing that leaves it is the text you
send to whichever model provider you configure.

---

## Quick start

```bat
setup.bat          :: installs pyautogui / psutil / vosk (once)
start_jarvis.bat   :: starts the core and opens http://localhost:8765
```

Then click the **gear** icon in the top right and connect a brain.

## Connecting a free brain

Jarvis talks to any OpenAI-compatible endpoint. Two providers offer free
models today:

| Provider | Where to get a key | Free models |
|---|---|---|
| **OpenRouter** (recommended) | <https://openrouter.ai/keys> | dozens of `:free` models |
| **OpenCode Zen** | <https://opencode.ai/auth> | ~7 free models |

1. Paste the key in the settings panel.
2. Pick a model from the dropdown — it is fetched **live** from the provider
   and filtered to models that are free right now and support tool calling.
   Hit ⟳ to refresh; the free line-up rotates often.
3. Press **TEST**. If it comes back with a model name, you are done.

> Free models are rate limited: OpenRouter allows 50 requests/day on free
> models, or 1,000/day once you have bought $10 of credits. Jarvis keeps a
> fallback list and walks it automatically when a model is rate limited.

**Where the key is stored:** in `config.local.json`, which is git-ignored.
`config.json` (tracked) only ever holds harmless settings, so a key cannot be
committed by accident. You can also export `JARVIS_API_KEY` instead.

## What it can do

Say it, type it, or use the chips under the input box.

* **Desktop control** — `open notepad`, `search youtube lofi beats`,
  `screenshot`, `run command dir`, `volume up`, `open url google.com`
* **Mouse** — `move the mouse to 900 500`, `click at 300 300`,
  `move the mouse to the center`, `where is the mouse`. The pointer *glides*
  (eased, interruptible) instead of teleporting.
* **Drawing** — `draw a circle`, `draw a cat`, `draw a house`. Jarvis converts
  the shape into a stroke path and drags the mouse through it inside whatever
  paint app is focused. The drawing also appears in the panel bottom-left.
  Shapes: circle, ellipse, rect, line, polygon, star, heart, spiral, sine,
  arc, cross, diamond, arrow. Pictures: house, robot, cat, tree, sun, flower,
  boat, mountain, car, rocket, fish, mushroom, cup, smiley.
* **3D models** — `make a robot`, `make a 3d vase`, `build a gear`. Writes a
  real `.obj` / `.stl` to `Desktop\Jarvis3D\` and opens it, with a shaded
  preview in the panel. Models: box, sphere, cylinder, cone, pyramid, prism,
  torus, gear, gem, vase, mug, pawn, goblet, robot, house, tree, snowman,
  rocket, table, chair. STL is exported Z-up, so it is ready to slice.
* **Windows** — `window list`, and via the brain: move / resize / focus /
  minimize / maximize / close any window by title.
* **WhatsApp** — `call my father`, `message mom running late`
  (contacts live in `contacts.json`).
* **Secretary / call mode** — `secretary mode on` auto-answers incoming calls
  and speaks a message; `listen mode on` uses Vosk to hear the call audio.

## Talking to people for you

Jarvis can sit in a conversation and answer as you, in a call or a chat.
Open the **LIVE** panel (the button above the AI chat bubble) or just say it.

| Say | What happens |
|---|---|
| `call mode on discord` / `talk to them` | Jarvis joins the live audio and answers out loud |
| `stop talking` / `i'll take over` | leaves the conversation |
| `go quiet` / `you can talk` | mutes/unmutes Jarvis *inside* the call (not your mic) |
| `chat mode on whatsapp` / `chat with dad` | watches that chat and replies as you |
| `read the chat` | scrapes the visible conversation to the clipboard and reads it back |
| `reply <text>` | types and sends to the focused chat |
| `what call is this` | lists windows that look like live calls |

Supported apps: WhatsApp, Discord, Telegram, Zoom, Google Meet, Teams,
Messenger. Detection reads window titles, so it is a heuristic — the LIVE
panel shows the confidence and lets you pick the app yourself.

### Being heard inside a call

Voice calls need one extra piece of plumbing: an app cannot hear Jarvis
unless Jarvis speaks into that app's microphone. On Windows you do that with
a free virtual audio cable:

1. Install [VB-CABLE](https://vb-audio.com/Cable/) (donationware, no account).
2. In Discord/WhatsApp/Zoom, set the **input/microphone** device to
   `CABLE Output`.
3. Say `audio devices`, then `use audio device CABLE Input`
   (or pick it in the LIVE panel). Jarvis now speaks straight into the call.

Without a cable Jarvis still hears and answers — you just hear it on your
speakers and the other person does not.

### How chat reading works

There is no reliable cross-app chat API, so Jarvis focuses the window and
uses select-all + copy, then **restores whatever was on your clipboard**.
Two guards: it never scrapes while a different app is in front, and it stops
after `max_turns` replies.

Text chats need `listen mode` off; voice calls need it **on** (that is the
loopback capture that hears the other person).

## Safety

An AI moving your mouse needs brakes:

* **STOP button** (top right) and **Esc** abort everything mid-action — the
  movement loop checks the flag between every step and releases the mouse.
* **Mouse failsafe** is on: shove the pointer into any screen corner (the
  pyautogui failsafe) to kill a runaway action.
* **Safe mode** blocks destructive shell commands (`format`, `del /`,
  `rm -rf`, `shutdown`, …).
* The API only accepts requests from `localhost` — a random website cannot
  drive your PC through it.
* Actions are capped per command (`max_actions`, default 6) and logged
  (`GET /actions`, shown under the clock).

Turn failsafe/safe mode off in the settings panel if you need to.

## Files

| File | What it is |
|---|---|
| `server.py` | the core: HTTP API, brain client, action dispatcher |
| `draw.py` | pure-geometry drawing library (shapes → mouse stroke paths) |
| `model3d.py` | pure-geometry 3D modeller (meshes → OBJ/STL + SVG preview) |
| `index.html` | the whole UI — canvas face, voice, chat, settings |
| `config.json` | tracked settings (never secrets) |
| `config.local.json` | your API key (git-ignored, written by the UI) |
| `contacts.json` | phone numbers by relation (`father`, `mother`, …) |
| `tools/preview.py` | dev-only: renders shapes/models to PNG for checking |

## Tests

```bat
python -m unittest discover -s tests -v
```

Covers the geometry (volumes against closed-form values, watertightness, OBJ/
STL round-trips), the drawing pipeline, the tool schema and the offline
command parser. None of it needs Windows or an API key.

## Notes

* `listen` / `secretary` mode need the Vosk model folder
  (`vosk-model-small-en-us-0.15`) next to `server.py`.
* `testing.html` is an old standalone experiment, not used by the app.
* The default host is `127.0.0.1`. `JARVIS_HOST=0.0.0.0` exposes it on your
  LAN — only do that on a network you trust.
