#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ponto de entrada principal do sistema (Headless).
Inicia o monitoramento da galeria e o servidor frontend web administrativo.
"""

from pathlib import Path
import threading
import time
import sys

from galeria_monitor import monitorar_e_gerar
from simple_frontend import SimpleMosaicFrontend

_PROJECT_DIR = Path(__file__).resolve().parent.parent

def main():
    print("=" * 60)
    print(" 📸 MOSAICO PIXEL - SERVIDOR ADMINISTRATIVO ")
    print("=" * 60)
    
    frontend = SimpleMosaicFrontend(host="0.0.0.0", port=8765)
    
    # Thread do servidor Web
    web_thread = threading.Thread(target=frontend.start, daemon=True)
    web_thread.start()
    print("[Web] Servidor Admin rodando em: http://127.0.0.1:8765/admin")
    print("[Web] Tela do Resolume rodando em: http://127.0.0.1:8765/")
    
    # Thread do monitor de pasta
    pasta_galeria = _PROJECT_DIR / "Galeria"
    pasta_galeria.mkdir(exist_ok=True)
    
    def log_callback(msg: str):
        print(f"[Monitor] {msg}")
        
    stop_event = threading.Event()
    
    print(f"[Monitor] Monitorando pasta de imagens: {pasta_galeria}")
    monitor_thread = threading.Thread(
        target=monitorar_e_gerar,
        kwargs={
            "pasta_entrada": pasta_galeria,
            "log_callback": log_callback,
            "status_callback": log_callback,
            "stop_event": stop_event,
            "aplicar_moldura": False,
            "filtro_vermelho": False,
            "nova_imagem_callback": None
        },
        daemon=True
    )
    monitor_thread.start()
    
    print("=" * 60)
    print("Sistema rodando! Aperte Ctrl+C para desligar.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDesligando sistema...")
        stop_event.set()
        frontend.stop()

if __name__ == "__main__":
    main()
