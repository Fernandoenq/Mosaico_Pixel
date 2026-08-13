from fastapi import FastAPI, BackgroundTasks, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any, List, Optional
import uuid
import time
import hashlib
import threading
from app.services.video_export import run_export_video_task, exports
import cv2
import numpy as np
from pathlib import Path
import json
import math
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
        # Trava por identidade: vale nos dois modos. A varredura inicial da hot
        # folder reprocessa a pasta inteira a cada restart, e é só isto que
        # impede o mesmo arquivo de virar um segundo tile.
        if state.queue_manager.is_duplicate_id(photo_id):
            print(f"[{origem}] Já ingerido nesta rodada, ignorando: {photo_id}")
            return

        # Trava por conteúdo: opcional. Desligada, a cópia `*masked` que a cabine
        # publica junto do original também entra no mosaico.
        if not state.config.get("permitirFotosRepetidas", False):
            ja_visto = state.queue_manager.is_duplicate(content_hash)
            if ja_visto:
                print(f"[{origem}] Duplicata ignorada: {photo_id} tem o mesmo conteúdo de {ja_visto}")
                return

        state.queue_manager.register_id(photo_id)
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

        state.register_tile_url(photo_id, url)
        _emit_from_thread("TILE_PLACED", {
            "photo_id": photo_id,
            "url": url,
            "row": r,
            "col": c,
            "target_x": c * state.engine.tile_w,
            "target_y": r * state.engine.tile_h,
            "score": best_score,
        })
        # Este é o caminho que roda num evento de verdade (Auto-Place ligado) e
        # era o único que não perguntava se o mosaico tinha acabado de fechar:
        # enchia até a última célula e a animação final nunca disparava.
        check_auto_outro()


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

# --- Duplicação gradual ---

_DUP_TASK: asyncio.Task | None = None
# Contador global de cópias. Garante id único mesmo depois de desligar e religar
# o interruptor: repetir um id faria a cópia nova sobrescrever a antiga no motor.
_DUP_CONTADOR = 0
# Marca a janela entre o `cancel()` e a morte real da task. Sem ela, um
# desliga/liga rápido deixava o laço morto com o interruptor ligado.
_DUP_CANCELANDO = False

# Fechamento animado: mesma duplicação, mas em um só gesto — enche o que falta
# foto a foto e para sozinho quando a grade fecha.
_FECHA_TASK: asyncio.Task | None = None
_FECHA_CANCELANDO = False


def _caminho_do_storage(url: str) -> Path | None:
    """Arquivo em disco por trás de uma URL /storage/..."""
    prefixo = "/storage/"
    if not url or not url.startswith(prefixo):
        return None
    return settings.STORAGE_DIR / url[len(prefixo):]


def _fotos_reais_no_mosaico() -> list[tuple[str, str]]:
    """(photo_id, url) das fotos de verdade já pousadas, sem as cópias."""
    reais: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for photo_id in state.engine.placed_tiles.values():
        chave = str(photo_id)
        if "_dup_" in chave or chave in vistos:
            continue
        url = state.tile_urls.get(chave)
        if url:
            vistos.add(chave)
            reais.append((chave, url))
    return reais


def _espera_entre_copias() -> float:
    """
    Segundos entre uma cópia e a seguinte.

    `duplicateIntervalSeconds` é o respiro DEPOIS que o telão termina de exibir
    a cópia anterior, não o intervalo bruto. Mandando pelo valor cru, o laço
    soltava uma cópia a cada 3s enquanto cada uma leva uns 12s na tela: a fila
    do telão crescia sem parar e as fotos acabavam se atropelando.
    """
    config = state.config
    hold = float(config.get("centralPreviewDuration", 10.0)) if config.get("centralPreviewEnabled", True) else 0.0
    exibicao = 0.75 + hold + float(config.get("animationDuration", 0.8)) * 2
    respiro = float(config.get("previewGapSeconds", 1.5))
    intervalo = float(config.get("duplicateIntervalSeconds", 3.0))
    return max(0.2, exibicao + respiro, intervalo)


async def _duplicar_uma_foto(fontes: list[tuple[str, str]], indice: int) -> bool:
    """
    Copia UMA foto do rodízio para a próxima célula vaga. True se pousou.

    Sai por `TILE_PLACED`, o mesmo evento de uma foto nova — é o que faz o telão
    animar a cópia igual: cartão no centro e voo até a célula.

    Dividido entre o laço gradual e o fechamento animado, que só diferem em
    QUANDO param: o interruptor roda enquanto estiver ligado, o fechamento roda
    até a grade fechar.
    """
    global _DUP_CONTADOR

    photo_id_fonte, url = fontes[indice % len(fontes)]
    caminho = _caminho_do_storage(url)
    img_bgr = cv2.imread(str(caminho)) if caminho and caminho.exists() else None
    if img_bgr is None:
        print(f"[Duplicação] Arquivo ilegível para {photo_id_fonte}, pulando.")
        return False

    _DUP_CONTADOR += 1
    novo_id = f"{photo_id_fonte}_dup_{_DUP_CONTADOR}"
    r, c, score = state.engine.find_best_tile_position(
        img_bgr,
        novo_id,
        duplicate_dist_limit=0,
        strictness=state.color_strictness,
        fill_sequence=state.fill_sequence,
    )
    if r is None:
        return False

    state.register_tile_url(novo_id, url)
    await broadcast_event("TILE_PLACED", {
        "photo_id": novo_id,
        "url": url,
        "row": r,
        "col": c,
        "target_x": c * state.engine.tile_w,
        "target_y": r * state.engine.tile_h,
        "score": score,
    })
    check_auto_outro()
    return True


