# Instrucciones para agentes de IA

Este repositorio **es una herramienta**: sirve para que tú, como agente, grabes
video tutoriales de cualquier aplicación web. No hay que escribir código para
crear un tutorial; hay que escribir un **guion YAML** y ejecutar `vtr record`.

## Contrato de uso

1. Escribe el guion en `ejemplos/` o en el directorio que indique el usuario,
   con extensión `.yaml`.
2. Valida antes de grabar: `vtr validate GUION --json`.
3. Graba: `vtr record GUION --json`.
4. Lee el JSON de stdout. Si `ok` es `false`, mira `error` y el paso con
   `status: "failed"`; también se guarda una captura del fallo en `capturas/`.

Con `--json`, **stdout contiene solo JSON** y todo el progreso va a stderr.
Códigos de salida: `0` correcto, `1` fallo de grabación, `2` guion inválido.

```bash
vtr schema                     # formato exacto del guion (JSON Schema)
vtr validate tutorial.yaml     # duración estimada, pasos, acciones
vtr record tutorial.yaml --json
vtr voices -l es               # voces disponibles
```

## Reglas para escribir buenos guiones

- **Un paso = una idea.** El paso dura lo que dure la parte más lenta entre la
  narración y las acciones; no calcules tiempos a mano ni añadas `wait` para
  cuadrar la voz.
- **Narra en frases completas y naturales**, sin markdown, sin viñetas y sin
  siglas raras: es texto que se va a leer en voz alta. 2 a 4 frases por paso.
- **Espera de forma explícita** después de navegar o de acciones que disparan
  carga: `wait_for: { selector: ... }` o `wait_for: { load_state: networkidle }`.
  No uses `wait: 5` como sustituto.
- **Selectores estables**: `role=`, `text=`, `data-test`, `id`. Evita cadenas CSS
  largas y frágiles.
- **Muestra dónde mirar**: `highlight` para marcar un elemento mientras lo
  explicas y `note` para un cartel de texto. Ambos se retiran solos.
- **Nunca pongas credenciales reales** en el guion. Usa datos de demo o
  `storage_state` con una sesión ya iniciada.
- Empieza con un paso de introducción y termina con un cierre breve: dan ritmo
  y generan buenos capítulos.

## Antes de grabar por primera vez

`vtr doctor` verifica ffmpeg, Xvfb, Chromium y el acceso a edge-tts (la síntesis
de voz necesita internet). Ejecuta siempre dentro del contenedor del proyecto.

## Qué produces

`vtr record` deja, junto al MP4:

| Archivo | Contenido |
| --- | --- |
| `*.mp4` | Video narrado, con capítulos por paso. |
| `*.srt` / `*.vtt` | Subtítulos sincronizados con la narración. |
| `*.report.json` | Resultado, duración total y `start`/`end` de cada paso. |
| `capturas/*.png` | Capturas pedidas con `screenshot` y la del fallo, si lo hubo. |

Referencia completa de acciones: `docs/GUION.md`.

## Sobre este entorno

- El único directorio compartido con el host es `/workspace` (este repositorio).
  Todo lo que escribas fuera de él se pierde al eliminar el contenedor.
- La autenticación de los CLIs de agentes es efímera y vive solo en este
  contenedor.
- El código de la herramienta está instalado en modo editable desde `/workspace`:
  si modificas `src/vtr/`, el cambio aplica de inmediato, sin reconstruir.
