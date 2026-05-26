"""Download Alpine linux-virt APK and extract kernel + 9p modules for the sandbox VM."""

from __future__ import annotations

import gzip
import io
import tarfile
import urllib.request
from pathlib import Path

from rich.console import Console

from .paths import CACHE_DIR

console = Console()

_APK_INDEX = "https://dl-cdn.alpinelinux.org/alpine/v3.21/main/aarch64/APKINDEX.tar.gz"
_APK_BASE = "https://dl-cdn.alpinelinux.org/alpine/v3.21/main/aarch64"
_INITRD_URL = "https://dl-cdn.alpinelinux.org/alpine/v3.21/releases/aarch64/netboot/initramfs-virt"

VM_DIR = CACHE_DIR / "vm"
KERNEL_PATH = VM_DIR / "vmlinuz"
INITRD_PATH = VM_DIR / "initrd.img"

# 9p kernel modules needed for workspace mount (paths inside the APK)
_9P_MODULE_PATHS = [
    "fs/netfs/netfs.ko",        # required by 9pnet
    "net/9p/9pnet.ko",
    "net/9p/9pnet_virtio.ko",
    "fs/9p/9p.ko",
]


def ensure_kernel_and_initrd() -> tuple[Path, Path]:
    """Return (kernel, initrd) paths, downloading and building if needed."""
    VM_DIR.mkdir(parents=True, exist_ok=True)

    apk_path = _ensure_apk()
    mods_dir = VM_DIR / "modules"

    if not KERNEL_PATH.exists() or not mods_dir.exists():
        _extract_apk(apk_path, mods_dir)

    if not INITRD_PATH.exists():
        alpine_initrd = VM_DIR / "alpine-initramfs.gz"
        if not alpine_initrd.exists():
            _download(_INITRD_URL, alpine_initrd, "Alpine initramfs-virt")
        _build_initrd(alpine_initrd, mods_dir, INITRD_PATH)

    return KERNEL_PATH, INITRD_PATH


def _ensure_apk() -> Path:
    """Find and download the latest linux-virt APK, return its path."""
    apk_name = _latest_virt_apk_name()
    apk_path = VM_DIR / apk_name
    if not apk_path.exists():
        _download(f"{_APK_BASE}/{apk_name}", apk_path, f"Alpine {apk_name}")
    return apk_path


def _latest_virt_apk_name() -> str:
    """Fetch the APKINDEX to find the current linux-virt package filename."""
    console.print("[dim]Checking Alpine package index...[/]")
    data = urllib.request.urlopen(_APK_INDEX).read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        idx = tf.extractfile("APKINDEX")
        if idx is None:
            raise RuntimeError("Could not read APKINDEX")
        text = idx.read().decode()

    pkg, ver = None, None
    for block in text.split("\n\n"):
        fields = dict(
            line.split(":", 1) for line in block.splitlines() if ":" in line
        )
        if fields.get("P") == "linux-virt":
            ver = fields.get("V", "")
            pkg = f"linux-virt-{ver}.apk"
            break

    if not pkg:
        raise RuntimeError("linux-virt not found in Alpine APKINDEX")
    return pkg


def _extract_apk(apk_path: Path, mods_dir: Path) -> None:
    """Extract vmlinuz-virt and 9p .ko files from the APK."""
    console.print(f"[dim]Extracting kernel and modules from {apk_path.name}...[/]")
    mods_dir.mkdir(parents=True, exist_ok=True)

    with gzip.open(apk_path, "rb") as gz:
        raw = gz.read()

    with tarfile.open(fileobj=io.BytesIO(raw), mode="r") as tf:
        members = tf.getnames()

        # Extract kernel binary
        kernel_member = next((m for m in members if m.endswith("vmlinuz-virt")), None)
        if not kernel_member:
            raise RuntimeError("vmlinuz-virt not found in APK")
        data = tf.extractfile(kernel_member).read()
        KERNEL_PATH.write_bytes(data)
        console.print(f"[dim]  kernel: {KERNEL_PATH.name} ({len(data) // 1024} KB)[/]")

        # Determine kernel version from module directory
        kver = next(
            (m.split("lib/modules/")[1].split("/")[0]
             for m in members if m.startswith("lib/modules/") and "/kernel/" in m),
            None,
        )
        if not kver:
            raise RuntimeError("Could not determine kernel version from APK")
        console.print(f"[dim]  kernel version: {kver}[/]")

        # Extract 9p modules (may be .ko or .ko.gz)
        for mod_rel in _9P_MODULE_PATHS:
            for suffix in ("", ".gz"):
                member = f"lib/modules/{kver}/kernel/{mod_rel}{suffix}"
                if member in members:
                    raw_mod = tf.extractfile(member).read()
                    if suffix == ".gz":
                        raw_mod = gzip.decompress(raw_mod)
                    dest = mods_dir / Path(mod_rel).name
                    dest.write_bytes(raw_mod)
                    console.print(f"[dim]  module: {dest.name} ({len(raw_mod) // 1024} KB)[/]")
                    break