async def _laco_fechamento_animado():
    """
    Fecha a grade foto a foto, no ritmo do telão, e para sozinho no fim.

    O irmão deste laço é `POST /api/mosaic/auto-fill-duplicates`, que despeja
    tudo de uma vez: serve para a foto oficial e para a gravação, quando não dá
    para esperar. Só que ele fecha o mosaico num piscar, e é o voo de cada foto
    que o telão existe para mostrar. Aqui cada cópia entra com a animação
    inteira, uma de cada vez, até não sobrar célula.

    Não é o interruptor gradual: aquele é rodízio permanente, fica ligado e
    absorve quem chega no meio do evento. Este é um gesto de encerramento —
    começa, fecha e acaba.
    """
    global _FECHA_CANCELANDO
    indice = 0
    vagas_no_inicio = len(state.engine.available_cells())
    print(f"[Fechamento] Animado, foto a foto — {vagas_no_inicio} célula(s) a preencher.")
    try:
        while True:
            if not state.engine.available_cells():
                print("[Fechamento] Grade fechada.")
                break

            fontes = _fotos_reais_no_mosaico()
            if not fontes:
                print("[Fechamento] Sem foto real no mosaico para copiar — encerrando.")
                break

            if await _duplicar_uma_foto(fontes, indice):
                indice += 1
            elif indice >= len(fontes) * 2:
                # Todo o rodízio já falhou duas voltas seguidas: os arquivos
                # sumiram do disco ou não há célula alcançável. Insistir aqui
                # seria um laço eterno cuspindo erro no log.
                print("[Fechamento] Nenhuma foto do rodízio pôde ser posicionada — encerrando.")
                break
            else:
                indice += 1
                continue

            await asyncio.sleep(_espera_entre_copias())
    except asyncio.CancelledError:
        print("[Fechamento] Interrompido pelo painel.")
        raise
    except Exception as exc:
        print(f"[Fechamento] Laço interrompido por erro: {exc}")
    finally:
        _FECHA_CANCELANDO = False


def _fechamento_animado_rodando() -> bool:
    """Vivo E não em processo de morrer — a mesma distinção do laço gradual."""
    return _FECHA_TASK is not None and not _FECHA_TASK.done() and not _FECHA_CANCELANDO


async def _laco_duplicacao():
    """
    Duplicação GRADUAL, enquanto o interruptor estiver ligado.

    Cada cópia entra pelo mesmo TILE_PLACED de uma foto nova, então o telão a
    anima igual: cartão no centro e voo até a célula. Despejar tudo de uma vez
    enchia a grade num piscar e matava justamente o efeito que o telão existe
    para dar.

    A ordem é rodízio sobre as fotos reais: 50 fotos viram 100, depois 150, até
    a grade fechar. Quem chega no meio do evento entra no rodízio na hora.
    """
    global _DUP_CANCELANDO
    indice = 0
    print("[Duplicação] Ligada — copiando as fotos do mosaico aos poucos.")
    try:
        while state.config.get("autoDuplicateToFill", False):
            await asyncio.sleep(_espera_entre_copias())

            if state.run_state != "running":
                continue
            if not state.engine.available_cells():
                continue

            fontes = _fotos_reais_no_mosaico()
            if not fontes:
                continue

            await _duplicar_uma_foto(fontes, indice)
            indice += 1
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"[Duplicação] Laço interrompido por erro: {exc}")
    finally:
        _DUP_CANCELANDO = False
        print("[Duplicação] Desligada.")


def _sincronizar_duplicacao():
    """
    Liga ou desliga o laço conforme `autoDuplicateToFill`.

    `cancel()` NÃO encerra na hora: a task só morre quando a cancelação chega ao
    `await`, e até lá `done()` continua False. Sem separar "vivo" de "morrendo",
    desligar e religar rápido caía numa janela em que o laço parecia estar
    rodando, esta função voltava sem fazer nada, e a task antiga morria em
    seguida — a duplicação ficava desligada em silêncio, com o interruptor
    ligado no painel. É a mesma armadilha que derrubou o watcher do S3.
    """
    global _DUP_TASK, _DUP_CANCELANDO
    ativo = bool(state.config.get("autoDuplicateToFill", False))
    vivo = _DUP_TASK is not None and not _DUP_TASK.done()

    if ativo and (not vivo or _DUP_CANCELANDO):
        _DUP_CANCELANDO = False
        _DUP_TASK = asyncio.create_task(_laco_duplicacao())
    elif not ativo and vivo and not _DUP_CANCELANDO:
        _DUP_CANCELANDO = True
        _DUP_TASK.cancel()


@app.on_event("startup")
async def startup_event():
    global main_loop
    try:
        main_loop = asyncio.get_running_loop()
    except:
        pass
    hot_folder_watcher.start()
    s3_watcher.start()
    # A config vem do disco: se o evento parou com a duplicação ligada, ela
    # precisa voltar sozinha depois do restart.
    _sincronizar_duplicacao()

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

    if _DUP_TASK and not _DUP_TASK.done():
        _DUP_TASK.cancel()

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
        "watcher": hot_folder_watcher.ativo(),
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
            "watcher_ativo": hot_folder_watcher.ativo(),
            "s3_ativo": s3_watcher.ativo(),
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
    return {
        "config": state.config,
        "run_state": state.run_state,
        # Sinaliza ao painel que o recorte do logo não corresponde mais à
        # geometria atual da grade e precisa ser refeito.
        "mask_stale": state.mask_stale,
    }

