"""Agent Mode: a coding agent that works in your current folder.

Open a terminal in your project (e.g. VS Code's built-in terminal), run `arena`,
pick Agent Mode, and the AI can list, read, edit and create files there —
with your approval (y / n / a = allow all for this task).
"""

import difflib
import json
import os
import re
import subprocess

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from . import config
from .api import get_client, get_models, DemoClient, LLMError
from .chat import pick_model

console = Console()

MAX_STEPS = 20
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             ".next", ".cache", ".idea", ".vscode", "target", ".mypy_cache", ".pytest_cache"}

SYSTEM_PROMPT = """You are a coding agent inside arena-cli, working in the user's current project folder (their cwd). You can create files, edit files, and run commands — like a pair programmer living in their terminal.

To use a tool, reply with ONLY a fenced json block, nothing else:

```json
{"tool": "shell", "command": "ls -la"}
```

Available tools:
- {"tool": "list_dir", "path": "."}                                   -> list files/folders (recursive tree)
- {"tool": "read_file", "path": "index.html"}                          -> read a text file
- {"tool": "write_file", "path": "style.css", "content": "..."}        -> create a NEW file or fully overwrite one
- {"tool": "edit_file", "path": "index.html", "find": "...", "replace": "..."} -> edit an EXISTING file by replacing the first exact occurrence of `find` with `replace`
- {"tool": "shell", "command": "..."}                                  -> run a shell command in the project folder

Rules:
- One tool call per reply. After each call you get the result, then continue.
- Prefer edit_file for small changes to existing files (read the file first so `find` matches EXACTLY, including whitespace). Use write_file for new files or full rewrites.
- Paths are relative to the project folder. Never touch files outside it unless the user explicitly asks.
- When the task is done (or impossible), reply with plain text (no json block) summarizing what you changed.
"""

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_tool_call(text):
    m = _JSON_BLOCK.search(text)
    raw = m.group(1) if m else None
    if raw is None:
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            raw = stripped
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and "tool" in data else None


def _approve(question, state, default=False):
    """y = yes, n = no, a = yes to everything for the rest of this task."""
    if state.get("auto"):
        console.print(f"[dim]auto-approved ({question})[/dim]")
        return True
    ans = Prompt.ask(
        f"[bold yellow]{question}[/] [dim](y=yes · n=no · a=allow all this task)[/dim]",
        choices=["y", "n", "a"],
        default="y" if default else "n",
    )
    if ans == "a":
        state["auto"] = True
        return True
    return ans == "y"


def _safe_path(path):
    """Resolve a path and make sure it stays inside the project folder."""
    root = os.path.realpath(os.getcwd())
    full = os.path.realpath(os.path.join(root, os.path.expanduser(path)))
    inside = full == root or full.startswith(root + os.sep)
    return full, inside


def _tree(root=".", max_depth=3, max_entries=250):
    """Small recursive tree of the project folder."""
    lines = []
    root = os.path.abspath(root)

    def walk(d, prefix, depth):
        if depth > max_depth or len(lines) >= max_entries:
            return
        try:
            entries = sorted(os.listdir(d))
        except OSError:
            return
        entries = [e for e in entries if not e.startswith(".") and e not in SKIP_DIRS]
        for e in entries:
            if len(lines) >= max_entries:
                lines.append(prefix + "... (truncated)")
                return
            p = os.path.join(d, e)
            if os.path.isdir(p):
                lines.append(f"{prefix}{e}/")
                walk(p, prefix + "  ", depth + 1)
            else:
                lines.append(f"{prefix}{e}")

    walk(root, "", 1)
    return "\n".join(lines) if lines else "(empty folder)"


def _show_diff(path, old, new):
    diff = "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}",
    ))
    if len(diff) > 4000:
        diff = diff[:4000] + "\n... (diff truncated)"
    console.print(Panel(Syntax(diff or "(no changes)", "diff", theme="monokai"),
                        title=f"✏️  proposed changes to {path}", border_style="yellow"))


