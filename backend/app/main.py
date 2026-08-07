from fastapi import FastAPI, BackgroundTasks, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import cv2
import numpy as np
from pathlib import Path
import json
import asyncio
from typing import List

from app.core.config import settings
from app.core.state import state
from app.services.smart_crop import smart_crop_face
from app.services.watcher import HotFolderWatcher
from app.services.print_exporter import export_mosaic_to_print_spooler

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Monta diretório de arquivos estáticos (/storage)
app.mount("/storage", StaticFiles(directory=str(settings.STORAGE_DIR)), name="storage")

ACTIVE_CONNECTIONS: List[WebSocket] = []

async def broadcast_event(event_type: str, payload: dict):
    message = json.dumps({"type": event_type, "payload": payload})
    for connection in list(ACTIVE_CONNECTIONS):
        try:
            await connection.send_text(message)
        except Exception:
            if connection in ACTIVE_CONNECTIONS:
                ACTIVE_CONNECTIONS.remove(connection)

def on_hot_folder_file(file_path: Path):
    """
    Callback disparado quando o HotFolderWatcher detecta uma foto da câmera no diretório.
    """
    img_bgr = cv2.imread(str(file_path))
    if img_bgr is None:
        return
        
    photo_id = f"photo_{file_path.stem}"
    cropped = smart_crop_face(img_bgr, target_size=(250, 250))
    # Grava em TILES_DIR, nunca na pasta assistida — evita realimentar o watcher.
    save_path = settings.TILES_DIR / f"{photo_id}.jpg"
    cv2.imwrite(str(save_path), cropped)

    url = f"/storage/tiles/{photo_id}.jpg"
    item = state.queue_manager.add_pending(photo_id, url, str(save_path))
    
    # Notifica frontend WebSocket sobre nova foto no painel de moderação
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast_event("PHOTO_INGESTED", item), loop)
    except Exception as e:
        print(f"[HotFolder] Erro no broadcast: {e}")

hot_folder_watcher = HotFolderWatcher(settings.HOT_FOLDER_DIR, on_hot_folder_file)

@app.on_event("startup")
async def startup_event():
    hot_folder_watcher.start()

@app.on_event("shutdown")
async def shutdown_event():
    hot_folder_watcher.stop()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ACTIVE_CONNECTIONS.append(websocket)
    # Envia estado inicial do mosaico ao conectar. Inclui config, run_state e os
    # tiles já pousados para que um telão que conecte tarde se recupere inteiro.
    initial_payload = {
        "config": state.config,
        "run_state": state.run_state,
        "rows": state.rows,
        "cols": state.cols,
        "layers": state.layers,
        "target_base_url": state.target_base_url,
        "pending": state.queue_manager.pending_queue,
        "approved": state.queue_manager.approved_photos,
        "placed_tiles": state.placed_tiles_payload(),
    }
    await websocket.send_text(json.dumps({"type": "INIT_STATE", "payload": initial_payload}))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in ACTIVE_CONNECTIONS:
            ACTIVE_CONNECTIONS.remove(websocket)

# --- RUN CONFIG & TRANSPORTE (Aplicar / Play / Pause / Stop / Reset) ---

@app.get("/api/config")
async def get_run_config():
    return {"config": state.config, "run_state": state.run_state}

@app.put("/api/config")
async def put_run_config(patch: dict):
    """
    Recebe a configuração do painel (patch parcial ou completo), valida, persiste
    e retransmite para todos os telões conectados.
    """
    config = state.apply_config(patch)
    if "hotFolderDir" in patch:
        hot_folder_watcher.update_dir(patch["hotFolderDir"])
    await broadcast_event("CONFIG_UPDATED", config)
    return {"status": "success", "config": config, "run_state": state.run_state}

@app.post("/api/run/{action}")
async def run_transport(action: str):
    """
    start  -> o telão passa a aceitar fotos automaticamente
    pause  -> congela a entrada de fotos, mantém o mosaico na tela
    stop   -> volta para idle, mantém o mosaico na tela
    reset  -> limpa tiles e filas para o próximo evento (config é preservada)
    """
    if action == "start":
        state.set_run_state("running")
    elif action == "pause":
        state.set_run_state("paused")
    elif action == "stop":
        state.set_run_state("idle")
    elif action == "reset":
        state.reset_mosaic()
        await broadcast_event("MOSAIC_RESET", {})
    else:
        raise HTTPException(status_code=400, detail=f"Ação de transporte inválida: {action}")

    await broadcast_event("RUN_STATE_CHANGED", {"run_state": state.run_state})
    return {"status": "success", "run_state": state.run_state}

