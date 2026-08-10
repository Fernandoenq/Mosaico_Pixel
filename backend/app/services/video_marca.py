"""
Exportação de vídeo no modelo da marca (referência: video/*.mp4 do projeto).

Diferente do export "fractal" de video_export.py, este reproduz o que o cliente
aprovou: fundo preto, a foto surge COLORIDA e grande no centro, voa até a célula
dela e pousa TINGIDA na cor da marca — as fotos pousadas é que vão desenhando o
logo, célula por célula, até a arte fechar.

A composição de cada frame, de baixo para cima:

    1. fundo preto
    2. fotos pousadas, tingidas na cor da marca
    3. overlay da marca (PNG com alfa) — o preto cobre o que está fora do
       desenho e os textos ficam por cima
    4. a foto que está voando, em cores originais, acima de tudo

O passo 3 é o que faz o recorte: só o que estiver sob um losango transparente
sobrevive, então as fotos pousadas aparecem exatamente na forma do logo.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def tingir(bgr: np.ndarray, cor_bgr: tuple[int, int, int]) -> np.ndarray:
    """
    Converte para luminância e recolore na cor da marca, preservando o contraste
    do rosto. Chapar a cor por cima achataria a foto numa mancha só.
    """
    cinza = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    # Clareia um pouco as altas luzes para o rosto não sumir no tom escuro.
    realce = np.clip(cinza * 0.9 + 0.12, 0, 1)
    saida = np.zeros_like(bgr, dtype=np.float32)
    for canal in range(3):
        saida[:, :, canal] = realce * cor_bgr[canal]
    return saida.astype(np.uint8)


def carregar_overlay(caminho: Path, largura: int, altura: int):
    """Devolve (rgb_bgr, alfa 0..1) do overlay já na resolução do vídeo."""
    overlay = Image.open(caminho).convert("RGBA").resize((largura, altura), Image.Resampling.LANCZOS)
    dados = np.array(overlay)
    bgr = dados[:, :, :3][:, :, ::-1].astype(np.float32)
    alfa = (dados[:, :, 3].astype(np.float32) / 255.0)[:, :, None]
    return bgr, alfa


def celulas_da_marca(alfa: np.ndarray, rows: int, cols: int, offx: float, offy: float,
                     gw: float, gh: float) -> list[tuple[int, int, float]]:
    """
    Células cujo ladrilho toca uma janela do overlay, com a fração coberta.
    Só essas recebem foto: as de fora ficariam escondidas atrás do preto.
    """
    janela = (alfa[:, :, 0] == 0)
    H, W = janela.shape
    tw, th = gw / cols, gh / rows

    encontradas = []
    for r in range(rows):
        y0, y1 = int(round(offy + r * th)), int(round(offy + (r + 1) * th))
        if y1 <= 0 or y0 >= H:
            continue
        for c in range(cols):
            x0, x1 = int(round(offx + c * tw)), int(round(offx + (c + 1) * tw))
            if x1 <= 0 or x0 >= W:
                continue
            bloco = janela[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]
            if bloco.size and bloco.any():
                encontradas.append((r, c, float(bloco.mean())))
    return encontradas


def gerar_video_marca(
    saida: Path,
    fotos: list[Path],
    overlay_path: Path,
    config: dict,
    *,
    largura: int = 1152,
    altura: int = 688,
    fps: int = 30,
    intervalo_entre_fotos: float = 0.12,
    hold_central: float = 0.5,
    duracao_voo: float = 0.6,
    segundos_finais: float = 3.0,
    cor_marca: tuple[int, int, int] = (28, 28, 226),  # BGR do vermelho HSBC
    progresso: Callable[[int], None] | None = None,
) -> dict:
    if not fotos:
        raise ValueError("Nenhuma foto disponível para o vídeo.")
    if not overlay_path.exists():
        raise ValueError(f"Overlay da marca não encontrado: {overlay_path}")

    overlay_bgr, alfa = carregar_overlay(overlay_path, largura, altura)

    # A grade do painel é descrita na resolução do telão; reescala para o vídeo.
    escala_x = largura / float(config.get("screenWidth", largura))
    escala_y = altura / float(config.get("screenHeight", altura))
    rows = int(config.get("rows", 38))
    cols = int(config.get("cols", 62))
    offx = float(config.get("gridOffsetX", 0)) * escala_x
    offy = float(config.get("gridOffsetY", 0)) * escala_y
    gw = float(config.get("gridWidth", config.get("screenWidth", largura))) * escala_x
    gh = float(config.get("gridHeight", config.get("screenHeight", altura))) * escala_y
    tw, th = gw / cols, gh / rows

    alvos = celulas_da_marca(alfa, rows, cols, offx, offy, gw, gh)
    if not alvos:
        raise ValueError("Nenhuma célula da grade cai dentro do desenho da marca.")

    # Preenche do centro para fora: o logo "cresce" em vez de aparecer em faixas.
    cx_grade, cy_grade = cols / 2, rows / 2
    alvos.sort(key=lambda a: math.hypot(a[1] - cx_grade, a[0] - cy_grade))

    # Recorte quadrado de cada foto, no tamanho do ladrilho, já tingido.
    lado_tile = (max(1, int(round(tw))), max(1, int(round(th))))
    cache_tile: list[np.ndarray] = []
    cache_grande: list[np.ndarray] = []
    lado_central = int(min(largura, altura) * 0.42)

    for caminho in fotos:
        img = cv2.imread(str(caminho))
        if img is None:
            continue
        lado = min(img.shape[:2])
        y0 = (img.shape[0] - lado) // 2
        x0 = (img.shape[1] - lado) // 2
        quadrado = img[y0:y0 + lado, x0:x0 + lado]
        cache_tile.append(tingir(cv2.resize(quadrado, lado_tile, interpolation=cv2.INTER_AREA), cor_marca))
        cache_grande.append(cv2.resize(quadrado, (lado_central, lado_central), interpolation=cv2.INTER_AREA))

    if not cache_tile:
        raise ValueError("Nenhuma das fotos pôde ser lida.")

    total_secs = len(alvos) * intervalo_entre_fotos + hold_central + duracao_voo + segundos_finais
    total_frames = int(total_secs * fps)

    saida.parent.mkdir(parents=True, exist_ok=True)
    escritor = cv2.VideoWriter(str(saida), cv2.VideoWriter_fourcc(*"mp4v"), fps, (largura, altura))
    if not escritor.isOpened():
        raise RuntimeError("Não consegui abrir o VideoWriter.")

    centro_x, centro_y = largura / 2, altura / 2
    pousadas = np.zeros((altura, largura, 3), dtype=np.float32)
    proxima = 0
    ultimo_progresso = -1

    try:
        for f_idx in range(total_frames):
            t = f_idx / fps

            # Fotos cujo voo já terminou entram de vez na camada de pousadas.
            while proxima < len(alvos):
                r, c, _ = alvos[proxima]
                t_pouso = proxima * intervalo_entre_fotos + hold_central + duracao_voo
                if t < t_pouso:
                    break
                tile = cache_tile[proxima % len(cache_tile)]
                y0 = int(round(offy + r * th))
                x0 = int(round(offx + c * tw))
                y1, x1 = y0 + tile.shape[0], x0 + tile.shape[1]
                ys0, xs0 = max(0, y0), max(0, x0)
                ys1, xs1 = min(altura, y1), min(largura, x1)
                if ys1 > ys0 and xs1 > xs0:
                    pousadas[ys0:ys1, xs0:xs1] = tile[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
                proxima += 1

            frame = pousadas.copy()

            # Overlay da marca por cima: recorta o que aparece e traz os textos.
            frame = frame * (1.0 - alfa) + overlay_bgr * alfa

            # A foto em trânsito fica acima de tudo, em cores originais.
            for i in range(proxima, len(alvos)):
                t_inicio = i * intervalo_entre_fotos
                if t < t_inicio:
                    break
                r, c, _ = alvos[i]
                dt = t - t_inicio
                p = 0.0 if dt < hold_central else ease_out_cubic(min(1.0, (dt - hold_central) / duracao_voo))

                grande = cache_grande[i % len(cache_grande)]
                alvo_x = offx + c * tw + tw / 2
                alvo_y = offy + r * th + th / 2
                lado_agora = max(2, int(round(lado_central + (tw - lado_central) * p)))
                cx = centro_x + (alvo_x - centro_x) * p
                cy = centro_y + (alvo_y - centro_y) * p

                voando = cv2.resize(grande, (lado_agora, lado_agora), interpolation=cv2.INTER_AREA)
                x0 = int(round(cx - lado_agora / 2))
                y0 = int(round(cy - lado_agora / 2))
                xs0, ys0 = max(0, x0), max(0, y0)
                xs1, ys1 = min(largura, x0 + lado_agora), min(altura, y0 + lado_agora)
                if xs1 > xs0 and ys1 > ys0:
                    frame[ys0:ys1, xs0:xs1] = voando[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]

            escritor.write(np.clip(frame, 0, 255).astype(np.uint8))

            if progresso:
                pct = int(f_idx / total_frames * 100)
                if pct != ultimo_progresso:
                    progresso(pct)
                    ultimo_progresso = pct
    finally:
        escritor.release()

    return {
        "arquivo": str(saida),
        "celulas": len(alvos),
        "fotos": len(cache_tile),
        "duracao": round(total_secs, 1),
        "resolucao": f"{largura}x{altura}",
    }


def fotos_disponiveis() -> list[Path]:
    """Todas as fotos já recortadas em storage/tiles, em ordem de chegada."""
    tiles = settings.TILES_DIR
    if not tiles.exists():
        return []
    return sorted((p for p in tiles.glob("*.jpg") if p.is_file()), key=lambda p: p.stat().st_mtime)
