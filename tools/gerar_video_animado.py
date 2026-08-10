"""
Script para geração de vídeo com Animação de Entrada e Saída do Mosaico (PICBRAND ARCH).

Conformidade com os padrões do sistema:
- Imagens da raiz do projeto (foto1.jpg, foto2.png, foto3.png).
- Entrada: Fotos surgem no centro em preview colorido, voam até a célula.
- Cores: Células da marca ficam tingidas em vermelho HSBC; células do miolo/meio mantêm a cor original.
- Saída: Dispersão radial para fora da tela com esvanecimento (Mosaic Outro).
- Saída de vídeo em MP4 na Área de Trabalho do Usuário.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Adiciona o backend ao PYTHONPATH
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from app.services.video_marca import gerar_video_marca, carregar_overlay, celulas_da_marca


def main():
    fotos = [RAIZ / "foto1.jpg", RAIZ / "foto2.png", RAIZ / "foto3.png"]
    fotos_validas = [f for f in fotos if f.exists()]
    if not fotos_validas:
        print("Erro: nenhuma foto (foto1.jpg, foto2.png, foto3.png) encontrada na raiz do projeto.")
        sys.exit(1)

    overlay_orig = RAIZ / "assets" / "backgrounds" / "overlay_marca.png"
    overlay_fore = RAIZ / "backend" / "storage" / "foreground.png"
    
    if not overlay_fore.exists():
        overlay_fore = overlay_orig

    desktop_path = Path.home() / "Desktop" / "mosaico_animacao_entrada_saida.mp4"

    config_path = RAIZ / "backend" / "storage" / "run_config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {"screenWidth": 1920, "screenHeight": 1080, "rows": 38, "cols": 62}

    # Identifica as células vermelhas da marca
    largura, altura = 1920, 1080
    if overlay_orig.exists():
        _, alfa_orig = carregar_overlay(overlay_orig, largura, altura)
        alvos_orig = celulas_da_marca(alfa_orig, 38, 62, 0, 0, largura, altura)
        red_cell_filters = {f"{r}_{c}": "red" for r, c, _ in alvos_orig}
        config["cellFilters"] = red_cell_filters

    print(f"Gerando video com entrada e saida em {largura}x{altura}...")
    print(f"   - Fotos utilizadas: {[f.name for f in fotos_validas]}")
    print(f"   - Destino: {desktop_path}")

    resultado = gerar_video_marca(
        saida=desktop_path,
        fotos=fotos_validas,
        overlay_path=overlay_fore,
        config=config,
        largura=largura,
        altura=altura,
        fps=30,
        intervalo_entre_fotos=0.08,
        hold_central=0.6,
        duracao_voo=0.6,
        segundos_finais=4.0,
        duracao_saida=3.0,
        modo_saida="dispersar",
        cor_marca=(28, 28, 226),  # BGR do vermelho HSBC
        ordem="centro",
    )

    print("\nVIDEO CONCLUIDO COM SUCESSO!")
    print(f"   - Arquivo gerado: {resultado['arquivo']}")
    print(f"   - Resolucao: {resultado['resolucao']}")
    print(f"   - Duracao total: {resultado['duracao']}s")
    print(f"   - Celulas no video: {resultado['celulas']} ({resultado['corOriginal']} na cor original do miolo)")


if __name__ == "__main__":
    main()
