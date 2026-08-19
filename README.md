# Video Tutorial Recorder

Contenedor de desarrollo + herramienta (`vtr`) para **grabar video tutoriales de
aplicaciones web de forma automática**: Playwright navega la aplicación, edge-tts
pone la voz y ffmpeg entrega un MP4 narrado, con subtítulos y capítulos.

Está pensado como **herramienta para agentes de IA**: el agente escribe un guion
declarativo en YAML y ejecuta un comando; recibe de vuelta un MP4 y un reporte
JSON con la línea de tiempo de cada paso.

```
guion.yaml ──▶ edge-tts (narración)  ─┐
           └─▶ Playwright (navegación)─┼─▶ Xvfb + ffmpeg ──▶ tutorial.mp4
                                       │                     tutorial.srt / .vtt
                                       └────────────────────▶ tutorial.report.json
```

---

## 1. Contenedor

Incluye Claude Code, Codex CLI, Gemini CLI, Python 3 + Playwright (Chromium),
ffmpeg, edge-tts y una pantalla virtual X.

```bash
docker compose build          # construir la imagen
docker compose up -d          # levantar el contenedor
docker compose exec dev bash  # entrar
```

En VS Code: **Reopen in Container** (`.devcontainer/devcontainer.json`).

Dos decisiones de diseño que conviene conocer:

- **Un único volumen entre host y contenedor: el workspace** (`.` → `/workspace`).
  No se monta ningún directorio de credenciales, cachés ni configuración.
- **Autenticación efímera.** Los agentes (`claude`, `codex`, `gemini`) hacen login
  dentro del contenedor y esa sesión vive únicamente ahí; al eliminar el
  contenedor se pierde. Como alternativa puedes pasar claves de API por `.env`
  (ver `.env.example`), que tampoco se escriben en disco.

Comprobar el entorno:

```bash
vtr doctor
```

## 2. Uso rápido

```bash
vtr init mi-tutorial.yaml --url https://mi-app.com   # crea un guion de ejemplo
vtr validate mi-tutorial.yaml                        # revisa el guion sin grabar
vtr record mi-tutorial.yaml                          # graba el MP4
```

`vtr record` deja junto al video: `*.srt`, `*.vtt`, capítulos incrustados en el
MP4 y `*.report.json` con la duración y los tiempos de cada paso.

Para comprobar que todo funciona sin depender de ninguna aplicación externa:

```bash
vtr record ejemplos/local.tutorial.yaml   # graba una página local de prueba
```

## 3. El guion

```yaml
title: "Cómo crear una factura"
output: "salida/factura.mp4"
base_url: "https://demo.mi-app.com"
voice: "es-MX-DaliaNeural"
screen: "1600x900"

steps:
  - name: "Inicio de sesión"
    narrate: >-
      Entramos con nuestro usuario y contraseña.
    actions:
      - goto: "/login"
      - type: { selector: "#email", text: "demo@empresa.com" }
      - type: { selector: "#password", text: "secreto" }
      - click: "button[type=submit]"
      - wait_for: { selector: ".dashboard" }

  - name: "Nueva factura"
    narrate: >-
      Desde el panel abrimos el módulo de facturación y creamos una factura nueva.
    actions:
      - highlight: { selector: "nav .facturacion", label: "Facturación" }
      - click: "text=Facturación"
      - click: "text=Nueva factura"
```

**Cada paso dura lo que dure la parte más lenta**: si la narración es de ocho
segundos y las acciones tardan tres, el video espera a la voz; si las acciones
tardan más, la narración se queda quieta hasta que terminan. No hay que
cronometrar nada a mano.

Referencia completa de acciones y opciones: `docs/GUION.md`, o el esquema
legible por máquina:

```bash
vtr schema                                        # JSON Schema a stdout
vtr schema -o schemas/tutorial-script.schema.json # para autocompletado en el editor
```

## 4. Comandos

| Comando | Para qué sirve |
| --- | --- |
| `vtr record GUION [-o salida.mp4] [--json]` | Graba el video. |
| `vtr validate GUION [--json]` | Valida el guion y estima la duración. |
| `vtr schema [-o archivo]` | JSON Schema del formato de guion. |
| `vtr voices [-l es]` | Lista las voces de edge-tts. |
| `vtr say "texto" -o voz.mp3` | Prueba una voz. |
| `vtr init [ruta] [--url URL]` | Crea un guion de ejemplo. |
| `vtr doctor` | Verifica ffmpeg, Xvfb, Chromium y edge-tts. |

Con `--json`, stdout es exclusivamente JSON y el progreso va a stderr — pensado
para que un agente lo consuma sin post-procesar texto.

## 5. Motores de captura

| Motor | Cómo funciona | Cuándo usarlo |
| --- | --- | --- |
| `xvfb` (por defecto) | Chromium visible en una pantalla virtual X, capturada por ffmpeg. Cursor real y cronometraje exacto. | Casi siempre. |
| `playwright` | Grabación nativa de Playwright en headless; el cursor se dibuja por software. | Entornos sin X o cuando se necesita menos CPU. |

## 6. Estructura

```
docker/            Dockerfile y entrypoint del contenedor
.devcontainer/     Integración con VS Code
src/vtr/           La herramienta
  actionspec.py      Catálogo de acciones (fuente del esquema y la validación)
  script.py          Carga y validación del guion
  tts.py             Narración con edge-tts
  browser.py         Chromium y ejecución de acciones
  capture.py         Xvfb + ffmpeg
  mux.py             Mezcla de audio/video y capítulos
  recorder.py        Orquestación y línea de tiempo
  cli.py             CLI
docs/              Guía del guion y guía para agentes
ejemplos/          Guiones de ejemplo
```

## 7. Licencia

MIT.
