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
    img_path = r"C:\Users\jrval\.gemini\antigravity-ide\brain\db23e326-ec59-4067-801b-9e0f6c5f2338\media__1785979137002.png"
    out_video_path = os.path.join(desktop, "video_hsbc_fotos_grandes.mp4")

    # A foto enviada pelo usuario agora:
    user_photo_path = r"C:/Users/jrval/.gemini/antigravity-ide/brain/tempmediaStorage/media__1785979894285.png"

    if not os.path.exists(img_path):
        print("Erro: Imagem original nao encontrada.")
        return

    # 1. Carrega a imagem original do HSBC
    bg_pil = Image.open(img_path).convert("RGB")
    width, height = bg_pil.size
    bg_bgr_base = np.array(bg_pil)[:, :, ::-1]

    # 2. Cria as mascaras precisas
    r = bg_bgr_base[:,:,2]
    g = bg_bgr_base[:,:,1]
    b = bg_bgr_base[:,:,0]

    red_mask = ((r > 120) & (g < 80) & (b < 80)).astype(np.uint8) * 255
    white_mask = ((r > 200) & (g > 200) & (b > 200)).astype(np.uint8) * 255
    black_mask = ((r < 50) & (g < 50) & (b < 50)).astype(np.uint8) * 255

    # Identifica as linhas pretas (geometria) dilando o vermelho
    kernel = np.ones((5, 5), np.uint8)
    red_dilated = cv2.dilate(red_mask, kernel, iterations=2)
    grid_lines_mask = cv2.bitwise_and(red_dilated, black_mask)

    top_overlay_mask = cv2.bitwise_or(grid_lines_mask, white_mask)
    top_overlay_alpha = (top_overlay_mask > 0).astype(np.float32)

    base_layer = bg_bgr_base.copy()
    base_layer[red_mask > 0] = [0, 0, 0]

    # 3. Carrega as fotos (vamos usar a foto nova e as da galeria)
    valid_photos = []
    if os.path.exists(user_photo_path):
        try:
            im = Image.open(user_photo_path).convert("RGB")
            valid_photos.append(im)
            valid_photos.append(im) # Adiciona duas vezes pra ter mais frequencia
        except Exception:
            pass

    galeria_dir = r"C:/Users/jrval/Desktop/Mosaico_Pixel/Galeria/sem_moldura"
    photo_files = sorted(glob.glob(os.path.join(galeria_dir, "*.jpg"))) + sorted(glob.glob(os.path.join(galeria_dir, "*.png")))
    for p in photo_files[:50]: # limitando um pouco senao pesa
        try:
            im = Image.open(p).convert("RGB")
            if im.size[0] > 60 and im.size[1] > 60:
                valid_photos.append(im)
        except Exception:
            continue
            
    if not valid_photos:
        valid_photos = [bg_pil]

    print(f"CONFIRMADO: Carregadas {len(valid_photos)} FOTOS distintas da Galeria.")

    # 4. Encontra EXATAMENTE cada losango para preencher o maximo de area
    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    logo_cells = [] # Vai guardar (x, y, w, h) de cada losango
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 50: # Ignora ruidos pequenos
            x, y, w, h = cv2.boundingRect(cnt)
            logo_cells.append((x, y, w, h))

    # Ordena as celulas (ex: da esquerda pra direita)
    logo_cells = sorted(logo_cells, key=lambda c: (c[0] // 50, c[1]))
    print(f"Encontrados {len(logo_cells)} losangos perfeitos!")

    # 6. Renderizacao do Video
    fps = 30
    total_frames = fps * 15
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

    mosaic_red_accumulated = np.zeros((height, width, 3), dtype=np.uint8)
    red_accumulated_mask = np.zeros((height, width), dtype=np.float32)

    centerX, centerY = width // 2, height // 2

    for f_idx in range(total_frames):
        t = (f_idx / total_frames) * len(logo_cells)
        current_cell_idx = int(t) % len(logo_cells)
        progress_cell = t - int(t)
        ep = ease_out_cubic(progress_cell)

        x_t, y_t, w_t, h_t = logo_cells[current_cell_idx]
        # Centro do losango alvo
        tx = x_t + w_t // 2
        ty = y_t + h_t // 2
        # Tamanho da foto a ser desenhada: suficiente para cobrir todo o losango
        cell_size = max(w_t, h_t)

        img_pil = valid_photos[current_cell_idx % len(valid_photos)]
        img_np_bgr = np.array(img_pil)[:, :, ::-1]

        # Preview grande no centro
        preview_w = int(220 + (cell_size - 220) * ep)
        preview_h = int(220 + (cell_size - 220) * ep)
        px_now = int(centerX - 110 + (tx - cell_size//2 - (centerX - 110)) * ep)
        py_now = int(centerY - 110 + (ty - cell_size//2 - (centerY - 110)) * ep)

        photo_frame = cv2.resize(img_np_bgr, (max(2, preview_w), max(2, preview_h)))
        red_photo_frame = apply_red_tint(photo_frame)
        blended_photo = cv2.addWeighted(photo_frame, 1.0 - ep, red_photo_frame, ep, 0)

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
            final_tile_red = apply_red_tint(cv2.resize(img_np_bgr, (w_t, h_t)))
            # Desenha no tamanho exato do bounding box
            mosaic_red_accumulated[y_t:y_t+h_t, x_t:x_t+w_t] = final_tile_red
            red_accumulated_mask[y_t:y_t+h_t, x_t:x_t+w_t] = 1.0

        frame = base_layer.astype(np.float32)

        mask_3ch = np.dstack([red_accumulated_mask]*3)
        frame = frame * (1.0 - mask_3ch) + mosaic_red_accumulated.astype(np.float32) * mask_3ch

        # FOTO VOANDO (na frente de tudo)
        mask_3ch = np.dstack([active_alpha]*3)
        frame = frame * (1.0 - mask_3ch) + active_layer * mask_3ch

        # TOP OVERLAY MASK (linhas pretas por cima fatiando os losangos)
        mask_3ch = np.dstack([top_overlay_alpha]*3)
        frame = frame * (1.0 - mask_3ch) + bg_bgr_base.astype(np.float32) * mask_3ch

        out.write(frame.clip(0, 255).astype(np.uint8))

    out.release()
    print("Video HSBC Area Maxima gerado com sucesso em:", out_video_path)

if __name__ == "__main__":
    main()
