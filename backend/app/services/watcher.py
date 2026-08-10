import os
import time
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Callable

IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.png', '.webp')

# Intervalo da varredura de segurança. Nenhum backend de eventos do SO é 100%
# confiável (renomeios, cópias por rede, picos de I/O), e numa ativação ao vivo
# uma foto perdida é uma foto que nunca entra no telão.
RESCAN_INTERVAL_SECONDS = 10


def _wait_until_stable(path: Path, timeout: float = 10.0) -> bool:
    """
    Espera o arquivo parar de crescer antes de entregá-lo ao processamento.
    Substitui o `sleep(0.3)` fixo, que estourava em foto grande vinda da rede.
    """
    deadline = time.monotonic() + timeout
    last_size = -1
    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size > 0 and size == last_size:
            return True
        last_size = size
        time.sleep(0.25)
    return path.exists()


class HotFolderHandler(FileSystemEventHandler):
    def __init__(self, on_new_file_callback: Callable[[Path], None]):
        super().__init__()
        self.on_new_file_callback = on_new_file_callback
        self._processed: set[str] = set()
        self._lock = threading.Lock()

    def claim(self, path: Path) -> bool:
        """Marca o arquivo como nosso. False = alguém já pegou (evento duplicado)."""
        key = str(path).lower()
        with self._lock:
            if key in self._processed:
                return False
            self._processed.add(key)
            return True

    def handle(self, path: Path):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            return
        if not self.claim(path):
            return
        if not _wait_until_stable(path):
            # Não conseguiu estabilizar: solta a marca para a varredura tentar de novo.
            with self._lock:
                self._processed.discard(str(path).lower())
            return
        self.on_new_file_callback(path)

    def on_created(self, event):
        if event.is_directory:
            return
        self.handle(Path(event.src_path))

    def on_moved(self, event):
        """
        O download do S3 (boto3) grava num arquivo temporário e RENOMEIA para o
        nome final — isso emite `on_moved`, não `on_created`. Sem este handler a
        foto caía na pasta e o watcher a ignorava em silêncio; ela só virava tile
        no próximo restart do backend, via varredura inicial.
        """
        if event.is_directory:
            return
        self.handle(Path(event.dest_path))


class HotFolderWatcher:
    def __init__(self, watch_dir: Path, on_new_file_callback: Callable[[Path], None]):
        self.watch_dir = Path(watch_dir)
        self.on_new_file_callback = on_new_file_callback
        self.observer = None
        self.handler = None
        self._stop_event = threading.Event()
        self._rescan_thread = None

    def _scan_once(self):
        """Processa em ordem cronológica tudo que estiver na pasta e ainda não foi visto."""
        try:
            entries = sorted(self.watch_dir.glob("*.*"), key=lambda p: p.stat().st_mtime)
        except OSError as exc:
            print(f"[HotFolderWatcher] Falha ao varrer {self.watch_dir}: {exc}")
            return
        for path in entries:
            if self._stop_event.is_set():
                return
            try:
                self.handler.handle(path)
            except Exception as exc:
                print(f"[HotFolderWatcher] Erro ao processar {path.name}: {exc}")

    def _rescan_loop(self):
        self._scan_once()  # varredura inicial: recupera o que chegou com o backend parado
        while not self._stop_event.wait(RESCAN_INTERVAL_SECONDS):
            self._scan_once()

    def start(self):
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        self.handler = HotFolderHandler(self.on_new_file_callback)

        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.watch_dir), recursive=False)
        self.observer.start()
        print(f"[HotFolderWatcher] Monitorando diretório local: {self.watch_dir}")

        self._rescan_thread = threading.Thread(target=self._rescan_loop, daemon=True)
        self._rescan_thread.start()

    def stop(self):
        self._stop_event.set()
        if self.observer:
            self.observer.stop()
            # join com teto: um observer que não responde não pode segurar o
            # shutdown do backend (é daemon, o processo o leva embora).
            self.observer.join(timeout=3)
            self.observer = None
            print("[HotFolderWatcher] Parado.")
        if self._rescan_thread:
            self._rescan_thread.join(timeout=2)
            self._rescan_thread = None

    def update_dir(self, new_dir: Path):
        new_dir = Path(new_dir)
        if new_dir == self.watch_dir and self.observer is not None:
            return  # já estamos nesta pasta; reiniciar só reprocessaria tudo à toa
        self.stop()
        self.watch_dir = new_dir
        self.start()
