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
      --card: transparent;
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
      background-repeat: no-repeat;
      z-index: -2;
      /* Fundo Pic Brand visivel; filtros leves para nao travar a GPU */
      filter: saturate(1.12) contrast(1.06) brightness(1.03);
      transform: scale(1.02);
      transform-origin: center center;
    }
    .grid {
      --tile-size: 120px;
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      z-index: 2;
      /* Faixa superior curta; com .grid-fullscreen cobre o ecra (video cliente). */
      height: calc(var(--tile-size) * 6);
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      align-content: flex-start;
      justify-content: flex-start;
      overflow: hidden;
    }
    .grid.grid-fullscreen {
      height: 100vh;
      height: 100dvh;
    }
    .grid.focused {
      filter: blur(2px) brightness(0.78);
      transition: filter 380ms cubic-bezier(0.22, 1, 0.36, 1);
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
      /* Mais transparente sobre o fundo Pic Brand; sem multiply (evita tom esverdeado). */
      opacity: 0.48;
      mix-blend-mode: normal;
      transition: opacity 0.35s ease;
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
      z-index: 3;
      display: grid;
      place-items: center;
      pointer-events: none;
      opacity: 0;
      transition: opacity 260ms cubic-bezier(0.22, 1, 0.36, 1);
    }
    .spotlight.show {
      opacity: 1;
    }
    .spotlight.show.exit {
      opacity: 0;
      transition: opacity 340ms cubic-bezier(0.4, 0, 0.2, 1) 80ms;
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
      animation: spotlightExit 560ms cubic-bezier(0.4, 0, 0.2, 1) forwards;
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
      40% {
        opacity: 0.95;
      }
      100% {
        transform: translateY(12px) scale(0.93);
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
      tile_interval_ms: 360,
      duplicate_fill: false,
      mosaic_fullscreen: true,
      tile_size_px: 120,
    };
    const renderedSet = new Set();
    const srcToNode = new Map();
    const pendingQueue = [];
    const pendingSet = new Set();
    let feederRunning = false;
    let feederTimer = null;
    let firstSyncDone = false;
    let firstSyncPending = false;
    let lastDupSig = "";
    let prevDupFill = false;
    let bulkAppendTimer = null;
    let bulkAppendSig = "";
    let resizeTimer = null;
    let bulkAppendGen = 0;
    const BULK_TILE_CHUNK = 40;
    let lastMosaicFp = "";
    let lastSettingsKey = "";

    function applyGridLayout() {
      const px = Math.max(64, Math.min(220, Number(settings.tile_size_px) || 120));
      grid.style.setProperty("--tile-size", px + "px");
      grid.classList.toggle("grid-fullscreen", !!settings.mosaic_fullscreen);
    }

    function computeTargetSlots() {
      const style = getComputedStyle(grid);
      let ts = parseFloat(style.getPropertyValue("--tile-size"));
      if (!Number.isFinite(ts) || ts <= 0) ts = 120;
      const w = grid.clientWidth || 0;
      const h = grid.clientHeight || 0;
      if (w <= 0 || h <= 0) return 0;
      const cols = Math.max(1, Math.floor(w / ts));
      const rows = Math.max(1, Math.floor(h / ts));
      return cols * rows;
    }

    function expandToTarget(base, target) {
      if (!base || !base.length || target <= 0) return [];
      const out = [];
      for (let i = 0; i < target; i++) {
        const src = base[i % base.length];
        const sep = src.includes("?") ? "&" : "?";
        out.push(src + sep + "fill=" + i);
      }
      return out;
    }

    function intensityProfile() {
      /* spotlightExit = ms com o hero em destaque antes da animacao de volta ao mosaico */
      const map = {
        suave: { entry: 280, spotlightExit: 820 },
        medio: { entry: 420, spotlightExit: 1320 },
        forte: { entry: 620, spotlightExit: 1880 },
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
      const exitCardMs = 560;
      const settleMs = 140;
      const hideAt = prof.spotlightExit + exitCardMs + settleMs;

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
        grid.classList.remove("focused");
      }, prof.spotlightExit);
      spotlightTimer = setTimeout(() => {
        spotlight.classList.remove("exit");
        spotlight.classList.remove("show");
        spotlightTimer = null;
        spotlightExitTimer = null;
      }, hideAt);
    }

    function shouldShowSpotlight() {
      const m = modeKey();
      return m === "hero_spotlight_pulse" || m === "soft_zoom_fade";
    }

    function createTile(src, animated, lazyLoad) {
      const d = document.createElement("div");
      d.className = "tile" + (animated ? " anim-" + modeKey() : "");
      if (animated) {
        d.style.setProperty("--entry-ms", intensityProfile().entry + "ms");
      }
      const img = document.createElement("img");
      img.loading = lazyLoad ? "lazy" : "eager";
      img.decoding = "async";
      if ("fetchPriority" in img) img.fetchPriority = lazyLoad ? "low" : "auto";
      img.src = src;
      d.appendChild(img);
      return d;
    }

    function appendTile(src, animated) {
      if (renderedSet.has(src)) return;
      const d = createTile(src, animated, false);
      grid.appendChild(d);
      renderedSet.add(src);
      srcToNode.set(src, d);
    }

    function appendTilesInstantChunk(images, start, lazyLoad) {
      const frag = document.createDocumentFragment();
      const end = Math.min(start + BULK_TILE_CHUNK, images.length);
      for (let i = start; i < end; i++) {
        const src = images[i];
        if (renderedSet.has(src)) continue;
        const d = createTile(src, false, lazyLoad);
        frag.appendChild(d);
        renderedSet.add(src);
        srcToNode.set(src, d);
      }
      grid.appendChild(frag);
      return end;
    }

    function appendTilesInstant(images, onDone) {
      bulkAppendGen += 1;
      const myGen = bulkAppendGen;
      const lazyLoad = images.length > 16;
      if (images.length <= BULK_TILE_CHUNK) {
        appendTilesInstantChunk(images, 0, lazyLoad);
        if (typeof onDone === "function") onDone();
        return;
      }
      let offset = 0;
      function step() {
        if (myGen !== bulkAppendGen) return;
        offset = appendTilesInstantChunk(images, offset, lazyLoad);
        if (offset < images.length) {
          requestAnimationFrame(step);
        } else if (typeof onDone === "function") {
          onDone();
        }
      }
      requestAnimationFrame(step);
    }

    function clearGrid() {
      bulkAppendGen += 1;
      grid.innerHTML = "";
      renderedSet.clear();
      srcToNode.clear();
      pendingQueue.length = 0;
      pendingSet.clear();
      if (feederTimer) { clearTimeout(feederTimer); feederTimer = null; }
      if (bulkAppendTimer) { clearTimeout(bulkAppendTimer); bulkAppendTimer = null; }
      bulkAppendSig = "";
      feederRunning = false;
      firstSyncDone = false;
      firstSyncPending = false;
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
      pendingSet.delete(src);
      appendTile(src, true);
      if (shouldShowSpotlight()) {
        showSpotlight(src);
      }
      if (!pendingQueue.length) { feederRunning = false; return; }
      const wait = Math.max(80, Math.min(8000, settings.tile_interval_ms || 360));
      feederTimer = setTimeout(feedStep, wait);
    }

    function syncQueueFromServer(images) {
      const dup = !!settings.duplicate_fill;
      if (dup !== prevDupFill) {
        prevDupFill = dup;
        lastDupSig = "";
        clearGrid();
      }

      if (dup) {
        const target = computeTargetSlots();
        if (!images.length) {
          if (lastDupSig !== "") {
            clearGrid();
            lastDupSig = "";
          }
          return;
        }
        if (target <= 0) return;
        const display = expandToTarget(images, target);
        const sig = display.length + "\0" + (display[0] || "") + "\0" + (display[display.length - 1] || "");
        if (sig === lastDupSig) return;
        if (bulkAppendTimer) { clearTimeout(bulkAppendTimer); bulkAppendTimer = null; }
        clearGrid();
        lastDupSig = sig;
        firstSyncPending = true;
        appendTilesInstant(display, () => {
          firstSyncDone = true;
          firstSyncPending = false;
        });
        return;
      }

      lastDupSig = "";
      if (!images.length) {
        if (renderedSet.size) clearGrid();
        return;
      }
      /* Evitar clearGrid() por lista mais curta (leitura transitoria): apagava pendingQueue e
         estourava centenas de pastilhas de uma vez sem cadencia. Removemos so tiles obsoletos. */
      if (images.length < renderedSet.size) {
        const keep = new Set(images);
        for (let i = pendingQueue.length - 1; i >= 0; i--) {
          const q = pendingQueue[i];
          if (!keep.has(q)) {
            pendingSet.delete(q);
            pendingQueue.splice(i, 1);
          }
        }
        for (const s of Array.from(renderedSet)) {
          if (!keep.has(s)) {
            renderedSet.delete(s);
            const node = srcToNode.get(s);
            if (node) {
              node.remove();
              srcToNode.delete(s);
            }
          }
        }
      }
      if (!firstSyncDone) {
        if (firstSyncPending) return;
        firstSyncPending = true;
        appendTilesInstant(images, () => {
          firstSyncDone = true;
          firstSyncPending = false;
          startFeederIfNeeded();
        });
        return;
      }
      for (const src of images) {
        if (!renderedSet.has(src) && !pendingSet.has(src)) {
          pendingQueue.push(src);
          pendingSet.add(src);
        }
      }
      startFeederIfNeeded();
    }

    async function tick() {
      try {
        const r = await fetch("/api/state", { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        const images = data.images || [];
        if (data.settings) settings = Object.assign(settings, data.settings);
        applyGridLayout();
        const gen = Number(data.mosaic_generation) || 0;
        const settingsKey = [
          settings.tile_size_px,
          settings.duplicate_fill,
          settings.mosaic_fullscreen,
          settings.animation_mode,
          settings.animation_intensity,
        ].join("|");
        const fp = gen + "|" + images.length + "|" + (images[0] || "") + "|" + (images[images.length - 1] || "");
        if (fp !== lastMosaicFp || settingsKey !== lastSettingsKey) {
          lastMosaicFp = fp;
          lastSettingsKey = settingsKey;
          known = images.slice();
          syncQueueFromServer(images);
        }
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

    applyGridLayout();
    tick();
    /* ~0,8 s: resposta mais rapida; syncQueue evita trabalho quando o estado nao muda. */
    setInterval(tick, 800);
    setInterval(cycleSpotlight, 10000);

    window.addEventListener("resize", () => {
      if (!settings.duplicate_fill) return;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        lastDupSig = "";
        lastMosaicFp = "";
        tick();
      }, 200);
    });

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
    setInterval(checkVersion, 2500);
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
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            stem = file_path.stem.lower()
            if re.match(r"^img\d+$", stem):
                self.send_header("Cache-Control", "public, max-age=604800, immutable")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/background":
            bg = self.server_ref.background_path
            if bg is None or not bg.exists():
                self.send_error(404)
                return
            ctype = mimetypes.guess_type(str(bg))[0] or "application/octet-stream"
            body = bg.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=600")
            self.end_headers()
            self.wfile.write(body)
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
        self.tile_interval_ms: int = 360
        self.tile_size_px: int = 120
        self.mosaic_fullscreen: bool = True
        self.duplicate_fill: bool = False

        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False
        self._opened_once = False
        # Incrementado quando chega nova pastilha (injecao/monitor) para o cliente re-pollar.
        self._mosaic_generation: int = 0
        self._images_list_cache: list[str] | None = None
        self._images_list_mtime: int | None = None
        self._images_cache_gen: int = -1

    def update_settings(
        self,
        animation_mode: str | None = None,
        animation_intensity: str | None = None,
        tile_interval_ms: int | None = None,
        tile_size_px: int | None = None,
        mosaic_fullscreen: bool | None = None,
        duplicate_fill: bool | None = None,
    ):
        if animation_mode is not None:
            s = str(animation_mode).strip().lower()
            if s:
                self.animation_mode = s
        if animation_intensity is not None:
            s = str(animation_intensity).strip().lower()
            if s:
                self.animation_intensity = s
        if tile_interval_ms is not None:
            try:
                self.tile_interval_ms = max(80, min(8000, int(tile_interval_ms)))
            except (TypeError, ValueError):
                pass
        if tile_size_px is not None:
            try:
                self.tile_size_px = max(64, min(220, int(tile_size_px)))
            except (TypeError, ValueError):
                pass
        if mosaic_fullscreen is not None:
            self.mosaic_fullscreen = bool(mosaic_fullscreen)
        if duplicate_fill is not None:
            self.duplicate_fill = bool(duplicate_fill)

    def notify_mosaic_changed(self) -> None:
        """Chame apos cada nova imagem no MOSAIC para o cliente re-pollar."""
        try:
            self._mosaic_generation = int(self._mosaic_generation) + 1
        except (TypeError, ValueError):
            self._mosaic_generation = 1
        self._images_list_cache = None
        self._images_list_mtime = None

    def _list_mosaic_image_urls(self) -> list[str]:
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif"}
        try:
            mtime_ns = int(self.mosaic_dir.stat().st_mtime_ns)
        except OSError:
            mtime_ns = -1

        if self._images_list_cache is not None:
            if getattr(self, "_images_cache_gen", -1) != self._mosaic_generation:
                pass
            elif self._images_list_mtime == mtime_ns:
                return self._images_list_cache

        def _order_key(path: Path):
            m = re.match(r"^img(\d+)$", path.stem.lower())
            if m:
                return (0, int(m.group(1)), path.name.lower())
            return (1, 0, path.name.lower())

        images: list[str] = []
        try:
            for p in sorted(self.mosaic_dir.iterdir(), key=_order_key):
                if p.is_file() and p.suffix.lower() in exts:
                    images.append(f"/mosaic/{p.name}")
        except OSError:
            images = []

        self._images_list_cache = images
        self._images_list_mtime = mtime_ns
        self._images_cache_gen = int(self._mosaic_generation)
        return images

    def build_state(self) -> dict:
        images = self._list_mosaic_image_urls()
        return {
            "images": images,
            "mosaic_generation": int(self._mosaic_generation),
            "background": "/background" if self.background_path and self.background_path.exists() else None,
            "settings": {
                "animation_mode": self.animation_mode,
                "animation_intensity": self.animation_intensity,
                "tile_interval_ms": self.tile_interval_ms,
                "tile_size_px": self.tile_size_px,
                "mosaic_fullscreen": self.mosaic_fullscreen,
                "duplicate_fill": self.duplicate_fill,
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

