import os
import subprocess
import time
import sys

def open_resolume_capture():
    print("==============================================")
    print(" 🚀 Mosaico Pixel - Agente do Resolume        ")
    print("==============================================")
    print("Este script abre o Mosaico na proporcao exata para")
    print("ser capturado via NDI ou Resolume Desktop Capture.")
    print("Se voce usa Resolume Arena 7+, considere usar o ")
    print("plugin 'WebSource' colando diretamente a URL lá!")
    print("----------------------------------------------")
    
    url = "http://127.0.0.1:8765/telao"
    width = 768
    height = 960
    
    print(f"Iniciando Chrome em modo Kiosk (Tela Cheia)...")
    print(f"URL: {url}")
    print(f"Resolução Alvo: {width}x{height}")
    
    # Comando para iniciar o Chrome em app mode e tela cheia (headless style para teloes)
    chrome_cmd = [
        "start", "chrome",
        f"--app={url}",
        f"--window-size={width},{height}",
        "--kiosk",
        "--disable-infobars"
    ]
    
    try:
        os.system(" ".join(chrome_cmd))
        print("\n✅ Navegador iniciado com sucesso!")
        print("Para fechar o modo Kiosk, aperte ALT+F4 no teclado.")
    except Exception as e:
        print(f"\n❌ Erro ao iniciar o navegador: {e}")

if __name__ == "__main__":
    open_resolume_capture()
    time.sleep(3)
