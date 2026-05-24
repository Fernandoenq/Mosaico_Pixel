#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera vídeos de entrada (intro) e saída (outro) do mosaico.
Resolução 768x960 (4:5) — igual ao telão P2.6.

  intro_mosaico.mp4 — tiles voam para dentro e montam o mosaico (~11s)
  outro_mosaico.mp4 — tiles voam para fora desmontando o mosaico (~8s)
"""

import re
import random
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

VIDEO_W = 768
VIDEO_H = 960
FPS = 30
TILE_SIZE = 38
COLS = VIDEO_W // TILE_SIZE        # 20  (20 * 38 = 760)
ROWS = VIDEO_H // TILE_SIZE        # 25  (25 * 38 = 950)
TOTAL_CELLS = COLS * ROWS          # 500
BG_BGR = (18, 15, 12)              # fallback if no backdrop provided
OVERLAY_TINT_ALPHA = 1.0

_PROJECT_DIR = Path(__file__).parent

INTRO_FILL_SECS = 9.0
INTRO_HOLD_SECS = 2.0
OUTRO_HOLD_SECS = 1.0
OUTRO_CLEAR_SECS = 7.0
ANIM_TILE_SECS = 0.45


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_in(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t ** 3


def _load_images(pasta: Path) -> list[np.ndarray]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif"}

    def sort_key(p: Path):
        m = re.match(r"^img(\d+)$", p.stem.lower())
        return (0, int(m.group(1))) if m else (1, p.name)

    files = sorted(
        [f for f in pasta.iterdir() if f.suffix.lower() in exts and not f.name.startswith(".")],
        key=sort_key,
    )
    tiles: list[np.ndarray] = []
    for f in files:
        try:
            img = Image.open(f).convert("RGB").resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
            tiles.append(np.asarray(img, dtype=np.uint8)[:, :, ::-1].copy())
        except Exception:
            continue
    if not tiles:
        return []
    # Repeat tiles cyclically to fill all TOTAL_CELLS slots
    return [tiles[i % len(tiles)] for i in range(TOTAL_CELLS)]


def _load_backdrop(backdrop_path: Path | None) -> np.ndarray:
    """Loads and resizes backdrop to (VIDEO_H, VIDEO_W, 3) BGR. Falls back to solid dark color."""
    if backdrop_path and backdrop_path.is_file():
        try:
            img = Image.open(backdrop_path).convert("RGB").resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
            return np.asarray(img, dtype=np.uint8)[:, :, ::-1].copy()
        except Exception:
            pass
    return np.full((VIDEO_H, VIDEO_W, 3), BG_BGR, dtype=np.uint8)


def _prep_overlay(overlay_path: Path | None) -> np.ndarray | None:
    """Retorna weight (VIDEO_H, VIDEO_W, 3) float32 para multiply blend, ou None.

    Replica exatamente o front:
      1. Logo desenhado com globalAlpha=OVERLAY_TINT_ALPHA
      2. Mascarado por destination-in (só onde há tiles)
      3. mix-blend-mode: multiply → weight[y,x] = 1 - alpha*tint*(1 - logo_bgr)
    """
    if not overlay_path or not overlay_path.is_file():
        return None
    try:
        img = Image.open(overlay_path).convert("RGBA")
        nw, nh = img.size
        scale = min(VIDEO_W * 1.5 / max(1, nw), VIDEO_H * 1.5 / max(1, nh))
        fw = max(1, int(nw * scale))
        fh = max(1, int(nh * scale))
        img = img.resize((fw, fh), Image.LANCZOS)
        arr = np.asarray(img, dtype=np.float32) / 255.0  # (fh, fw, 4) RGBA

        # neutral para multiply = 1.0 (1*frame = frame, sem efeito fora do logo)
        bgr_f = np.ones((VIDEO_H, VIDEO_W, 3), dtype=np.float32)
        alpha_f = np.zeros((VIDEO_H, VIDEO_W, 1), dtype=np.float32)

        ox = (VIDEO_W - fw) // 2
        oy = (VIDEO_H - fh) // 2
        dx0, dy0 = max(0, ox), max(0, oy)
        dx1, dy1 = min(VIDEO_W, ox + fw), min(VIDEO_H, oy + fh)
        sx0, sy0 = dx0 - ox, dy0 - oy
        sx1, sy1 = dx1 - ox, dy1 - oy

        if dx1 > dx0 and dy1 > dy0:
            ph, pw = dy1 - dy0, dx1 - dx0
            patch = arr[sy0:sy1, sx0:sx1]
            bgr_f[dy0:dy0 + ph, dx0:dx0 + pw, 0] = patch[:, :, 2]  # B
            bgr_f[dy0:dy0 + ph, dx0:dx0 + pw, 1] = patch[:, :, 1]  # G
            bgr_f[dy0:dy0 + ph, dx0:dx0 + pw, 2] = patch[:, :, 0]  # R
            alpha_f[dy0:dy0 + ph, dx0:dx0 + pw, 0] = patch[:, :, 3]

        # weight = 1 - source_alpha*(1 - logo_bgr)  →  frame*weight = multiply blend
        source_alpha = alpha_f * OVERLAY_TINT_ALPHA
        return (1.0 - source_alpha * (1.0 - bgr_f)).astype(np.float32)
    except Exception:
        return None


def _apply_overlay(frame: np.ndarray, ov_weight: np.ndarray | None, tile_mask: np.ndarray | None) -> np.ndarray:
    """Aplica multiply blend onde tile_mask > 0 — igual ao front (destination-in + multiply).

    tile_mask: (VIDEO_H, VIDEO_W, 1) float32, 1=tile presente, 0=fundo.
    """
    if ov_weight is None or tile_mask is None:
        return frame
    frame_f = frame.astype(np.float32) / 255.0
    # onde tile_mask=1 → multiply; onde tile_mask=0 → weight neutro (1) = sem efeito
    effective = 1.0 - tile_mask * (1.0 - ov_weight)
    return (frame_f * effective * 255.0).clip(0, 255).astype(np.uint8)


def _tile_center(cell_idx: int) -> tuple[int, int]:
    col = cell_idx % COLS
    row = cell_idx // COLS
    return col * TILE_SIZE + TILE_SIZE // 2, row * TILE_SIZE + TILE_SIZE // 2


def _fly_start(direction: str, tx: int, ty: int) -> tuple[float, float]:
    if direction == "left":
        return -TILE_SIZE * 0.5, float(ty)
    if direction == "right":
        return VIDEO_W + TILE_SIZE * 0.5, float(ty)
    if direction == "top":
        return float(tx), -TILE_SIZE * 0.5
    return float(tx), VIDEO_H + TILE_SIZE * 0.5  # bottom


def _draw_tile(
    frame: np.ndarray,
    tile: np.ndarray,
    cx: float,
    cy: float,
    scale: float,
    mask: np.ndarray | None = None,
):
    """Draws a tile onto frame. If mask is provided, marks covered pixels as 1.0."""
    if scale < 0.05:
        return
    if abs(scale - 1.0) < 0.02:
        s = TILE_SIZE
        x0 = int(round(cx - s / 2))
        y0 = int(round(cy - s / 2))
        fx0, fy0 = max(0, x0), max(0, y0)
        fx1, fy1 = min(VIDEO_W, x0 + s), min(VIDEO_H, y0 + s)
        if fx0 < fx1 and fy0 < fy1:
            try:
                frame[fy0:fy1, fx0:fx1] = tile[fy0 - y0: fy0 - y0 + (fy1 - fy0), fx0 - x0: fx0 - x0 + (fx1 - fx0)]
                if mask is not None:
                    mask[fy0:fy1, fx0:fx1, 0] = 1.0
            except Exception:
                pass
        return
    s = max(2, int(TILE_SIZE * scale))
    try:
        t = cv2.resize(tile, (s, s), interpolation=cv2.INTER_LINEAR)
    except Exception:
        return
    x0 = int(round(cx - s / 2))
    y0 = int(round(cy - s / 2))
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(VIDEO_W, x0 + s), min(VIDEO_H, y0 + s)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    try:
        frame[fy0:fy1, fx0:fx1] = t[fy0 - y0: fy0 - y0 + (fy1 - fy0), fx0 - x0: fx0 - x0 + (fx1 - fx0)]
        if mask is not None:
            mask[fy0:fy1, fx0:fx1, 0] = 1.0
    except Exception:
        pass


def gerar_intro(
    pasta_imagens: Path,
    output_path: Path,
    backdrop_path: Path | None = None,
    overlay_path: Path | None = None,
    callback=None,
) -> bool:
    """Gera o vídeo de entrada (mosaico se montando). Retorna True se gerado com sucesso."""
    # Usa arquivos do projeto como padrão se não fornecidos
    if backdrop_path is None:
        _d = _PROJECT_DIR / "fundo amarelo.png"
        if _d.is_file():
            backdrop_path = _d
    if overlay_path is None:
        _o = _PROJECT_DIR / "overlay.png"
        if _o.is_file():
            overlay_path = _o

    images = _load_images(pasta_imagens)
    if not images:
        return False

    ov_weight = _prep_overlay(overlay_path)
    rng = random.Random(42)
    dirs = ["left", "right", "top", "bottom"]
    tile_dirs = [rng.choice(dirs) for _ in range(TOTAL_CELLS)]

    centers = [_tile_center(ci) for ci in range(TOTAL_CELLS)]
    fly_starts = [_fly_start(tile_dirs[ci], *centers[ci]) for ci in range(TOTAL_CELLS)]
    t0s = [(ci / TOTAL_CELLS) * INTRO_FILL_SECS for ci in range(TOTAL_CELLS)]

    total_secs = INTRO_FILL_SECS + INTRO_HOLD_SECS
    total_frames = int(total_secs * FPS)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, FPS, (VIDEO_W, VIDEO_H))
    if not out.isOpened():
        return False

    bg = _load_backdrop(backdrop_path)

    # Precompute hold frame with full mosaic + overlay
    full_frame = bg.copy()
    full_mask = np.zeros((VIDEO_H, VIDEO_W, 1), dtype=np.float32)
    for ci in range(TOTAL_CELLS):
        tx, ty = centers[ci]
        _draw_tile(full_frame, images[ci], float(tx), float(ty), 1.0, mask=full_mask)
    full_frame_ov = _apply_overlay(full_frame, ov_weight, full_mask)

    for fi in range(total_frames):
        t = fi / FPS
        if t >= INTRO_FILL_SECS:
            out.write(full_frame_ov)
        else:
            frame = bg.copy()
            tile_mask = np.zeros((VIDEO_H, VIDEO_W, 1), dtype=np.float32)
            for ci in range(TOTAL_CELLS):
                t0 = t0s[ci]
                if t < t0:
                    break  # tiles are sorted by t0, remaining not started yet
                tx, ty = centers[ci]
                t1 = t0 + ANIM_TILE_SECS
                img = images[ci]
                if t >= t1:
                    _draw_tile(frame, img, float(tx), float(ty), 1.0, mask=tile_mask)
                else:
                    ep = _ease_out((t - t0) / ANIM_TILE_SECS)
                    sx, sy = fly_starts[ci]
                    _draw_tile(frame, img, sx + (tx - sx) * ep, sy + (ty - sy) * ep, max(0.1, ep), mask=tile_mask)
            out.write(_apply_overlay(frame, ov_weight, tile_mask))
        if callback:
            callback(fi, total_frames, "intro")

    out.release()
    return True


def gerar_outro(
    pasta_imagens: Path,
    output_path: Path,
    backdrop_path: Path | None = None,
    overlay_path: Path | None = None,
    callback=None,
) -> bool:
    """Gera o vídeo de saída (mosaico se desmontando). Retorna True se gerado com sucesso."""
    # Usa arquivos do projeto como padrão se não fornecidos
    if backdrop_path is None:
        _d = _PROJECT_DIR / "fundo amarelo.png"
        if _d.is_file():
            backdrop_path = _d
    if overlay_path is None:
        _o = _PROJECT_DIR / "overlay.png"
        if _o.is_file():
            overlay_path = _o

    images = _load_images(pasta_imagens)
    if not images:
        return False

    ov_weight = _prep_overlay(overlay_path)
    rng = random.Random(42)
    dirs = ["left", "right", "top", "bottom"]
    tile_dirs = [rng.choice(dirs) for _ in range(TOTAL_CELLS)]

    centers = [_tile_center(ci) for ci in range(TOTAL_CELLS)]
    fly_starts = [_fly_start(tile_dirs[ci], *centers[ci]) for ci in range(TOTAL_CELLS)]
    t0s = [OUTRO_HOLD_SECS + (ci / TOTAL_CELLS) * OUTRO_CLEAR_SECS for ci in range(TOTAL_CELLS)]

    total_secs = OUTRO_HOLD_SECS + OUTRO_CLEAR_SECS
    total_frames = int(total_secs * FPS)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, FPS, (VIDEO_W, VIDEO_H))
    if not out.isOpened():
        return False

    bg = _load_backdrop(backdrop_path)

    for fi in range(total_frames):
        t = fi / FPS
        frame = bg.copy()
        tile_mask = np.zeros((VIDEO_H, VIDEO_W, 1), dtype=np.float32)
        for ci in range(TOTAL_CELLS):
            tx, ty = centers[ci]
            t0 = t0s[ci]
            t1 = t0 + ANIM_TILE_SECS
            img = images[ci]
            if t < t0:
                _draw_tile(frame, img, float(tx), float(ty), 1.0, mask=tile_mask)
            elif t < t1:
                ep = _ease_in((t - t0) / ANIM_TILE_SECS)
                sx, sy = fly_starts[ci]
                _draw_tile(frame, img, tx + (sx - tx) * ep, ty + (sy - ty) * ep, max(0.1, 1.0 - ep * 0.9), mask=tile_mask)
            # else: tile has left — not drawn, mask stays 0
        out.write(_apply_overlay(frame, ov_weight, tile_mask))
        if callback:
            callback(fi, total_frames, "outro")

    out.release()
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pasta",    default=None)
    parser.add_argument("--backdrop", default=None)
    parser.add_argument("--overlay",  default=None)
    parser.add_argument("--out-dir",  default=None)
    args = parser.parse_args()

    pasta   = Path(args.pasta)   if args.pasta   else _PROJECT_DIR / "MOSAIC"
    backdrop = Path(args.backdrop) if args.backdrop else None
    overlay  = Path(args.overlay)  if args.overlay  else None
    out_dir  = Path(args.out_dir)  if args.out_dir  else _PROJECT_DIR

    if not pasta.is_dir():
        print("ERRO:MOSAIC_VAZIA", flush=True)
        sys.exit(1)

    def _cb(fi, ft, v):
        if fi % 5 == 0 or fi == ft - 1:
            print(f"PROGRESS:{v}:{fi}:{ft}", flush=True)

    ok = gerar_intro(pasta, out_dir / "intro_mosaico.mp4",
                     backdrop_path=backdrop, overlay_path=overlay, callback=_cb)
    print(f"DONE:intro:{'ok' if ok else 'fail'}", flush=True)

    ok = gerar_outro(pasta, out_dir / "outro_mosaico.mp4",
                     backdrop_path=backdrop, overlay_path=overlay, callback=_cb)
    print(f"DONE:outro:{'ok' if ok else 'fail'}", flush=True)
