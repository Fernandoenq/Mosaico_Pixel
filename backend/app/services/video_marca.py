"""
Exportação de vídeo no modelo da marca (referência: video/*.mp4 do projeto).

Diferente do export "fractal" de video_export.py, este reproduz o que o cliente
aprovou: fundo preto, a foto surge COLORIDA e grande no centro, voa até a célula
dela e pousa TINGIDA na cor da marca — as fotos pousadas é que vão desenhando o
logo, célula por célula, até a arte fechar.

O "outro video" que o cliente mandou depois é uma variação desse modelo, e
medi-lo quadro a quadro rendeu quatro ajustes que viram parâmetro aqui:

    bg_image_path    a ARTE aparece desde o primeiro frame, não um fundo preto
                     que vai sendo preenchido;
    tingir_fotos     as fotos entram na COR ORIGINAL. O vermelho na tela é a
                     arte por baixo, nas células que ainda não receberam foto;
    voo_de_fora      a foto entra pequena pela borda e vai direto para a célula.
                     Não há cartão gigante no centro — ele taparia justamente o
                     mosaico que está se formando;
    estilo_losango   o ladrilho é cortado em losango, casando com a malha.

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


def aplicar_mascara_losango(img: np.ndarray, bg_color: tuple[int, int, int]) -> np.ndarray:
    """Aplica uma máscara de losango (diamond) na imagem, preenchendo os cantos com bg_color."""
    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    pts = np.array([[w//2, 0], [w, h//2], [w//2, h], [0, h//2]], np.int32)
    cv2.fillPoly(mask, [pts], 255)
    res = np.full_like(img, bg_color)
    res[mask == 255] = img[mask == 255]
    return res


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
    duracao_saida: float = 2.0,
    modo_saida: str = "dispersar",
    cor_marca: tuple[int, int, int] = (28, 28, 226),  # BGR do vermelho HSBC
    cor_fundo: tuple[int, int, int] = (0, 0, 0),      # BGR do fundo
    intensidade_filtro_claro: float = 0.0,            # 0.0 a 1.0 para esbranquiçar as células claras
    estilo_losango: bool = False,                     # Se True, corta cada foto em formato de losango (efeito picotado)
    tingir_fotos: bool = True,                        # False: nenhuma foto leva a cor da marca
    celulas_claras: set[str] | None = None,           # Células que recebem o véu branco, no formato "r_c"
    voo_de_fora: bool = False,                        # True: a foto entra pequena pela borda, sem cartão central
    ordem: str = "linha",
    bg_image_path: Path | None = None,
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

    if ordem == "centro":
        # Do centro para fora: o logo "cresce" em vez de aparecer em faixas.
        cx_grade, cy_grade = cols / 2, rows / 2
        alvos.sort(key=lambda a: math.hypot(a[1] - cx_grade, a[0] - cy_grade))
    else:
        # Linha a linha, de cima para baixo — o mesmo desenho que o telão faz
        # ao vivo.
        alvos.sort(key=lambda a: (a[0], a[1]))

    # Quais células saem TINGIDAS. A pintura do painel manda: célula pintada
    # entra na cor da marca, célula sem pintura entra na cor original.
    #
    # Com `tingir_fotos=False` ninguém é tingido — é o modelo do vídeo de
    # referência, em que o vermelho na tela é a ARTE aparecendo nas células que
    # ainda não receberam foto, e não a foto pintada de vermelho.
    pintadas = set((config.get("cellFilters") or {}).keys()) if tingir_fotos else set()
    tinge_tudo = tingir_fotos and not pintadas
    claras = set(celulas_claras or ())

    # Recorte quadrado de cada foto, no tamanho do ladrilho, nas duas versões.
    lado_tile = (max(1, int(round(tw))), max(1, int(round(th))))
    cache_tile: list[np.ndarray] = []
    cache_tile_original: list[np.ndarray] = []
    cache_tile_claro: list[np.ndarray] = []
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
        pequena = cv2.resize(quadrado, lado_tile, interpolation=cv2.INTER_AREA)
        pequena_tingida = tingir(pequena, cor_marca)
        
        # Véu branco num banco SEPARADO: com `celulas_claras` só o miolo é
        # lavado, e o resto das fotos continua na cor original. Aplicando por
        # cima do banco original, o clareamento vazaria para o mosaico inteiro.
        pequena_clara = pequena
        if intensidade_filtro_claro > 0:
            branco = np.full_like(pequena, 255, dtype=np.float32)
            pequena_clara = cv2.addWeighted(
                pequena.astype(np.float32), 1.0 - intensidade_filtro_claro,
                branco, intensidade_filtro_claro, 0,
            ).astype(np.uint8)

        pequena_original = pequena if claras else pequena_clara

        if estilo_losango:
            pequena_tingida = aplicar_mascara_losango(pequena_tingida, cor_fundo)
            pequena_original = aplicar_mascara_losango(pequena_original, cor_fundo)
            pequena_clara = aplicar_mascara_losango(pequena_clara, cor_fundo)

        cache_tile.append(pequena_tingida)
        cache_tile_original.append(pequena_original)
        cache_tile_claro.append(pequena_clara)
        cache_grande.append(cv2.resize(quadrado, (lado_central, lado_central), interpolation=cv2.INTER_AREA))

    if not cache_tile:
        raise ValueError("Nenhuma das fotos pôde ser lida.")

    def _banco_da_celula(r: int, c: int) -> list[np.ndarray]:
        """
        De qual banco sai o ladrilho desta célula.

        Três destinos e não dois: tingido na cor da marca, cor original, e o
        véu branco do miolo. Sem separar os dois últimos, clarear o miolo
        clareava o mosaico inteiro.
        """
        chave = f"{r}_{c}"
        if tinge_tudo or chave in pintadas:
            return cache_tile
        if chave in claras:
            return cache_tile_claro
        return cache_tile_original

    t_entrada_fim = len(alvos) * intervalo_entre_fotos + hold_central + duracao_voo
    t_saida_inicio = t_entrada_fim + segundos_finais
    total_secs = t_saida_inicio + (duracao_saida if modo_saida != "nenhum" else 0.0)
    total_frames = int(total_secs * fps)

    saida.parent.mkdir(parents=True, exist_ok=True)
    escritor = cv2.VideoWriter(str(saida), cv2.VideoWriter_fourcc(*"mp4v"), fps, (largura, altura))
    if not escritor.isOpened():
        raise RuntimeError("Não consegui abrir o VideoWriter.")

    centro_x, centro_y = largura / 2, altura / 2
    
    # Prepara o fundo com a imagem original ou a cor escolhida
    if bg_image_path and bg_image_path.exists():
        bg_img_pil = Image.open(bg_image_path).convert("RGB").resize((largura, altura), Image.Resampling.LANCZOS)
        pousadas = np.array(bg_img_pil)[:, :, ::-1].astype(np.float32)
    else:
        pousadas = np.full((altura, largura, 3), cor_fundo, dtype=np.float32)
    
    proxima = 0
    ultimo_progresso = -1
    dist_max = math.hypot(largura, altura)

    try:
        for f_idx in range(total_frames):
            t = f_idx / fps

            if modo_saida != "nenhum" and t >= t_saida_inicio:
                # 💥 FASE 3: ANIMAÇÃO DE SAÍDA (MOSAIC OUTRO / DISPERSAR)
                t_exit = t - t_saida_inicio
                p_geral = min(1.0, t_exit / max(0.1, duracao_saida))
                
                # Fundo com a imagem original ou a cor escolhida para composicao
                if bg_image_path and bg_image_path.exists():
                    frame = pousadas.copy()
                else:
                    frame = np.full((altura, largura, 3), cor_fundo, dtype=np.float32)
                
                if modo_saida == "dispersar":
                    for i, (r, c, _) in enumerate(alvos):
                        banco = _banco_da_celula(r, c)
                        tile = banco[i % len(banco)]
                        
                        tx = offx + c * tw
                        ty = offy + r * th
                        cx_tile = tx + tw / 2.0
                        cy_tile = ty + th / 2.0
                        
                        dx = cx_tile - centro_x
                        dy = cy_tile - centro_y
                        d = math.hypot(dx, dy) or 1.0
                        
                        delay = (1.0 - min(1.0, d / (dist_max / 2.0))) * 0.35
                        dt_tile = max(0.0, t_exit - delay)
                        dur_efetiva = max(0.2, duracao_saida - 0.35)
                        p_tile = ease_out_cubic(min(1.0, dt_tile / dur_efetiva))
                        
                        if p_tile >= 1.0:
                            continue
                            
                        # Deslocamento radial para fora da tela
                        x_now = int(round(tx + (dx / d) * dist_max * p_tile))
                        y_now = int(round(ty + (dy / d) * dist_max * p_tile))
                        alpha_tile = 1.0 - p_tile
                        
                        th_tile, tw_tile = tile.shape[:2]
                        ys0, xs0 = max(0, y_now), max(0, x_now)
                        ys1, xs1 = min(altura, y_now + th_tile), min(largura, x_now + tw_tile)
                        if ys1 > ys0 and xs1 > xs0:
                            sub_tile = tile[ys0 - y_now:ys1 - y_now, xs0 - x_now:xs1 - x_now].astype(np.float32) * alpha_tile
                            frame[ys0:ys1, xs0:xs1] = np.maximum(frame[ys0:ys1, xs0:xs1], sub_tile)
                            
                    # Overlay esvanecendo junto da dispersao
                    alfa_saida = alfa * (1.0 - p_geral)
                    frame = frame * (1.0 - alfa_saida) + overlay_bgr * alfa_saida
                else: # retorno
                    p_ret = ease_out_cubic(min(1.0, t_exit / max(0.1, duracao_saida)))
                    for i, (r, c, _) in enumerate(alvos):
                        banco = _banco_da_celula(r, c)
                        tile = banco[i % len(banco)]
                        tx = offx + c * tw + tw / 2.0
                        ty = offy + r * th + th / 2.0
                        cx_now = tx + (centro_x - tx) * p_ret
                        cy_now = ty + (centro_y - ty) * p_ret
                        lado_now = max(2, int(round(tw + (lado_central - tw) * p_ret)))
                        alpha_ret = 1.0 - (p_ret ** 2)
                        
                        res = cv2.resize(tile, (lado_now, lado_now), interpolation=cv2.INTER_AREA).astype(np.float32) * alpha_ret
                        x0 = int(round(cx_now - lado_now / 2))
                        y0 = int(round(cy_now - lado_now / 2))
                        xs0, ys0 = max(0, x0), max(0, y0)
                        xs1, ys1 = min(largura, x0 + lado_now), min(altura, y0 + lado_now)
                        if xs1 > xs0 and ys1 > ys0:
                            frame[ys0:ys1, xs0:xs1] = np.maximum(frame[ys0:ys1, xs0:xs1], res[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0])
                    alfa_saida = alfa * (1.0 - p_ret)
                    frame = frame * (1.0 - alfa_saida) + overlay_bgr * alfa_saida

                escritor.write(np.clip(frame, 0, 255).astype(np.uint8))
            else:
                # 🌟 FASE 1 & 2: ENTRADA E HOLD CENTRAL
                while proxima < len(alvos):
                    r, c, _ = alvos[proxima]
                    t_pouso = proxima * intervalo_entre_fotos + hold_central + duracao_voo
                    if t < t_pouso:
                        break
                    banco = _banco_da_celula(r, c)
                    tile = banco[proxima % len(banco)]
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

                    if voo_de_fora:
                        # Modelo do vídeo de referência: a foto entra PEQUENA
                        # pela borda mais próxima da célula dela e vai direto
                        # para o lugar. Não há cartão gigante no meio da tela —
                        # ele tapa justamente o mosaico que está se formando.
                        angulo = math.atan2(alvo_y - centro_y, alvo_x - centro_x)
                        raio = math.hypot(largura, altura) * 0.62
                        origem_x = centro_x + math.cos(angulo) * raio
                        origem_y = centro_y + math.sin(angulo) * raio
                        lado_agora = max(2, int(round(tw * (1.9 - 0.9 * p))))
                        cx = origem_x + (alvo_x - origem_x) * p
                        cy = origem_y + (alvo_y - origem_y) * p
                    else:
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

    na_cor_original = 0 if tinge_tudo else sum(1 for r, c, _ in alvos if f"{r}_{c}" not in pintadas)
    return {
        "arquivo": str(saida),
        "celulas": len(alvos),
        "corOriginal": na_cor_original,
        "fotos": len(cache_tile),
        "ordem": ordem,
        "duracao": round(total_secs, 1),
        "resolucao": f"{largura}x{altura}",
    }


def fotos_disponiveis() -> list[Path]:
    """Todas as fotos já recortadas em storage/tiles, em ordem de chegada."""
    tiles = settings.TILES_DIR
    if not tiles.exists():
        return []
    return sorted((p for p in tiles.glob("*.jpg") if p.is_file()), key=lambda p: p.stat().st_mtime)
