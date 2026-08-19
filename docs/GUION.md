# Referencia del guion

Un guion es un archivo YAML (o JSON) con opciones generales y una lista de
`steps`. Cada paso combina una **narración** con una lista de **acciones**; el
paso termina cuando ambas han acabado.

El esquema legible por máquina se obtiene con `vtr schema`.

---

## Opciones generales

| Clave | Por defecto | Descripción |
| --- | --- | --- |
| `title` | nombre del archivo | Título del tutorial (metadatos del MP4). |
| `output` | `salida/<guion>.mp4` | Ruta del MP4, relativa al guion. |
| `base_url` | — | URL base para las rutas relativas de `goto`. |
| `voice` | `es-MX-DaliaNeural` | Voz de edge-tts (`vtr voices -l es`). |
| `rate` / `pitch` / `volume` | `+0%` / `+0Hz` / `+0%` | Ajustes de la voz. |
| `screen` | `1600x900` | Resolución del video (`width`/`height` también valen). |
| `fps` | `30` | Fotogramas por segundo. |
| `engine` | `xvfb` | `xvfb` (pantalla virtual + ffmpeg) o `playwright` (headless). |
| `browser_ui` | `true` | Mostrar barra de direcciones y pestañas. |
| `cursor` | `auto` | Puntero dibujado y ondas de clic: `auto`, `on`, `off`. |
| `lead_in` / `lead_out` | `1.0` / `1.5` | Margen en segundos al principio y al final. |
| `step_gap` | `0.5` | Pausa por defecto entre pasos. |
| `timeout` | `20` | Timeout por defecto de las acciones, en segundos. |
| `move_steps` | `25` | Suavidad del desplazamiento del puntero. |
| `crf` / `preset` | `21` / `veryfast` | Calidad y velocidad de codificación x264. |
| `locale` / `timezone` / `color_scheme` / `user_agent` | `es-MX` / — | Contexto del navegador. |
| `storage_state` | — | `storage_state.json` de Playwright para empezar autenticado. |
| `http_credentials` | — | `{ username, password }` para autenticación básica. |
| `extra_http_headers` | — | Cabeceras adicionales. |
| `ignore_https_errors` | `false` | Aceptar certificados inválidos. |
| `subtitles` / `chapters` | `true` | Generar `.srt`/`.vtt` e incrustar capítulos. |
| `keep_temp` | `false` | Conservar los archivos intermedios. |

## Pasos

```yaml
steps:
  - name: "Inicio de sesión"      # título del capítulo
    narrate: "Texto que se leerá en voz alta."
    voice: "es-ES-AlvaroNeural"   # voz solo para este paso (opcional)
    rate: "-5%"                   # opcional
    wait_for_narration: true      # esperar a que la voz termine (por defecto sí)
    pause_before: 0               # segundos antes del paso
    pause_after: 1.5              # sustituye a step_gap en este paso
    actions: [...]
```

Un paso puede escribirse como una simple cadena cuando solo narra:

```yaml
steps:
  - "Bienvenidos a este tutorial."
```

## Acciones

Tres formas equivalentes de escribir una acción:

```yaml
- click: "#guardar"                        # abreviada
- click: { selector: "#guardar", index: 1 } # con parámetros
- { action: "click", selector: "#guardar" } # explícita
```

Los selectores son de Playwright: `#id`, `.clase`, `text=Guardar`,
`role=button[name="Guardar"]`, `[data-test=save]`, `nav >> text=Docs`. Cuando un
selector coincide con varios elementos se usa el primero, salvo que indiques
`index`.

### Navegación

| Acción | Parámetros | Descripción |
| --- | --- | --- |
| `goto` | `url`*, `wait_until`, `timeout` | Navega; las rutas relativas usan `base_url`. |
| `back` / `forward` / `reload` | — | Historial y recarga. |

### Interacción

| Acción | Parámetros | Descripción |
| --- | --- | --- |
| `click` | `selector`*, `index`, `button`, `clicks`, `force`, `move`, `timeout` | Clic con desplazamiento suave del puntero. |
| `dblclick` | `selector`*, … | Doble clic. |
| `hover` | `selector`*, … | Puntero sobre el elemento (menús). |
| `fill` | `selector`*, `text`* | Rellena el campo de golpe. |
| `type` | `selector`*, `text`*, `delay`, `clear` | Teclea carácter a carácter (se ve natural). |
| `press` | `key`*, `selector`, `repeat` | `Enter`, `Escape`, `Control+S`… |
| `select` | `selector`*, `value` \| `label` \| `option_index` | Opción de un `<select>`. |
| `check` / `uncheck` | `selector`* | Casillas y radios. |
| `upload` | `selector`*, `files`* | Sube archivos (rutas relativas al guion). |
| `focus` / `clear` | `selector`* | Foco / vaciar campo. |
| `drag` | `source`*, `target`* | Arrastrar y soltar. |
| `mouse_move` | `selector` \| `x`+`y`, `steps` | Mueve el puntero sin hacer clic. |

### Ritmo y espera

| Acción | Parámetros | Descripción |
| --- | --- | --- |
| `wait` | `seconds`* | Pausa fija. Úsala con moderación. |
| `wait_for` | `selector`+`state`, `text`, `url`, `load_state`, `timeout` | Espera una condición real. |
| `scroll` | `selector` \| `y` \| `by`, `smooth` | Desplaza la página. |

### Elementos visuales

| Acción | Parámetros | Descripción |
| --- | --- | --- |
| `highlight` | `selector`*, `duration`, `label`, `color`, `padding` | Marco animado alrededor de un elemento. |
| `note` | `text`*, `selector`, `duration`, `position` | Cartel de texto sobre el video. |
| `clear_overlays` | — | Retira resaltados y carteles al instante. |
| `zoom` | `factor`* | Zoom de la página (`1` = 100%). |

`highlight` y `note` no bloquean: la narración sigue mientras el elemento
permanece visible el tiempo indicado.

### Extras

| Acción | Parámetros | Descripción |
| --- | --- | --- |
| `screenshot` | `path`, `selector`, `full_page` | Guarda un PNG además del video. |
| `eval` | `expression`*, `selector` | Ejecuta JavaScript en la página. |

`*` = obligatorio.

---

## Salidas

`vtr record` genera, junto al MP4:

- `*.srt` y `*.vtt` — subtítulos alineados con la narración.
- Capítulos incrustados en el MP4, uno por paso.
- `*.report.json`:

```json
{
  "ok": true,
  "video": "/workspace/salida/tutorial.mp4",
  "duration": 96.4,
  "steps": [
    { "index": 0, "name": "Introducción", "start": 1.0, "end": 9.8,
      "narration": "En este tutorial…", "narration_duration": 8.3,
      "actions": 2, "status": "ok" }
  ],
  "warnings": [],
  "screenshots": []
}
```

Si un paso falla, la grabación se detiene ahí pero **el video se genera igual**
con lo grabado hasta ese punto, `ok` es `false`, el paso queda marcado como
`failed` y se guarda `capturas/fallo-paso-NN.png`.

## Consejos de calidad

- Resolución `1600x900` para tutoriales de producto; `1920x1080` si el video se
  verá a pantalla completa.
- Narración de 2 a 4 frases por paso: por debajo suena entrecortado y por encima
  el espectador pierde el hilo de la pantalla.
- `rate: "-5%"` da un ritmo más didáctico en explicaciones densas.
- Marca con `highlight` el elemento del que hablas justo antes de interactuar con
  él; el espectador lo localiza mientras terminas la frase.
- Si la aplicación tarda en cargar, `wait_for` con `load_state: networkidle`
  evita grabar pantallas a medio pintar.
