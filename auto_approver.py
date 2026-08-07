import urllib.request
import urllib.parse
import json
import time

def get_pending():
    req = urllib.request.Request("http://127.0.0.1:8000/api/moderation/pending")
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def approve_photo(photo_id):
    url = f"http://127.0.0.1:8000/api/moderation/approve/{photo_id}?fill_sequence=color_match&force=true"
    req = urllib.request.Request(url, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Erro ao aprovar {photo_id}: {e}", flush=True)

print("Iniciando Auto-Approver...", flush=True)
while True:
    try:
        pending = get_pending()
        for p in pending:
            print(f"Aprovando {p['id']}...", flush=True)
            approve_photo(p['id'])
            time.sleep(0.1) # Small delay between approvals
    except Exception as e:
        print(f"Erro ao buscar pending: {e}", flush=True)
    time.sleep(1.0)
