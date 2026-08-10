from fastapi import FastAPI, BackgroundTasks, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import uuid
import time
import hashlib
import threading
from app.services.video_export import run_export_video_task, exports
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
from app.services.s3_watcher import S3Watcher
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

# Serializa a ingestão: watcher e uploads do painel entram por threads distintas
# e disputariam o mesmo par (checar duplicata -> escolher célula).
_INGEST_LOCK = threading.Lock()

# Lado do recorte gravado em storage/tiles. Era 250, mas é este mesmo arquivo que
# o preview central amplia para ~1240px no telão: a foto chegava borrada bem na
# hora em que a pessoa se olha. No ladrilho o excedente não faz diferença.
TILE_SIZE = (512, 512)

async def broadcast_event(event_type: str, payload: dict):
    message = json.dumps({"type": event_type, "payload": payload})
    for connection in list(ACTIVE_CONNECTIONS):
        try:
            await connection.send_text(message)
        except Exception:
            if connection in ACTIVE_CONNECTIONS:
                ACTIVE_CONNECTIONS.remove(connection)

def _emit_from_thread(event_type: str, payload: dict):
    """
    Broadcast a partir de uma thread (watcher / background task do FastAPI).
    `asyncio.run` aqui criaria um loop novo, sem acesso aos WebSockets do loop
    principal — o evento sumia silenciosamente.
    """
    try:
        if main_loop and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast_event(event_type, payload), main_loop)
        else:
            print(f"[Broadcast] Loop principal indisponível, {event_type} descartado.")
    except Exception as exc:
        print(f"[Broadcast] Erro ao emitir {event_type}: {exc}")


def _ingest_image(img_bgr, photo_id: str, content_hash: str, origem: str):
    """
    Caminho único de ingestão (hot folder e upload do painel): descarta
    duplicata, recorta, enfileira e — com Auto-Place — pousa no mosaico.
    Roda sempre fora do event loop, então o broadcast passa por _emit_from_thread.
    """
    with _INGEST_LOCK:
        ja_visto = state.queue_manager.is_duplicate(content_hash)
        if ja_visto:
            print(f"[{origem}] Duplicata ignorada: {photo_id} tem o mesmo conteúdo de {ja_visto}")
            return
        state.queue_manager.register_hash(content_hash, photo_id)

        cropped = smart_crop_face(img_bgr, target_size=TILE_SIZE)
        # Grava em TILES_DIR, nunca na pasta assistida — evita realimentar o watcher.
        save_path = settings.TILES_DIR / f"{photo_id}.jpg"
        cv2.imwrite(str(save_path), cropped)

        url = f"/storage/tiles/{photo_id}.jpg"
        item = state.queue_manager.add_pending(photo_id, url, str(save_path))

        if not state.config.get("autoPlaceMode", False):
            _emit_from_thread("PHOTO_INGESTED", item)
            return

        state.queue_manager.approve(photo_id)
        if state.run_state != "running":
            print(f"[{origem}] run_state={state.run_state}: foto aprovada, aguardando Play.")
            return

        r, c, best_score = state.engine.find_best_tile_position(
            img_bgr,
            photo_id,
            duplicate_dist_limit=state.duplicate_dist_limit,
            strictness=state.color_strictness,
            fill_sequence=state.fill_sequence,
        )
        if r is None:
            print(f"[{origem}] Sem célula livre para {photo_id}")
            return

        _emit_from_thread("TILE_PLACED", {
            "photo_id": photo_id,
            "url": url,
            "row": r,
            "col": c,
            "target_x": c * state.engine.tile_w,
            "target_y": r * state.engine.tile_h,
            "score": best_score,
        })


def on_hot_folder_file(file_path: Path):
    """
    Callback disparado quando o HotFolderWatcher detecta uma foto da câmera no diretório.
    """
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        print(f"[HotFolder] Não consegui ler {file_path.name}: {exc}")
        return

    img_bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img_bgr is None:
        return

    _ingest_image(img_bgr, f"photo_{file_path.stem}", hashlib.md5(raw).hexdigest(), "HotFolder")

hot_folder_watcher = HotFolderWatcher(settings.HOT_FOLDER_DIR, on_hot_folder_file)
s3_watcher = S3Watcher(settings.HOT_FOLDER_DIR, poll_interval=5)

main_loop = None

