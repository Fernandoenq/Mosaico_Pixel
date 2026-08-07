import cv2
import numpy as np
from PIL import Image
import os

def ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def apply_red_tint(bgr_img):
    """Aplica filtro tom vermelho vibrante nos losangos do logo"""
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    red_tinted = np.zeros_like(bgr_img)
    red_tinted[:, :, 2] = cv2.addWeighted(gray, 0.9, np.full_like(gray, 255), 0.1, 0) # R
    red_tinted[:, :, 1] = (gray * 0.12).astype(np.uint8) # G
    red_tinted[:, :, 0] = (gray * 0.12).astype(np.uint8) # B
    return red_tinted

def main():
    desktop = r"C:/Users/jrval/Desktop"
    bg_path = os.path.join(desktop, "hsbc_fundo.jpg")
    out_video_path = os.path.join(desktop, "video_hsbc_mosaico_preenchido.mp4")

    if not os.path.exists(bg_path):
        print("Erro: hsbc_fundo.jpg nao encontrado.")
        return

    bg_pil = Image.open(bg_path).convert("RGB")
    width, height = bg_pil.size
    bg_bgr_base = np.array(bg_pil)[:, :, ::-1]

    # Garante 3 FOTOS distintas de alta qualidade da Galeria
    galeria_dir = r"C:/Users/jrval/Desktop/Mosaico_Pixel/Galeria/sem_moldura"
    p1 = os.path.join(galeria_dir, "img1.jpg")
    p2 = os.path.join(galeria_dir, "img10.jpg")
    p3 = os.path.join(galeria_dir, "img100.jpg")

    source_images = []
    for p in [p1, p2, p3]:
        if os.path.exists(p):
            source_images.append(Image.open(p).convert("RGB"))
        else:
            source_images.append(bg_pil)

    print(f"CONFIRMADO: Carregadas EXATAMENTE {len(source_images)} FOTOS distintas para a animacao!")

    tile_size = 24  # Grade fina para o logo HSBC
    cols = width // tile_size
    rows = height // tile_size

    # Detecta celulas vermelhas do logo HSBC e texto branco
    logo_cells = []
    logo_mask = np.zeros((height, width), dtype=np.float32)
    text_mask = np.zeros((height, width), dtype=np.float32)

    for r in range(rows):
        for c in range(cols):
            x_start = c * tile_size
            y_start = r * tile_size
            red_count = 0
            white_count = 0

            for dy in range(tile_size):
                for dx in range(tile_size):
                    px = x_start + dx
                    py = y_start + dy
                    if px < width and py < height:
                        b_val, g_val, r_val = bg_bgr_base[py, px]
                        if r_val > 120 and g_val < 70 and b_val < 70:
                            red_count += 1
                        elif r_val > 200 and g_val > 200 and b_val > 200:
                            white_count += 1

            if red_count > (tile_size * tile_size * 0.2):
                logo_cells.append((c, r))
                logo_mask[y_start:y_start+tile_size, x_start:x_start+tile_size] = 1.0
            if white_count > 5:
                text_mask[y_start:y_start+tile_size, x_start:x_start+tile_size] = 1.0

    print(f"Grade HSBC: {cols}x{rows} | Celulas do Logo Vermelho: {len(logo_cells)}")

    # Prepara a camada da area preta preenchida com as 3 FOTOS em CORES NORMAIS
    bg_photos_layer = np.zeros((height, width, 3), dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            x = c * tile_size
            y = r * tile_size
            idx = (r * cols + c) % len(source_images)
            img_resized = source_images[idx].resize((tile_size, tile_size), Image.Resampling.BILINEAR)
            bg_photos_layer[y:y+tile_size, x:x+tile_size] = np.array(img_resized)[:, :, ::-1]

    fps = 30
    total_frames = fps * 15
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

    if not out.isOpened():
        print("Erro ao abrir VideoWriter.")
        return

    mosaic_accumulated = bg_photos_layer.copy()
    centerX, centerY = width // 2, height // 2

    print("Renderizando video HSBC com as 3 FOTOS distintas...")

    for f_idx in range(total_frames):
        t = (f_idx / total_frames) * len(logo_cells)
        current_cell_idx = int(t) % len(logo_cells)
        progress_cell = t - int(t)
        ep = ease_out_cubic(progress_cell)

        c_target, r_target = logo_cells[current_cell_idx]
        tx, ty = c_target * tile_size, r_target * tile_size

        # Alterna entre as 3 fotos
        img_pil = source_images[current_cell_idx % len(source_images)]
        img_np_bgr = np.array(img_pil)[:, :, ::-1]

        # Preview grande no centro da tela em CORES NORMAIS
        preview_w = int(220 + (tile_size - 220) * ep)
        preview_h = int(220 + (tile_size - 220) * ep)
        px_now = int(centerX - 110 + (tx - (centerX - 110)) * ep)
        py_now = int(centerY - 110 + (ty - (centerY - 110)) * ep)

        photo_frame = cv2.resize(img_np_bgr, (max(2, preview_w), max(2, preview_h)))
        red_photo_frame = apply_red_tint(photo_frame)
        blended_photo = cv2.addWeighted(photo_frame, 1.0 - ep, red_photo_frame, ep, 0)

        current_frame_layer = mosaic_accumulated.copy()

        y0, y1 = max(0, py_now), min(height, py_now + preview_h)
        x0, x1 = max(0, px_now), min(width, px_now + preview_w)
        h_d, w_d = y1 - y0, x1 - x0

        if h_d > 0 and w_d > 0:
            crop_photo = blended_photo[:h_d, :w_d]
            current_frame_layer[y0:y1, x0:x1] = crop_photo

        if progress_cell > 0.95:
            final_tile_red = apply_red_tint(cv2.resize(img_np_bgr, (tile_size, tile_size)))
            mosaic_accumulated[ty:ty+tile_size, tx:tx+tile_size] = final_tile_red

        # Preserva o texto branco nitido por cima
        text_mask_3ch = np.dstack([text_mask] * 3)
        final_frame = current_frame_layer.astype(float) * (1.0 - text_mask_3ch) + bg_bgr_base.astype(float) * text_mask_3ch

        out.write(final_frame.clip(0, 255).astype(np.uint8))

    out.release()
    print("Video HSBC com as 3 fotos distintas gerado com sucesso em:", out_video_path)

if __name__ == "__main__":
    main()
