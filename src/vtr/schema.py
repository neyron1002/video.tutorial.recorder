"""JSON Schema del guion, derivado del catálogo de acciones.

Se expone con `vtr schema` para que un agente pueda auto-descubrir el formato
exacto sin leer documentación en prosa.
"""

from __future__ import annotations

from typing import Any

from .actionspec import ACTIONS, ActionSpec
from .script import DEFAULT_VOICE


def _param_schema(spec: ActionSpec) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for p in spec.params:
        entry: dict[str, Any] = {"type": p.type, "description": p.doc}
        if p.enum:
            entry["enum"] = list(p.enum)
        if p.default is not None:
            entry["default"] = p.default
        if p.type == "array":
            entry["items"] = {"type": "string"}
        props[p.name] = entry
    obj: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
    if spec.required:
        obj["required"] = list(spec.required)
    return obj


def _action_variant(spec: ActionSpec) -> dict[str, Any]:
    """Variante `{nombre: params}` de una acción, con su forma abreviada."""
    forms: list[dict[str, Any]] = [_param_schema(spec)]
    if spec.shorthand:
        p = spec.param(spec.shorthand)
        forms.append({"type": p.type, "description": f"Abreviatura de `{spec.shorthand}`. {p.doc}"})
    if not spec.params:
        forms.append({"type": "null"})
    value = forms[0] if len(forms) == 1 else {"anyOf": forms}
    return {
        "type": "object",
        "title": spec.name,
        "description": spec.doc,
        "properties": {spec.name: value, "comment": {"type": "string"}},
        "required": [spec.name],
        "additionalProperties": False,
    }


def action_schema() -> dict[str, Any]:
    no_arg = [s.name for s in ACTIONS if not s.required and not s.params]
    return {
        "title": "Acción",
        "anyOf": [
            {"type": "string", "enum": sorted(no_arg), "description": "Acción sin parámetros."},
            *[_action_variant(s) for s in ACTIONS],
        ],
    }


def script_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://geus.local/schemas/vtr-tutorial-script.json",
        "title": "Guion de video tutorial (vtr)",
        "description": (
            "Guion declarativo que el recorder convierte en un MP4 narrado. "
            "Cada paso combina una narración (edge-tts) con acciones de navegador (Playwright); "
            "el paso dura lo que dure la más larga de las dos."
        ),
        "type": "object",
        "required": ["steps"],
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "description": "Título del tutorial (metadatos del MP4)."},
            "output": {
                "type": "string",
                "default": "salida/<nombre-del-guion>.mp4",
                "description": "Ruta del MP4 de salida, relativa al guion. Debe terminar en .mp4.",
            },
            "base_url": {
                "type": "string",
                "description": "URL base; las rutas relativas de `goto` se resuelven contra ella.",
            },
            "voice": {"type": "string", "default": DEFAULT_VOICE, "description": "Voz de edge-tts (ver `vtr voices`)."},
            "rate": {"type": "string", "default": "+0%", "description": "Velocidad de habla, p.ej. '-10%' o '+15%'."},
            "pitch": {"type": "string", "default": "+0Hz", "description": "Tono, p.ej. '-5Hz'."},
            "volume": {"type": "string", "default": "+0%", "description": "Volumen relativo, p.ej. '+10%'."},
            "screen": {"type": "string", "default": "1600x900", "description": "Tamaño del video, 'ANCHOxALTO'."},
            "width": {"type": "integer", "description": "Ancho del video (alternativa a `screen`)."},
            "height": {"type": "integer", "description": "Alto del video (alternativa a `screen`)."},
            "fps": {"type": "integer", "default": 30, "minimum": 1, "maximum": 60},
            "engine": {
                "type": "string",
                "enum": ["xvfb", "playwright"],
                "default": "xvfb",
                "description": (
                    "'xvfb': navegador visible en pantalla virtual capturada con ffmpeg (cursor real, "
                    "cronometraje exacto). 'playwright': grabación nativa headless (sin X, cursor simulado)."
                ),
            },
            "browser_ui": {
                "type": "boolean",
                "default": True,
                "description": "Mostrar la barra de direcciones y pestañas del navegador (motor xvfb).",
            },
            "cursor": {
                "type": "string",
                "enum": ["auto", "on", "off"],
                "default": "auto",
                "description": "Puntero simulado y ondas de clic sobre la página.",
            },
            "lead_in": {"type": "number", "default": 1.0, "description": "Segundos de margen antes del primer paso."},
            "lead_out": {"type": "number", "default": 1.5, "description": "Segundos de margen tras el último paso."},
            "step_gap": {"type": "number", "default": 0.5, "description": "Pausa por defecto entre pasos."},
            "timeout": {"type": "number", "default": 20.0, "description": "Timeout por defecto de las acciones, en segundos."},
            "move_steps": {"type": "integer", "default": 25, "description": "Suavidad del movimiento del puntero."},
            "crf": {"type": "integer", "default": 21, "description": "Calidad x264 (menor = mejor y más pesado)."},
            "preset": {"type": "string", "default": "veryfast", "description": "Preset de x264."},
            "locale": {"type": "string", "default": "es-MX"},
            "timezone": {"type": "string", "description": "Zona horaria del navegador, p.ej. 'America/Mexico_City'."},
            "color_scheme": {"type": "string", "enum": ["light", "dark"]},
            "user_agent": {"type": "string"},
            "storage_state": {
                "type": "string",
                "description": "Ruta a un storage_state.json de Playwright para empezar ya autenticado.",
            },
            "http_credentials": {
                "type": "object",
                "description": "Autenticación HTTP básica: {username, password}.",
                "additionalProperties": {"type": "string"},
            },
            "extra_http_headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "ignore_https_errors": {"type": "boolean", "default": False},
            "subtitles": {"type": "boolean", "default": True, "description": "Generar .srt y .vtt junto al video."},
            "chapters": {"type": "boolean", "default": True, "description": "Incrustar capítulos (uno por paso narrado)."},
            "keep_temp": {"type": "boolean", "default": False, "description": "Conservar archivos intermedios."},
            "steps": {
                "type": "array",
                "minItems": 1,
                "description": "Pasos del tutorial, en orden.",
                "items": {
                    "anyOf": [
                        {"type": "string", "description": "Atajo: paso que solo narra este texto."},
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string", "description": "Nombre del paso (título del capítulo)."},
                                "narrate": {"type": "string", "description": "Texto que narrará la voz."},
                                "voice": {"type": "string", "description": "Voz solo para este paso."},
                                "rate": {"type": "string"},
                                "pitch": {"type": "string"},
                                "volume": {"type": "string"},
                                "wait_for_narration": {
                                    "type": "boolean",
                                    "default": True,
                                    "description": "Esperar a que termine la narración antes del siguiente paso.",
                                },
                                "pause_before": {"type": "number", "default": 0},
                                "pause_after": {"type": "number", "description": "Sustituye a `step_gap` en este paso."},
                                "actions": {"type": "array", "items": action_schema()},
                            },
                        },
                    ]
                },
            },
        },
    }
