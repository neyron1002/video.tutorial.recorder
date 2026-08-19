"""Control del navegador: arranque de Chromium y ejecución de las acciones."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    async_playwright,
)

from .errors import BrowserError
from .script import Action, Script
from .util import log

OVERLAY_JS = (Path(__file__).parent / "assets" / "overlay.js").read_text(encoding="utf-8")

# Margen vertical reservado en la pantalla virtual para el cromo del navegador
# cuando el guion pide un video sin barra de direcciones.
CHROME_MARGIN = 140


def chromium_args(script: Script, *, screen_w: int, screen_h: int, headless: bool) -> list[str]:
    # Todo lo que pueda aparecer encima de la página (globos, diálogos,
    # notificaciones) arruina una grabación, así que se desactiva de antemano.
    args = [
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-infobars",
        # Sin esto Chrome graba encima de la página la barra amarilla de
        # "estás usando un flag no soportado" cuando se corre sin sandbox.
        "--test-type",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "--disable-dev-shm-usage",
        "--disable-translate",
        "--disable-notifications",
        "--disable-component-update",
        "--disable-search-engine-choice-screen",
        "--noerrdialogs",
        "--password-store=basic",
        "--use-mock-keychain",
        "--disable-features="
        "Translate,TranslateUI,AutofillServerCommunication,MediaRouter,"
        "OptimizationHints,PrivacySandboxSettings4,DialMediaRouteProvider,"
        "GlobalMediaControls,ChromeWhatsNewUI",
        "--force-device-scale-factor=1",
        "--start-maximized",
        # Que la interfaz hable el mismo idioma que la página evita el globo de
        # "¿Traducir esta página?" en mitad de la grabación.
        f"--lang={script.locale}",
    ]
    if not headless:
        args += [f"--window-size={screen_w},{screen_h}", "--window-position=0,0"]
    # En contenedores el sandbox de Chromium suele requerir privilegios extra.
    if os.environ.get("VTR_NO_SANDBOX", "1") == "1":
        args += ["--no-sandbox", "--disable-setuid-sandbox"]
    return args


@dataclass
class BrowserSession:
    playwright: Any
    context: BrowserContext
    page: Page
    chrome_height: int = 0

    async def close(self) -> None:
        for closer in (self.context.close, self.playwright.stop):
            try:
                await closer()
            except Exception:  # noqa: BLE001 - el cierre nunca debe tumbar la grabación
                pass


# Preferencias del perfil: silencian todo lo que Chromium podría superponer a la
# página (traducción, gestor de contraseñas, restauración de sesión).
PROFILE_PREFS = {
    "translate": {"enabled": False},
    "translate_blocked_languages": ["en", "es", "pt", "fr", "de", "it"],
    "credentials_enable_service": False,
    "credentials_enable_autosignin": False,
    "profile": {
        "exit_type": "Normal",
        "exited_cleanly": True,
        "password_manager_enabled": False,
        "password_manager_leak_detection": False,
        "default_content_setting_values": {"notifications": 2, "geolocation": 2},
    },
    "browser": {"has_seen_welcome_page": True, "window_placement": {"maximized": True}},
    "bookmark_bar": {"show_on_all_tabs": False},
    "signin": {"allowed": False},
    "search_engine_choice_screen": {"completed": True},
}


def prepare_profile(profile_dir: Path) -> Path:
    """Crea un perfil de Chromium limpio y silencioso para la grabación."""
    default = profile_dir / "Default"
    default.mkdir(parents=True, exist_ok=True)
    (default / "Preferences").write_text(json.dumps(PROFILE_PREFS), encoding="utf-8")
    (profile_dir / "First Run").write_text("", encoding="utf-8")
    return profile_dir


async def apply_storage_state(context: BrowserContext, path: Path) -> None:
    """Aplica un storage_state.json de Playwright a un contexto persistente."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("cookies"):
        await context.add_cookies(data["cookies"])
    origins = {
        entry["origin"]: {item["name"]: item["value"] for item in entry.get("localStorage", [])}
        for entry in data.get("origins", [])
        if entry.get("localStorage")
    }
    if origins:
        await context.add_init_script(
            "(() => { const data = " + json.dumps(origins) + ";"
            " const store = data[location.origin]; if (!store) return;"
            " for (const [k, v] of Object.entries(store)) { try { localStorage.setItem(k, v); } catch (e) {} }"
            "})();"
        )


