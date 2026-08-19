"""Artefactos derivados de la grabación: subtítulos y reporte JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .util import timestamp


@dataclass
class StepResult:
    index: int
    name: str
    start: float
    end: float
    narration: str | None = None
    narration_duration: float = 0.0
    actions: int = 0
    status: str = "ok"  # ok | failed
    error: str | None = None


@dataclass
class RecordingReport:
    ok: bool
    video: str
    title: str
    duration: float
    width: int
    height: int
    fps: int
    engine: str
    voice: str
    steps: list[StepResult] = field(default_factory=list)
    subtitles: str | None = None
    subtitles_vtt: str | None = None
    screenshots: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: dict | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["duration"] = round(self.duration, 2)
        for step in data["steps"]:
            step["start"] = round(step["start"], 2)
            step["end"] = round(step["end"], 2)
            step["narration_duration"] = round(step["narration_duration"], 2)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def _wrap(text: str, width: int = 42) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3] if len(lines) > 3 else lines


def write_subtitles(steps: list[StepResult], base: Path) -> tuple[Path | None, Path | None]:
    """Genera .srt y .vtt a partir de los pasos narrados."""
    entries = [s for s in steps if s.narration and s.narration_duration > 0]
    if not entries:
        return None, None

    srt_lines, vtt_lines = [], ["WEBVTT", ""]
    for i, step in enumerate(entries, start=1):
        start, end = step.start, step.start + step.narration_duration
        text = "\n".join(_wrap(step.narration or ""))
        srt_lines += [str(i), f"{timestamp(start)} --> {timestamp(end)}", text, ""]
        vtt_lines += [f"{timestamp(start, sep='.')} --> {timestamp(end, sep='.')}", text, ""]

    srt = base.with_suffix(".srt")
    vtt = base.with_suffix(".vtt")
    srt.write_text("\n".join(srt_lines), encoding="utf-8")
    vtt.write_text("\n".join(vtt_lines), encoding="utf-8")
    return srt, vtt


def write_report(report: RecordingReport, base: Path) -> Path:
    path = base.with_suffix(".report.json")
    path.write_text(report.to_json(), encoding="utf-8")
    return path
