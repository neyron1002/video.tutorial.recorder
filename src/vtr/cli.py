"""Interfaz de línea de comandos: `vtr`.

Pensada para ser usada por agentes de IA: stdout siempre es limpio (JSON cuando
se pide `--json`), los mensajes de progreso van a stderr y los códigos de salida
son estables.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .errors import ScriptError, VtrError
from .script import DEFAULT_VOICE, load_script
from .util import human_duration, log, set_quiet

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID_SCRIPT = 2

EXAMPLE = Path(__file__).parent / "assets" / "ejemplo.tutorial.yaml"


# --------------------------------------------------------------------------- #
# Comandos
# --------------------------------------------------------------------------- #
def cmd_record(args: argparse.Namespace) -> int:
    from .recorder import record

    script = load_script(args.script)
    _apply_overrides(script, args)

    out = Path(args.output).expanduser() if args.output else None
    report = asyncio.run(record(script, output=out))

    if args.json:
        print(report.to_json())
    elif report.ok:
        print(report.video)
        log(
            f"{len(report.steps)} pasos · {human_duration(report.duration)} · "
            f"{report.width}x{report.height}@{report.fps}",
            level="ok",
        )
    for warning in report.warnings:
        log(warning, level="warn")
    return EXIT_OK if report.ok else EXIT_ERROR


def cmd_validate(args: argparse.Namespace) -> int:
    script = load_script(args.script)
    summary = {
        "ok": True,
        "script": str(script.source),
        "title": script.title,
        "output": str(script.output_path),
        "engine": script.engine,
        "voice": script.voice,
        "resolution": f"{script.width}x{script.height}",
        "steps": len(script.steps),
        "narrated_steps": sum(1 for s in script.steps if s.narrate),
        "actions": sum(len(s.actions) for s in script.steps),
        "estimated_words": sum(len((s.narrate or "").split()) for s in script.steps),
    }
    # ~2.6 palabras/segundo es una velocidad de locución neutra en español.
    summary["estimated_duration_s"] = round(
        summary["estimated_words"] / 2.6 + len(script.steps) * script.step_gap + script.lead_in + script.lead_out,
        1,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for key, value in summary.items():
            print(f"{key:20} {value}")
    return EXIT_OK


def cmd_schema(args: argparse.Namespace) -> int:
    from .schema import script_schema

    text = json.dumps(script_schema(), ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        log(f"esquema escrito en {args.output}", level="ok")
    else:
        print(text)
    return EXIT_OK


def cmd_voices(args: argparse.Namespace) -> int:
    from .tts import list_voices

    voices = asyncio.run(list_voices(args.lang))
    if args.json:
        print(json.dumps(voices, ensure_ascii=False, indent=2))
    else:
        for voice in voices:
            tags = ", ".join(voice.get("VoiceTag", {}).get("VoicePersonalities", []) or [])
            print(f"{voice['ShortName']:32} {voice.get('Gender', ''):8} {tags}")
        log(f"{len(voices)} voces", level="ok")
    return EXIT_OK


def cmd_say(args: argparse.Namespace) -> int:
    from .tts import say

    out = Path(args.output).expanduser()
    duration = asyncio.run(say(args.text, out, voice=args.voice, rate=args.rate, pitch=args.pitch))
    if args.json:
        print(json.dumps({"ok": True, "audio": str(out), "duration": round(duration, 2)}, ensure_ascii=False))
    else:
        print(str(out))
        log(f"{duration:.1f}s de audio", level="ok")
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser()
    if target.is_dir():
        target = target / "tutorial.yaml"
    if target.exists() and not args.force:
        raise VtrError(f"ya existe {target}; usa --force para sobrescribir")
    target.parent.mkdir(parents=True, exist_ok=True)
    content = EXAMPLE.read_text(encoding="utf-8")
    if args.url:
        content = content.replace("https://playwright.dev", args.url.rstrip("/"))
    target.write_text(content, encoding="utf-8")
    if args.json:
        print(json.dumps({"ok": True, "script": str(target)}, ensure_ascii=False))
    else:
        print(str(target))
        log("edita el guion y grábalo con: vtr record " + str(target), level="ok")
    return EXIT_OK


async def _check_chromium() -> str:
    """Lanza Chromium de verdad: comprobar solo el binario deja pasar fallos."""
    import os

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    try:
        args = ["--disable-dev-shm-usage"]
        if os.environ.get("VTR_NO_SANDBOX", "1") == "1":
            args += ["--no-sandbox", "--disable-setuid-sandbox"]
        browser = await pw.chromium.launch(headless=True, args=args, chromium_sandbox=False)
        version = browser.version
        await browser.close()
        return f"{pw.chromium.executable_path} (v{version})"
    finally:
        await pw.stop()


def cmd_doctor(args: argparse.Namespace) -> int:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    for binary in ("ffmpeg", "ffprobe", "Xvfb", "xdpyinfo"):
        path = shutil.which(binary)
        add(binary, bool(path), path or "no encontrado en PATH")

    try:
        add("chromium", True, asyncio.run(_check_chromium()))
    except Exception as exc:  # noqa: BLE001
        add("chromium", False, f"{type(exc).__name__}: {exc}")

    try:
        from .tts import list_voices

        voices = asyncio.run(list_voices("es"))
        add("edge-tts", bool(voices), f"{len(voices)} voces en español disponibles")
    except Exception as exc:  # noqa: BLE001
        add("edge-tts", False, f"{type(exc).__name__}: {exc}")

    ok = all(c["ok"] for c in checks)
    if args.json:
        print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        for check in checks:
            mark = "✓" if check["ok"] else "✗"
            print(f"{mark} {check['check']:12} {check['detail']}")
    return EXIT_OK if ok else EXIT_ERROR


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def _apply_overrides(script, args: argparse.Namespace) -> None:
    if args.engine:
        script.engine = args.engine
    if args.voice:
        script.voice = args.voice
    if args.base_url:
        script.base_url = args.base_url
    if args.fps:
        script.fps = args.fps
    if args.screen:
        width, height = (int(v) for v in args.screen.lower().split("x")[:2])
        script.width, script.height = width - width % 2, height - height % 2
    if args.keep_temp:
        script.keep_temp = True
    if args.no_subtitles:
        script.subtitles = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vtr",
        description="Graba video tutoriales de aplicaciones web: Playwright navega, edge-tts narra.",
    )
    parser.add_argument("--version", action="version", version=f"vtr {__version__}")
    parser.add_argument("-q", "--quiet", action="store_true", help="silencia el progreso en stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("record", help="graba el video a partir de un guion")
    p.add_argument("script", help="ruta del guion .yaml o .json")
    p.add_argument("-o", "--output", help="MP4 de salida (sobrescribe el del guion)")
    p.add_argument("--engine", choices=("xvfb", "playwright"), help="motor de captura")
    p.add_argument("--voice", help="voz de edge-tts")
    p.add_argument("--base-url", help="URL base")
    p.add_argument("--screen", help="resolución, p.ej. 1920x1080")
    p.add_argument("--fps", type=int, help="fotogramas por segundo")
    p.add_argument("--keep-temp", action="store_true", help="conserva archivos intermedios")
    p.add_argument("--no-subtitles", action="store_true", help="no generar .srt/.vtt")
    p.add_argument("--json", action="store_true", help="imprime el reporte JSON en stdout")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("validate", help="valida el guion sin grabar")
    p.add_argument("script")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("schema", help="imprime el JSON Schema del guion")
    p.add_argument("-o", "--output", help="escribe el esquema en un archivo")
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser("voices", help="lista las voces de edge-tts")
    p.add_argument("-l", "--lang", help="filtra por idioma o locale, p.ej. 'es' o 'es-MX'")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_voices)

    p = sub.add_parser("say", help="sintetiza un texto a MP3 (prueba de voz)")
    p.add_argument("text")
    p.add_argument("-o", "--output", default="voz.mp3")
    p.add_argument("--voice", default=DEFAULT_VOICE)
    p.add_argument("--rate", default="+0%")
    p.add_argument("--pitch", default="+0Hz")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_say)

    p = sub.add_parser("init", help="crea un guion de ejemplo")
    p.add_argument("path", nargs="?", default="tutorial.yaml")
    p.add_argument("--url", help="base_url de tu aplicación")
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("doctor", help="verifica el entorno (ffmpeg, Xvfb, Chromium, edge-tts)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    set_quiet(bool(getattr(args, "quiet", False)))
    want_json = bool(getattr(args, "json", False))
    try:
        return args.func(args)
    except ScriptError as exc:
        if want_json:
            print(json.dumps({"ok": False, **exc.to_dict()}, ensure_ascii=False, indent=2))
        else:
            log(exc.message, level="error")
            if exc.detail:
                log(exc.detail, level="error")
        return EXIT_INVALID_SCRIPT
    except VtrError as exc:
        if want_json:
            print(json.dumps({"ok": False, **exc.to_dict()}, ensure_ascii=False, indent=2))
        else:
            log(exc.message, level="error")
            if exc.detail:
                log(exc.detail, level="error")
        return EXIT_ERROR
    except KeyboardInterrupt:
        log("interrumpido", level="warn")
        return 130


if __name__ == "__main__":
    sys.exit(main())
