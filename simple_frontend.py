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
from urllib.parse import quote, unquote, urlparse

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
TELAO_COLUNAS = 4
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
      object-fit: contain;
      object-position: center;
      filter: saturate(1.12) contrast(1.06) brightness(1.03);
    }
    .bg.forming-from-tiles img {
      display: none;
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
      filter: blur(2px) brightness(0.78);
      transition: filter 380ms cubic-bezier(0.22, 1, 0.36, 1);
    }
    .tile {
      position: relative;
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      margin: 0;
      padding: 0;
      box-sizing: border-box;
      border-radius: 0;
      overflow: hidden;
      background: #1a1a22;
      border: none;
    }
    .tile-bg-slice {
      position: absolute;
      inset: 0;
      z-index: 0;
      background-repeat: no-repeat;
      filter: saturate(1.12) contrast(1.06) brightness(1.03);
      opacity: 0;
      transition: opacity 0.45s ease;
    }
    .tile.has-bg-slice .tile-bg-slice {
      opacity: 1;
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
      opacity: 0.42;
      mix-blend-mode: normal;
      transition: opacity 0.55s ease;
    }
    .tile.has-bg-slice .tile-photo {
      opacity: 0.38;
    }
    .tile.tile-waiting-spotlight .tile-photo {
      opacity: 0;
    }
    .tile.tile-in-mosaic:not(.has-bg-slice) .tile-photo {
      opacity: 0.42;
    }
    .tile.tile-in-mosaic.has-bg-slice .tile-photo {
      opacity: 0.38;
    }
    .tile > .tile-photo.anim-soft_zoom_fade,
    .tile > .tile-photo.anim-hero_spotlight_pulse {
      animation: softZoomFadeIn var(--entry-ms, 420ms) cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    .tile > .tile-photo.anim-staggered_grid_cascade {
      animation: cascadeIn var(--entry-ms, 420ms) cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    .tile > .tile-photo.anim-pure_fade_mosaic {
      animation: pureFade var(--entry-ms, 420ms) ease both;
    }
    @keyframes softZoomFadeIn {
      0% { opacity: 0; }
      100% { opacity: var(--tile-photo-opacity, 0.42); }
    }
    @keyframes cascadeIn {
      0% { opacity: 0; }
      100% { opacity: var(--tile-photo-opacity, 0.42); }
    }
    @keyframes pureFade {
      0% { opacity: 0; }
      100% { opacity: var(--tile-photo-opacity, 0.42); }
    }
    .spotlight {
      position: fixed;
      inset: 0;
      z-index: 25;
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
      animation: spotlightEnter 520ms cubic-bezier(0.22, 1, 0.36, 1) forwards;
    }
    .spotlight.exit #spotlightImg {
      animation: spotlightExit 560ms cubic-bezier(0.4, 0, 0.2, 1) forwards;
    }
    @keyframes spotlightEnter {
      0% { opacity: 0; }
      100% { opacity: 1; }
    }
    @keyframes spotlightExit {
      0% { opacity: 1; }
      100% { opacity: 0; }
    }
    #spotlightImg {
      display: block;
      margin: 0;
      padding: 0;
      border: none;
      outline: none;
      width: 0;
      height: 0;
      max-width: min(58vw, 560px);
      max-height: min(72vh, 680px);
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
  </div>
  <div class="spotlight" id="spotlight">
    <img id="spotlightImg" alt="Nova imagem" />
  </div>

  <script>
    const grid = document.getElementById("grid");
    const telaoShell = document.getElementById("telaoShell");
    const mosaicStage = document.getElementById("mosaicStage");
    const bg = document.getElementById("bg");
    const bgImg = document.getElementById("bgImg");
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
      tile_size_px: 48,
      mosaic_width: 768,
      mosaic_height: 960,
      mosaic_cols: 4,
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
    const BULK_TILE_CHUNK = 40;
    let lastMosaicFp = "";
    let lastMosaicGen = 0;
    let lastBrowserFlush = 0;
    let lastSettingsKey = "";
    let layoutCols = 4;
    let layoutRows = 5;
    let layoutTilePx = 48;
    let lastLayoutSig = "";
    let gridCursor = 0;
    let bgFormingMode = false;
    let bgNaturalW = 0;
    let bgNaturalH = 0;

    function maxGridCells() {
      return Math.max(1, layoutCols * layoutRows);
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

    function containedBackgroundRect() {
      const shell = shellPixelSize();
      const w = shell.w;
      const h = shell.h;
      if (!bgNaturalW || !bgNaturalH) {
        return { dw: w, dh: h, ox: 0, oy: 0 };
      }
      const scale = Math.min(w / bgNaturalW, h / bgNaturalH);
      const dw = bgNaturalW * scale;
      const dh = bgNaturalH * scale;
      return { dw, dh, ox: (w - dw) * 0.5, oy: (h - dh) * 0.5 };
    }

    function applyBgSliceToTile(tileEl, cellIndex) {
      if (!tileEl || !bgFormingMode || !bgCurrent) return;
      const slice = tileEl.querySelector(".tile-bg-slice");
      if (!slice) return;
      const col = cellIndex % layoutCols;
      const row = Math.floor(cellIndex / layoutCols);
      const ts = layoutTilePx;
      const x = col * ts;
      const y = row * ts;
      const rect = containedBackgroundRect();
      slice.style.backgroundImage = "url(" + JSON.stringify(bgCurrent) + ")";
      slice.style.backgroundSize = rect.dw + "px " + rect.dh + "px";
      slice.style.backgroundPosition = (-(x - rect.ox)) + "px " + (-(y - rect.oy)) + "px";
      tileEl.classList.add("has-bg-slice");
    }

    function refreshAllTileBgSlices() {
      if (!bgFormingMode) return;
      for (const node of srcToNode.values()) {
        const idx = parseInt(node.dataset.cellIndex || "", 10);
        if (!isNaN(idx)) applyBgSliceToTile(node, idx);
      }
    }

    function syncBgFormingMode(hasBg) {
      bgFormingMode = !!hasBg;
      if (bg) {
        bg.classList.toggle("forming-from-tiles", bgFormingMode);
      }
      if (!bgFormingMode) {
        for (const node of srcToNode.values()) {
          node.classList.remove("has-bg-slice");
        }
      } else {
        refreshAllTileBgSlices();
      }
    }

    function updateBgMetricsFromImage() {
      if (!bgImg) return;
      if (bgImg.naturalWidth > 0) {
        bgNaturalW = bgImg.naturalWidth;
        bgNaturalH = bgImg.naturalHeight;
        refreshAllTileBgSlices();
      }
    }

    if (bgImg) {
      bgImg.addEventListener("load", updateBgMetricsFromImage);
    }

    function applyGridLayout() {
      if (!telaoShell || !mosaicStage || !grid) return false;
      const vw = window.innerWidth || 768;
      const vh = window.innerHeight || 960;
      const hint = Math.max(28, Math.min(96, Number(settings.tile_size_px) || 48));

      let ts;
      if (settings.mosaic_fullscreen) {
        telaoShell.classList.add("shell-fill");
        telaoShell.style.width = vw + "px";
        telaoShell.style.height = vh + "px";
        telaoShell.style.transform = "none";
        layoutCols = Math.max(1, Math.floor(vw / hint));
        ts = Math.max(28, Math.floor(vw / layoutCols));
        layoutRows = Math.max(1, Math.floor(vh / ts));
      } else {
        telaoShell.classList.remove("shell-fill");
        const fw = Math.max(320, Number(settings.mosaic_width) || 768);
        const fh = Math.max(400, Number(settings.mosaic_height) || 960);
        layoutCols = Math.max(1, Number(settings.mosaic_cols) || 4);
        layoutRows = Math.max(1, Number(settings.mosaic_rows) || 5);
        telaoShell.style.width = fw + "px";
        telaoShell.style.height = fh + "px";
        const scale = Math.min(vw / fw, vh / fh, 1);
        telaoShell.style.transform = "scale(" + scale + ")";
        ts = Math.max(28, Math.floor(Math.min(fw / layoutCols, fh / layoutRows)));
      }

      layoutTilePx = ts;
      const sig = layoutCols + "x" + ts;
      const changed = sig !== lastLayoutSig;
      lastLayoutSig = sig;
      grid.style.setProperty("--tile-size", ts + "px");
      grid.style.gridTemplateColumns = "repeat(" + layoutCols + ", " + ts + "px)";
      grid.style.gridAutoRows = ts + "px";
      return changed;
    }

    function rebuildGridTiles() {
      if (!known.length) return;
      if (settings.duplicate_fill) {
        lastDupSig = "";
        syncQueueFromServer(known.slice());
        return;
      }
      const snap = sortImageUrls(known);
      clearGrid();
      firstSyncDone = true;
      for (let i = 0; i < snap.length; i++) {
        appendTileAt(snap[i], false, i % maxGridCells());
      }
      gridCursor = snap.length;
    }

    function computeTargetSlots() {
      return Math.max(1, layoutCols * layoutRows);
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
      const maxW = Math.min(window.innerWidth * 0.58, 560);
      const maxH = Math.min(window.innerHeight * 0.72, 680);
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
    }

    function finishSpotlightCycle() {
      if (currentSpotlightSrc) {
        setTileInMosaic(currentSpotlightSrc);
        currentSpotlightSrc = null;
      }
      spotlightActive = false;
      spotlightTimer = null;
      spotlightExitTimer = null;
      spotlightBusyUntil = Date.now() + spotlightGapMs();
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

    function createTile(src, animated, lazyLoad, cellIndex) {
      const d = document.createElement("div");
      d.className = "tile";
      d.dataset.cellIndex = String(cellIndex);
      d.style.setProperty("--tile-photo-opacity", bgFormingMode ? "0.38" : "0.42");

      const slice = document.createElement("div");
      slice.className = "tile-bg-slice";
      slice.setAttribute("aria-hidden", "true");

      const img = document.createElement("img");
      img.className = "tile-photo";
      const waitSpotlight = animated && shouldShowSpotlight();
      if (waitSpotlight) {
        d.classList.add("tile-waiting-spotlight");
      } else {
        d.classList.add("tile-in-mosaic");
        if (animated) {
          img.classList.add("anim-" + modeKey());
          img.style.setProperty("--entry-ms", intensityProfile().entry + "ms");
        }
      }
      img.loading = lazyLoad ? "lazy" : "eager";
      img.decoding = "async";
      if ("fetchPriority" in img) img.fetchPriority = lazyLoad ? "low" : "auto";
      img.alt = "";
      img.src = src;
      img.onerror = function() {
        this.style.background = "rgba(255,80,80,0.35)";
      };
      d.appendChild(slice);
      d.appendChild(img);
      applyBgSliceToTile(d, cellIndex);
      return d;
    }

    function appendTileAt(src, animated, cellIndex) {
      const key = mosaicTileKey(src);
      if (renderedSet.has(key)) return;
      const d = createTile(src, animated, false, cellIndex);
      grid.appendChild(d);
      renderedSet.add(key);
      srcToNode.set(key, d);
    }

    function appendTile(src, animated) {
      const cellIndex = gridCursor % maxGridCells();
      gridCursor += 1;
      appendTileAt(src, animated, cellIndex);
    }

    function appendTilesInstantChunk(images, start, lazyLoad) {
      const frag = document.createDocumentFragment();
      const end = Math.min(start + BULK_TILE_CHUNK, images.length);
      for (let i = start; i < end; i++) {
        const src = images[i];
        const key = mosaicTileKey(src);
        if (renderedSet.has(key)) continue;
        const d = createTile(src, false, lazyLoad, i);
        frag.appendChild(d);
        renderedSet.add(key);
        srcToNode.set(key, d);
      }
      grid.appendChild(frag);
      if (end >= images.length) {
        gridCursor = Math.max(gridCursor, images.length);
      }
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
        if (myGen !== bulkAppendGen) {
          firstSyncPending = false;
          return;
        }
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
      feederAwaitingSpotlight = false;
      cycleIndex = 0;
      gridCursor = 0;
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
      const tileMs = Math.max(200, Math.min(8000, Number(settings.tile_interval_ms) || 360));
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
          const last = display[display.length - 1];
          if (last && shouldShowSpotlight()) scheduleSpotlight(last);
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
        const keepKeys = new Set(images.map(mosaicTileKey));
        for (let i = pendingQueue.length - 1; i >= 0; i--) {
          const q = pendingQueue[i];
          if (!keepKeys.has(mosaicTileKey(q))) {
            pendingSet.delete(mosaicTileKey(q));
            pendingQueue.splice(i, 1);
          }
        }
        for (const key of Array.from(renderedSet)) {
          if (!keepKeys.has(key)) {
            renderedSet.delete(key);
            const node = srcToNode.get(key);
            if (node) {
              node.remove();
              srcToNode.delete(key);
            }
          }
        }
      }
      if (!firstSyncDone) {
        if (firstSyncPending) return;
        firstSyncDone = true;
        enqueueNewImages(images);
        return;
      }
      enqueueNewImages(images);
    }

    async function tick() {
      try {
        const r = await fetch("/api/state", { cache: "no-store" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        const images = data.images || [];
        if (data.settings) settings = Object.assign(settings, data.settings);
        const layoutChanged = applyGridLayout();
        const gen = Number(data.mosaic_generation) || 0;
        const settingsKey = [
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
        const sorted = sortImageUrls(images);
        const listKey = sorted.map(mosaicTileKey).join("\\0");
        const fp = listKey;
        const needsSync = fp !== lastMosaicFp || settingsKey !== lastSettingsKey;
        if (needsSync) {
          lastMosaicFp = fp;
          lastSettingsKey = settingsKey;
          lastMosaicGen = gen;
          known = sorted;
          syncQueueFromServer(known);
        } else if (gen !== lastMosaicGen) {
          lastMosaicGen = gen;
          known = sorted;
          refreshTileImageUrls(known);
        } else if (layoutChanged && firstSyncDone && known.length) {
          rebuildGridTiles();
        } else if (
          images.length > 0 &&
          renderedSet.size === 0 &&
          !feederRunning &&
          !firstSyncPending
        ) {
          known = sortImageUrls(images);
          syncQueueFromServer(known);
        }
        const nextBg = data.background || "";
        const bgUrl = nextBg
          ? nextBg + (nextBg.indexOf("?") >= 0 ? "&" : "?") + "t=" + gen
          : "";
        if (typeof data.background_width === "number" && data.background_width > 0) {
          bgNaturalW = data.background_width;
        }
        if (typeof data.background_height === "number" && data.background_height > 0) {
          bgNaturalH = data.background_height;
        }
        if (bgUrl !== bgCurrent) {
          bgCurrent = bgUrl;
          syncBgFormingMode(!!bgUrl);
          if (bgImg) {
            if (bgUrl) {
              bgImg.src = bgUrl;
              bgImg.style.display = "none";
            } else {
              bgImg.removeAttribute("src");
              bgImg.style.display = "none";
              bgNaturalW = 0;
              bgNaturalH = 0;
            }
          }
        } else {
          syncBgFormingMode(!!bgCurrent);
        }
        if (bgFormingMode && bgNaturalW > 0) {
          refreshAllTileBgSlices();
        }
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

    applyGridLayout();
    tick();
    setTimeout(function() {
      if (!renderedSet.size) tick();
    }, 400);
    /* ~0,8 s: resposta mais rapida; syncQueue evita trabalho quando o estado nao muda. */
    setInterval(tick, 500);
    setInterval(cycleSpotlight, 14000);

    window.addEventListener("resize", () => {
      applyGridLayout();
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        const layoutChanged = applyGridLayout();
        if (layoutChanged && firstSyncDone && known.length) {
          rebuildGridTiles();
        } else if (layoutChanged && bgFormingMode) {
          refreshAllTileBgSlices();
        } else if (settings.duplicate_fill) {
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
            name = path.removeprefix("/mosaic/").split("?")[0]
            file_path = (self.server_ref.mosaic_dir / name).resolve()
            mosaic_root = self.server_ref.mosaic_dir.resolve()
            if not str(file_path).startswith(str(mosaic_root)) or not file_path.is_file():
                self.send_error(404)
                return
            if needs_mosaic_normalize(file_path):
                body, ctype = oriented_image_bytes(file_path)
            else:
                body = file_path.read_bytes()
                ctype = mimetypes.guess_type(str(file_path))[0] or _guess_image_mime(body)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/background":
            bg = self.server_ref.background_path
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
            self.wfile.write(body)
            return

        self.send_error(404)


class SimpleMosaicFrontend:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.mosaic_dir = _PROJECT_DIR / "MOSAIC"
        self.background_path: Path | None = None

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
    def reset_mosaic_catalog(self) -> None:
        """Zera lista em cache apos limpar a pasta MOSAIC."""
        self._mosaic_generation = 0
        self._images_list_cache = None
        self._images_list_mtime = None
        self._images_cache_gen = -1

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
                self.tile_size_px = max(28, min(96, int(tile_size_px)))
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
            try:
                mt = path.stat().st_mtime_ns
            except OSError:
                mt = 0
            return (1, mt, path.name.lower())

        gen = int(self._mosaic_generation)
        images: list[str] = []
        try:
            for p in sorted(self.mosaic_dir.iterdir(), key=_order_key):
                if _is_image_file(p):
                    images.append(f"/mosaic/{quote(p.name)}?v={gen}")
        except OSError:
            images = []

        self._images_list_cache = images
        self._images_list_mtime = mtime_ns
        self._images_cache_gen = gen
        return images

    def _background_dimensions(self) -> tuple[int, int] | None:
        if self.background_path is None or not self.background_path.exists():
            return None
        try:
            from PIL import Image

            with Image.open(self.background_path) as im:
                w, h = im.size
                return int(w), int(h)
        except Exception:
            return None

    def build_state(self) -> dict:
        images = self._list_mosaic_image_urls()
        bg_dims = self._background_dimensions()
        return {
            "images": images,
            "mosaic_generation": int(self._mosaic_generation),
            "background": "/background" if self.background_path and self.background_path.exists() else None,
            "background_width": bg_dims[0] if bg_dims else None,
            "background_height": bg_dims[1] if bg_dims else None,
            "settings": {
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

