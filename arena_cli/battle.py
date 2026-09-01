"""Battle Mode: two anonymous models fight, you vote, Elo leaderboard updates."""

import random

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.markdown import Markdown

from . import config
from .api import get_client, get_models, LLMError

console = Console()


def _stream_answer(client, model, prompt, label, color):
    console.print(Panel(f"[bold {color}]{label}[/bold {color}] is thinking...", border_style=color))
    messages = [
        {"role": "system", "content": "You are a helpful assistant competing in a blind arena battle. Answer well and concisely."},
        {"role": "user", "content": prompt},
    ]
    text = ""
    try:
        with console.status(f"[{color}]{label} typing...[/]", spinner="dots"):
            for chunk in client.stream_chat(model, messages):
                text += chunk
    except LLMError as e:
        text = f"(this model crashed mid-battle: {e})"
    console.print(Panel(Markdown(text.strip() or "(empty answer)"), title=f"[bold {color}]{label}[/]", border_style=color))
    return text


def show_leaderboard():
    board = config.load_leaderboard()
    if not board:
        console.print("[dim]No battles fought yet. The leaderboard is empty and sad.[/dim]")
        return
    table = Table(title="🏆 Your Local Arena Leaderboard", header_style="bold magenta")
    table.add_column("#", justify="right")
    table.add_column("Model", style="cyan")
    table.add_column("Elo", justify="right", style="bold yellow")
    table.add_column("W", justify="right", style="green")
    table.add_column("L", justify="right", style="red")
    table.add_column("T", justify="right")
    table.add_column("Battles", justify="right")
    ranked = sorted(board.items(), key=lambda kv: kv[1]["elo"], reverse=True)
    for i, (model, s) in enumerate(ranked, 1):
        table.add_row(str(i), model, f"{s['elo']:.0f}", str(s["wins"]), str(s["losses"]), str(s["ties"]), str(s["battles"]))
    console.print(table)


def run_battle():
    cfg = config.load_config()
    client = get_client(cfg)
    models = get_models(cfg)
    if len(models) < 2:
        console.print("[red]Need at least 2 models configured to battle. Check Settings.[/red]")
        return

    console.print(Panel.fit(
        "[bold]⚔️  BATTLE MODE[/bold]\nTwo anonymous models answer your prompt. You vote. Names revealed after.\nType [bold cyan]/lb[/] for leaderboard, [bold cyan]/back[/] to return to menu.",
        border_style="red",
    ))

    while True:
        prompt = Prompt.ask("\n[bold red]battle[/] [bold]>[/]").strip()
        if not prompt:
            continue
        if prompt.lower() in ("/back", "/exit", "/quit", "back", "exit"):
            return
        if prompt.lower() in ("/lb", "/leaderboard"):
            show_leaderboard()
            continue

        model_a, model_b = random.sample(models, 2)
        console.print()
        text_a = _stream_answer(client, model_a, prompt, "Model A", "blue")
        text_b = _stream_answer(client, model_b, prompt, "Model B", "green")

        vote = Prompt.ask(
            "\n[bold]Who won?[/]",
            choices=["a", "b", "tie", "bad", "skip"],
            default="skip",
            show_choices=True,
        )

        console.print(Panel(
            f"[bold blue]Model A[/] was [bold]{model_a}[/]\n[bold green]Model B[/] was [bold]{model_b}[/]",
            title="🎭 Reveal",
            border_style="magenta",
        ))

        if vote == "skip":
            console.print("[dim]No vote recorded.[/dim]")
            continue

        board = config.load_leaderboard()
        if vote == "a":
            config.update_elo(board, model_a, model_b)
            console.print(f"[bold blue]{model_a}[/] takes the win! 🏆")
        elif vote == "b":
            config.update_elo(board, model_b, model_a)
            console.print(f"[bold green]{model_b}[/] takes the win! 🏆")
        else:  # tie or both bad
            config.update_elo(board, model_a, model_b, tie=True)
            console.print("Recorded as a tie." if vote == "tie" else "Both bad... recorded as a tie of shame. 💀")
        config.save_leaderboard(board)
        show_leaderboard()
