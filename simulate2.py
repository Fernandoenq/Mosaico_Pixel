import urllib.request
import urllib.parse
import json
import random
import time
import os
import io

photos = [
    r"c:\Users\jrval\Desktop\Mosaico_Pixel\randow 3.jpg",
    r"c:\Users\jrval\Desktop\Mosaico_Pixel\randow 2.jpg",
    r"c:\Users\jrval\Desktop\Mosaico_Pixel\foto pessoa randow 1.jpg"
]

def post_multipart(url, filename, filepath):
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    with open(filepath, 'rb') as f:
        file_content = f.read()
        
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode('utf-8'))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode('utf-8'))
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(file_content)
    body.extend(f"\r\n--{boundary}--\r\n".encode('utf-8'))
    
    req = urllib.request.Request(url, data=body)
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    req.add_header('Content-Length', str(len(body)))
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def post_json(url):
    req = urllib.request.Request(url, method='POST')
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

print("Iniciando simulacao completa...", flush=True)

total_cells = 244
for i in range(total_cells):
    photo_path = random.choice(photos)
    filename = os.path.basename(photo_path)
    
    try:
        data = post_multipart("http://127.0.0.1:8000/api/ingest/upload", filename, photo_path)
        photo_id = data["photo_id"]
        
        post_json(f"http://127.0.0.1:8000/api/moderation/approve/{photo_id}?fill_sequence=color_match&force=true")
        print(f"[{i+1}/{total_cells}] Inserida e aprovada: {photo_id}", flush=True)
        
    except Exception as e:
        print(f"Erro na iteração {i}: {e}", flush=True)
        
    time.sleep(1.0)
