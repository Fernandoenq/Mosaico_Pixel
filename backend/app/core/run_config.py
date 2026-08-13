"""
RunConfig — fonte única da verdade da configuração do mosaico.

O painel publica a configuração via PUT /api/config; o backend valida, persiste
em storage/run_config.json e retransmite por WebSocket. O telão apenas consome.
Persistir em disco garante que a config sobreviva a um restart do servidor no
meio do evento.

As chaves usam camelCase para bater 1:1 com o store do frontend
(frontend/src/store/mosaicStore.ts), dispensando camada de tradução.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings

CONFIG_PATH: Path = settings.STORAGE_DIR / "run_config.json"
# Separado do run_config.json: o transporte muda numa cadência diferente da
# config e o painel não deve conseguir sobrescrevê-lo por um PUT /api/config.
RUN_STATE_PATH: Path = settings.STORAGE_DIR / "run_state.json"
RUN_STATES = ("idle", "running", "paused")

GRID_SHAPES = {"square", "diamond", "hexagon", "circle"}
CONTAINER_SHAPES = {
    "rectangle",
    "diamond_mask",
    "hexagon_mask",
    "circle_mask",
    "hexagon_halftone",
    "auto_color_mask",
    "custom_mask",
}
# `explode_outro` saiu daqui de propósito: dispersar o mosaico é ação de
# encerramento (POST /api/mosaic/outro), não um preset de entrada por foto.
# Configs antigas que ainda tenham esse valor caem no default ao carregar.
ANIMATION_PRESETS = {
    "fly_parabolic",
    "hsbc_cascade",
    "spiral",
    "wave",
    "flip_3d",
}
# Como o mosaico se desfaz quando fica 100% cheio.
# `espalhar` é o do vídeo de referência do cliente, medido quadro a quadro:
# cada ladrilho anda pouco e apaga quase junto, sem voar para fora da tela.
OUTRO_MODES = {"dispersar", "espalhar", "retorno"}
FILL_SEQUENCES = {
    "color_match",
    "top_to_bottom",
    "bottom_to_top",
    "center_out",
    "random",
    "brand_first",
}
# "auto" = cada preset roda a sua curva característica (PRESET_DEFAULT_EASE no
# frontend). Qualquer outro valor é aplicado ao voo principal de todos eles.
ANIMATION_EASES = {
    "auto",
    "power3.inOut",
    "cubic.out",
    "elastic.out(1, 0.5)",
    "back.out(1.7)",
}

DEFAULT_LAYERS: list[dict] = [
    {"id": "base", "name": "Camada 0: Imagem Base", "visible": True, "opacity": 1.0, "blur": 0, "zIndex": 0},
    {"id": "landed", "name": "Camada 1: Fotos Pousadas", "visible": True, "opacity": 1.0, "blur": 0, "zIndex": 1},
    {"id": "flying", "name": "Camada 2: Foto Voadora Preview", "visible": True, "opacity": 1.0, "blur": 0, "zIndex": 2},
    {"id": "grid", "name": "Camada 3: Linhas de Grade", "visible": True, "opacity": 0.6, "blur": 0, "zIndex": 3},
    {"id": "logo", "name": "Camada 4: Logo Overlay", "visible": True, "opacity": 0.8, "blur": 0, "zIndex": 4},
    {"id": "text", "name": "Camada 5: Texto Overlay", "visible": True, "opacity": 1.0, "blur": 0, "zIndex": 5},
]

DEFAULTS: dict[str, Any] = {
    # Display / telão
    "screenWidth": settings.DEFAULT_SCREEN_WIDTH,
    "screenHeight": settings.DEFAULT_SCREEN_HEIGHT,
    # Grade
    "rows": settings.DEFAULT_GRID_ROWS,
    "cols": settings.DEFAULT_GRID_COLS,
    "gridOffsetX": 0,
    "gridOffsetY": 0,
    "gridWidth": settings.DEFAULT_SCREEN_WIDTH,
    "gridHeight": settings.DEFAULT_SCREEN_HEIGHT,
    "gridColor": "#00ffff",
    "gridThickness": 2,
    "gridOpacity": 0.6,
    "gridShape": "diamond",
    "gridContainerShape": "diamond_mask",
    # Animação
    "animationPreset": "hsbc_cascade",
    "animationDuration": 0.8,
    "animationEase": "auto",
    # Tempo em que a foto fica parada no centro do telão. É o momento em que a
    # pessoa se reconhece; abaixo de ~2s ela não consegue apontar para a tela.
    # Desligado, a foto voa direto para a celula: sem cartao no centro.
    "centralPreviewEnabled": True,
    "centralPreviewDuration": 10.0,
    # Lado do cartao de preview como fracao da altura do telao. Vive na
    # config (e nao no codigo) para o operador ajustar no painel e ver o
    # efeito na hora, sem recarregar o telao.
    "previewCardScale": 1.00,
    # Respiro entre um preview e o seguinte. Sem ele as fotos entram coladas
    # numa rajada e ninguem consegue acompanhar quem acabou de aparecer.
    "previewGapSeconds": 1.5,
    # Quantas fotos o telao monta AO MESMO TEMPO. Com o preview central
    # ligado vale sempre 1: so existe um cartao no centro da tela.
    "montagemSimultanea": 1,
    # Modo ocioso: sem foto nova por um tempo, o telao volta a destacar
    # fotos que ja estao no mosaico, para a tela nunca ficar parada.
    "idleReplayEnabled": True,
    "idleReplayDelay": 20.0,
    "idleReplayInterval": 5.0,
    # Pintura de áreas e máscara
    "cellFilters": {},
    "customMaskCells": [],
    "selectedBrushFilter": "red",
    # Preenchimento
    "fillSequence": "color_match",
    "autoDuplicateToFill": False,
    # Ritmo da duplicação gradual: uma cópia a cada N segundos, cada uma com a
    # mesma animação de foto nova.
    "duplicateIntervalSeconds": 3.0,
    "duplicateDistLimit": settings.DEFAULT_DUPLICATE_DIST_LIMIT,
    "colorStrictness": settings.DEFAULT_COLOR_STRICTNESS,
    # Ingestão / assets
    "hotFolderDir": "storage/hot_folder",
    "targetBaseUrl": None,
    # PNG com transparencia desenhado por cima de tudo (Camada 4). E o
    # recorte da marca: onde ele e transparente, o mosaico aparece.
    "foregroundUrl": None,
    # Fotos DESENHADAS POR CIMA do overlay da marca. Ligado, o mosaico cobre o
    # logo conforme enche; desligado, o logo fica sempre por cima.
    "photosAboveBrand": False,
    # Cenario do evento em uso (telao + arte + grade), de storage/cenarios.
    "cenarioAtual": None,
    # O que acontece nas celulas do BRANCO do logo: "original" ou "branco".
    "fotosClaras": "original",
    # Quantos losangos da malha impressa na arte cada foto cobre (NxN).
    # 1 = uma foto por losango (o desenho original do cliente). 2 = cada foto
    # cobre 4 losangos: o logo fica do MESMO tamanho na tela, com 1/4 das fotos
    # e cada ladrilho o dobro de largo. E o botao para o mosaico fechar mais
    # rapido sem trocar a arte.
    "cenarioAgrupamento": 1,
    "autoPlaceMode": True,
    # Aceita no mosaico duas fotos de conteudo identico. A cabine publica o
    # mesmo arquivo com dois nomes (`img_Nmasked` e `originals/...`); desligado,
    # so o primeiro entra. Ligado, os dois viram tile e o mosaico enche em
    # metade do tempo — a mesma pessoa aparece duas vezes, de proposito.
    # A trava por nome de arquivo continua valendo nos dois modos.
    "permitirFotosRepetidas": False,
    # Camadas
    "layers": DEFAULT_LAYERS,
    # Saída automática ao completar o mosaico. O ciclo é:
    #   cheio → espera `autoOutroDelaySeconds` → desfaz (`outroMode`) →
    #   remonta completo → segura `outroHoldSeconds` parado → limpa e enche de novo.
    "autoOutroOnComplete": True,
    "outroMode": "espalhar",
    "autoOutroDelaySeconds": 3.0,
    # Quanto tempo o mosaico completo fica parado na tela depois de remontar,
    # antes de limpar e recomeçar. Nenhuma foto nova anima durante esse tempo:
    # é o respiro para quem está na frente do telão fotografar o resultado.
    "outroHoldSeconds": 3.0,
}


def _int(minimum: int, maximum: int) -> Callable[[Any, Any], Any]:
    def coerce(value: Any, fallback: Any) -> Any:
        try:
            return max(minimum, min(maximum, int(value)))
        except (TypeError, ValueError):
            return fallback

    return coerce


def _float(minimum: float, maximum: float) -> Callable[[Any, Any], Any]:
    def coerce(value: Any, fallback: Any) -> Any:
        try:
            return max(minimum, min(maximum, float(value)))
        except (TypeError, ValueError):
            return fallback

    return coerce


def _enum(allowed: set[str]) -> Callable[[Any, Any], Any]:
    def coerce(value: Any, fallback: Any) -> Any:
        return value if isinstance(value, str) and value in allowed else fallback

    return coerce


def _bool(value: Any, fallback: Any) -> Any:
    return bool(value) if isinstance(value, bool) else fallback


def _color(value: Any, fallback: Any) -> Any:
    if isinstance(value, str) and value.startswith("#") and len(value) in (4, 7):
        try:
            int(value[1:], 16)
            return value
        except ValueError:
            return fallback
    return fallback


def _text(value: Any, fallback: Any) -> Any:
    return value if isinstance(value, str) else fallback


def _nullable_text(value: Any, fallback: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    return fallback


def _cell_filters(value: Any, fallback: Any) -> Any:
    if not isinstance(value, dict):
        return fallback
    cleaned: dict[str, str] = {}
    for key, filter_id in value.items():
        if not isinstance(key, str) or not isinstance(filter_id, str):
            continue
        parts = key.split("_")
        if len(parts) != 2 or not all(p.lstrip("-").isdigit() for p in parts):
            continue
        if filter_id in ("none", "clear", ""):
            continue
        cleaned[key] = filter_id
    return cleaned


def _mask_cells(value: Any, fallback: Any) -> Any:
    """
    Lista de células "linha_coluna" do contorno personalizado.

    Sem este coercer a chave não estava em COERCERS e o `merge_patch` a
    descartava calada — o modo `custom_mask` nunca chegava a ser publicado.
    """
    if not isinstance(value, list):
        return fallback
    limpas: list[str] = []
    vistas: set[str] = set()
    for item in value:
        if not isinstance(item, str) or item in vistas:
            continue
        partes = item.split("_")
        if len(partes) != 2 or not all(p.lstrip("-").isdigit() for p in partes):
            continue
        vistas.add(item)
        limpas.append(item)
    return limpas


def _layers(value: Any, fallback: Any) -> Any:
    if not isinstance(value, list):
        return fallback
    cleaned: list[dict] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            continue
        default = next((l for l in DEFAULT_LAYERS if l["id"] == raw["id"]), {})
        cleaned.append(
            {
                "id": raw["id"],
                "name": _text(raw.get("name"), default.get("name", raw["id"])),
                "visible": _bool(raw.get("visible"), default.get("visible", True)),
                "opacity": _float(0.0, 1.0)(raw.get("opacity"), default.get("opacity", 1.0)),
                "blur": _int(0, 40)(raw.get("blur"), default.get("blur", 0)),
                "zIndex": _int(0, 99)(raw.get("zIndex"), default.get("zIndex", index)),
            }
        )
    return cleaned or fallback


COERCERS: dict[str, Callable[[Any, Any], Any]] = {
    "screenWidth": _int(320, 16384),
    "screenHeight": _int(240, 16384),
    "rows": _int(2, 200),
    "cols": _int(2, 200),
    "gridOffsetX": _int(-16384, 16384),
    "gridOffsetY": _int(-16384, 16384),
    "gridWidth": _int(50, 16384),
    "gridHeight": _int(50, 16384),
    "gridColor": _color,
    "gridThickness": _int(1, 12),
    "gridOpacity": _float(0.0, 1.0),
    "gridShape": _enum(GRID_SHAPES),
    "gridContainerShape": _enum(CONTAINER_SHAPES),
    "animationPreset": _enum(ANIMATION_PRESETS),
    "animationDuration": _float(0.1, 10.0),
    "animationEase": _enum(ANIMATION_EASES),
    "centralPreviewEnabled": _bool,
    "centralPreviewDuration": _float(0.0, 20.0),
    "previewCardScale": _float(0.20, 1.00),
    "previewGapSeconds": _float(0.0, 30.0),
    "montagemSimultanea": _int(1, 8),
    "idleReplayEnabled": _bool,
    "idleReplayDelay": _float(3.0, 600.0),
    "idleReplayInterval": _float(0.0, 300.0),
    "cellFilters": _cell_filters,
    "customMaskCells": _mask_cells,
    "selectedBrushFilter": _text,
    "fillSequence": _enum(FILL_SEQUENCES),
    "autoDuplicateToFill": _bool,
    "duplicateIntervalSeconds": _float(0.2, 60.0),
    "duplicateDistLimit": _int(0, 50),
    "colorStrictness": _float(0.0, 5.0),
    "hotFolderDir": _text,
    "targetBaseUrl": _nullable_text,
    "foregroundUrl": _nullable_text,
    "photosAboveBrand": _bool,
    "cenarioAtual": _nullable_text,
    "fotosClaras": _enum(("original", "branco")),
    "cenarioAgrupamento": _int(1, 6),
    "autoPlaceMode": _bool,
    "permitirFotosRepetidas": _bool,
    "layers": _layers,
    # Estas quatro faltavam aqui: sem coercer, `merge_patch` descarta a chave em
    # silêncio e o valor do painel nunca chegava a valer. Os controles de saída
    # no Animation Studio eram decorativos — o modo ficava preso no default.
    "autoOutroOnComplete": _bool,
    "outroMode": _enum(OUTRO_MODES),
    "autoOutroDelaySeconds": _float(0.0, 60.0),
    "outroHoldSeconds": _float(0.0, 30.0),
}


def default_config() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULTS))


def merge_patch(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """
    Aplica um patch parcial sobre a config atual. Chaves desconhecidas são
    ignoradas e valores inválidos caem no valor atual — um painel com bug nunca
    derruba o telão.
    """
    merged = json.loads(json.dumps(current))
    if not isinstance(patch, dict):
        return merged

    for key, value in patch.items():
        coerce = COERCERS.get(key)
        if coerce is None:
            continue
        merged[key] = coerce(value, merged.get(key, DEFAULTS.get(key)))

    return merged


def load_config() -> dict[str, Any]:
    config = default_config()
    if not CONFIG_PATH.exists():
        return config
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[RunConfig] Falha ao ler {CONFIG_PATH}, usando defaults: {exc}")
        return config
    return merge_patch(config, stored if isinstance(stored, dict) else {})


def _write_atomic(path: Path, payload: Any, label: str) -> None:
    """Grava em temporário e substitui, evitando JSON truncado por queda no meio."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), prefix=f".{path.stem}-", suffix=".tmp", delete=False
    )
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(handle.name, path)
    except OSError as exc:
        print(f"[RunConfig] Falha ao salvar {label}: {exc}")
        try:
            os.unlink(handle.name)
        except OSError:
            pass


def save_config(config: dict[str, Any]) -> None:
    _write_atomic(CONFIG_PATH, config, "config")


def load_run_state() -> str:
    """Transporte persistido. Qualquer conteúdo estranho cai em 'idle'."""
    if not RUN_STATE_PATH.exists():
        return "idle"
    try:
        with RUN_STATE_PATH.open("r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[RunConfig] Falha ao ler {RUN_STATE_PATH}, assumindo idle: {exc}")
        return "idle"
    value = stored.get("runState") if isinstance(stored, dict) else None
    return value if value in RUN_STATES else "idle"


def save_run_state(value: str) -> None:
    if value not in RUN_STATES:
        return
    _write_atomic(RUN_STATE_PATH, {"runState": value}, "run_state")
