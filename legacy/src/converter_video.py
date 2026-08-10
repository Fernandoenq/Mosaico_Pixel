"""
Script para converter o vídeo gerado para um formato mais compatível
usando FFmpeg (se disponível no sistema)
"""

import subprocess
import sys
import os

def verificar_ffmpeg():
    """Verifica se o FFmpeg está instalado"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def converter_video(arquivo_entrada, arquivo_saida):
    """Converte o vídeo usando FFmpeg"""
    print(f"\n🔄 Convertendo {arquivo_entrada} para {arquivo_saida}...")
    print("   Usando FFmpeg para máxima compatibilidade...")
    
    comando = [
        'ffmpeg',
        '-i', arquivo_entrada,
        '-c:v', 'libx264',  # Codec H.264
        '-preset', 'medium',
        '-crf', '23',  # Qualidade (menor = melhor, 18-28 é bom)
        '-pix_fmt', 'yuv420p',  # Formato de pixel compatível
        '-y',  # Sobrescreve arquivo existente
        arquivo_saida
    ]
    
    try:
        subprocess.run(comando, check=True)
        print(f"\n✅ Conversão concluída com sucesso!")
        print(f"   📁 Arquivo convertido: {arquivo_saida}")
        
        # Mostra o tamanho dos arquivos
        tamanho_original = os.path.getsize(arquivo_entrada) / (1024 * 1024)
        tamanho_convertido = os.path.getsize(arquivo_saida) / (1024 * 1024)
        print(f"   📦 Tamanho original: {tamanho_original:.1f} MB")
        print(f"   📦 Tamanho convertido: {tamanho_convertido:.1f} MB")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Erro ao converter: {e}")
        return False

def main():
    print("="*60)
    print("CONVERSOR DE VÍDEO - Máxima Compatibilidade")
    print("="*60)
    
    arquivo_entrada = "assets/videos/album_fotos.mp4"
    arquivo_saida = "assets/videos/album_fotos_h264.mp4"
    
    # Verifica se o arquivo de entrada existe
    if not os.path.exists(arquivo_entrada):
        print(f"\n❌ Arquivo não encontrado: {arquivo_entrada}")
        print("   Execute primeiro: python criar_video_album.py")
        return
    
    # Verifica se o FFmpeg está instalado
    if not verificar_ffmpeg():
        print("\n❌ FFmpeg não encontrado no sistema!")
        print("\n💡 Para instalar o FFmpeg:")
        print("   1. Windows: baixe em https://ffmpeg.org/download.html")
        print("   2. Ou use: winget install ffmpeg")
        print("   3. Ou use: choco install ffmpeg (com Chocolatey)")
        print("\n   Após instalar, reinicie o terminal e tente novamente.")
        return
    
    print(f"\n✅ FFmpeg encontrado!")
    print(f"   📁 Arquivo de entrada: {arquivo_entrada}")
    print(f"   📁 Arquivo de saída: {arquivo_saida}")
    
    # Converte o vídeo
    sucesso = converter_video(arquivo_entrada, arquivo_saida)
    
    if sucesso:
        print("\n" + "="*60)
        print("✅ CONVERSÃO CONCLUÍDA!")
        print("="*60)
        print(f"\nO arquivo convertido está pronto:")
        print(f"   {arquivo_saida}")
        print("\nEste arquivo deve funcionar em qualquer player! 🎬")

if __name__ == "__main__":
    main()