def _run_tool(call, state):
    tool = call.get("tool")

    if tool == "list_dir":
        path = call.get("path", ".") or "."
        full, inside = _safe_path(path)
        if not inside:
            return "DENIED: path is outside the project folder."
        console.print(f"[dim]🛠️  listing {path}[/dim]")
        return _tree(full)

    if tool == "read_file":
        path = call.get("path", "")
        full, inside = _safe_path(path)
        if not inside and not _approve(f"Agent wants to read {path} (OUTSIDE project folder). Allow?", state):
            return "USER DENIED reading this file."
        console.print(f"[dim]🛠️  reading {path}[/dim]")
        try:
            with open(full, "r", errors="replace") as f:
                content = f.read()
            if len(content) > 12000:
                return content[:12000] + "\n... (file truncated at 12000 chars)"
            return content if content else "(empty file)"
        except OSError as e:
            return f"Error reading file: {e}"

    if tool == "write_file":
        path = call.get("path", "")
        content = call.get("content", "")
        full, inside = _safe_path(path)
        exists = os.path.exists(full)
        old = ""
        if exists:
            try:
                with open(full, "r", errors="replace") as f:
                    old = f.read()
            except OSError:
                pass
        _show_diff(path, old, content)
        verb = "overwrite" if exists else "create"
        warn = "" if inside else " (OUTSIDE project folder!)"
        if not _approve(f"Agent wants to {verb} {path}{warn}. Allow?", state):
            return "USER DENIED writing this file."
        try:
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "w") as f:
                f.write(content)
            console.print(f"[green]✔ {'overwrote' if exists else 'created'} {path}[/green]")
            return f"OK: wrote {len(content)} chars to {path}."
        except OSError as e:
            return f"Error writing file: {e}"

    if tool == "edit_file":
        path = call.get("path", "")
        find = call.get("find", "")
        replace = call.get("replace", "")
        full, inside = _safe_path(path)
        if not os.path.exists(full):
            return f"Error: {path} does not exist. Use write_file to create it."
        if not find:
            return "Error: 'find' is empty."
        try:
            with open(full, "r", errors="replace") as f:
                old = f.read()
        except OSError as e:
            return f"Error reading file: {e}"
        if find not in old:
            return ("Error: 'find' text not found in the file. Read the file again and make sure "
                    "'find' matches EXACTLY (including whitespace/indentation).")
        new = old.replace(find, replace, 1)
        _show_diff(path, old, new)
        warn = "" if inside else " (OUTSIDE project folder!)"
        if not _approve(f"Agent wants to edit {path}{warn}. Allow?", state):
            return "USER DENIED this edit."
        try:
            with open(full, "w") as f:
                f.write(new)
            console.print(f"[green]✔ edited {path}[/green]")
            return f"OK: edited {path}."
        except OSError as e:
            return f"Error writing file: {e}"

    if tool == "shell":
        cmd = call.get("command", "")
        console.print(Panel(Syntax(cmd, "bash", theme="monokai"),
                            title="🛠️  wants to run", border_style="yellow"))
        if not _approve("Allow this command?", state):
            return "USER DENIED this command. Try another approach or ask the user."
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            out = (proc.stdout + proc.stderr).strip()
            out = out[-4000:] if out else "(no output)"
            return f"exit code {proc.returncode}\n{out}"
        except subprocess.TimeoutExpired:
            return "Command timed out after 120s."

    return f"Unknown tool '{tool}'."


def run_agent():
    cfg = config.load_config()
    client = get_client(cfg)

    console.print(Panel.fit(
        "[bold]🤖 AGENT MODE[/bold] — coding agent for [bold]this folder[/bold]\n"
        f"[dim]project:[/dim] [bold]{os.getcwd()}[/]\n"
        "It can list, read, edit and create files here, and run commands.\n"
        "Every change shows a diff and asks [bold]y/n/a[/] (a = allow all for the task).\n"
        "Tip: open your project in VS Code, use the built-in terminal, run [bold]arena[/].\n"
        "Type [bold cyan]/back[/] to return to menu.",
        border_style="green",
    ))

    if isinstance(client, DemoClient):
        console.print(Panel(
            "Agent mode needs a real API key (demo models can't actually think).\n"
            "Go to [bold]Settings[/bold] in the main menu and add an OpenRouter or OpenAI key.",
            border_style="red", title="⚠️  demo mode",
        ))
        return

    models = get_models(cfg)
    model = cfg.get("default_model") or None
    if model not in models:
        model = pick_model(models, cfg.get("default_model", ""))
    console.print(f"[dim]Agent brain:[/dim] [bold green]{model}[/]")

    while True:
        task = Prompt.ask("\n[bold green]agent task[/] [bold]>[/]").strip()
        if not task:
            continue
        if task.lower() in ("/back", "/exit", "/quit", "back", "exit"):
            return

        state = {"auto": False}
        tree = _tree(".", max_depth=3)
        history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Project folder: {os.getcwd()}\n\n"
                f"Current file tree:\n{tree}\n\n"
                f"Task: {task}"
            )},
        ]

        for step in range(1, MAX_STEPS + 1):
            try:
                with console.status(f"[green]agent thinking (step {step}/{MAX_STEPS})...[/]"):
                    reply = client.chat(model, history, temperature=0.2)
            except LLMError as e:
                console.print(f"[red]API error:[/red] {e}")
                break

            history.append({"role": "assistant", "content": reply})
            call = _extract_tool_call(reply)

            if call is None:
                console.print(Panel(Markdown(reply.strip() or "(empty reply)"),
                                    title="🤖 agent", border_style="green"))
                break

            result = _run_tool(call, state)
            preview = result if len(result) <= 1200 else result[:1200] + "\n... (truncated)"
            console.print(Panel(preview, title="↩️  tool result", border_style="dim"))
            history.append({"role": "user", "content": f"Tool result:\n{result}"})
        else:
            console.print("[yellow]Agent hit the step limit. Stopping here.[/yellow]")