def _build_initrd(alpine_initrd: Path, mods_dir: Path, dest: Path) -> None:
    """Append a cpio overlay (our /init + 9p modules) to Alpine's initramfs."""
    console.print("[dim]Building sandbox initrd...[/]")

    files: dict[str, tuple[int, bytes]] = {
        "init": (0o755, _INIT_SCRIPT.encode()),
    }
    for mod in mods_dir.iterdir():
        files[f"lib/modules/{mod.name}"] = (0o644, mod.read_bytes())

    override = gzip.compress(_make_cpio(files))
    with open(dest, "wb") as f:
        f.write(alpine_initrd.read_bytes())
        f.write(override)


def _download(url: str, dest: Path, label: str) -> None:
    console.print(f"[dim]Downloading {label}...[/]")
    urllib.request.urlretrieve(url, dest)
    console.print(f"[dim]  saved {dest.name} ({dest.stat().st_size // 1024} KB)[/]")


# ── cpio builder (newc format) ────────────────────────────────────────────────

def _make_cpio(files: dict[str, tuple[int, bytes]]) -> bytes:
    buf = io.BytesIO()
    for ino, (name, (mode, data)) in enumerate(files.items(), start=1):
        _write_entry(buf, ino, 0o100000 | mode, name, data)
    _write_entry(buf, 0, 0, "TRAILER!!!", b"")
    pos = buf.tell()
    if pos % 512:
        buf.write(b"\x00" * (512 - pos % 512))
    return buf.getvalue()


def _write_entry(buf: io.BytesIO, ino: int, mode: int, name: str, data: bytes) -> None:
    name_bytes = name.encode() + b"\x00"
    hdr = (
        f"070701"
        f"{ino:08x}"
        f"{mode:08x}"
        f"00000000"
        f"00000000"
        f"00000001"
        f"00000000"
        f"{len(data):08x}"
        f"00000003"
        f"00000001"
        f"00000000"
        f"00000000"
        f"{len(name_bytes):08x}"
        f"00000000"
    ).encode()
    buf.write(hdr)
    buf.write(name_bytes)
    _pad4(buf, len(hdr) + len(name_bytes))
    buf.write(data)
    _pad4(buf, len(data))


def _pad4(buf: io.BytesIO, n: int) -> None:
    if n % 4:
        buf.write(b"\x00" * (4 - n % 4))


# ── guest init script ─────────────────────────────────────────────────────────

_INIT_SCRIPT = """\
#!/bin/busybox sh
/bin/busybox --install -s /bin 2>/dev/null
export PATH=/bin:/sbin:/usr/bin:/usr/sbin

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null || mdev -s

# Load 9p modules for workspace mount (order matters: deps first)
insmod /lib/modules/netfs.ko 2>/dev/null
insmod /lib/modules/9pnet.ko 2>/dev/null
insmod /lib/modules/9pnet_virtio.ko 2>/dev/null
insmod /lib/modules/9p.ko 2>/dev/null

mkdir -p /workspace
mount -t 9p -o trans=virtio,version=9p2000.L workspace /workspace 2>/dev/null

exec >/dev/ttyAMA0 2>&1 0</dev/ttyAMA0
stty -echo raw

echo CODCODE_READY
while true; do
    read -r CMD
    case "$CMD" in
        __EXIT__) poweroff -f; break;;
        *) ( cd /workspace && eval "$CMD" ) 2>&1; echo "---CODCODE_EXIT:$?---";;
    esac
done
"""
