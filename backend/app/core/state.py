import numpy as np

from app.core import run_config
from app.services.mosaic_engine import MosaicEngine
from app.services.queue_manager import QueueManager

RUN_STATES = ("idle", "running", "paused")


class MosaicState:
    """
    Estado vivo do evento. A configuração (`self.config`) é a fonte da verdade
    compartilhada entre painel e telão; `run_state` controla se o show está
    rodando. Os atributos legados (rows, cols, layers, ...) são views sobre a
    config para que o resto do código continue funcionando sem alteração.
    """

    def __init__(self):
        self.config = run_config.load_config()
        # Restaurado do disco: um restart do backend no meio do evento (ou o
        # --reload em desenvolvimento) voltava o show para "idle" em silêncio, e
        # as fotos continuavam chegando sem nunca pousar no telão.
        self.run_state: str = run_config.load_run_state()
        # Enquanto nenhuma imagem base for enviada, o alvo é um placeholder do
        # tamanho do telão — precisa ser regerado quando a resolução muda.
        self.has_target_image = False
        # Máscara do logo desatualizada em relação à geometria atual.
        self.mask_stale = False

        self.target_image_bgr = self._build_placeholder_target()
        # As células do contorno personalizado precisam vir JUNTO na construção.
        # Sem elas o motor nascia com `container_shape="custom_mask"` e a máscara
        # vazia: nenhuma célula era considerada válida e toda foto acabava na
        # (0,0), o último recurso de `find_best_tile_position`. Só aparecia
        # depois de um restart do backend, quando a config já vem do disco.
        self.engine = MosaicEngine(
            self.target_image_bgr,
            self.rows,
            self.cols,
            container_shape=self.container_shape,
            custom_mask_cells=self.custom_mask_cells,
        )
        self.queue_manager = QueueManager()
        # URL de cada ladrilho pousado, por photo_id. O preenchimento por
        # duplicatas pode usar arquivos de `storage/tiles` que nunca passaram
        # pela fila de moderação: sem este registro, `placed_tiles_payload` não
        # acha a URL e um telão que reconecta recebe o mosaico VAZIO.
        self.tile_urls: dict[str, str] = {}

    # --- Views sobre a config (compatibilidade com o código existente) ---

    @property
    def rows(self) -> int:
        return int(self.config["rows"])

    @rows.setter
    def rows(self, value: int):
        self.config["rows"] = int(value)

    @property
    def cols(self) -> int:
        return int(self.config["cols"])

    @cols.setter
    def cols(self, value: int):
        self.config["cols"] = int(value)

    @property
    def duplicate_dist_limit(self) -> int:
        return int(self.config["duplicateDistLimit"])

    @duplicate_dist_limit.setter
    def duplicate_dist_limit(self, value: int):
        self.config["duplicateDistLimit"] = int(value)

    @property
    def color_strictness(self) -> float:
        return float(self.config["colorStrictness"])

    @color_strictness.setter
    def color_strictness(self, value: float):
        self.config["colorStrictness"] = float(value)

    @property
    def fill_sequence(self) -> str:
        return str(self.config["fillSequence"])

    @property
    def container_shape(self) -> str:
        return str(self.config["gridContainerShape"])

    @property
    def custom_mask_cells(self) -> list:
        return self.config.get("customMaskCells", [])

    @property
    def layers(self) -> list:
        return self.config["layers"]

    @layers.setter
    def layers(self, value: list):
        self.config["layers"] = value

    @property
    def target_base_url(self):
        return self.config["targetBaseUrl"]

    @target_base_url.setter
    def target_base_url(self, value):
        self.config["targetBaseUrl"] = value

    # --- Imagem alvo e grade ---

    def _build_placeholder_target(self) -> np.ndarray:
        height = int(self.config["screenHeight"])
        width = int(self.config["screenWidth"])
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[:, :] = (200, 30, 30)  # Vermelho de teste
        return image

    def set_target_image(self, image_bgr: np.ndarray):
        self.target_image_bgr = image_bgr
        self.has_target_image = True
        self.engine.update_grid(self.target_image_bgr, self.rows, self.cols)

    def set_grid_dimensions(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.engine.update_grid(self.target_image_bgr, self.rows, self.cols)

    # --- Configuração publicada pelo painel ---

    def apply_config(self, patch: dict) -> dict:
        """
        Aplica um patch parcial, persiste em disco e reconstrói o motor quando a
        geometria muda. Retorna a config completa já validada.
        """
        previous = self.config
        self.config = run_config.merge_patch(previous, patch)
        run_config.save_config(self.config)

        changed = {key for key, value in self.config.items() if previous.get(key) != value}
        needs_regrid = bool({"rows", "cols"} & changed)

        if {"screenWidth", "screenHeight"} & changed and not self.has_target_image:
            self.target_image_bgr = self._build_placeholder_target()
            needs_regrid = True

        if needs_regrid:
            self.engine.update_grid(self.target_image_bgr, self.rows, self.cols)

        # O contorno define quais células o telão desenha. Sem isso no motor,
        # fotos são alocadas em células invisíveis e somem.
        if "gridContainerShape" in changed or "customMaskCells" in changed:
            self.engine.set_container_shape(self.container_shape, getattr(self, "custom_mask_cells", []))

        if needs_regrid or "gridContainerShape" in changed or "customMaskCells" in changed:
            orphans = self.engine.purge_tiles_outside_container()
            if orphans:
                print(f"[Config] {len(orphans)} ladrilho(s) fora do novo contorno foram liberados.")

        # A máscara do logo é um recorte calculado EM CIMA de uma geometria
        # específica. Mexer na grade ou no enquadramento sem recalcular deixa
        # cada célula apontando para outro pedaço da arte, e o mosaico para de
        # casar com o desenho. Aqui só sinalizamos — quem recalcula é o painel,
        # via POST /api/mosaic/grade-da-marca.
        geometria = {"rows", "cols", "gridOffsetX", "gridOffsetY", "gridWidth", "gridHeight"}
        if (geometria & changed) and self.container_shape == "custom_mask" and self.custom_mask_cells:
            self.mask_stale = True
            print(
                "[Config] AVISO: a geometria mudou e o contorno é o do logo. "
                "A máscara está defasada — reencaixe em 'Formato do Logo'."
            )
        elif "customMaskCells" in changed:
            self.mask_stale = False

        return self.config

    # --- Transporte (play / pause / stop / reset) ---

    def set_run_state(self, value: str) -> str:
        if value not in RUN_STATES:
            raise ValueError(f"run_state inválido: {value}")
        self.run_state = value
        run_config.save_run_state(value)
        return self.run_state

    def reset_mosaic(self):
        """Zera o mosaico para o próximo evento. Não mexe na configuração."""
        self.engine.placed_tiles.clear()
        self.engine.locked_tiles.clear()
        self.tile_urls.clear()
        self.queue_manager = QueueManager()
        self.set_run_state("idle")

    def register_tile_url(self, photo_id: str, url: str):
        """Guarda a URL usada no TILE_PLACED para reconstruir o estado depois."""
        if photo_id and url:
            self.tile_urls[photo_id] = url

    def placed_tiles_payload(self) -> list[dict]:
        """
        Tiles já pousados, no mesmo formato do evento TILE_PLACED. Permite que um
        telão que conecte no meio do evento se recupere sem perder o mosaico.
        """
        url_by_id = {
            item["id"]: item["url"]
            for item in self.queue_manager.approved_photos + self.queue_manager.brand_fallbacks
        }

        payload = []
        for (row, col), photo_id in self.engine.placed_tiles.items():
            url = (
                self.tile_urls.get(photo_id)
                or url_by_id.get(photo_id)
                or url_by_id.get(photo_id.split("_dup_")[0])
            )
            if not url:
                continue
            payload.append(
                {
                    "photo_id": photo_id,
                    "url": url,
                    "row": row,
                    "col": col,
                    "target_x": col * self.engine.tile_w,
                    "target_y": row * self.engine.tile_h,
                    "score": 0.0,
                }
            )
        return payload


state = MosaicState()
