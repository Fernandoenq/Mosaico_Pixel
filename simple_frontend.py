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
import time
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
TELAO_SPOTLIGHT_GAP_MS = 1000


HTML_PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
  <meta http-equiv="Pragma" content="no-cache" />
  <meta http-equiv="Expires" content="0" />
  <title>Mosaico Pic Brand - Front</title>
  <!-- FRONT_BUILD:__FRONT_BUILD__ -->
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
    .tile.tile-waiting-spotlight .tile-photo {
      opacity: 0;
    }
    .tile.tile-in-mosaic .tile-photo {
      opacity: 1;
    }
    .tile.tile-lock-flash .tile-photo {
      animation: tileLockFlash 200ms ease-out forwards;
    }
    @keyframes tileLockFlash {
      0% { opacity: 0.5; }
      50% { opacity: 1; }
      100% { opacity: 1; }
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
        transform: translate3d(var(--entry-from-x, 0), var(--entry-from-y, 14px), 0) scale(0.86);
      }
      65% {
        opacity: 1;
        transform: translate3d(0, -2px, 0) scale(1.02);
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
      visibility: hidden;
      line-height: 0;
      font-size: 0;
      transition: opacity 260ms cubic-bezier(0.22, 1, 0.36, 1);
    }
    .spotlight.show {
      opacity: 1;
      visibility: visible;
    }
    .spotlight.show.exit {
      opacity: 0;
      visibility: hidden;
      transition: opacity 340ms cubic-bezier(0.4, 0, 0.2, 1) 80ms;
    }
    .spotlight.fly-mode {
      display: block;
    }
    .spotlight.fly-mode #spotlightImg {
      position: absolute;
      margin: 0;
      max-width: none;
      max-height: none;
      border-radius: 0;
      animation: none !important;
      object-fit: cover;
    }
    .spotlight.enter #spotlightImg {
      animation: spotlightPopIn 640ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }
    .spotlight.exit #spotlightImg {
      animation: spotlightExit 580ms cubic-bezier(0.4, 0, 0.2, 1) forwards;
    }
    @keyframes spotlightPopIn {
      0% {
        opacity: 0;
        transform: scale(0);
      }
      68% {
        opacity: 1;
        transform: scale(1.2);
      }
      100% {
        opacity: 1;
        transform: scale(1);
      }
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
      border: 2px solid rgba(255, 255, 255, 0.9);
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
    #mosaicVideo {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      z-index: 9;
      object-fit: fill;
      display: none;
      pointer-events: none;
      background: #000;
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
    <video id="mosaicVideo" playsinline muted></video>
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
    let spotlightFlyAnim = null;
    const SPOTLIGHT_GAP_MS_DEFAULT = 1000;
    const MOSAIC_FLY_POP_MS = 640;
    const MOSAIC_FLY_HOLD_MS_DEFAULT = 1250;
    const MOSAIC_FLY_DURATION_MS = 720;
    const MOSAIC_FLY_LOCK_MS = 200;
    const EASE_MOSAIC_FLY = "cubic-bezier(0.25, 1, 0.5, 1)";

    let settings = {
      animation_mode: "mosaic_fly_in",
      animation_intensity: "medio",
      tile_interval_ms: 360,
      spotlight_min_gap_ms: 1000,
      duplicate_fill: false,
      overlay_telao_enabled: true,
      mosaic_fullscreen: true,
      tile_size_px: 38,
      mosaic_width: 768,
      mosaic_height: 960,
      mosaic_cols: 20,
      mosaic_rows: 25,
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
    let dupGradualTimer = null;
    let bulkAppendSig = "";
    let resizeTimer = null;
    let bulkAppendGen = 0;
    const ENTRY_STAGGER_COL_MS = 26;
    const ENTRY_STAGGER_ROW_MS = 38;
    const ENTRY_STAGGER_MAX_MS = 420;
    const MAX_PARALLEL_TILE_ANIMS = 1;
    const EASE_SNAP = "cubic-bezier(0.16, 1, 0.3, 1)";
    const MAX_DUP_FILL_CELLS_CAP = 520;
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
    const OVERLAY_TINT_ALPHA = 0.96;
    const TELAO_REF_W = 768;
    const TELAO_REF_H = 960;
    const MOSAIC_BAND_FRAC = 0.65;
    const BRAND_BAND_FRAC = 0.35;
    const LOGO_SHELL_WIDTH_FRAC = 1.0;
    const LOGO_BAND_HEIGHT_FRAC = 1.0;
    const REVEAL_TILE_STAGGER_MS = 10;
    let overlayRevealMask = null;
    let overlayRevealMaskCtx = null;
    let overlayRevealTmp = null;
    let overlayRevealTmpCtx = null;
    let overlayHasReveal = false;
    let overlayLayerPinned = false;
    let overlayTelaoSettingWasOn = false;
    let pendingOverlayRevealCatchup = false;
    let tileRevealGen = 0;
    let redrawOverlayPending = 0;
    let overlayRescanPending = 0;
    let overlayPaintDirty = false;
    let activeTileAnims = 0;
    const tileAnimWaitQueue = [];
    let tickBusy = false;
    let tickBackoffMs = 500;
    let tickTimer = null;
    let dupSyncTimer = null;
    let syncApplyLock = false;
    let lastCatalogFp = "";
    const health = {
      ticks: 0,
      tickErrors: 0,
      tickSkipped: 0,
      fullSyncs: 0,
      unchangedTicks: 0,
      gridClears: 0,
      overlayRescans: 0,
      dupSyncRuns: 0,
      tilesEnqueued: 0,
      startedAt: Date.now(),
    };

    function mosaicListFingerprint(urls) {
      return sortImageUrls(urls || []).map(mosaicTileKey).join("\\0");
    }

    /* Nao inclui destaque: o poll /api/mosaic/delta deve seguir com foto em voo. */
    function mosaicHeavyBusy() {
      return (
        syncApplyLock
        || firstSyncPending
        || dupGradualTimer !== null
        || activeTileAnims > 0
        || tileAnimWaitQueue.length > 0
      );
    }

    function systemBusy() {
      return mosaicHeavyBusy();
    }

    function scheduleDupSync(images) {
      if (dupSyncTimer) clearTimeout(dupSyncTimer);
      dupSyncTimer = setTimeout(function() {
        dupSyncTimer = null;
        if (mosaicHeavyBusy()) {
          scheduleDupSync(images);
          return;
        }
        const fp = mosaicListFingerprint(images);
        if (fp && fp === lastMosaicFp && renderedSet.size > 0) {
          return;
        }
        lastMosaicFp = fp;
        health.dupSyncRuns += 1;
        syncDuplicateFill(images);
      }, 220);
    }

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

    function overlayTelaoEnabled() {
      return settings.overlay_telao_enabled === true;
    }

    function maskHasRevealContent() {
      if (!overlayRevealMaskCtx || !overlayRevealMask) return false;
      const w = overlayRevealMask.width;
      const h = overlayRevealMask.height;
      if (w < 2 || h < 2) return false;
      try {
        const data = overlayRevealMaskCtx.getImageData(0, 0, w, h).data;
        const step = Math.max(4, Math.floor((w * h) / 4096));
        for (let i = 3; i < data.length; i += step * 4) {
          if (data[i] > 12) return true;
        }
      } catch (e) {
        return overlayHasReveal;
      }
      return false;
    }

    function overlayRevealIsActive() {
      return (
        overlayTelaoEnabled()
        && overlayHasReveal
        && overlayRevealMask
        && overlayRevealMaskCtx
        && maskHasRevealContent()
      );
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
      if (!overlayTelaoEnabled() || !overlayCurrent) return;
      if (overlayRescanPending) return;
      health.overlayRescans += 1;
      overlayRescanPending = requestAnimationFrame(function() {
        overlayRescanPending = requestAnimationFrame(function() {
          overlayRescanPending = 0;
          if (mosaicHeavyBusy() && activeTileAnims > 0) {
            setTimeout(scheduleOverlayRescan, 180);
            return;
          }
          rescanOverlayReveal();
        });
      });
    }

    function loadOverlayArt(url, catchupExistingTiles) {
      const next = (overlayTelaoEnabled() && url) ? url : "";
      if (next === overlayCurrent && overlayArtImage && overlayArtImage.complete) {
        if (!next) resetOverlayReveal();
        return;
      }
      overlayCurrent = next;
      resetOverlayReveal();
      if (!next) {
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
        hideOverlayLayer();
        if (catchupExistingTiles && renderedSet.size) {
          revealExistingTilesStaggered(overlayRevealStepMs(0));
        }
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

    function mosaicBandHeightPx() {
      const shellH = Math.max(1, telaoShell ? telaoShell.clientHeight : TELAO_REF_H);
      return Math.max(1, Math.floor(shellH * MOSAIC_BAND_FRAC));
    }

    function brandBandHeightPx() {
      const shellH = Math.max(1, telaoShell ? telaoShell.clientHeight : TELAO_REF_H);
      return Math.max(1, shellH - mosaicBandHeightPx());
    }

    function applyTelaoBandLayout() {
      if (!telaoShell) return;
      const mh = mosaicBandHeightPx();
      const bh = brandBandHeightPx();
      telaoShell.style.setProperty("--mosaic-band-h", mh + "px");
      telaoShell.style.setProperty("--brand-band-h", bh + "px");
      if (mosaicStage) {
        mosaicStage.style.height = mh + "px";
        mosaicStage.style.top = "0";
      }
      if (bg) {
        bg.style.height = "100%";
        bg.style.top = "0";
      }
    }

    /* Faixa superior do telao (mosaico), nao o ecrã inteiro. */
    function getMosaicCoverageRect() {
      const ts = Math.max(1, layoutTilePx || 56);
      const cols = Math.max(1, layoutCols || MOSAIC_COLS_FIXED);
      const rows = Math.max(1, layoutRows || 1);
      const shellW = Math.max(1, telaoShell ? telaoShell.clientWidth : TELAO_REF_W);
      const shellH = Math.max(1, telaoShell ? telaoShell.clientHeight : TELAO_REF_H);
      return {
        x: 0,
        y: 0,
        w: Math.min(shellW, cols * ts),
        h: Math.min(shellH, rows * ts),
      };
    }

    function logoFitScaleForShell() {
      const sw = Math.max(1, telaoShell ? telaoShell.clientWidth : TELAO_REF_W);
      const sh = Math.max(1, telaoShell ? telaoShell.clientHeight : TELAO_REF_H);
      const s = Math.min(sw / TELAO_REF_W, sh / TELAO_REF_H);
      return Math.max(1.0, Math.min(3.5, 1.2 * Math.pow(s, 0.82)));
    }

    function fitLogoInMosaicArea(nw, nh) {
      const shellW = Math.max(1, telaoShell ? telaoShell.clientWidth : TELAO_REF_W);
      const shellH = Math.max(1, telaoShell ? telaoShell.clientHeight : TELAO_REF_H);
      const scale = Math.min(shellW * 1.5 / Math.max(1, nw), shellH * 1.5 / Math.max(1, nh));
      const fw = nw * scale;
      const fh = nh * scale;
      return {
        x: (shellW - fw) / 2,
        y: (shellH - fh) / 2,
        w: fw,
        h: fh,
      };
    }

    function isBlockedBackdropUrl(url) {
      const u = String(url || "").toLowerCase();
      return (
        u.includes("fundo_evento")
        || u.includes("halo")
        || u.includes("/overlay?")
      );
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
      if (!overlayTelaoEnabled()) return;
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
      if (!overlayTelaoEnabled() || !overlayCurrent || !overlayArtImage) {
        resetOverlayReveal();
        return;
      }
      if (!renderedSet.size) {
        overlayHasReveal = false;
        hideOverlayLayer();
        return;
      }
      const ctx = ensureOverlayRevealPaintCtx();
      if (!ctx || !overlayRevealCanvas) return;
      const w = overlayRevealCanvas.width;
      const h = overlayRevealCanvas.height;
      if (!maskHasRevealContent()) {
        overlayHasReveal = false;
        hideOverlayLayer();
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

    function queueTileOverlayReveal(tileNode, cellIndex) {
      const run = function() {
        if (!tileNode.isConnected) return;
        onTilePlaced(tileNode, cellIndex);
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
      if (!overlayTelaoEnabled() || !overlayCurrent || !overlayArtImage || !overlayArtImage.complete) return;
      const step = Math.max(4, stepMs || REVEAL_TILE_STAGGER_MS);
      ensureOverlayRevealMask();
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
          if (!node.isConnected) return;
          revealTileCellOnLogo(node);
        }, si * step);
        si += 1;
      }
    }

    function onTilePlaced(node, cellIndexHint) {
      if (!node || node.classList.contains("tile-waiting-spotlight")) return;
      const cellIndex = Number(node.dataset.cellIndex) || 0;
      const hint = cellIndexHint == null ? cellIndex : Number(cellIndexHint) || 0;
      const stepDelay = overlayRevealStepMs(hint);
      if (activeTileAnims > 0 || tileAnimWaitQueue.length) {
        scheduleTileReveal(node, Math.min(stepDelay, 200));
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
      hideOverlayLayer();
      if (!renderedSet.size) return;
      revealExistingTilesStaggered(overlayRevealStepMs(0));
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

    /* 20 colunas exatas: pastilha = largura_util / 20 (telao 768 px => 38 px). */
    function telaoTilePxForWidth(widthPx) {
      return Math.max(32, Math.floor(Math.max(1, widthPx) / MOSAIC_COLS_FIXED));
    }

    function applyGridLayout() {
      if (!telaoShell || !mosaicStage || !grid) return false;
      const vw = window.innerWidth || TELAO_REF_W;
      const vh = window.innerHeight || TELAO_REF_H;
      layoutCols = MOSAIC_COLS_FIXED;

      if (settings.mosaic_fullscreen) {
        telaoShell.classList.add("shell-fill");
        telaoShell.style.width = vw + "px";
        telaoShell.style.height = vh + "px";
        telaoShell.style.transform = "none";
        layoutTilePx = telaoTilePxForWidth(vw);
        layoutRows = Math.max(1, Math.floor(vh / layoutTilePx));
      } else {
        telaoShell.classList.remove("shell-fill");
        const fw = Math.max(TELAO_REF_W, Number(settings.mosaic_width) || TELAO_REF_W);
        const fh = Math.max(TELAO_REF_H, Number(settings.mosaic_height) || TELAO_REF_H);
        telaoShell.style.width = fw + "px";
        telaoShell.style.height = fh + "px";
        const scale = Math.min(vw / fw, vh / fh, 1);
        telaoShell.style.transform = "scale(" + scale + ")";
        layoutTilePx = telaoTilePxForWidth(fw);
        layoutRows = Math.max(1, Math.floor(fh / layoutTilePx));
      }
      const ts = layoutTilePx;
      const sig = layoutCols + "x" + layoutRows + "x" + ts;
      const changed = sig !== lastLayoutSig;
      if (changed) {
        lastLayoutSig = sig;
        grid.style.setProperty("--tile-size", ts + "px");
        grid.style.gridTemplateColumns = "repeat(" + layoutCols + ", " + ts + "px)";
        grid.style.gridAutoRows = ts + "px";
        gridCursor = renderedSet.size;
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
      return Math.min(computeTargetSlots(), MAX_DUP_FILL_CELLS_CAP);
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
      /* Revelacao do overlay ja ocorreu pastilha a pastilha em appendSingleDupTile / onTilePlaced. */
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

    function dupFillPauseMs(cellIndex) {
      const configured = Number(settings.tile_interval_ms) || 320;
      const prof = intensityProfile();
      const wave = entryStaggerMs(cellIndex) * 0.35;
      return Math.max(
        80,
        Math.min(8000, Math.round(configured + wave + prof.entry * 0.08))
      );
    }

    /* Ritmo da revelacao do logo = ritmo da montagem do mosaico. */
    function overlayRevealStepMs(cellIndex) {
      const configured = Number(settings.tile_interval_ms) || 320;
      const wave = entryStaggerMs(cellIndex == null ? 0 : cellIndex) * 0.25;
      return Math.max(40, Math.min(8000, Math.round(configured * 0.85 + wave)));
    }

    function normalizeDisplayItems(displayList) {
      const out = [];
      for (let i = 0; i < displayList.length; i++) {
        const item = displayList[i];
        if (typeof item === "string") {
          out.push({ src: item, cellIndex: i });
        } else if (item && item.src) {
          out.push({ src: item.src, cellIndex: Number(item.cellIndex) || i });
        }
      }
      return out;
    }

    function gridCellFromIndex(cellIndex) {
      const idx = Math.max(0, Number(cellIndex) || 0);
      const cols = Math.max(1, layoutCols || 20);
      return { col: idx % cols, row: Math.floor(idx / cols) };
    }

    /* Onda na grelha: pastilhas organizam-se por coluna/linha (chuncks). */
    function entryStaggerMs(cellIndex) {
      const g = gridCellFromIndex(cellIndex);
      return Math.min(
        g.col * ENTRY_STAGGER_COL_MS + g.row * ENTRY_STAGGER_ROW_MS,
        ENTRY_STAGGER_MAX_MS
      );
    }

    function applyChunkEntryMotionVars(img, cellIndex) {
      if (!img) return;
      const g = gridCellFromIndex(cellIndex);
      const fromX = (g.col % 2 === 0 ? -8 : 8) + "px";
      const fromY = (12 + (g.row % 3) * 4) + "px";
      img.style.setProperty("--entry-from-x", fromX);
      img.style.setProperty("--entry-from-y", fromY);
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
      if (usesMosaicFlyIn()) {
        if (onDone) onDone();
        else finishTileEntryAnimation(img, tileNode);
        return;
      }
      const prof = intensityProfile();
      const entryMs = prof.entry;
      /* Uma animacao por vez: a onda vem da fila em ordem de celula, sem delay CSS extra. */
      const delayMs = 0;
      clearTileEntryClasses(img);
      if (tileNode) tileNode.classList.add("tile-animating");
      img.style.setProperty("--ease-snap", EASE_SNAP);
      img.style.setProperty("--entry-ms", entryMs + "ms");
      img.style.setProperty("--entry-delay", delayMs + "ms");
      applyChunkEntryMotionVars(img, cellIndex);
      requestAnimationFrame(function() {
        img.classList.add(tileEntryAnimClass());
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
      const m = String(settings.animation_mode || "mosaic_fly_in").trim().toLowerCase();
      return m || "mosaic_fly_in";
    }

    function usesMosaicFlyIn() {
      return modeKey() === "mosaic_fly_in";
    }

    function usesClassicSpotlight() {
      const m = modeKey();
      return (
        m === "staggered_grid_cascade"
        || m === "hero_spotlight_pulse"
        || m === "soft_zoom_fade"
      );
    }

    function tileEntryAnimClass() {
      const map = {
        soft_zoom_fade: "anim-soft_zoom_fade",
        hero_spotlight_pulse: "anim-hero_spotlight_pulse",
        staggered_grid_cascade: "anim-staggered_grid_cascade",
        pure_fade_mosaic: "anim-pure_fade_mosaic",
      };
      return map[modeKey()] || "anim-staggered_grid_cascade";
    }

    function mosaicFlyHoldMs() {
      const prof = intensityProfile();
      return Math.max(1000, Math.min(1500, prof.spotlightExit));
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

    function clearSpotlightTimers() {
      if (spotlightTimer) {
        clearTimeout(spotlightTimer);
        spotlightTimer = null;
      }
      if (spotlightExitTimer) {
        clearTimeout(spotlightExitTimer);
        spotlightExitTimer = null;
      }
      if (spotlightFlyAnim) {
        try {
          spotlightFlyAnim.cancel();
        } catch (e) { /* ignore */ }
        spotlightFlyAnim = null;
      }
    }

    function cancelSpotlightFlyAnim() {
      if (spotlightFlyAnim) {
        try {
          spotlightFlyAnim.cancel();
        } catch (e) { /* ignore */ }
        spotlightFlyAnim = null;
      }
      if (!spotlightImg || !spotlightImg.getAnimations) return;
      const anims = spotlightImg.getAnimations();
      for (let i = 0; i < anims.length; i++) {
        try {
          anims[i].cancel();
        } catch (e) { /* ignore */ }
      }
    }

    function resetSpotlightFlyInline() {
      if (!spotlightImg) return;
      spotlightImg.style.position = "";
      spotlightImg.style.left = "";
      spotlightImg.style.top = "";
      spotlightImg.style.margin = "";
      spotlightImg.style.maxWidth = "";
      spotlightImg.style.maxHeight = "";
      spotlightImg.style.transform = "";
      spotlightImg.style.objectFit = "";
      spotlight.classList.remove("fly-mode");
    }

    function applyHeroRectInSpotlight(rect) {
      if (!spotlightImg || !rect) return;
      spotlightImg.style.position = "absolute";
      spotlightImg.style.left = rect.x + "px";
      spotlightImg.style.top = rect.y + "px";
      spotlightImg.style.width = Math.max(1, rect.w) + "px";
      spotlightImg.style.height = Math.max(1, rect.h) + "px";
      spotlightImg.style.margin = "0";
      spotlightImg.style.maxWidth = "none";
      spotlightImg.style.maxHeight = "none";
      spotlightImg.style.transform = "none";
    }

    function lockTileAfterFly(src) {
      const node = srcToNode.get(mosaicTileKey(src));
      if (!node) return false;
      node.classList.remove("tile-waiting-spotlight");
      node.classList.add("tile-in-mosaic");
      delete node.dataset.deferEntryAnim;
      const img = node.querySelector(".tile-photo");
      if (img) {
        img.style.opacity = "";
        clearTileEntryClasses(img);
        node.classList.remove("tile-animating");
      }
      node.classList.add("tile-lock-flash");
      setTimeout(function() {
        if (node.isConnected) node.classList.remove("tile-lock-flash");
      }, MOSAIC_FLY_LOCK_MS + 40);
      requestAnimationFrame(function() {
        revealTileCellOnLogo(node);
      });
      return true;
    }

    function hideSpotlightHero() {
      if (!spotlight) return;
      cancelSpotlightFlyAnim();
      spotlight.classList.remove("show", "enter", "exit", "fly-mode");
      if (spotlightImg) {
        spotlightImg.classList.remove("spotlight-ready");
        spotlightImg.removeAttribute("src");
        spotlightImg.style.opacity = "0";
        spotlightImg.style.width = "0";
        spotlightImg.style.height = "0";
        resetSpotlightFlyInline();
      }
    }

    function beginMosaicFlyToCell() {
      const src = currentSpotlightSrc;
      if (!src || !spotlightImg) {
        finishSpotlightCycle();
        return;
      }
      const node = srcToNode.get(mosaicTileKey(src));
      const target = node ? elementRectInShell(node) : null;
      if (!node || !target) {
        hideSpotlightHero();
        finishSpotlightCycle();
        return;
      }

      cancelSpotlightFlyAnim();
      spotlight.classList.remove("enter", "exit");
      const nw = Number(spotlightImg.dataset.heroNw) || 0;
      const nh = Number(spotlightImg.dataset.heroNh) || 0;
      if (nw > 0 && nh > 0) fitSpotlightSize(nw, nh);
      void spotlightImg.offsetWidth;

      let from = elementRectInShell(spotlightImg);
      if (!from || from.w < 64 || from.h < 64) {
        if (nw > 0 && nh > 0) fitSpotlightSize(nw, nh);
        void spotlightImg.offsetWidth;
        from = elementRectInShell(spotlightImg);
      }
      if (!from) {
        hideSpotlightHero();
        finishSpotlightCycle();
        return;
      }

      spotlight.classList.add("fly-mode");
      spotlightImg.style.opacity = "1";
      applyHeroRectInSpotlight(from);
      spotlightImg.style.objectFit = "cover";

      let finished = false;
      const completeFly = function() {
        if (finished) return;
        finished = true;
        cancelSpotlightFlyAnim();
        const locked = lockTileAfterFly(src);
        hideSpotlightHero();
        finishSpotlightCycle({ locked: locked });
      };

      const keyframes = [
        {
          left: from.x + "px",
          top: from.y + "px",
          width: Math.max(1, from.w) + "px",
          height: Math.max(1, from.h) + "px",
          opacity: 1,
        },
        {
          left: target.x + "px",
          top: target.y + "px",
          width: Math.max(1, target.w) + "px",
          height: Math.max(1, target.h) + "px",
          opacity: 1,
        },
      ];

      try {
        spotlightFlyAnim = spotlightImg.animate(keyframes, {
          duration: MOSAIC_FLY_DURATION_MS,
          easing: EASE_MOSAIC_FLY,
          fill: "forwards",
        });
        spotlightFlyAnim.onfinish = completeFly;
        spotlightFlyAnim.oncancel = completeFly;
      } catch (e) {
        completeFly();
      }
      setTimeout(completeFly, MOSAIC_FLY_DURATION_MS + 150);
    }

    function revealSpotlightFlyIn() {
      clearSpotlightTimers();
      spotlightActive = true;
      const holdMs = mosaicFlyHoldMs();
      const nw = Number(spotlightImg.dataset.heroNw) || 0;
      const nh = Number(spotlightImg.dataset.heroNh) || 0;
      if (!spotlightImg.src || nw < 1 || nh < 1) {
        hideSpotlightHero();
        finishSpotlightCycle();
        return;
      }
      resetSpotlightFlyInline();
      if (nw > 0 && nh > 0) fitSpotlightSize(nw, nh);

      spotlightImg.classList.add("spotlight-ready");
      spotlightImg.style.opacity = "1";
      spotlight.classList.remove("exit", "fly-mode");
      spotlight.classList.add("show", "enter");
      grid.classList.add("focused");
      cancelOverlayRevealTrack();

      setTimeout(function() {
        spotlight.classList.remove("enter");
        if (spotlightImg) spotlightImg.style.transform = "none";
      }, MOSAIC_FLY_POP_MS);

      spotlightExitTimer = setTimeout(function() {
        grid.classList.remove("focused");
        beginMosaicFlyToCell();
      }, MOSAIC_FLY_POP_MS + holdMs);

      spotlightTimer = setTimeout(function() {
        if (spotlightActive && currentSpotlightSrc) {
          hideSpotlightHero();
          finishSpotlightCycle();
        }
      }, MOSAIC_FLY_POP_MS + holdMs + MOSAIC_FLY_DURATION_MS + MOSAIC_FLY_LOCK_MS + 600);
    }

    function revealSpotlightClassic() {
      const prof = intensityProfile();
      const exitCardMs = 560;
      const settleMs = 140;
      const hideAt = prof.spotlightExit + exitCardMs + settleMs;

      spotlightActive = true;
      spotlightImg.classList.add("spotlight-ready");
      spotlight.classList.remove("exit", "fly-mode");
      resetSpotlightFlyInline();
      spotlight.classList.add("show", "enter");
      grid.classList.add("focused");
      cancelOverlayRevealTrack();

      setTimeout(function() {
        spotlight.classList.remove("enter");
      }, 560);
      spotlightExitTimer = setTimeout(function() {
        spotlight.classList.add("exit");
        spotlightImg.classList.remove("spotlight-ready");
        grid.classList.remove("focused");
      }, prof.spotlightExit);
      spotlightTimer = setTimeout(function() {
        spotlight.classList.remove("exit", "show");
        spotlightImg.removeAttribute("src");
        spotlightImg.style.width = "0";
        spotlightImg.style.height = "0";
        spotlightImg.classList.remove("spotlight-ready");
        finishSpotlightCycle();
      }, hideAt);
    }

    function hydrateCatalogWithoutSpotlight(images) {
      const ordered = sortImageUrls(images || []);
      let cell = 0;
      for (const src of ordered) {
        const key = mosaicTileKey(src);
        if (renderedSet.has(key)) continue;
        appendTileAt(src, false, cell);
        cell += 1;
      }
      gridCursor = Math.max(gridCursor, cell);
      firstSyncDone = true;
      firstSyncPending = false;
    }

    /* Fly-in: catalogo grande = grelha instantanea; poucas fotos = fila com destaque/voo. */
    function bootstrapFlyInCatalog(images) {
      const ordered = sortImageUrls(images || []);
      if (!ordered.length) {
        firstSyncDone = true;
        firstSyncPending = false;
        return;
      }
      const FLY_IN_HYDRATE_THRESHOLD = 12;
      if (ordered.length > FLY_IN_HYDRATE_THRESHOLD) {
        hydrateCatalogWithoutSpotlight(ordered);
        return;
      }
      enqueueNewImages(ordered);
      firstSyncDone = true;
      firstSyncPending = false;
      startFeederIfNeeded();
    }

    function spotlightCycleMs() {
      if (usesMosaicFlyIn()) {
        return (
          MOSAIC_FLY_POP_MS
          + mosaicFlyHoldMs()
          + MOSAIC_FLY_DURATION_MS
          + MOSAIC_FLY_LOCK_MS
          + 120
          + spotlightGapMs()
        );
      }
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
      return url ? String(url) : "";
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
      if (!spotlightImg) return;
      const sw = telaoShell ? telaoShell.clientWidth : window.innerWidth;
      const sh = telaoShell ? telaoShell.clientHeight : window.innerHeight;
      const maxW = Math.min(sw * 0.76, 680);
      const maxH = Math.min(sh * 0.76, 780);
      let w = Math.max(1, Number(naturalW) || 1);
      let h = Math.max(1, Number(naturalH) || 1);
      const scale = Math.min(maxW / w, maxH / h);
      w = Math.max(48, Math.round(w * scale));
      h = Math.max(48, Math.round(h * scale));
      resetSpotlightFlyInline();
      spotlightImg.style.width = w + "px";
      spotlightImg.style.height = h + "px";
      spotlightImg.style.objectFit = "contain";
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
      if (usesMosaicFlyIn()) {
        lockTileAfterFly(src);
        return;
      }
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

    function finishSpotlightCycle(opts) {
      if (!spotlightActive && !(opts && opts.locked)) {
        if (currentSpotlightSrc) {
          setTileInMosaic(currentSpotlightSrc);
          currentSpotlightSrc = null;
        }
        pumpSpotlightQueue();
        continueFeederAfterSpotlight();
        return;
      }
      const alreadyLocked = opts && opts.locked;
      clearSpotlightTimers();
      cancelOverlayRevealTrack();
      spotlightActive = false;
      if (!alreadyLocked && currentSpotlightSrc) {
        setTileInMosaic(currentSpotlightSrc);
      }
      currentSpotlightSrc = null;
      spotlightBusyUntil = Date.now() + spotlightGapMs();
      if (overlayRevealIsActive()) redrawOverlay();
      pumpSpotlightQueue();
      continueFeederAfterSpotlight();
    }

    function revealSpotlightUI() {
      if (usesMosaicFlyIn()) {
        revealSpotlightFlyIn();
      } else {
        revealSpotlightClassic();
      }
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
      const key = mosaicTileKey(src);
      if (currentSpotlightSrc && mosaicTileKey(currentSpotlightSrc) === key) return;
      for (let i = 0; i < spotlightQueue.length; i++) {
        if (mosaicTileKey(spotlightQueue[i]) === key) return;
      }
      spotlightQueue.push(src);
      pumpSpotlightQueue();
    }

    function showSpotlightNow(src) {
      const url = spotlightSrc(src);
      if (!url || !spotlightImg) {
        if (src) spotlightQueue.unshift(src);
        return;
      }
      if (spotlightActive) {
        scheduleSpotlight(src);
        return;
      }

      currentSpotlightSrc = src;
      spotlightProbe = null;
      cancelSpotlightFlyAnim();
      resetSpotlightFlyInline();
      spotlightImg.classList.remove("spotlight-ready");
      spotlightImg.style.opacity = "0";
      spotlightImg.removeAttribute("src");
      spotlightImg.style.width = "0";
      spotlightImg.style.height = "0";
      delete spotlightImg.dataset.heroNw;
      delete spotlightImg.dataset.heroNh;

      const probe = new Image();
      spotlightProbe = probe;
      probe.onload = function() {
        if (spotlightProbe !== probe || currentSpotlightSrc !== src) return;
        spotlightImg.dataset.heroNw = String(probe.naturalWidth);
        spotlightImg.dataset.heroNh = String(probe.naturalHeight);
        fitSpotlightSize(probe.naturalWidth, probe.naturalHeight);
        spotlightImg.src = url;
        spotlightImg.style.opacity = "1";
        revealSpotlightUI();
      };
      probe.onerror = function() {
        if (spotlightProbe !== probe || currentSpotlightSrc !== src) return;
        spotlightImg.dataset.heroNw = "1200";
        spotlightImg.dataset.heroNh = "1600";
        fitSpotlightSize(1200, 1600);
        spotlightImg.src = url;
        spotlightImg.style.opacity = "1";
        revealSpotlightUI();
      };
      probe.src = url;
    }

    function showSpotlight(src) {
      scheduleSpotlight(src);
    }

    function shouldShowSpotlight() {
      /* Duplicar grelha: centenas de pastilhas; spotlight deixava fotos invisíveis (opacity 0). */
      if (settings.duplicate_fill) return false;
      return usesMosaicFlyIn() || usesClassicSpotlight();
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
        health.tilesEnqueued += added;
        sortPendingQueue();
        startFeederIfNeeded();
        scheduleTick(140);
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
          queueTileOverlayReveal(d, cellIndex);
        }
      }
      img.loading = lazyLoad ? "lazy" : "eager";
      img.decoding = "async";
      if ("fetchPriority" in img) img.fetchPriority = lazyLoad ? "low" : "auto";
      img.alt = "";
      let loadAttempts = 0;
      const maxLoadAttempts = 4;
      function assignTileSrc() {
        const sep = src.indexOf("?") >= 0 ? "&" : "?";
        const bust = loadAttempts > 0
          ? sep + "_r=" + loadAttempts + "&_t=" + Date.now()
          : "";
        img.src = src + bust;
      }
      img.onerror = function() {
        loadAttempts += 1;
        if (loadAttempts < maxLoadAttempts) {
          setTimeout(assignTileSrc, 120 * loadAttempts);
          return;
        }
        removeStaleTile(mosaicTileKey(src));
      };
      assignTileSrc();
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
      if (!(animated && shouldShowSpotlight())) {
        startTileEntryAnimIfNeeded(d, function() {
          onTilePlaced(d, 0);
        });
      }
      renderedSet.add(key);
      srcToNode.set(key, d);
    }

    function appendTile(src, animated) {
      const cellIndex = gridCursor % maxGridCells();
      gridCursor += 1;
      appendTileAt(src, animated, cellIndex);
    }

    function appendSingleDupTile(src, cellIndex, onDone) {
      const key = mosaicTileKey(src);
      if (renderedSet.has(key)) {
        if (typeof onDone === "function") onDone();
        return;
      }
      if (findTileByCellIndex(cellIndex)) {
        if (typeof onDone === "function") onDone();
        return;
      }
      const d = createTile(src, true, false, cellIndex, false);
      const img = d.querySelector(".tile-photo");
      if (img) {
        img.style.setProperty("--entry-delay", "0ms");
        applyChunkEntryMotionVars(img, cellIndex);
      }
      grid.appendChild(d);
      renderedSet.add(key);
      srcToNode.set(key, d);
      if (shouldShowSpotlight()) {
        scheduleSpotlight(src);
        if (typeof onDone === "function") onDone();
        return;
      }
      startTileEntryAnimIfNeeded(d, function() {
        onTilePlaced(d, 0);
        if (typeof onDone === "function") onDone();
      });
    }

    function appendTilesGradual(displayList, onDone) {
      bulkAppendGen += 1;
      const myGen = bulkAppendGen;
      const items = normalizeDisplayItems(displayList);
      if (!items.length) {
        if (typeof onDone === "function") onDone();
        return;
      }
      let idx = 0;
      function cancelGradual() {
        if (dupGradualTimer) {
          clearTimeout(dupGradualTimer);
          dupGradualTimer = null;
        }
        firstSyncPending = false;
      }
      function placeNext() {
        dupGradualTimer = null;
        if (myGen !== bulkAppendGen) {
          cancelGradual();
          return;
        }
        if (spotlightPipelineBusy()) {
          dupGradualTimer = setTimeout(placeNext, 120);
          return;
        }
        if (activeTileAnims >= MAX_PARALLEL_TILE_ANIMS || tileAnimWaitQueue.length) {
          dupGradualTimer = setTimeout(placeNext, 70);
          return;
        }
        while (idx < items.length) {
          const item = items[idx];
          const key = mosaicTileKey(item.src);
          idx += 1;
          if (renderedSet.has(key) && findTileByCellIndex(item.cellIndex)) {
            continue;
          }
          appendSingleDupTile(item.src, item.cellIndex, function() {
            if (myGen !== bulkAppendGen) return;
            if (idx >= items.length) {
              if (typeof onDone === "function") onDone();
              return;
            }
            dupGradualTimer = setTimeout(placeNext, dupFillPauseMs(item.cellIndex));
          });
          return;
        }
        if (typeof onDone === "function") onDone();
      }
      requestAnimationFrame(placeNext);
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
      if (dupGradualTimer) {
        clearTimeout(dupGradualTimer);
        dupGradualTimer = null;
      }
      lastDupSig = sig;
      firstSyncPending = true;

      const hadTiles = renderedSet.size > 0;
      const fullRebuild = !hadTiles;

      if (fullRebuild) {
        clearGrid();
        lastDupSig = sig;
        appendTilesGradual(display, function() {
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

      appendTilesGradual(toCreate, function() {
        finishBulkMosaicAppend();
      });
    }

    function clearGrid() {
      health.gridClears += 1;
      bulkAppendGen += 1;
      grid.innerHTML = "";
      renderedSet.clear();
      srcToNode.clear();
      pendingQueue.length = 0;
      pendingSet.clear();
      if (feederTimer) { clearTimeout(feederTimer); feederTimer = null; }
      if (dupGradualTimer) { clearTimeout(dupGradualTimer); dupGradualTimer = null; }
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
      const fp = mosaicListFingerprint(images);
      if (fp && fp === lastMosaicFp && !settings.duplicate_fill) {
        return;
      }
      lastMosaicFp = fp;
      const dup = !!settings.duplicate_fill;
      if (dup !== prevDupFill) {
        prevDupFill = dup;
        lastDupSig = "";
        clearGrid();
      }

      if (dup) {
        scheduleDupSync(images);
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
        if (usesMosaicFlyIn()) {
          bootstrapFlyInCatalog(images);
        } else {
          enqueueNewImages(images);
          firstSyncDone = true;
          startFeederIfNeeded();
        }
        return;
      }
      enqueueNewImages(images);
    }

    function applyArtFromState(data) {
      let nextBg = data.background || data.backdrop || "";
      if (isBlockedBackdropUrl(nextBg)) {
        nextBg = "";
      }
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
      if (!overlayTelaoEnabled()) {
        if (overlayCurrent) loadOverlayArt("");
      } else if (nextOverlay) {
        if (nextOverlay !== overlayCurrent || pendingOverlayRevealCatchup) {
          const catchup = pendingOverlayRevealCatchup;
          pendingOverlayRevealCatchup = false;
          loadOverlayArt(nextOverlay, catchup);
        }
      } else if (overlayCurrent) {
        loadOverlayArt("");
      }
    }

    function syncOverlayTelaoFromSettings() {
      const on = overlayTelaoEnabled();
      if (!on) {
        overlayTelaoSettingWasOn = false;
        if (overlayCurrent || overlayArtImage) loadOverlayArt("");
        return;
      }
      if (on && !overlayTelaoSettingWasOn) {
        pendingOverlayRevealCatchup = true;
        scheduleTick(80);
      }
      overlayTelaoSettingWasOn = on;
    }

    function applyMosaicDelta(data) {
      if (data.unchanged) {
        health.unchangedTicks += 1;
        return;
      }
      const gen = Number(data.mosaic_generation) || 0;
      if (data.catalog_fp) lastCatalogFp = data.catalog_fp;
      if (gen < lastMosaicGen) {
        clearGrid();
        firstSyncDone = false;
        lastMosaicFp = "";
        lastCatalogFp = "";
        lastDeltaGen = 0;
      }

      if (data.full_sync) {
        health.fullSyncs += 1;
        const images = sortImageUrls(data.images || []);
        known = images;
        lastMosaicFp = mosaicListFingerprint(images);
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
        lastMosaicFp = mosaicListFingerprint(known);
        if (settings.duplicate_fill) {
          syncQueueFromServer(known);
        } else if (!firstSyncDone) {
          if (!firstSyncPending) {
            if (usesMosaicFlyIn()) {
              bootstrapFlyInCatalog(known);
            } else {
              enqueueNewImages(known);
              firstSyncDone = true;
              startFeederIfNeeded();
            }
          }
        } else {
          const n = enqueueNewImages(addedUrls);
          if (n > 0) scheduleTick(160);
        }
      } else if (
        !firstSyncDone &&
        !firstSyncPending &&
        known.length > 0 &&
        renderedSet.size === 0 &&
        !feederRunning
      ) {
        if (usesMosaicFlyIn()) {
          bootstrapFlyInCatalog(known);
        } else {
          enqueueNewImages(known);
          firstSyncDone = true;
          startFeederIfNeeded();
        }
      }
    }

    async function tick() {
      if (tickBusy) return;
      tickBusy = true;
      health.ticks += 1;
      try {
        const fetchOpts = { cache: "no-store" };
        if (typeof AbortSignal !== "undefined" && AbortSignal.timeout) {
          fetchOpts.signal = AbortSignal.timeout(8000);
        }
        const r = await fetch(
          "/api/mosaic/delta?since=" + encodeURIComponent(String(lastDeltaGen)),
          fetchOpts
        );
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        if (data.unchanged) {
          health.unchangedTicks += 1;
          tickBackoffMs = 500;
          lastMosaicGen = Number(data.mosaic_generation) || lastMosaicGen;
          lastDeltaGen = lastMosaicGen;
          return;
        }
        syncApplyLock = true;
        if (data.settings) settings = Object.assign(settings, data.settings);
        syncOverlayTelaoFromSettings();
        const settingsKey = [
          settings.tile_size_px,
          settings.spotlight_min_gap_ms,
          settings.duplicate_fill,
          settings.overlay_telao_enabled,
          settings.mosaic_fullscreen,
          settings.mosaic_width,
          settings.mosaic_height,
          settings.mosaic_cols,
          settings.mosaic_rows,
          settings.animation_mode,
          settings.animation_intensity,
        ].join("|");
        const layoutChanged = applyGridLayout();
        if (layoutChanged && overlayCurrent) {
          relayoutOverlayReveal();
        }
        lastSettingsKey = settingsKey;
        applyArtFromState(data);
        applyMosaicDelta(data);
        lastMosaicGen = Number(data.mosaic_generation) || 0;
        lastDeltaGen = lastMosaicGen;
        tickBackoffMs = spotlightPipelineBusy() ? 320 : 420;
      } catch (e) {
        health.tickErrors += 1;
        tickBackoffMs = Math.min(4000, tickBackoffMs + 400);
        console.error("Mosaico front tick:", e);
      } finally {
        syncApplyLock = false;
        tickBusy = false;
      }
    }

    function scheduleTick(ms) {
      if (tickTimer) clearTimeout(tickTimer);
      tickTimer = setTimeout(function() {
        tickTimer = null;
        tick();
      }, Math.max(200, ms || tickBackoffMs));
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

    window.addEventListener("error", function(ev) {
      health.tickErrors += 1;
      console.error("Mosaico front erro:", ev.error || ev.message);
    });
    window.addEventListener("unhandledrejection", function(ev) {
      health.tickErrors += 1;
      console.error("Mosaico front promise:", ev.reason);
    });

    if (spotlight) {
      spotlight.classList.remove("show", "enter", "exit");
    }
    spotlightActive = false;
    currentSpotlightSrc = null;
    spotlightQueue.length = 0;

    loadOverlayArt("");
    applyGridLayout();
    fetch("/api/version", { cache: "no-store" })
      .then(function(r) { return r.json(); })
      .then(function(v) {
        console.log("[Mosaico telao] build", v && v.version ? v.version : "?");
      })
      .catch(function() {});
    scheduleTick(0);
    setTimeout(function() {
      if (!renderedSet.size) scheduleTick(0);
    }, 400);
    setInterval(function() {
      if (!tickBusy) scheduleTick(tickBackoffMs);
    }, 600);
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
        if (settings.duplicate_fill && !mosaicHeavyBusy()) {
          scheduleDupSync(known.slice());
        }
      }, 280);
    });

    /* --- Vídeo de entrada / saída do mosaico --- */
    const mosaicVideo = document.getElementById('mosaicVideo');
    let videoPolling = false;

    function pollVideoStatus() {
      if (videoPolling) return;
      videoPolling = true;
      fetch('/api/video/status', { cache: 'no-store' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          videoPolling = false;
          if (data.play && mosaicVideo.style.display === 'none') {
            startMosaicVideo(data.play);
          }
        })
        .catch(function() { videoPolling = false; });
    }

    function startMosaicVideo(type) {
      mosaicVideo.src = '/video/' + type + '_mosaico.mp4?_t=' + Date.now();
      mosaicVideo.style.display = 'block';
      mosaicVideo.load();
      mosaicVideo.play().catch(function() {});
      mosaicVideo.onended = function() {
        mosaicVideo.style.display = 'none';
        mosaicVideo.src = '';
        mosaicVideo.onended = null;
        fetch('/api/video/clear', { cache: 'no-store' }).catch(function() {});
      };
    }

    setInterval(pollVideoStatus, 2000);

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
            html = match.group(1)
            build = _frontend_version()
            html = html.replace("__FRONT_BUILD__", build)
            return html
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

    def _serve_video(self, file_path: Path):
        try:
            file_size = file_path.stat().st_size
        except OSError:
            self.send_error(404)
            return
        range_header = self.headers.get("Range", "")
        try:
            if range_header.startswith("bytes="):
                spec = range_header[6:]
                start_s, end_s = spec.split("-", 1)
                start = int(start_s) if start_s.strip() else 0
                end = int(end_s) if end_s.strip() else min(file_size - 1, start + 1024 * 512)
                end = min(end, file_size - 1)
                length = max(0, end - start + 1)
                self.send_response(206)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with file_path.open("rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        if not self._safe_write(self.wfile, chunk):
                            break
                        remaining -= len(chunk)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with file_path.open("rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        if not self._safe_write(self.wfile, chunk):
                            break
        except Exception:
            pass

    def do_GET(self):  # noqa: N802
        try:
            self._do_get_inner()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
        except OSError:
            return
        except Exception:
            try:
                self.send_error(500)
            except Exception:
                pass

    def _do_get_inner(self) -> None:
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

        if path == "/api/video/status":
            self._send_json(self.server_ref.build_video_status())
            return

        if path == "/api/video/clear":
            self.server_ref.clear_video_queue()
            self._send_json({"ok": True})
            return

        if path.startswith("/video/"):
            name = path.removeprefix("/video/").split("?")[0]
            if not name.endswith(".mp4") or "/" in name or ".." in name:
                self.send_error(404)
                return
            video_path = (_PROJECT_DIR / name).resolve()
            if not str(video_path).startswith(str(_PROJECT_DIR.resolve())) or not video_path.is_file():
                self.send_error(404)
                return
            self._serve_video(video_path)
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
        self.animation_mode: str = "mosaic_fly_in"
        self.animation_intensity: str = "medio"
        self.tile_interval_ms: int = 360
        self.tile_size_px: int = 38
        self.mosaic_fullscreen: bool = True
        self.duplicate_fill: bool = False
        self.overlay_telao_enabled: bool = True
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

        self._video_to_play: str | None = None
        self._video_to_play_until: float = 0.0
        self._video_intro_ready: bool = False
        self._video_outro_ready: bool = False
        self._mosaic_was_full: bool = False
        self._video_lock = threading.Lock()

    def reset_mosaic_catalog(self) -> None:
        """Zera lista em cache apos limpar a pasta MOSAIC."""
        with self._video_lock:
            if self._video_outro_ready and self._mosaic_was_full:
                self._video_to_play = "outro"
                self._video_to_play_until = time.time() + 60.0
            self._mosaic_was_full = False
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
        overlay_telao_enabled: bool | None = None,
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
        if overlay_telao_enabled is not None:
            self.overlay_telao_enabled = bool(overlay_telao_enabled)

    def notify_mosaic_changed(self) -> None:
        """Chame apos cada nova imagem no MOSAIC para o cliente re-pollar."""
        entries = self._scan_mosaic_entries()
        ids = frozenset(e["id"] for e in entries)
        with self._catalog_lock:
            try:
                self._mosaic_generation = int(self._mosaic_generation) + 1
            except (TypeError, ValueError):
                self._mosaic_generation = 1
            gen = int(self._mosaic_generation)
            self._snapshots_after_gen[gen] = ids
            if 0 not in self._snapshots_after_gen:
                self._snapshots_after_gen[0] = frozenset()
            if len(self._snapshots_after_gen) > 500:
                for g in sorted(self._snapshots_after_gen.keys())[:-320]:
                    if g > 0:
                        self._snapshots_after_gen.pop(g, None)
        self._images_list_cache = None
        self._images_list_mtime = None

        if self._video_intro_ready:
            count = len(entries)
            with self._video_lock:
                if count >= 500 and not self._mosaic_was_full:
                    self._mosaic_was_full = True
                    self._video_to_play = "intro"
                    self._video_to_play_until = time.time() + 60.0
                elif count < 500:
                    self._mosaic_was_full = False

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
            "overlay_telao_enabled": self.overlay_telao_enabled,
            "mosaic_width": self.mosaic_width,
            "mosaic_height": self.mosaic_height,
            "mosaic_cols": self.mosaic_cols,
            "mosaic_rows": self.mosaic_rows,
            "spotlight_min_gap_ms": self.spotlight_min_gap_ms,
        }

    def _snapshot_ids_at_or_before(self, since: int) -> frozenset[str] | None:
        """Estado do catálogo na geração pedida ou na anterior mais próxima."""
        with self._catalog_lock:
            if since <= 0:
                return self._snapshots_after_gen.get(0, frozenset())
            if since in self._snapshots_after_gen:
                return self._snapshots_after_gen[since]
            prior = [g for g in self._snapshots_after_gen if g < since]
            if not prior:
                return None
            return self._snapshots_after_gen[max(prior)]

    def build_mosaic_delta(self, since: int) -> dict:
        since = max(0, int(since))
        entries = self._scan_mosaic_entries()
        ids_now = [e["id"] for e in entries]
        set_now = frozenset(ids_now)
        current_gen = int(self._mosaic_generation)
        catalog_fp = "|".join(sorted(ids_now))

        ids_after_since = self._snapshot_ids_at_or_before(since)
        full_sync = ids_after_since is None or (
            self.duplicate_fill and since == 0 and current_gen > 0
        )
        if ids_after_since is None:
            ids_after_since = frozenset()

        if (
            not full_sync
            and since == current_gen
            and not any(i for i in ids_now if i not in ids_after_since)
            and not any(i for i in ids_after_since if i not in set_now)
        ):
            payload = self._art_payload()
            payload.update(
                {
                    "mosaic_generation": current_gen,
                    "since": since,
                    "unchanged": True,
                    "full_sync": False,
                    "added": [],
                    "removed": [],
                    "total": len(entries),
                    "images": [],
                    "catalog_fp": catalog_fp,
                    "settings": self._settings_payload(),
                }
            )
            return payload

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
                    "catalog_fp": catalog_fp,
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
                "catalog_fp": catalog_fp,
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

    @staticmethod
    def _reject_backdrop_path(path: Path | None) -> Path | None:
        if path is None or not path.is_file():
            return None
        stem = path.stem.lower()
        if stem.startswith("fundo_evento") or stem.startswith("fundobaixo"):
            return None
        if "halo" in stem:
            return None
        return path

    def set_backdrop_path(self, backdrop_path: str | None = None, background_path: str | None = None):
        path = backdrop_path or background_path
        if path:
            p = self._reject_backdrop_path(Path(path))
            self.backdrop_path = p
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
        open_browser: bool = True,
    ):
        self.set_backdrop_path(backdrop_path, background_path=background_path)
        self.set_overlay_path(overlay_path)

        if not self._is_running:
            handler = type("DynamicFrontendHandler", (_FrontendHandler,), {})
            handler.server_ref = self
            self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
            self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            self._thread.start()
            self._is_running = True

        if open_browser and not self._opened_once:
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

    def set_videos_ready(self, intro: bool = False, outro: bool = False) -> None:
        with self._video_lock:
            self._video_intro_ready = intro
            self._video_outro_ready = outro

    def queue_video(self, which: str) -> None:
        with self._video_lock:
            self._video_to_play = which
            self._video_to_play_until = time.time() + 60.0

    def clear_video_queue(self) -> None:
        with self._video_lock:
            self._video_to_play = None

    def build_video_status(self) -> dict:
        with self._video_lock:
            play = None
            if self._video_to_play and time.time() < self._video_to_play_until:
                play = self._video_to_play
            return {
                "play": play,
                "ready_intro": self._video_intro_ready,
                "ready_outro": self._video_outro_ready,
            }