# --- INGESTION ENDPOINTS ---

@app.post("/api/ingest/target-base")
async def upload_target_base(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img_bgr is None:
        raise HTTPException(status_code=400, detail="Arquivo enviado não é uma imagem válida")

    save_path = settings.STORAGE_DIR / "target_base.jpg"
    cv2.imwrite(str(save_path), img_bgr)

    # Atualiza o motor de mosaico com a nova imagem base
    state.set_target_image(img_bgr)
    url = f"/storage/target_base.jpg?t={int(np.random.randint(1000000))}"
    # Passa pela config para persistir em disco e chegar em todos os telões
    state.apply_config({"targetBaseUrl": url})

    await broadcast_event("TARGET_BASE_UPDATED", {"url": url})
    return {"status": "success", "url": url}

@app.get("/api/system/select-folder")
async def select_folder():
    """Abre o seletor de pasta nativo do Windows/SO usando Tkinter via subprocess."""
    import subprocess
    import sys
    
    code = """
import tkinter as tk
from tkinter import filedialog
import sys
import ctypes

root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
root.lift()
root.focus_force()

try:
    HWND = ctypes.windll.user32.GetParent(root.winfo_id())
    ctypes.windll.user32.SetForegroundWindow(HWND)
except Exception:
    pass

path = filedialog.askdirectory(parent=root, title="Selecione a pasta de fotos (Hot Folder)")
root.destroy()
sys.stdout.write(path)
sys.stdout.flush()
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    return {"path": result.stdout.strip()}

@app.post("/api/ingest/upload")
async def upload_photo(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    photo_id = f"photo_{len(state.queue_manager.pending_queue) + len(state.queue_manager.approved_photos) + 1}"
    
    def process_ingestion():
        cropped = smart_crop_face(img_bgr, target_size=(250, 250))
        save_path = settings.TILES_DIR / f"{photo_id}.jpg"
        cv2.imwrite(str(save_path), cropped)

        url = f"/storage/tiles/{photo_id}.jpg"
        item = state.queue_manager.add_pending(photo_id, url, str(save_path))
        asyncio.run(broadcast_event("PHOTO_INGESTED", item))

    if background_tasks:
        background_tasks.add_task(process_ingestion)
    else:
        process_ingestion()
        
    return {"status": "processing", "photo_id": photo_id}

@app.post("/api/ingest/test-gallery-photos")
async def ingest_test_gallery_photos(count: int = 5):
    """
    Carrega fotos reais da pasta Galeria do projeto para teste rápido no estúdio.
    """
    import random
    gallery_dir = settings.BASE_DIR.parent / "Galeria"
    if not gallery_dir.exists():
        gallery_dir = Path("Galeria")

    valid_files = list(gallery_dir.glob("*.jpg")) + list(gallery_dir.glob("*.png"))
    if not valid_files:
        # Fallback se a pasta Galeria não for encontrada no caminho relativo
        gallery_dir = settings.STORAGE_DIR
        valid_files = list(gallery_dir.rglob("*.jpg"))

    if not valid_files:
        raise HTTPException(status_code=404, detail="Nenhuma foto encontrada na pasta Galeria!")

    selected_files = random.sample(valid_files, min(count, len(valid_files)))
    ingested_items = []

    for file_path in selected_files:
        img_bgr = cv2.imread(str(file_path))
        if img_bgr is None:
            continue
        
        photo_id = f"galeria_{file_path.stem[:8]}_{random.randint(1000, 9999)}"
        cropped = smart_crop_face(img_bgr, target_size=(250, 250))
        save_path = settings.TILES_DIR / f"{photo_id}.jpg"
        cv2.imwrite(str(save_path), cropped)

        url = f"/storage/tiles/{photo_id}.jpg"
        item = state.queue_manager.add_pending(photo_id, url, str(save_path))
        ingested_items.append(item)
        await broadcast_event("PHOTO_INGESTED", item)

    return {"status": "success", "count": len(ingested_items), "items": ingested_items}

@app.post("/api/ingest/brand-fallback")
async def upload_brand_fallback(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    photo_id = f"brand_{len(state.queue_manager.brand_fallbacks) + 1}"
    save_path = settings.BRAND_FALLBACKS_DIR / f"{photo_id}.jpg"
    cv2.imwrite(str(save_path), img_bgr)
    
    url = f"/storage/brand_fallbacks/{photo_id}.jpg"
    item = state.queue_manager.add_brand_fallback(photo_id, url, str(save_path))
    await broadcast_event("FALLBACK_ADDED", item)
    return {"status": "success", "item": item}

# --- MODERATION ENDPOINTS ---

@app.get("/api/moderation/pending")
async def get_pending_photos():
    return state.queue_manager.pending_queue

@app.post("/api/moderation/approve/{photo_id}")
async def approve_photo(
    photo_id: str,
    background_tasks: BackgroundTasks,
    fill_sequence: str | None = None,
    force: bool = False,
):
    # O show só pousa fotos sozinho depois do Play. `force=true` é a aprovação
    # manual do operador, que continua valendo em qualquer estado.
    if state.run_state != "running" and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Mosaico não está rodando (run_state={state.run_state}). Dê Play no painel.",
        )

    fill_sequence = fill_sequence or state.fill_sequence

    item = state.queue_manager.approve(photo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Photo not found in pending queue")

    # Captura o loop do evento principal antes de entrar na background task
    main_loop = asyncio.get_event_loop()
    
    def process_matching():
        try:
            img_bgr = cv2.imread(item["local_path"])
            if img_bgr is None:
                print(f"[Approve] ERRO: Imagem não encontrada em {item['local_path']}")
                return
            
            r, c, score = state.engine.find_best_tile_position(
                img_bgr,
                photo_id,
                duplicate_dist_limit=state.duplicate_dist_limit,
                strictness=state.color_strictness,
                fill_sequence=fill_sequence
            )
            
            placement = {
                "photo_id": photo_id,
                "url": item["url"],
                "row": r,
                "col": c,
                "target_x": c * state.engine.tile_w,
                "target_y": r * state.engine.tile_h,
                "score": score
            }
            print(f"[Approve] TILE_PLACED: photo={photo_id} -> row={r}, col={c}, score={score:.2f}")
            
            # Usa run_coroutine_threadsafe para enviar ao loop principal do asyncio
            future = asyncio.run_coroutine_threadsafe(
                broadcast_event("TILE_PLACED", placement),
                main_loop
            )
            future.result(timeout=5.0)  # Aguarda confirmação de envio (timeout 5s)
        except Exception as e:
            print(f"[Approve] ERRO no process_matching: {e}")

    background_tasks.add_task(process_matching)
    return {"status": "approved", "photo_id": photo_id}

@app.post("/api/moderation/reject/{photo_id}")
async def reject_photo(photo_id: str):
    item = state.queue_manager.reject(photo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Photo not found in pending queue")
    await broadcast_event("PHOTO_REJECTED", {"photo_id": photo_id})
    return {"status": "rejected", "photo_id": photo_id}

# --- MOSAIC & STUDIO ENDPOINTS ---

@app.post("/api/mosaic/settings")
async def update_settings(
    rows: int | None = None,
    cols: int | None = None,
    duplicate_dist_limit: int | None = None,
    color_strictness: float | None = None,
):
    """Atalho legado de grade. Escreve na RunConfig, que é a fonte da verdade."""
    patch = {
        "rows": rows,
        "cols": cols,
        "duplicateDistLimit": duplicate_dist_limit,
        "colorStrictness": color_strictness,
    }
    config = state.apply_config({k: v for k, v in patch.items() if v is not None})
    await broadcast_event("CONFIG_UPDATED", config)
    return {
        "status": "success",
        "settings": {
            "rows": config["rows"],
            "cols": config["cols"],
            "duplicate_dist_limit": config["duplicateDistLimit"],
            "color_strictness": config["colorStrictness"],
        },
    }

@app.post("/api/mosaic/auto-fill-duplicates")
async def auto_fill_duplicates(fill_sequence: str | None = None):
    """
    Preenche todas as células vagas restantes no mosaico duplicando fotos aprovadas ou existentes.
    """
    fill_sequence = fill_sequence or state.fill_sequence
    available_photos = state.queue_manager.approved_photos
    if not available_photos:
        tile_files = list(settings.TILES_DIR.glob("*.jpg"))
        if not tile_files:
            raise HTTPException(status_code=400, detail="Nenhuma foto aprovada ou disponível para duplicar!")
        available_photos = [{"photo_id": f.stem, "url": f"/storage/tiles/{f.name}", "local_path": str(f)} for f in tile_files]

    placed_count = 0
    total_cells = state.engine.rows * state.engine.cols

    for i in range(total_cells):
        empty_count = len(state.engine.available_cells())
        if empty_count == 0:
            break

        item = available_photos[i % len(available_photos)]
        img_bgr = cv2.imread(item["local_path"])
        if img_bgr is None:
            continue

        r, c, score = state.engine.find_best_tile_position(
            img_bgr,
            item["photo_id"],
            duplicate_dist_limit=0,
            strictness=state.color_strictness,
            fill_sequence=fill_sequence
        )

        placement = {
            "photo_id": f"{item['photo_id']}_dup_{i}",
            "url": item["url"],
            "row": r,
            "col": c,
            "target_x": c * state.engine.tile_w,
            "target_y": r * state.engine.tile_h,
            "score": score
        }
        placed_count += 1
        await broadcast_event("TILE_PLACED", placement)

    return {"status": "success", "placed_count": placed_count}

@app.post("/api/mosaic/outro")
async def play_mosaic_outro():
    """
    Encerramento do evento: dispersa o mosaico para fora da tela.

    Limpa os ladrilhos no servidor junto com a animação para que o estado bata
    com o que ficou na tela — um telão que reconecte depois não ressuscita o
    mosaico dispersado. A fila e as fotos aprovadas são preservadas.
    """
    tile_count = len(state.engine.placed_tiles)
    await broadcast_event("MOSAIC_OUTRO", {"tile_count": tile_count})
    state.engine.placed_tiles.clear()
    state.engine.locked_tiles.clear()
    return {"status": "success", "dispersed_tiles": tile_count}

@app.post("/api/mosaic/layers")
async def update_layers(layers: List[dict]):
    config = state.apply_config({"layers": layers})
    await broadcast_event("CONFIG_UPDATED", config)
    return {"status": "success", "layers": config["layers"]}

@app.get("/api/mosaic/suggestions/{row}/{col}")
async def get_tile_suggestions(row: int, col: int):
    photos = []
    for item in state.queue_manager.approved_photos + state.queue_manager.brand_fallbacks:
        img_bgr = cv2.imread(item["local_path"])
        if img_bgr is not None:
            photos.append({"id": item["id"], "url": item["url"], "image_bgr": img_bgr})
            
    top_5 = state.engine.get_top_5_suggestions_for_cell(row, col, photos)
    return top_5

@app.post("/api/export/print-spooler")
async def export_to_print_spooler(background_tasks: BackgroundTasks):
    approved_map = {item["id"]: item["local_path"] for item in state.queue_manager.approved_photos + state.queue_manager.brand_fallbacks}
    
    def process_export():
        out_path = export_mosaic_to_print_spooler(
            placed_tiles=state.engine.placed_tiles,
            approved_photos_map=approved_map,
            output_dir=settings.PRINT_OUT_DIR,
            rows=state.rows,
            cols=state.cols
        )
        asyncio.run(broadcast_event("PRINT_EXPORTED", {"path": out_path}))

    background_tasks.add_task(process_export)
    return {"status": "exporting", "message": "High-res composition exporting to print spooler"}

@app.get("/api/mosaic/save-state")
async def save_project_state():
    return {
        "config": state.config,
        "run_state": state.run_state,
        "placed_tiles": {f"{r}_{c}": pid for (r, c), pid in state.engine.placed_tiles.items()},
        "locked_tiles": [f"{r}_{c}" for (r, c) in state.engine.locked_tiles]
    }
