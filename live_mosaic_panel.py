#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Painel de mosaico ao vivo para exibir imagens monitoradas em tempo real.
"""

from pathlib import Path
import tkinter as tk
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageTk


class LiveMosaicPanel:
    def __init__(self, master: tk.Tk, largura: int, altura: int, fundo_path: str | None = None, celula_px: int = 90):
        self.master = master
        self.width = max(320, int(largura))
        self.height = max(240, int(altura))
        self.cell_size = max(40, int(celula_px))
        self.cols = max(1, self.width // self.cell_size)
        self.rows = max(1, self.height // self.cell_size)
        self.max_cells = self.cols * self.rows
        self.cursor = 0
        self._entrada_anim_ms = 520
        self._entrada_anim_frames = 11
        self._stagger_ms = 140
        self._opacidade_mosaico = 0.58
        self._spotlight_hold_ms = 1700
        self._spotlight_pop_ms = 920
        self._spotlight_sustain_ms = 2100
        self._spotlight_return_ms = 1200
        self._spotlight_scale_center = 3.2

        self.window = tk.Toplevel(master)
        self.window.title("Mosaico Ao Vivo")
        self.window.geometry(f"{self.width}x{self.height}")
        self.window.resizable(False, False)

        self.canvas = tk.Canvas(self.window, width=self.width, height=self.height, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self._background_image = None
        self._fundo_imgtk = None
        self._tile_refs = []
        self._tile_items = [None] * self.max_cells
        self._tile_images = [None] * self.max_cells
        self._stagger_job = None
        self._spotlight_item = None
        self._focus_overlay_item = None
        self._focus_overlay_photo = None
        self._spotlight_running = False
        self._preview_hide_job = None
        self._pending_spotlights: list[int] = []
        self._queue_token = 0
        self._apply_background(fundo_path)

    def _apply_background(self, fundo_path: str | None):
        if fundo_path and Path(fundo_path).exists():
            bg_img = Image.open(fundo_path).convert("RGB")
        else:
            bg_img = Image.new("RGB", (self.width, self.height), (255, 255, 255))

        bg_img = bg_img.resize((self.width, self.height), Image.Resampling.LANCZOS)
        self._background_image = bg_img.copy()
        self._fundo_imgtk = ImageTk.PhotoImage(bg_img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._fundo_imgtk)
        self._tile_refs.clear()
        self._tile_items = [None] * self.max_cells
        self._tile_images = [None] * self.max_cells
        self.cursor = 0
        self._spotlight_item = None
        self._focus_overlay_item = None
        self._focus_overlay_photo = None
        self._spotlight_running = False
        self._preview_hide_job = None
        self._pending_spotlights.clear()
        self._queue_token += 1

    def _cell_xy(self, index: int):
        row = index // self.cols
        col = index % self.cols
        return col * self.cell_size, row * self.cell_size

    def _cell_background(self, x: int, y: int):
        if self._background_image is None:
            return Image.new("RGB", (self.cell_size, self.cell_size), (255, 255, 255))
        return self._background_image.crop((x, y, x + self.cell_size, y + self.cell_size))

    def _compor_frame_tile(self, tile_base: Image.Image, bg_cell: Image.Image, progress: float):
        progress = max(0.0, min(1.0, progress))
        scale = 0.8 + (0.2 * progress)
        blur_radius = 10.0 * (1.0 - progress)
        opacity = self._opacidade_mosaico * progress
        glow_strength = max(0.0, 1.0 - progress)

        tile_rgba = tile_base.convert("RGBA")
        if blur_radius > 0.05:
            tile_rgba = tile_rgba.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        scaled = max(1, int(self.cell_size * scale))
        tile_rgba = tile_rgba.resize((scaled, scaled), Image.Resampling.LANCZOS)

        frame = Image.new("RGBA", (self.cell_size, self.cell_size), (0, 0, 0, 0))
        offset = (self.cell_size - scaled) // 2
        frame.paste(tile_rgba, (offset, offset), tile_rgba)

        alpha = frame.getchannel("A").point(lambda px: int(px * opacity))
        frame.putalpha(alpha)

        if glow_strength > 0.0:
            glow_alpha = int(145 * glow_strength)
            overlay = Image.new("RGBA", (self.cell_size, self.cell_size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.rectangle(
                (1, 1, self.cell_size - 2, self.cell_size - 2),
                outline=(167, 115, 255, glow_alpha),
                width=2,
            )
            overlay = overlay.filter(ImageFilter.GaussianBlur(radius=2))
            frame = Image.alpha_composite(frame, overlay)

        base = bg_cell.convert("RGBA")
        return Image.alpha_composite(base, frame).convert("RGB")

    @staticmethod
    def _ease_out_cubic(t: float):
        t = max(0.0, min(1.0, t))
        return 1 - ((1 - t) ** 3)

    @staticmethod
    def _ease_in_out_cubic(t: float):
        t = max(0.0, min(1.0, t))
        if t < 0.5:
            return 4 * t * t * t
        return 1 - ((-2 * t + 2) ** 3) / 2

    @staticmethod
    def _ease_out_back(t: float):
        t = max(0.0, min(1.0, t))
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * ((t - 1) ** 3) + c1 * ((t - 1) ** 2)

    def _render_tile_static(self, index: int):
        tile = self._tile_images[index]
        if tile is None:
            return
        x, y = self._cell_xy(index)
        bg = self._cell_background(x, y)
        frame_final = self._compor_frame_tile(tile, bg, progress=1.0)
        tile_imgtk = ImageTk.PhotoImage(frame_final)
        if self._tile_items[index] is None:
            self._tile_items[index] = self.canvas.create_image(x, y, anchor="nw", image=tile_imgtk, tags=("tiles",))
        else:
            self.canvas.itemconfigure(self._tile_items[index], image=tile_imgtk)
            self.canvas.coords(self._tile_items[index], x, y)
        self._tile_refs.append(tile_imgtk)

    def _set_focus_overlay(self, enabled: bool):
        if enabled:
            if self._focus_overlay_item is not None:
                return
            if self._background_image is None:
                return
            blurred = self._background_image.filter(ImageFilter.GaussianBlur(radius=5))
            dark = Image.new("RGBA", (self.width, self.height), (12, 10, 18, 135))
            base = blurred.convert("RGBA")
            merged = Image.alpha_composite(base, dark)
            self._focus_overlay_photo = ImageTk.PhotoImage(merged)
            self._focus_overlay_item = self.canvas.create_image(
                0, 0, anchor="nw", image=self._focus_overlay_photo, tags=("focus_overlay",)
            )
        else:
            if self._focus_overlay_item is not None:
                self.canvas.delete(self._focus_overlay_item)
                self._focus_overlay_item = None
            self._focus_overlay_photo = None

    def _build_spotlight_rgba(self, tile_base: Image.Image, scale: float, blur_radius: float, glow_strength: float):
        base_size = max(1, int(self.cell_size * scale))
        tile_rgba = tile_base.convert("RGBA").resize((base_size, base_size), Image.Resampling.LANCZOS)
        if blur_radius > 0.01:
            tile_rgba = tile_rgba.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        canvas_size = base_size + 44
        frame = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        offset = (canvas_size - base_size) // 2
        frame.paste(tile_rgba, (offset, offset), tile_rgba)

        if glow_strength > 0.0:
            glow_alpha = int(170 * glow_strength)
            overlay = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.rectangle(
                (offset + 2, offset + 2, offset + base_size - 3, offset + base_size - 3),
                outline=(167, 115, 255, glow_alpha),
                width=3,
            )
            overlay = overlay.filter(ImageFilter.GaussianBlur(radius=3))
            frame = Image.alpha_composite(frame, overlay)
        return frame

    def _play_spotlight_cycle(self, index: int):
        tile = self._tile_images[index]
        if tile is None or not self.window.winfo_exists():
            return

        target_x, target_y = self._cell_xy(index)
        center_x = self.width // 2
        center_y = self.height // 2
        start_center_x = target_x + self.cell_size // 2
        start_center_y = target_y + self.cell_size // 2

        self._spotlight_running = True
        self._set_focus_overlay(True)
        if self._tile_items[index] is not None:
            self.canvas.itemconfigure(self._tile_items[index], state="hidden")

        if self._spotlight_item is None:
            placeholder = ImageTk.PhotoImage(Image.new("RGBA", (2, 2), (0, 0, 0, 0)))
            self._spotlight_item = self.canvas.create_image(center_x, center_y, anchor="center", image=placeholder, tags=("spotlight",))
            self._tile_refs.append(placeholder)

        pop_frames = 12
        sustain_frames = 14
        return_frames = 14
        total_ms = self._spotlight_pop_ms + self._spotlight_sustain_ms + self._spotlight_return_ms

        # Etapa 1: Pop para o centro com scale up e foco.
        for frame_idx in range(pop_frames):
            delay = int(self._spotlight_pop_ms * frame_idx / max(1, pop_frames - 1))

            def _pop_step(i=frame_idx):
                if not self.window.winfo_exists():
                    return
                t = i / max(1, pop_frames - 1)
                p = self._ease_out_cubic(t)
                cx = int(start_center_x + (center_x - start_center_x) * p)
                cy = int(start_center_y + (center_y - start_center_y) * p)
                scale = 0.9 + (self._spotlight_scale_center - 0.9) * p
                blur = 5.0 * (1.0 - p)
                glow = max(0.0, 1.0 - p * 0.7)
                frame_rgba = self._build_spotlight_rgba(tile, scale=scale, blur_radius=blur, glow_strength=glow)
                tk_img = ImageTk.PhotoImage(frame_rgba)
                self.canvas.itemconfigure(self._spotlight_item, image=tk_img, state="normal")
                self.canvas.coords(self._spotlight_item, cx, cy)
                self._tile_refs.append(tk_img)

            self.window.after(delay, _pop_step)

        # Etapa 2: Sustain com boiar / zoom quase imperceptível.
        for frame_idx in range(sustain_frames):
            delay = self._spotlight_pop_ms + int(self._spotlight_sustain_ms * frame_idx / max(1, sustain_frames - 1))

            def _sustain_step(i=frame_idx):
                if not self.window.winfo_exists():
                    return
                t = i / max(1, sustain_frames - 1)
                p = self._ease_in_out_cubic(t)
                float_y = int(center_y - 6 * p)
                scale = self._spotlight_scale_center * (1.0 + 0.05 * p)
                frame_rgba = self._build_spotlight_rgba(tile, scale=scale, blur_radius=0.0, glow_strength=0.25)
                tk_img = ImageTk.PhotoImage(frame_rgba)
                self.canvas.itemconfigure(self._spotlight_item, image=tk_img, state="normal")
                self.canvas.coords(self._spotlight_item, center_x, float_y)
                self._tile_refs.append(tk_img)

            self.window.after(delay, _sustain_step)

        # Etapa 3: Retorno para o slot com overshoot elástico.
        for frame_idx in range(return_frames):
            delay = self._spotlight_pop_ms + self._spotlight_sustain_ms + int(
                self._spotlight_return_ms * frame_idx / max(1, return_frames - 1)
            )

            def _return_step(i=frame_idx):
                if not self.window.winfo_exists():
                    return
                t = i / max(1, return_frames - 1)
                p = self._ease_out_back(t)
                cx = int(center_x + (start_center_x - center_x) * p)
                cy = int(center_y + (start_center_y - center_y) * p)
                scale = self._spotlight_scale_center + (1.0 - self._spotlight_scale_center) * p
                glow = max(0.0, 0.35 - (0.35 * t))
                frame_rgba = self._build_spotlight_rgba(tile, scale=scale, blur_radius=0.0, glow_strength=glow)
                tk_img = ImageTk.PhotoImage(frame_rgba)
                self.canvas.itemconfigure(self._spotlight_item, image=tk_img, state="normal")
                self.canvas.coords(self._spotlight_item, cx, cy)
                self._tile_refs.append(tk_img)

            self.window.after(delay, _return_step)

        def _finish():
            if not self.window.winfo_exists():
                return
            if self._spotlight_item is not None:
                self.canvas.itemconfigure(self._spotlight_item, state="hidden")
            self._set_focus_overlay(False)
            self._render_tile_static(index)
            if self._tile_items[index] is not None:
                self.canvas.itemconfigure(self._tile_items[index], state="normal")
            self._spotlight_running = False
            self._try_start_next_spotlight()

        self.window.after(total_ms + 20, _finish)

    def _try_start_next_spotlight(self):
        if self._spotlight_running:
            return
        while self._pending_spotlights:
            idx = self._pending_spotlights.pop(0)
            if 0 <= idx < self.max_cells and self._tile_images[idx] is not None:
                self._show_spotlight_sem_animacao(idx)
                return

    def _enqueue_spotlight(self, index: int, delay_ms: int = 0):
        token = self._queue_token

        def _push():
            if token != self._queue_token:
                return
            if not self.window.winfo_exists():
                return
            self._pending_spotlights.append(index)
            self._try_start_next_spotlight()

        if delay_ms > 0:
            self.window.after(delay_ms, _push)
        else:
            _push()

    def _show_spotlight_sem_animacao(self, index: int):
        """Mostra a imagem no centro por um curto tempo, sem animação contínua."""
        tile = self._tile_images[index]
        if tile is None or not self.window.winfo_exists():
            return

        center_x = self.width // 2
        center_y = self.height // 2

        self._spotlight_running = True
        self._set_focus_overlay(True)
        if self._tile_items[index] is not None:
            self.canvas.itemconfigure(self._tile_items[index], state="hidden")

        frame_rgba = self._build_spotlight_rgba(
            tile_base=tile,
            scale=self._spotlight_scale_center,
            blur_radius=0.0,
            glow_strength=0.18,
        )
        tk_img = ImageTk.PhotoImage(frame_rgba)

        if self._spotlight_item is None:
            self._spotlight_item = self.canvas.create_image(center_x, center_y, anchor="center", image=tk_img, tags=("spotlight",))
        else:
            self.canvas.itemconfigure(self._spotlight_item, image=tk_img, state="normal")
            self.canvas.coords(self._spotlight_item, center_x, center_y)
        self._tile_refs.append(tk_img)

        def _finish():
            if not self.window.winfo_exists():
                return
            if self._spotlight_item is not None:
                self.canvas.itemconfigure(self._spotlight_item, state="hidden")
            self._set_focus_overlay(False)
            self._render_tile_static(index)
            if self._tile_items[index] is not None:
                self.canvas.itemconfigure(self._tile_items[index], state="normal")
            self._spotlight_running = False
            self._try_start_next_spotlight()

        self.window.after(self._spotlight_hold_ms, _finish)

    def _show_center_preview_nonblocking(self, index: int):
        """
        Mostra prévia central sem bloquear novas entradas.
        A imagem já é encaixada no mosaico imediatamente.
        """
        tile = self._tile_images[index]
        if tile is None or not self.window.winfo_exists():
            return

        center_x = self.width // 2
        center_y = self.height // 2
        self._set_focus_overlay(True)

        frame_rgba = self._build_spotlight_rgba(
            tile_base=tile,
            scale=self._spotlight_scale_center,
            blur_radius=0.0,
            glow_strength=0.14,
        )
        tk_img = ImageTk.PhotoImage(frame_rgba)

        if self._spotlight_item is None:
            self._spotlight_item = self.canvas.create_image(center_x, center_y, anchor="center", image=tk_img, tags=("spotlight",))
        else:
            self.canvas.itemconfigure(self._spotlight_item, image=tk_img, state="normal")
            self.canvas.coords(self._spotlight_item, center_x, center_y)
        self._tile_refs.append(tk_img)

        if self._preview_hide_job is not None:
            try:
                self.window.after_cancel(self._preview_hide_job)
            except Exception:
                pass
            self._preview_hide_job = None

        def _hide_preview():
            if not self.window.winfo_exists():
                return
            if self._spotlight_item is not None:
                self.canvas.itemconfigure(self._spotlight_item, state="hidden")
            self._set_focus_overlay(False)
            self._preview_hide_job = None

        self._preview_hide_job = self.window.after(self._spotlight_hold_ms, _hide_preview)

    def add_image(self, image_path: str):
        if self.cursor >= self.max_cells:
            self.cursor = 0
            # Reinicia o painel mantendo o mesmo fundo
            self.canvas.delete("tiles")
            self._tile_refs.clear()
            self._tile_items = [None] * self.max_cells
            self._tile_images = [None] * self.max_cells

        caminho = Path(image_path)
        if not caminho.exists():
            return

        with Image.open(caminho) as img:
            img = ImageOps.fit(img.convert("RGB"), (self.cell_size, self.cell_size), Image.Resampling.LANCZOS)
            self._tile_images[self.cursor] = img.copy()

        # Exibe no mosaico imediatamente e mostra destaque central sem bloquear próximas imagens.
        self._render_tile_static(self.cursor)
        self._show_center_preview_nonblocking(self.cursor)
        self.cursor += 1

    def clear_tiles(self):
        """Limpa todas as fotos do mosaico e mantém o fundo."""
        if self._stagger_job is not None:
            try:
                self.window.after_cancel(self._stagger_job)
            except Exception:
                pass
            self._stagger_job = None
        self._queue_token += 1
        self._pending_spotlights.clear()
        self._spotlight_running = False
        if self._preview_hide_job is not None:
            try:
                self.window.after_cancel(self._preview_hide_job)
            except Exception:
                pass
            self._preview_hide_job = None
        self.canvas.delete("tiles")
        self._set_focus_overlay(False)
        self._tile_refs.clear()
        self._tile_items = [None] * self.max_cells
        self._tile_images = [None] * self.max_cells
        self.cursor = 0

    def play_staggered_flow(self):
        """Reconstrói o mosaico atual em cascata de baixo para cima."""
        if self._stagger_job is not None:
            try:
                self.window.after_cancel(self._stagger_job)
            except Exception:
                pass
            self._stagger_job = None

        indices = [idx for idx, tile in enumerate(self._tile_images) if tile is not None]
        if not indices:
            return

        # Sem animação: apenas redesenha em ordem natural do mosaico.
        indices.sort()
        self.canvas.delete("tiles")
        self._tile_refs.clear()
        self._tile_items = [None] * self.max_cells
        self._set_focus_overlay(False)
        self._queue_token += 1
        self._pending_spotlights.clear()

        for idx in indices:
            self._render_tile_static(idx)

