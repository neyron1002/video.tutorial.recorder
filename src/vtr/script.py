"""Carga y validación del guion (YAML o JSON) a un modelo tipado."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .actionspec import ACTION_BY_NAME, ACTION_NAMES, ActionSpec
from .errors import ScriptError

DEFAULT_VOICE = "es-MX-DaliaNeural"

# Claves que puede llevar una acción además del nombre de la acción.
ACTION_META_KEYS = {"comment", "note_to_self"}


# --------------------------------------------------------------------------- #
# Modelo
# --------------------------------------------------------------------------- #
@dataclass
class Action:
    type: str
    params: dict[str, Any]
    path: str  # p.ej. "steps[2].actions[0]" para mensajes de error


@dataclass
class Step:
    index: int
    name: str
    narrate: str | None = None
    voice: str | None = None
    rate: str | None = None
    pitch: str | None = None
    volume: str | None = None
    actions: list[Action] = field(default_factory=list)
    wait_for_narration: bool = True
    pause_before: float = 0.0
    pause_after: float | None = None  # None => usa step_gap del guion


@dataclass
class Script:
    title: str
    output: str
    steps: list[Step]
    source: Path
    base_url: str | None = None
    voice: str = DEFAULT_VOICE
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    width: int = 1600
    height: int = 900
    fps: int = 30
    engine: str = "xvfb"  # xvfb | playwright
    browser_ui: bool = True
    cursor: str = "auto"  # auto | on | off
    lead_in: float = 1.0
    lead_out: float = 1.5
    step_gap: float = 0.5
    timeout: float = 20.0
    move_steps: int = 25
    crf: int = 21
    preset: str = "veryfast"
    locale: str = "es-MX"
    timezone: str | None = None
    color_scheme: str | None = None  # light | dark
    user_agent: str | None = None
    storage_state: str | None = None
    http_credentials: dict[str, str] | None = None
    extra_http_headers: dict[str, str] | None = None
    ignore_https_errors: bool = False
    subtitles: bool = True
    chapters: bool = True
    keep_temp: bool = False

    @property
    def base_dir(self) -> Path:
        return self.source.parent

    def resolve(self, relative: str) -> Path:
        """Resuelve una ruta del guion respecto al directorio del propio guion."""
        p = Path(relative).expanduser()
        return p if p.is_absolute() else (self.base_dir / p)

    @property
    def output_path(self) -> Path:
        return self.resolve(self.output)


# --------------------------------------------------------------------------- #
# Utilidades de validación
# --------------------------------------------------------------------------- #
def _fail(path: str, msg: str) -> None:
    raise ScriptError(f"{path}: {msg}")


def _as_dict(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        _fail(path, f"se esperaba un objeto, se recibió {type(value).__name__}")
    return value


def _num(value: Any, path: str, *, integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, f"se esperaba un número, se recibió {value!r}")
    return int(value) if integer else float(value)


def _str(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _fail(path, f"se esperaba texto, se recibió {value!r}")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, f"se esperaba true/false, se recibió {value!r}")
    return value


def _coerce(spec: ActionSpec, name: str, value: Any, path: str) -> Any:
    p = spec.param(name)
    if p is None:
        known = ", ".join(sorted(q.name for q in spec.params)) or "(ninguno)"
        _fail(path, f"parámetro desconocido '{name}' para la acción '{spec.name}'. Válidos: {known}")
    where = f"{path}.{name}"
    if p.type == "string":
        value = _str(value, where)
    elif p.type == "number":
        value = _num(value, where)
    elif p.type == "integer":
        value = _num(value, where, integer=True)
    elif p.type == "boolean":
        value = _bool(value, where)
    elif p.type == "array":
        if not isinstance(value, list):
            _fail(where, f"se esperaba una lista, se recibió {value!r}")
    elif p.type == "object":
        value = _as_dict(value, where)
    if p.enum and value not in p.enum:
        _fail(where, f"valor '{value}' inválido. Permitidos: {', '.join(p.enum)}")
    return value


def parse_action(raw: Any, path: str) -> Action:
    """Normaliza una acción a `Action(type, params)`.

    Formas admitidas:
      - `reload`                              (cadena, acción sin parámetros)
      - `{click: "#boton"}`                   (abreviada)
      - `{type: {selector: "#u", text: "a"}}` (mapa de parámetros)
      - `{action: "click", selector: "#b"}`   (explícita)
    """
    if isinstance(raw, str):
        spec = ACTION_BY_NAME.get(raw)
        if spec is None:
            _fail(path, f"acción desconocida '{raw}'. Disponibles: {', '.join(ACTION_NAMES)}")
        if spec.required:
            _fail(path, f"la acción '{raw}' requiere parámetros: {', '.join(spec.required)}")
        return Action(spec.name, {}, path)

    data = dict(_as_dict(raw, path))
    for meta in ACTION_META_KEYS:
        data.pop(meta, None)

    if "action" in data:
        name = _str(data.pop("action"), f"{path}.action")
        spec = ACTION_BY_NAME.get(name)
        if spec is None:
            _fail(path, f"acción desconocida '{name}'. Disponibles: {', '.join(ACTION_NAMES)}")
        params = data
    else:
        keys = list(data)
        if len(keys) != 1:
            _fail(
                path,
                "una acción debe ser un objeto con exactamente una clave (el nombre de la acción) "
                f"o llevar la clave 'action'. Recibido: {keys}",
            )
        name = keys[0]
        spec = ACTION_BY_NAME.get(name)
        if spec is None:
            _fail(path, f"acción desconocida '{name}'. Disponibles: {', '.join(ACTION_NAMES)}")
        value = data[name]
        if isinstance(value, dict):
            params = dict(value)
        elif value is None:
            params = {}
        else:
            if spec.shorthand is None:
                _fail(
                    path,
                    f"la acción '{name}' no admite forma abreviada; usa un objeto con "
                    f"{', '.join(p.name for p in spec.params)}",
                )
            params = {spec.shorthand: value}

    clean: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        clean[key] = _coerce(spec, key, value, f"{path}.{spec.name}")

    for req in spec.required:
        if req not in clean:
            _fail(f"{path}.{spec.name}", f"falta el parámetro obligatorio '{req}'")

    # Validaciones cruzadas.
    if spec.name in {"scroll", "mouse_move", "wait_for"} and not clean:
        _fail(f"{path}.{spec.name}", "requiere al menos un parámetro")
    if spec.name == "select" and not ({"value", "label", "option_index"} & set(clean)):
        _fail(f"{path}.select", "indica 'value', 'label' u 'option_index'")

    return Action(spec.name, clean, path)


def _parse_step(raw: Any, index: int) -> Step:
    path = f"steps[{index}]"
    if isinstance(raw, str):  # atajo: un paso que solo narra
        return Step(index=index, name=f"paso-{index + 1}", narrate=raw)

    data = dict(_as_dict(raw, path))
    step = Step(index=index, name=str(data.pop("name", f"paso-{index + 1}")))

    narrate = data.pop("narrate", data.pop("say", None))
    if narrate is not None:
        text = _str(narrate, f"{path}.narrate").strip()
        step.narrate = text or None

    for key in ("voice", "rate", "pitch", "volume"):
        if key in data:
            setattr(step, key, _str(data.pop(key), f"{path}.{key}"))

    if "wait_for_narration" in data:
        step.wait_for_narration = _bool(data.pop("wait_for_narration"), f"{path}.wait_for_narration")
    if "pause_before" in data:
        step.pause_before = float(_num(data.pop("pause_before"), f"{path}.pause_before"))
    if "pause_after" in data:
        step.pause_after = float(_num(data.pop("pause_after"), f"{path}.pause_after"))

    actions = data.pop("actions", data.pop("do", []))
    if actions is None:
        actions = []
    if not isinstance(actions, list):
        _fail(f"{path}.actions", "se esperaba una lista de acciones")
    step.actions = [parse_action(a, f"{path}.actions[{i}]") for i, a in enumerate(actions)]

    if data:
        _fail(path, f"claves desconocidas: {', '.join(sorted(data))}")
    if not step.narrate and not step.actions:
        _fail(path, "el paso debe tener 'narrate', 'actions' o ambos")
    return step


_SCRIPT_KEYS = {
    "title", "output", "base_url", "voice", "rate", "pitch", "volume",
    "width", "height", "screen", "fps", "engine", "browser_ui", "cursor",
    "lead_in", "lead_out", "step_gap", "timeout", "move_steps", "crf", "preset",
    "locale", "timezone", "color_scheme", "user_agent", "storage_state",
    "http_credentials", "extra_http_headers", "ignore_https_errors",
    "subtitles", "chapters", "keep_temp", "steps",
}


def load_script(path: str | Path) -> Script:
    """Lee un guion YAML/JSON del disco y lo valida."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ScriptError(f"no existe el guion: {p}")
    text = p.read_text(encoding="utf-8")
    try:
        data = json.loads(text) if p.suffix.lower() == ".json" else yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ScriptError(f"{p.name}: no se pudo interpretar el archivo", detail=str(exc)) from exc
    return parse_script(data, source=p)


