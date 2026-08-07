import cv2
import numpy as np
from PIL import Image
import os

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

def main():
    desktop = r"C:/Users/jrval/Desktop"
    bg_path = os.path.join(desktop, "fundo_teste.jpg")
    img1_path = os.path.join(desktop, "foto1.jpg")
    img2_path = os.path.join(desktop, "foto2.png")
    img3_path = os.path.join(desktop, "foto3.png")
    out_video_path = os.path.join(desktop, "mosaico_logo_com_fundo_fotos.mp4")

    # Garante que a imagem de fundo existe ou usa um fallback da pasta assets
    if not os.path.exists(bg_path):
        bg_path = r"C:/Users/jrval/Desktop/Mosaico_Pixel/assets/backgrounds/fundo.jpg"
    if not os.path.exists(img1_path):
        img1_path = bg_path

    bg_pil = Image.open(bg_path).convert("RGB")
    width, height = bg_pil.size
    bg_bgr_base = np.array(bg_pil)[:, :, ::-1]

    tile_size = 38
    cols = width // tile_size
    rows = height // tile_size
    start_x = 0
    start_y = 0

    # Carrega as imagens de origem
    images_pil = []
    for p in [img1_path, img2_path, img3_path]:
        if os.path.exists(p):
            images_pil.append(Image.open(p).convert("RGB"))
    if not images_pil:
        images_pil = [bg_pil]

    # Prepara a camada de fundo preenchida com fotos em cores normais
    bg_photos_layer = np.zeros((height, width, 3), dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            x = c * tile_size
            y = r * tile_size
            idx = (r * cols + c) % len(images_pil)
            img_resized = images_pil[idx].resize((tile_size, tile_size), Image.Resampling.BILINEAR)
            bg_photos_layer[y:y+tile_size, x:x+tile_size] = np.array(img_resized)[:, :, ::-1]

    # Detecta as células que formam o logo (vermelho)
    logo_cells = []
    logo_mask = np.zeros((height, width, 1), dtype=np.float32)

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
                logo_cells.append((c, r))
                logo_mask[y_start:y_start+tile_size, x_start:x_start+tile_size, 0] = 1.0

    print(f"Células do Logo identificadas: {len(logo_cells)} de {cols*rows}")

    # Configuração de vídeo
    fps = 30
    duration_sec = 10
    total_frames = fps * duration_sec

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

    if not out.isOpened():
        print("Erro ao abrir VideoWriter.")
        return

    print("Gerando vídeo com fundo preenchido de fotos nas cores normais...")

    for f_idx in range(total_frames):
        t = f_idx / total_frames  # 0.0 a 1.0
        p = ease_out_cubic(t)

        # Começa com o fundo preenchido de fotos normais
        frame = bg_photos_layer.copy().astype(float)

        # Sobrepõe o mosaico animado do logo (com filtro avermelhado suave / fusão do logo)
        logo_overlay = bg_bgr_base.astype(float) * 0.65 + bg_photos_layer.astype(float) * 0.35
        
        # Aplica a animação de revelação gradual
        alpha_mask = logo_mask * p
        frame = frame * (1.0 - alpha_mask) + logo_overlay * alpha_mask

        out.write(frame.clip(0, 255).astype(np.uint8))

    out.release()
    print("Video gerado com sucesso em:", out_video_path)

if __name__ == "__main__":
    main()
