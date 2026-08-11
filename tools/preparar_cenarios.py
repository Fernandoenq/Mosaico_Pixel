"""
Prepara os cenários do evento a partir das artes entregues pelo cliente.

Cada arte é um PNG/JPG de tela cheia com o logo CHEIO — não mais o halftone
picotado em centenas de losangos. Era o picote que deixava aquela "sombra": as
fotos só apareciam pelos furinhos e o preto entre eles dominava a imagem. Com o
logo cheio, cada célula da grade é um quadrado inteiro de foto.

Para cada arte o script produz:

  * o overlay (PNG com alfa) — o logo vira janela transparente, o resto (fundo
    preto e os textos) continua opaco e é desenhado por cima do mosaico;
  * a grade que melhor cobre o logo com ~250 células quase quadradas;
  * a lista de células do logo e a pintura de cada uma: as do vermelho saem
    tingidas, as do branco saem claras.

Roda uma vez, quando o cliente manda arte nova:

    python tools/preparar_cenarios.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "fundos"
DESTINO = RAIZ / "backend" / "storage" / "cenarios"

# Quantas células de foto o cliente quer ver dentro do logo.
ALVO_CELULAS = 250
# Quanto a célula pode fugir do quadrado antes de a foto começar a distorcer.
PROPORCAO_MIN, PROPORCAO_MAX = 0.88, 1.14
# Fração do ladrilho que precisa estar sobre o logo para a célula valer.
COBERTURA_MINIMA = 0.5


def separar_regioes(img_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    (vermelho, branco) do logo.

    O branco dos TEXTOS também é branco; o que separa um do outro é o tamanho.
    Sem esse corte, "HSBC Brazil Decade" viraria célula de foto.
    """
    b, g, r = (img_bgr[:, :, i].astype(np.int16) for i in range(3))
    vermelho = (r > 110) & (g < 90) & (b < 90)
    claro = ((r > 170) & (g > 170) & (b > 170)).astype(np.uint8)

    altura, largura = claro.shape
    quantidade, rotulos, stats, _ = cv2.connectedComponentsWithStats(claro, 8)
    branco = np.zeros_like(claro, dtype=bool)
    for i in range(1, quantidade):
        if stats[i, cv2.CC_STAT_AREA] > largura * altura * 0.005:
            branco |= rotulos == i
    return vermelho, branco


def melhor_grade(logo: np.ndarray, caixa: tuple[int, int, int, int]) -> tuple[int, int]:
    """(rows, cols) que chega mais perto de ALVO_CELULAS mantendo a célula quadrada."""
    x0, y0, gw, gh = caixa
    candidatos = []
    for rows in range(8, 22):
        for cols in range(14, 40):
            tw, th = gw / cols, gh / rows
            if not (PROPORCAO_MIN <= tw / th <= PROPORCAO_MAX):
                continue
            dentro = sum(
                1
                for r in range(rows)
                for c in range(cols)
                if logo[int(y0 + r * th):int(y0 + (r + 1) * th),
                        int(x0 + c * tw):int(x0 + (c + 1) * tw)].mean() >= COBERTURA_MINIMA
            )
            candidatos.append((abs(dentro - ALVO_CELULAS), rows, cols, dentro))
    if not candidatos:
        raise ValueError("Nenhuma grade quadrada cabe nesta arte.")
    _, rows, cols, dentro = min(candidatos)
    print(f"      grade {rows}x{cols} -> {dentro} células no logo")
    return rows, cols


def identificador(nome: str) -> str:
    """Nome de arquivo do cliente vira um id estável e sem surpresa."""
    base = re.sub(r"\.(png|jpe?g)$", "", nome, flags=re.I)
    base = re.sub(r"[^0-9a-zA-Z]+", "_", base).strip("_").lower()
    return base


def preparar(caminho: Path) -> dict:
    img = cv2.imread(str(caminho))
    if img is None:
        raise ValueError(f"Arte ilegível: {caminho}")
    altura, largura = img.shape[:2]
    print(f"   {caminho.name}  {largura}x{altura}")

    vermelho, branco = separar_regioes(img)
    logo = vermelho | branco
    ys, xs = np.where(logo)
    if not len(xs):
        raise ValueError(f"Não achei o logo em {caminho.name}")

    x0, y0 = int(xs.min()), int(ys.min())
    gw, gh = int(xs.max() - x0 + 1), int(ys.max() - y0 + 1)
    rows, cols = melhor_grade(logo, (x0, y0, gw, gh))
    tw, th = gw / cols, gh / rows

    celulas: list[str] = []
    pintura: dict[str, str] = {}
    for r in range(rows):
        ya, yb = int(y0 + r * th), int(y0 + (r + 1) * th)
        for c in range(cols):
            xa, xb = int(x0 + c * tw), int(x0 + (c + 1) * tw)
            if logo[ya:yb, xa:xb].mean() < COBERTURA_MINIMA:
                continue
            chave = f"{r}_{c}"
            celulas.append(chave)
            # Quem manda na cor é a região que ocupa a MAIOR parte da célula.
            if vermelho[ya:yb, xa:xb].mean() >= branco[ya:yb, xa:xb].mean():
                pintura[chave] = "red"

    # Overlay: o logo vira janela; fundo e textos continuam opacos por cima do
    # mosaico. Borda afiada para garantir que a cor das células fique forte até o limite.
    alfa = np.where(logo, 0, 255).astype(np.uint8)
    overlay = np.dstack([img, alfa])

    DESTINO.mkdir(parents=True, exist_ok=True)
    nome = f"{identificador(caminho.name)}.png"
    cv2.imwrite(str(DESTINO / nome), overlay)

    return {
        "id": identificador(caminho.name),
        "rotulo": f"{largura}x{altura} · {'vermelho + branco' if branco.any() else 'vermelho + preto'}",
        "arquivo": nome,
        "screenWidth": largura,
        "screenHeight": altura,
        "rows": rows,
        "cols": cols,
        "gridOffsetX": x0,
        "gridOffsetY": y0,
        "gridWidth": gw,
        "gridHeight": gh,
        "customMaskCells": celulas,
        "cellFilters": pintura,
        "celulasNoLogo": len(celulas),
        "celulasVermelhas": len(pintura),
        "celulasClaras": len(celulas) - len(pintura),
    }


def main():
    if not ORIGEM.exists():
        raise SystemExit(f"Pasta das artes não encontrada: {ORIGEM}")

    cenarios = []
    for caminho in sorted(ORIGEM.iterdir()):
        if caminho.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        cenarios.append(preparar(caminho))

    manifesto = DESTINO / "cenarios.json"
    manifesto.write_text(json.dumps({"cenarios": cenarios}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(cenarios)} cenário(s) em {manifesto}")
    for c in cenarios:
        print(f"   {c['id']:<26} {c['rows']}x{c['cols']} | {c['celulasNoLogo']} células "
              f"({c['celulasVermelhas']} vermelhas, {c['celulasClaras']} claras)")


if __name__ == "__main__":
    main()
