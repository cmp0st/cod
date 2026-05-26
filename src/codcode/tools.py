"""Tool definitions. All tools execute inside the sandbox VM."""

from __future__ import annotations

import shlex
from pathlib import Path

from .vm import SandboxVM

_vm: SandboxVM | None = None
_shared_dir: Path | None = None


def configure(vm: SandboxVM, shared_dir: Path) -> None:
    global _vm, _shared_dir
    _vm = vm
    _shared_dir = shared_dir.resolve()


def _vp(path: str) -> str:
    """Translate a host absolute path under shared_dir to its /workspace equivalent."""
    if _shared_dir is None:
        return path
    try:
        rel = Path(path).resolve().relative_to(_shared_dir)
        return f"/workspace/{rel}"
    except ValueError:
        return path  # outside shared_dir; pass through and let the VM reject it


def _exec(cmd: str, cwd: str | None = None, timeout: int = 30) -> str:
    if _vm is None:
        return "Error: sandbox VM is not running"
    full = f"cd {shlex.quote(cwd)} && {cmd}" if cwd else cmd
    out, code = _vm.run(full, timeout=timeout)
    result = out.rstrip("\n")
    if not result:
        return f"(exit {code})" if code else "(no output)"
    return result


def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: Absolute or relative path to the file to read.
    """
    return _exec(f"cat {shlex.quote(_vp(path))}")


def list_directory(path: str) -> str:
    """List files and directories at a given path.

    Args:
        path: Directory path to list.
    """
    return _exec(f"ls -la {shlex.quote(_vp(path))}")


def hash_file(path: str, algorithm: str = "sha256") -> str:
    """Compute the cryptographic hash of a file.

    Args:
        path: Path to the file to hash.
        algorithm: Hash algorithm to use (md5, sha1, sha256, sha512). Defaults to sha256.
    """
    cmds = {"md5": "md5sum", "sha1": "sha1sum", "sha256": "sha256sum", "sha512": "sha512sum"}
    if algorithm not in cmds:
        return f"Unsupported algorithm '{algorithm}'. Choose from: {', '.join(cmds)}"
    return _exec(f"{cmds[algorithm]} {shlex.quote(_vp(path))}")


def check_permissions(path: str) -> str:
    """Inspect file or directory permissions and ownership.

    Args:
        path: Path to inspect.
    """
    return _exec(f"stat {shlex.quote(_vp(path))}")


def run_command(command: str, working_dir: str = ".") -> str:
    """Run a shell command and return its output.

    Args:
        command: The shell command to execute.
        working_dir: Directory to run the command in. Defaults to the project root.
    """
    cwd = _translate_working_dir(working_dir)
    return _exec(command, cwd=cwd, timeout=30)


def search_in_file(path: str, pattern: str) -> str:
    """Search for a text pattern in a file and return matching lines.

    Args:
        path: Path to the file to search.
        pattern: Text pattern to search for (case-sensitive substring match).
    """
    return _exec(f"grep -n {shlex.quote(pattern)} {shlex.quote(_vp(path))}")


def _translate_working_dir(working_dir: str) -> str:
    if working_dir in (".", ""):
        return "/workspace"
    wd = Path(working_dir)
    if wd.is_absolute():
        return _vp(working_dir)
    return f"/workspace/{wd}"


ALL_TOOLS = [
    read_file,
    list_directory,
    hash_file,
    check_permissions,
    run_command,
    search_in_file,
]