@app.on_event("startup")
async def startup_event():
    global main_loop
    try:
        main_loop = asyncio.get_running_loop()
    except:
        pass
    hot_folder_watcher.start()
    s3_watcher.start()

@app.on_event("shutdown")
async def shutdown_event():
    # O uvicorn não encerra o worker enquanto houver WebSocket aberto, e o telão
    # fica conectado o tempo todo: sem este fechamento o `--reload` anunciava
    # "Reloading..." e pendurava, deixando o código antigo servindo em silêncio.
    for connection in list(ACTIVE_CONNECTIONS):
        try:
            await connection.close()
        except Exception:
            pass
        if connection in ACTIVE_CONNECTIONS:
            ACTIVE_CONNECTIONS.remove(connection)

    hot_folder_watcher.stop()
    s3_watcher.stop()

# --- HEALTH (PICBRAND ARCH §11) ---

APP_INICIADO_EM = time.time()


@app.get("/health")
async def health():
    """
    Público e simples: só diz que o processo responde. Sem caminhos de disco,
    sem nome de bucket, sem contagem de fotos — nada que ajude quem não deveria
    estar olhando.
    """
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.get("/ready")
async def ready():
    """
    Pronto para receber tráfego: o telão depende do storage para servir os
    ladrilhos e do watcher para ingerir foto. Sem isso o show não roda, então
    responde 503 e o operador vê o problema antes do evento começar.
    """
    checagens = {
        "storage": settings.STORAGE_DIR.exists() and settings.TILES_DIR.exists(),
        "hot_folder": settings.HOT_FOLDER_DIR.exists(),
        "watcher": hot_folder_watcher.observer is not None,
        "engine": state.engine is not None,
    }
    pronto = all(checagens.values())
    return JSONResponse(
        status_code=200 if pronto else 503,
        content={"status": "ready" if pronto else "not_ready", "checks": checagens},
    )


@app.get("/admin/health")
async def admin_health():
    """
    Visão operacional do evento. Fica sob /admin porque expõe estado interno;
    a proteção da área é a decisão registrada em docs/ARCHITECTURE.md.
    """
    uptime = int(time.time() - APP_INICIADO_EM)
    try:
        tiles = len(list(settings.TILES_DIR.glob("*.jpg")))
        na_hot_folder = len([p for p in settings.HOT_FOLDER_DIR.iterdir() if p.is_file()])
    except OSError:
        tiles = na_hot_folder = -1

    return {
        "status": "ok",
        "uptime_segundos": uptime,
        "run_state": state.run_state,
        "mosaico": {
            "tiles_pousados": len(state.engine.placed_tiles),
            "grade": f"{state.rows}x{state.cols}",
            "fila_moderacao": len(state.queue_manager.pending_queue),
        },
        "ingestao": {
            "fotos_processadas": tiles,
            "na_hot_folder": na_hot_folder,
            "watcher_ativo": hot_folder_watcher.observer is not None,
            "s3_ativo": s3_watcher.s3 is not None,
            "s3_chaves_importadas": len(s3_watcher.seen_keys),
        },
        "telao": {
            "conexoes_websocket": len(ACTIVE_CONNECTIONS),
            "overlay_marca": bool(state.config.get("foregroundUrl")),
        },
    }


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
        # O painel manda "storage/hot_folder" (relativo ao projeto). Resolver
        # contra BASE_DIR evita que o watcher vigie uma pasta vazia criada no
        # cwd de quem subiu o uvicorn.
        raw_dir = Path(str(patch["hotFolderDir"]))
        watch_dir = raw_dir if raw_dir.is_absolute() else (settings.BASE_DIR / raw_dir)
        hot_folder_watcher.update_dir(watch_dir)
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
        # Coloca no mosaico as fotos que já foram aprovadas (ex: via Auto-Place em idle) 
        # mas que ainda não estão no mosaico.
        placed_ids = set(state.engine.placed_tiles.values())
        for item in state.queue_manager.approved_photos:
            if item["id"] not in placed_ids:
                img_bgr = cv2.imread(item["local_path"])
                if img_bgr is not None:
                    r, c, best_score = state.engine.find_best_tile_position(
                        img_bgr, 
                        item["id"], 
                        duplicate_dist_limit=state.duplicate_dist_limit,
                        strictness=state.color_strictness,
                        fill_sequence=state.fill_sequence
                    )
                    if r is not None:
                        target_cell = (r, c)
                        payload = {
                            "photo_id": item["id"],
                            "url": item["url"],
                            "row": target_cell[0],
                            "col": target_cell[1],
                            "target_x": target_cell[1] * state.engine.tile_w,
                            "target_y": target_cell[0] * state.engine.tile_h,
                            "score": best_score,
                        }
                        await broadcast_event("TILE_PLACED", payload)
                        await asyncio.sleep(0.15)  # Dá respiro pro event loop e cria efeito cascata visual
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

