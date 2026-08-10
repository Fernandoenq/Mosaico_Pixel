import cv2
import numpy as np
from PIL import Image
import os
import glob

def ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def apply_red_tint(bgr_img):
    """Aplica filtro tom vermelho elegante (estilo Mosaico Pixel)"""
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    red_tinted = np.zeros_like(bgr_img)
    red_tinted[:, :, 2] = cv2.addWeighted(gray, 0.88, np.full_like(gray, 255), 0.12, 0) # R
    red_tinted[:, :, 1] = (gray * 0.18).astype(np.uint8) # G
    red_tinted[:, :, 0] = (gray * 0.18).astype(np.uint8) # B
    return red_tinted

def main():
    desktop = r"C:/Users/jrval/Desktop"
    bg_path = os.path.join(desktop, "fundo_teste.jpg")
    out_video_path = os.path.join(desktop, "video_mosaico_galeria_bucket.mp4")

    if not os.path.exists(bg_path):
        bg_path = r"C:/Users/jrval/Desktop/Mosaico_Pixel/assets/backgrounds/fundo.jpg"

    # Carrega as imagens reais da Galeria sem_moldura
    galeria_dir = r"C:/Users/jrval/Desktop/Mosaico_Pixel/Galeria/sem_moldura"
    photo_files = sorted(glob.glob(os.path.join(galeria_dir, "*.jpg")))

    # Seleciona uma lista de fotos de boa qualidade (ex: 25 fotos reais do bucket)
    valid_photos = []
    for p in photo_files[:30]:
        try:
            im = Image.open(p).convert("RGB")
            # Garante que a foto tem resolução válida
            if im.size[0] > 100 and im.size[1] > 100:
                valid_photos.append(im)
        except Exception:
            continue

    if not valid_photos:
        print("Erro: Nenhuma foto encontrada na galeria.")
        return

    print(f"Total de {len(valid_photos)} fotos reais da Galeria carregadas com sucesso.")

    bg_pil = Image.open(bg_path).convert("RGB")
    width, height = bg_pil.size
    bg_bgr_base = np.array(bg_pil)[:, :, ::-1]

    tile_size = 38
    cols = width // tile_size
    rows = height // tile_size

    # Identifica a máscara transparente dos losangos do logo
    logo_mask = np.zeros((height, width), dtype=np.float32)
    cells = []

    for r in range(rows):
        for c in range(cols):
            red_count = 0
            x_start = c * tile_size
            y_start = r * tile_size
            for dy in range(tile_size):
                for dx in range(tile_size):
                    px = x_start + dx
                    py = y_start + dy
                    if px < width and py < height:
                        b_val, g_val, r_val = bg_bgr_base[py, px]
                        if r_val > 60 and g_val < 45 and b_val < 45:
                            red_count += 1
            if red_count > 30:
                cells.append((c, r))
                logo_mask[y_start:y_start+tile_size, x_start:x_start+tile_size] = 1.0

    print(f"Células dos losangos transparentes: {len(cells)}")

    fps = 30
    total_frames = fps * 15 # 15 segundos de animação
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

    if not out.isOpened():
        print("Erro ao abrir VideoWriter.")
        return

    mosaic_accumulated = np.zeros((height, width, 3), dtype=np.uint8)
    centerX, centerY = width // 2, height // 2

    print("Renderizando animação com fotos reais do Bucket (Preview Grande -> Filtro Vermelho atrás dos Losangos)...")

    for f_idx in range(total_frames):
        t = (f_idx / total_frames) * len(cells)
        current_cell_idx = int(t) % len(cells)
        progress_cell = t - int(t)
        ep = ease_out_cubic(progress_cell)

        c_target, r_target = cells[current_cell_idx]
        tx, ty = c_target * tile_size, r_target * tile_size

        # Foto real do participante
        img_pil = valid_photos[current_cell_idx % len(valid_photos)]
        img_np_bgr = np.array(img_pil)[:, :, ::-1]

        # 1. Preview Grande no centro da tela (Cores Normais)
        preview_w = int(240 + (tile_size - 240) * ep)
        preview_h = int(240 + (tile_size - 240) * ep)
        px_now = int(centerX - 120 + (tx - (centerX - 120)) * ep)
        py_now = int(centerY - 120 + (ty - (centerY - 120)) * ep)

        photo_frame = cv2.resize(img_np_bgr, (max(2, preview_w), max(2, preview_h)))
        red_photo_frame = apply_red_tint(photo_frame)
        blended_photo = cv2.addWeighted(photo_frame, 1.0 - ep, red_photo_frame, ep, 0)

        canvas_behind_mask = mosaic_accumulated.copy()

        y0, y1 = max(0, py_now), min(height, py_now + preview_h)
        x0, x1 = max(0, px_now), min(width, px_now + preview_w)
        h_d, w_d = y1 - y0, x1 - x0

        if h_d > 0 and w_d > 0:
            crop_photo = blended_photo[:h_d, :w_d]
            canvas_behind_mask[y0:y1, x0:x1] = crop_photo

        if progress_cell > 0.95:
            final_tile_red = apply_red_tint(cv2.resize(img_np_bgr, (tile_size, tile_size)))
            mosaic_accumulated[ty:ty+tile_size, tx:tx+tile_size] = final_tile_red

        # Composição: Fotos por trás dos losangos transparentes, arte de fundo ao redor
        logo_mask_3ch = np.dstack([logo_mask] * 3)
        final_frame = bg_bgr_base.astype(float) * (1.0 - logo_mask_3ch) + canvas_behind_mask.astype(float) * logo_mask_3ch

        out.write(final_frame.clip(0, 255).astype(np.uint8))

    out.release()
    print("Video gerado com sucesso em:", out_video_path)

if __name__ == "__main__":
    main()
