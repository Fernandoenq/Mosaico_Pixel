import cv2
import numpy as np
from PIL import Image
import os
import random
from pathlib import Path

def ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def apply_red_tint(bgr_img):
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    red_tinted = np.zeros_like(bgr_img)
    red_tinted[:, :, 2] = cv2.addWeighted(gray, 0.9, np.full_like(gray, 255), 0.1, 0)
    red_tinted[:, :, 1] = (gray * 0.12).astype(np.uint8)
    red_tinted[:, :, 0] = (gray * 0.12).astype(np.uint8)
    return red_tinted

def generate_hsbc_video(main_img_path: Path, base_images_paths: list[Path], out_video_path: Path):
    bg_pil = Image.open(main_img_path).convert("RGB")
    width, height = bg_pil.size
    bg_bgr_base = np.array(bg_pil)[:, :, ::-1]

    # 1. Cria a mascara vermelha rigorosa (respeitando o desenho original sem expansão artificial)
    r_ch = bg_bgr_base[:,:,2]
    g_ch = bg_bgr_base[:,:,1]
    b_ch = bg_bgr_base[:,:,0]
    
    # Tolerância estrita para o vermelho do HSBC
    red_mask_bin = (r_ch > 80) & (g_ch < 60) & (b_ch < 60)

    tile_size = 22
    cols = width // tile_size
    rows = height // tile_size
    start_x = (width - (cols * tile_size)) // 2
    start_y = (height - (rows * tile_size)) // 2

    red_cells = set()
    for r in range(rows):
        for c in range(cols):
            x_start = start_x + c * tile_size
            y_start = start_y + r * tile_size
            y_end = min(height, y_start + tile_size)
            x_end = min(width, x_start + tile_size)
            
            # Requer um percentual de pixels vermelhos para ser considerada uma celula valida
            # Mantem o desenho exato da logo
            if np.sum(red_mask_bin[y_start:y_end, x_start:x_end]) > (tile_size * tile_size * 0.3):
                red_cells.add((c, r))

    if not red_cells:
        raise ValueError("Nenhuma celula vermelha (logo) encontrada na imagem base!")

    cells = list(red_cells)
    total_cells = len(cells)
    random.seed(42)
    random.shuffle(cells)

    base_layer = bg_bgr_base.copy()

    valid_photos = []
    for p in base_images_paths:
        try:
            valid_photos.append(Image.open(p).convert("RGB"))
        except: pass

    if not valid_photos:
        raise ValueError("Nenhuma foto base foi carregada da Galeria!")

    fps = 30
    delay_between_photos = 0.05
    hold_duration = 0.2
    fly_duration = 0.4
    total_secs = (total_cells * delay_between_photos) + hold_duration + fly_duration + 2.0
    total_frames = int(total_secs * fps)
    
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(out_video_path), fourcc, fps, (width, height))

    # Pre-calcular as imagens da galeria (red-tinted)
    precalculated_tiles = []
    for _ in range(total_cells):
        img_pil = random.choice(valid_photos)
        img_bgr = np.array(img_pil.resize((tile_size, tile_size)))[:, :, ::-1]
        precalculated_tiles.append(apply_red_tint(img_bgr))

    for f_idx in range(total_frames):
        t_global = f_idx / fps
        frame = base_layer.copy().astype(np.float32)
        
        current_tiles_layer = np.zeros((height, width, 3), dtype=np.float32)
        current_tiles_mask = np.zeros((height, width), dtype=np.float32)
        
        for idx, (c, r) in enumerate(cells):
            start_t = idx * delay_between_photos
            if t_global < start_t:
                continue
                
            progress = min(1.0, (t_global - start_t) / fly_duration)
            eased = ease_out_cubic(progress)
            
            x_dst = start_x + c * tile_size
            y_dst = start_y + r * tile_size
            
            x_src = width // 2 - tile_size // 2
            y_src = height // 2 - tile_size // 2
            
            x_curr = int(x_src + (x_dst - x_src) * eased)
            y_curr = int(y_src + (y_dst - y_src) * eased)
            
            # Desenha o tile no frame
            if 0 <= x_curr < width - tile_size and 0 <= y_curr < height - tile_size:
                tile = precalculated_tiles[idx]
                current_tiles_layer[y_curr:y_curr+tile_size, x_curr:x_curr+tile_size] = tile
                current_tiles_mask[y_curr:y_curr+tile_size, x_curr:x_curr+tile_size] = 1.0

        mask_3ch = np.expand_dims(current_tiles_mask, axis=2)
        frame = frame * (1 - mask_3ch) + current_tiles_layer * mask_3ch
        
        out.write(frame.astype(np.uint8))

    out.release()
