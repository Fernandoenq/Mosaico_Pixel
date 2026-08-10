"""
Gera o overlay da marca (Camada 4 do telão) a partir da arte do cliente.

A arte entra com a marca desenhada numa cor sólida sobre fundo escuro. O script
transforma essa cor em BURACO (alfa 0) e mantém todo o resto opaco. No telão, o
PNG fica por cima do mosaico: as fotos aparecem só pelos recortes, e o fundo e os
textos da arte continuam cobrindo o que estiver atrás.

A arte é encaixada na resolução do telão preservando a proporção (contain) e
centralizada sobre fundo preto opaco. Esticar para forçar o formato deformaria a
marca; a sobra fica preta como o resto da arte, então não aparece na tela.

Uso:
    python tools/gerar_overlay_marca.py                       # usa os padrões
    python tools/gerar_overlay_marca.py --arte outra.png --largura 1920 --altura 1080
    python tools/gerar_overlay_marca.py --enviar               # já sobe para o telão
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
ARTE_PADRAO = RAIZ / "assets" / "backgrounds" / "fundo_dinamico.jpg"
SAIDA_PADRAO = RAIZ / "assets" / "backgrounds" / "overlay_marca.png"


def recortar_cor(
    arte: Image.Image,
    canal_min: int,
    outros_max: int,
    canal: int = 0,
) -> Image.Image:
    """
    Devolve a arte em RGBA com a cor da marca virada em transparência.

    `canal` é o índice RGB dominante (0=vermelho). O teste é "o canal dominante
    é forte E os outros dois são fracos" — mais robusto que comparar com um RGB
    exato, porque a arte costuma vir com compressão JPEG e bordas suavizadas.
    """
    dados = np.array(arte.convert("RGBA"))
    rgb = dados[:, :, :3].astype(int)

    dominante = rgb[:, :, canal]
    outros = np.delete(rgb, canal, axis=2)

    marca = (dominante > canal_min) & (outros.max(axis=2) < outros_max)
    dados[marca, 3] = 0
    return Image.fromarray(dados, "RGBA"), marca


def encaixar(arte: Image.Image, largura: int, altura: int) -> Image.Image:
    """Encaixa preservando a proporção, centralizado sobre preto opaco."""
    escala = min(largura / arte.width, altura / arte.height)
    novo = (max(1, round(arte.width * escala)), max(1, round(arte.height * escala)))
    redimensionada = arte.resize(novo, Image.Resampling.LANCZOS)

    tela = Image.new("RGBA", (largura, altura), (0, 0, 0, 255))
    # `paste` SEM máscara: substitui os pixels, alfa incluído. Passar a própria
    # imagem como máscara comporia a arte sobre o preto e os buracos sumiriam —
    # o overlay saía 100% opaco e cobria o mosaico inteiro.
    tela.paste(redimensionada, ((largura - novo[0]) // 2, (altura - novo[1]) // 2))
    return tela


def main() -> int:
    p = argparse.ArgumentParser(description="Gera o overlay recortado da marca para o telão.")
    p.add_argument("--arte", type=Path, default=ARTE_PADRAO, help="Imagem original do cliente")
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="PNG de saída (com alfa)")
    p.add_argument("--largura", type=int, default=2304, help="Largura do telão")
    p.add_argument("--altura", type=int, default=1377, help="Altura do telão")
    p.add_argument("--canal", type=int, default=0, choices=[0, 1, 2], help="0=R (vermelho), 1=G, 2=B")
    p.add_argument("--canal-min", type=int, default=110, help="Mínimo do canal dominante")
    p.add_argument("--outros-max", type=int, default=90, help="Máximo dos outros dois canais")
    p.add_argument("--enviar", action="store_true", help="Envia para POST /api/ingest/foreground")
    p.add_argument("--api", default="http://127.0.0.1:8000", help="Base da API")
    args = p.parse_args()

    if not args.arte.exists():
        print(f"ERRO: arte não encontrada: {args.arte}")
        return 1

    arte = Image.open(args.arte)
    print(f"arte: {args.arte.name} ({arte.width}x{arte.height})")

    recortada, marca = recortar_cor(arte, args.canal_min, args.outros_max, args.canal)
    proporcao = marca.mean() * 100
    print(f"recorte: {proporcao:.1f}% da arte virou janela para as fotos")

    if proporcao < 1:
        print("AVISO: quase nada foi recortado. Ajuste --canal-min / --outros-max.")
    elif proporcao > 70:
        print("AVISO: recortou quase tudo — o overlay quase não vai cobrir nada.")

    final = encaixar(recortada, args.largura, args.altura)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    final.save(args.saida, "PNG")

    transparente = (np.array(final)[:, :, 3] == 0).mean() * 100
    print(f"salvo: {args.saida}")
    print(f"       {args.largura}x{args.altura} | {transparente:.1f}% transparente")

    if args.enviar:
        import requests

        with args.saida.open("rb") as fh:
            resposta = requests.post(
                f"{args.api}/api/ingest/foreground",
                files={"file": (args.saida.name, fh, "image/png")},
                timeout=30,
            )
        resposta.raise_for_status()
        print(f"enviado ao telão: {resposta.json()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
