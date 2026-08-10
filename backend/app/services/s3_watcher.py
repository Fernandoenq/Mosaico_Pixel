import time
import os
import json
import threading
import boto3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class S3Watcher:
    def __init__(self, download_dir: Path, poll_interval: int = 5):
        self.download_dir = download_dir
        self.poll_interval = poll_interval
        
        self.bucket_name = os.getenv("S3_BUCKET")
        self.access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = os.getenv("AWS_REGION")
        
        self._stop_event = threading.Event()
        self._thread = None

        # Chaves já importadas, PERSISTIDAS em disco. Ficavam só em memória: a
        # cada restart do backend o watcher rebaixava o bucket inteiro e o
        # histórico do evento voltava a pousar no mosaico como se fosse novo.
        # Apagar este arquivo é o jeito de reimportar tudo de propósito.
        self.state_path = download_dir.parent / "s3_seen.json"
        self._state_lock = threading.Lock()
        self.seen_keys = self._load_seen()
        
        # We only initialize S3 client if we have credentials
        if self.bucket_name and self.access_key and self.secret_key:
            try:
                self.s3 = boto3.client(
                    "s3",
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region,
                )
                print(f"[S3Watcher] S3 Client initialized. Bucket: {self.bucket_name}")
            except Exception as e:
                print(f"[S3Watcher] Error initializing S3 client: {e}")
                self.s3 = None
        else:
            print("[S3Watcher] Missing S3 credentials in .env. S3 Watcher disabled.")
            self.s3 = None

    def start(self):
        if not self.s3:
            return
            
        if self._thread is not None and self._thread.is_alive():
            return
            
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("[S3Watcher] Started.")

    def stop(self):
        if self._thread is not None:
            self._stop_event.set()
            # Teto no join: a thread pode estar dentro de um download lento e não
            # pode pendurar o shutdown do backend.
            self._thread.join(timeout=3)
            print("[S3Watcher] Stopped.")

    def _run(self):
        while not self._stop_event.is_set():
            try:
                response = self.s3.list_objects_v2(Bucket=self.bucket_name)
                if 'Contents' in response:
                    objetos = sorted(response['Contents'], key=lambda obj: obj['LastModified'])
                    novas = False
                    for obj in objetos:
                        key = obj['Key']
                        # Only download image files
                        if key not in self.seen_keys and key.lower().endswith(('.png', '.jpg', '.jpeg')):
                            self.seen_keys.add(key)
                            self._download_file(key)
                            novas = True
                    if novas:
                        self._save_seen()
            except Exception as e:
                print(f"[S3Watcher] Polling error: {e}")
                
            time.sleep(self.poll_interval)

    def esquecer_tudo(self):
        """
        Esquece as chaves já importadas, em memória e em disco.

        Apagar só o arquivo não bastava: `seen_keys` é carregado uma única vez,
        na construção, e o watcher segue rodando com a lista antiga na memória
        — o bucket novo nunca seria reimportado sem reiniciar o backend.
        """
        with self._state_lock:
            self.seen_keys = set()
            try:
                self.state_path.unlink(missing_ok=True)
            except OSError as e:
                print(f"[S3Watcher] Falha ao apagar o estado: {e}")

    def _load_seen(self) -> set:
        try:
            with self.state_path.open("r", encoding="utf-8") as handle:
                dados = json.load(handle)
            chaves = set(dados.get("keys", []))
            print(f"[S3Watcher] {len(chaves)} chave(s) já importada(s) carregadas de {self.state_path.name}")
            return chaves
        except FileNotFoundError:
            return set()
        except (OSError, json.JSONDecodeError) as e:
            print(f"[S3Watcher] Estado ilegível ({e}); começando do zero.")
            return set()

    def _save_seen(self):
        """Escrita atômica — um JSON truncado aqui faria o bucket inteiro voltar."""
        with self._state_lock:
            try:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.state_path.with_suffix(".tmp")
                with tmp.open("w", encoding="utf-8") as handle:
                    json.dump({"keys": sorted(self.seen_keys)}, handle, ensure_ascii=False, indent=2)
                os.replace(tmp, self.state_path)
            except OSError as e:
                print(f"[S3Watcher] Falha ao salvar estado: {e}")

    def _download_file(self, key: str):
        safe_name = key.replace("/", "_")
        dest_path = self.download_dir / safe_name

        if dest_path.exists():
            print(f"[S3Watcher] Já existe, pulando download: {dest_path}")
            return

        try:
            self.s3.download_file(self.bucket_name, key, str(dest_path))
            print(f"[S3Watcher] Downloaded {key} -> {dest_path}")
        except Exception as e:
            print(f"[S3Watcher] Failed to download {key}: {e}")
