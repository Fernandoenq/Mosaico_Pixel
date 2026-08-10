import requests
import random
import time
import os

photos = [
    r"c:\Users\jrval\Desktop\Mosaico_Pixel\randow 3.jpg",
    r"c:\Users\jrval\Desktop\Mosaico_Pixel\randow 2.jpg",
    r"c:\Users\jrval\Desktop\Mosaico_Pixel\foto pessoa randow 1.jpg"
]

# Validate photos
for p in photos:
    if not os.path.exists(p):
        print(f"Erro: Arquivo não encontrado - {p}")
        exit(1)

print("Iniciando simulação de preenchimento (244 células)...")

total_cells = 244
for i in range(total_cells):
    photo_path = random.choice(photos)
    
    try:
        # 1. Enviar foto
        with open(photo_path, 'rb') as f:
            res = requests.post("http://127.0.0.1:8000/api/ingest/upload", files={"file": f})
            if res.status_code != 200:
                print(f"Erro ao enviar foto: {res.text}")
                continue
            
            data = res.json()
            photo_id = data["photo_id"]
            
        # 2. Aprovar a foto (forçar o envio pro mosaico)
        # Usamos force=true para que, caso a queue esteja processando, passe direto
        app_res = requests.post(f"http://127.0.0.1:8000/api/moderation/approve/{photo_id}?fill_sequence=color_match&force=true")
        
        if app_res.status_code == 200:
            print(f"[{i+1}/{total_cells}] Inserida e aprovada com sucesso: {photo_id}")
        else:
            print(f"[{i+1}/{total_cells}] Erro ao aprovar {photo_id}: {app_res.text}")
            
    except Exception as e:
        print(f"Erro na iteração {i}: {e}")
        
    # Espera 1.5s entre fotos para a animação ficar visível e bonita no frontend
    time.sleep(1.5)

print("Simulação concluída!")
