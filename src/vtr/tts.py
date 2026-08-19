"""Síntesis de narración con edge-tts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import edge_tts

from .errors import TtsError
from .script import Script, Step
from .util import ensure_parent, log, media_duration

MAX_CONCURRENT_SYNTH = 4
RETRIES = 3


@dataclass
class Narration:
    step_index: int
    text: str
    path: Path
    duration: float


async def _synth_one(text: str, path: Path, *, voice: str, rate: str, pitch: str, volume: str) -> None:
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            comm = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch, volume=volume)
            await comm.save(str(path))
            if path.exists() and path.stat().st_size > 0:
                return
            raise TtsError("edge-tts devolvió un audio vacío")
        except Exception as exc:  # noqa: BLE001 - edge-tts lanza varios tipos
            last = exc
            path.unlink(missing_ok=True)
            if attempt < RETRIES:
                await asyncio.sleep(1.5 * attempt)
    raise TtsError(
        f"no se pudo sintetizar la voz '{voice}'",
        detail=f"{type(last).__name__}: {last}. edge-tts necesita acceso a internet.",
    )


async def synthesize_all(script: Script, workdir: Path) -> dict[int, Narration]:
    """Sintetiza la narración de todos los pasos antes de grabar.

    Conocer la duración de cada audio de antemano permite acompasar la
    navegación con la voz sin cortes ni silencios largos.
    """
    pending: list[Step] = [s for s in script.steps if s.narrate]
    if not pending:
        log("el guion no tiene narración; el video saldrá sin audio", level="warn")
        return {}

    workdir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(MAX_CONCURRENT_SYNTH)
    results: dict[int, Narration] = {}

    async def work(step: Step) -> None:
        path = workdir / f"narracion-{step.index:03d}.mp3"
        async with sem:
            await _synth_one(
                step.narrate or "",
                path,
                voice=step.voice or script.voice,
                rate=step.rate or script.rate,
                pitch=step.pitch or script.pitch,
                volume=step.volume or script.volume,
            )
        results[step.index] = Narration(
            step_index=step.index,
            text=step.narrate or "",
            path=path,
            duration=media_duration(path),
        )

    log(f"sintetizando {len(pending)} narraciones con edge-tts…")
    await asyncio.gather(*(work(s) for s in pending))
    total = sum(n.duration for n in results.values())
    log(f"narración lista: {len(results)} pistas, {total:.1f}s de voz", level="ok")
    return results


async def list_voices(language: str | None = None) -> list[dict]:
    try:
        voices = await edge_tts.list_voices()
    except Exception as exc:  # noqa: BLE001
        raise TtsError("no se pudo obtener la lista de voces", detail=str(exc)) from exc
    if language:
        needle = language.lower()
        voices = [v for v in voices if v.get("Locale", "").lower().startswith(needle)]
    return sorted(voices, key=lambda v: (v.get("Locale", ""), v.get("ShortName", "")))


async def say(text: str, out: Path, *, voice: str, rate: str = "+0%", pitch: str = "+0Hz", volume: str = "+0%") -> float:
    ensure_parent(out)
    await _synth_one(text, out, voice=voice, rate=rate, pitch=pitch, volume=volume)
    return media_duration(out)
