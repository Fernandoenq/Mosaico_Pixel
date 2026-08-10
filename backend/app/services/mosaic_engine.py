import numpy as np
import cv2

class MosaicEngine:
    """
    Motor de processamento de True Photo Mosaic usando NumPy e OpenCV.
    Calcula as cores médias das células em espaço perceptual LAB e aloca
    fotos de forma otimizada com trava de distância de duplicadas.
    """
    def __init__(self, target_image_bgr: np.ndarray, rows: int = 30, cols: int = 40, container_shape: str = "rectangle", custom_mask_cells: list = None):
        self.rows = rows
        self.cols = cols
        # Contorno da região do mosaico. O frontend NÃO desenha células fora
        # dele, então alocar uma foto ali equivale a perdê-la.
        self.container_shape = container_shape
        self.custom_mask_cells = set(custom_mask_cells) if custom_mask_cells else set()
        # Ordem de prioridade da máscara: quem vem antes na lista é preenchido
        # antes na sequência "brand_first". O gerador da grade entrega as
        # células ordenadas da mais visível para a menos visível.
        self.mask_order = self._indexar_mascara(custom_mask_cells)
        self.target_image = target_image_bgr
        self.h, self.w = target_image_bgr.shape[:2]
        self.tile_h = self.h // rows
        self.tile_w = self.w // cols
        
        # Matriz de cores LAB médias para cada célula do grid (shape: [rows, cols, 3])
        self.grid_lab_colors = np.zeros((rows, cols, 3), dtype=np.float32)
        self.grid_bgr_colors = np.zeros((rows, cols, 3), dtype=np.float32)
        self._calculate_grid_colors()
        
        # Rastreamento de células ocupadas: (row, col) -> photo_id
        self.placed_tiles: dict[tuple[int, int], str] = {}
        # Trava manual de células (Right-Click Lock): (row, col) -> bool
        self.locked_tiles: set[tuple[int, int]] = set()

    def cell_in_container(self, r: int, c: int) -> bool:
        """
        Espelha isCellInsideContainerMask() do PixiViewport.

        O teste depende só da posição RELATIVA da célula na grade — offset e
        tamanho em pixels se cancelam na normalização —, então backend e
        frontend chegam ao mesmo resultado sem trocar geometria.
        """
        shape = self.container_shape
        if shape == "rectangle" or not shape:
            return True
        if self.rows <= 0 or self.cols <= 0:
            return True

        dx = abs(2.0 * (c + 0.5) / self.cols - 1.0)
        dy = abs(2.0 * (r + 0.5) / self.rows - 1.0)

        if shape == "diamond_mask":
            return dx + dy <= 1.02
        if shape in ("hexagon_mask", "hexagon_halftone"):
            return dx <= 1.01 and dy <= 1.01 and (dx * 0.5 + dy * 0.866 <= 1.01)
        if shape == "circle_mask":
            return dx * dx + dy * dy <= 1.04
        if shape == "custom_mask":
            return f"{r}_{c}" in self.custom_mask_cells
        return True

    def available_cells(self) -> list[tuple[int, int]]:
        """Células vagas, dentro do contorno e não travadas."""
        return [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if (r, c) not in self.placed_tiles
            and (r, c) not in self.locked_tiles
            and self.cell_in_container(r, c)
        ]

    def purge_tiles_outside_container(self) -> list[tuple[int, int]]:
        """
        Libera ladrilhos que ficaram fora do contorno depois de uma mudança de
        forma ou de grade. Eles são invisíveis no telão; mantê-los só ocuparia
        células e falsearia a contagem de preenchimento.
        """
        orphans = [cell for cell in self.placed_tiles if not self.cell_in_container(*cell)]
        for cell in orphans:
            self.placed_tiles.pop(cell, None)
            self.locked_tiles.discard(cell)
        return orphans

    @staticmethod
    def _indexar_mascara(custom_mask_cells: list | None) -> dict:
        """Posição de cada célula na lista da máscara, para ordenar depois."""
        if not custom_mask_cells:
            return {}
        ordem = {}
        for i, chave in enumerate(custom_mask_cells):
            try:
                r, c = (int(x) for x in str(chave).split("_"))
            except (ValueError, TypeError):
                continue
            ordem.setdefault((r, c), i)
        return ordem

    def set_container_shape(self, shape: str, custom_mask_cells: list = None):
        self.container_shape = shape
        self.custom_mask_cells = set(custom_mask_cells) if custom_mask_cells else set()
        self.mask_order = self._indexar_mascara(custom_mask_cells)

    def update_grid(self, target_image_bgr: np.ndarray, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.target_image = target_image_bgr
        self.h, self.w = target_image_bgr.shape[:2]
        self.tile_h = self.h // rows
        self.tile_w = self.w // cols
        self.grid_lab_colors = np.zeros((rows, cols, 3), dtype=np.float32)
        self.grid_bgr_colors = np.zeros((rows, cols, 3), dtype=np.float32)
        self._calculate_grid_colors()

    def _calculate_grid_colors(self):
        lab_img = cv2.cvtColor(self.target_image, cv2.COLOR_BGR2LAB).astype(np.float32)
        bgr_img = self.target_image.astype(np.float32)
        
        for r in range(self.rows):
            for c in range(self.cols):
                y0, y1 = r * self.tile_h, (r + 1) * self.tile_h
                x0, x1 = c * self.tile_w, (c + 1) * self.tile_w
                
                self.grid_lab_colors[r, c] = np.mean(lab_img[y0:y1, x0:x1], axis=(0, 1))
                self.grid_bgr_colors[r, c] = np.mean(bgr_img[y0:y1, x0:x1], axis=(0, 1))

    def find_best_tile_position(
        self,
        photo_bgr: np.ndarray,
        photo_id: str,
        duplicate_dist_limit: int = 3,
        strictness: float = 1.0,
        fill_sequence: str = "color_match"
    ) -> tuple[int, int, float]:
        """
        Encontra a melhor célula vaga no grid com suporte a sequências de início:
        - color_match: Menor distância de cor LAB
        - top_to_bottom: Sequencial de cima para baixo
        - bottom_to_top: Sequencial de baixo para cima
        - center_out: Expansão a partir do centro
        - random: Seleção aleatória
        - brand_first: Ordem da máscara da marca (mais visível primeiro)
        """
        # Só células dentro do contorno: as de fora não são desenhadas pelo
        # telão, então colocar uma foto ali é o mesmo que descartá-la.
        empty_cells = self.available_cells()

        is_full = False
        if not empty_cells:
            is_full = True
            # Mosaico cheio: reaproveita qualquer célula destravada do contorno
            empty_cells = [
                (r, c)
                for r in range(self.rows)
                for c in range(self.cols)
                if (r, c) not in self.locked_tiles and self.cell_in_container(r, c)
            ]
            if not empty_cells:
                empty_cells = [(0, 0)]

        if is_full:
            import random
            best_cell = random.choice(empty_cells)
            best_score = 0.0
        elif fill_sequence == "top_to_bottom":
            best_cell = empty_cells[0]
            best_score = 0.0
        elif fill_sequence == "bottom_to_top":
            empty_cells.sort(key=lambda cell: (-cell[0], cell[1]))
            best_cell = empty_cells[0]
            best_score = 0.0
        elif fill_sequence == "center_out":
            cr, cc = self.rows / 2.0, self.cols / 2.0
            empty_cells.sort(key=lambda cell: (cell[0] - cr) ** 2 + (cell[1] - cc) ** 2)
            best_cell = empty_cells[0]
            best_score = 0.0
        elif fill_sequence == "brand_first":
            # Preenche pela ordem da máscara da marca: os losangos cheios
            # primeiro, o halftone das pontas por último. Com poucas fotos o
            # logo já nasce legível, em vez de começar pelos pontinhos onde a
            # foto aparece do tamanho de um grão.
            if self.mask_order:
                empty_cells.sort(key=lambda cell: self.mask_order.get(cell, 10**9))
            else:
                cr, cc = self.rows / 2.0, self.cols / 2.0
                empty_cells.sort(key=lambda cell: (cell[0] - cr) ** 2 + (cell[1] - cc) ** 2)
            best_cell = empty_cells[0]
            best_score = 0.0
        elif fill_sequence == "random":
            import random
            best_cell = random.choice(empty_cells)
            best_score = 0.0
        else:
            # color_match (Perceptual LAB)
            photo_lab = cv2.cvtColor(photo_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
            photo_mean_lab = np.mean(photo_lab, axis=(0, 1))

            best_score = float('inf')
            best_cell = empty_cells[0]

            for (r, c) in empty_cells:
                color_dist = np.linalg.norm(self.grid_lab_colors[r, c] - photo_mean_lab) * strictness
                penalty = 0.0
                for (pr, pc), pid in self.placed_tiles.items():
                    if pid == photo_id:
                        dist = abs(r - pr) + abs(c - pc)
                        if dist <= duplicate_dist_limit:
                            penalty += (duplicate_dist_limit - dist + 1) * 150.0

                score = color_dist + penalty
                if score < best_score:
                    best_score = score
                    best_cell = (r, c)

        r, c = best_cell
        self.placed_tiles[(r, c)] = photo_id
        return r, c, float(best_score)

    def get_top_5_suggestions_for_cell(
        self,
        r: int,
        c: int,
        available_photos: list[dict]
    ) -> list[dict]:
        """
        Para o modal de substituição manual (Left-Click), calcula as 5 fotos
        que possuem a cor mais próxima da célula (r, c) informada.
        """
        cell_lab = self.grid_lab_colors[r, c]
        scored_photos = []
        
        for photo in available_photos:
            photo_bgr = photo.get("image_bgr")
            if photo_bgr is None:
                continue
                
            photo_lab = cv2.cvtColor(photo_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
            photo_mean_lab = np.mean(photo_lab, axis=(0, 1))
            dist = float(np.linalg.norm(cell_lab - photo_mean_lab))
            
            scored_photos.append({
                "id": photo["id"],
                "url": photo["url"],
                "score": dist
            })
            
        scored_photos.sort(key=lambda x: x["score"])
        return scored_photos[:5]

    def lock_tile(self, r: int, c: int):
        self.locked_tiles.add((r, c))

    def unlock_tile(self, r: int, c: int):
        self.locked_tiles.discard((r, c))

    def remove_tile(self, r: int, c: int) -> str | None:
        self.locked_tiles.discard((r, c))
        return self.placed_tiles.pop((r, c), None)
