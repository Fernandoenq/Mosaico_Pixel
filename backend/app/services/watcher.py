import time
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Callable

class HotFolderHandler(FileSystemEventHandler):
    def __init__(self, on_new_file_callback: Callable[[Path], None]):
        super().__init__()
        self.on_new_file_callback = on_new_file_callback
        self._processed = set()

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            if str(path) not in self._processed:
                self._processed.add(str(path))
                # Aguarda gravação completa do arquivo no disco
                time.sleep(0.3)
                self.on_new_file_callback(path)

class HotFolderWatcher:
    def __init__(self, watch_dir: Path, on_new_file_callback: Callable[[Path], None]):
        self.watch_dir = watch_dir
        self.on_new_file_callback = on_new_file_callback
        self.observer = None

    def start(self):
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        event_handler = HotFolderHandler(self.on_new_file_callback)
        self.observer = Observer()
        self.observer.schedule(event_handler, str(self.watch_dir), recursive=False)
        self.observer.start()
        print(f"[HotFolderWatcher] Monitorando diretório local: {self.watch_dir}")

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            print("[HotFolderWatcher] Parado.")

    def update_dir(self, new_dir: Path):
        self.stop()
        self.watch_dir = Path(new_dir)
        self.start()
