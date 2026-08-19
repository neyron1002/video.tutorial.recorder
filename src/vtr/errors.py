"""Errores del recorder, con códigos estables para consumo por agentes."""

from __future__ import annotations


class VtrError(Exception):
    """Error base. `code` es estable y apto para automatización."""

    code = "vtr_error"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        out = {"error": self.code, "message": self.message}
        if self.detail:
            out["detail"] = self.detail
        return out


class ScriptError(VtrError):
    """El guion es inválido (estructura, tipos o acción desconocida)."""

    code = "invalid_script"


class DependencyError(VtrError):
    """Falta una dependencia del sistema (ffmpeg, Xvfb, navegador...)."""

    code = "missing_dependency"


class TtsError(VtrError):
    """Falló la síntesis de voz con edge-tts."""

    code = "tts_failed"


class CaptureError(VtrError):
    """Falló la captura de pantalla/video."""

    code = "capture_failed"


class BrowserError(VtrError):
    """Falló una acción del navegador durante la grabación."""

    code = "browser_action_failed"


class MuxError(VtrError):
    """Falló el ensamblado final de audio y video."""

    code = "mux_failed"