@app.post("/api/ingest/foreground")
async def upload_foreground(file: UploadFile = File(...)):
    """
    Sobe o recorte da marca (Camada 4): um PNG que fica por cima do mosaico e
    deixa as fotos aparecerem pelas partes transparentes.

    Os bytes são gravados como vieram, sem passar por `cv2.imdecode` — decodificar
    e regravar descartaria o canal alfa, e sem alfa o overlay viraria uma chapa
    opaca cobrindo o mosaico inteiro.
    """
    contents = await file.read()

    imagem = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_UNCHANGED)
    if imagem is None:
        raise HTTPException(status_code=400, detail="Arquivo enviado não é uma imagem válida")

    tem_alfa = imagem.ndim == 3 and imagem.shape[2] == 4
    extensao = Path(file.filename or "").suffix.lower()
    if extensao not in (".png", ".webp"):
        extensao = ".png"

    save_path = settings.STORAGE_DIR / f"foreground{extensao}"
    save_path.write_bytes(contents)

    url = f"/storage/{save_path.name}?t={uuid.uuid4().hex[:8]}"
    config = state.apply_config({"foregroundUrl": url})

    print(f"[Foreground] {save_path.name} ({imagem.shape[1]}x{imagem.shape[0]}), alfa={tem_alfa}")
    await broadcast_event("CONFIG_UPDATED", config)
    return {"status": "success", "url": url, "hasAlpha": tem_alfa}


@app.delete("/api/ingest/foreground")
async def remove_foreground():
    config = state.apply_config({"foregroundUrl": None})
    await broadcast_event("CONFIG_UPDATED", config)
    return {"status": "success"}


@app.post("/api/hsbc/apply-bowtie")
async def apply_hsbc_bowtie():
    """
    Calcula as red_cells do target_image atual, depois computa row_bounds
    para preencher a gravata-borboleta. Atualiza a config com cellFilters
    e customMaskCells para o frontend renderizar e o motor alocar corretamente.
    """
    if not state.has_target_image:
        raise HTTPException(status_code=400, detail="Nenhuma imagem base (logo) carregada.")
    
    img_bgr = state.target_image_bgr
    h, w = img_bgr.shape[:2]
    tile_h = h // state.rows
    tile_w = w // state.cols
    
    # 1. Detectar red_cells (pixels vermelhos)
    r_ch = img_bgr[:,:,2]
    g_ch = img_bgr[:,:,1]
    b_ch = img_bgr[:,:,0]
    red_mask_bin = (r_ch > 80) & (g_ch < 60) & (b_ch < 60)
    
    red_cells = set()
    for r in range(state.rows):
        for c in range(state.cols):
            y_start = r * tile_h
            x_start = c * tile_w
            y_end = y_start + tile_h
            x_end = x_start + tile_w
            if np.sum(red_mask_bin[y_start:y_end, x_start:x_end]) > (tile_w * tile_h * 0.03):
                red_cells.add((r, c))
                
    if not red_cells:
        raise HTTPException(status_code=400, detail="Logo não possui pixels vermelhos suficientes (tolerância HSBC).")
        
    # 2. Calcular row_bounds para preenchimento da gravata-borboleta
    row_bounds = {}
    for r, c in red_cells:
        if r not in row_bounds:
            row_bounds[r] = [c, c]
        else:
            row_bounds[r][0] = min(row_bounds[r][0], c)
            row_bounds[r][1] = max(row_bounds[r][1], c)
            
    # 3. Gerar customMaskCells e cellFilters
    custom_mask_cells = []
    cell_filters = {}
    
    # Criar uma imagem de debug para salvar na área de trabalho
    debug_img = img_bgr.copy()
    
    for r, bounds in row_bounds.items():
        min_c, max_c = bounds
        for c in range(min_c, max_c + 1):
            cell_id = f"{r}_{c}"
            custom_mask_cells.append(cell_id)
            
            y_start = r * tile_h
            x_start = c * tile_w
            y_end = y_start + tile_h
            x_end = x_start + tile_w
            
            if (r, c) in red_cells:
                cell_filters[cell_id] = "red"
                # Contorno vermelho forte nas bordas mapeadas
                cv2.rectangle(debug_img, (x_start, y_start), (x_end, y_end), (0, 0, 255), 2)
            else:
                cell_filters[cell_id] = "none"
                # Contorno verde claro no "miolo" vazio
                cv2.rectangle(debug_img, (x_start, y_start), (x_end, y_end), (0, 255, 0), 2)
                
    # Salvar na Área de Trabalho do Usuário
    import os
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "logo_hsbc_mapeada.jpg")
    cv2.imwrite(desktop_path, debug_img)
                
    # 4. Atualizar configuração via patch (para persistir e propagar)
    patch = {
        "gridContainerShape": "custom_mask",
        "customMaskCells": custom_mask_cells,
        "cellFilters": cell_filters,
    }
    config = state.apply_config(patch)
    await broadcast_event("CONFIG_UPDATED", config)
    
    return {"status": "success", "message": "Gravata-borboleta aplicada com sucesso!", "config": config}

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
    if img_bgr is None:
        raise HTTPException(status_code=400, detail="Arquivo não é uma imagem válida")

    # ID por uuid: contar as filas colidia assim que uma foto era rejeitada,
    # sobrescrevendo o tile anterior no disco.
    photo_id = f"photo_{uuid.uuid4().hex[:12]}"

    content_hash = hashlib.md5(contents).hexdigest()

    def process_ingestion():
        _ingest_image(img_bgr, photo_id, content_hash, "Upload")

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
        cropped = smart_crop_face(img_bgr, target_size=TILE_SIZE)
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

