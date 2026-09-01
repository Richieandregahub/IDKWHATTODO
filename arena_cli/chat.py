"""Direct Chat: pick a model, talk to it."""

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt

from . import config
from .api import get_client, get_models, LLMError

console = Console()


def pick_model(models, default_model=""):
    console.print("\n[bold]Pick a model:[/bold]")
    for i, m in enumerate(models, 1):
        marker = " [dim](default)[/dim]" if m == default_model else ""
        console.print(f"  [cyan]{i}[/cyan]. {m}{marker}")
    while True:
        try:
            idx = IntPrompt.ask("Model number", default=1)
        except Exception:
            continue
        if 1 <= idx <= len(models):
            return models[idx - 1]
        console.print("[red]Not a valid number, try again.[/red]")


def run_chat():
    cfg = config.load_config()
    client = get_client(cfg)
    models = get_models(cfg)
    if not models:
        console.print("[red]No models configured. Check Settings.[/red]")
        return

    console.print(Panel.fit(
        "[bold]💬 DIRECT CHAT[/bold]\nTalk to one model directly.\nCommands: [bold cyan]/model[/] switch model · [bold cyan]/clear[/] reset history · [bold cyan]/back[/] menu",
        border_style="cyan",
    ))

    model = cfg.get("default_model") or None
    if model not in models:
        model = pick_model(models, cfg.get("default_model", ""))
    console.print(f"[dim]Chatting with[/dim] [bold cyan]{model}[/]")

    history = [{"role": "system", "content": "You are a helpful, friendly assistant in a terminal chat app called arena-cli."}]

    while True:
        user = Prompt.ask("\n[bold cyan]you[/] [bold]>[/]").strip()
        if not user:
            continue
        low = user.lower()
        if low in ("/back", "/exit", "/quit", "back", "exit"):
            return
        if low == "/clear":
            history = history[:1]
            console.print("[dim]History cleared.[/dim]")
            continue
        if low == "/model":
            model = pick_model(models)
            console.print(f"[dim]Now chatting with[/dim] [bold cyan]{model}[/]")
            continue

        history.append({"role": "user", "content": user})
        text = ""
        try:
            with Live(console=console, refresh_per_second=12) as live:
                for chunk in client.stream_chat(model, history):
                    text += chunk
                    live.update(Panel(Markdown(text), title=f"[bold cyan]{model}[/]", border_style="cyan"))
        except LLMError as e:
            console.print(f"[red]API error:[/red] {e}")
            history.pop()
            continue
        history.append({"role": "assistant", "content": text})