async def launch(
    script: Script,
    *,
    display: str | None,
    screen_w: int,
    screen_h: int,
    profile_dir: Path,
    video_dir: Path | None = None,
) -> BrowserSession:
    headless = script.engine == "playwright"
    if display:
        os.environ["DISPLAY"] = display

    ctx_args: dict[str, Any] = {
        "locale": script.locale,
        "ignore_https_errors": script.ignore_https_errors,
        "reduced_motion": "no-preference",
    }
    if headless:
        ctx_args["viewport"] = {"width": script.width, "height": script.height}
        if video_dir is not None:
            ctx_args["record_video_dir"] = str(video_dir)
            ctx_args["record_video_size"] = {"width": script.width, "height": script.height}
    else:
        ctx_args["no_viewport"] = True
    if script.timezone:
        ctx_args["timezone_id"] = script.timezone
    if script.color_scheme:
        ctx_args["color_scheme"] = script.color_scheme
    if script.user_agent:
        ctx_args["user_agent"] = script.user_agent
    if script.http_credentials:
        ctx_args["http_credentials"] = script.http_credentials
    if script.extra_http_headers:
        ctx_args["extra_http_headers"] = script.extra_http_headers
    ctx_args = {k: v for k, v in ctx_args.items() if v is not None}

    state_path: Path | None = None
    if script.storage_state:
        state_path = script.resolve(script.storage_state)
        if not state_path.is_file():
            raise BrowserError(f"no existe storage_state: {state_path}")

    prepare_profile(profile_dir)
    pw = await async_playwright().start()
    try:
        # Perfil persistente (efímero, uno por grabación): es la única forma
        # fiable de desactivar el globo de traducción y demás avisos de Chromium.
        context = await pw.chromium.launch_persistent_context(
            str(profile_dir),
            headless=headless,
            args=chromium_args(script, screen_w=screen_w, screen_h=screen_h, headless=headless),
            chromium_sandbox=False,
            **ctx_args,
        )
    except PlaywrightError as exc:
        await pw.stop()
        raise BrowserError(
            "no se pudo iniciar Chromium",
            detail=f"{exc}\nEjecuta `playwright install chromium` dentro del contenedor.",
        ) from exc

    if state_path is not None:
        await apply_storage_state(context, state_path)

    context.set_default_timeout(script.timeout * 1000)
    context.set_default_navigation_timeout(max(script.timeout, 30.0) * 1000)

    show_cursor = script.cursor == "on" or (script.cursor == "auto" and headless)
    await context.add_init_script(f"window.__vtrConfig = {json.dumps({'cursor': show_cursor})};")
    await context.add_init_script(OVERLAY_JS)

    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto("about:blank")

    chrome_height = 0
    if not headless:
        try:
            metrics = await page.evaluate("() => ({o: window.outerHeight, i: window.innerHeight})")
            chrome_height = max(0, int(metrics["o"]) - int(metrics["i"]))
        except PlaywrightError:
            chrome_height = 0
    return BrowserSession(playwright=pw, context=context, page=page, chrome_height=chrome_height)