@app.put("/api/config")
async def put_run_config(patch: dict):
    """
    Recebe a configuração do painel (patch parcial ou completo), valida, persiste
    e retransmite para todos os telões conectados.
    """
    config = state.apply_config(patch)
    _sincronizar_duplicacao()
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
                        state.register_tile_url(item["id"], item["url"])
                        await broadcast_event("TILE_PLACED", payload)
                        await asyncio.sleep(0.15)  # Dá respiro pro event loop e cria efeito cascata visual

        # O mosaico pode JÁ estar cheio na hora do Play — é o que acontece
        # quando o operador enche com duplicatas ainda em idle e só então dá
        # Play. Sem esta verificação a saída nunca dispararia: as outras só
        # rodam quando um tile pousa, e não há mais célula onde pousar.
        check_auto_outro()
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
            
            if r is None:
                print(f"[Approve] Sem célula dentro do contorno para {photo_id}")
                return

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
            state.register_tile_url(photo_id, item["url"])
            
            # Usa run_coroutine_threadsafe para enviar ao loop principal do asyncio
            future = asyncio.run_coroutine_threadsafe(
                broadcast_event("TILE_PLACED", placement),
                main_loop
            )
            future.result(timeout=5.0)  # Aguarda confirmação de envio (timeout 5s)
            check_auto_outro()
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
    # A fila usa a chave "id"; ler "photo_id" aqui estourava KeyError e derrubava
    # o endpoint com 500 sempre que HAVIA foto aprovada — justamente o caso
    # normal de uso. Só o fallback dos tiles em disco funcionava.
    available_photos = [
        {
            "photo_id": item.get("id") or item.get("photo_id"),
            "url": item["url"],
            "local_path": item["local_path"],
        }
        for item in state.queue_manager.approved_photos
        if item.get("url") and item.get("local_path")
    ]
    if not available_photos:
        tile_files = list(settings.TILES_DIR.glob("*.jpg"))
        if not tile_files:
            raise HTTPException(status_code=400, detail="Nenhuma foto aprovada ou disponível para duplicar!")
        available_photos = [{"photo_id": f.stem, "url": f"/storage/tiles/{f.name}", "local_path": str(f)} for f in tile_files]

    placed_count = 0
    ilegiveis = 0
    total_cells = state.engine.rows * state.engine.cols

    for i in range(total_cells):
        if not state.engine.available_cells():
            break

        item = available_photos[i % len(available_photos)]
        img_bgr = cv2.imread(item["local_path"])
        if img_bgr is None:
            ilegiveis += 1
            # Sem esta saída, um lote inteiro de arquivos ilegíveis faria o laço
            # girar `total_cells` vezes sem colocar nada.
            if ilegiveis >= len(available_photos):
                break
            continue

        # O id precisa ser único por ladrilho: o motor indexa placed_tiles por
        # photo_id, e repetir o mesmo id faria a duplicata sobrescrever a
        # original em vez de ocupar uma célula nova.
        photo_id = f"{item['photo_id']}_dup_{i}"

        r, c, score = state.engine.find_best_tile_position(
            img_bgr,
            photo_id,
            duplicate_dist_limit=0,
            strictness=state.color_strictness,
            fill_sequence=fill_sequence
        )
        if r is None:
            # Sem célula dentro do contorno — não há o que preencher.
            break

        state.register_tile_url(photo_id, item["url"])
        await broadcast_event("TILE_PLACED", {
            "photo_id": photo_id,
            "url": item["url"],
            "row": r,
            "col": c,
            "target_x": c * state.engine.tile_w,
            "target_y": r * state.engine.tile_h,
            "score": score,
        })
        placed_count += 1
        # Dá respiro ao event loop: sem isso, preencher centenas de células
        # segurava o servidor e o telão recebia tudo de uma vez no fim.
        await asyncio.sleep(0.02)

    restantes = len(state.engine.available_cells())
    print(f"[AutoFill] {placed_count} duplicata(s) posicionada(s); {restantes} célula(s) ainda vaga(s).")
    check_auto_outro()
    return {
        "status": "success",
        "placed_count": placed_count,
        "restantes": restantes,
        "ilegiveis": ilegiveis,
    }

@app.post("/api/mosaic/fechar-animado")
async def fechar_animado():
    """
    Fecha o mosaico foto a foto, com a animação de sempre, e para no fim.

    O `auto-fill-duplicates` fecha tudo no mesmo instante; este leva o tempo do
    telão: cada cópia ganha o cartão no centro e o voo até a célula. O ritmo é o
    mesmo respiro da duplicação gradual, então mexer no slider muda os dois.
    """
    global _FECHA_TASK, _FECHA_CANCELANDO

    if _fechamento_animado_rodando():
        return {
            "status": "already_running",
            "restantes": len(state.engine.available_cells()),
        }

    vagas = state.engine.available_cells()
    if not vagas:
        return {"status": "complete", "restantes": 0, "estimativa_segundos": 0}

    if not _fotos_reais_no_mosaico():
        raise HTTPException(
            status_code=400,
            detail="Nenhuma foto real no mosaico para copiar. Coloque ao menos uma foto antes de fechar.",
        )

    _FECHA_CANCELANDO = False
    _FECHA_TASK = asyncio.create_task(_laco_fechamento_animado())
    return {
        "status": "started",
        "restantes": len(vagas),
        "estimativa_segundos": round(len(vagas) * _espera_entre_copias()),
    }


@app.get("/api/mosaic/fechar-animado")
async def status_fechamento_animado():
    """
    O laço ainda está de pé?

    Quem pergunta é o painel: o fechamento acaba sozinho quando a grade fecha, e
    sem isso o botão ficaria preso em "Parar" esperando um laço que já morreu.
    Também é o que reconstrói o estado depois de um F5 no meio do fechamento.
    """
    return {
        "rodando": _fechamento_animado_rodando(),
        "restantes": len(state.engine.available_cells()),
    }


