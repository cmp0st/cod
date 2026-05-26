"""Agent harness: manages the engine, conversation, and tool approval."""

from __future__ import annotations

import os
import sys

import litert_lm
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from .paths import CACHE_DIR, LOG_DIR
from .tools import ALL_TOOLS

console = Console()

SYSTEM_PROMPT = """\
You are codcode, a security-oriented CLI assistant. You help users inspect files,
analyse permissions, compute hashes, search content, and run shell commands —
with careful attention to security implications. Always explain what you are doing
and flag anything suspicious you encounter.

When using tools, prefer read-only operations first. Ask before running commands
that could modify state. Highlight SUID/SGID bits, world-writable paths,
or unusual permissions when you see them.\
"""


def redirect_engine_logs() -> None:
    """Redirect fd 2 to the engine log file so C++ output stays off the console."""
    log_path = LOG_DIR / "engine.log"
    log_fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(log_fd, 2)  # stderr → log
    os.close(log_fd)
    sys.stderr = open(str(log_path), "a")


class Harness:
    def __init__(self, model_path: Path, require_approval: bool = True) -> None:
        self.model_path = model_path
        self.require_approval = require_approval
        self._engine: litert_lm.Engine | None = None
        self._conversation = None

    def __enter__(self) -> "Harness":
        console.print(
            Panel(
                "[bold green]codcode[/] — security-oriented agent harness\n"
                f"[dim]model: {self.model_path.name}[/]\n"
                f"[dim]logs:  {LOG_DIR / 'engine.log'}[/]",
                border_style="green",
            )
        )
        self._engine = litert_lm.Engine(
            str(self.model_path),
            backend=litert_lm.Backend.GPU(),
            enable_speculative_decoding=True,
            cache_dir=str(CACHE_DIR),
        )
        self._engine.__enter__()

        messages = [litert_lm.Message.system(SYSTEM_PROMPT)]
        tools = _wrap_tools_with_approval(ALL_TOOLS) if self.require_approval else ALL_TOOLS

        self._conversation = self._engine.create_conversation(
            messages=messages,
            tools=tools,
        )
        self._conversation.__enter__()
        return self

    def __exit__(self, *args) -> None:
        if self._conversation:
            self._conversation.__exit__(*args)
        if self._engine:
            self._engine.__exit__(*args)

    def send(self, user_input: str) -> None:
        """Send a user message and stream the response to the console."""
        console.print(f"\n[bold cyan]you:[/] {escape(user_input)}")
        console.print("[bold magenta]codcode:[/] ", end="")

        stream = self._conversation.send_message_async(user_input)
        for chunk in stream:
            for item in chunk.get("content", []):
                if item.get("type") == "text":
                    console.print(item["text"], end="")

        console.print()  # newline after response


def _wrap_tools_with_approval(tools: list) -> list:
    return [_make_approval_wrapper(fn) for fn in tools]


def _make_approval_wrapper(fn):
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        arg_parts = [repr(a) for a in args] + [
            f"{k}={repr(v)}" for k, v in kwargs.items()
        ]
        call_str = f"{fn.__name__}({', '.join(arg_parts)})"
        console.print(
            Panel(
                f"[yellow]Tool call requested:[/]\n[bold]{escape(call_str)}[/]",
                border_style="yellow",
                title="[bold yellow]approval required[/]",
            )
        )
        try:
            answer = console.input("[bold yellow]Allow? [y/N]:[/] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if answer == "y":
            result = fn(*args, **kwargs)
            console.print(f"[dim]tool result:[/] {escape(str(result)[:500])}")
            return result
        else:
            msg = "(tool call denied by user)"
            console.print(f"[dim]{msg}[/]")
            return msg

    return wrapper
