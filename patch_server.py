with open("src/simple_frontend.py", "r", encoding="utf-8") as f:
    content = f.read()

old_route = """        if path in ("/", "/index.html"):
            html = _load_html_page().encode("utf-8")
            self._send_bytes(html, "text/html; charset=utf-8")
            return"""
new_route = """        if path in ("/", "/index.html", "/telao"):
            html = _load_html_page("telao.html").encode("utf-8")
            self._send_bytes(html, "text/html; charset=utf-8")
            return

        if path == "/admin":
            html = _load_html_page("admin.html").encode("utf-8")
            self._send_bytes(html, "text/html; charset=utf-8")
            return"""

content = content.replace(old_route, new_route)

new_post = """    def do_POST(self):
        try:
            from urllib.parse import urlparse, unquote
            import json
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path == "/api/settings":
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    settings = json.loads(post_data)
                    if "cols" in settings: self.server_ref.mosaic_cols = int(settings["cols"])
                    if "rows" in settings: self.server_ref.mosaic_rows = int(settings["rows"])
                    if "opacity" in settings: self.server_ref.opacity = float(settings["opacity"])
                    if "width" in settings: self.server_ref.mosaic_width = int(settings["width"])
                    if "height" in settings: self.server_ref.mosaic_height = int(settings["height"])
                    
                    self._send_json({"status": "ok"})
                except Exception as e:
                    self.send_error(400, f"Bad Request: {e}")
                return
            self.send_error(404)
        except Exception as e:
            try: self.send_error(500)
            except: pass

"""

if "def do_POST" not in content:
    content = content.replace("    def do_GET(self):", new_post + "    def do_GET(self):")

with open("src/simple_frontend.py", "w", encoding="utf-8") as f:
    f.write(content)
