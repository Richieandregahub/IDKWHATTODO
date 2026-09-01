# ⚔️ arena-cli

**arena.ai but it lives in your terminal.** Battle Mode, Agent Mode, and Direct Chat — installed straight from GitHub.

```
   ▄▄▄       ██▀███  ▓█████  ███▄    █  ▄▄▄
  ▒████▄    ▓██ ▒ ██▒▓█   ▀  ██ ▀█   █ ▒████▄
  ▒██  ▀█▄  ▓██ ░▄█ ▒▒███   ▓██  ▀█ ██▒▒██  ▀█▄
  ░██▄▄▄▄██ ▒██▀▀█▄  ▒▓█  ▄ ▓██▒  ▐▌██▒░██▄▄▄▄██
   ▓█   ▓██▒░██▓ ▒██▒░▒████▒▒██░   ▓██░ ▓█   ▓██▒
```

## 🚀 Install (from this GitHub repo)

You need Python 3.8+ and pip. Then:

```bash
pip install git+https://github.com/Richieandregahub/IDKWHATTODO.git
```

Then just run:

```bash
arena
```

That's it. You get the menu:

```
  1 ⚔️  Battle Mode   two anonymous models fight, you vote
  2 🤖 Agent Mode    AI runs commands & edits files (with approval)
  3 💬 Direct Chat   talk to one model
  4 🏆 Leaderboard   your local battle rankings
  5 ⚙️  Settings      API keys & models
```

## 🎮 The Modes

### ⚔️ Battle Mode
Type a prompt → two **anonymous** models ("Model A" and "Model B") both answer → you vote for the winner → names get revealed → your local **Elo leaderboard** updates. Just like the real arena, but in your terminal.

### 🤖 Agent Mode
A coding agent for **whatever folder you're in**. Open your project in VS Code, pop open the built-in terminal (`` Ctrl+` ``), run `arena`, pick Agent Mode, and tell it stuff like:

- *"add a dark mode toggle to index.html"*
- *"create a style.css and link it"*
- *"make a snake game with html/css/js"*

It automatically sees your folder's file tree, then it can **list, read, edit and create files** and run shell commands. Every file change is shown as a **diff** first and asks for approval: `y` = yes, `n` = no, `a` = allow everything for the rest of the task (so it can build multi-file things without spamming you). Needs a real API key.

### 💬 Direct Chat
Pick a model, chat with it. Streaming responses, markdown rendering, `/model` to switch, `/clear` to reset.

## 🔑 API keys (optional but recommended)

Out of the box it runs in **Demo Mode** — free fake models so you can try everything without a key.

For real models, get an API key and either:

- **Option A:** run `arena` → `5` (Settings) → set provider + paste your key
- **Option B:** environment variable:
  ```bash
  export OPENROUTER_API_KEY=sk-or-...   # recommended: one key, tons of models
  # or
  export OPENAI_API_KEY=sk-...
  ```

[OpenRouter](https://openrouter.ai) is recommended because one key gets you GPT, Claude, Gemini, Llama, DeepSeek, Qwen, etc. — which makes Battle Mode actually fun. Any OpenAI-compatible API also works (Settings → provider `custom` → set base URL).

## 🏆 Leaderboard

Every battle vote updates a local Elo rating stored in `~/.arena-cli/leaderboard.json`. Your votes, your rankings.

## 🔄 Update / uninstall

```bash
pip install --upgrade --force-reinstall git+https://github.com/Richieandregahub/IDKWHATTODO.git
pip uninstall arena-cli
```

## ⚠️ Notes

- Agent Mode executes shell commands **on your machine** (after you approve each one). Read before you press `y`.
- Demo Mode models are fake and slightly unhinged on purpose.
