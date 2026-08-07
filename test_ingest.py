import urllib.request
import json
import time

def put_config(patch):
    data = json.dumps(patch).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:8000/api/config', data=data, headers={'Content-Type': 'application/json'}, method='PUT')
    urllib.request.urlopen(req)

def post(url, data=None):
    if data:
        data = json.dumps(data).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
    else:
        data = b''
        headers = {}
    req = urllib.request.Request(f'http://127.0.0.1:8000{url}', data=data, headers=headers, method='POST')
    return json.loads(urllib.request.urlopen(req).read().decode())

def get(url):
    req = urllib.request.Request(f'http://127.0.0.1:8000{url}')
    return json.loads(urllib.request.urlopen(req).read().decode())

print("Setting circle_mask, rows=15, cols=20...")
put_config({"gridContainerShape": "circle_mask", "rows": 15, "cols": 20})

print("Resetting mosaic...")
post("/api/run/reset")
post("/api/run/start")

print("Ingesting test photos...")
res = post("/api/ingest/test-gallery-photos?count=10")
print(f"Ingested {res.get('count')} photos")

time.sleep(2) # let it process matching

print("Auto filling duplicates...")
res = post("/api/mosaic/auto-fill-duplicates")
print(f"Auto filled {res.get('placed_count')} duplicates")

print("Fetching state...")
state = get("/api/mosaic/save-state")
placed = state.get('placed_tiles', {})

corners = ["0_0", "0_1", "14_0", "14_19", "0_19"]
errors = 0
for corner in corners:
    if corner in placed:
        print(f"ERROR: Tile found in corner cell {corner}!")
        errors += 1

print(f"Total tiles placed: {len(placed)}")
if errors == 0:
    print("SUCCESS: No tiles in corners!")
else:
    print(f"FAILED: {errors} corner cells filled.")
