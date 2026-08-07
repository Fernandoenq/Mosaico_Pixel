import cv2
import numpy as np
from PIL import Image
import os
import glob

def ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def apply_red_tint(bgr_img):
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    red_tinted = np.zeros_like(bgr_img)
    red_tinted[:, :, 2] = cv2.addWeighted(gray, 0.9, np.full_like(gray, 255), 0.1, 0)
    red_tinted[:, :, 1] = (gray * 0.12).astype(np.uint8)
    red_tinted[:, :, 0] = (gray * 0.12).astype(np.uint8)
    return red_tinted

def union_bbox(diamonds):
    min_x = min(d['bbox'][0] for d in diamonds)
    min_y = min(d['bbox'][1] for d in diamonds)
    max_x = max(d['bbox'][0] + d['bbox'][2] for d in diamonds)
    max_y = max(d['bbox'][1] + d['bbox'][3] for d in diamonds)
    return (min_x, min_y, max_x - min_x, max_y - min_y)

def main():
    desktop = r"C:/Users/jrval/Desktop"
    img_path = r"C:\Users\jrval\.gemini\antigravity-ide\brain\db23e326-ec59-4067-801b-9e0f6c5f2338\media__1785979137002.png"
    out_video_path = os.path.join(desktop, "video_hsbc_diamantes_fractal.mp4")

    # 1. Carrega a imagem original do HSBC
    bg_pil = Image.open(img_path).convert("RGB")
    width, height = bg_pil.size
    bg_bgr_base = np.array(bg_pil)[:, :, ::-1]

    # 2. Mascaras para detectar os losangos perfeitos
    r = bg_bgr_base[:,:,2]
    g = bg_bgr_base[:,:,1]
    b = bg_bgr_base[:,:,0]

    red_mask_bin = (r > 120) & (g < 80) & (b < 80)
    red_mask = red_mask_bin.astype(np.uint8) * 255
    white_mask = ((r > 200) & (g > 200) & (b > 200)).astype(np.uint8) * 255
    black_mask = ((r < 50) & (g < 50) & (b < 50)).astype(np.uint8) * 255

    # Dilata o vermelho para pegar as linhas pretas finas
    kernel = np.ones((5, 5), np.uint8)
    red_dilated = cv2.dilate(red_mask, kernel, iterations=2)
    grid_lines_mask = cv2.bitwise_and(red_dilated, black_mask)

    top_overlay_mask = cv2.bitwise_or(grid_lines_mask, white_mask)
    top_overlay_alpha = (top_overlay_mask > 0).astype(np.float32)

    base_layer = bg_bgr_base.copy()
    base_layer[red_mask > 0] = [0, 0, 0]

    # 3. Encontra EXATAMENTE os losangos usando findContours
    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    diamonds = []
    for i, cnt in enumerate(contours):
        if cv2.contourArea(cnt) > 20: # Filtra ruidos
            x, y, w, h = cv2.boundingRect(cnt)
            cx = x + w // 2
            cy = y + h // 2
            diamonds.append({'id': i, 'bbox': (x, y, w, h), 'cx': cx, 'cy': cy})
            
    print(f"Encontrados {len(diamonds)} losangos reais na imagem!")

    # 4. Cria a Arvore Fractal Binaria (8 Niveis) baseada na geometria espacial!
    num_levels = 9 # Niveis 0 a 8
    level_blocks = {lvl: {} for lvl in range(num_levels)}
    
    level_blocks[0]['0'] = {
        'diamonds': diamonds,
        'bbox': union_bbox(diamonds)
    }
    
    for lvl in range(1, num_levels):
        for p_key, p_data in level_blocks[lvl-1].items():
            parent_diamonds = p_data['diamonds']
            if len(parent_diamonds) == 1:
                level_blocks[lvl][p_key + "_0"] = {
                    'diamonds': parent_diamonds,
                    'bbox': union_bbox(parent_diamonds)
                }
            else:
                if lvl % 2 == 1:
                    sorted_d = sorted(parent_diamonds, key=lambda d: d['cx'])
                else:
                    sorted_d = sorted(parent_diamonds, key=lambda d: d['cy'])
                    
                half = len(sorted_d) // 2
                child1 = sorted_d[:half]
                child2 = sorted_d[half:]
                
                if child1:
                    level_blocks[lvl][p_key + "_0"] = {
                        'diamonds': child1,
                        'bbox': union_bbox(child1)
                    }
                if child2:
                    level_blocks[lvl][p_key + "_1"] = {
                        'diamonds': child2,
                        'bbox': union_bbox(child2)
                    }

    # 5. Carrega as fotos
    galeria_dir = r"C:/Users/jrval/Desktop/Mosaico_Pixel/Galeria/sem_moldura"
    photo_files = sorted(glob.glob(os.path.join(galeria_dir, "*.jpg"))) + sorted(glob.glob(os.path.join(galeria_dir, "*.png")))
    
    valid_photos = []
    user_photo_path = r"C:/Users/jrval/.gemini/antigravity-ide/brain/tempmediaStorage/media__1785979894285.png"
    if os.path.exists(user_photo_path):
        try:
            valid_photos.append(Image.open(user_photo_path).convert("RGB"))
        except: pass

    for p in photo_files[:60]:
        try:
            valid_photos.append(Image.open(p).convert("RGB"))
        except: pass

    # 6. Atribui Fotos aos Blocos Fractais
    block_photos = {}
    block_photos[0] = {"0": 0}
    next_photo_idx = 1
    
    for lvl in range(1, num_levels):
        block_photos[lvl] = {}
        for p_key in level_blocks[lvl-1].keys():
            children_keys = sorted([k for k in level_blocks[lvl].keys() if k.startswith(p_key + "_")])
            if not children_keys: continue
            
            parent_photo = block_photos[lvl-1][p_key]
            block_photos[lvl][children_keys[0]] = parent_photo
            
            for child in children_keys[1:]:
                block_photos[lvl][child] = next_photo_idx
                next_photo_idx += 1

    # 7. Renderizacao
    step_duration = 3.0
    transition_duration = 1.6
    total_secs = (num_levels - 1) * step_duration + 4.0
    fps = 30
    total_frames = int(total_secs * fps)
    
    centerX = width // 2
    centerY = height // 2

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

    print(f"Gerando video fractal geometrico com {total_frames} frames...")

    for f_idx in range(total_frames):
        t = f_idx / fps
        level_idx = int(t // step_duration)
        level_idx = min(level_idx, num_levels - 1)
        t_in_step = t - level_idx * step_duration
        
        tiles_layer = np.zeros((height, width, 3), dtype=np.uint8)
        flying_layer = np.zeros((height, width, 3), dtype=np.float32)
        flying_alpha = np.zeros((height, width), dtype=np.float32)
        
        if level_idx == 0:
            bx, by, bw, bh = level_blocks[0]["0"]['bbox']
            photo_idx = block_photos[0]["0"]
            img_pil = valid_photos[photo_idx % len(valid_photos)]
            resized = np.array(img_pil.resize((bw, bh), Image.Resampling.BILINEAR))[:, :, ::-1].copy()
            tiles_layer[by:by+bh, bx:bx+bw] = apply_red_tint(resized)
            
        elif t_in_step < transition_duration and level_idx < num_levels:
            ep = ease_out_cubic(t_in_step / transition_duration)
            prev_level = level_idx - 1
            curr_level = level_idx
            
            for b_key, b_data in level_blocks[curr_level].items():
                p_key = "_".join(b_key.split("_")[:-1])
                px, py, pw, ph = level_blocks[prev_level][p_key]['bbox']
                tx, ty, tw, th = b_data['bbox']
                
                photo_idx = block_photos[curr_level][b_key]
                img_pil = valid_photos[photo_idx % len(valid_photos)]
                
                children_keys = sorted([k for k in level_blocks[curr_level].keys() if k.startswith(p_key + "_")])
                is_first_child = (b_key == children_keys[0])
                
                if is_first_child:
                    cx_now = int(round(px + (tx - px) * ep))
                    cy_now = int(round(py + (ty - py) * ep))
                    cw_now = max(2, int(round(pw + (tw - pw) * ep)))
                    ch_now = max(2, int(round(ph + (th - ph) * ep)))
                    
                    img_bgr = np.array(img_pil)[:, :, ::-1].copy()
                    resized = cv2.resize(img_bgr, (cw_now, ch_now))
                    red_tinted = apply_red_tint(resized)
                    
                    y0, y1 = max(0, cy_now), min(height, cy_now + ch_now)
                    x0, x1 = max(0, cx_now), min(width, cx_now + cw_now)
                    if y1 > y0 and x1 > x0:
                        tiles_layer[y0:y1, x0:x1] = red_tinted[y0-cy_now:y0-cy_now+(y1-y0), x0-cx_now:x0-cx_now+(x1-x0)]
                else:
                    cx_now = int(round(centerX - 125 + (tx - (centerX - 125)) * ep))
                    cy_now = int(round(centerY - 125 + (ty - (centerY - 125)) * ep))
                    cw_now = max(2, int(round(250 + (tw - 250) * ep)))
                    ch_now = max(2, int(round(250 + (th - 250) * ep)))
                    
                    img_bgr = np.array(img_pil)[:, :, ::-1].copy()
                    resized = cv2.resize(img_bgr, (cw_now, ch_now))
                    red_tinted = apply_red_tint(resized)
                    blended = cv2.addWeighted(resized, 1.0 - ep, red_tinted, ep, 0)
                    
                    y0, y1 = max(0, cy_now), min(height, cy_now + ch_now)
                    x0, x1 = max(0, cx_now), min(width, cx_now + cw_now)
                    if y1 > y0 and x1 > x0:
                        src_roi = blended[y0-cy_now:y0-cy_now+(y1-y0), x0-cx_now:x0-cx_now+(x1-x0)]
                        flying_layer[y0:y1, x0:x1] = src_roi.astype(np.float32)
                        flying_alpha[y0:y1, x0:x1] = 1.0
        else:
            for b_key, b_data in level_blocks[level_idx].items():
                bx, by, bw, bh = b_data['bbox']
                photo_idx = block_photos[level_idx][b_key]
                img_pil = valid_photos[photo_idx % len(valid_photos)]
                resized = np.array(img_pil.resize((bw, bh), Image.Resampling.BILINEAR))[:, :, ::-1].copy()
                tiles_layer[by:by+bh, bx:bx+bw] = apply_red_tint(resized)

        frame = base_layer.astype(np.float32)
        red_holes_mask = (red_mask > 0).astype(np.float32)
        mask_3ch = np.dstack([red_holes_mask]*3)
        frame = frame * (1.0 - mask_3ch) + tiles_layer.astype(np.float32) * mask_3ch

        mask_3ch = np.dstack([flying_alpha]*3)
        frame = frame * (1.0 - mask_3ch) + flying_layer * mask_3ch

        mask_3ch = np.dstack([top_overlay_alpha]*3)
        frame = frame * (1.0 - mask_3ch) + bg_bgr_base.astype(np.float32) * mask_3ch

        out.write(frame.clip(0, 255).astype(np.uint8))

    out.release()
    print("Video Final Perfeito salvo em:", out_video_path)

if __name__ == "__main__":
    main()