@app.post("/api/export/video")
async def start_video_export():
    from app.core.state import state
    import uuid
    import threading
    from app.services.video_export import run_export_video_task, exports
    
    export_id = str(uuid.uuid4())
    exports[export_id] = {"status": "pending", "progress": 0}
    
    payload = state.placed_tiles_payload()
    bg_bgr = state.target_image_bgr.copy()
    config = state.config.copy()
    
    t = threading.Thread(
        target=run_export_video_task,
        args=(export_id, payload, bg_bgr, config),
        daemon=True
    )
    t.start()
    
    return {"export_id": export_id}

class OpcoesVideoMarca(BaseModel):
    """Ajustes do vídeo da marca. Tudo opcional — os defaults são os aprovados."""

    largura: int = 1152
    altura: int = 688
    fps: int = 30
    intervaloEntreFotos: float = 0.12
    holdCentral: float = 0.5
    duracaoVoo: float = 0.6
    segundosFinais: float = 3.0
    corMarca: str = "#e21c1c"  # vermelho HSBC


def _hex_para_bgr(valor: str, padrao: tuple[int, int, int] = (28, 28, 226)) -> tuple[int, int, int]:
    texto = (valor or "").strip().lstrip("#")
    if len(texto) == 3:
        texto = "".join(c * 2 for c in texto)
    if len(texto) != 6:
        return padrao
    try:
        r, g, b = (int(texto[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return padrao
    return (b, g, r)  # OpenCV trabalha em BGR


def _limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


@app.get("/api/export/video-marca/info")
async def info_video_marca():
    """
    O que o painel precisa para estimar a duração antes de gerar: quantas fotos
    existem e quantas células do logo serão preenchidas.
    """
    from app.services import video_marca

    overlay = _caminho_overlay()
    fotos = video_marca.fotos_disponiveis()
    celulas = None

    if overlay is not None:
        try:
            _, alfa = video_marca.carregar_overlay(
                overlay,
                int(state.config.get("screenWidth", 1920)),
                int(state.config.get("screenHeight", 1080)),
            )
            c = state.config
            celulas = len(video_marca.celulas_da_marca(
                alfa, int(c.get("rows", 38)), int(c.get("cols", 62)),
                float(c.get("gridOffsetX", 0)), float(c.get("gridOffsetY", 0)),
                float(c.get("gridWidth", c.get("screenWidth", 1920))),
                float(c.get("gridHeight", c.get("screenHeight", 1080))),
            ))
        except Exception as exc:
            print(f"[VideoMarca] info indisponível: {exc}")

    return {
        "temOverlay": overlay is not None,
        "fotos": len(fotos),
        "celulas": celulas,
    }


@app.post("/api/export/video-marca")
async def start_video_marca(opcoes: OpcoesVideoMarca | None = None):
    """
    Vídeo no modelo aprovado pelo cliente (referência em video/): a foto surge
    colorida no centro, voa e pousa tingida na cor da marca, desenhando o logo.

    Usa o overlay já configurado no painel e TODAS as fotos disponíveis em
    storage/tiles — não depende do mosaico estar montado na tela.
    """
    from app.services.video_export import exports
    from app.services import video_marca

    overlay = _caminho_overlay()
    if overlay is None:
        raise HTTPException(
            status_code=409,
            detail="Nenhum overlay de marca configurado. Suba a arte em Camadas > Logo Overlay.",
        )

    fotos = video_marca.fotos_disponiveis()
    if not fotos:
        raise HTTPException(status_code=409, detail="Nenhuma foto disponível em storage/tiles.")

    o = opcoes or OpcoesVideoMarca()
    # Limites de sanidade: um painel com bug não pode pedir um vídeo de 8K
    # nem um ritmo que gere um arquivo de horas.
    largura = int(_limitar(o.largura, 320, 3840))
    altura = int(_limitar(o.altura, 240, 2160))
    fps = int(_limitar(o.fps, 12, 60))
    intervalo = _limitar(o.intervaloEntreFotos, 0.02, 2.0)
    hold = _limitar(o.holdCentral, 0.0, 5.0)
    voo = _limitar(o.duracaoVoo, 0.1, 3.0)
    finais = _limitar(o.segundosFinais, 0.0, 15.0)
    cor = _hex_para_bgr(o.corMarca)

    export_id = str(uuid.uuid4())
    exports[export_id] = {"status": "pending", "progress": 0, "modelo": "marca"}
    config = state.config.copy()
    destino = settings.STORAGE_DIR / "exports" / f"export_{export_id}.mp4"

    def tarefa():
        try:
            exports[export_id]["status"] = "running"
            resumo = video_marca.gerar_video_marca(
                destino, fotos, overlay, config,
                largura=largura, altura=altura, fps=fps,
                intervalo_entre_fotos=intervalo,
                hold_central=hold,
                duracao_voo=voo,
                segundos_finais=finais,
                cor_marca=cor,
                progresso=lambda p: exports[export_id].update(progress=p),
            )
            exports[export_id].update(status="done", progress=100,
                                      local_path=str(destino), resumo=resumo)
            print(f"[VideoMarca] concluído: {resumo}")
        except Exception as exc:
            exports[export_id].update(status="error", error=str(exc))
            print(f"[VideoMarca] ERRO: {exc}")

    threading.Thread(target=tarefa, daemon=True).start()
    return {"export_id": export_id, "fotos": len(fotos)}


def _caminho_overlay() -> Path | None:
    """Arquivo local do overlay publicado na config, se existir."""
    url = state.config.get("foregroundUrl")
    if not url:
        return None
    nome = url.split("?")[0].rsplit("/", 1)[-1]
    caminho = settings.STORAGE_DIR / nome
    return caminho if caminho.exists() else None


@app.get("/api/export/video/status/{export_id}")
async def get_export_status(export_id: str):
    from app.services.video_export import exports
    if export_id not in exports:
        raise HTTPException(status_code=404, detail="Export ID não encontrado")
    return exports[export_id]

@app.get("/api/export/video/download/{export_id}")
async def download_video(export_id: str):
    import os
    from fastapi.responses import FileResponse
    from app.services.video_export import exports
    
    # Os dois exportadores marcam o fim de formas diferentes ('done' e
    # 'completed'); aceitar só uma delas bloqueava o download de um vídeo pronto.
    if export_id not in exports or exports[export_id]["status"] not in ("done", "completed"):
        raise HTTPException(status_code=400, detail="Vídeo não está pronto ou erro")
        
    file_path = exports[export_id].get("local_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo de vídeo não encontrado no disco")
        
    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=f"mosaico_subdivisao_{export_id}.mp4"
    )