@app.post("/api/mosaic/fechar-animado/parar")
async def parar_fechamento_animado():
    """Interrompe o fechamento animado. O que já pousou fica."""
    global _FECHA_CANCELANDO

    if not _fechamento_animado_rodando():
        return {"status": "idle", "restantes": len(state.engine.available_cells())}

    _FECHA_CANCELANDO = True
    _FECHA_TASK.cancel()
    return {"status": "stopped", "restantes": len(state.engine.available_cells())}


@app.post("/api/mosaic/remove-duplicates")
async def remove_duplicates():
    """
    Desfaz o preenchimento por duplicatas: o mosaico volta a mostrar só as fotos
    reais do evento. Toda cópia carrega o sufixo `_dup_` no photo_id, então dá
    para distinguir sem guardar estado à parte.
    """
    cancel_auto_outro()
    duplicadas = [
        (cell, photo_id)
        for cell, photo_id in state.engine.placed_tiles.items()
        if "_dup_" in str(photo_id)
    ]

    for (r, c), photo_id in duplicadas:
        state.engine.remove_tile(r, c)
        state.tile_urls.pop(photo_id, None)

    if duplicadas:
        # O telão não tem como saber quais células esvaziaram: manda a lista, e
        # cada uma some da tela sem precisar recarregar o mosaico inteiro.
        await broadcast_event(
            "TILES_REMOVED",
            {"cells": [{"row": r, "col": c} for (r, c), _ in duplicadas]},
        )

    restantes = len(state.engine.placed_tiles)
    print(f"[AutoFill] {len(duplicadas)} duplicata(s) removida(s); {restantes} foto(s) real(is) no mosaico.")
    return {
        "status": "success",
        "removed_count": len(duplicadas),
        "originais": restantes,
    }

# Pode ser um asyncio.Task (agendado de dentro do loop) ou um
# concurrent.futures.Future (agendado de uma thread). Os dois expõem
# `.done()` e `.cancel()`, que é tudo o que usamos aqui.
_outro_task: Any = None
_outro_limpeza_task: Optional[asyncio.Task] = None

# Folga para a parte animada do ciclo (desfazer + remontar) antes de liberar as
# células. O telão desfaz em até ~0,9s e remonta em ~1,2s; 3s cobre os dois com
# sobra mesmo num telão lento. Só o `hold` é configurável — este é o piso
# técnico, e ele precisa continuar MAIOR que a soma das duas animações no
# frontend (animateMosaicOutro + animateMosaicReturn).
OUTRO_MARGEM_ANIMACAO = 3.0


async def _limpar_apos_outro(espera: float):
    """
    Libera as células depois que o telão terminou de remontar e segurar a
    imagem final. Enquanto isso o mosaico segue cheio de propósito — é a foto
    que o público está tirando da tela.
    """
    try:
        await asyncio.sleep(espera)
        tile_count = len(state.engine.placed_tiles)
        state.engine.placed_tiles.clear()
        state.engine.locked_tiles.clear()
        state.tile_urls.clear()
        await broadcast_event("MOSAIC_RESET", {"motivo": "outro", "tiles": tile_count})
        print(f"[AutoOutro] Ciclo concluído: {tile_count} célula(s) liberadas, o mosaico volta a encher.")
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        print(f"[AutoOutro] Erro ao limpar depois da dispersão: {exc}")


async def _trigger_auto_outro_after_delay(delay: float, modo: str):
    try:
        await asyncio.sleep(delay)
        if len(state.engine.available_cells()) == 0 and len(state.engine.placed_tiles) > 0 and state.run_state == "running":
            print(f"[AutoOutro] Mosaico 100% completo com {len(state.engine.placed_tiles)} células! Dispersando mosaico (modo={modo})...")
            await play_mosaic_outro(modo=modo)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        print(f"[AutoOutro] Erro ao disparar dispersão automática: {exc}")

def check_auto_outro():
    """
    Mosaico cheio? Agenda o ciclo de saída.

    Chamada tanto de dentro do event loop (duplicação, auto-fill) quanto de
    THREAD (ingestão de foto, aprovação) — por isso não usa
    `asyncio.get_running_loop()`: numa thread ele levanta RuntimeError, e o
    `except` engolia a exceção. O mosaico enchia de fotos reais e a animação
    final simplesmente nunca acontecia, sem uma linha de log.
    """
    global _outro_task
    if not state.config.get("autoOutroOnComplete", True):
        return
    if len(state.engine.available_cells()) != 0 or len(state.engine.placed_tiles) == 0:
        return
    if state.run_state != "running":
        return
    if _outro_task is not None and not _outro_task.done():
        return

    delay = float(state.config.get("autoOutroDelaySeconds", 3.0))
    modo = str(state.config.get("outroMode", "espalhar"))
    print(f"[AutoOutro] Mosaico preenchido! Agendando saída ({modo}) em {delay}s...")

    if not (main_loop and main_loop.is_running()):
        print("[AutoOutro] Loop principal indisponível; saída não agendada.")
        return

    corrotina = _trigger_auto_outro_after_delay(delay, modo)
    try:
        loop_atual = asyncio.get_running_loop()
    except RuntimeError:
        loop_atual = None

    if loop_atual is main_loop:
        _outro_task = main_loop.create_task(corrotina)
    else:
        # De outra thread: agenda no loop principal e guarda o Future só para o
        # teste de "já tem um ciclo em andamento" continuar valendo.
        _outro_task = asyncio.run_coroutine_threadsafe(corrotina, main_loop)

def cancel_auto_outro():
    global _outro_task
    if _outro_task and not _outro_task.done():
        _outro_task.cancel()
        _outro_task = None

