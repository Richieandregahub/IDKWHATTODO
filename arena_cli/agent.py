"""Agent Mode: an AI that can run shell commands + read/write files (with your approval)."""

import json
import os
import re
import subprocess

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax

from . import config
from .api import get_client, get_models, DemoClient, LLMError
from .chat import pick_model

console = Console()

MAX_STEPS = 12

SYSTEM_PROMPT = """You are an autonomous terminal agent inside arena-cli, working in the user's current directory.

You can use tools. To use a tool, reply with ONLY a fenced json block like:

```json
{"tool": "shell", "command": "ls -la"}
```

Available tools:
- {"tool": "shell", "command": "<bash command>"}            -> run a shell command
- {"tool": "read_file", "path": "<path>"}                    -> read a text file
- {"tool": "write_file", "path": "<path>", "content": "..."} -> create/overwrite a file

Rules:
- One tool call per reply, nothing else in that reply.
- After each tool call you'll receive the result, then continue.
- When the task is complete (or impossible), reply with plain text (no json block) summarizing what you did.
- Be careful and minimal with shell commands.
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


def _run_tool(call):
    tool = call.get("tool")
    if tool == "shell":
        cmd = call.get("command", "")
        console.print(Panel(Syntax(cmd, "bash", theme="monokai"), title="🛠️  wants to run", border_style="yellow"))
        if not Confirm.ask("[bold yellow]Allow this command?[/]", default=False):
            return "USER DENIED this command. Try another approach or ask the user."
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            out = (proc.stdout + proc.stderr).strip()
            out = out[-4000:] if out else "(no output)"
            return f"exit code {proc.returncode}\n{out}"
        except subprocess.TimeoutExpired:
            return "Command timed out after 60s."
    if tool == "read_file":
        path = call.get("path", "")
        console.print(f"[yellow]🛠️  wants to read[/] [bold]{path}[/]")
        if not Confirm.ask("[bold yellow]Allow?[/]", default=True):
            return "USER DENIED reading this file."
        try:
            with open(os.path.expanduser(path), "r", errors="replace") as f:
                return f.read()[:8000]
        except OSError as e:
            return f"Error reading file: {e}"
    if tool == "write_file":
        path = call.get("path", "")
        content = call.get("content", "")
        console.print(Panel(content[:2000], title=f"🛠️  wants to write {path}", border_style="yellow"))
        if not Confirm.ask("[bold yellow]Allow writing this file?[/]", default=False):
            return "USER DENIED writing this file."
        try:
            p = os.path.expanduser(path)
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(p, "w") as f:
                f.write(content)
            return f"Wrote {len(content)} chars to {path}."
        except OSError as e:
            return f"Error writing file: {e}"
    return f"Unknown tool '{tool}'."


def run_agent():
    cfg = config.load_config()
    client = get_client(cfg)

    console.print(Panel.fit(
        "[bold]🤖 AGENT MODE[/bold]\nGive the agent a task. It can run shell commands and read/write files\n[bold](every action needs your y/n approval)[/bold].\nType [bold cyan]/back[/] to return to menu.",
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
    console.print(f"[dim]Agent brain:[/dim] [bold green]{model}[/] · [dim]cwd:[/dim] {os.getcwd()}")

    while True:
        task = Prompt.ask("\n[bold green]agent task[/] [bold]>[/]").strip()
        if not task:
            continue
        if task.lower() in ("/back", "/exit", "/quit", "back", "exit"):
            return

        history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
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
                console.print(Panel(Markdown(reply.strip() or "(empty reply)"), title="🤖 agent", border_style="green"))
                break

            result = _run_tool(call)
            console.print(Panel(result[:1500], title="↩️  tool result", border_style="dim"))
            history.append({"role": "user", "content": f"Tool result:\n{result}"})
        else:
            console.print("[yellow]Agent hit the step limit. Stopping here.[/yellow]")
