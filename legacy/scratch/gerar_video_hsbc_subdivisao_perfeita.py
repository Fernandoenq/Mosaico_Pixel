import cv2
import numpy as np
from PIL import Image
import os
import glob

def ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def get_block_key(c, r, level):
    if level == 0:
        c_g, r_g = 0, 0
    elif level == 1:
        c_g = 0 if c <= 13 else 1
        r_g = 0
    elif level == 2:
        c_g = 0 if c <= 13 else 1
        r_g = 0 if r <= 7 else 1
    elif level == 3:
        c_g = 0 if c <= 6 else (1 if c <= 13 else (2 if c <= 20 else 3))
        r_g = 0 if r <= 7 else 1
    elif level == 4:
        c_g = 0 if c <= 6 else (1 if c <= 13 else (2 if c <= 20 else 3))
        r_g = 0 if r <= 3 else (1 if r <= 7 else (2 if r <= 11 else 3))
    elif level == 5:
        c_g = 0 if c <= 2 else (1 if c <= 5 else (2 if c <= 9 else (3 if c <= 13 else (4 if c <= 17 else (5 if c <= 20 else (6 if c <= 23 else 7))))))
        r_g = 0 if r <= 3 else (1 if r <= 7 else (2 if r <= 11 else 3))
    elif level == 6:
        c_g = 0 if c <= 2 else (1 if c <= 5 else (2 if c <= 9 else (3 if c <= 13 else (4 if c <= 17 else (5 if c <= 20 else (6 if c <= 23 else 7))))))
        r_g = 0 if r <= 1 else (1 if r <= 3 else (2 if r <= 5 else (3 if r <= 7 else (4 if r <= 9 else (5 if r <= 11 else (6 if r <= 13 else 7))))))
    else:
        c_g, r_g = c, r
    return f"{c_g}_{r_g}"

def apply_red_tint(bgr_img):
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    red_tinted = np.zeros_like(bgr_img)
    red_tinted[:, :, 2] = cv2.addWeighted(gray, 0.9, np.full_like(gray, 255), 0.1, 0)
    red_tinted[:, :, 1] = (gray * 0.12).astype(np.uint8)
    red_tinted[:, :, 0] = (gray * 0.12).astype(np.uint8)
    return red_tinted

