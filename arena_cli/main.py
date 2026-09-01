"""arena-cli entry point: the big menu."""

import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from . import __version__, config
from .agent import run_agent
from .battle import run_battle, show_leaderboard
from .chat import run_chat

console = Console()

BANNER = r"""
   ▄▄▄       ██▀███  ▓█████  ███▄    █  ▄▄▄
  ▒████▄    ▓██ ▒ ██▒▓█   ▀  ██ ▀█   █ ▒████▄
  ▒██  ▀█▄  ▓██ ░▄█ ▒▒███   ▓██  ▀█ ██▒▒██  ▀█▄
  ░██▄▄▄▄██ ▒██▀▀█▄  ▒▓█  ▄ ▓██▒  ▐▌██▒░██▄▄▄▄██
   ▓█   ▓██▒░██▓ ▒██▒░▒████▒▒██░   ▓██░ ▓█   ▓██▒
   ▒▒   ▓▒█░░ ▒▓ ░▒▓░░░ ▒░ ░░ ▒░   ▒ ▒  ▒▒   ▓▒█░
"""


def settings_menu():
    cfg = config.load_config()
    while True:
        console.print(Panel(
            f"provider: [bold]{cfg['provider']}[/]\n"
            f"api key:  [bold]{'set (' + cfg['api_key'][:8] + '...)' if cfg['api_key'] else 'not set'}[/]\n"
            f"base url: [bold]{cfg['base_url'] or '(default for provider)'}[/]\n"
            f"models:   [bold]{len(cfg['models'])}[/] configured\n"
            f"default:  [bold]{cfg['default_model'] or '(ask every time)'}[/]",
            title="⚙️  Settings", border_style="yellow",
        ))
        choice = Prompt.ask(
            "[bold]1[/] provider · [bold]2[/] api key · [bold]3[/] base url · [bold]4[/] models · [bold]5[/] default model · [bold]b[/] back",
            choices=["1", "2", "3", "4", "5", "b"], default="b",
        )
        if choice == "b":
            config.save_config(cfg)
            return
        if choice == "1":
            cfg["provider"] = Prompt.ask("Provider", choices=["openrouter", "openai", "custom", "demo"], default=cfg["provider"])
            if cfg["provider"] == "demo":
                console.print("[dim]Demo mode: free fake models, no key needed.[/dim]")
        elif choice == "2":
            cfg["api_key"] = Prompt.ask("API key (paste it)", password=True).strip()
        elif choice == "3":
            cfg["base_url"] = Prompt.ask("Base URL (OpenAI-compatible, blank for provider default)", default=cfg["base_url"]).strip()
        elif choice == "4":
            console.print("[dim]Current models:[/dim] " + ", ".join(cfg["models"]))
            raw = Prompt.ask("Comma-separated model list (blank = keep)", default="").strip()
            if raw:
                cfg["models"] = [m.strip() for m in raw.split(",") if m.strip()]
        elif choice == "5":
            cfg["default_model"] = Prompt.ask("Default model id (blank = ask every time)", default=cfg["default_model"]).strip()
        config.save_config(cfg)


def main_menu():
    cfg = config.load_config()
    mode = "demo mode (free, fake models)" if (cfg["provider"] == "demo" or not cfg["api_key"]) else f"{cfg['provider']} (real models)"
    console.print(Text(BANNER, style="bold magenta"))
    console.print(Panel.fit(
        f"[bold magenta]arena[/] in your terminal · v{__version__} · running on: [bold]{mode}[/]",
        border_style="magenta",
    ))
    console.print(
        "\n  [bold red]1[/] ⚔️  Battle Mode   [dim]two anonymous models fight, you vote[/dim]"
        "\n  [bold green]2[/] 🤖 Agent Mode    [dim]AI runs commands & edits files (with approval)[/dim]"
        "\n  [bold cyan]3[/] 💬 Direct Chat   [dim]talk to one model[/dim]"
        "\n  [bold yellow]4[/] 🏆 Leaderboard   [dim]your local battle rankings[/dim]"
        "\n  [bold]5[/] ⚙️  Settings      [dim]API keys & models[/dim]"
        "\n  [bold]q[/] 👋 Quit\n"
    )
    return Prompt.ask("[bold magenta]arena[/] [bold]>[/]", choices=["1", "2", "3", "4", "5", "q"], default="1")


def main():
    try:
        while True:
            choice = main_menu()
            if choice == "1":
                run_battle()
            elif choice == "2":
                run_agent()
            elif choice == "3":
                run_chat()
            elif choice == "4":
                show_leaderboard()
                Prompt.ask("[dim]press enter to go back[/dim]", default="")
            elif choice == "5":
                settings_menu()
            elif choice == "q":
                console.print("[magenta]gg, see you in the arena. 👋[/magenta]")
                return 0
    except (KeyboardInterrupt, EOFError):
        console.print("\n[magenta]gg, see you in the arena. 👋[/magenta]")
        return 0


if __name__ == "__main__":
    sys.exit(main())