@app.post("/api/mosaic/outro")
async def play_mosaic_outro(modo: str = "dispersar"):
    """
    Encerramento do evento / conclusão do mosaico: desfaz o mosaico na tela.

    `dispersar` (padrão) é a saída com a animação de explosão radial/dispersão para fora da tela.
    `espalhar` é o desfazimento suave local.
    `retorno` é o voo de volta para o centro.

    Limpa os ladrilhos no servidor junto com a animação para que o estado bata
    com o que ficou na tela.
    """
    cancel_auto_outro()
    if modo not in ("retorno", "dispersar", "espalhar"):
        raise HTTPException(status_code=400, detail=f"Modo de saída inválido: {modo}")

    global _outro_limpeza_task

    tile_count = len(state.engine.placed_tiles)
    hold = float(state.config.get("outroHoldSeconds", 3.0))
    await broadcast_event("MOSAIC_OUTRO", {"tile_count": tile_count, "modo": modo, "hold": hold})

    # Os tiles NÃO são apagados aqui. O telão ainda vai remontar o mosaico
    # completo e segurá-lo parado por `hold` segundos; limpar agora liberaria as
    # células e uma foto nova entraria por baixo da imagem final. Quem limpa é a
    # tarefa abaixo, no fim do ciclo.
    if _outro_limpeza_task and not _outro_limpeza_task.done():
        _outro_limpeza_task.cancel()
    try:
        loop = asyncio.get_running_loop()
        _outro_limpeza_task = loop.create_task(_limpar_apos_outro(hold + OUTRO_MARGEM_ANIMACAO))
    except RuntimeError:
        # Sem event loop (chamada fora do servidor): limpa na hora, senão o
        # mosaico ficaria cheio para sempre e nada mais entraria.
        state.engine.placed_tiles.clear()
        state.engine.locked_tiles.clear()

    return {"status": "success", "dispersed_tiles": tile_count, "hold": hold}

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
    # "linha": de cima para baixo, como o telão desenha ao vivo. "centro": o
    # logo cresce do meio para as bordas.
    ordem: str = "linha"


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



def _ordem_aleatoria(celulas: list[tuple[int, int, float]]) -> list:
    """
    Embaralha as células, mas com peso pela cobertura.

    Aleatório puro faria muita foto cair nos pontinhos do halftone logo de
    cara, onde só se vê um grão. Aqui a chance de vir cedo é proporcional ao
    quanto o losango preenche o ladrilho: o resultado parece espalhado ao
    acaso, sem desperdiçar as primeiras fotos nas células piores.

    Amostragem ponderada sem reposição (Efraimidis-Spirakis): a chave
    `random ** (1/peso)` ordenada decrescente dá exatamente essa distribuição.
    """
    import random

    def chave(c):
        peso = max(0.01, c[2])
        return random.random() ** (1.0 / peso)

    return sorted(celulas, key=chave, reverse=True)


def _ordem_espalhada(celulas: list[tuple[int, int, float]], divisoes: int = 6) -> list:
    """
    Reordena as células para o logo crescer por inteiro em vez de por região.

    Divide o desenho numa malha de regiões, ordena cada uma pela cobertura e
    depois percorre em rodízio: a melhor da região 1, a melhor da região 2, e
    assim por diante. Sem isso, ordenar só por cobertura concentra tudo onde a
    arte é densa.
    """
    if not celulas:
        return []

    linhas = [c[0] for c in celulas]
    colunas = [c[1] for c in celulas]
    r0, r1 = min(linhas), max(linhas) + 1
    c0, c1 = min(colunas), max(colunas) + 1
    alt = max(1, (r1 - r0) / divisoes)
    larg = max(1, (c1 - c0) / divisoes)

    baldes: dict[tuple[int, int], list] = {}
    for celula in celulas:
        chave = (int((celula[0] - r0) / alt), int((celula[1] - c0) / larg))
        baldes.setdefault(chave, []).append(celula)

    for balde in baldes.values():
        balde.sort(key=lambda c: -c[2])

    # Regiões mais cheias primeiro, para o rodízio não começar pelas pontas.
    ordem_regioes = sorted(baldes, key=lambda k: -len(baldes[k]))
    saida = []
    passo = 0
    while len(saida) < len(celulas):
        for chave in ordem_regioes:
            balde = baldes[chave]
            if passo < len(balde):
                saida.append(balde[passo])
        passo += 1
    return saida


