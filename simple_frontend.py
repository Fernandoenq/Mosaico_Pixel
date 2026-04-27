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
      min-height: 100vh;
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
      height: 100vh;
      padding: 10px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
      gap: 6px;
      align-content: start;
      overflow: auto;
    }
    .grid.focused {
      filter: blur(2px) brightness(0.78);
      transition: filter 220ms ease;
    }
    .tile {
      width: 100%;
      aspect-ratio: 1 / 1;
      border-radius: 8px;
      overflow: hidden;
      background: var(--card);
      border: none;
    }
    .tile img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      image-rendering: auto;
      display: block;
      opacity: 0.42;
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
      width: min(36vw, 520px);
      aspect-ratio: 1 / 1;
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.28);
      box-shadow: 0 0 36px rgba(255, 255, 255, 0.16);
      background: rgba(22, 24, 30, 0.8);
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
      object-fit: cover;
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
    let tiles = new Map();
    let bgCurrent = "";
    let spotlightTimer = null;
    let spotlightExitTimer = null;
    let cycleIndex = 0;

    function sameList(a, b) {
      if (a.length !== b.length) return false;
      for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
      return true;
    }

    function showSpotlight(src) {
      if (spotlightTimer) {
        clearTimeout(spotlightTimer);
        spotlightTimer = null;
      }
      if (spotlightExitTimer) {
        clearTimeout(spotlightExitTimer);
        spotlightExitTimer = null;
      }
      spotlightImg.src = src;
      spotlight.classList.remove("exit");
      spotlight.classList.remove("enter");
      spotlight.classList.add("show");
      spotlight.classList.add("enter");
      grid.classList.add("focused");

      // Remove classe de entrada após completar animação.
      setTimeout(() => spotlight.classList.remove("enter"), 560);

      // Inicia animação de saída pouco antes de esconder.
      spotlightExitTimer = setTimeout(() => {
        spotlight.classList.add("exit");
      }, 1300);

      spotlightTimer = setTimeout(() => {
        spotlight.classList.remove("exit");
        spotlight.classList.remove("show");
        grid.classList.remove("focused");
        spotlightTimer = null;
        spotlightExitTimer = null;
      }, 1700);
    }

    function createTile(src) {
      const d = document.createElement("div");
      d.className = "tile";
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = src;
      d.appendChild(img);
      return d;
    }

    function render(images) {
      const newSet = new Set(images);

      // Remove tiles inexistentes (ex: limpar mosaico)
      for (const [src, el] of tiles.entries()) {
        if (!newSet.has(src)) {
          el.remove();
          tiles.delete(src);
        }
      }

      // Adiciona apenas novas imagens (evita piscar)
      for (const src of images) {
        if (!tiles.has(src)) {
          const el = createTile(src);
          grid.appendChild(el);
          tiles.set(src, el);
          showSpotlight(src);
        }
      }

      // Reordena visualmente conforme lista do backend
      const frag = document.createDocumentFragment();
      for (const src of images) {
        const el = tiles.get(src);
        if (el) frag.appendChild(el);
      }
      grid.innerHTML = "";
      grid.appendChild(frag);
    }

    async function tick() {
      try {
        const r = await fetch("/api/state", { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        const images = data.images || [];
        if (!sameList(images, known)) {
          known = images.slice();
          render(images);
        }
        const nextBg = data.background || "";
        if (nextBg !== bgCurrent) {
          bgCurrent = nextBg;
          bg.style.backgroundImage = nextBg ? `url("${nextBg}")` : "";
        }
      } catch (e) {}
    }

    function cycleSpotlight() {
      if (!known.length) return;
      if (cycleIndex >= known.length) cycleIndex = 0;
      const src = known[cycleIndex];
      cycleIndex += 1;
      if (src) showSpotlight(src);
    }

    tick();
    setInterval(tick, 1200);
    setInterval(cycleSpotlight, 10000);
  </script>
</body>
</html>
"""


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
            self._send_bytes(HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path == "/api/state":
            self._send_json(self.server_ref.build_state())
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

        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False
        self._opened_once = False

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

