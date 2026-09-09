# Richie Jarvis

A local AI butler for Windows. It runs a small Python server on
`localhost:8765`, serves one self-contained HTML page (animated "bit face",
voice input, chat panel), and lets a language model drive your PC: open apps,
move/click/drag the **real mouse**, draw pictures, generate 3D model files,
control windows, send WhatsApp messages and run shell commands.

Everything runs on your machine. The only thing that leaves it is the text you
send to whichever brain you pick — and with the default **Puter.js** provider
that trip is made by your browser, not by the Python core, so there is no API
key stored anywhere.

---

## Quick start

```bat
setup.bat          :: installs pyautogui / psutil / vosk (once)
start_jarvis.bat   :: starts the core and opens http://localhost:8765
```

That is it — the brain is free and keyless out of the box. Keep the dashboard
tab open, and click the **gear** icon only if you want to switch to Gemini or
OpenRouter.

## Connecting a brain (for free)

Three ways in, ordered by how little they cost you:

| Provider | What you need | Models |
|---|---|---|
| **Puter.js** (default) | nothing — no API key, no card | 500+ via Puter's ["user pays" model](https://docs.puter.com/AI/) |
| **Google Gemini** | a free key from <https://aistudio.google.com/apikey> | the Flash / Flash-Lite free tier |
| **OpenRouter** | a key from <https://openrouter.ai/keys> | dozens of `:free` models |

Any other OpenAI-compatible endpoint works too — pick **Custom** and set the
base URL.

### Puter.js — free, no key at all

Puter.js is a browser library, so **the dashboard tab is the brain**. The Python
core queues a job on `GET /puter/jobs`, the page answers it with
`puter.ai.chat()` and posts the reply back to `POST /puter/result`. Nothing else
changes: tools, actions, mouse control, chat and call mode all still run in
`server.py` — only the HTTP hop to the model moves into the browser.

* Keep the dashboard tab open while Jarvis is working.
* The first call pops up a free Puter sign-in; or press **CONNECT PUTER** in the
  settings. The badge there reads `relay: online` when the tab is doing its job.
* The model dropdown is filled live from `puter.ai.listModels()`.
* If the tab is closed *and* a normal API key is saved, Jarvis quietly falls back
  to that key instead of going dumb.

### Gemini / OpenRouter

1. Paste the key in the settings panel. It lands in **that provider's own slot**,
   so a Gemini key and an OpenRouter key can both sit in `config.local.json` and
   you can flip between them without pasting anything again.
2. Pick a model from the dropdown — fetched **live** from the provider and
   filtered to models that are free right now and support tool calling. Hit ⟳ to
   refresh; the free line-up rotates often.
3. Press **TEST**. If it comes back with a model name, you are done.

Gemini is not OpenAI-compatible, so `server.py` translates in both directions:
your messages become `contents` + `systemInstruction`, the action catalogue
becomes `functionDeclarations`, and `candidates[0].content.parts` (including
`functionCall` parts) come back as a normal assistant message with `tool_calls`.

> Free tiers are rate limited — Gemini's Flash tier is roughly 10-15 requests a
> minute, OpenRouter's is 50 requests/day until you buy $10 of credits. Jarvis
> always queues the provider's other free models *behind* your chosen one and
> walks the list automatically when a model is rate limited or retired.

**Where keys are stored:** in `config.local.json`, which is git-ignored.
`config.json` (tracked) only ever holds harmless settings, so a key cannot be
committed by accident. You can also export `JARVIS_API_KEY`
(OpenRouter/custom) or `GEMINI_API_KEY` / `GOOGLE_API_KEY`.

> **Note:** OpenCode Zen (`provider: "zen"`) was retired and replaced by
> Puter.js. An old `config.json` that still says `zen` is migrated to `puter`
> automatically on load.

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
| `server.py` | the core: HTTP API, brain clients (OpenAI / Gemini / Puter relay), action dispatcher |
| `draw.py` | pure-geometry drawing library (shapes → mouse stroke paths) |
| `model3d.py` | pure-geometry 3D modeller (meshes → OBJ/STL + SVG preview) |
| `index.html` | the whole UI — canvas face, voice, chat, settings, Puter.js relay |
| `config.json` | tracked settings (never secrets) |
| `config.local.json` | your API keys, one slot per provider (git-ignored, written by the UI) |
| `contacts.json` | phone numbers by relation (`father`, `mother`, …) |
| `tools/preview.py` | dev-only: renders shapes/models to PNG for checking |

## HTTP API

Everything the page uses is plain JSON on `localhost:8765` (`127.0.0.1` only,
plus an origin check so a random website cannot drive your PC through it).

| Endpoint | What it does |
|---|---|
| `POST /command` | run a spoken/typed instruction (local parser first, then the brain) |
| `POST /chat` | plain conversation with the brain |
| `GET /health` | core + brain status, provider, last model used |
| `GET /config` · `POST /config` | read/save settings, keys and the provider |
| `GET /providers` | provider metadata (labels, key hints, which API each one speaks) |
| `GET /models?refresh=1&provider=` | that provider's free models, best first |
| `POST /test` | one tiny round trip to prove the key/model works |
| `GET /puter/jobs?wait=20` | long-poll the Puter.js relay for a brain job |
| `POST /puter/result` | the browser posts the model's reply back |
| `POST /puter/models` | the browser uploads `puter.ai.listModels()` |
| `GET /puter/status` | is the relay online, how many models, runs/failures |
| `POST /abort` | stop everything and release the mouse |
| `GET /actions` | the last 25 actions the model performed |

## Tests

```bat
python -m unittest discover -s tests -v
```

Covers the geometry (volumes against closed-form values, watertightness, OBJ/
STL round-trips), the drawing pipeline, the tool schema, the offline command
parser, and the brain layer: per-provider key slots, the retired-`zen`
migration, the Gemini request/response translation (URL, headers,
`functionDeclarations`, `functionCall` → `tool_calls`, model fall-through on
404/429), the action-name/parameter collision fix, and a full Puter.js relay
round trip driven by a fake browser thread. None of it needs Windows, a real
browser or an API key.

## Notes

* `listen` / `secretary` mode need the Vosk model folder
  (`vosk-model-small-en-us-0.15`) next to `server.py`.
* `testing.html` is an old standalone experiment, not used by the app.
* The default host is `127.0.0.1`. `JARVIS_HOST=0.0.0.0` exposes it on your
  LAN — only do that on a network you trust.