def main():
    desktop = r"C:/Users/jrval/Desktop"
    img_path = r"C:\Users\jrval\.gemini\antigravity-ide\brain\db23e326-ec59-4067-801b-9e0f6c5f2338\media__1785979137002.png"
    out_video_path = os.path.join(desktop, "video_hsbc_subdivisao_perfeita.mp4")

    # 1. Carrega a imagem original do HSBC
    bg_pil = Image.open(img_path).convert("RGB")
    width, height = bg_pil.size
    bg_bgr_base = np.array(bg_pil)[:, :, ::-1]

    # 2. Cria as mascaras precisas para o efeito de "passar por tras das formas"
    r = bg_bgr_base[:,:,2]
    g = bg_bgr_base[:,:,1]
    b = bg_bgr_base[:,:,0]

    red_mask_bin = (r > 120) & (g < 80) & (b < 80)
    red_mask = red_mask_bin.astype(np.uint8) * 255
    white_mask = ((r > 200) & (g > 200) & (b > 200)).astype(np.uint8) * 255
    black_mask = ((r < 50) & (g < 50) & (b < 50)).astype(np.uint8) * 255

    # Dilata o vermelho para pegar as linhas pretas finas (formas geometricas)
    kernel = np.ones((5, 5), np.uint8)
    red_dilated = cv2.dilate(red_mask, kernel, iterations=2)
    grid_lines_mask = cv2.bitwise_and(red_dilated, black_mask)

    # Mascara Topo: Apenas a grade fina e o texto. Isso ficara por cima do preview voador!
    top_overlay_mask = cv2.bitwise_or(grid_lines_mask, white_mask)
    top_overlay_alpha = (top_overlay_mask > 0).astype(np.float32)

    # Base Layer: A imagem inteira, com o VERMELHO zerado (pra virar buraco) e o PRETO/BRANCO intactos
    base_layer = bg_bgr_base.copy()
    base_layer[red_mask > 0] = [0, 0, 0]

    # 3. Carrega as fotos
    galeria_dir = r"C:/Users/jrval/Desktop/Mosaico_Pixel/Galeria/sem_moldura"
    photo_files = sorted(glob.glob(os.path.join(galeria_dir, "*.jpg"))) + sorted(glob.glob(os.path.join(galeria_dir, "*.png")))
    
    valid_photos = []
    # Adiciona a foto especifica do usuario primeiro
    user_photo_path = r"C:/Users/jrval/.gemini/antigravity-ide/brain/tempmediaStorage/media__1785979894285.png"
    if os.path.exists(user_photo_path):
        try:
            im = Image.open(user_photo_path).convert("RGB")
            valid_photos.append(im)
        except:
            pass

    for p in photo_files[:50]:
        try:
            im = Image.open(p).convert("RGB")
            if im.size[0] > 60 and im.size[1] > 60:
                valid_photos.append(im)
        except:
            pass
            
    if not valid_photos:
        valid_photos = [bg_pil]

    print(f"CONFIRMADO: Carregadas {len(valid_photos)} fotos.")

    # 4. Configura grade para animacao da subdivisao (Igual ao script do usuario)
    tile_size = 28 # Usando 28 para preencher perfeitamente os losangos
    cols = width // tile_size + 1
    rows = height // tile_size + 1
    start_x = 0
    start_y = 0

    cells = []
    for row in range(rows):
        for col in range(cols):
            x = start_x + col * tile_size
            y = start_y + row * tile_size
            # Verifica se tem vermelho dentro do quadrado
            cell_red = red_mask_bin[y:min(y+tile_size, height), x:min(x+tile_size, width)]
            if np.sum(cell_red) > 20: # Limiar baixo para garantir cobertura total
                cells.append((col, row))

    print(f"Subdivisao: {len(cells)} celulas ativas encontradas.")

    level_blocks = {}
    for lvl in range(8):
        level_blocks[lvl] = {}
        for c, r in cells:
            b_key = get_block_key(c, r, lvl)
            if b_key not in level_blocks[lvl]:
                level_blocks[lvl][b_key] = []
            level_blocks[lvl][b_key].append((c, r))
        
        for b_key, b_cells in level_blocks[lvl].items():
            c_min = min(cc for cc, rr in b_cells)
            c_max = max(cc for cc, rr in b_cells)
            r_min = min(rr for cc, rr in b_cells)
            r_max = max(rr for cc, rr in b_cells)
            
            bx = start_x + c_min * tile_size
            by = start_y + r_min * tile_size
            bw = (c_max - c_min + 1) * tile_size
            bh = (r_max - r_min + 1) * tile_size
            
            level_blocks[lvl][b_key] = {
                'cells': b_cells,
                'bbox': (bx, by, bw, bh)
            }

    block_photos = {}
    block_photos[0] = {"0_0": 0}
    for lvl in range(1, 8):
        block_photos[lvl] = {}
        parent_to_children = {}
        for b_key in level_blocks[lvl].keys():
            c_val, r_val = level_blocks[lvl][b_key]['cells'][0]
            p_key = get_block_key(c_val, r_val, lvl - 1)
            if p_key not in parent_to_children:
                parent_to_children[p_key] = []
            parent_to_children[p_key].append(b_key)
            
        next_photo_idx = max(block_photos[lvl - 1].values()) + 1
        for p_key, children in parent_to_children.items():
            children.sort()
            parent_photo = block_photos[lvl - 1][p_key]
            block_photos[lvl][children[0]] = parent_photo
            for child in children[1:]:
                block_photos[lvl][child] = next_photo_idx
                next_photo_idx += 1

    # 6. Renderizacao do Video
    step_duration = 3.0
    transition_duration = 1.6
    total_levels = 8
    total_secs = (total_levels - 1) * step_duration + 4.0
    fps = 30
    total_frames = int(total_secs * fps)
    
    centerX = width // 2
    centerY = height // 2

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

    for f_idx in range(total_frames):
        t = f_idx / fps
        level_idx = int(t // step_duration)
        level_idx = min(level_idx, total_levels - 1)
        t_in_step = t - level_idx * step_duration
        
        # Camada base de tiles (desenhada por tras do fundo preto)
        tiles_layer = np.zeros((height, width, 3), dtype=np.uint8)
        # Camada voadora de tiles (desenhada na frente do fundo preto, por tras das linhas da grade)
        flying_layer = np.zeros((height, width, 3), dtype=np.float32)
        flying_alpha = np.zeros((height, width), dtype=np.float32)
        
        if level_idx == 0:
            bbox = level_blocks[0]["0_0"]['bbox']
            bx, by, bw, bh = bbox
            photo_idx = block_photos[0]["0_0"]
            img_pil = valid_photos[photo_idx % len(valid_photos)]
            resized = np.array(img_pil.resize((bw, bh), Image.Resampling.BILINEAR))[:, :, ::-1].copy()
            red_tinted = apply_red_tint(resized)
            tiles_layer[by:by+bh, bx:bx+bw] = red_tinted
        elif t_in_step < transition_duration and level_idx < total_levels:
            p = t_in_step / transition_duration
            ep = ease_out_cubic(p)
            
            prev_level = level_idx - 1
            curr_level = level_idx
            
            for b_key, b_data in level_blocks[curr_level].items():
                c_val, r_val = b_data['cells'][0]
                p_key = get_block_key(c_val, r_val, prev_level)
                
                px, py, pw, ph = level_blocks[prev_level][p_key]['bbox']
                tx, ty, tw, th = b_data['bbox']
                
                photo_idx = block_photos[curr_level][b_key]
                img_pil = valid_photos[photo_idx % len(valid_photos)]
                
                parent_children = sorted(
                    [k for k, v in level_blocks[curr_level].items() 
                     if get_block_key(v['cells'][0][0], v['cells'][0][1], prev_level) == p_key]
                )
                
                if b_key == parent_children[0]:
                    cx_now = int(round(px + (tx - px) * ep))
                    cy_now = int(round(py + (ty - py) * ep))
                    cw_now = max(2, int(round(pw + (tw - pw) * ep)))
                    ch_now = max(2, int(round(ph + (th - ph) * ep)))
                    
                    img_bgr = np.array(img_pil)[:, :, ::-1].copy()
                    resized = cv2.resize(img_bgr, (cw_now, ch_now))
                    red_tinted = apply_red_tint(resized)
                    
                    y0, y1 = max(0, cy_now), min(height, cy_now + ch_now)
                    x0, x1 = max(0, cx_now), min(width, cx_now + cw_now)
                    h_d, w_d = y1 - y0, x1 - x0
                    if h_d > 0 and w_d > 0:
                        tiles_layer[y0:y1, x0:x1] = red_tinted[y0-cy_now:y0-cy_now+h_d, x0-cx_now:x0-cx_now+w_d]
                else:
                    cx_now = int(round(centerX - 125 + (tx - (centerX - 125)) * ep))
                    cy_now = int(round(centerY - 125 + (ty - (centerY - 125)) * ep))
                    cw_now = max(2, int(round(250 + (tw - 250) * ep)))
                    ch_now = max(2, int(round(250 + (th - 250) * ep)))
                    
                    img_bgr = np.array(img_pil)[:, :, ::-1].copy()
                    resized = cv2.resize(img_bgr, (cw_now, ch_now))
                    red_tinted = apply_red_tint(resized)
                    blended = cv2.addWeighted(resized, 1.0 - ep, red_tinted, ep, 0)
                    
                    alpha = ep
                    
                    y0, y1 = max(0, cy_now), min(height, cy_now + ch_now)
                    x0, x1 = max(0, cx_now), min(width, cx_now + cw_now)
                    h_d, w_d = y1 - y0, x1 - x0
                    if h_d > 0 and w_d > 0:
                        src_roi = blended[y0-cy_now:y0-cy_now+h_d, x0-cx_now:x0-cx_now+w_d]
                        flying_layer[y0:y1, x0:x1] = src_roi.astype(np.float32)
                        flying_alpha[y0:y1, x0:x1] = 1.0
        else:
            for b_key, b_data in level_blocks[level_idx].items():
                bx, by, bw, bh = b_data['bbox']
                photo_idx = block_photos[level_idx][b_key]
                img_pil = valid_photos[photo_idx % len(valid_photos)]
                resized = np.array(img_pil.resize((bw, bh), Image.Resampling.BILINEAR))[:, :, ::-1].copy()
                red_tinted = apply_red_tint(resized)
                tiles_layer[by:by+bh, bx:bx+bw] = red_tinted

        # ARQUITETURA PERFEITA DE COMPOSICAO:
        # 1. Base Layer: Imagem inteira com os losangos vermelhos ocos (fundo preto intacto)
        frame = base_layer.astype(np.float32)

        # Mascara invertida dos losangos: Onde ERA vermelho, vira 1, resto 0.
        red_holes_mask = (red_mask > 0).astype(np.float32)
        mask_3ch = np.dstack([red_holes_mask]*3)

        # 2. Tiles Layer (blocos estaticos/herdados): SÓ SAO VISTOS PELOS BURACOS VERMELHOS
        frame = frame * (1.0 - mask_3ch) + tiles_layer.astype(np.float32) * mask_3ch

        # 3. Flying Layer (novos blocos): DESENHADO POR CIMA DO FUNDO PRETO! Fica "na frente"!
        mask_3ch = np.dstack([flying_alpha]*3)
        frame = frame * (1.0 - mask_3ch) + flying_layer * mask_3ch

        # 4. Top Overlay (Grade Geometrica Preta e Texto): CORTA A FOTO VOADORA NO FINAL
        mask_3ch = np.dstack([top_overlay_alpha]*3)
        frame = frame * (1.0 - mask_3ch) + bg_bgr_base.astype(np.float32) * mask_3ch

        out.write(frame.clip(0, 255).astype(np.uint8))

    out.release()
    print("Video Subdivision Perfeito gerado em:", out_video_path)

if __name__ == "__main__":
    main()
