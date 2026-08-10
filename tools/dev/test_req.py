import urllib.request
import json

data = json.dumps({"cols": ""}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8765/api/settings', data=data, headers={'Content-Type': 'application/json'}, method='POST')

try:
    response = urllib.request.urlopen(req)
    print("Success:", response.read().decode())
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code, e.read().decode())
except Exception as e:
    print("Error:", e)
