"""Ensamblado final: coloca cada narración en su instante y la mezcla con el video."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import MuxError
from .util import log, require_binary


@dataclass
class AudioCue:
    """Una narración y el segundo del video en el que debe empezar."""

    path: Path
    offset: float
    title: str = ""


def _escape_meta(value: str) -> str:
    for ch in ("\\", "=", ";", "#", "\n"):
        value = value.replace(ch, "\\" + ch if ch != "\n" else "\\\n")
    return value


def write_chapters(cues: list[tuple[str, float, float]], path: Path) -> Path:
    """Escribe un archivo ffmetadata con un capítulo por paso narrado."""
    lines = [";FFMETADATA1"]
    for title, start, end in cues:
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={int(start * 1000)}",
            f"END={int(max(end, start + 0.5) * 1000)}",
            f"title={_escape_meta(title)}",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def mux(
    video: Path,
    cues: list[AudioCue],
    output: Path,
    *,
    title: str = "",
    chapters_file: Path | None = None,
    reencode_video: bool = False,
) -> Path:
    """Mezcla las narraciones sobre la pista de video y escribe el MP4 final."""
    require_binary("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    for cue in cues:
        cmd += ["-i", str(cue.path)]

    meta_index = None
    if chapters_file is not None:
        meta_index = 1 + len(cues)
        cmd += ["-i", str(chapters_file)]

    if cues:
        parts = []
        for i, cue in enumerate(cues, start=1):
            ms = max(0, int(round(cue.offset * 1000)))
            parts.append(f"[{i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
        mix_inputs = "".join(f"[a{i}]" for i in range(1, len(cues) + 1))
        parts.append(f"{mix_inputs}amix=inputs={len(cues)}:normalize=0:dropout_transition=0[aout]")
        cmd += ["-filter_complex", ";".join(parts), "-map", "0:v:0", "-map", "[aout]"]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    else:
        cmd += ["-map", "0:v:0", "-an"]

    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"] if reencode_video \
        else ["-c:v", "copy"]

    if meta_index is not None:
        cmd += ["-map_metadata", str(meta_index)]
    if title:
        cmd += ["-metadata", f"title={title}"]
    cmd += ["-movflags", "+faststart", str(output)]

    log("ensamblando audio y video con ffmpeg…")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0 or not output.exists():
        raise MuxError(
            "ffmpeg no pudo generar el MP4 final",
            detail=(proc.stderr or proc.stdout or "").strip()[-2000:],
        )
    return output


def webm_to_mp4(source: Path, target: Path, *, fps: int = 30, crf: int = 21) -> Path:
    """Convierte el .webm que produce Playwright a un MP4 con timeline estable."""
    require_binary("ffmpeg")
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source),
        "-vf", f"fps={fps},format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
        "-movflags", "+faststart",
        str(target),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0 or not target.exists():
        raise MuxError("no se pudo convertir el video de Playwright a MP4", detail=proc.stderr[-2000:])
    return target
