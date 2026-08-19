"""Captura de video: pantalla virtual X (Xvfb) grabada con ffmpeg.

El motor `xvfb` da dos ventajas frente a la grabación nativa de Playwright:
cursor real dibujado en el video y una línea de tiempo de reloj de pared exacta,
imprescindible para colocar la narración en el momento correcto.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

from .errors import CaptureError
from .util import free_display, log, media_duration, require_binary, run


class VirtualDisplay:
    """Servidor Xvfb dedicado a una grabación."""

    def __init__(self, width: int, height: int, depth: int = 24) -> None:
        self.width = width
        self.height = height
        self.depth = depth
        self.display = free_display()
        self._proc: subprocess.Popen | None = None

    def start(self) -> str:
        require_binary("Xvfb", hint="Instala el paquete 'xvfb' (ya viene en el contenedor del proyecto).")
        cmd = [
            "Xvfb", self.display,
            "-screen", "0", f"{self.width}x{self.height}x{self.depth}",
            "-nolisten", "tcp", "-noreset", "-ac",
            "+extension", "GLX", "+extension", "RANDR", "+render",
        ]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                err = (self._proc.stderr.read().decode(errors="replace") if self._proc.stderr else "")
                raise CaptureError(f"Xvfb terminó inesperadamente en {self.display}", detail=err[-1500:])
            probe = subprocess.run(
                ["xdpyinfo", "-display", self.display], capture_output=True, text=True
            )
            if probe.returncode == 0:
                log(f"pantalla virtual {self.display} lista ({self.width}x{self.height})")
                return self.display
            time.sleep(0.15)
        self.stop()
        raise CaptureError(f"la pantalla virtual {self.display} no arrancó a tiempo")

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def __enter__(self) -> "VirtualDisplay":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


class ScreenRecorder:
    """Graba un display X a MP4 con ffmpeg (x11grab)."""

    def __init__(
        self,
        display: str,
        output: Path,
        *,
        width: int,
        height: int,
        offset_x: int = 0,
        offset_y: int = 0,
        fps: int = 30,
        crf: int = 21,
        preset: str = "veryfast",
        draw_mouse: bool = True,
    ) -> None:
        self.display = display
        self.output = output
        self.width = width
        self.height = height
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.fps = fps
        self.crf = crf
        self.preset = preset
        self.draw_mouse = draw_mouse
        self._proc: subprocess.Popen | None = None
        self._first_frame = threading.Event()
        self._stderr: list[str] = []
        self.t0: float = 0.0
        self.bias: float = 0.0

    def _pump_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        for raw in self._proc.stderr:
            line = raw.decode(errors="replace").rstrip()
            if not line:
                continue
            self._stderr.append(line)
            if len(self._stderr) > 400:
                del self._stderr[:200]

    def _pump_progress(self) -> None:
        """Lee `-progress pipe:1` para anclar t0 al primer fotograma real.

        ffmpeg emite bloques `clave=valor` terminados en `progress=continue`.
        `out_time_us` indica cuánto video lleva escrito, así que
        `t0 = ahora - out_time_us` sitúa el origen de la línea de tiempo con
        precisión de milisegundos.
        """
        assert self._proc and self._proc.stdout
        frame = 0
        for raw in self._proc.stdout:
            now = time.monotonic()
            line = raw.decode(errors="replace").strip()
            key, _, value = line.partition("=")
            if key == "frame":
                try:
                    frame = int(value)
                except ValueError:
                    frame = 0
            elif key == "out_time_us" and frame >= 1 and not self._first_frame.is_set():
                try:
                    self.t0 = now - int(value) / 1_000_000
                except ValueError:
                    self.t0 = now
                self._first_frame.set()

    def start(self) -> float:
        """Arranca la grabación y devuelve el instante t0 (time.monotonic)."""
        require_binary("ffmpeg")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostats", "-y",
            "-f", "x11grab",
            "-draw_mouse", "1" if self.draw_mouse else "0",
            "-framerate", str(self.fps),
            "-video_size", f"{self.width}x{self.height}",
            "-i", f"{self.display}.0+{self.offset_x},{self.offset_y}",
            "-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf),
            "-pix_fmt", "yuv420p", "-g", str(self.fps * 2),
            "-movflags", "+faststart",
            "-stats_period", "0.1", "-progress", "pipe:1",
            str(self.output),
        ]
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        threading.Thread(target=self._pump_stderr, daemon=True).start()
        threading.Thread(target=self._pump_progress, daemon=True).start()

        # El primer fotograma marca el origen de la línea de tiempo del video.
        if not self._first_frame.wait(timeout=15):
            if self._proc.poll() is not None:
                raise CaptureError(
                    "ffmpeg no pudo capturar la pantalla",
                    detail="\n".join(self._stderr[-25:]),
                )
            log("ffmpeg no reportó progreso; la sincronía puede desviarse", level="warn")
            self.t0 = time.monotonic()
        log(f"grabando {self.width}x{self.height}@{self.fps} → {self.output.name}", level="ok")
        return self.t0

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.t0 if self.t0 else 0.0

    def stop(self) -> float:
        """Cierra ffmpeg limpiamente y devuelve la duración grabada."""
        if not self._proc:
            return 0.0
        duration = self.elapsed
        if self._proc.poll() is None:
            try:
                assert self._proc.stdin
                self._proc.stdin.write(b"q")
                self._proc.stdin.flush()
                self._proc.stdin.close()
            except (BrokenPipeError, OSError, AssertionError):
                self._proc.send_signal(signal.SIGINT)
            try:
                self._proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=10)
        if self._proc.returncode not in (0, 255) or not self.output.exists():
            raise CaptureError(
                f"ffmpeg terminó con código {self._proc.returncode}",
                detail="\n".join(self._stderr[-25:]),
            )
        self._proc = None

        # ffmpeg reporta el progreso con algo de retraso respecto a lo que ya ha
        # capturado, así que t0 queda un poco tarde. Comparando la duración real
        # del archivo con el tiempo medido obtenemos ese desfase y lo aplicamos
        # después a la narración, para que voz e imagen encajen.
        try:
            self.bias = max(0.0, min(5.0, media_duration(self.output) - duration))
        except Exception:  # noqa: BLE001
            self.bias = 0.0
        log(f"captura detenida ({duration:.1f}s, desfase {self.bias * 1000:.0f} ms)", level="ok")
        return duration


def x11_env(display: str) -> dict[str, str]:
    """Entorno para procesos hijos que deben pintar en `display`."""
    env = dict(os.environ)
    env["DISPLAY"] = display
    return env


def check_display(display: str) -> bool:
    try:
        return run(["xdpyinfo", "-display", display], timeout=10, check=False).returncode == 0
    except Exception:  # noqa: BLE001
        return False
