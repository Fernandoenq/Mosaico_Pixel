#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orientacao de imagens para o mosaico.

1) EXIF Orientation (Canon, etc.) via ImageOps.exif_transpose
2) Retrato Canon sem EXIF: ficheiro 3:2 em paisagem (ex. 1920x1280, tag=1) — gira -90 graus
   (equivalente ao EXIF orientation 6, habitual em disparo vertical).
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

_EXIF_ORIENTATION = 274
# Largura/altura tipica de JPEG Canon retrato gravado "deitado" (3:2, 4:3).
_LANDSCAPE_STORED_RATIO_MIN = 1.2
_LANDSCAPE_STORED_RATIO_MAX = 1.85


def exif_orientation_tag(img: Image.Image) -> int:
    try:
        exif = img.getexif()
        if not exif:
            return 1
        return int(exif.get(_EXIF_ORIENTATION, 1) or 1)
    except Exception:
        return 1


def orient_pil(img: Image.Image) -> Image.Image:
    """Gira/espelha conforme EXIF."""
    return ImageOps.exif_transpose(img)


def is_stored_landscape_portrait(width: int, height: int) -> bool:
    """True se pixels estao em paisagem mas aspecto e de foto retrato mal gravada."""
    if width <= height:
        return False
    ratio = width / height
    return _LANDSCAPE_STORED_RATIO_MIN <= ratio <= _LANDSCAPE_STORED_RATIO_MAX


def rotate_stored_landscape_to_portrait(img: Image.Image) -> Image.Image:
    """Canon retrato sem EXIF: -90 graus (mesmo sentido que orientation 6)."""
    return img.rotate(-90, expand=True)


def normalize_for_display(img: Image.Image) -> Image.Image:
    """Pixels prontos para exibir no telao (retrato quando a camera estava na vertical)."""
    out = orient_pil(img)
    w, h = out.size
    if is_stored_landscape_portrait(w, h):
        out = rotate_stored_landscape_to_portrait(out)
    return out


def open_image_normalized(path: Path) -> Image.Image:
    with Image.open(path) as raw:
        return normalize_for_display(raw)


def needs_exif_transpose(path: Path) -> bool:
    try:
        with Image.open(path) as img:
            return exif_orientation_tag(img) not in (1,)
    except Exception:
        return False


def needs_mosaic_normalize(path: Path) -> bool:
    """True se o ficheiro precisa re-encodar para o browser (EXIF ou retrato deitado)."""
    if needs_exif_transpose(path):
        return True
    try:
        with Image.open(path) as img:
            w, h = img.size
            return is_stored_landscape_portrait(w, h)
    except Exception:
        return False


def _encode_image(img: Image.Image, path: Path) -> tuple[bytes, str]:
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    ext = path.suffix.lower()
    buf = io.BytesIO()
    if ext == ".png":
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "image/png"
    if ext == ".webp":
        img.save(buf, format="WEBP", quality=88, method=4)
        return buf.getvalue(), "image/webp"
    if ext == ".bmp":
        img.save(buf, format="BMP")
        return buf.getvalue(), "image/bmp"
    if ext == ".gif":
        img.save(buf, format="GIF", optimize=True)
        return buf.getvalue(), "image/gif"
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue(), "image/jpeg"


def oriented_image_bytes(path: Path) -> tuple[bytes, str]:
    """Re-encoda com orientacao correta para servir no browser."""
    return _encode_image(open_image_normalized(path), path)


def regravar_ficheiro_normalizado(path: Path) -> bool:
    """Grava por cima se precisar normalizar (EXIF ou retrato deitado)."""
    if not path.is_file():
        return False
    if not needs_mosaic_normalize(path):
        return False
    img = open_image_normalized(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    ext = path.suffix.lower() or ".jpg"
    tmp = path.with_suffix(path.suffix + ".orient.tmp")
    try:
        if ext == ".png":
            img.save(tmp, format="PNG", optimize=True)
        elif ext == ".webp":
            img.save(tmp, format="WEBP", quality=88, method=4)
        else:
            img.save(tmp, format="JPEG", quality=90, optimize=True)
        tmp.replace(path)
        return True
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False


def corrigir_pasta_mosaic(pasta: Path) -> int:
    """Normaliza orientacao de todas as imagens na pasta. Retorna quantas alterou."""
    if not pasta.is_dir():
        return 0
    alteradas = 0
    for f in sorted(pasta.iterdir()):
        if not f.is_file():
            continue
        if regravar_ficheiro_normalizado(f):
            alteradas += 1
    return alteradas