class Director:
    """Ejecuta las acciones del guion sobre la página."""

    def __init__(self, session: BrowserSession, script: Script, *, output_dir: Path) -> None:
        self.session = session
        self.script = script
        self.output_dir = output_dir
        self.screenshots: list[str] = []
        self._shot_seq = 0

    @property
    def page(self) -> Page:
        # Si la app abre una pestaña nueva, seguimos a la última.
        pages = [p for p in self.session.context.pages if not p.is_closed()]
        if pages and pages[-1] is not self.session.page:
            self.session.page = pages[-1]
        return self.session.page

    # ----------------------------------------------------------------- #
    # Auxiliares
    # ----------------------------------------------------------------- #
    def _timeout(self, params: dict) -> float:
        return float(params.get("timeout", self.script.timeout)) * 1000

    def _locator(self, params: dict, key: str = "selector") -> Locator:
        selector = params[key]
        loc = self.page.locator(selector)
        index = params.get("index")
        return loc.nth(int(index)) if index is not None else loc.first

    async def _box(self, loc: Locator) -> dict | None:
        try:
            return await loc.bounding_box()
        except PlaywrightError:
            return None

    async def _glide(self, loc: Locator, params: dict) -> None:
        """Lleva el puntero hasta el elemento con un movimiento continuo."""
        if params.get("move") is False:
            return
        try:
            await loc.scroll_into_view_if_needed(timeout=self._timeout(params))
        except PlaywrightError:
            pass
        box = await self._box(loc)
        if not box:
            return
        await self.page.mouse.move(
            box["x"] + box["width"] / 2,
            box["y"] + box["height"] / 2,
            steps=max(1, self.script.move_steps),
        )
        await self.page.wait_for_timeout(120)

    async def _overlay(self, fn: str, *args) -> None:
        try:
            await self.page.evaluate(
                f"(a) => window.__vtr && window.__vtr.{fn}(...a)", list(args)
            )
        except PlaywrightError:
            pass  # la capa visual nunca debe romper la grabación

    def _url(self, url: str) -> str:
        if url.startswith(("http://", "https://", "file://", "about:", "data:")):
            return url
        base = (self.script.base_url or "").rstrip("/")
        if not base:
            raise BrowserError(f"la URL '{url}' es relativa pero el guion no define 'base_url'")
        return f"{base}/{url.lstrip('/')}"

    # ----------------------------------------------------------------- #
    # Despacho
    # ----------------------------------------------------------------- #
    async def run(self, action: Action) -> None:
        handler = getattr(self, f"_do_{action.type}", None)
        if handler is None:  # no debería ocurrir: el parser ya validó
            raise BrowserError(f"acción no implementada: {action.type}")
        try:
            await handler(action.params)
        except BrowserError:
            raise
        except PlaywrightError as exc:
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else str(exc)
            raise BrowserError(
                f"{action.path} ({action.type}) falló: {first}",
                detail=f"URL actual: {self.page.url}",
            ) from exc

    # --- navegación ---------------------------------------------------- #
    async def _do_goto(self, p: dict) -> None:
        url = self._url(p["url"])
        log(f"  → {url}")
        await self.page.goto(
            url,
            wait_until=p.get("wait_until", "load"),
            timeout=max(self._timeout(p), 30000),
        )

    async def _do_back(self, p: dict) -> None:
        await self.page.go_back()

    async def _do_forward(self, p: dict) -> None:
        await self.page.go_forward()

    async def _do_reload(self, p: dict) -> None:
        await self.page.reload()

    # --- interacción --------------------------------------------------- #
    async def _do_click(self, p: dict) -> None:
        loc = self._locator(p)
        await self._glide(loc, p)
        await loc.click(
            button=p.get("button", "left"),
            click_count=int(p.get("clicks", 1)),
            force=bool(p.get("force", False)),
            timeout=self._timeout(p),
        )

    async def _do_dblclick(self, p: dict) -> None:
        loc = self._locator(p)
        await self._glide(loc, p)
        await loc.dblclick(timeout=self._timeout(p))

    async def _do_hover(self, p: dict) -> None:
        loc = self._locator(p)
        await self._glide(loc, p)
        await loc.hover(timeout=self._timeout(p))

    async def _do_fill(self, p: dict) -> None:
        loc = self._locator(p)
        await self._glide(loc, p)
        await loc.fill(p["text"], timeout=self._timeout(p))

    async def _do_type(self, p: dict) -> None:
        loc = self._locator(p)
        await self._glide(loc, p)
        await loc.click(timeout=self._timeout(p))
        if p.get("clear", True):
            await loc.fill("", timeout=self._timeout(p))
        delay = float(p.get("delay", 60))
        if hasattr(loc, "press_sequentially"):
            await loc.press_sequentially(p["text"], delay=delay, timeout=self._timeout(p))
        else:  # Playwright < 1.38
            await loc.type(p["text"], delay=delay, timeout=self._timeout(p))

    async def _do_press(self, p: dict) -> None:
        repeat = int(p.get("repeat", 1))
        if "selector" in p:
            loc = self._locator(p)
            for _ in range(repeat):
                await loc.press(p["key"], timeout=self._timeout(p))
        else:
            for _ in range(repeat):
                await self.page.keyboard.press(p["key"])

    async def _do_select(self, p: dict) -> None:
        loc = self._locator(p)
        await self._glide(loc, p)
        kwargs: dict[str, Any] = {}
        if "value" in p:
            kwargs["value"] = p["value"]
        if "label" in p:
            kwargs["label"] = p["label"]
        if "option_index" in p:
            kwargs["index"] = int(p["option_index"])
        await loc.select_option(timeout=self._timeout(p), **kwargs)

    async def _do_check(self, p: dict) -> None:
        loc = self._locator(p)
        await self._glide(loc, p)
        await loc.check(timeout=self._timeout(p))

    async def _do_uncheck(self, p: dict) -> None:
        loc = self._locator(p)
        await self._glide(loc, p)
        await loc.uncheck(timeout=self._timeout(p))

    async def _do_upload(self, p: dict) -> None:
        files = [str(self.script.resolve(f)) for f in p["files"]]
        missing = [f for f in files if not Path(f).exists()]
        if missing:
            raise BrowserError(f"no existen los archivos a subir: {', '.join(missing)}")
        await self._locator(p).set_input_files(files, timeout=self._timeout(p))

    async def _do_focus(self, p: dict) -> None:
        await self._locator(p).focus(timeout=self._timeout(p))

    async def _do_clear(self, p: dict) -> None:
        await self._locator(p).fill("", timeout=self._timeout(p))

    async def _do_drag(self, p: dict) -> None:
        source = self.page.locator(p["source"]).first
        target = self.page.locator(p["target"]).first
        await self._glide(source, p)
        await source.drag_to(target, timeout=self._timeout(p))

    async def _do_mouse_move(self, p: dict) -> None:
        steps = int(p.get("steps", self.script.move_steps))
        if "selector" in p:
            loc = self._locator(p)
            box = await self._box(loc)
            if not box:
                return
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        else:
            x, y = float(p.get("x", 0)), float(p.get("y", 0))
        await self.page.mouse.move(x, y, steps=max(1, steps))

    # --- desplazamiento y espera --------------------------------------- #
    async def _do_scroll(self, p: dict) -> None:
        behavior = "smooth" if p.get("smooth", True) else "auto"
        if "selector" in p:
            loc = self._locator(p)
            await loc.evaluate(
                "(el, b) => el.scrollIntoView({behavior: b, block: 'center', inline: 'center'})",
                behavior,
            )
        elif "by" in p:
            await self.page.evaluate(
                "([d, b]) => window.scrollBy({top: d, behavior: b})", [float(p["by"]), behavior]
            )
        else:
            await self.page.evaluate(
                "([x, y, b]) => window.scrollTo({left: x, top: y, behavior: b})",
                [float(p.get("x", 0)), float(p.get("y", 0)), behavior],
            )
        await self.page.wait_for_timeout(700 if behavior == "smooth" else 150)

    async def _do_wait(self, p: dict) -> None:
        await self.page.wait_for_timeout(float(p["seconds"]) * 1000)

    async def _do_wait_for(self, p: dict) -> None:
        timeout = self._timeout(p)
        if "selector" in p:
            await self._locator(p).wait_for(state=p.get("state", "visible"), timeout=timeout)
        if "text" in p:
            await self.page.get_by_text(p["text"]).first.wait_for(state="visible", timeout=timeout)
        if "url" in p:
            await self.page.wait_for_url(p["url"], timeout=timeout)
        if "load_state" in p:
            await self.page.wait_for_load_state(p["load_state"], timeout=timeout)

    # --- capa visual ---------------------------------------------------- #
    async def _do_highlight(self, p: dict) -> None:
        loc = self._locator(p)
        if p.get("scroll", True):
            try:
                await loc.scroll_into_view_if_needed(timeout=self._timeout(p))
            except PlaywrightError:
                pass
        box = await self._box(loc)
        if not box:
            raise BrowserError(f"no se pudo localizar '{p['selector']}' para resaltarlo")
        await self._overlay(
            "highlight",
            box,
            {
                "duration": float(p.get("duration", 3.0)),
                "label": p.get("label"),
                "color": p.get("color", "#ff3d71"),
                "padding": float(p.get("padding", 6)),
            },
        )

    async def _do_note(self, p: dict) -> None:
        box = None
        if "selector" in p:
            box = await self._box(self._locator(p))
        await self._overlay(
            "note",
            p["text"],
            {
                "duration": float(p.get("duration", 4.0)),
                "position": p.get("position", "bottom"),
                "box": box,
            },
        )

    async def _do_clear_overlays(self, p: dict) -> None:
        await self._overlay("clear")

    async def _do_zoom(self, p: dict) -> None:
        await self.page.evaluate(
            "(f) => { document.documentElement.style.zoom = f; }", float(p["factor"])
        )
        await self.page.wait_for_timeout(250)

    # --- extras ---------------------------------------------------------- #
    async def _do_screenshot(self, p: dict) -> None:
        self._shot_seq += 1
        rel = p.get("path") or f"capturas/{self.script.output_path.stem}-{self._shot_seq:02d}.png"
        path = self.script.resolve(rel) if Path(rel).is_absolute() else (self.output_dir / rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        if "selector" in p:
            await self._locator(p).screenshot(path=str(path))
        else:
            await self.page.screenshot(path=str(path), full_page=bool(p.get("full_page", False)))
        self.screenshots.append(str(path))

    async def _do_eval(self, p: dict) -> None:
        expr = p["expression"]
        if "selector" in p:
            await self._locator(p).evaluate(expr if expr.strip().startswith("(") else f"(el) => {{ {expr} }}")
        else:
            await self.page.evaluate(expr if expr.strip().startswith("(") else f"() => {{ {expr} }}")
