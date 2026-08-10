import cv2
import numpy as np
from PIL import Image
import os
import random

def ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def apply_red_tint(bgr_img):
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    red_tinted = np.zeros_like(bgr_img)
    red_tinted[:, :, 2] = cv2.addWeighted(gray, 0.9, np.full_like(gray, 255), 0.1, 0)
    red_tinted[:, :, 1] = (gray * 0.12).astype(np.uint8)
    red_tinted[:, :, 0] = (gray * 0.12).astype(np.uint8)
    return red_tinted

def main():
    desktop = r"C:/Users/jrval/Desktop"
    bg_path = r"C:\Users\jrval\.gemini\antigravity-ide\brain\db23e326-ec59-4067-801b-9e0f6c5f2338\media__1785984745282.jpg"
    out_video_path = os.path.join(desktop, "video_hsbc_sem_buracos.mp4")

    bg_pil = Image.open(bg_path).convert("RGB")
    width, height = bg_pil.size
    bg_bgr_base = np.array(bg_pil)[:, :, ::-1]

    # 1. Cria a mascara vermelha perfeita espelhando o lado direito para o esquerdo
    r_ch = bg_bgr_base[:,:,2]
    g_ch = bg_bgr_base[:,:,1]
    b_ch = bg_bgr_base[:,:,0]
    red_mask_bin = (r_ch > 60) & (g_ch < 45) & (b_ch < 45)
    h, w = red_mask_bin.shape
    red_mask_bin[:, :w//2] = np.fliplr(red_mask_bin[:, w//2:])
    red_mask_alpha = red_mask_bin.astype(np.float32)

    # IMAGENS MENORES para caber mais fotos (como pedido)
    tile_size = 22
    cols = width // tile_size
    rows = height // tile_size
    start_x = (width - (cols * tile_size)) // 2
    start_y = (height - (rows * tile_size)) // 2

    # 2. Encontra as celulas que possuem vermelho (logo) usando a mascara perfeita
    red_cells = set()
    for r in range(rows):
        for c in range(cols):
            x_start = start_x + c * tile_size
            y_start = start_y + r * tile_size
            y_end = min(height, y_start + tile_size)
            x_end = min(width, x_start + tile_size)
            
            if np.sum(red_mask_bin[y_start:y_end, x_start:x_end]) > 5:
                red_cells.add((c, r))

    if not red_cells:
        print("Nenhuma celula vermelha!")
        return

    # Para preencher TUDO sem buracos, pegamos o inicio e o fim de cada linha (row) que possui logo
    row_bounds = {}
    for c, r in red_cells:
        if r not in row_bounds:
            row_bounds[r] = [c, c]
        else:
            row_bounds[r][0] = min(row_bounds[r][0], c)
            row_bounds[r][1] = max(row_bounds[r][1], c)
            
    cells = []
    # Preenche de min_c ate max_c para CADA LINHA
    for r, bounds in row_bounds.items():
        min_c, max_c = bounds
        for c in range(min_c, max_c + 1):
            cells.append((c, r))

    total_cells = len(cells)
    print(f"Total de celulas (logo + meio): {total_cells}")

    random.seed(42)
    random.shuffle(cells)

    base_layer = bg_bgr_base.copy()

    # Carrega as 3 fotos da raiz do projeto
    project_dir = r"C:\Users\jrval\Desktop\Mosaico_Pixel"
    photo_names = ["foto pessoa randow 1.jpg", "randow 2.jpg", "randow 3.jpg"]
    valid_photos = []
    for name in photo_names:
        p = os.path.join(project_dir, name)
        if os.path.exists(p):
            try:
                valid_photos.append(Image.open(p).convert("RGB"))
            except: pass

    if not valid_photos:
        print("Nenhuma das 3 fotos foi encontrada na raiz!")
        return
    else:
        print(f"Fotos carregadas com sucesso: {len(valid_photos)}")

    fps = 30
    delay_between_photos = 0.05 # Rapido pois agora temos muitas celulas
    hold_duration = 0.2
    fly_duration = 0.4
    total_secs = (total_cells * delay_between_photos) + hold_duration + fly_duration + 2.0
    total_frames = int(total_secs * fps)
    
    centerX = width // 2
    centerY = height // 2

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

    print(f"Gerando {total_frames} frames...")

    for f_idx in range(total_frames):
        t = f_idx / fps
        frame = base_layer.copy().astype(np.float32)
        
        current_tiles_layer = np.zeros((height, width, 3), dtype=np.float32)
        current_tiles_mask = np.zeros((height, width), dtype=np.float32)
        
        flying_layer = np.zeros((height, width, 3), dtype=np.float32)
        flying_alpha = np.zeros((height, width), dtype=np.float32)

        for i, (c, r) in enumerate(cells):
            t_start = i * delay_between_photos
            t_fly_end = t_start + hold_duration + fly_duration
            if t < t_start:
                continue
                
            x_target = start_x + c * tile_size
            y_target = start_y + r * tile_size
            
            photo_idx = i % len(valid_photos)
            img_pil = valid_photos[photo_idx]
            
            if t >= t_fly_end:
                # COR ORIGINAL SEM FILTRO
                resized = np.array(img_pil.resize((tile_size, tile_size), Image.Resampling.BILINEAR))[:, :, ::-1]
                
                y0, y1 = max(0, y_target), min(height, y_target+tile_size)
                x0, x1 = max(0, x_target), min(width, x_target+tile_size)
                if y1 > y0 and x1 > x0:
                    tile_red_mask = red_mask_alpha[y0:y1, x0:x1]
                    mask_3ch = np.dstack([tile_red_mask]*3)
                    
                    red_tinted = apply_red_tint(resized)
                    # Mistura: onde a logo eh vermelha, fica vermelho. Onde for preto/meio, fica cor original!
                    final_tile = resized * (1.0 - mask_3ch) + red_tinted * mask_3ch
                    
                    current_tiles_layer[y0:y1, x0:x1] = final_tile[0:(y1-y0), 0:(x1-x0)]
                    current_tiles_mask[y0:y1, x0:x1] = 1.0 # Sem buracos! O tile inteiro eh desenhado!
            
            elif t >= t_start:
                dt = t - t_start
                if dt < hold_duration:
                    ep = 0.0
                else:
                    ep = ease_out_cubic((dt - hold_duration) / fly_duration)
                
                size_center = 260
                x_center = centerX - size_center // 2
                y_center = centerY - size_center // 2
                
                cx_now = int(round(x_center + (x_target - x_center) * ep))
                cy_now = int(round(y_center + (y_target - y_center) * ep))
                cw_now = max(2, int(round(size_center + (tile_size - size_center) * ep)))
                ch_now = max(2, int(round(size_center + (tile_size - size_center) * ep)))
                
                img_bgr = np.array(img_pil.resize((cw_now, ch_now), Image.Resampling.BILINEAR))[:, :, ::-1].copy()
                
                border_w = max(0, int(round(4 * (1 - ep))))
                if border_w > 0:
                    cv2.rectangle(img_bgr, (0, 0), (cw_now-1, ch_now-1), (255, 255, 255), border_w)
                
                # Voando fica 100% original
                blended = img_bgr 
                
                y0, y1 = max(0, cy_now), min(height, cy_now + ch_now)
                x0, x1 = max(0, cx_now), min(width, cx_now + cw_now)
                if y1 > y0 and x1 > x0:
                    src_roi = blended[y0-cy_now:y0-cy_now+(y1-y0), x0-cx_now:x0-cx_now+(x1-x0)]
                    flying_layer[y0:y1, x0:x1] = src_roi.astype(np.float32)
                    flying_alpha[y0:y1, x0:x1] = 1.0
        
        # 2. Fotos Pousadas
        mask_3ch = np.dstack([current_tiles_mask]*3)
        frame = frame * (1.0 - mask_3ch) + current_tiles_layer * mask_3ch
        
        # 3. As fotos Voando
        mask_3ch = np.dstack([flying_alpha]*3)
        frame = frame * (1.0 - mask_3ch) + flying_layer * mask_3ch

        out.write(frame.clip(0, 255).astype(np.uint8))

    out.release()
    print("Video salvo com sucesso em:", out_video_path)

if __name__ == "__main__":
    main()