@app.post("/api/mosaic/grade-da-marca")
async def grade_da_marca(cobertura: float = 0.15, distribuicao: str = "visibilidade"):
    """
    Recorta a grade no formato do logo.

    Lê o overlay já publicado e marca como válidas apenas as células cujo
    ladrilho cai sobre uma parte transparente da arte — ou seja, onde a foto
    realmente vai aparecer. O motor passa a alocar só nessas células, então
    nenhuma foto é gasta numa posição que ficaria escondida atrás do preto.

    `cobertura` é a fração mínima do ladrilho sob a janela (0 a 1). Valores
    altos deixam só os losangos cheios; baixos incluem o halftone das pontas.

    `distribuicao` define a ORDEM de preenchimento gravada na máscara:
      - "visibilidade": as células mais cobertas primeiro. Cada foto aparece
        inteira, mas o logo enche por região — na arte do HSBC as células
        cheias estão todas do lado direito, então o mosaico cresce só ali.
      - "espalhado": percorre as regiões do desenho em rodízio, pegando a
        melhor célula de cada uma por vez. O logo inteiro se insinua desde as
        primeiras fotos, ao custo de usar células menos cobertas mais cedo.
      - "aleatorio": sorteia a ordem com peso pela cobertura. Espalha por todo
        o desenho sem padrão perceptível, mas ainda favorece os losangos
        cheios, então as primeiras fotos não caem só nos pontinhos.
    """
    from app.services import video_marca

    overlay = _caminho_overlay()
    if overlay is None:
        raise HTTPException(
            status_code=409,
            detail="Nenhum overlay de marca configurado. Suba a arte em Camadas > Logo Overlay.",
        )

    limite = max(0.0, min(1.0, cobertura))
    c = state.config
    _, alfa = video_marca.carregar_overlay(
        overlay, int(c.get("screenWidth", 1920)), int(c.get("screenHeight", 1080))
    )
    encontradas = video_marca.celulas_da_marca(
        alfa,
        int(c.get("rows", 38)), int(c.get("cols", 62)),
        float(c.get("gridOffsetX", 0)), float(c.get("gridOffsetY", 0)),
        float(c.get("gridWidth", c.get("screenWidth", 1920))),
        float(c.get("gridHeight", c.get("screenHeight", 1080))),
    )

    validas = [c for c in encontradas if c[2] >= limite]
    if distribuicao == "aleatorio":
        validas = _ordem_aleatoria(validas)
    elif distribuicao == "espalhado":
        validas = _ordem_espalhada(validas)
    else:
        # Da célula mais coberta pela arte para a menos coberta: as primeiras
        # fotos caem nos losangos cheios, onde aparecem inteiras, e não nos
        # pontinhos do halftone, onde mal se enxerga um pedaço.
        validas = sorted(validas, key=lambda c: -c[2])
    celulas = [f"{r}_{col}" for r, col, _ in validas]
    if not celulas:
        raise HTTPException(
            status_code=409,
            detail=f"Nenhuma célula atingiu {int(limite * 100)}% de cobertura. Reduza a exigência.",
        )

    config = state.apply_config({
        "customMaskCells": celulas,
        "gridContainerShape": "custom_mask",
    })
    await broadcast_event("CONFIG_UPDATED", config)

    total = int(c.get("rows", 38)) * int(c.get("cols", 62))
    print(f"[GradeDaMarca] {len(celulas)} de {total} células no formato do logo")
    return {
        "status": "success",
        "celulas": len(celulas),
        "total": total,
        "cobertura_minima": limite,
        "distribuicao": distribuicao,
    }


def _cenarios_disponiveis() -> list[dict]:
    """Manifesto gerado por tools/preparar_cenarios.py."""
    manifesto = settings.STORAGE_DIR / "cenarios" / "cenarios.json"
    if not manifesto.exists():
        return []
    try:
        return json.loads(manifesto.read_text(encoding="utf-8")).get("cenarios", [])
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[Cenários] Manifesto ilegível: {exc}")
        return []


@app.get("/api/cenarios")
async def listar_cenarios():
    """
    Cenários prontos do evento: cada um é um telão + arte + grade + máscara.

    O painel mostra só o resumo; a máscara inteira (centenas de células) fica
    fora daqui para não trafegar em toda abertura de tela.
    """
    atual = state.config.get("cenarioAtual")
    return {
        "atual": atual,
        "cenarios": [
            {
                "id": c["id"],
                "rotulo": c["rotulo"],
                "telao": f"{c['screenWidth']}x{c['screenHeight']}",
                "grade": f"{c['rows']}x{c['cols']}",
                "celulas": c["celulasNoLogo"],
                "vermelhas": c["celulasVermelhas"],
                "claras": c["celulasClaras"],
            }
            for c in _cenarios_disponiveis()
        ],
    }


