import os
import time
import shutil
import random

photos = [
    r"c:\Users\jrval\Desktop\Mosaico_Pixel\randow 3.jpg",
    r"c:\Users\jrval\Desktop\Mosaico_Pixel\randow 2.jpg",
    r"c:\Users\jrval\Desktop\Mosaico_Pixel\foto pessoa randow 1.jpg"
]

hot_folder = r"C:\Users\jrval\Desktop\Mosaico_Pixel\backend\storage\hot_folder"
os.makedirs(hot_folder, exist_ok=True)

print("Iniciando simulação via Hot Folder...", flush=True)

for i in range(244):
    photo_path = random.choice(photos)
    dest_name = f"simulacao_{i}_{int(time.time())}.jpg"
    dest_path = os.path.join(hot_folder, dest_name)
    
    try:
        shutil.copy2(photo_path, dest_path)
        print(f"Copiada {dest_name}", flush=True)
    except Exception as e:
        print(f"Erro ao copiar {dest_name}: {e}", flush=True)
        
    time.sleep(1.5)

print("Concluído!", flush=True)
