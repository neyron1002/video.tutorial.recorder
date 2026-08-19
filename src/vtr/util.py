"""Utilidades comunes: ejecución de procesos, ffprobe y registro en consola."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .errors import DependencyError

_QUIET = False
_START = time.monotonic()


def set_quiet(value: bool) -> None:
    global _QUIET
    _QUIET = value


def log(message: str, *, level: str = "info") -> None:
    """Registro humano en stderr (stdout queda libre para JSON)."""
    if _QUIET and level == "info":
        return
    colors = {"info": "\033[36m", "ok": "\033[32m", "warn": "\033[33m", "error": "\033[31m", "step": "\033[35m"}
    icons = {"info": "·", "ok": "✓", "warn": "!", "error": "✗", "step": "▶"}
    color = colors.get(level, "") if sys.stderr.isatty() else ""
    reset = "\033[0m" if color else ""
    elapsed = time.monotonic() - _START
    print(f"{color}{icons.get(level, '·')}{reset} [{elapsed:6.1f}s] {message}", file=sys.stderr, flush=True)


def require_binary(name: str, *, hint: str = "") -> str:
    path = shutil.which(name)
    if not path:
        raise DependencyError(
            f"no se encontró el ejecutable '{name}' en PATH",
            detail=hint or "Ejecuta el recorder dentro del contenedor de desarrollo del proyecto.",
        )
    return path


def run(cmd: list[str], *, timeout: float = 120, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise DependencyError(
            f"falló el comando: {' '.join(cmd[:3])}...",
            detail=(proc.stderr or proc.stdout or "").strip()[-2000:],
        )
    return proc


def media_duration(path: str | Path) -> float:
    """Duración en segundos de un archivo de audio/video, vía ffprobe."""
    require_binary("ffprobe")
    proc = run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=60,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise DependencyError(f"ffprobe no devolvió duración para {path}", detail=proc.stdout) from exc


def timestamp(seconds: float, *, sep: str = ",") -> str:
    """Formatea segundos como HH:MM:SS,mmm (SRT) o HH:MM:SS.mmm (VTT)."""
    seconds = max(0.0, seconds)
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def human_duration(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def free_display() -> str:
    """Devuelve un número de display X libre, p.ej. ':81'."""
    used = set()
    sock_dir = Path("/tmp/.X11-unix")
    if sock_dir.is_dir():
        for entry in sock_dir.iterdir():
            if entry.name.startswith("X") and entry.name[1:].isdigit():
                used.add(int(entry.name[1:]))
    for num in range(80, 200):
        if num not in used and not Path(f"/tmp/.X{num}-lock").exists():
            return f":{num}"
    raise DependencyError("no hay displays X libres disponibles")


def is_inside_container() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("VTR_IN_CONTAINER") == "1"
