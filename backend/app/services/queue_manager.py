from typing import List, Optional
import time

class QueueManager:
    """
    Gerenciador da Fila de Moderação do Evento (Pending -> Approved / Rejected).
    """
    def __init__(self):
        self.pending_queue: List[dict] = []
        self.approved_photos: List[dict] = []
        self.rejected_photos: List[dict] = []
        self.brand_fallbacks: List[dict] = []
        # Hashes do conteúdo já ingerido nesta rodada. A cabine publica a mesma
        # foto no bucket com dois nomes (`img_Nmasked` e `originals/...`), o que
        # colocava a pessoa duas vezes no mosaico. Zera junto com o mosaico.
        self.seen_hashes: dict = {}

    def is_duplicate(self, content_hash: str) -> Optional[str]:
        """Retorna o photo_id já ingerido com esse conteúdo, ou None."""
        return self.seen_hashes.get(content_hash)

    def register_hash(self, content_hash: str, photo_id: str) -> None:
        self.seen_hashes.setdefault(content_hash, photo_id)

    def add_pending(self, photo_id: str, url: str, local_path: str) -> dict:
        item = {
            "id": photo_id,
            "url": url,
            "local_path": local_path,
            "status": "PENDING",
            "timestamp": time.time()
        }
        self.pending_queue.append(item)
        return item

    def approve(self, photo_id: str) -> Optional[dict]:
        item = next((p for p in self.pending_queue if p["id"] == photo_id), None)
        if item:
            self.pending_queue.remove(item)
            item["status"] = "APPROVED"
            self.approved_photos.append(item)
            return item
        return None

    def reject(self, photo_id: str) -> Optional[dict]:
        item = next((p for p in self.pending_queue if p["id"] == photo_id), None)
        if item:
            self.pending_queue.remove(item)
            item["status"] = "REJECTED"
            self.rejected_photos.append(item)
            return item
        return None

    def add_brand_fallback(self, photo_id: str, url: str, local_path: str) -> dict:
        item = {
            "id": photo_id,
            "url": url,
            "local_path": local_path,
            "status": "FALLBACK"
        }
        self.brand_fallbacks.append(item)
        return item

    def get_all_approved_and_fallbacks(self) -> List[dict]:
        return self.approved_photos + self.brand_fallbacks
