#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera vídeos de entrada (intro) e saída (outro) do mosaico.
Resolução 768x960 (4:5) — igual ao telão P2.6.

Animação estilo colagem: fotos voam de fora com tamanhos variados,
rotações aleatórias e posições livres, fundo amarelo.
"""

import random
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

VIDEO_W = 768
VIDEO_H = 960
FPS = 30
OVERLAY_TINT_ALPHA = 0.96

_PROJECT_DIR = Path(__file__).parent

INTRO_FILL_SECS = 8.0
INTRO_HOLD_SECS = 2.0
OUTRO_HOLD_SECS = 1.0
OUTRO_CLEAR_SECS = 6.0
PHOTO_FLY_SECS   = 0.7   # duração do voo de cada foto até pousar


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_in(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t ** 3


def _load_images(pasta: Path) -> list[np.ndarray]:
    """Carrega todas as imagens da pasta sem redimensionar para tamanho fixo."""
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif"}
    files = sorted([f for f in pasta.iterdir()
                    if f.suffix.lower() in exts and not f.name.startswith(".")])
    imgs = []
    for f in files:
        try:
            img = Image.open(f).convert("RGB")
            imgs.append(np.asarray(img, dtype=np.uint8)[:, :, ::-1].copy())
        except Exception:
            continue
    return imgs


def _load_backdrop(backdrop_path: Path | None) -> np.ndarray:
    if backdrop_path and backdrop_path.is_file():
        try:
            img = Image.open(backdrop_path).convert("RGB").resize(
                (VIDEO_W, VIDEO_H), Image.LANCZOS)
            return np.asarray(img, dtype=np.uint8)[:, :, ::-1].copy()
        except Exception:
            pass
    return np.full((VIDEO_H, VIDEO_W, 3), (66, 198, 244), dtype=np.uint8)


def _prep_overlay(overlay_path: Path | None):
    """Retorna (bgr_canvas, alpha_canvas) float32, ou None."""
    if not overlay_path or not overlay_path.is_file():
        return None
    try:
        img = Image.open(overlay_path).convert("RGBA")
        nw, nh = img.size
        scale = min(VIDEO_W * 1.0 / max(1, nw), VIDEO_H * 1.0 / max(1, nh))
        fw = max(1, int(nw * scale))
        fh = max(1, int(nh * scale))
        img = img.resize((fw, fh), Image.LANCZOS)
        arr = np.asarray(img, dtype=np.float32) / 255.0

        bgr_f  = np.zeros((VIDEO_H, VIDEO_W, 3), dtype=np.float32)
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
            bgr_f [dy0:dy0+ph, dx0:dx0+pw, 0] = patch[:, :, 2]
            bgr_f [dy0:dy0+ph, dx0:dx0+pw, 1] = patch[:, :, 1]
            bgr_f [dy0:dy0+ph, dx0:dx0+pw, 2] = patch[:, :, 0]
            alpha_f[dy0:dy0+ph, dx0:dx0+pw, 0] = patch[:, :, 3]

        return bgr_f.astype(np.float32), alpha_f.astype(np.float32)
    except Exception:
        return None


def _apply_overlay(frame: np.ndarray, ov, alpha_blend: float = 1.0) -> np.ndarray:
    """Alpha composite do overlay sobre o frame inteiro com opacidade alpha_blend."""
    if ov is None:
        return frame
    logo_bgr, logo_alpha = ov
    frame_f = frame.astype(np.float32) / 255.0
    blend = logo_alpha * OVERLAY_TINT_ALPHA * alpha_blend
    result = frame_f * (1.0 - blend) + logo_bgr * blend
    return (result * 255.0).clip(0, 255).astype(np.uint8)


def _random_photo_size(rng: random.Random) -> int:
    """Tamanho do lado da foto (variado, como no vídeo de referência)."""
    return rng.randint(80, 260)


def _random_angle(rng: random.Random) -> float:
    """Rotação aleatória entre -20° e +20°."""
    return rng.uniform(-20, 20)


def _random_pos(rng: random.Random, size: int) -> tuple[int, int]:
    """Posição aleatória dentro do frame (centro da foto)."""
    margin = size // 2
    x = rng.randint(margin, VIDEO_W - margin)
    y = rng.randint(margin, VIDEO_H - margin)
    return x, y


def _fly_origin(rng: random.Random, tx: int, ty: int) -> tuple[float, float]:
    """Ponto de origem fora da tela para a foto voar de."""
    side = rng.randint(0, 3)
    if side == 0:   return float(rng.randint(0, VIDEO_W)), -200.0
    if side == 1:   return float(rng.randint(0, VIDEO_W)), float(VIDEO_H + 200)
    if side == 2:   return -200.0,  float(rng.randint(0, VIDEO_H))
    return float(VIDEO_W + 200), float(rng.randint(0, VIDEO_H))


def _draw_photo_rotated(frame: np.ndarray, photo: np.ndarray,
                         cx: float, cy: float, size: int, angle: float):
    """Desenha photo redimensionada e rotacionada em cx, cy."""
    if size < 4:
        return
    try:
        h_orig, w_orig = photo.shape[:2]
        # Mantém proporção, encaixa em size×size
        scale = size / max(h_orig, w_orig)
        pw = max(2, int(w_orig * scale))
        ph = max(2, int(h_orig * scale))
        resized = cv2.resize(photo, (pw, ph), interpolation=cv2.INTER_LINEAR)

        # Rotaciona
        M = cv2.getRotationMatrix2D((pw / 2, ph / 2), angle, 1.0)
        rotated = cv2.warpAffine(resized, M, (pw, ph),
                                  flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REPLICATE)

        # Cola no frame
        x0 = int(cx - pw / 2)
        y0 = int(cy - ph / 2)
        fx0, fy0 = max(0, x0), max(0, y0)
        fx1, fy1 = min(VIDEO_W, x0 + pw), min(VIDEO_H, y0 + ph)
        if fx0 >= fx1 or fy0 >= fy1:
            return
        sx0, sy0 = fx0 - x0, fy0 - y0
        frame[fy0:fy1, fx0:fx1] = rotated[sy0:sy0+(fy1-fy0), sx0:sx0+(fx1-fx0)]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Estado de cada foto na cena
# ---------------------------------------------------------------------------

class _Photo:
    def __init__(self, img, cx, cy, size, angle, ox, oy, t0):
        self.img   = img
        self.cx    = cx    # posição final
        self.cy    = cy
        self.size  = size
        self.angle = angle
        self.ox    = ox    # origem (fora da tela)
        self.oy    = oy
        self.t0    = t0    # tempo em que começa a voar

    def state_at(self, t):
        """Retorna (cx, cy, size, alpha) interpolados no tempo t."""
        elapsed = t - self.t0
        if elapsed < 0:
            return None  # ainda não começou
        p = min(1.0, elapsed / PHOTO_FLY_SECS)
        ep = _ease_out(p)
        cx = self.ox + (self.cx - self.ox) * ep
        cy = self.oy + (self.cy - self.oy) * ep
        size = max(4, int(self.size * max(0.1, ep)))
        return cx, cy, size, min(1.0, ep * 2)


def _build_photos(images: list, rng: random.Random,
                  total_secs: float, n_photos: int | None = None) -> list[_Photo]:
    """Gera lista de fotos com posições e tempos de entrada."""
    if not images:
        return []
    n = n_photos or min(len(images) * 3, 400)
    photos = []
    for i in range(n):
        img   = images[i % len(images)]
        size  = _random_photo_size(rng)
        angle = _random_angle(rng)
        cx, cy = _random_pos(rng, size)
        ox, oy = _fly_origin(rng, cx, cy)
        t0 = (i / n) * total_secs
        photos.append(_Photo(img, cx, cy, size, angle, ox, oy, t0))
    return photos


# ---------------------------------------------------------------------------
# Geração dos vídeos
# ---------------------------------------------------------------------------

def gerar_intro(pasta_imagens: Path, output_path: Path,
                backdrop_path: Path | None = None,
                overlay_path: Path | None = None,
                callback=None) -> bool:
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

    bg  = _load_backdrop(backdrop_path)
    ov  = _prep_overlay(overlay_path)
    rng = random.Random(42)

    total_secs   = INTRO_FILL_SECS + INTRO_HOLD_SECS
    total_frames = int(total_secs * FPS)
    photos = _build_photos(images, rng, INTRO_FILL_SECS)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, FPS, (VIDEO_W, VIDEO_H))
    if not out.isOpened():
        return False

    for fi in range(total_frames):
        t = fi / FPS
        frame = bg.copy()

        # overlay aparece gradualmente na fase hold
        hold_t = max(0.0, t - INTRO_FILL_SECS) / max(0.01, INTRO_HOLD_SECS)
        ov_alpha = min(1.0, hold_t * 2)

        for ph in photos:
            state = ph.state_at(t)
            if state is None:
                continue
            cx, cy, size, _ = state
            _draw_photo_rotated(frame, ph.img, cx, cy, size, ph.angle)

        if ov_alpha > 0:
            frame = _apply_overlay(frame, ov, ov_alpha)

        out.write(frame)
        if callback and (fi % 5 == 0 or fi == total_frames - 1):
            callback(fi, total_frames, "intro")

    out.release()
    return True


def gerar_outro(pasta_imagens: Path, output_path: Path,
                backdrop_path: Path | None = None,
                overlay_path: Path | None = None,
                callback=None) -> bool:
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

    bg  = _load_backdrop(backdrop_path)
    ov  = _prep_overlay(overlay_path)
    rng = random.Random(42)

    total_secs   = OUTRO_HOLD_SECS + OUTRO_CLEAR_SECS
    total_frames = int(total_secs * FPS)

    # Usa as mesmas posições do intro (seed 42) para reverter de forma consistente
    photos = _build_photos(images, rng, OUTRO_CLEAR_SECS)
    # Inverte: fotos partem das posições finais e voam para fora
    for ph in photos:
        ph.t0 = OUTRO_HOLD_SECS + ph.t0
        ph.cx, ph.ox = ph.ox, ph.cx   # troca origem/destino
        ph.cy, ph.oy = ph.oy, ph.cy

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, FPS, (VIDEO_W, VIDEO_H))
    if not out.isOpened():
        return False

    for fi in range(total_frames):
        t = fi / FPS
        frame = bg.copy()

        # overlay some durante o hold
        hold_p = min(1.0, t / max(0.01, OUTRO_HOLD_SECS))
        ov_alpha = 1.0 - min(1.0, hold_p * 1.5)

        if ov_alpha > 0:
            frame = _apply_overlay(frame, ov, ov_alpha)

        for ph in photos:
            state = ph.state_at(t)
            if state is None:
                _draw_photo_rotated(frame, ph.img, ph.ox, ph.oy,
                                     ph.size, ph.angle)
                continue
            cx, cy, size, _ = state
            _draw_photo_rotated(frame, ph.img, cx, cy, size, ph.angle)

        out.write(frame)
        if callback and (fi % 5 == 0 or fi == total_frames - 1):
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

    pasta    = Path(args.pasta)    if args.pasta    else _PROJECT_DIR / "MOSAIC"
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
