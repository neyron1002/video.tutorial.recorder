"""Orquestador: narración + navegación + captura → MP4 con subtítulos y reporte."""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path

from .browser import CHROME_MARGIN, BrowserSession, Director, launch
from .capture import ScreenRecorder, VirtualDisplay
from .errors import BrowserError, CaptureError, VtrError
from .mux import AudioCue, mux, webm_to_mp4, write_chapters
from .report import RecordingReport, StepResult, write_report, write_subtitles
from .script import Script
from .tts import Narration, synthesize_all
from .util import ensure_parent, human_duration, log, media_duration


class Timeline:
    """Reloj alineado con el primer fotograma del video."""

    def __init__(self) -> None:
        self.t0 = time.monotonic()

    def reset(self, t0: float | None = None) -> None:
        self.t0 = t0 if t0 is not None else time.monotonic()

    @property
    def now(self) -> float:
        return time.monotonic() - self.t0


async def record(script: Script, *, output: Path | None = None) -> RecordingReport:
    out = Path(output) if output else script.output_path
    out = out if out.is_absolute() else Path.cwd() / out
    ensure_parent(out)

    tmp = out.parent / f".vtr-{out.stem}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    report = RecordingReport(
        ok=True,
        video=str(out),
        title=script.title,
        duration=0.0,
        width=script.width,
        height=script.height,
        fps=script.fps,
        engine=script.engine,
        voice=script.voice,
    )

    try:
        narrations = await synthesize_all(script, tmp / "voz")
        if script.engine == "xvfb":
            await _run_xvfb(script, out, tmp, narrations, report)
        else:
            await _run_playwright(script, out, tmp, narrations, report)
    except VtrError as exc:
        report.ok = False
        report.error = exc.to_dict()
        log(exc.message, level="error")
        if exc.detail:
            log(exc.detail, level="error")
    finally:
        if not script.keep_temp and tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        elif tmp.exists():
            log(f"archivos intermedios en {tmp}", level="warn")

    return report


# --------------------------------------------------------------------------- #
# Motores
# --------------------------------------------------------------------------- #
async def _run_xvfb(
    script: Script,
    out: Path,
    tmp: Path,
    narrations: dict[int, Narration],
    report: RecordingReport,
) -> None:
    # Cuando el guion pide video sin barra de direcciones, la pantalla virtual
    # se agranda y luego recortamos el cromo del navegador.
    screen_w = script.width
    screen_h = script.height + (0 if script.browser_ui else CHROME_MARGIN)

    display = VirtualDisplay(screen_w, screen_h)
    display.start()
    session: BrowserSession | None = None
    recorder: ScreenRecorder | None = None
    raw = tmp / "pantalla.mp4"
    try:
        session = await launch(
            script,
            display=display.display,
            screen_w=screen_w,
            screen_h=screen_h,
            profile_dir=tmp / "perfil",
        )

        crop_y = 0
        if not script.browser_ui:
            crop_y = min(session.chrome_height or CHROME_MARGIN, CHROME_MARGIN)
            crop_y -= crop_y % 2

        recorder = ScreenRecorder(
            display.display,
            raw,
            width=script.width,
            height=script.height,
            offset_x=0,
            offset_y=crop_y,
            fps=script.fps,
            crf=script.crf,
            preset=script.preset,
            draw_mouse=script.cursor != "off",
        )
        timeline = Timeline()
        timeline.reset(recorder.start())

        cues = await _play(script, session, timeline, narrations, report, out.parent)
        duration = recorder.stop()
        shift = recorder.bias
        recorder = None
    finally:
        if recorder is not None:
            try:
                recorder.stop()
            except CaptureError:
                pass
        if session is not None:
            await session.close()
        display.stop()

    _finish(script, out, tmp, raw, cues, report, shift=shift)


