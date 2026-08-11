import sys
from pathlib import Path
import json

# Adiciona o backend ao PYTHONPATH
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from app.services.video_marca import gerar_video_marca

def main():
    fotos = [RAIZ / "foto1.jpg", RAIZ / "foto2.png", RAIZ / "foto3.png"]
    fotos_validas = [f for f in fotos if f.exists()]
    if not fotos_validas:
        print("Erro: nenhuma foto encontrada.")
        sys.exit(1)

    # Pegando um dos cenarios gerados da pasta fundos
    # O preparar_cenarios ja rodou e gerou os PNGs em backend/storage/cenarios
    cenarios_dir = RAIZ / "backend" / "storage" / "cenarios"
    manifesto_path = cenarios_dir / "cenarios.json"
    
    if not manifesto_path.exists():
        print("Cenários não encontrados, rode preparar_cenarios.py primeiro.")
        sys.exit(1)
        
    with open(manifesto_path, "r", encoding="utf-8") as f:
        dados = json.load(f)
        
    # Vamos pegar o cenário 3840_x_1920
    cenario_id = "3840_x_1920"
    config = next((c for c in dados["cenarios"] if c["id"] == cenario_id), None)
    
    if not config:
        config = dados["cenarios"][0]
    
    overlay_path = cenarios_dir / config["arquivo"]
    bg_image_path = RAIZ / "fundos" / "3840 x 1920 .png"
    
    print(f"Usando overlay: {overlay_path.name}")
    print(f"Usando imagem de fundo: {bg_image_path.name}")

    largura, altura = config.get("screenWidth", 3840), config.get("screenHeight", 1920)
    
    desktop_path = Path.home() / "Desktop"
    video_path = desktop_path / "videos 2 versao proposta.mp4"

    print("\n--- GERANDO VÍDEO (3840x1920): Fundo Intacto + Fotos em Cima com Filtros ---")
    gerar_video_marca(
        saida=video_path,
        fotos=fotos_validas,
        overlay_path=overlay_path,
        config=config,
        largura=largura,
        altura=altura,
        fps=30,
        intervalo_entre_fotos=0.15,
        hold_central=0.6,
        duracao_voo=0.8,
        segundos_finais=3.0,
        duracao_saida=4.0,
        modo_saida="dispersar",
        cor_marca=(28, 28, 226),
        cor_fundo=(0, 0, 0),
        intensidade_filtro_claro=0.4, # Leve filtro branco nas áreas do meio/claras
        estilo_losango=False,
        ordem="linha",
        bg_image_path=bg_image_path
    )
    print(f"Vídeo salvo em: {video_path}")
    print("\nCONCLUÍDO!")

if __name__ == "__main__":
    main()
