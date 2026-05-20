#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Frontend web básico para visualização do mosaico em boa qualidade.
"""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from image_orientation import needs_mosaic_normalize, oriented_image_bytes

_PROJECT_DIR = Path(__file__).resolve().parent
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif", ".gif"}


def _is_image_file(path: Path) -> bool:
    if not path.is_file():
        return False
    ext = path.suffix.lower()
    if ext in _IMAGE_EXTENSIONS:
        return True
    if ext:
        return False
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return False
    return (
        head.startswith(b"\xff\xd8")
        or head.startswith(b"\x89PNG\r\n\x1a\n")
        or (len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP")
        or head.startswith(b"BM")
        or head.startswith(b"GIF8")
    )


def _guess_image_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith(b"GIF8"):
        return "image/gif"
    return "image/jpeg"


# Telão P2.6 mm reto (INDOOR): 768×960 px, grelha 4×5, módulo 192×192 px (4:5)
TELAO_LARGURA_PX = 768
TELAO_ALTURA_PX = 960
TELAO_MODULO_PX = 192
TELAO_COLUNAS = 20
TELAO_LINHAS = 5
# Intervalo minimo entre destaques no centro (evita cortar animacao da foto anterior).
TELAO_SPOTLIGHT_GAP_MS = 1500


HTML_PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
  <meta http-equiv="Pragma" content="no-cache" />
  <meta http-equiv="Expires" content="0" />
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
    .telao-shell {
      position: fixed;
      top: 0;
      left: 0;
      z-index: 10;
      width: 768px;
      height: 960px;
      transform-origin: top left;
      will-change: transform;
      overflow: hidden;
    }
    .bg {
      position: absolute;
      inset: 0;
      z-index: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      background-color: var(--bg);
      pointer-events: none;
    }
    .bg img {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center;
    }
    .overlay-layer {
      position: absolute;
      inset: 0;
      z-index: 3;
      pointer-events: none;
      display: none !important;
      opacity: 0;
      visibility: hidden;
      align-items: center;
      justify-content: center;
    }
    .overlay-layer.is-revealing {
      display: flex !important;
      opacity: 1;
      visibility: visible;
      transition: none;
    }
    .overlay-layer canvas {
      display: block;
      width: 100%;
      height: 100%;
      pointer-events: none;
      opacity: 1;
      mix-blend-mode: multiply;
    }
    .overlay-layer img.overlay-src {
      display: none;
      width: 0;
      height: 0;
    }
    .telao-shell.shell-fill {
      width: 100vw;
      height: 100dvh;
      transform: none !important;
    }
    .mosaic-stage {
      position: absolute;
      inset: 0;
      z-index: 2;
      overflow: hidden;
      isolation: isolate;
      contain: layout style;
    }
    .grid {
      --tile-size: 48px;
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 0;
      align-content: start;
      justify-content: start;
      overflow: hidden;
    }
    .grid.focused {
      filter: none;
    }
    .tile {
      position: relative;
      width: var(--tile-size, 56px);
      height: var(--tile-size, 56px);
      min-width: 0;
      min-height: 0;
      margin: 0;
      padding: 0;
      box-sizing: border-box;
      border-radius: 0;
      overflow: hidden;
      background: #000;
      border: none;
      contain: layout paint style;
    }
    .tile.tile-animating .tile-photo {
      will-change: transform;
      transform: translateZ(0);
    }
    .tile-photo {
      position: relative;
      z-index: 1;
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center;
      image-rendering: auto;
      display: block;
      opacity: 1;
    }
    .tile.tile-waiting-spotlight .tile-photo,
    .tile.tile-in-mosaic .tile-photo {
      opacity: 1;
    }
    .tile > .tile-photo[class*="anim-"] {
      animation-delay: var(--entry-delay, 0ms);
      animation-timing-function: var(--ease-snap, cubic-bezier(0.16, 1, 0.3, 1));
      backface-visibility: hidden;
    }
    .tile > .tile-photo.anim-soft_zoom_fade {
      animation-name: softZoomFadeIn;
      animation-duration: var(--entry-ms, 520ms);
      animation-fill-mode: both;
    }
    .tile > .tile-photo.anim-hero_spotlight_pulse {
      animation-name: heroSpotlightPulse;
      animation-duration: var(--entry-ms, 520ms);
      animation-fill-mode: both;
    }
    .tile > .tile-photo.anim-staggered_grid_cascade {
      animation-name: cascadeIn;
      animation-duration: var(--entry-ms, 520ms);
      animation-fill-mode: both;
    }
    .tile > .tile-photo.anim-pure_fade_mosaic {
      animation-name: pureSettle;
      animation-duration: var(--entry-ms, 520ms);
      animation-fill-mode: both;
    }
    @keyframes softZoomFadeIn {
      0% {
        opacity: 1;
        transform: scale(0.88) translateZ(0);
      }
      100% {
        opacity: 1;
        transform: scale(1) translateZ(0);
      }
    }
    @keyframes cascadeIn {
      0% {
        opacity: 1;
        transform: translate3d(0, 8px, 0) scale(0.92);
      }
      100% {
        opacity: 1;
        transform: translate3d(0, 0, 0) scale(1);
      }
    }
    @keyframes pureSettle {
      0% {
        opacity: 1;
        transform: scale(0.94);
      }
      100% {
        opacity: 1;
        transform: scale(1);
      }
    }
    @keyframes heroSpotlightPulse {
      0% {
        opacity: 1;
        transform: scale(0.9) translateZ(0);
      }
      100% {
        opacity: 1;
        transform: scale(1) translateZ(0);
      }
    }
    .spotlight {
      position: absolute;
      inset: 0;
      z-index: 4;
      display: flex;
      align-items: center;
      justify-content: center;
      pointer-events: none;
      opacity: 0;
      line-height: 0;
      font-size: 0;
      transition: opacity 260ms cubic-bezier(0.22, 1, 0.36, 1);
    }
    .spotlight.show {
      opacity: 1;
    }
    .spotlight.show.exit {
      opacity: 0;
      transition: opacity 340ms cubic-bezier(0.4, 0, 0.2, 1) 80ms;
    }
    .spotlight.enter #spotlightImg {
      animation: spotlightEnter 620ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }
    .spotlight.exit #spotlightImg {
      animation: spotlightExit 580ms cubic-bezier(0.4, 0, 0.2, 1) forwards;
    }
    @keyframes spotlightEnter {
      0% {
        opacity: 0;
        transform: scale(0.9);
      }
      100% {
        opacity: 1;
        transform: scale(1);
      }
    }
    @keyframes spotlightExit {
      0% {
        opacity: 1;
        transform: scale(1);
      }
      100% {
        opacity: 0;
        transform: scale(0.96);
      }
    }
    #spotlightImg {
      display: block;
      margin: 0;
      padding: 0;
      border: none;
      outline: none;
      width: 0;
      height: 0;
      max-width: min(75%, 560px);
      max-height: min(85%, 680px);
      object-fit: contain;
      border-radius: 12px;
      box-shadow:
        0 0 0 2px rgba(255, 255, 255, 0.35),
        0 12px 80px rgba(0, 0, 0, 0.55);
      background: transparent;
      opacity: 0;
      transform-origin: center center;
    }
    #spotlightImg.spotlight-ready {
      opacity: 1;
    }
  </style>
</head>
<body>
  <div class="telao-shell" id="telaoShell">
    <div class="bg" id="bg"><img id="bgImg" alt="" /></div>
    <div class="mosaic-stage" id="mosaicStage">
      <div class="grid" id="grid"></div>
    </div>
    <div class="overlay-layer" id="overlayLayer" hidden>
      <canvas id="overlayRevealCanvas"></canvas>
    </div>
    <div class="spotlight" id="spotlight">
      <img id="spotlightImg" alt="Nova imagem" />
    </div>
  </div>

  <script>
    const grid = document.getElementById("grid");
    const telaoShell = document.getElementById("telaoShell");
    const mosaicStage = document.getElementById("mosaicStage");
    const bg = document.getElementById("bg");
    const bgImg = document.getElementById("bgImg");
    const overlayRevealCanvas = document.getElementById("overlayRevealCanvas");
    let overlayRevealPaintCtx = null;
    let overlayArtImage = null;
    let overlayCurrent = "";
    let overlayRevealRaf = null;
    const spotlight = document.getElementById("spotlight");
    const spotlightImg = document.getElementById("spotlightImg");
    let known = [];
    let bgCurrent = "";
    let spotlightTimer = null;
    let spotlightExitTimer = null;
    let cycleIndex = 0;
    let spotlightProbe = null;
    let spotlightQueue = [];
    let spotlightActive = false;
    let spotlightBusyUntil = 0;
    let spotlightPumpTimer = null;
    let currentSpotlightSrc = null;
    const SPOTLIGHT_GAP_MS_DEFAULT = 1500;

    let settings = {
      animation_mode: "soft_zoom_fade",
      animation_intensity: "medio",
      tile_interval_ms: 360,
      spotlight_min_gap_ms: 1500,
      duplicate_fill: false,
      mosaic_fullscreen: true,
      tile_size_px: 56,
      mosaic_width: 768,
      mosaic_height: 960,
      mosaic_cols: 20,
      mosaic_rows: 5,
    };
    const renderedSet = new Set();
    const srcToNode = new Map();
    const pendingQueue = [];
    const pendingSet = new Set();
    let feederRunning = false;
    let feederAwaitingSpotlight = false;
    let feederTimer = null;
    let firstSyncDone = false;
    let firstSyncPending = false;
    let lastDupSig = "";
    let prevDupFill = false;
    let bulkAppendTimer = null;
    let bulkAppendSig = "";
    let resizeTimer = null;
    let bulkAppendGen = 0;
    const BULK_TILE_CHUNK = 10;
    const BULK_CHUNK_PAUSE_MS = 110;
    const ENTRY_STAGGER_STEP_MS = 32;
    const ENTRY_STAGGER_MAX_MS = 280;
    const MAX_PARALLEL_TILE_ANIMS = 5;
    const EASE_SNAP = "cubic-bezier(0.16, 1, 0.3, 1)";
    const MAX_DUP_FILL_CELLS = 180;
    let lastMosaicFp = "";
    let lastMosaicGen = 0;
    let lastDeltaGen = 0;
    let lastBrowserFlush = 0;
    let lastSettingsKey = "";
    let layoutCols = 20;
    let layoutRows = 5;
    let layoutTilePx = 48;
    let lastLayoutSig = "";
    let gridCursor = 0;
    function maxGridCells() {
      return Math.max(1, layoutCols * layoutRows);
    }

    /* Overlay por cima do mosaico (invisível): cada célula revela só tile ∩ logo, tinte semitransparente. */
    const OVERLAY_TINT_ALPHA = 0.88;
    const REVEAL_TILE_STAGGER_MS = 10;
    let overlayRevealMask = null;
    let overlayRevealMaskCtx = null;
    let overlayRevealTmp = null;
    let overlayRevealTmpCtx = null;
    let overlayHasReveal = false;
    let overlayLayerPinned = false;
    let tileRevealGen = 0;
    let redrawOverlayPending = 0;
    let overlayRescanPending = 0;
    let overlayPaintDirty = false;
    let activeTileAnims = 0;
    const tileAnimWaitQueue = [];

    function cancelOverlayRevealTrack() {
      if (overlayRevealRaf) {
        cancelAnimationFrame(overlayRevealRaf);
        overlayRevealRaf = null;
      }
    }

    function cancelRedrawOverlayPending() {
      if (redrawOverlayPending) {
        cancelAnimationFrame(redrawOverlayPending);
        redrawOverlayPending = 0;
      }
    }

    function overlayRevealIsActive() {
      return overlayHasReveal && overlayRevealMask && overlayRevealMaskCtx;
    }

    function showOverlayLayerDom() {
      const layer = document.getElementById("overlayLayer");
      if (!layer) return;
      layer.hidden = false;
      layer.classList.add("is-revealing");
      overlayLayerPinned = true;
    }

    function hideOverlayLayer(opts) {
      const clearCanvas = !opts || opts.clearCanvas !== false;
      const hideDom = !opts || opts.hideDom !== false;
      const layer = document.getElementById("overlayLayer");
      if (clearCanvas && overlayRevealPaintCtx && overlayRevealCanvas) {
        overlayRevealPaintCtx.clearRect(
          0, 0, overlayRevealCanvas.width, overlayRevealCanvas.height
        );
      }
      if (!hideDom) return;
      if (!layer) return;
      layer.classList.remove("is-revealing");
      layer.hidden = true;
      overlayLayerPinned = false;
    }

    function resetOverlayReveal() {
      cancelOverlayRevealTrack();
      cancelRedrawOverlayPending();
      if (overlayRescanPending) {
        cancelAnimationFrame(overlayRescanPending);
        overlayRescanPending = 0;
      }
      tileRevealGen += 1;
      overlayRevealMask = null;
      overlayRevealMaskCtx = null;
      overlayHasReveal = false;
      hideOverlayLayer();
    }

    function scheduleOverlayRescan() {
      if (!overlayCurrent) return;
      if (overlayRescanPending) return;
      overlayRescanPending = requestAnimationFrame(function() {
        overlayRescanPending = requestAnimationFrame(function() {
          overlayRescanPending = 0;
          rescanOverlayReveal();
        });
      });
    }

    function loadOverlayArt(url) {
      overlayCurrent = url || "";
      resetOverlayReveal();
      if (!url) {
        overlayArtImage = null;
        return;
      }
      const img = new Image();
      overlayArtImage = img;
      img.onload = function() {
        if (overlayArtImage !== img) return;
        if (overlayRevealMaskCtx && overlayRevealMask) {
          overlayRevealMaskCtx.clearRect(
            0, 0, overlayRevealMask.width, overlayRevealMask.height
          );
        }
        overlayHasReveal = false;
        if (renderedSet.size) scheduleOverlayRescan();
      };
      img.onerror = function() {
        if (overlayArtImage !== img) return;
        overlayCurrent = "";
        overlayArtImage = null;
        resetOverlayReveal();
      };
      img.src = url;
    }

    function fitImageContain(iw, ih, bw, bh) {
      const scale = Math.min(bw / Math.max(1, iw), bh / Math.max(1, ih));
      const w = iw * scale;
      const h = ih * scale;
      return { x: (bw - w) / 2, y: (bh - h) / 2, w: w, h: h };
    }

    /* Área real do grid (onde existem quadradinhos), não o telão inteiro. */
    function getMosaicCoverageRect() {
      const ts = Math.max(1, layoutTilePx || 56);
      const cols = Math.max(1, layoutCols || MOSAIC_COLS_FIXED);
      const rows = Math.max(1, layoutRows || 1);
      const shellW = Math.max(1, telaoShell ? telaoShell.clientWidth : 768);
      const shellH = Math.max(1, telaoShell ? telaoShell.clientHeight : 960);
      return {
        x: 0,
        y: 0,
        w: Math.min(shellW, cols * ts),
        h: Math.min(shellH, rows * ts),
      };
    }

    function fitLogoInMosaicArea(nw, nh) {
      const area = getMosaicCoverageRect();
      const scale = Math.min(
        area.w / Math.max(1, nw),
        area.h / Math.max(1, nh)
      );
      const w = nw * scale;
      const h = nh * scale;
      return {
        x: area.x + (area.w - w) / 2,
        y: area.y,
        w: w,
        h: h,
      };
    }

    function ensureOverlayRevealPaintCtx() {
      if (!telaoShell || !overlayRevealCanvas) return null;
      const w = Math.max(1, telaoShell.clientWidth);
      const h = Math.max(1, telaoShell.clientHeight);
      if (
        overlayRevealCanvas.width !== w
        || overlayRevealCanvas.height !== h
        || !overlayRevealPaintCtx
      ) {
        overlayRevealCanvas.width = w;
        overlayRevealCanvas.height = h;
        overlayRevealPaintCtx = overlayRevealCanvas.getContext("2d", { alpha: true });
      }
      return overlayRevealPaintCtx;
    }

    function ensureOverlayRevealMask() {
      if (!telaoShell) return null;
      const w = Math.max(1, telaoShell.clientWidth);
      const h = Math.max(1, telaoShell.clientHeight);
      if (
        !overlayRevealMask
        || overlayRevealMask.width !== w
        || overlayRevealMask.height !== h
      ) {
        const hadReveal = overlayHasReveal || overlayLayerPinned;
        overlayRevealMask = document.createElement("canvas");
        overlayRevealMask.width = w;
        overlayRevealMask.height = h;
        overlayRevealMaskCtx = overlayRevealMask.getContext("2d", { alpha: true });
        overlayRevealMaskCtx.clearRect(0, 0, w, h);
        overlayHasReveal = false;
        if (hadReveal && overlayCurrent) scheduleOverlayRescan();
      }
      return overlayRevealMaskCtx;
    }

    function viewportRectToShell(rect) {
      const shell = telaoShell.getBoundingClientRect();
      const sx = telaoShell.clientWidth / Math.max(1, shell.width);
      const sy = telaoShell.clientHeight / Math.max(1, shell.height);
      return {
        x: (rect.left - shell.left) * sx,
        y: (rect.top - shell.top) * sy,
        w: rect.width * sx,
        h: rect.height * sy,
      };
    }

    function getLogoBounds() {
      if (!telaoShell || !overlayArtImage || !overlayArtImage.complete || overlayArtImage.naturalWidth < 1) {
        return null;
      }
      return fitLogoInMosaicArea(
        overlayArtImage.naturalWidth,
        overlayArtImage.naturalHeight
      );
    }

    function expandRect(r, margin) {
      return {
        x: r.x - margin,
        y: r.y - margin,
        w: r.w + margin * 2,
        h: r.h + margin * 2,
      };
    }

    function rectsOverlap(a, b) {
      return !(
        a.x + a.w <= b.x
        || b.x + b.w <= a.x
        || a.y + a.h <= b.y
        || b.y + b.h <= a.y
      );
    }

    function intersectRects(a, b) {
      const x0 = Math.max(a.x, b.x);
      const y0 = Math.max(a.y, b.y);
      const x1 = Math.min(a.x + a.w, b.x + b.w);
      const y1 = Math.min(a.y + a.h, b.y + b.h);
      if (x1 <= x0 || y1 <= y0) return null;
      return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
    }

    function punchRevealHole(x, y, w, h, pad) {
      const ctx = ensureOverlayRevealMask();
      if (!ctx) return false;
      const p = pad == null ? 4 : pad;
      const x0 = Math.max(0, x - p);
      const y0 = Math.max(0, y - p);
      const x1 = Math.min(overlayRevealMask.width, x + w + p);
      const y1 = Math.min(overlayRevealMask.height, y + h + p);
      if (x1 <= x0 || y1 <= y0) return false;
      ctx.fillStyle = "rgba(255,255,255,1)";
      ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      overlayHasReveal = true;
      return true;
    }

    function resolveTileNode(node) {
      if (!node) return null;
      if (node.classList && node.classList.contains("tile")) return node;
      return node.closest ? node.closest(".tile") : null;
    }

    function elementRectInShell(el) {
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) return null;
      return viewportRectToShell(r);
    }

    /* Interseção exata: retângulo do quadradinho ∩ área do logo na tela. */
    function tileHitOnLogo(tileNode) {
      if (!overlayCurrent || !tileNode || !telaoShell) return null;
      const logo = getLogoBounds();
      if (!logo) return null;
      const tile = resolveTileNode(tileNode);
      if (!tile) return null;
      const tileRect = elementRectInShell(tile);
      if (!tileRect || !rectsOverlap(tileRect, logo)) return null;
      const hit = intersectRects(tileRect, logo);
      if (!hit || hit.w < 0.5 || hit.h < 0.5) return null;
      return hit;
    }

    function stampTileReveal(tileNode) {
      const hit = tileHitOnLogo(tileNode);
      if (!hit) return false;
      return punchRevealHole(hit.x, hit.y, hit.w, hit.h, 0);
    }

    function revealTileCellOnLogo(node) {
      const tile = resolveTileNode(node);
      if (!tile || tile.classList.contains("tile-waiting-spotlight")) return;
      if (!tileHitOnLogo(tile)) return;
      if (stampTileReveal(tile)) markOverlayDirty();
    }

    function markOverlayDirty() {
      overlayPaintDirty = true;
      redrawOverlay();
    }

    function redrawOverlayNow() {
      const layer = document.getElementById("overlayLayer");
      if (!overlayCurrent || !overlayArtImage) {
        resetOverlayReveal();
        return;
      }
      const ctx = ensureOverlayRevealPaintCtx();
      if (!ctx || !overlayRevealCanvas) return;
      const w = overlayRevealCanvas.width;
      const h = overlayRevealCanvas.height;
      if (!overlayRevealIsActive()) {
        /* Mosaico a preencher: não esconder camada já revelada até a máscara ser reposta. */
        if (!overlayLayerPinned) {
          overlayHasReveal = false;
          hideOverlayLayer();
        }
        return;
      }
      if (!overlayArtImage.complete || overlayArtImage.naturalWidth < 1) {
        return;
      }
      const tctx = ensureOverlayRevealTmp(w, h);
      if (!tctx) return;
      const fit = getLogoBounds();
      if (!fit) return;
      ctx.clearRect(0, 0, w, h);
      tctx.clearRect(0, 0, w, h);
      tctx.globalCompositeOperation = "source-over";
      tctx.globalAlpha = OVERLAY_TINT_ALPHA;
      tctx.drawImage(overlayArtImage, fit.x, fit.y, fit.w, fit.h);
      tctx.globalAlpha = 1;
      tctx.globalCompositeOperation = "destination-in";
      tctx.drawImage(overlayRevealMask, 0, 0, w, h);
      ctx.drawImage(overlayRevealTmp, 0, 0);
      if (layer) showOverlayLayerDom();
    }

    function redrawOverlay() {
      if (redrawOverlayPending) return;
      redrawOverlayPending = requestAnimationFrame(function() {
        redrawOverlayPending = 0;
        if (!overlayPaintDirty && !overlayRevealIsActive()) return;
        overlayPaintDirty = false;
        redrawOverlayNow();
      });
    }

    function redrawOverlaySync() {
      cancelRedrawOverlayPending();
      overlayPaintDirty = true;
      redrawOverlayNow();
      overlayPaintDirty = false;
    }

    function scheduleTileReveal(node, delayMs) {
      if (!node) return;
      setTimeout(function() {
        if (!node.isConnected) return;
        revealTileCellOnLogo(node);
      }, Math.max(0, delayMs || 0));
    }

    function queueTileOverlayReveal(tileNode, batchStagger) {
      const run = function() {
        if (!tileNode.isConnected) return;
        onTilePlaced(tileNode, batchStagger);
      };
      const img = tileNode.querySelector(".tile-photo");
      if (img && !img.complete) {
        img.addEventListener("load", function() {
          requestAnimationFrame(run);
        }, { once: true });
      } else {
        requestAnimationFrame(function() {
          requestAnimationFrame(run);
        });
      }
    }

    function revealExistingTilesStaggered(stepMs) {
      if (!overlayCurrent || !overlayArtImage || !overlayArtImage.complete) return;
      const step = Math.max(4, stepMs || REVEAL_TILE_STAGGER_MS);
      const tiles = [];
      for (const node of srcToNode.values()) {
        if (node.classList.contains("tile-waiting-spotlight")) continue;
        tiles.push(node);
      }
      tiles.sort(function(a, b) {
        return (Number(a.dataset.cellIndex) || 0) - (Number(b.dataset.cellIndex) || 0);
      });
      let si = 0;
      for (const node of tiles) {
        setTimeout(function() {
          revealTileCellOnLogo(node);
        }, si * step);
        si += 1;
      }
    }

    function onTilePlaced(node, batchStagger) {
      if (!node || node.classList.contains("tile-waiting-spotlight")) return;
      if (activeTileAnims > 0 || tileAnimWaitQueue.length) {
        const delay = batchStagger == null
          ? 48
          : Math.min(Math.max(0, Number(batchStagger)) * 10, 120);
        scheduleTileReveal(node, delay);
        return;
      }
      scheduleTileReveal(node, 0);
    }

    function rescanOverlayReveal() {
      if (!overlayCurrent) return;
      const ctx = ensureOverlayRevealMask();
      if (!ctx || !overlayRevealMask) return;
      ctx.clearRect(0, 0, overlayRevealMask.width, overlayRevealMask.height);
      overlayHasReveal = false;
      for (const node of srcToNode.values()) {
        if (node.classList.contains("tile-waiting-spotlight")) continue;
        stampTileReveal(node);
      }
      redrawOverlaySync();
    }

    function ensureOverlayRevealTmp(w, h) {
      if (!overlayRevealTmp || overlayRevealTmp.width !== w || overlayRevealTmp.height !== h) {
        overlayRevealTmp = document.createElement("canvas");
        overlayRevealTmp.width = w;
        overlayRevealTmp.height = h;
        overlayRevealTmpCtx = overlayRevealTmp.getContext("2d", { alpha: true });
      }
      return overlayRevealTmpCtx;
    }

    function shellPixelSize() {
      if (settings.mosaic_fullscreen) {
        return {
          w: window.innerWidth || 768,
          h: window.innerHeight || 960,
        };
      }
      return {
        w: Math.max(320, Number(settings.mosaic_width) || 768),
        h: Math.max(400, Number(settings.mosaic_height) || 960),
      };
    }

    const MOSAIC_COLS_FIXED = 20;

    function applyGridLayout() {
      if (!telaoShell || !mosaicStage || !grid) return false;
      const vw = window.innerWidth || 768;
      const vh = window.innerHeight || 960;
      layoutCols = MOSAIC_COLS_FIXED;
      const hint = Math.max(40, Math.min(80, Number(settings.tile_size_px) || 56));
      const maxTsFitWidth = Math.floor(vw / layoutCols);
      let ts = Math.min(hint, maxTsFitWidth);
      ts = Math.max(40, ts);

      if (settings.mosaic_fullscreen) {
        telaoShell.classList.add("shell-fill");
        telaoShell.style.width = vw + "px";
        telaoShell.style.height = vh + "px";
        telaoShell.style.transform = "none";
        layoutRows = Math.max(1, Math.floor(vh / ts));
      } else {
        telaoShell.classList.remove("shell-fill");
        const fw = Math.max(320, Number(settings.mosaic_width) || 768);
        const fh = Math.max(400, Number(settings.mosaic_height) || 960);
        layoutRows = Math.max(1, Number(settings.mosaic_rows) || 5);
        telaoShell.style.width = fw + "px";
        telaoShell.style.height = fh + "px";
        const scale = Math.min(vw / fw, vh / fh, 1);
        telaoShell.style.transform = "scale(" + scale + ")";
        ts = Math.max(40, Math.min(ts, Math.floor(Math.min(fw / layoutCols, fh / layoutRows))));
      }

      layoutTilePx = ts;
      const sig = layoutCols + "x" + layoutRows + "x" + ts;
      const changed = sig !== lastLayoutSig;
      if (changed) {
        lastLayoutSig = sig;
        grid.style.setProperty("--tile-size", ts + "px");
        grid.style.gridTemplateColumns = "repeat(" + layoutCols + ", " + ts + "px)";
        grid.style.gridAutoRows = ts + "px";
        const pin = overlayLayerPinned;
        overlayRevealMask = null;
        overlayRevealMaskCtx = null;
        overlayHasReveal = false;
        if (pin && overlayCurrent) scheduleOverlayRescan();
      }
      return changed;
    }

    function rebuildGridTiles() {
      if (!known.length) return;
      if (settings.duplicate_fill) {
        lastDupSig = "";
        syncQueueFromServer(known.slice());
        return;
      }
      /* Mantem pastilhas no DOM; so atualiza indices (sem clearGrid = sem "reinicio"). */
      const snap = sortImageUrls(known);
      for (let i = 0; i < snap.length; i++) {
        const key = mosaicTileKey(snap[i]);
        const node = srcToNode.get(key);
        if (node) node.dataset.cellIndex = String(i % maxGridCells());
      }
      gridCursor = snap.length;
    }

    function computeTargetSlots() {
      return Math.max(1, layoutCols * layoutRows);
    }

    function cappedTargetSlots() {
      return Math.min(computeTargetSlots(), MAX_DUP_FILL_CELLS);
    }

    function duplicateFillSignature(images, target) {
      const base = sortImageUrls(images).map(mosaicTileKey).join("\\0");
      return String(target) + "|" + base;
    }

    function findTileByCellIndex(cellIndex) {
      for (const node of srcToNode.values()) {
        if (Number(node.dataset.cellIndex) === cellIndex) return node;
      }
      return null;
    }

    function tileImgSrcKey(node) {
      const img = node && node.querySelector(".tile-photo");
      if (!img) return "";
      return mosaicTileKey(img.currentSrc || img.src || "");
    }

    function retargetTileNode(node, src) {
      const newKey = mosaicTileKey(src);
      for (const [k, n] of srcToNode.entries()) {
        if (n === node) {
          renderedSet.delete(k);
          srcToNode.delete(k);
          break;
        }
      }
      renderedSet.add(newKey);
      srcToNode.set(newKey, node);
      const img = node.querySelector(".tile-photo");
      if (img) img.src = src;
    }

    function removeTilesFromCellIndex(minIndex) {
      for (const key of Array.from(renderedSet)) {
        const node = srcToNode.get(key);
        if (!node) continue;
        if (Number(node.dataset.cellIndex) >= minIndex) {
          removeStaleTile(key);
        }
      }
    }

    function finishBulkMosaicAppend() {
      firstSyncDone = true;
      firstSyncPending = false;
      gridCursor = Math.max(gridCursor, renderedSet.size);
      if (!overlayCurrent) return;
      const deferMs = settings.duplicate_fill
        ? Math.min(480, intensityProfile().entry + 80)
        : 0;
      if (deferMs > 0) {
        setTimeout(scheduleOverlayRescan, deferMs);
      } else {
        scheduleOverlayRescan();
      }
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
        suave: { entry: 380, spotlightExit: 820 },
        medio: { entry: 520, spotlightExit: 1320 },
        forte: { entry: 680, spotlightExit: 1880 },
      };
      return map[settings.animation_intensity] || map.medio;
    }

    function entryStaggerMs(cellIndex) {
      const idx = Math.max(0, Number(cellIndex) || 0);
      return Math.min((idx % 18) * ENTRY_STAGGER_STEP_MS, ENTRY_STAGGER_MAX_MS);
    }

    function clearTileEntryClasses(img) {
      if (!img) return;
      img.classList.remove(
        "anim-soft_zoom_fade",
        "anim-hero_spotlight_pulse",
        "anim-staggered_grid_cascade",
        "anim-pure_fade_mosaic"
      );
    }

    function finishTileEntryAnimation(img, tileNode) {
      clearTileEntryClasses(img);
      if (tileNode) tileNode.classList.remove("tile-animating");
      activeTileAnims = Math.max(0, activeTileAnims - 1);
      if (tileAnimWaitQueue.length && activeTileAnims < MAX_PARALLEL_TILE_ANIMS) {
        const next = tileAnimWaitQueue.shift();
        requestAnimationFrame(next);
      }
    }

    function runTileEntryAnimation(img, cellIndex, onDone) {
      const tileNode = img.closest ? img.closest(".tile") : null;
      const mode = modeKey();
      const prof = intensityProfile();
      const bulkMode = !!settings.duplicate_fill;
      const entryMs = bulkMode
        ? Math.min(340, prof.entry)
        : prof.entry;
      const delayMs = bulkMode
        ? Math.min((Number(cellIndex) || 0) % MAX_PARALLEL_TILE_ANIMS * 40, 160)
        : entryStaggerMs(cellIndex);
      clearTileEntryClasses(img);
      if (tileNode) tileNode.classList.add("tile-animating");
      img.style.setProperty("--ease-snap", EASE_SNAP);
      img.style.setProperty("--entry-ms", entryMs + "ms");
      img.style.setProperty("--entry-delay", delayMs + "ms");
      const animClass = mode === "hero_spotlight_pulse"
        ? "anim-hero_spotlight_pulse"
        : (bulkMode ? "anim-pure_fade_mosaic" : "anim-" + mode);
      requestAnimationFrame(function() {
        img.classList.add(animClass);
      });
      if (!onDone) {
        const cleanupOnly = function() {
          finishTileEntryAnimation(img, tileNode);
        };
        img.addEventListener("animationend", cleanupOnly, { once: true });
        setTimeout(cleanupOnly, entryMs + delayMs + 60);
        return;
      }
      let settled = false;
      const done = function() {
        if (settled) return;
        settled = true;
        finishTileEntryAnimation(img, tileNode);
        onDone();
      };
      img.addEventListener("animationend", done, { once: true });
      setTimeout(done, entryMs + delayMs + 80);
    }

    function playTileEntryAnimation(img, cellIndex, onDone) {
      if (!img) {
        if (onDone) onDone();
        return;
      }
      const launch = function() {
        activeTileAnims += 1;
        runTileEntryAnimation(img, cellIndex, onDone);
      };
      if (activeTileAnims >= MAX_PARALLEL_TILE_ANIMS) {
        tileAnimWaitQueue.push(launch);
        return;
      }
      requestAnimationFrame(launch);
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

    function imageOrderKey(src) {
      if (!src) return 1e12;
      const m = mosaicTileKey(src).match(/img(\\d+)(?:\\.|$)/i);
      if (m) return parseInt(m[1], 10);
      return 1e11;
    }

    function sortImageUrls(urls) {
      return urls.slice().sort(function(a, b) {
        const ka = imageOrderKey(a);
        const kb = imageOrderKey(b);
        if (ka !== kb) return ka - kb;
        return String(a).localeCompare(String(b));
      });
    }

    function sortPendingQueue() {
      pendingQueue.sort(function(a, b) {
        return imageOrderKey(a) - imageOrderKey(b);
      });
    }

    function spotlightPipelineBusy() {
      return spotlightActive || spotlightQueue.length > 0 || Date.now() < spotlightBusyUntil;
    }

    function spotlightCycleMs() {
      const prof = intensityProfile();
      return prof.spotlightExit + 560 + 140 + spotlightGapMs();
    }

    function continueFeederAfterSpotlight() {
      if (!feederAwaitingSpotlight) return;
      feederAwaitingSpotlight = false;
      if (!pendingQueue.length) {
        feederRunning = false;
        return;
      }
      feederTimer = setTimeout(feedStep, spotlightGapMs());
    }

    function mosaicTileKey(url) {
      if (!url) return "";
      const s = String(url);
      if (settings.duplicate_fill && /[?&]fill=/.test(s)) return s;
      const q = s.indexOf("?");
      return q >= 0 ? s.slice(0, q) : s;
    }

    function spotlightSrc(url) {
      return mosaicTileKey(url);
    }

    function refreshTileImageUrls(images) {
      for (const src of images) {
        const key = mosaicTileKey(src);
        const node = srcToNode.get(key);
        if (!node) continue;
        const img = node.querySelector(".tile-photo");
        if (img && img.getAttribute("src") !== src) img.src = src;
      }
    }

    function fitSpotlightSize(naturalW, naturalH) {
      const sw = telaoShell ? telaoShell.clientWidth : window.innerWidth;
      const sh = telaoShell ? telaoShell.clientHeight : window.innerHeight;
      const maxW = Math.min(sw * 0.75, 560);
      const maxH = Math.min(sh * 0.85, 680);
      let w = Math.max(1, naturalW);
      let h = Math.max(1, naturalH);
      const scale = Math.min(1, maxW / w, maxH / h);
      w = Math.round(w * scale);
      h = Math.round(h * scale);
      spotlightImg.style.width = w + "px";
      spotlightImg.style.height = h + "px";
    }

    function spotlightGapMs() {
      return Math.max(
        SPOTLIGHT_GAP_MS_DEFAULT,
        Number(settings.spotlight_min_gap_ms) || SPOTLIGHT_GAP_MS_DEFAULT
      );
    }

    function setTileInMosaic(src) {
      const node = srcToNode.get(mosaicTileKey(src));
      if (!node) return;
      node.classList.remove("tile-waiting-spotlight");
      node.classList.add("tile-in-mosaic");
      node.dataset.deferEntryAnim = "1";
      const finish = function() {
        requestAnimationFrame(function() {
          revealTileCellOnLogo(node);
        });
      };
      startTileEntryAnimIfNeeded(node, finish);
    }

    function finishSpotlightCycle() {
      cancelOverlayRevealTrack();
      if (currentSpotlightSrc) {
        setTileInMosaic(currentSpotlightSrc);
        currentSpotlightSrc = null;
      }
      spotlightActive = false;
      spotlightTimer = null;
      spotlightExitTimer = null;
      spotlightBusyUntil = Date.now() + spotlightGapMs();
      if (overlayRevealIsActive()) redrawOverlay();
      pumpSpotlightQueue();
      continueFeederAfterSpotlight();
    }

    function revealSpotlightUI() {
      const prof = intensityProfile();
      const exitCardMs = 560;
      const settleMs = 140;
      const hideAt = prof.spotlightExit + exitCardMs + settleMs;

      spotlightActive = true;
      spotlightImg.classList.add("spotlight-ready");
      spotlight.classList.remove("exit");
      spotlight.classList.remove("enter");
      spotlight.classList.add("show");
      spotlight.classList.add("enter");
      grid.classList.add("focused");
      cancelOverlayRevealTrack();
      /* Mantém overlay já revelado visível — não limpar nem esconder no spotlight. */

      setTimeout(() => spotlight.classList.remove("enter"), 560);
      spotlightExitTimer = setTimeout(() => {
        spotlight.classList.add("exit");
        spotlightImg.classList.remove("spotlight-ready");
        grid.classList.remove("focused");
      }, prof.spotlightExit);
      spotlightTimer = setTimeout(() => {
        spotlight.classList.remove("exit");
        spotlight.classList.remove("show");
        spotlightImg.removeAttribute("src");
        spotlightImg.style.width = "0";
        spotlightImg.style.height = "0";
        spotlightImg.classList.remove("spotlight-ready");
        finishSpotlightCycle();
      }, hideAt);
    }

    function pumpSpotlightQueue() {
      if (spotlightPumpTimer) {
        clearTimeout(spotlightPumpTimer);
        spotlightPumpTimer = null;
      }
      if (!spotlightQueue.length) return;
      if (spotlightActive) return;
      const now = Date.now();
      if (now < spotlightBusyUntil) {
        spotlightPumpTimer = setTimeout(pumpSpotlightQueue, spotlightBusyUntil - now + 20);
        return;
      }
      const src = spotlightQueue.shift();
      if (src) showSpotlightNow(src);
    }

    function scheduleSpotlight(src) {
      if (!shouldShowSpotlight() || !src) return;
      spotlightQueue.push(src);
      pumpSpotlightQueue();
    }

    function showSpotlightNow(src) {
      const url = spotlightSrc(src);
      if (!url || !spotlightImg || spotlightActive) {
        if (src) spotlightQueue.unshift(src);
        return;
      }

      currentSpotlightSrc = src;
      spotlightProbe = null;
      spotlightImg.classList.remove("spotlight-ready");
      spotlightImg.style.opacity = "0";
      spotlightImg.removeAttribute("src");
      spotlightImg.style.width = "0";
      spotlightImg.style.height = "0";

      const probe = new Image();
      spotlightProbe = probe;
      probe.onload = function() {
        if (spotlightProbe !== probe) return;
        fitSpotlightSize(probe.naturalWidth, probe.naturalHeight);
        spotlightImg.src = url;
        spotlightImg.style.opacity = "1";
        revealSpotlightUI();
      };
      probe.onerror = function() {
        if (spotlightProbe !== probe) return;
        spotlightImg.src = url;
        spotlightImg.style.width = "";
        spotlightImg.style.height = "";
        spotlightImg.style.maxWidth = "min(58vw, 560px)";
        spotlightImg.style.maxHeight = "min(72vh, 680px)";
        spotlightImg.style.opacity = "1";
        revealSpotlightUI();
      };
      probe.src = url;
    }

    function showSpotlight(src) {
      scheduleSpotlight(src);
    }

    function shouldShowSpotlight() {
      const m = modeKey();
      return m === "soft_zoom_fade" || m === "hero_spotlight_pulse" || m === "staggered_grid_cascade";
    }

    function enqueueNewImages(images) {
      let added = 0;
      const ordered = sortImageUrls(images);
      for (const src of ordered) {
        const key = mosaicTileKey(src);
        if (!renderedSet.has(key) && !pendingSet.has(key)) {
          pendingQueue.push(src);
          pendingSet.add(key);
          added += 1;
        }
      }
      if (added) {
        sortPendingQueue();
        startFeederIfNeeded();
      }
      return added;
    }

    function removeStaleTile(key) {
      if (!key) return;
      pendingSet.delete(key);
      for (let i = pendingQueue.length - 1; i >= 0; i--) {
        if (mosaicTileKey(pendingQueue[i]) === key) pendingQueue.splice(i, 1);
      }
      if (!renderedSet.has(key)) return;
      renderedSet.delete(key);
      const node = srcToNode.get(key);
      if (node) {
        node.remove();
        srcToNode.delete(key);
      }
      redrawOverlay();
    }

    function pruneTilesNotInList(images) {
      const keepKeys = new Set(images.map(mosaicTileKey));
      for (let i = pendingQueue.length - 1; i >= 0; i--) {
        const qk = mosaicTileKey(pendingQueue[i]);
        if (!keepKeys.has(qk)) {
          pendingSet.delete(qk);
          pendingQueue.splice(i, 1);
        }
      }
      for (const key of Array.from(renderedSet)) {
        if (!keepKeys.has(key)) removeStaleTile(key);
      }
      if (spotlightQueue.length) {
        spotlightQueue = spotlightQueue.filter(function(s) {
          return keepKeys.has(mosaicTileKey(s));
        });
      }
      if (currentSpotlightSrc && !keepKeys.has(mosaicTileKey(currentSpotlightSrc))) {
        currentSpotlightSrc = null;
      }
      redrawOverlay();
    }

    function createTile(src, animated, lazyLoad, cellIndex, deferOverlayQueue) {
      const d = document.createElement("div");
      d.className = "tile";
      d.dataset.cellIndex = String(cellIndex);
      const img = document.createElement("img");
      img.className = "tile-photo";
      const waitSpotlight = animated && shouldShowSpotlight();
      if (waitSpotlight) {
        d.classList.add("tile-waiting-spotlight");
      } else {
        d.classList.add("tile-in-mosaic");
        if (animated) {
          d.dataset.deferEntryAnim = "1";
        } else if (!deferOverlayQueue) {
          queueTileOverlayReveal(d, 0);
        }
      }
      img.loading = lazyLoad ? "lazy" : "eager";
      img.decoding = "async";
      if ("fetchPriority" in img) img.fetchPriority = lazyLoad ? "low" : "auto";
      img.alt = "";
      img.src = src;
      img.onerror = function() {
        removeStaleTile(mosaicTileKey(src));
      };
      d.appendChild(img);
      return d;
    }

    function startTileEntryAnimIfNeeded(tileNode, onDone) {
      if (!tileNode || tileNode.dataset.deferEntryAnim !== "1") {
        if (onDone) onDone();
        return;
      }
      delete tileNode.dataset.deferEntryAnim;
      const img = tileNode.querySelector(".tile-photo");
      const cellIndex = Number(tileNode.dataset.cellIndex) || 0;
      if (!img) {
        if (onDone) onDone();
        return;
      }
      requestAnimationFrame(function() {
        if (!tileNode.isConnected) {
          if (onDone) onDone();
          return;
        }
        playTileEntryAnimation(img, cellIndex, onDone || null);
      });
    }

    function appendTileAt(src, animated, cellIndex) {
      const key = mosaicTileKey(src);
      if (renderedSet.has(key)) return;
      const d = createTile(src, animated, false, cellIndex);
      grid.appendChild(d);
      startTileEntryAnimIfNeeded(d, function() {
        onTilePlaced(d, 0);
      });
      renderedSet.add(key);
      srcToNode.set(key, d);
    }

    function appendTile(src, animated) {
      const cellIndex = gridCursor % maxGridCells();
      gridCursor += 1;
      appendTileAt(src, animated, cellIndex);
    }

    function appendTilesInstantChunk(displayList, start, lazyLoad) {
      const frag = document.createDocumentFragment();
      const pendingAnim = [];
      const end = Math.min(start + BULK_TILE_CHUNK, displayList.length);
      for (let i = start; i < end; i++) {
        const item = displayList[i];
        const src = typeof item === "string" ? item : item.src;
        const cellIndex = typeof item === "string" ? i : item.cellIndex;
        const key = mosaicTileKey(src);
        if (renderedSet.has(key)) continue;
        const existing = findTileByCellIndex(cellIndex);
        if (existing) continue;
        const d = createTile(src, true, lazyLoad, cellIndex, true);
        const img = d.querySelector(".tile-photo");
        if (img) {
          const localIdx = i - start;
          img.style.setProperty(
            "--entry-delay",
            (localIdx % MAX_PARALLEL_TILE_ANIMS) * 36 + "ms"
          );
        }
        pendingAnim.push(d);
        frag.appendChild(d);
        renderedSet.add(key);
        srcToNode.set(key, d);
      }
      grid.appendChild(frag);
      requestAnimationFrame(function() {
        for (const d of pendingAnim) {
          startTileEntryAnimIfNeeded(d, null);
        }
      });
      return end;
    }

    function appendTilesInstant(displayList, onDone) {
      bulkAppendGen += 1;
      const myGen = bulkAppendGen;
      const lazyLoad = true;
      if (!displayList.length) {
        if (typeof onDone === "function") onDone();
        return;
      }
      if (displayList.length <= BULK_TILE_CHUNK) {
        appendTilesInstantChunk(displayList, 0, lazyLoad);
        if (typeof onDone === "function") onDone();
        return;
      }
      let offset = 0;
      function step() {
        if (myGen !== bulkAppendGen) {
          firstSyncPending = false;
          return;
        }
        offset = appendTilesInstantChunk(displayList, offset, lazyLoad);
        if (offset < displayList.length) {
          setTimeout(function() {
            requestAnimationFrame(step);
          }, BULK_CHUNK_PAUSE_MS);
        } else if (typeof onDone === "function") {
          onDone();
        }
      }
      requestAnimationFrame(step);
    }

    function syncDuplicateFill(images) {
      const target = cappedTargetSlots();
      if (!images.length) {
        if (lastDupSig !== "") {
          clearGrid();
          lastDupSig = "";
        }
        return;
      }
      if (target <= 0) return;
      const display = expandToTarget(images, target);
      const sig = duplicateFillSignature(images, target);
      if (sig === lastDupSig) return;
      if (bulkAppendTimer) {
        clearTimeout(bulkAppendTimer);
        bulkAppendTimer = null;
      }
      lastDupSig = sig;
      firstSyncPending = true;

      const hadTiles = renderedSet.size > 0;
      const fullRebuild = !hadTiles
        || Math.abs(display.length - renderedSet.size) > Math.max(12, display.length * 0.35);

      if (fullRebuild) {
        clearGrid();
        lastDupSig = sig;
        appendTilesInstant(display, function() {
          finishBulkMosaicAppend();
          const last = display[display.length - 1];
          if (last && shouldShowSpotlight()) scheduleSpotlight(last);
        });
        return;
      }

      removeTilesFromCellIndex(display.length);
      const toCreate = [];
      for (let i = 0; i < display.length; i++) {
        const src = display[i];
        const key = mosaicTileKey(src);
        const node = findTileByCellIndex(i);
        if (node) {
          if (tileImgSrcKey(node) !== key) retargetTileNode(node, src);
          continue;
        }
        toCreate.push({ src: src, cellIndex: i });
      }

      if (!toCreate.length) {
        finishBulkMosaicAppend();
        return;
      }

      appendTilesInstant(toCreate, function() {
        finishBulkMosaicAppend();
      });
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
      feederAwaitingSpotlight = false;
      cycleIndex = 0;
      gridCursor = 0;
      tileAnimWaitQueue.length = 0;
      activeTileAnims = 0;
      if (overlayRevealMaskCtx && overlayRevealMask) {
        overlayRevealMaskCtx.clearRect(
          0, 0, overlayRevealMask.width, overlayRevealMask.height
        );
      }
      overlayHasReveal = false;
      /* Mantém último frame no canvas até o próximo rescan (evita sumir ao completar grelha). */
    }

    function startFeederIfNeeded() {
      if (feederRunning) return;
      if (!pendingQueue.length) return;
      feederRunning = true;
      feedStep();
    }

    function feedStep() {
      feederTimer = null;
      if (spotlightPipelineBusy()) {
        feederTimer = setTimeout(feedStep, 220);
        return;
      }
      if (activeTileAnims >= MAX_PARALLEL_TILE_ANIMS) {
        feederTimer = setTimeout(feedStep, 90);
        return;
      }
      if (!pendingQueue.length) {
        feederRunning = false;
        feederAwaitingSpotlight = false;
        return;
      }
      sortPendingQueue();
      const src = pendingQueue.shift();
      pendingSet.delete(mosaicTileKey(src));
      appendTile(src, true);
      if (shouldShowSpotlight()) {
        feederAwaitingSpotlight = true;
        scheduleSpotlight(src);
        return;
      }
      setTileInMosaic(src);
      if (!pendingQueue.length) {
        feederRunning = false;
        return;
      }
      const entryMs = intensityProfile().entry;
      const configured = Number(settings.tile_interval_ms) || 360;
      const tileMs = Math.max(
        200,
        Math.min(8000, Math.max(configured, entryMs + entryStaggerMs(gridCursor) + 100))
      );
      feederTimer = setTimeout(feedStep, tileMs);
    }

    function syncQueueFromServer(images) {
      const dup = !!settings.duplicate_fill;
      if (dup !== prevDupFill) {
        prevDupFill = dup;
        lastDupSig = "";
        clearGrid();
      }

      if (dup) {
        syncDuplicateFill(images);
        return;
      }

      lastDupSig = "";
      if (!images.length) {
        if (renderedSet.size) clearGrid();
        firstSyncDone = false;
        return;
      }
      /* Remove pastilhas/fila cujo ficheiro ja nao esta no MOSAIC (mesmo se o total de fotos nao diminuir). */
      pruneTilesNotInList(images);
      if (!firstSyncDone) {
        if (firstSyncPending) return;
        enqueueNewImages(images);
        firstSyncDone = true;
        startFeederIfNeeded();
        return;
      }
      enqueueNewImages(images);
    }

    function applyArtFromState(data) {
      const nextBg = data.background || data.backdrop || "";
      if (bgImg) {
        if (nextBg) {
          if (nextBg !== bgCurrent) {
            bgCurrent = nextBg;
            bgImg.onload = null;
            bgImg.onerror = function() {
              bgCurrent = "";
              bgImg.removeAttribute("src");
              bgImg.style.display = "none";
            };
            bgImg.src = nextBg;
          }
          bgImg.style.display = "block";
        } else {
          bgCurrent = "";
          bgImg.onload = null;
          bgImg.onerror = null;
          bgImg.removeAttribute("src");
          bgImg.style.display = "none";
        }
      }
      const nextOverlay = data.overlay || "";
      if (nextOverlay !== overlayCurrent) {
        if (nextOverlay) loadOverlayArt(nextOverlay);
        else loadOverlayArt("");
      }
    }

    function applyMosaicDelta(data) {
      const gen = Number(data.mosaic_generation) || 0;
      if (gen < lastMosaicGen) {
        clearGrid();
        firstSyncDone = false;
        lastMosaicFp = "";
        lastDeltaGen = 0;
      }

      if (data.full_sync) {
        const images = sortImageUrls(data.images || []);
        known = images;
        lastMosaicFp = images.map(mosaicTileKey).join("\\0");
        syncQueueFromServer(known);
        return;
      }

      if (data.removed && data.removed.length) {
        const removedKeys = new Set();
        for (const item of data.removed) {
          const url = item && item.url ? item.url : "";
          if (!url) continue;
          const key = mosaicTileKey(url);
          removedKeys.add(key);
          removeStaleTile(key);
        }
        if (removedKeys.size) {
          known = known.filter(function(u) {
            return !removedKeys.has(mosaicTileKey(u));
          });
        }
      }

      const addedUrls = (data.added || [])
        .map(function(e) { return e && e.url ? e.url : ""; })
        .filter(Boolean);
      if (addedUrls.length) {
        known = sortImageUrls(known.concat(addedUrls));
        lastMosaicFp = known.map(mosaicTileKey).join("\\0");
        if (settings.duplicate_fill) {
          syncQueueFromServer(known);
        } else if (!firstSyncDone) {
          if (!firstSyncPending) {
            enqueueNewImages(known);
            firstSyncDone = true;
            startFeederIfNeeded();
          }
        } else {
          enqueueNewImages(addedUrls);
        }
      } else if (
        !firstSyncDone &&
        !firstSyncPending &&
        known.length > 0 &&
        renderedSet.size === 0 &&
        !feederRunning
      ) {
        enqueueNewImages(known);
        firstSyncDone = true;
        startFeederIfNeeded();
      }
    }

    async function tick() {
      try {
        const r = await fetch(
          "/api/mosaic/delta?since=" + encodeURIComponent(String(lastDeltaGen)),
          { cache: "no-store" }
        );
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        if (data.settings) settings = Object.assign(settings, data.settings);
        const layoutChanged = applyGridLayout();
        if (layoutChanged && overlayCurrent) {
          relayoutOverlayReveal();
        }
        lastSettingsKey = [
          settings.tile_size_px,
          settings.spotlight_min_gap_ms,
          settings.duplicate_fill,
          settings.mosaic_fullscreen,
          settings.mosaic_width,
          settings.mosaic_height,
          settings.mosaic_cols,
          settings.mosaic_rows,
          settings.animation_mode,
          settings.animation_intensity,
        ].join("|");
        applyArtFromState(data);
        applyMosaicDelta(data);
        lastMosaicGen = Number(data.mosaic_generation) || 0;
        lastDeltaGen = lastMosaicGen;
      } catch (e) {
        console.error("Mosaico front tick:", e);
      }
    }

    function cycleSpotlight() {
      if (!shouldShowSpotlight()) return;
      if (feederRunning || feederAwaitingSpotlight || pendingQueue.length) return;
      if (spotlightPipelineBusy()) return;
      const list = sortImageUrls(known);
      if (!list.length) return;
      if (cycleIndex >= list.length) cycleIndex = 0;
      const src = list[cycleIndex];
      cycleIndex += 1;
      if (src) scheduleSpotlight(src);
    }

    loadOverlayArt("");
    applyGridLayout();
    tick();
    setTimeout(function() {
      if (!renderedSet.size) tick();
    }, 400);
    /* ~0,8 s: resposta mais rapida; syncQueue evita trabalho quando o estado nao muda. */
    setInterval(tick, 500);
    setInterval(cycleSpotlight, 14000);

    function relayoutOverlayReveal() {
      scheduleOverlayRescan();
    }

    window.addEventListener("resize", () => {
      const layoutChanged = applyGridLayout();
      if (layoutChanged) relayoutOverlayReveal();
      else if (overlayRevealIsActive()) redrawOverlay();
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        const changed = applyGridLayout();
        if (changed) relayoutOverlayReveal();
        else if (overlayRevealIsActive()) redrawOverlay();
        if (settings.duplicate_fill) {
          lastDupSig = "";
          lastMosaicFp = "";
          tick();
        }
      }, 280);
    });

    /* Recarregue com Ctrl+F5 apos atualizar o codigo (reload automatico desativado). */
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

    @staticmethod
    def _safe_write(wfile, body: bytes) -> bool:
        try:
            wfile.write(body)
            return True
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            return False

    def _send_json(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self._safe_write(self.wfile, data)

    def _send_bytes(self, body: bytes, content_type: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._safe_write(self.wfile, body)

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

        if path == "/api/mosaic/delta":
            qs = parse_qs(parsed.query or "")
            since_raw = (qs.get("since") or ["0"])[0]
            try:
                since = max(0, int(since_raw))
            except (TypeError, ValueError):
                since = 0
            self._send_json(self.server_ref.build_mosaic_delta(since))
            return

        if path == "/api/version":
            self._send_json({"version": _frontend_version()})
            return

        if path.startswith("/mosaic/"):
            name = path.removeprefix("/mosaic/").split("?")[0]
            file_path = (self.server_ref.mosaic_dir / name).resolve()
            mosaic_root = self.server_ref.mosaic_dir.resolve()
            if not str(file_path).startswith(str(mosaic_root)) or not file_path.is_file():
                self.send_error(404)
                return
            body, ctype = self.server_ref.read_mosaic_file_bytes(file_path)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._safe_write(self.wfile, body)
            return

        if path in ("/background", "/backdrop"):
            bg = self.server_ref.backdrop_path
            if bg is None or not bg.exists():
                self.send_error(404)
                return
            body = bg.read_bytes()
            ctype = mimetypes.guess_type(str(bg))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._safe_write(self.wfile, body)
            return

        if path == "/overlay":
            ov = self.server_ref.overlay_path
            if ov is None or not ov.exists():
                self.send_error(404)
                return
            body = ov.read_bytes()
            ctype = mimetypes.guess_type(str(ov))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._safe_write(self.wfile, body)
            return

        self.send_error(404)


class SimpleMosaicFrontend:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.mosaic_dir = _PROJECT_DIR / "MOSAIC"
        self.backdrop_path: Path | None = None
        self.overlay_path: Path | None = None

        # Configs sincronizadas com a interface principal.
        self.animation_mode: str = "soft_zoom_fade"
        self.animation_intensity: str = "medio"
        self.tile_interval_ms: int = 360
        self.tile_size_px: int = 48
        self.mosaic_fullscreen: bool = True
        self.duplicate_fill: bool = False
        self.mosaic_width: int = TELAO_LARGURA_PX
        self.mosaic_height: int = TELAO_ALTURA_PX
        self.mosaic_cols: int = TELAO_COLUNAS
        self.mosaic_rows: int = TELAO_LINHAS
        self.spotlight_min_gap_ms: int = TELAO_SPOTLIGHT_GAP_MS

        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False
        self._opened_once = False
        # Incrementado quando chega nova pastilha (injecao/monitor) para o cliente re-pollar.
        self._mosaic_generation: int = 0
        self._images_list_cache: list[str] | None = None
        self._images_list_mtime: int | None = None
        self._images_cache_gen: int = -1
        self._overlay_revision: int = 0
        self._backdrop_revision: int = 0
        self._catalog_lock = threading.Lock()
        self._snapshots_after_gen: dict[int, frozenset[str]] = {0: frozenset()}
        self._serve_cache_dir = self.mosaic_dir / ".serve_cache"

    def reset_mosaic_catalog(self) -> None:
        """Zera lista em cache apos limpar a pasta MOSAIC."""
        with self._catalog_lock:
            self._mosaic_generation = 0
            self._images_list_cache = None
            self._images_list_mtime = None
            self._images_cache_gen = -1
            self._snapshots_after_gen = {0: frozenset()}
        try:
            if self._serve_cache_dir.is_dir():
                shutil.rmtree(self._serve_cache_dir, ignore_errors=True)
        except OSError:
            pass
        self._overlay_revision = 0

    def _overlay_cache_token(self) -> str:
        if self.overlay_path is None or not self.overlay_path.exists():
            return ""
        try:
            st = self.overlay_path.stat()
            return f"{int(st.st_mtime_ns)}-{int(st.st_size)}"
        except OSError:
            return str(self.overlay_path.resolve())

    def _backdrop_cache_token(self) -> str:
        if self.backdrop_path is None or not self.backdrop_path.exists():
            return ""
        try:
            st = self.backdrop_path.stat()
            return f"{int(st.st_mtime_ns)}-{int(st.st_size)}"
        except OSError:
            return str(self.backdrop_path.resolve())

    def _backdrop_dimensions(self) -> tuple[int, int] | None:
        return self._image_dimensions(self.backdrop_path)

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
                self.tile_size_px = max(40, min(80, int(tile_size_px)))
            except (TypeError, ValueError):
                pass
        if mosaic_fullscreen is not None:
            self.mosaic_fullscreen = bool(mosaic_fullscreen)
        if duplicate_fill is not None:
            self.duplicate_fill = bool(duplicate_fill)

    def notify_mosaic_changed(self) -> None:
        """Chame apos cada nova imagem no MOSAIC para o cliente re-pollar."""
        entries = self._scan_mosaic_entries()
        ids = frozenset(e["id"] for e in entries)
        with self._catalog_lock:
            try:
                self._mosaic_generation = int(self._mosaic_generation) + 1
            except (TypeError, ValueError):
                self._mosaic_generation = 1
            self._snapshots_after_gen[int(self._mosaic_generation)] = ids
            if len(self._snapshots_after_gen) > 400:
                for g in sorted(self._snapshots_after_gen.keys())[:-250]:
                    if g > 0:
                        self._snapshots_after_gen.pop(g, None)
        self._images_list_cache = None
        self._images_list_mtime = None

    def _mosaic_order_key(self, path: Path):
        m = re.match(r"^img(\d+)$", path.stem.lower())
        if m:
            return (0, int(m.group(1)), path.name.lower())
        try:
            mt = path.stat().st_mtime_ns
        except OSError:
            mt = 0
        return (1, mt, path.name.lower())

    def _scan_mosaic_entries(self) -> list[dict]:
        gen = int(self._mosaic_generation)
        entries: list[dict] = []
        try:
            for p in sorted(self.mosaic_dir.iterdir(), key=self._mosaic_order_key):
                if not _is_image_file(p) or not p.exists():
                    continue
                if p.name.startswith("."):
                    continue
                try:
                    mt = int(p.stat().st_mtime_ns)
                except OSError:
                    mt = 0
                entries.append(
                    {
                        "id": p.name,
                        "name": p.name,
                        "order": len(entries),
                        "mtime_ns": mt,
                        "url": self._mosaic_url_for(p.name, gen, mt),
                    }
                )
        except OSError:
            entries = []
        return entries

    def _mosaic_url_for(self, name: str, gen: int, mtime_ns: int) -> str:
        return f"/mosaic/{quote(name)}?v={gen}&t={mtime_ns}"

    def _settings_payload(self) -> dict:
        return {
            "animation_mode": self.animation_mode,
            "animation_intensity": self.animation_intensity,
            "tile_interval_ms": self.tile_interval_ms,
            "tile_size_px": self.tile_size_px,
            "mosaic_fullscreen": self.mosaic_fullscreen,
            "duplicate_fill": self.duplicate_fill,
            "mosaic_width": self.mosaic_width,
            "mosaic_height": self.mosaic_height,
            "mosaic_cols": self.mosaic_cols,
            "mosaic_rows": self.mosaic_rows,
            "spotlight_min_gap_ms": self.spotlight_min_gap_ms,
        }

    def build_mosaic_delta(self, since: int) -> dict:
        since = max(0, int(since))
        entries = self._scan_mosaic_entries()
        ids_now = [e["id"] for e in entries]
        set_now = frozenset(ids_now)
        current_gen = int(self._mosaic_generation)

        with self._catalog_lock:
            ids_after_since = self._snapshots_after_gen.get(since)
            if ids_after_since is None and since > 0:
                ids_after_since = None
            elif ids_after_since is None:
                ids_after_since = frozenset()

        full_sync = bool(self.duplicate_fill) or (
            since > 0 and ids_after_since is None
        )

        if full_sync:
            urls = [e["url"] for e in entries]
            payload = self._art_payload()
            payload.update(
                {
                    "mosaic_generation": current_gen,
                    "since": since,
                    "full_sync": True,
                    "added": [],
                    "removed": [],
                    "total": len(entries),
                    "images": urls,
                    "settings": self._settings_payload(),
                }
            )
            return payload

        added_ids = [i for i in ids_now if i not in ids_after_since]
        removed_ids = sorted(i for i in ids_after_since if i not in set_now)
        added = [e for e in entries if e["id"] in added_ids]
        removed = [
            {
                "id": rid,
                "url": self._mosaic_url_for(rid, current_gen, 0),
            }
            for rid in removed_ids
        ]

        payload = self._art_payload()
        payload.update(
            {
                "mosaic_generation": current_gen,
                "since": since,
                "full_sync": False,
                "added": added,
                "removed": removed,
                "total": len(entries),
                "images": [],
                "settings": self._settings_payload(),
            }
        )
        return payload

    def _art_payload(self) -> dict:
        bg_token = self._backdrop_cache_token()
        backdrop_url = None
        if bg_token:
            backdrop_url = (
                f"/backdrop?r={int(self._backdrop_revision)}&m={quote(bg_token, safe='')}"
            )
        ov_token = self._overlay_cache_token()
        overlay_url = None
        if ov_token:
            overlay_url = (
                f"/overlay?r={int(self._overlay_revision)}&m={quote(ov_token, safe='')}"
            )
        bg_dims = self._backdrop_dimensions()
        return {
            "background": backdrop_url,
            "backdrop": backdrop_url,
            "background_width": bg_dims[0] if bg_dims else None,
            "background_height": bg_dims[1] if bg_dims else None,
            "backdrop_revision": int(self._backdrop_revision),
            "overlay": overlay_url,
            "overlay_revision": int(self._overlay_revision),
        }

    def read_mosaic_file_bytes(self, file_path: Path) -> tuple[bytes, str]:
        if not needs_mosaic_normalize(file_path):
            body = file_path.read_bytes()
            ctype = mimetypes.guess_type(str(file_path))[0] or _guess_image_mime(body)
            return body, ctype

        try:
            st = file_path.stat()
            tag = f"{int(st.st_mtime_ns)}_{int(st.st_size)}"
        except OSError:
            tag = "0"
        cache_path = self._serve_cache_dir / f"{file_path.name}.{tag}.jpg"
        if cache_path.is_file():
            return cache_path.read_bytes(), "image/jpeg"

        body, ctype = oriented_image_bytes(file_path)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(body)
        except OSError:
            pass
        return body, ctype

    def _list_mosaic_image_urls(self) -> list[str]:
        try:
            mtime_ns = int(self.mosaic_dir.stat().st_mtime_ns)
        except OSError:
            mtime_ns = -1

        if self._images_list_cache is not None:
            if getattr(self, "_images_cache_gen", -1) != self._mosaic_generation:
                pass
            elif self._images_list_mtime == mtime_ns:
                return self._images_list_cache

        images = [e["url"] for e in self._scan_mosaic_entries()]

        self._images_list_cache = images
        self._images_list_mtime = mtime_ns
        self._images_cache_gen = gen
        return images

    def _image_dimensions(self, path: Path | None) -> tuple[int, int] | None:
        if path is None or not path.exists():
            return None
        try:
            from PIL import Image

            with Image.open(path) as im:
                w, h = im.size
                return int(w), int(h)
        except Exception:
            return None

    def build_state(self) -> dict:
        payload = self._art_payload()
        payload.update(
            {
                "images": self._list_mosaic_image_urls(),
                "mosaic_generation": int(self._mosaic_generation),
                "settings": self._settings_payload(),
            }
        )
        return payload

    def set_backdrop_path(self, backdrop_path: str | None = None, background_path: str | None = None):
        path = backdrop_path or background_path
        if path:
            p = Path(path)
            self.backdrop_path = p if p.exists() else None
        else:
            self.backdrop_path = None
        self._backdrop_revision = int(self._backdrop_revision) + 1

    def set_overlay_path(self, overlay_path: str | None = None):
        if overlay_path:
            p = Path(overlay_path)
            self.overlay_path = p if p.exists() else None
        else:
            self.overlay_path = None
        self._overlay_revision = int(self._overlay_revision) + 1
        self._images_list_cache = None
        if self._is_running:
            self.notify_mosaic_changed()

    def set_art_paths(self, backdrop_path: str | None = None, overlay_path: str | None = None):
        self.set_backdrop_path(backdrop_path)
        self.set_overlay_path(overlay_path)

    def start(
        self,
        overlay_path: str | None = None,
        backdrop_path: str | None = None,
        background_path: str | None = None,
    ):
        self.set_backdrop_path(backdrop_path, background_path=background_path)
        self.set_overlay_path(overlay_path)

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