async def _run_playwright(
    script: Script,
    out: Path,
    tmp: Path,
    narrations: dict[int, Narration],
    report: RecordingReport,
) -> None:
    video_dir = tmp / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    session = await launch(
        script,
        display=None,
        screen_w=script.width,
        screen_h=script.height,
        profile_dir=tmp / "perfil",
        video_dir=video_dir,
    )
    timeline = Timeline()
    try:
        cues = await _play(script, session, timeline, narrations, report, out.parent)
        elapsed = timeline.now
    finally:
        await session.close()  # el .webm se escribe al cerrar el contexto

    webm = next(iter(sorted(video_dir.glob("*.webm"))), None)
    if webm is None:
        raise CaptureError("Playwright no generó ningún video")
    raw = tmp / "pantalla.mp4"
    webm_to_mp4(webm, raw, fps=script.fps, crf=script.crf)
    # La grabación nativa empieza al crear la página, algo antes de nuestro t0.
    shift = max(0.0, min(5.0, media_duration(raw) - elapsed))
    _finish(script, out, tmp, raw, cues, report, shift=shift)


# --------------------------------------------------------------------------- #
# Ejecución del guion
# --------------------------------------------------------------------------- #
async def _play(
    script: Script,
    session: BrowserSession,
    timeline: Timeline,
    narrations: dict[int, Narration],
    report: RecordingReport,
    output_dir: Path,
) -> list[AudioCue]:
    director = Director(session, script, output_dir=output_dir)
    cues: list[AudioCue] = []

    if script.lead_in > 0:
        await asyncio.sleep(script.lead_in)

    for step in script.steps:
        if step.pause_before > 0:
            await asyncio.sleep(step.pause_before)

        start = timeline.now
        narration = narrations.get(step.index)
        label = f"[{step.index + 1}/{len(script.steps)}] {step.name}"
        log(f"{label}  t={start:6.1f}s", level="step")

        if narration:
            cues.append(AudioCue(path=narration.path, offset=start, title=step.name))

        result = StepResult(
            index=step.index,
            name=step.name,
            start=start,
            end=start,
            narration=step.narrate,
            narration_duration=narration.duration if narration else 0.0,
            actions=len(step.actions),
        )
        report.steps.append(result)

        try:
            for action in step.actions:
                await director.run(action)
        except BrowserError as exc:
            result.status = "failed"
            result.error = exc.message
            result.end = timeline.now
            report.ok = False
            report.error = exc.to_dict()
            log(exc.message, level="error")
            await _failure_shot(director, output_dir, step.index, report)
            break

        # El paso dura lo que dure la parte más lenta: acciones o narración.
        if narration and step.wait_for_narration:
            remaining = narration.duration - (timeline.now - start)
            if remaining > 0:
                await asyncio.sleep(remaining)
            elif remaining < -1.0:
                report.warnings.append(
                    f"paso '{step.name}': las acciones tardaron {abs(remaining):.1f}s más que la narración"
                )

        gap = script.step_gap if step.pause_after is None else step.pause_after
        if gap > 0:
            await asyncio.sleep(gap)
        result.end = timeline.now

    if script.lead_out > 0:
        await asyncio.sleep(script.lead_out)

    report.screenshots.extend(director.screenshots)
    return cues


async def _failure_shot(director: Director, output_dir: Path, index: int, report: RecordingReport) -> None:
    """Captura el estado de la página al fallar, para que el agente pueda depurar."""
    try:
        path = output_dir / "capturas" / f"fallo-paso-{index + 1:02d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        await director.page.screenshot(path=str(path))
        report.screenshots.append(str(path))
        log(f"captura del fallo: {path}", level="warn")
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Cierre
# --------------------------------------------------------------------------- #
def _finish(
    script: Script,
    out: Path,
    tmp: Path,
    raw: Path,
    cues: list[AudioCue],
    report: RecordingReport,
    *,
    shift: float = 0.0,
) -> None:
    # `shift` corrige el desfase entre el inicio real del video y nuestro reloj.
    if shift > 0.01:
        for cue in cues:
            cue.offset += shift
        for step in report.steps:
            step.start += shift
            step.end += shift

    chapters_file = None
    if script.chapters and report.steps:
        marks = [(s.name, s.start, s.end) for s in report.steps]
        chapters_file = write_chapters(marks, tmp / "capitulos.txt")

    mux(raw, cues, out, title=script.title, chapters_file=chapters_file)
    report.duration = media_duration(out)
    report.video = str(out)

    if script.subtitles:
        srt, vtt = write_subtitles(report.steps, out)
        report.subtitles = str(srt) if srt else None
        report.subtitles_vtt = str(vtt) if vtt else None

    write_report(report, out)
    log(f"video listo: {out}  ({human_duration(report.duration)})", level="ok")
