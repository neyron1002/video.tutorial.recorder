"""Catálogo declarativo de acciones del guion.

Una sola tabla describe cada acción: parámetros requeridos, opcionales, la forma
abreviada (`{click: "#boton"}`) y la documentación. De aquí se derivan tanto la
validación (`vtr.script`) como el JSON Schema que consumen los agentes
(`vtr.schema`).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:
    name: str
    type: str  # string | number | integer | boolean | array | object
    doc: str
    required: bool = False
    default: object | None = None
    enum: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ActionSpec:
    name: str
    doc: str
    params: tuple[Param, ...] = ()
    shorthand: str | None = None  # parámetro que acepta la forma abreviada
    aliases: tuple[str, ...] = ()

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params if p.required)

    def param(self, name: str) -> Param | None:
        for p in self.params:
            if p.name == name:
                return p
        return None


_SELECTOR = Param(
    "selector",
    "string",
    "Selector de Playwright: CSS, `text=...`, `role=button[name=\"Guardar\"]`, `#id`, etc.",
    required=True,
)
_INDEX = Param("index", "integer", "Índice (base 0) cuando el selector coincide con varios elementos.")
_TIMEOUT = Param("timeout", "number", "Timeout en segundos para esta acción (por defecto el del guion).")
_MOVE = Param(
    "move",
    "boolean",
    "Desplazar el puntero suavemente hasta el elemento antes de actuar.",
    default=True,
)

ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec(
        "goto",
        "Navega a una URL. Si es relativa se resuelve contra `base_url`.",
        params=(
            Param("url", "string", "URL absoluta o ruta relativa (`/login`).", required=True),
            Param(
                "wait_until",
                "string",
                "Evento de carga a esperar.",
                default="load",
                enum=("load", "domcontentloaded", "networkidle", "commit"),
            ),
            _TIMEOUT,
        ),
        shorthand="url",
    ),
    ActionSpec(
        "click",
        "Hace clic en un elemento (con desplazamiento suave del puntero y onda de clic).",
        params=(
            _SELECTOR,
            _INDEX,
            Param("button", "string", "Botón del ratón.", default="left", enum=("left", "right", "middle")),
            Param("clicks", "integer", "Número de clics.", default=1),
            Param("force", "boolean", "Omitir comprobaciones de accionabilidad.", default=False),
            _MOVE,
            _TIMEOUT,
        ),
        shorthand="selector",
    ),
    ActionSpec(
        "dblclick",
        "Doble clic sobre un elemento.",
        params=(_SELECTOR, _INDEX, _MOVE, _TIMEOUT),
        shorthand="selector",
    ),
    ActionSpec(
        "hover",
        "Sitúa el puntero sobre un elemento (útil para menús desplegables).",
        params=(_SELECTOR, _INDEX, _MOVE, _TIMEOUT),
        shorthand="selector",
    ),
    ActionSpec(
        "fill",
        "Rellena un campo de golpe (rápido, sin animación de tecleo).",
        params=(
            _SELECTOR,
            Param("text", "string", "Texto a escribir.", required=True),
            _INDEX,
            _MOVE,
            _TIMEOUT,
        ),
    ),
    ActionSpec(
        "type",
        "Escribe carácter a carácter (se ve natural en el video).",
        params=(
            _SELECTOR,
            Param("text", "string", "Texto a teclear.", required=True),
            Param("delay", "number", "Milisegundos entre teclas.", default=60),
            Param("clear", "boolean", "Vaciar el campo antes de teclear.", default=True),
            _INDEX,
            _MOVE,
            _TIMEOUT,
        ),
    ),
    ActionSpec(
        "press",
        "Pulsa una tecla o combinación (`Enter`, `Control+S`, `Escape`).",
        params=(
            Param("key", "string", "Tecla o combinación.", required=True),
            Param("selector", "string", "Elemento que recibe la pulsación (opcional; por defecto la página)."),
            Param("repeat", "integer", "Repeticiones.", default=1),
            _INDEX,
            _TIMEOUT,
        ),
        shorthand="key",
        aliases=("key",),
    ),
    ActionSpec(
        "select",
        "Selecciona una opción de un `<select>`.",
        params=(
            _SELECTOR,
            Param("value", "string", "Valor de la opción."),
            Param("label", "string", "Etiqueta visible de la opción."),
            Param("option_index", "integer", "Índice de la opción."),
            _INDEX,
            _MOVE,
            _TIMEOUT,
        ),
    ),
    ActionSpec("check", "Marca una casilla o radio.", params=(_SELECTOR, _INDEX, _MOVE, _TIMEOUT), shorthand="selector"),
    ActionSpec("uncheck", "Desmarca una casilla.", params=(_SELECTOR, _INDEX, _MOVE, _TIMEOUT), shorthand="selector"),
    ActionSpec(
        "upload",
        "Sube archivos a un `<input type=file>`.",
        params=(
            _SELECTOR,
            Param("files", "array", "Rutas de archivo (relativas al guion).", required=True),
            _INDEX,
            _TIMEOUT,
        ),
    ),
    ActionSpec(
        "focus", "Da el foco a un elemento.", params=(_SELECTOR, _INDEX, _TIMEOUT), shorthand="selector"
    ),
    ActionSpec(
        "clear", "Vacía un campo de texto.", params=(_SELECTOR, _INDEX, _TIMEOUT), shorthand="selector"
    ),
    ActionSpec(
        "scroll",
        "Desplaza la página hasta un elemento o a una posición concreta.",
        params=(
            Param("selector", "string", "Elemento al que desplazarse."),
            Param("x", "number", "Posición horizontal absoluta en píxeles."),
            Param("y", "number", "Posición vertical absoluta en píxeles."),
            Param("by", "number", "Desplazamiento relativo en píxeles (positivo = hacia abajo)."),
            Param("smooth", "boolean", "Desplazamiento animado.", default=True),
            _INDEX,
        ),
        shorthand="selector",
    ),
    ActionSpec(
        "wait",
        "Pausa fija en segundos.",
        params=(Param("seconds", "number", "Segundos a esperar.", required=True),),
        shorthand="seconds",
        aliases=("sleep",),
    ),
    ActionSpec(
        "wait_for",
        "Espera a que se cumpla una condición antes de continuar.",
        params=(
            Param("selector", "string", "Espera a que el elemento alcance `state`."),
            Param(
                "state",
                "string",
                "Estado esperado del elemento.",
                default="visible",
                enum=("attached", "detached", "visible", "hidden"),
            ),
            Param("text", "string", "Espera a que este texto aparezca en la página."),
            Param("url", "string", "Espera a que la URL coincida (admite patrón glob)."),
            Param(
                "load_state",
                "string",
                "Espera un estado de carga de la página.",
                enum=("load", "domcontentloaded", "networkidle"),
            ),
            _INDEX,
            _TIMEOUT,
        ),
        shorthand="selector",
    ),
    ActionSpec(
        "highlight",
        "Resalta un elemento con un marco animado (no bloquea; se retira solo).",
        params=(
            _SELECTOR,
            Param("duration", "number", "Segundos que permanece el resaltado.", default=3.0),
            Param("label", "string", "Etiqueta opcional pegada al marco."),
            Param("color", "string", "Color CSS del marco.", default="#ff3d71"),
            Param("padding", "number", "Margen del marco en píxeles.", default=6),
            Param("scroll", "boolean", "Desplazar el elemento a la vista primero.", default=True),
            _INDEX,
        ),
        shorthand="selector",
    ),
    ActionSpec(
        "note",
        "Muestra un cartel de texto sobre el video (llamada de atención).",
        params=(
            Param("text", "string", "Texto del cartel.", required=True),
            Param("selector", "string", "Anclar el cartel junto a este elemento."),
            Param("duration", "number", "Segundos visible.", default=4.0),
            Param(
                "position",
                "string",
                "Posición cuando no hay `selector`.",
                default="bottom",
                enum=("top", "bottom", "center", "top-left", "top-right", "bottom-left", "bottom-right"),
            ),
            _INDEX,
        ),
        shorthand="text",
    ),
    ActionSpec(
        "clear_overlays",
        "Retira de inmediato resaltados y carteles visibles.",
    ),
    ActionSpec(
        "mouse_move",
        "Mueve el puntero a un elemento o a coordenadas concretas.",
        params=(
            Param("selector", "string", "Elemento destino."),
            Param("x", "number", "Coordenada X."),
            Param("y", "number", "Coordenada Y."),
            Param("steps", "integer", "Pasos de interpolación (más = más lento y suave).", default=25),
            _INDEX,
        ),
        shorthand="selector",
    ),
    ActionSpec(
        "drag",
        "Arrastra un elemento sobre otro.",
        params=(
            Param("source", "string", "Selector del elemento a arrastrar.", required=True),
            Param("target", "string", "Selector del destino.", required=True),
            _TIMEOUT,
        ),
    ),
    ActionSpec(
        "screenshot",
        "Guarda una captura PNG (además del video).",
        params=(
            Param("path", "string", "Ruta de salida, relativa al directorio de salida."),
            Param("selector", "string", "Capturar solo este elemento."),
            Param("full_page", "boolean", "Capturar la página completa.", default=False),
            _INDEX,
        ),
        shorthand="path",
    ),
    ActionSpec(
        "eval",
        "Ejecuta JavaScript en la página (escotilla de escape).",
        params=(
            Param("expression", "string", "Expresión o función JS.", required=True),
            Param("selector", "string", "Si se indica, el elemento se pasa como argumento."),
            _INDEX,
        ),
        shorthand="expression",
    ),
    ActionSpec("back", "Vuelve a la página anterior del historial."),
    ActionSpec("forward", "Avanza en el historial."),
    ActionSpec("reload", "Recarga la página actual."),
    ActionSpec(
        "zoom",
        "Cambia el zoom de la página (útil para acercarse a un detalle).",
        params=(Param("factor", "number", "Factor de zoom, 1 = 100%.", required=True, default=1.0),),
        shorthand="factor",
    ),
)

ACTION_BY_NAME: dict[str, ActionSpec] = {}
for _spec in ACTIONS:
    ACTION_BY_NAME[_spec.name] = _spec
    for _alias in _spec.aliases:
        ACTION_BY_NAME[_alias] = _spec

ACTION_NAMES: tuple[str, ...] = tuple(sorted(ACTION_BY_NAME))
