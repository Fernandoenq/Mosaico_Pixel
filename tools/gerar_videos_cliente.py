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
        
    # Vamos pegar o cenário Camada 1
    cenario_id = "camada_1"
    config = next((c for c in dados["cenarios"] if c["id"] == cenario_id), None)
    
    if not config:
        # Pega o primeiro que tiver células claras
        config = next((c for c in dados["cenarios"] if c.get("celulasClaras", 0) > 0), dados["cenarios"][0])
    
    overlay_path = cenarios_dir / config["arquivo"]
    
    print(f"Usando overlay: {overlay_path.name}")

    largura, altura = 1920, 1080
    
    desktop_path = Path.home() / "Desktop"
    video1_path = desktop_path / "amostra_fundo_preto.mp4"
    video2_path = desktop_path / "amostra_fundo_branco.mp4"

    print("\n--- GERANDO VÍDEO 1: Fundo Preto, Cores Originais no Meio ---")
    gerar_video_marca(
        saida=video1_path,
        fotos=fotos_validas,
        overlay_path=overlay_path,
        config=config,
        largura=largura,
        altura=altura,
        fps=30,
        intervalo_entre_fotos=0.15, # Mais devagar
        hold_central=0.6,
        duracao_voo=0.8,
        segundos_finais=3.0,
        duracao_saida=4.0, # Dispersao mais lenta
        modo_saida="dispersar",
        cor_marca=(28, 28, 226),
        cor_fundo=(0, 0, 0), # Fundo preto
        intensidade_filtro_claro=0.0, # Cor original
        estilo_losango=False, # Removido o picotado para as células aparecerem inteiras
        ordem="linha" # Linha a linha
    )
    print(f"Vídeo 1 salvo em: {video1_path}")

    print("\n--- GERANDO VÍDEO 2: Fundo Branco, Filtro Branco no Meio ---")
    gerar_video_marca(
        saida=video2_path,
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
        cor_fundo=(0, 0, 0), # Fundo preto, como na Camada 0.png
        intensidade_filtro_claro=0.45, # Leve filtro branco no meio
        estilo_losango=False, # Removido o picotado
        ordem="linha"
    )
    print(f"Vídeo 2 salvo em: {video2_path}")
    print("\nCONCLUÍDO!")

if __name__ == "__main__":
    main()
