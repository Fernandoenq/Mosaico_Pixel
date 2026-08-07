#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Frontend web básico para visualização do mosaico em boa qualidade.
"""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from image_orientation import needs_mosaic_normalize, oriented_image_bytes

_PROJECT_DIR = Path(__file__).resolve().parent.parent
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".jfif", ".gif"}


def _is_image_file(path: Path) -> bool:
    if not path.is_file():
        return False
    ext = path.suffix.lower()
    if ext in _IMAGE_EXTENSIONS:
        return True
    if ext:
        return False
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return False
    return (
        head.startswith(b"\xff\xd8")
        or head.startswith(b"\x89PNG\r\n\x1a\n")
        or (len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP")
        or head.startswith(b"BM")
        or head.startswith(b"GIF8")
    )


def _guess_image_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith(b"GIF8"):
        return "image/gif"
    return "image/jpeg"


# Telão P2.6 mm reto (INDOOR): 768×960 px, grelha 4×5, módulo 192×192 px (4:5)
TELAO_LARGURA_PX = 768
TELAO_ALTURA_PX = 960
TELAO_MODULO_PX = 192
TELAO_COLUNAS = 20
TELAO_LINHAS = 5
# Intervalo minimo entre destaques no centro (evita cortar animacao da foto anterior).
TELAO_SPOTLIGHT_GAP_MS = 1000


def _load_html_page(template_name: str) -> str:
    from pathlib import Path
    try:
        template_path = Path(__file__).parent / "templates" / template_name
        html = template_path.read_text(encoding="utf-8")
        build = _frontend_version()
        return html.replace("__FRONT_BUILD__", build)
    except Exception as e:
        return f"<html><body><h1>Erro {template_name}</h1><p>{e}</p></body></html>"

def _frontend_version() -> str:
    """Versao baseada no mtime deste arquivo, para o JS detectar mudancas."""
    try:
        return str(Path(__file__).stat().st_mtime_ns)
    except Exception:
        return "0"


class _FrontendHandler(BaseHTTPRequestHandler):
    server_ref: "SimpleMosaicFrontend" = None  # type: ignore[assignment]

    def log_message(self, fmt, *args):  # noqa: N802
        return

    @staticmethod
    def _safe_write(wfile, body: bytes) -> bool:
        try:
            wfile.write(body)
            return True
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            return False

    def _send_json(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self._safe_write(self.wfile, data)

    def _send_bytes(self, body: bytes, content_type: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._safe_write(self.wfile, body)

    def _serve_video(self, file_path: Path):
        try:
            file_size = file_path.stat().st_size
        except OSError:
            self.send_error(404)
            return
        range_header = self.headers.get("Range", "")
        try:
            if range_header.startswith("bytes="):
                spec = range_header[6:]
                start_s, end_s = spec.split("-", 1)
                start = int(start_s) if start_s.strip() else 0
                end = int(end_s) if end_s.strip() else min(file_size - 1, start + 1024 * 512)
                end = min(end, file_size - 1)
                length = max(0, end - start + 1)
                self.send_response(206)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with file_path.open("rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        if not self._safe_write(self.wfile, chunk):
                            break
                        remaining -= len(chunk)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with file_path.open("rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        if not self._safe_write(self.wfile, chunk):
                            break
        except Exception:
            pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            from urllib.parse import urlparse, unquote
            import json
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path.endswith("/api/action"):
                import time
                try:
                    content_length = int(self.headers.get('Content-Length', 0))
                    post_data = self.rfile.read(content_length)
                    payload = json.loads(post_data)
                    cmd = payload.get("command", "")
                    if cmd in ["clear", "restart"]:
                        import shutil
                        from pathlib import Path
                        try:
                            # Apagar imagens do mosaico
                            for f in self.server_ref.mosaic_dir.glob("*.jpg"):
                                f.unlink(missing_ok=True)
                            self.server_ref.reset_mosaic_catalog()
                        except Exception as e:
                            print(f"Erro ao limpar pastas: {e}")
                            
                        self.server_ref.action_signal = {"command": cmd, "ts": time.time()}
                        self._send_json({"ok": True, "command": cmd})
                    else:
                        self._send_json({"ok": False, "msg": "Invalid command"})
                except Exception as e:
                    self.send_error(500, f"Error: {e}")
                return

            if path.endswith("/api/test_animation"):
                try:
                    import time
                    import random
                    from pathlib import Path
                    from PIL import Image, ImageDraw
                    
                    # Cria uma imagem de teste na Galeria
                    galeria_dir = Path(__file__).resolve().parent.parent / "Galeria"
                    galeria_dir.mkdir(exist_ok=True)
                    
                    cores = ["#ff0000", "#00ff00", "#0000ff", "#ff00ff", "#ffff00", "#00ffff"]
                    img = Image.new("RGB", (800, 800), color=random.choice(cores))
                    draw = ImageDraw.Draw(img)
                    draw.text((300, 380), "TESTE", fill=(255,255,255))
                    
                    test_file = galeria_dir / f"teste_{int(time.time())}.jpg"
                    img.save(test_file)
                    
                    self._send_json({"status": "ok", "file": str(test_file)})
                except Exception as e:
                    self.send_error(500, f"Error: {e}")
                return

            if path.endswith("/api/settings"):
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    settings = json.loads(post_data)
                    if "cols" in settings:
                        try: self.server_ref.mosaic_cols = int(settings["cols"])
                        except: pass
                    if "rows" in settings:
                        try: self.server_ref.mosaic_rows = int(settings["rows"])
                        except: pass
                    if "opacity" in settings:
                        try: self.server_ref.opacity = float(settings["opacity"])
                        except: pass
                    if "width" in settings:
                        try: self.server_ref.mosaic_width = int(settings["width"])
                        except: pass
                    if "height" in settings:
                        try: self.server_ref.mosaic_height = int(settings["height"])
                        except: pass
                    if "animation_mode" in settings: self.server_ref.animation_mode = str(settings["animation_mode"])
                    if "animation_intensity" in settings: self.server_ref.animation_intensity = str(settings["animation_intensity"])
                    if "duplicate_fill" in settings: self.server_ref.duplicate_fill = bool(settings["duplicate_fill"])
                    
                    if "backdrop_base64" in settings:
                        import base64
                        from pathlib import Path
                        b64_str = settings["backdrop_base64"]
                        if "," in b64_str:
                            b64_str = b64_str.split(",", 1)[1]
                        img_data = base64.b64decode(b64_str)
                        assets_dir = Path(__file__).resolve().parent.parent / "assets" / "backgrounds"
                        assets_dir.mkdir(parents=True, exist_ok=True)
                        bg_path = assets_dir / "fundo_dinamico.jpg"
                        bg_path.write_bytes(img_data)
                        self.server_ref.backdrop_path = bg_path
                    
                    self._send_json({"status": "ok"})
                except Exception as e:
                    self.send_error(400, f"Bad Request: {e}")
                return

            if path.endswith("/api/hsbc/generate"):
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    import base64
                    import uuid
                    from pathlib import Path
                    from hsbc_animator import generate_hsbc_video
                    
                    payload = json.loads(post_data)
                    bg_b64 = payload.get("bg_base64")
                    if not bg_b64:
                        self._send_json({"ok": False, "msg": "Missing background image"})
                        return
                        
                    if "," in bg_b64:
                        bg_b64 = bg_b64.split(",", 1)[1]
                        
                    # Salva a imagem de fundo recebida
                    temp_dir = _PROJECT_DIR / "temp_hsbc"
                    temp_dir.mkdir(exist_ok=True)
                    bg_path = temp_dir / "hsbc_bg.jpg"
                    bg_path.write_bytes(base64.b64decode(bg_b64))
                    
                    # Usa a pasta Galeria original do projeto
                    galeria_dir = _PROJECT_DIR / "Galeria"
                    base_images = list(galeria_dir.glob("*.*"))
                    if not base_images:
                        self._send_json({"ok": False, "msg": "Galeria vazia!"})
                        return
                        
                    videos_dir = _PROJECT_DIR / "assets" / "videos"
                    videos_dir.mkdir(parents=True, exist_ok=True)
                    video_name = f"hsbc_{uuid.uuid4().hex[:6]}.mp4"
                    out_path = videos_dir / video_name
                    
                    generate_hsbc_video(bg_path, base_images, out_path)
                    
                    self._send_json({"ok": True, "url": f"/video/assets/videos/{video_name}"})
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self._send_json({"ok": False, "msg": str(e)})
                return

            self.send_error(404)
        except Exception as e:
            try: self.send_error(500)
            except: pass

    def do_GET(self):  # noqa: N802
        try:
            self._do_get_inner()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
        except OSError:
            return
        except Exception:
            try:
                self.send_error(500)
            except Exception:
                pass

    def _do_get_inner(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path in ("/", "/index.html"):
            html = _load_html_page("telao.html").encode("utf-8")
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Content-Length', str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if path == "/telao":
            html = _load_html_page("telao.html").encode("utf-8")
            self._send_bytes(html, "text/html; charset=utf-8")
            return

        if path == "/admin":
            html = _load_html_page("admin.html").encode("utf-8")
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Content-Length', str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if path == "/api/state":
            self._send_json(self.server_ref.build_state())
            return

        if path == "/api/mosaic/delta":
            qs = parse_qs(parsed.query or "")
            since_raw = (qs.get("since") or ["0"])[0]
            try:
                since = max(0, int(since_raw))
            except (TypeError, ValueError):
                since = 0
            self._send_json(self.server_ref.build_mosaic_delta(since))
            return

        if path == "/api/version":
            self._send_json({"version": _frontend_version()})
            return

        if path.startswith("/mosaic/"):
            name = path.removeprefix("/mosaic/").split("?")[0]
            file_path = (self.server_ref.mosaic_dir / name).resolve()
            mosaic_root = self.server_ref.mosaic_dir.resolve()
            if not str(file_path).startswith(str(mosaic_root)) or not file_path.is_file():
                self.send_error(404)
                return
            body, ctype = self.server_ref.read_mosaic_file_bytes(file_path)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._safe_write(self.wfile, body)
            return

        if path in ("/background", "/backdrop"):
            bg = self.server_ref.backdrop_path
            if bg is None or not bg.exists():
                self.send_error(404)
                return
            body = bg.read_bytes()
            ctype = mimetypes.guess_type(str(bg))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._safe_write(self.wfile, body)
            return

        if path == "/overlay":
            ov = self.server_ref.overlay_path
            if ov is None or not ov.exists():
                self.send_error(404)
                return
            body = ov.read_bytes()
            ctype = mimetypes.guess_type(str(ov))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._safe_write(self.wfile, body)
            return

        if path == "/api/video/status":
            self._send_json(self.server_ref.build_video_status())
            return

        if path == "/api/video/clear":
            self.server_ref.clear_video_queue()
            self._send_json({"ok": True})
            return

        if path == "/api/video/test":
            video_file = _PROJECT_DIR / "assets/videos" / "mosaico_video.mp4"
            if video_file.exists():
                with self.server_ref._video_lock:
                    self.server_ref._video_to_play = "completo"
                    self.server_ref._video_to_play_until = time.time() + 600.0
                self._send_json({"ok": True, "msg": "video queued"})
            else:
                self._send_json({"ok": False, "msg": "mosaico_video.mp4 nao encontrado"})
            return

        if path.startswith("/video/"):
            name = path.removeprefix("/video/").split("?")[0]
            if not name.endswith(".mp4") or "/" in name or ".." in name:
                self.send_error(404)
                return
            video_path = (_PROJECT_DIR / name).resolve()
            if not str(video_path).startswith(str(_PROJECT_DIR.resolve())) or not video_path.is_file():
                self.send_error(404)
                return
            self._serve_video(video_path)
            return

        self.send_error(404)


class SimpleMosaicFrontend:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.mosaic_dir = _PROJECT_DIR / "MOSAIC"
        self.backdrop_path: Path | None = None
        self.overlay_path: Path | None = None

        # Configs sincronizadas com a interface principal.
        self.animation_mode: str = "mosaic_fly_in"
        self.animation_intensity: str = "medio"
        self.action_signal: dict = {"command": "", "ts": 0.0}
        self.tile_interval_ms: int = 360
        self.tile_size_px: int = 38
        self.mosaic_fullscreen: bool = True
        self.duplicate_fill: bool = False
        self.overlay_telao_enabled: bool = True
        self.mosaic_width: int = TELAO_LARGURA_PX
        self.mosaic_height: int = TELAO_ALTURA_PX
        self.mosaic_cols: int = TELAO_COLUNAS
        self.mosaic_rows: int = TELAO_LINHAS
        self.spotlight_min_gap_ms: int = TELAO_SPOTLIGHT_GAP_MS

        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._watcher_thread: threading.Thread | None = None
        self._is_running = False
        self._opened_once = False
        # Incrementado quando chega nova pastilha (injecao/monitor) para o cliente re-pollar.
        self._mosaic_generation: int = 0
        self._images_list_cache: list[str] | None = None
        self._images_list_mtime: int | None = None
        self._images_cache_gen: int = -1
        self._overlay_revision: int = 0
        self._backdrop_revision: int = 0
        self._catalog_lock = threading.Lock()
        self._snapshots_after_gen: dict[int, frozenset[str]] = {0: frozenset()}
        self._serve_cache_dir = self.mosaic_dir / ".serve_cache"

        self._video_to_play: str | None = None
        self._video_to_play_until: float = 0.0
        self._video_intro_ready: bool = False
        self._video_outro_ready: bool = False
        self._video_completo_ready: bool = False
        self._video_generating: bool = False
        self._mosaic_was_full: bool = False
        self._video_lock = threading.Lock()

    def reset_mosaic_catalog(self) -> None:
        """Zera lista em cache apos limpar a pasta MOSAIC."""
        with self._video_lock:
            self._video_completo_ready = False
            self._video_to_play = None
            self._mosaic_was_full = False
        with self._catalog_lock:
            self._mosaic_generation = 0
            self._images_list_cache = None
            self._images_list_mtime = None
            self._images_cache_gen = -1
            self._snapshots_after_gen = {0: frozenset()}
        try:
            if self._serve_cache_dir.is_dir():
                shutil.rmtree(self._serve_cache_dir, ignore_errors=True)
        except OSError:
            pass
        self._overlay_revision = 0

    def _overlay_cache_token(self) -> str:
        if self.overlay_path is None or not self.overlay_path.exists():
            return ""
        try:
            st = self.overlay_path.stat()
            return f"{int(st.st_mtime_ns)}-{int(st.st_size)}"
        except OSError:
            return str(self.overlay_path.resolve())

    def _backdrop_cache_token(self) -> str:
        if self.backdrop_path is None or not self.backdrop_path.exists():
            return ""
        try:
            st = self.backdrop_path.stat()
            return f"{int(st.st_mtime_ns)}-{int(st.st_size)}"
        except OSError:
            return str(self.backdrop_path.resolve())

    def _backdrop_dimensions(self) -> tuple[int, int] | None:
        return self._image_dimensions(self.backdrop_path)

    def update_settings(
        self,
        animation_mode: str | None = None,
        animation_intensity: str | None = None,
        tile_interval_ms: int | None = None,
        tile_size_px: int | None = None,
        mosaic_fullscreen: bool | None = None,
        duplicate_fill: bool | None = None,
        overlay_telao_enabled: bool | None = None,
    ):
        if animation_mode is not None:
            s = str(animation_mode).strip().lower()
            if s:
                self.animation_mode = s
        if animation_intensity is not None:
            s = str(animation_intensity).strip().lower()
            if s:
                self.animation_intensity = s
        if tile_interval_ms is not None:
            try:
                self.tile_interval_ms = max(80, min(8000, int(tile_interval_ms)))
            except (TypeError, ValueError):
                pass
        if tile_size_px is not None:
            try:
                self.tile_size_px = max(40, min(80, int(tile_size_px)))
            except (TypeError, ValueError):
                pass
        if mosaic_fullscreen is not None:
            self.mosaic_fullscreen = bool(mosaic_fullscreen)
        if duplicate_fill is not None:
            self.duplicate_fill = bool(duplicate_fill)
        if overlay_telao_enabled is not None:
            self.overlay_telao_enabled = bool(overlay_telao_enabled)

    def notify_mosaic_changed(self) -> None:
        """Chame apos cada nova imagem no MOSAIC para o cliente re-pollar."""
        entries = self._scan_mosaic_entries()
        ids = frozenset(e["id"] for e in entries)
        with self._catalog_lock:
            try:
                self._mosaic_generation = int(self._mosaic_generation) + 1
            except (TypeError, ValueError):
                self._mosaic_generation = 1
            gen = int(self._mosaic_generation)
            self._snapshots_after_gen[gen] = ids
            if 0 not in self._snapshots_after_gen:
                self._snapshots_after_gen[0] = frozenset()
            if len(self._snapshots_after_gen) > 500:
                for g in sorted(self._snapshots_after_gen.keys())[:-320]:
                    if g > 0:
                        self._snapshots_after_gen.pop(g, None)
        self._images_list_cache = None
        self._images_list_mtime = None

        count = len(entries)
        with self._video_lock:
            if count >= 500 and not self._mosaic_was_full:
                self._mosaic_was_full = True
                threading.Thread(target=self._generate_and_play_video, daemon=True).start()
            elif count < 500:
                self._mosaic_was_full = False

    def _mosaic_order_key(self, path: Path):
        m = re.match(r"^img(\d+)$", path.stem.lower())
        if m:
            return (0, int(m.group(1)), path.name.lower())
        try:
            mt = path.stat().st_mtime_ns
        except OSError:
            mt = 0
        return (1, mt, path.name.lower())

    def _scan_mosaic_entries(self) -> list[dict]:
        gen = int(self._mosaic_generation)
        entries: list[dict] = []
        try:
            for p in sorted(self.mosaic_dir.iterdir(), key=self._mosaic_order_key):
                if not _is_image_file(p) or not p.exists():
                    continue
                if p.name.startswith("."):
                    continue
                try:
                    mt = int(p.stat().st_mtime_ns)
                except OSError:
                    mt = 0
                entries.append(
                    {
                        "id": p.name,
                        "name": p.name,
                        "order": len(entries),
                        "mtime_ns": mt,
                        "url": self._mosaic_url_for(p.name, gen, mt),
                    }
                )
        except OSError:
            entries = []
        return entries

    def _mosaic_url_for(self, name: str, gen: int, mtime_ns: int) -> str:
        return f"/mosaic/{quote(name)}?v={gen}&t={mtime_ns}"

    def _settings_payload(self) -> dict:
        return {
            "animation_mode": self.animation_mode,
            "animation_intensity": self.animation_intensity,
            "tile_interval_ms": self.tile_interval_ms,
            "tile_size_px": self.tile_size_px,
            "mosaic_fullscreen": self.mosaic_fullscreen,
            "duplicate_fill": self.duplicate_fill,
            "overlay_telao_enabled": self.overlay_telao_enabled,
            "mosaic_width": self.mosaic_width,
            "mosaic_height": self.mosaic_height,
            "mosaic_cols": self.mosaic_cols,
            "mosaic_rows": self.mosaic_rows,
            "spotlight_min_gap_ms": self.spotlight_min_gap_ms,
        }

    def _snapshot_ids_at_or_before(self, since: int) -> frozenset[str] | None:
        """Estado do catálogo na geração pedida ou na anterior mais próxima."""
        with self._catalog_lock:
            if since <= 0:
                return self._snapshots_after_gen.get(0, frozenset())
            if since in self._snapshots_after_gen:
                return self._snapshots_after_gen[since]
            prior = [g for g in self._snapshots_after_gen if g < since]
            if not prior:
                return None
            return self._snapshots_after_gen[max(prior)]

    def build_mosaic_delta(self, since: int) -> dict:
        since = max(0, int(since))
        entries = self._scan_mosaic_entries()
        ids_now = [e["id"] for e in entries]
        set_now = frozenset(ids_now)
        current_gen = int(self._mosaic_generation)
        catalog_fp = "|".join(sorted(ids_now))

        ids_after_since = self._snapshot_ids_at_or_before(since)
        full_sync = ids_after_since is None or (
            self.duplicate_fill and since == 0 and current_gen > 0
        )
        if ids_after_since is None:
            ids_after_since = frozenset()

        if (
            not full_sync
            and since == current_gen
            and not any(i for i in ids_now if i not in ids_after_since)
            and not any(i for i in ids_after_since if i not in set_now)
        ):
            payload = self._art_payload()
            payload.update(
                {
                    "mosaic_generation": current_gen,
                    "since": since,
                    "unchanged": True,
                    "full_sync": False,
                    "added": [],
                    "removed": [],
                    "total": len(entries),
                    "images": [], "action": self.action_signal,
                    "catalog_fp": catalog_fp,
                    "settings": self._settings_payload(),
                }
            )
            return payload

        if full_sync:
            urls = [e["url"] for e in entries]
            payload = self._art_payload()
            payload.update(
                {
                    "mosaic_generation": current_gen,
                    "since": since,
                    "full_sync": True,
                    "added": [],
                    "removed": [],
                    "total": len(entries),
                    "images": urls, "action": self.action_signal,
                    "catalog_fp": catalog_fp,
                    "settings": self._settings_payload(),
                }
            )
            return payload

        added_ids = [i for i in ids_now if i not in ids_after_since]
        removed_ids = sorted(i for i in ids_after_since if i not in set_now)
        added = [e for e in entries if e["id"] in added_ids]
        removed = [
            {
                "id": rid,
                "url": self._mosaic_url_for(rid, current_gen, 0),
            }
            for rid in removed_ids
        ]

        payload = self._art_payload()
        payload.update(
            {
                "mosaic_generation": current_gen,
                "since": since,
                "full_sync": False,
                "added": added,
                "removed": removed,
                "total": len(entries),
                "images": [], "action": self.action_signal,
                "catalog_fp": catalog_fp,
                "settings": self._settings_payload(),
            }
        )
        return payload

    def _art_payload(self) -> dict:
        bg_token = self._backdrop_cache_token()
        backdrop_url = None
        if bg_token:
            backdrop_url = (
                f"/backdrop?r={int(self._backdrop_revision)}&m={quote(bg_token, safe='')}"
            )
        ov_token = self._overlay_cache_token()
        overlay_url = None
        if ov_token:
            overlay_url = (
                f"/overlay?r={int(self._overlay_revision)}&m={quote(ov_token, safe='')}"
            )
        bg_dims = self._backdrop_dimensions()
        return {
            "background": backdrop_url,
            "backdrop": backdrop_url,
            "background_width": bg_dims[0] if bg_dims else None,
            "background_height": bg_dims[1] if bg_dims else None,
            "backdrop_revision": int(self._backdrop_revision),
            "overlay": overlay_url,
            "overlay_revision": int(self._overlay_revision),
        }

    def read_mosaic_file_bytes(self, file_path: Path) -> tuple[bytes, str]:
        if not needs_mosaic_normalize(file_path):
            body = file_path.read_bytes()
            ctype = mimetypes.guess_type(str(file_path))[0] or _guess_image_mime(body)
            return body, ctype

        try:
            st = file_path.stat()
            tag = f"{int(st.st_mtime_ns)}_{int(st.st_size)}"
        except OSError:
            tag = "0"
        cache_path = self._serve_cache_dir / f"{file_path.name}.{tag}.jpg"
        if cache_path.is_file():
            return cache_path.read_bytes(), "image/jpeg"

        body, ctype = oriented_image_bytes(file_path)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(body)
        except OSError:
            pass
        return body, ctype

    def _list_mosaic_image_urls(self) -> list[str]:
        try:
            mtime_ns = int(self.mosaic_dir.stat().st_mtime_ns)
        except OSError:
            mtime_ns = -1

        if self._images_list_cache is not None:
            if getattr(self, "_images_cache_gen", -1) != self._mosaic_generation:
                pass
            elif self._images_list_mtime == mtime_ns:
                return self._images_list_cache

        images = [e["url"] for e in self._scan_mosaic_entries()]

        self._images_list_cache = images
        self._images_list_mtime = mtime_ns
        self._images_cache_gen = gen
        return images

    def _image_dimensions(self, path: Path | None) -> tuple[int, int] | None:
        if path is None or not path.exists():
            return None
        try:
            from PIL import Image

            with Image.open(path) as im:
                w, h = im.size
                return int(w), int(h)
        except Exception:
            return None

    def build_state(self) -> dict:
        payload = self._art_payload()
        payload.update(
            {
                "images": self._list_mosaic_image_urls(),
                "action": self.server_ref.action_signal,
                "mosaic_generation": int(self._mosaic_generation),
                "settings": self._settings_payload(),
            }
        )
        return payload

    @staticmethod
    def _reject_backdrop_path(path: Path | None) -> Path | None:
        if path is None or not path.is_file():
            return None
        stem = path.stem.lower()
        if stem.startswith("fundo_evento") or stem.startswith("fundobaixo"):
            return None
        if "halo" in stem:
            return None
        return path

    def set_backdrop_path(self, backdrop_path: str | None = None, background_path: str | None = None):
        path = backdrop_path or background_path
        if path:
            p = self._reject_backdrop_path(Path(path))
            self.backdrop_path = p
        else:
            self.backdrop_path = None
        self._backdrop_revision = int(self._backdrop_revision) + 1

    def set_overlay_path(self, overlay_path: str | None = None):
        if overlay_path:
            p = Path(overlay_path)
            self.overlay_path = p if p.exists() else None
        else:
            self.overlay_path = None
        self._overlay_revision = int(self._overlay_revision) + 1
        self._images_list_cache = None
        if self._is_running:
            self.notify_mosaic_changed()

    def set_art_paths(self, backdrop_path: str | None = None, overlay_path: str | None = None):
        self.set_backdrop_path(backdrop_path)
        self.set_overlay_path(overlay_path)

    def _watch_mosaic_loop(self) -> None:
        import time as _time
        while self._is_running:
            try:
                self.notify_mosaic_changed()
            except Exception:
                pass
            _time.sleep(10)

    def start(
        self,
        overlay_path: str | None = None,
        backdrop_path: str | None = None,
        background_path: str | None = None,
        open_browser: bool = True,
    ):
        self.set_backdrop_path(backdrop_path, background_path=background_path)
        self.set_overlay_path(overlay_path)

        if not self._is_running:
            handler = type("DynamicFrontendHandler", (_FrontendHandler,), {})
            handler.server_ref = self
            self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
            self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            self._thread.start()
            self._is_running = True
            self._watcher_thread = threading.Thread(target=self._watch_mosaic_loop, daemon=True)
            self._watcher_thread.start()

        if open_browser and not self._opened_once:
            webbrowser.open(f"http://{self.host}:{self.port}", new=1)
            self._opened_once = True

    def stop(self):
        if not self._is_running:
            return
        assert self._httpd is not None
        self._is_running = False
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None

    def set_videos_ready(self, intro: bool = False, outro: bool = False, completo: bool = False) -> None:
        with self._video_lock:
            self._video_intro_ready = intro
            self._video_outro_ready = outro
            self._video_completo_ready = completo

    def queue_video(self, which: str) -> None:
        with self._video_lock:
            self._video_to_play = which
            self._video_to_play_until = time.time() + 60.0

    def clear_video_queue(self) -> None:
        with self._video_lock:
            self._video_to_play = None

    def build_video_status(self) -> dict:
        with self._video_lock:
            play = None
            if self._video_to_play and time.time() < self._video_to_play_until:
                play = self._video_to_play
            return {
                "play": play,
                "ready_intro": self._video_intro_ready,
                "ready_outro": self._video_outro_ready,
                "ready_completo": self._video_completo_ready,
            }

    def _generate_and_play_video(self) -> None:
        """Gera mosaico_video.mp4 em background e dispara reprodução ao concluir."""
        import subprocess, sys as _sys
        with self._video_lock:
            if self._video_generating:
                return
            self._video_generating = True
        try:
            _video_backdrop = _PROJECT_DIR / "assets/backgrounds/fundo preto.jpg"
            _video_overlay  = _PROJECT_DIR / "assets/backgrounds/essa é a certa.png"
            cmd = [_sys.executable, str(_PROJECT_DIR / "criar_video_mosaico.py"),
                   "--pasta", str(self.mosaic_dir),
                   "--out-dir", str(_PROJECT_DIR / "assets/videos")]
            if _video_backdrop.exists():
                cmd.extend(["--backdrop", str(_video_backdrop)])
            if _video_overlay.exists():
                cmd.extend(["--overlay", str(_video_overlay)])
            ok = False
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for line in proc.stdout:
                if line.strip() == "DONE:completo:ok":
                    ok = True
            proc.wait()
            if ok:
                with self._video_lock:
                    self._video_completo_ready = True
                    self._video_to_play = "completo"
                    self._video_to_play_until = time.time() + 600.0
        finally:
            with self._video_lock:
                self._video_generating = False

