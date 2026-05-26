"""Tool definitions available to the cod agent."""

import hashlib
import os
import shlex
import stat
import subprocess


def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: Absolute or relative path to the file to read.
    """
    try:
        with open(path) as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


def list_directory(path: str) -> str:
    """List files and directories at a given path.

    Args:
        path: Directory path to list. Defaults to current directory.
    """
    try:
        entries = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            s = os.stat(full)
            mode = stat.filemode(s.st_mode)
            size = s.st_size
            entries.append(f"{mode}  {size:>10}  {name}")
        return "\n".join(entries) if entries else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {e}"


def hash_file(path: str, algorithm: str = "sha256") -> str:
    """Compute the cryptographic hash of a file.

    Args:
        path: Path to the file to hash.
        algorithm: Hash algorithm to use (md5, sha1, sha256, sha512). Defaults to sha256.
    """
    supported = {"md5", "sha1", "sha256", "sha512"}
    if algorithm not in supported:
        return f"Unsupported algorithm '{algorithm}'. Choose from: {', '.join(supported)}"
    try:
        h = hashlib.new(algorithm)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return f"{algorithm}:{h.hexdigest()}  {path}"
    except Exception as e:
        return f"Error hashing file: {e}"


def check_permissions(path: str) -> str:
    """Inspect file or directory permissions and ownership.

    Args:
        path: Path to inspect.
    """
    try:
        s = os.stat(path)
        mode = stat.filemode(s.st_mode)
        uid = s.st_uid
        gid = s.st_gid
        octal = oct(s.st_mode)
        lines = [
            f"path:    {path}",
            f"mode:    {mode}  ({octal})",
            f"uid:     {uid}",
            f"gid:     {gid}",
            f"size:    {s.st_size} bytes",
        ]
        # SUID/SGID/sticky warnings
        if s.st_mode & stat.S_ISUID:
            lines.append("WARNING: SUID bit is set")
        if s.st_mode & stat.S_ISGID:
            lines.append("WARNING: SGID bit is set")
        if s.st_mode & stat.S_ISVTX:
            lines.append("NOTE: Sticky bit is set")
        return "\n".join(lines)
    except Exception as e:
        return f"Error checking permissions: {e}"


def run_command(command: str, working_dir: str = ".") -> str:
    """Run a shell command and return its output. Use with caution.

    Args:
        command: The shell command to execute.
        working_dir: Directory to run the command in. Defaults to current directory.
    """
    try:
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=30,
        )
        out = result.stdout
        err = result.stderr
        parts = []
        if out:
            parts.append(f"stdout:\n{out.rstrip()}")
        if err:
            parts.append(f"stderr:\n{err.rstrip()}")
        if result.returncode != 0:
            parts.append(f"exit code: {result.returncode}")
        return "\n".join(parts) if parts else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 30 seconds"
    except Exception as e:
        return f"Error running command: {e}"


def search_in_file(path: str, pattern: str) -> str:
    """Search for a text pattern in a file and return matching lines.

    Args:
        path: Path to the file to search.
        pattern: Text pattern to search for (case-sensitive substring match).
    """
    try:
        matches = []
        with open(path) as f:
            for i, line in enumerate(f, 1):
                if pattern in line:
                    matches.append(f"{i:5}: {line}", )
        if not matches:
            return f"No matches for '{pattern}' in {path}"
        return f"{len(matches)} match(es):\n" + "".join(matches)
    except Exception as e:
        return f"Error searching file: {e}"


ALL_TOOLS = [
    read_file,
    list_directory,
    hash_file,
    check_permissions,
    run_command,
    search_in_file,
]
