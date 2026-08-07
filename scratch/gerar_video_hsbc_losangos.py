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

def main():
    desktop = r"C:/Users/jrval/Desktop"
    img_path = r"C:\Users\jrval\.gemini\antigravity-ide\brain\db23e326-ec59-4067-801b-9e0f6c5f2338\media__1785978057370.png"
    out_video_path = os.path.join(desktop, "video_hsbc_losangos_perfeitos.mp4")

    if not os.path.exists(img_path):
        print("Erro: Imagem original do HSBC nao encontrada.")
        return

    # 1. Carrega a imagem original do HSBC
    bg_pil = Image.open(img_path).convert("RGB")
    width, height = bg_pil.size
    bg_bgr_base = np.array(bg_pil)[:, :, ::-1]

    # 2. Cria a mascara inteligente
    # Identifica pixels vermelhos, pretos e brancos
    r = bg_bgr_base[:,:,2]
    g = bg_bgr_base[:,:,1]
    b = bg_bgr_base[:,:,0]

    red_mask = (r > 120) & (g < 80) & (b < 80)
    white_mask = (r > 200) & (g > 200) & (b > 200)
    black_mask = (r < 50) & (g < 50) & (b < 50)

    # Dilata a mascara vermelha para capturar as linhas pretas finas da grade geometrica
    kernel = np.ones((5, 5), np.uint8)
    red_dilated = cv2.dilate(red_mask.astype(np.uint8), kernel, iterations=2)
    grid_lines_mask = (red_dilated == 1) & black_mask

    # O Overlay final tera Alpha = 255 apenas nas linhas da grade e nos textos.
    # Alpha = 0 nos losangos vermelhos e no fundo/centro preto.
    overlay_alpha = np.zeros((height, width), dtype=np.float32)
    overlay_alpha[grid_lines_mask] = 1.0
    overlay_alpha[white_mask] = 1.0

    # 3. Carrega EXATAMENTE 3 FOTOS distintas do Bucket
    galeria_dir = r"C:/Users/jrval/Desktop/Mosaico_Pixel/Galeria/sem_moldura"
    photo_files = sorted(glob.glob(os.path.join(galeria_dir, "*.jpg"))) + sorted(glob.glob(os.path.join(galeria_dir, "*.png")))
    
    valid_photos = []
    for p in photo_files:
        try:
            im = Image.open(p).convert("RGB")
            if im.size[0] > 60 and im.size[1] > 60:
                valid_photos.append(im)
            if len(valid_photos) == 3: # Garante exatamente 3
                break
        except Exception:
            continue
            
    if not valid_photos:
        valid_photos = [bg_pil]

    print(f"CONFIRMADO: Carregadas EXATAMENTE {len(valid_photos)} FOTOS distintas.")

    # 4. Configura grade para animacao das fotos
    tile_size = 24
    cols = width // tile_size
    rows = height // tile_size

    logo_cells = []
    for row in range(rows):
        for col in range(cols):
            x = col * tile_size
            y = row * tile_size
            # Se a celula tiver bastante vermelho original, eh parte do logo
            cell_red = red_mask[y:y+tile_size, x:x+tile_size]
            if np.sum(cell_red) > (tile_size * tile_size * 0.15):
                logo_cells.append((col, row))

    print(f"Celulas animadas do Logo: {len(logo_cells)}")

    # 5. Prepara a Camada Base (Fundo totalmente preenchido de fotos NORMAIS)
    base_layer = np.zeros((height, width, 3), dtype=np.uint8)
    for row in range(rows):
        for col in range(cols):
            x = col * tile_size
            y = row * tile_size
            idx = (row * cols + col) % len(valid_photos)
            img_resized = valid_photos[idx].resize((tile_size, tile_size), Image.Resampling.BILINEAR)
            base_layer[y:y+tile_size, x:x+tile_size] = np.array(img_resized)[:, :, ::-1]

    # 6. Renderizacao do Video
    fps = 30
    total_frames = fps * 15
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

    if not out.isOpened():
        print("Erro ao abrir VideoWriter.")
        return

    mosaic_red_accumulated = np.zeros((height, width, 3), dtype=np.uint8)
    # Mascara para saber onde ja aplicamos a foto vermelha definitiva
    red_accumulated_mask = np.zeros((height, width), dtype=np.float32)

    centerX, centerY = width // 2, height // 2

    print("Renderizando video HSBC com mascaramento preciso dos losangos...")

    for f_idx in range(total_frames):
        t = (f_idx / total_frames) * len(logo_cells)
        current_cell_idx = int(t) % len(logo_cells)
        progress_cell = t - int(t)
        ep = ease_out_cubic(progress_cell)

        c_target, r_target = logo_cells[current_cell_idx]
        tx, ty = c_target * tile_size, r_target * tile_size

        img_pil = valid_photos[current_cell_idx % len(valid_photos)]
        img_np_bgr = np.array(img_pil)[:, :, ::-1]

        # Preview grande no centro da tela em CORES NORMAIS
        preview_w = int(220 + (tile_size - 220) * ep)
        preview_h = int(220 + (tile_size - 220) * ep)
        px_now = int(centerX - 110 + (tx - (centerX - 110)) * ep)
        py_now = int(centerY - 110 + (ty - (centerY - 110)) * ep)

        photo_frame = cv2.resize(img_np_bgr, (max(2, preview_w), max(2, preview_h)))
        red_photo_frame = apply_red_tint(photo_frame)
        # Mistura para vermelho progressivamente
        blended_photo = cv2.addWeighted(photo_frame, 1.0 - ep, red_photo_frame, ep, 0)

        # Camada de animacao ativa
        active_layer = np.zeros((height, width, 3), dtype=np.float32)
        active_alpha = np.zeros((height, width), dtype=np.float32)

        y0, y1 = max(0, py_now), min(height, py_now + preview_h)
        x0, x1 = max(0, px_now), min(width, px_now + preview_w)
        h_d, w_d = y1 - y0, x1 - x0

        if h_d > 0 and w_d > 0:
            crop_photo = blended_photo[:h_d, :w_d]
            active_layer[y0:y1, x0:x1] = crop_photo
            active_alpha[y0:y1, x0:x1] = 1.0

        if progress_cell > 0.95:
            final_tile_red = apply_red_tint(cv2.resize(img_np_bgr, (tile_size, tile_size)))
            mosaic_red_accumulated[ty:ty+tile_size, tx:tx+tile_size] = final_tile_red
            red_accumulated_mask[ty:ty+tile_size, tx:tx+tile_size] = 1.0

        # COMPOSICAO DAS CAMADAS (De baixo para cima):
        # 1. Base: Fotos normais (preenche tudo, fundo, centro vazio)
        frame = base_layer.astype(np.float32)

        # 2. Fotos vermelhas acumuladas nos losangos
        mask_3ch = np.dstack([red_accumulated_mask]*3)
        frame = frame * (1.0 - mask_3ch) + mosaic_red_accumulated.astype(np.float32) * mask_3ch

        # 3. Foto voando ativamente
        mask_3ch = np.dstack([active_alpha]*3)
        frame = frame * (1.0 - mask_3ch) + active_layer * mask_3ch

        # 4. Overlay da arte geométrica original (Linhas pretas da grade e Textos brancos)
        mask_3ch = np.dstack([overlay_alpha]*3)
        frame = frame * (1.0 - mask_3ch) + bg_bgr_base.astype(np.float32) * mask_3ch

        out.write(frame.clip(0, 255).astype(np.uint8))

    out.release()
    print("Video HSBC com mascaramento perfeito gerado em:", out_video_path)

if __name__ == "__main__":
    main()
