#!/usr/bin/env bash
# Arranque del contenedor:
#   1. levanta una pantalla virtual X de uso general (:99),
#   2. reinstala `vtr` en modo editable si el workspace contiene el proyecto,
#   3. cede el control al comando pedido.
set -euo pipefail

log() { printf '\033[36m·\033[0m %s\n' "$*" >&2; }

# --- 1. Pantalla virtual compartida ---------------------------------------- #
if [ "${VTR_START_XVFB:-1}" = "1" ]; then
  display="${DISPLAY:-:99}"
  if ! xdpyinfo -display "$display" >/dev/null 2>&1; then
    Xvfb "$display" -screen 0 "${SCREEN_SIZE:-1920x1080x24}" \
      -nolisten tcp -noreset -ac +extension GLX +extension RANDR +render \
      >/tmp/xvfb.log 2>&1 &
    for _ in $(seq 1 60); do
      xdpyinfo -display "$display" >/dev/null 2>&1 && break
      sleep 0.1
    done
    if xdpyinfo -display "$display" >/dev/null 2>&1; then
      log "pantalla virtual $display lista (${SCREEN_SIZE:-1920x1080x24})"
    else
      log "aviso: no se pudo iniciar Xvfb en $display (ver /tmp/xvfb.log)"
    fi
  fi
fi

# --- 2. Instalación editable del proyecto montado --------------------------- #
# El único volumen compartido con el host es /workspace. Si contiene el código
# de `vtr`, se instala en modo editable para que los cambios surtan efecto sin
# reconstruir la imagen.
if [ "${VTR_DEV_INSTALL:-1}" = "1" ] \
   && [ -f /workspace/pyproject.toml ] \
   && grep -q 'name = "video-tutorial-recorder"' /workspace/pyproject.toml 2>/dev/null; then
  if pip install -e /workspace --no-deps --quiet 2>/tmp/pip-editable.log; then
    log "vtr instalado en modo editable desde /workspace"
  else
    log "aviso: no se pudo instalar /workspace en modo editable (ver /tmp/pip-editable.log)"
  fi
fi

# --- 3. Aviso sobre autenticación efímera ----------------------------------- #
if [ ! -d "${HOME}/.claude" ] && [ -t 1 ]; then
  log "autenticación efímera: los agentes (claude, codex, gemini) pedirán login en este contenedor"
fi

exec "$@"
