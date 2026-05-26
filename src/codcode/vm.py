"""QEMU-based Linux sandbox for tool execution."""

from __future__ import annotations

import os
import pty
import select
import subprocess
import termios
import threading
import time
from pathlib import Path

_SENTINEL = "---CODCODE_EXIT:"
_READY_LINE = "CODCODE_READY"
_STOP_CMD = "__EXIT__"

# QEMU binary — prefer Homebrew aarch64 on Apple Silicon
_QEMU = "/opt/homebrew/bin/qemu-system-aarch64"


class SandboxVM:
    """QEMU Linux VM that mounts shared_dir at /workspace and runs commands via serial console."""

    def __init__(
        self,
        shared_dir: Path,
        kernel: Path,
        initrd: Path,
        cpus: int = 2,
        memory_mb: int = 512,
    ) -> None:
        self.shared_dir = shared_dir.resolve()
        self.kernel = kernel
        self.initrd = initrd
        self.cpus = cpus
        self.memory_mb = memory_mb
        self._proc: subprocess.Popen | None = None
        self._master_fd: int | None = None  # PTY master (host side)
        self._buf = ""
        self._lock = threading.Lock()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the QEMU VM and wait until the guest shell signals ready."""
        # Create a PTY for the serial console
        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd

        cmd = self._build_qemu_cmd(os.ttyname(slave_fd))
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            pass_fds=(slave_fd,),
        )
        os.close(slave_fd)  # QEMU has it now

        # Raw mode on the master so the PTY line discipline doesn't mangle I/O
        attrs = termios.tcgetattr(master_fd)
        attrs[3] &= ~(termios.ECHO | termios.ICANON)  # no echo, no line buffering
        termios.tcsetattr(master_fd, termios.TCSANOW, attrs)

        self._wait_ready(timeout=60)

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            os.write(self._master_fd, f"{_STOP_CMD}\n".encode())
        except OSError:
            pass
        time.sleep(0.3)
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        if self._master_fd is not None:
            os.close(self._master_fd)
        self._proc = None
        self._master_fd = None

    # ── command execution ─────────────────────────────────────────────────────

    def run(self, command: str, timeout: int = 30) -> tuple[str, int]:
        """Run a shell command in the VM; return (output, exit_code)."""
        with self._lock:
            os.write(self._master_fd, (command.rstrip("\n") + "\n").encode())
            return self._read_until_sentinel(timeout)

    def _read_until_sentinel(self, timeout: int) -> tuple[str, int]:
        output: list[str] = []
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            r, _, _ = select.select([self._master_fd], [], [], min(remaining, 0.1))
            if r:
                try:
                    chunk = os.read(self._master_fd, 4096).decode("utf-8", errors="replace")
                except OSError:
                    break
                self._buf += chunk

            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                line = line.rstrip("\r")
                if line.startswith(_SENTINEL):
                    try:
                        code = int(line.removeprefix(_SENTINEL).removesuffix("---"))
                    except ValueError:
                        code = 0
                    return "".join(output), code
                output.append(line + "\n")

        raise TimeoutError(f"VM command timed out after {timeout}s")

    def _wait_ready(self, timeout: int) -> None:
        deadline = time.monotonic() + timeout
        buf = ""
        while time.monotonic() < deadline:
            r, _, _ = select.select([self._master_fd], [], [], 0.2)
            if r:
                try:
                    chunk = os.read(self._master_fd, 256).decode("utf-8", errors="replace")
                except OSError:
                    break
                buf += chunk
                if _READY_LINE in buf:
                    idx = buf.index(_READY_LINE) + len(_READY_LINE)
                    self._buf = buf[idx:].lstrip("\r\n")
                    return
        raise RuntimeError("VM guest did not become ready within 60s")

    # ── QEMU configuration ────────────────────────────────────────────────────

    def _build_qemu_cmd(self, serial_tty: str) -> list[str]:
        return [
            _QEMU,
            "-M", "virt,highmem=off",
            "-cpu", "cortex-a57",
            "-smp", str(self.cpus),
            "-m", str(self.memory_mb),
            "-kernel", str(self.kernel),
            "-initrd", str(self.initrd),
            "-append", "console=ttyAMA0 quiet loglevel=0",
            # Serial console on PTY slave
            "-serial", serial_tty,
            # 9pfs share: tag "workspace" → /workspace in guest
            "-fsdev", f"local,id=workspace,path={self.shared_dir},security_model=mapped-xattr",
            "-device", "virtio-9p-pci,fsdev=workspace,mount_tag=workspace",
            # No graphics, no monitor
            "-nographic",
            "-monitor", "none",
            "-no-reboot",
        ]