def parse_script(data: Any, *, source: Path) -> Script:
    raw = dict(_as_dict(data, "<raíz>"))

    unknown = set(raw) - _SCRIPT_KEYS
    if unknown:
        _fail("<raíz>", f"claves desconocidas: {', '.join(sorted(unknown))}. Válidas: {', '.join(sorted(_SCRIPT_KEYS))}")

    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        _fail("steps", "se requiere una lista con al menos un paso")
    steps = [_parse_step(s, i) for i, s in enumerate(steps_raw)]

    title = _str(raw.get("title", source.stem), "title")
    output = _str(raw.get("output", f"salida/{source.stem}.mp4"), "output")
    if not output.lower().endswith(".mp4"):
        _fail("output", "la salida debe terminar en .mp4")

    script = Script(title=title, output=output, steps=steps, source=source)

    # Tamaño de pantalla: `screen: 1600x900` o `width`/`height`.
    if "screen" in raw:
        value = _str(raw["screen"], "screen").lower().replace(" ", "")
        try:
            w, h = (int(v) for v in value.split("x")[:2])
        except ValueError:
            _fail("screen", "formato esperado 'ANCHOxALTO', p.ej. '1600x900'")
        script.width, script.height = w, h
    if "width" in raw:
        script.width = int(_num(raw["width"], "width", integer=True))
    if "height" in raw:
        script.height = int(_num(raw["height"], "height", integer=True))
    # libx264 exige dimensiones pares.
    script.width -= script.width % 2
    script.height -= script.height % 2
    if script.width < 640 or script.height < 480:
        _fail("screen", "el tamaño mínimo es 640x480")

    for key in ("base_url", "voice", "rate", "pitch", "volume", "engine", "cursor",
                "preset", "locale", "timezone", "color_scheme", "user_agent", "storage_state"):
        if key in raw:
            setattr(script, key, _str(raw[key], key))
    for key in ("lead_in", "lead_out", "step_gap", "timeout"):
        if key in raw:
            setattr(script, key, float(_num(raw[key], key)))
    for key in ("fps", "move_steps", "crf"):
        if key in raw:
            setattr(script, key, int(_num(raw[key], key, integer=True)))
    for key in ("browser_ui", "ignore_https_errors", "subtitles", "chapters", "keep_temp"):
        if key in raw:
            setattr(script, key, _bool(raw[key], key))
    for key in ("http_credentials", "extra_http_headers"):
        if key in raw:
            setattr(script, key, _as_dict(raw[key], key))

    if script.engine not in ("xvfb", "playwright"):
        _fail("engine", "debe ser 'xvfb' o 'playwright'")
    if script.cursor not in ("auto", "on", "off"):
        _fail("cursor", "debe ser 'auto', 'on' u 'off'")
    if script.color_scheme not in (None, "light", "dark"):
        _fail("color_scheme", "debe ser 'light' o 'dark'")
    if not 1 <= script.fps <= 60:
        _fail("fps", "debe estar entre 1 y 60")
    if not 0 <= script.crf <= 51:
        _fail("crf", "debe estar entre 0 y 51")
    if script.base_url and not script.base_url.startswith(("http://", "https://", "file://")):
        _fail("base_url", "debe empezar por http://, https:// o file://")

    return script
