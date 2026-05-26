"""Model catalog, local discovery, and download management."""

from __future__ import annotations

import sys

from rich.console import Console

from .paths import MODELS_DIR

console = Console()

CATALOG = [
    {
        "name": "Gemma 4 2B Instruct",
        "repo": "litert-community/gemma-4-E2B-it-litert-lm",
        "filename": "gemma-4-E2B-it.litertlm",
        "size": "2.6 GB",
        "gated": False,
    },
    {
        "name": "Gemma 4 4B Instruct",
        "repo": "litert-community/gemma-4-E4B-it-litert-lm",
        "filename": "gemma-4-E4B-it.litertlm",
        "size": "4.2 GB",
        "gated": False,
    },
    {
        "name": "Gemma 3 1B Instruct INT4",
        "repo": "litert-community/Gemma3-1B-IT",
        "filename": "gemma3-1b-it-int4.litertlm",
        "size": "529 MB",
        "gated": True,
    },
]


def list_local() -> list[Path]:
    if not MODELS_DIR.exists():
        return []
    return sorted(MODELS_DIR.glob("*.litertlm"))


def resolve_model(session) -> Path:
    """Return the model path to use, downloading if necessary."""
    local = list_local()

    if len(local) == 1:
        console.print(f"[dim]model: {local[0].name}[/]")
        return local[0]

    if len(local) > 1:
        return _select_local(local, session)

    # Nothing downloaded yet — offer catalog
    return _offer_download(session)


def _select_local(models: list[Path], session) -> Path:
    console.print("\n[bold]Select a model:[/]")
    for i, p in enumerate(models, 1):
        size_mb = p.stat().st_size // (1024 * 1024)
        console.print(f"  [cyan]{i}.[/] {p.name}  [dim]({size_mb} MB)[/]")

    while True:
        try:
            raw = session.prompt([("class:prompt", f"  model [1-{len(models)}]: ")])
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(models):
                return models[idx]
            console.print(f"[red]  Enter a number between 1 and {len(models)}[/]")
        except ValueError:
            console.print("[red]  Please enter a number[/]")
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)


def _offer_download(session) -> Path:
    console.print("\n[bold]No models found.[/] Choose one to download:\n")
    for i, m in enumerate(CATALOG, 1):
        gated_note = "  [dim yellow](HF login required)[/]" if m["gated"] else ""
        console.print(
            f"  [cyan]{i}.[/] [bold]{m['name']}[/]  [dim]({m['size']})[/]{gated_note}"
        )

    console.print()
    while True:
        try:
            raw = session.prompt([("class:prompt", f"  download [1-{len(CATALOG)}]: ")])
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(CATALOG):
                return _download(CATALOG[idx])
            console.print(f"[red]  Enter a number between 1 and {len(CATALOG)}[/]")
        except ValueError:
            console.print("[red]  Please enter a number[/]")
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)


def _download(spec: dict) -> Path:
    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils import EntryNotFoundError, RepositoryNotFoundError

    dest = MODELS_DIR / spec["filename"]

    console.print(
        f"\n  Downloading [bold green]{spec['name']}[/] ({spec['size']}) "
        f"from [dim]{spec['repo']}[/]\n"
    )

    try:
        hf_hub_download(
            repo_id=spec["repo"],
            filename=spec["filename"],
            local_dir=str(MODELS_DIR),
        )
    except RepositoryNotFoundError:
        console.print(f"[red]Repository not found:[/] {spec['repo']}")
        sys.exit(1)
    except EntryNotFoundError:
        console.print(f"[red]File not found in repo:[/] {spec['filename']}")
        sys.exit(1)
    except Exception as e:
        if "gated" in str(e).lower() or "401" in str(e) or "403" in str(e):
            console.print(
                "[red]Access denied.[/] Accept the model license at "
                f"[link]https://huggingface.co/{spec['repo']}[/link] "
                "then set [bold]HF_TOKEN[/] in your environment."
            )
        else:
            console.print(f"[red]Download failed:[/] {e}")
        sys.exit(1)

    console.print(f"\n  [green]Saved to {dest}[/]\n")
    return dest