def _agrupar_malha(
    rows: int,
    cols: int,
    mask_cells: list[str],
    cell_filters: dict[str, str],
    fator: int,
) -> tuple[int, int, list[str], dict[str, str]]:
    """
    Junta blocos de `fator`x`fator` células da malha numa célula só.

    Serve para fechar o mosaico com menos fotos SEM encolher o logo: a área da
    grade não muda, então cada ladrilho fica `fator` vezes maior. Com fator 2 as
    823 células da arte viram ~206, e cada foto passa a cobrir quatro losangos
    do halftone impresso — o desenho continua o mesmo, com menos resolução.

    Uma célula agrupada entra na máscara quando METADE ou mais das células
    originais dentro dela estavam na máscara. Com um limite mais frouxo o
    mosaico transborda o contorno do logo; mais apertado, come as bordas.

    A pintura segue a maioria do bloco: o que vale é a cor que domina a área que
    a foto vai cobrir.
    """
    if fator <= 1:
        return rows, cols, list(mask_cells), dict(cell_filters)

    originais = set(mask_cells)
    blocos: dict[tuple[int, int], list[str]] = {}
    for chave in originais:
        try:
            r, c = (int(p) for p in chave.split("_", 1))
        except ValueError:
            continue
        blocos.setdefault((r // fator, c // fator), []).append(chave)

    novas_rows = math.ceil(rows / fator)
    novas_cols = math.ceil(cols / fator)
    nova_mascara: list[str] = []
    nova_pintura: dict[str, str] = {}

    for (br, bc), membros in sorted(blocos.items()):
        # Quantas células o bloco teria se estivesse inteiro dentro da grade.
        altura = min(fator, rows - br * fator)
        largura = min(fator, cols - bc * fator)
        capacidade = max(1, altura * largura)
        if len(membros) / capacidade < 0.5:
            continue

        chave = f"{br}_{bc}"
        nova_mascara.append(chave)

        tintas = [cell_filters[m] for m in membros if m in cell_filters]
        if tintas:
            nova_pintura[chave] = max(set(tintas), key=tintas.count)

    return novas_rows, novas_cols, nova_mascara, nova_pintura


@app.post("/api/cenarios/{cenario_id}/aplicar")
async def aplicar_cenario(cenario_id: str, fotosClaras: str = "original", agrupamento: int = 1):
    """
    Troca o cenário inteiro numa tacada: resolução do telão, arte, grade,
    recorte no formato do logo e a pintura de cada célula.

    Os valores vêm calculados de `tools/preparar_cenarios.py`, que roda em cima
    da arte do cliente. Recalcular aqui, a cada troca, arriscaria dar resultado
    diferente do que foi conferido na hora de preparar.

    `fotosClaras` decide o que acontece nas células do branco do logo:
      - "original": a foto como ela é
      - "branco": um véu branco leve, para clarear sem apagar o rosto
    """
    cenario = next((c for c in _cenarios_disponiveis() if c["id"] == cenario_id), None)
    if cenario is None:
        raise HTTPException(status_code=404, detail=f"Cenário desconhecido: {cenario_id}")

    arquivo = settings.STORAGE_DIR / "cenarios" / cenario["arquivo"]
    if not arquivo.exists():
        raise HTTPException(status_code=409, detail=f"Arte do cenário não está no disco: {cenario['arquivo']}")

    fator = max(1, min(6, int(agrupamento)))

    pintura = dict(cenario["cellFilters"])
    if fotosClaras == "branco":
        # As claras são as células do branco do logo — as que não têm tinta.
        for chave in cenario["customMaskCells"]:
            pintura.setdefault(chave, "branco_leve")

    # O agrupamento entra DEPOIS do fotosClaras: assim a maioria do bloco é
    # calculada já com a pintura final, e não sobra bloco sem tinta.
    rows, cols, mascara, pintura = _agrupar_malha(
        cenario["rows"], cenario["cols"], cenario["customMaskCells"], pintura, fator
    )
    if fator > 1:
        print(
            f"[Cenários] Agrupamento {fator}x{fator}: "
            f"{cenario['rows']}x{cenario['cols']} ({len(cenario['customMaskCells'])} células) "
            f"-> {rows}x{cols} ({len(mascara)} células)"
        )

    config = state.apply_config({
        "screenWidth": cenario["screenWidth"],
        "screenHeight": cenario["screenHeight"],
        "rows": rows,
        "cols": cols,
        "gridOffsetX": cenario["gridOffsetX"],
        "gridOffsetY": cenario["gridOffsetY"],
        "gridWidth": cenario["gridWidth"],
        "gridHeight": cenario["gridHeight"],
        "customMaskCells": mascara,
        "gridContainerShape": "custom_mask",
        # Quadrado, não losango: o logo novo é cheio, e o ladrilho tem que
        # cobrir a célula inteira. Foi o losango sobre a arte picotada que
        # deixava aquele preto entre as fotos parecendo sombra.
        "gridShape": "square",
        # A arte volta a ser a moldura por cima do mosaico.
        "photosAboveBrand": False,
        "cellFilters": pintura,
        "foregroundUrl": f"/storage/cenarios/{cenario['arquivo']}?t={uuid.uuid4().hex[:8]}",
        # A imagem-base é a MESMA arte: sem trocar as duas juntas, o telão
        # mostra dois logos desencontrados.
        "targetBaseUrl": f"/storage/cenarios/{cenario['arquivo']}?t={uuid.uuid4().hex[:8]}",
        "cenarioAtual": cenario_id,
        "fotosClaras": fotosClaras,
        "cenarioAgrupamento": fator,
    })

    orfaos = state.engine.purge_tiles_outside_container()
    await broadcast_event("CONFIG_UPDATED", config)

    print(
        f"[Cenários] {cenario_id} aplicado: {len(mascara)} células "
        f"(agrupamento {fator}x{fator}), fotos claras={fotosClaras}"
    )
    return {
        "status": "success",
        "cenario": cenario_id,
        "telao": f"{cenario['screenWidth']}x{cenario['screenHeight']}",
        "grade": f"{rows}x{cols}",
        "celulas": len(mascara),
        "celulasOriginais": cenario["celulasNoLogo"],
        "agrupamento": fator,
        "liberados": len(orfaos),
    }


@app.post("/api/admin/limpeza-geral")
async def limpeza_geral(bucket: bool = False, galeria: bool = True):
    """
    Zera o evento: mosaico, filas, ladrilhos, hot folder e — se pedido — a
    galeria e o bucket S3.

    NÃO mexe na configuração nem nos arquivos da marca (overlay, imagem-base,
    fallbacks, vídeos exportados). Refazer o encaixe da grade é justamente o
    trabalho que não dá para repetir com o cliente esperando.

    O bucket é opcional e vem desligado: apagar o que está na nuvem é a única
    parte que não dá para refazer com uma nova bateria de fotos.
    """
    from app.services import limpeza

    # O watcher é parado ANTES: com ele de pé, os arquivos que ainda estão na
    # hot folder voltariam a ser ingeridos no meio da faxina e o evento novo já
    # começaria com foto do anterior.
    hot_folder_watcher.stop()
    s3_watcher.stop()
    try:
        if bucket:
            resultado_bucket = limpeza.esvaziar_bucket()
        else:
            resultado_bucket = {"ok": True, "detalhe": "Bucket preservado."}

        disco = limpeza.limpar_disco(
            settings.STORAGE_DIR,
            settings.BASE_DIR.parent / "Galeria",
            galeria,
        )

        s3_watcher.esquecer_tudo()
        state.reset_mosaic()
        state.tile_urls.clear()
    finally:
        # Mesmo se algo falhar, o sistema não pode ficar sem ingestão.
        hot_folder_watcher.start()
        s3_watcher.start()

    await broadcast_event("MOSAIC_RESET", {})
    await broadcast_event("RUN_STATE_CHANGED", {"run_state": state.run_state})
    print(f"[Limpeza] disco={disco} bucket={resultado_bucket} run_state={state.run_state}")
    # O reset volta para idle, e em idle a foto é aprovada mas NÃO pousa. Sem
    # dizer isso aqui, o operador limpa, solta as fotos e não entende por que a
    # tela continua vazia — foi exatamente o que aconteceu no primeiro teste.
    return {
        "status": "success",
        "disco": disco,
        "bucket": resultado_bucket,
        "run_state": state.run_state,
    }


@app.post("/api/mosaic/abrir-miolo-da-marca")
async def abrir_miolo_da_marca():
    """
    Estende a malha de losangos para dentro do miolo da marca.

    Na arte o miolo é chapa preta: o telão cobre o mosaico ali e nenhuma foto
    aparece. Aqui recortamos um losango em cada célula vaga do contorno e
    somamos essas células à máscara, no FIM da lista — assim a sequência
    "brand_first" continua enchendo primeiro os losangos originais do desenho.

    As células novas não recebem pintura: sem filtro, a foto fica na cor
    original. O contorno da marca segue tingido, e o miolo vira a área onde as
    pessoas se veem como são.
    """
    from app.services import meio_da_marca

    overlay = _caminho_overlay()
    if overlay is None:
        raise HTTPException(
            status_code=409,
            detail="Nenhum overlay de marca configurado. Suba a arte em Camadas > Logo Overlay.",
        )

    c = state.config
    if c.get("gridContainerShape") != "custom_mask" or not c.get("customMaskCells"):
        raise HTTPException(
            status_code=409,
            detail="Recorte a grade no formato do logo antes: use 'Formato do Logo'.",
        )

    rows, cols = int(c["rows"]), int(c["cols"])
    atuais = list(c["customMaskCells"])
    novas = meio_da_marca.celulas_do_miolo(atuais, rows, cols)
    if not novas:
        return {"status": "success", "novas": 0, "detalhe": "O miolo já está aberto."}

    # Backup antes de sobrescrever: a arte veio do cliente e o recorte é
    # destrutivo — sem cópia, refazer significaria pedir o arquivo de novo.
    original = overlay.with_name(f"{overlay.stem}_sem_miolo{overlay.suffix}")
    if not original.exists():
        original.write_bytes(overlay.read_bytes())

    recortados = meio_da_marca.recortar_losangos(
        original, overlay, novas, rows, cols,
        float(c.get("gridOffsetX", 0)), float(c.get("gridOffsetY", 0)),
        float(c.get("gridWidth", c.get("screenWidth", 1920))),
        float(c.get("gridHeight", c.get("screenHeight", 1080))),
        int(c.get("screenWidth", 1920)), int(c.get("screenHeight", 1080)),
    )

    # As células do miolo entram sem pintura: cor original.
    filtros = {k: v for k, v in (c.get("cellFilters") or {}).items() if k not in set(novas)}

    url = f"/storage/{overlay.name}?t={uuid.uuid4().hex[:8]}"
    config = state.apply_config({
        "customMaskCells": atuais + novas,
        "cellFilters": filtros,
        "foregroundUrl": url,
    })
    await broadcast_event("CONFIG_UPDATED", config)

    print(f"[MioloDaMarca] {recortados} losango(s) abertos; máscara agora com {len(atuais) + len(novas)} células.")
    return {
        "status": "success",
        "novas": len(novas),
        "recortados": recortados,
        "mascara": len(atuais) + len(novas),
        "url": url,
    }


@app.post("/api/mosaic/restaurar-marca-original")
async def restaurar_marca_original():
    """Desfaz a abertura do miolo: volta à arte como o cliente entregou."""
    overlay = _caminho_overlay()
    if overlay is None:
        raise HTTPException(status_code=409, detail="Nenhum overlay configurado.")

    original = overlay.with_name(f"{overlay.stem}_sem_miolo{overlay.suffix}")
    if not original.exists():
        raise HTTPException(status_code=409, detail="Não há arte original guardada — o miolo nunca foi aberto.")

    overlay.write_bytes(original.read_bytes())
    url = f"/storage/{overlay.name}?t={uuid.uuid4().hex[:8]}"
    config = state.apply_config({"foregroundUrl": url})
    await broadcast_event("CONFIG_UPDATED", config)
    return {
        "status": "success",
        "url": url,
        "detalhe": "Arte restaurada. Reencaixe a grade em 'Formato do Logo' para tirar as células do miolo.",
    }


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
        "maskStale": state.mask_stale,
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
                ordem="centro" if o.ordem == "centro" else "linha",
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
    """
    Arquivo local do overlay publicado na config, se existir.

    Preserva o caminho DENTRO de storage/. Antes só o nome do arquivo era
    aproveitado, e o overlay de um cenário — que mora em `storage/cenarios/` —
    nunca era encontrado: "Abrir o miolo" respondia 409 dizendo que não havia
    overlay configurado, com a arte do cenário na tela.
    """
    url = state.config.get("foregroundUrl")
    if not url:
        return None

    relativo = url.split("?")[0].lstrip("/")
    if relativo.startswith("storage/"):
        relativo = relativo[len("storage/"):]

    # `..` numa URL não pode escapar de storage/.
    caminho = (settings.STORAGE_DIR / relativo).resolve()
    try:
        caminho.relative_to(settings.STORAGE_DIR.resolve())
    except ValueError:
        print(f"[Overlay] Caminho fora de storage/, ignorado: {url}")
        return None

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
