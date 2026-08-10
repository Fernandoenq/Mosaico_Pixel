"""
Abertura do miolo da marca.

Na arte do cliente a marca é um contorno de losangos e o miolo é chapa preta —
o telão não mostra foto nenhuma ali. Este módulo estende a MESMA malha de
losangos para dentro desse miolo: recorta um losango do tamanho da célula em
cada posição vaga do contorno, e devolve a lista de células novas para o motor
passar a alocar foto nelas.

A malha vem da grade já alinhada à arte (rows/cols + offset/tamanho), não de
uma detecção nova sobre os pixels: o alinhamento foi feito uma vez, e refazê-lo
por conta própria só criaria uma segunda verdade para divergir da primeira.
"""

from pathlib import Path

import cv2
import numpy as np


def _para_par(chave: str) -> tuple[int, int] | None:
    try:
        r, c = (int(x) for x in str(chave).split("_"))
    except (ValueError, TypeError):
        return None
    return r, c


def celulas_do_miolo(mask_cells: list[str], rows: int, cols: int, minimo: int = 4) -> list[str]:
    """
    Células do MIOLO da marca: a área vazia grande no meio do desenho.

    O contorno é o fecho convexo das células que JÁ estão na máscara — é o
    desenho da marca, não um retângulo. Assim o miolo acompanha a forma do logo
    em vez de invadir o fundo preto em volta dele.

    Dentro desse contorno há dois tipos de vazio, e eles NÃO podem receber o
    mesmo tratamento: o miolo, um bloco contínuo de centenas de células, e os
    respiros do halftone, células soltas entre um losango e outro. Tapar os
    respiros acabaria com o degradê que faz a ponta da marca desaparecer no
    fundo. Por isso só entram os blocos com pelo menos `minimo` células, medidos
    em vizinhança de 4 — na diagonal o xadrez do halftone se emenda todo e os
    dois casos viram um só.
    """
    pares = [p for p in (_para_par(k) for k in mask_cells) if p is not None]
    if len(pares) < 3:
        return []

    atuais = set(pares)
    pontos = np.array([[c, r] for r, c in pares], dtype=np.int32)
    casco = cv2.convexHull(pontos)

    vago = np.zeros((rows, cols), dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            if (r, c) in atuais:
                continue
            # measureDist=False devolve +1 dentro, 0 na borda, -1 fora.
            if cv2.pointPolygonTest(casco, (float(c), float(r)), False) >= 0:
                vago[r, c] = 1

    quantidade, rotulos, stats, _ = cv2.connectedComponentsWithStats(vago, connectivity=4)
    grandes = {i for i in range(1, quantidade) if stats[i, cv2.CC_STAT_AREA] >= minimo}
    if not grandes:
        return []

    return [
        f"{r}_{c}"
        for r in range(rows)
        for c in range(cols)
        if rotulos[r, c] in grandes
    ]


def recortar_losangos(
    overlay_path: Path,
    destino: Path,
    celulas: list[str],
    rows: int,
    cols: int,
    offset_x: float,
    offset_y: float,
    largura: float,
    altura: float,
    screen_w: int,
    screen_h: int,
    escala_losango: float = 0.86,
) -> int:
    """
    Torna transparente um losango por célula, gravando um overlay novo.

    A grade vive em coordenadas de tela e o PNG tem a resolução da arte; o telão
    estica o overlay para a tela inteira, então a conversão é uma regra de três
    em cada eixo. Recortar direto no PNG original evita o reamostrado que uma
    ida e volta pela resolução de tela introduziria nas bordas.
    """
    imagem = cv2.imread(str(overlay_path), cv2.IMREAD_UNCHANGED)
    if imagem is None:
        raise ValueError(f"Overlay ilegível: {overlay_path}")
    if imagem.ndim != 3 or imagem.shape[2] != 4:
        raise ValueError("O overlay não tem canal alfa — sem ele não há o que recortar.")

    alt_png, larg_png = imagem.shape[:2]
    sx = larg_png / float(screen_w)
    sy = alt_png / float(screen_h)

    passo_x = largura / cols
    passo_y = altura / rows
    recortados = 0

    # Os losangos vão para uma máscara à parte e só no fim descontam do alfa:
    # `fillConvexPoly` recusa a fatia `imagem[:, :, 3]` (não é contígua) e, com
    # antisserrilhado, desenhar um por vez direto no alfa deixaria degrau onde
    # dois losangos se encostam.
    recorte = np.zeros(imagem.shape[:2], dtype=np.uint8)

    for chave in celulas:
        par = _para_par(chave)
        if par is None:
            continue
        r, c = par

        cx = (offset_x + (c + 0.5) * passo_x) * sx
        cy = (offset_y + (r + 0.5) * passo_y) * sy
        hw = (passo_x * sx * escala_losango) / 2.0
        hh = (passo_y * sy * escala_losango) / 2.0

        losango = np.array(
            [[cx, cy - hh], [cx + hw, cy], [cx, cy + hh], [cx - hw, cy]],
            dtype=np.int32,
        )
        cv2.fillConvexPoly(recorte, losango, 255, lineType=cv2.LINE_AA)
        recortados += 1

    # Só o alfa muda: zerar o BGR junto deixaria uma franja preta na borda
    # antisserrilhada quando o telão estica o overlay para a tela.
    imagem[:, :, 3] = np.minimum(imagem[:, :, 3], 255 - recorte)

    cv2.imwrite(str(destino), imagem)
    return recortados
