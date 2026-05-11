#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Frontend web básico para visualização do mosaico em boa qualidade.
"""

from __future__ import annotations

import json
import mimetypes
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


HTML_PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Mosaico Pic Brand - Front</title>
  <style>
    :root {
      --bg: #0f0f12;
      --card: rgba(22, 24, 30, 0.15);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Segoe UI, Arial, sans-serif;
      background: var(--bg);
      width: 100vw;
      height: 100vh;
      overflow: hidden;
    }
    .bg {
      position: fixed;
      inset: 0;
      background-size: cover;
      background-position: center;
      filter: saturate(1.05);
      z-index: -2;
    }
    .bg::after {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(rgba(10, 8, 18, 0.25), rgba(10, 8, 18, 0.45));
      z-index: -1;
    }
    .grid {
      --tile-size: 56px;
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      /* Faixa superior mais curta, semelhante ao layout de referência. */
      height: calc(var(--tile-size) * 6);
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      align-content: flex-start;
      justify-content: flex-start;
      overflow: hidden;
    }
    .grid.focused {
      filter: blur(2px) brightness(0.78);
      transition: filter 220ms ease;
    }
    .tile {
      width: var(--tile-size);
      height: var(--tile-size);
      flex: 0 0 var(--tile-size);
      border-radius: 0;
      overflow: hidden;
      background: var(--card);
      border: none;
      animation-fill-mode: backwards;
    }
    .tile img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      image-rendering: auto;
      display: block;
      opacity: 0.55;
      mix-blend-mode: multiply;
    }
    .tile.anim-soft_zoom_fade {
      animation: softZoomFadeIn var(--entry-ms, 420ms) cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    .tile.anim-hero_spotlight_pulse {
      animation: softZoomFadeIn var(--entry-ms, 420ms) cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    .tile.anim-staggered_grid_cascade {
      animation: cascadeIn var(--entry-ms, 420ms) cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    .tile.anim-pure_fade_mosaic {
      animation: pureFade var(--entry-ms, 420ms) ease both;
    }
    @keyframes softZoomFadeIn {
      0% { transform: scale(0.86); opacity: 0; }
      100% { transform: scale(1); opacity: 1; }
    }
    @keyframes cascadeIn {
      0% { transform: translateY(-10px); opacity: 0; }
      100% { transform: translateY(0); opacity: 1; }
    }
    @keyframes pureFade {
      0% { opacity: 0; }
      100% { opacity: 1; }
    }
    .spotlight {
      position: fixed;
      inset: 0;
      display: grid;
      place-items: center;
      pointer-events: none;
      opacity: 0;
      transition: opacity 180ms ease;
    }
    .spotlight.show {
      opacity: 1;
    }
    .spotlight-card {
      width: min(86vw, 1080px);
      height: min(92vh, 1280px);
      max-width: 96vw;
      max-height: 94vh;
      aspect-ratio: auto;
      border-radius: 20px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.28);
      box-shadow: 0 0 60px rgba(255, 255, 255, 0.2);
      background: transparent;
      transform-origin: center center;
      will-change: transform, opacity;
    }
    .spotlight.enter .spotlight-card {
      animation: spotlightEnter 520ms cubic-bezier(0.22, 1, 0.36, 1) forwards;
    }
    .spotlight.exit .spotlight-card {
      animation: spotlightExit 420ms cubic-bezier(0.55, 0.06, 0.68, 0.19) forwards;
    }
    @keyframes spotlightEnter {
      0% {
        transform: translateY(20px) scale(0.85);
        opacity: 0;
      }
      100% {
        transform: translateY(0) scale(1);
        opacity: 1;
      }
    }
    @keyframes spotlightExit {
      0% {
        transform: translateY(0) scale(1);
        opacity: 1;
      }
      100% {
        transform: translateY(-10px) scale(0.88);
        opacity: 0;
      }
    }
    .spotlight-card img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }
  </style>
</head>
<body>
  <div class="bg" id="bg"></div>
  <div class="grid" id="grid"></div>
  <div class="spotlight" id="spotlight">
    <div class="spotlight-card">
      <img id="spotlightImg" alt="Nova imagem" />
    </div>
  </div>

  <script>
    const grid = document.getElementById("grid");
    const bg = document.getElementById("bg");
    const spotlight = document.getElementById("spotlight");
    const spotlightImg = document.getElementById("spotlightImg");
    let known = [];
    let bgCurrent = "";
    let spotlightTimer = null;
    let spotlightExitTimer = null;
    let cycleIndex = 0;

    let settings = {
      animation_mode: "soft_zoom_fade",
      animation_intensity: "medio",
      tile_interval_ms: 420,
    };
    const renderedSet = new Set();
    const pendingQueue = [];
    let feederRunning = false;
    let feederTimer = null;
    let firstSyncDone = false;

    function intensityProfile() {
      const map = {
        suave: { entry: 280, spotlightShow: 1100, spotlightExit: 900 },
        medio: { entry: 420, spotlightShow: 1700, spotlightExit: 1300 },
        forte: { entry: 620, spotlightShow: 2300, spotlightExit: 1800 },
      };
      return map[settings.animation_intensity] || map.medio;
    }

    function modeKey() {
      const allowed = new Set([
        "soft_zoom_fade",
        "hero_spotlight_pulse",
        "staggered_grid_cascade",
        "pure_fade_mosaic",
      ]);
      return allowed.has(settings.animation_mode) ? settings.animation_mode : "soft_zoom_fade";
    }

    function showSpotlight(src) {
      const prof = intensityProfile();
      if (spotlightTimer) { clearTimeout(spotlightTimer); spotlightTimer = null; }
      if (spotlightExitTimer) { clearTimeout(spotlightExitTimer); spotlightExitTimer = null; }
      spotlightImg.src = src;
      spotlight.classList.remove("exit");
      spotlight.classList.remove("enter");
      spotlight.classList.add("show");
      spotlight.classList.add("enter");
      grid.classList.add("focused");

      setTimeout(() => spotlight.classList.remove("enter"), 560);
      spotlightExitTimer = setTimeout(() => {
        spotlight.classList.add("exit");
      }, prof.spotlightExit);
      spotlightTimer = setTimeout(() => {
        spotlight.classList.remove("exit");
        spotlight.classList.remove("show");
        grid.classList.remove("focused");
        spotlightTimer = null;
        spotlightExitTimer = null;
      }, prof.spotlightShow);
    }

    function shouldShowSpotlight() {
      const m = modeKey();
      return m === "hero_spotlight_pulse" || m === "soft_zoom_fade";
    }

    function createTile(src, animated) {
      const d = document.createElement("div");
      d.className = "tile" + (animated ? " anim-" + modeKey() : "");
      if (animated) {
        d.style.setProperty("--entry-ms", intensityProfile().entry + "ms");
      }
      const img = document.createElement("img");
      img.loading = "lazy";
      img.decoding = "async";
      img.src = src;
      d.appendChild(img);
      return d;
    }

    function appendTile(src, animated) {
      if (renderedSet.has(src)) return;
      grid.appendChild(createTile(src, animated));
      renderedSet.add(src);
    }

    function appendTilesInstant(images) {
      // Render inicial: preserva a estrutura original sem animar nem enfileirar.
      const frag = document.createDocumentFragment();
      for (const src of images) {
        if (renderedSet.has(src)) continue;
        frag.appendChild(createTile(src, false));
        renderedSet.add(src);
      }
      grid.appendChild(frag);
    }

    function clearGrid() {
      grid.innerHTML = "";
      renderedSet.clear();
      pendingQueue.length = 0;
      if (feederTimer) { clearTimeout(feederTimer); feederTimer = null; }
      feederRunning = false;
      firstSyncDone = false;
    }

    function startFeederIfNeeded() {
      if (feederRunning) return;
      if (!pendingQueue.length) return;
      feederRunning = true;
      feedStep();
    }

    function feedStep() {
      feederTimer = null;
      if (!pendingQueue.length) { feederRunning = false; return; }
      const src = pendingQueue.shift();
      appendTile(src, true);
      if (shouldShowSpotlight()) {
        showSpotlight(src);
      }
      if (!pendingQueue.length) { feederRunning = false; return; }
      const wait = Math.max(80, Math.min(8000, settings.tile_interval_ms || 420));
      feederTimer = setTimeout(feedStep, wait);
    }

    function syncQueueFromServer(images) {
      // Lista do servidor diminuiu (limpar/reset) → reset total.
      if (images.length < renderedSet.size) {
        clearGrid();
      }
      // Render inicial (load da página): instantâneo, sem alterar disposição.
      if (!firstSyncDone) {
        appendTilesInstant(images);
        firstSyncDone = true;
        return;
      }
      // A partir daqui, somente imagens novas entram com animação/intervalo.
      for (const src of images) {
        if (!renderedSet.has(src) && !pendingQueue.includes(src)) {
          pendingQueue.push(src);
        }
      }
      startFeederIfNeeded();
    }

    async function tick() {
      try {
        const r = await fetch("/api/state", { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        if (data.settings) settings = Object.assign(settings, data.settings);
        const images = data.images || [];
        known = images.slice();
        syncQueueFromServer(images);
        const nextBg = data.background || "";
        if (nextBg !== bgCurrent) {
          bgCurrent = nextBg;
          bg.style.backgroundImage = nextBg ? `url("${nextBg}")` : "";
        }
      } catch (e) {}
    }

    function cycleSpotlight() {
      if (!shouldShowSpotlight()) return;
      if (!known.length) return;
      if (cycleIndex >= known.length) cycleIndex = 0;
      const src = known[cycleIndex];
      cycleIndex += 1;
      if (src) showSpotlight(src);
    }

    tick();
    setInterval(tick, 1200);
    setInterval(cycleSpotlight, 10000);

    // Live reload: recarrega a aba quando o template HTML mudar no servidor.
    let __frontVersion = null;
    async function checkVersion() {
      try {
        const r = await fetch("/api/version", { cache: "no-store" });
        if (!r.ok) return;
        const d = await r.json();
        if (__frontVersion == null) {
          __frontVersion = d.version;
          return;
        }
        if (d.version !== __frontVersion) {
          location.reload();
        }
      } catch (e) {}
    }
    setInterval(checkVersion, 1000);
  </script>
</body>
</html>
"""


