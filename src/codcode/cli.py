"""codcode CLI entry point."""

from __future__ import annotations

import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from rich.console import Console

from .harness import Harness, redirect_engine_logs
from .models import resolve_model
from .paths import ensure_dirs

console = Console()

PROMPT_STYLE = Style.from_dict({"prompt": "bold ansicyan"})

def print_banner() -> None:
    console.print("[bold green]  \\   /[/bold green]")
    console.print("[bold green]   \\ /[/bold green]")
    console.print("[bold cyan]~~~[/bold cyan][bold green]><((((°>[/bold green]  [bold white]codcode[/bold white]")
    console.print("[bold green]   / \\ [/bold green]   [dim]security-oriented agent harness[/dim]")
    console.print("[bold green]  /   \\ [/bold green]  [dim]v0.1.0[/dim]")
    console.print()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="cod",
        description="codcode — security-oriented local agent harness",
    )
    parser.add_argument(
        "--no-approval",
        action="store_true",
        help="Skip approval prompts for tool calls (dangerous)",
    )
    args = parser.parse_args(argv)

    ensure_dirs()
    print_banner()

    session: PromptSession = PromptSession(
        history=InMemoryHistory(),
        style=PROMPT_STYLE,
    )

    # Resolve model (auto-select, interactive select, or download)
    model_path = resolve_model(session)

    # Silence engine C++ logs before touching the engine
    redirect_engine_logs()

    try:
        with Harness(model_path, require_approval=not args.no_approval) as harness:
            console.print("[dim]Type your message. Ctrl-C or Ctrl-D to quit.[/]\n")
            while True:
                try:
                    user_input = session.prompt([("class:prompt", ">> ")]).strip()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[dim]Goodbye.[/]")
                    break

                if not user_input:
                    continue
                if user_input.lower() in {"/exit", "/quit", "exit", "quit"}:
                    console.print("[dim]Goodbye.[/]")
                    break

                harness.send(user_input)

    except Exception as e:
        console.print(f"[bold red]Fatal error:[/] {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