def _load_html_page() -> str:
    """
    Relê o template HTML deste arquivo a cada chamada, para suportar live-reload.
    Se algo falhar, devolve a constante embutida.
    """
    try:
        src_path = Path(__file__)
        text = src_path.read_text(encoding="utf-8")
        match = re.search(r'HTML_PAGE\s*=\s*"""(.*?)"""', text, flags=re.DOTALL)
        if match:
            return match.group(1)
    except Exception:
        pass
    return HTML_PAGE


def _frontend_version() -> str:
    """Versao baseada no mtime deste arquivo, para o JS detectar mudancas."""
    try:
        return str(Path(__file__).stat().st_mtime_ns)
    except Exception:
        return "0"


class _FrontendHandler(BaseHTTPRequestHandler):
    server_ref: "SimpleMosaicFrontend" = None  # type: ignore[assignment]

    def log_message(self, fmt, *args):  # noqa: N802
        return

    def _send_json(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, body: bytes, content_type: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path in ("/", "/index.html"):
            html = _load_html_page().encode("utf-8")
            self._send_bytes(html, "text/html; charset=utf-8")
            return

        if path == "/api/state":
            self._send_json(self.server_ref.build_state())
            return

        if path == "/api/version":
            self._send_json({"version": _frontend_version()})
            return

        if path.startswith("/mosaic/"):
            name = path.removeprefix("/mosaic/")
            file_path = (self.server_ref.mosaic_dir / name).resolve()
            if not str(file_path).startswith(str(self.server_ref.mosaic_dir.resolve())) or not file_path.exists():
                self.send_error(404)
                return
            ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self._send_bytes(file_path.read_bytes(), ctype)
            return

        if path == "/background":
            bg = self.server_ref.background_path
            if bg is None or not bg.exists():
                self.send_error(404)
                return
            ctype = mimetypes.guess_type(str(bg))[0] or "application/octet-stream"
            self._send_bytes(bg.read_bytes(), ctype)
            return

        self.send_error(404)


class SimpleMosaicFrontend:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.mosaic_dir = Path.cwd() / "MOSAIC"
        self.background_path: Path | None = None

        # Configs sincronizadas com a interface principal.
        self.animation_mode: str = "soft_zoom_fade"
        self.animation_intensity: str = "medio"
        self.tile_interval_ms: int = 420

        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False
        self._opened_once = False

    def update_settings(
        self,
        animation_mode: str | None = None,
        animation_intensity: str | None = None,
        tile_interval_ms: int | None = None,
    ):
        if animation_mode:
            self.animation_mode = animation_mode.strip().lower()
        if animation_intensity:
            self.animation_intensity = animation_intensity.strip().lower()
        if tile_interval_ms is not None:
            try:
                self.tile_interval_ms = max(80, min(8000, int(tile_interval_ms)))
            except (TypeError, ValueError):
                pass

    def build_state(self) -> dict:
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif"}
        images = []
        if self.mosaic_dir.exists():
            def _order_key(path: Path):
                m = re.match(r"^img(\d+)$", path.stem.lower())
                if m:
                    return (0, int(m.group(1)), path.name.lower())
                return (1, 0, path.name.lower())

            for p in sorted(self.mosaic_dir.iterdir(), key=_order_key):
                if p.is_file() and p.suffix.lower() in exts:
                    images.append(f"/mosaic/{p.name}")
        return {
            "images": images,
            "background": "/background" if self.background_path and self.background_path.exists() else None,
            "settings": {
                "animation_mode": self.animation_mode,
                "animation_intensity": self.animation_intensity,
                "tile_interval_ms": self.tile_interval_ms,
            },
        }

    def start(self, background_path: str | None = None):
        if background_path:
            bg = Path(background_path)
            self.background_path = bg if bg.exists() else None
        else:
            self.background_path = None

        if self._is_running:
            return

        handler = type("DynamicFrontendHandler", (_FrontendHandler,), {})
        handler.server_ref = self
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self._is_running = True

        if not self._opened_once:
            webbrowser.open(f"http://{self.host}:{self.port}", new=1)
            self._opened_once = True

    def stop(self):
        if not self._is_running:
            return
        assert self._httpd is not None
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._is_running = False

