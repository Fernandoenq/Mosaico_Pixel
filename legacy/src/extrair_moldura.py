import cv2
import numpy as np
from PIL import Image
import os

def main():
    desktop = r"C:/Users/jrval/Desktop"
    bg_path = r"C:\Users\jrval\.gemini\antigravity-ide\brain\49b905dd-9df4-4a9b-ad13-f01313aca374\media__1786077135663.png"
    out_path = os.path.join(desktop, "moldura_transparente.png")

    print(f"Lendo imagem: {bg_path}")
    bg_pil = Image.open(bg_path).convert("RGBA")
    width, height = bg_pil.size
    bg_rgba = np.array(bg_pil)

    # Convert to BGR for color detection
    bg_bgr = bg_rgba[:, :, 0:3][:, :, ::-1]

    tile_size = 38
    cols = width // tile_size
    rows = height // tile_size
    start_x = (width - (cols * tile_size)) // 2
    start_y = (height - (rows * tile_size)) // 2

    # Encontra celulas vermelhas
    red_cells = set()
    for r in range(rows):
        for c in range(cols):
            x_start = start_x + c * tile_size
            y_start = start_y + r * tile_size
            red_count = 0
            for dy in range(tile_size):
                for dx in range(tile_size):
                    px, py = x_start + dx, y_start + dy
                    if px < width and py < height:
                        b_val, g_val, r_val = bg_bgr[py, px]
                        if r_val > 60 and g_val < 45 and b_val < 45:
                            red_count += 1
            if red_count > 30:
                red_cells.add((c, r))

    if not red_cells:
        print("Nenhuma celula vermelha encontrada! A moldura nao podera ser calculada com precisao.")
        return

    row_bounds = {}
    for c, r in red_cells:
        if r not in row_bounds:
            row_bounds[r] = [c, c]
        else:
            row_bounds[r][0] = min(row_bounds[r][0], c)
            row_bounds[r][1] = max(row_bounds[r][1], c)

    cells = []
    for r, bounds in row_bounds.items():
        min_c, max_c = bounds
        for c in range(min_c, max_c + 1):
            cells.append((c, r))

    # Mascara Vermelha para o clipping nas bordas
    r_ch = bg_bgr[:,:,2]
    g_ch = bg_bgr[:,:,1]
    b_ch = bg_bgr[:,:,0]
    red_mask_bin = (r_ch > 60) & (g_ch < 45) & (b_ch < 45)
    
    # Criar imagem final RGBA que comeca opaca com as cores originais
    final_rgba = np.zeros((height, width, 4), dtype=np.uint8)
    final_rgba[:, :, 0:3] = bg_rgba[:, :, 0:3]
    final_rgba[:, :, 3] = 255 # Totalmente opaco inicialmente

    # Para cada celula que faz parte do mosaico, a foto vai aparecer por baixo.
    # Portanto, a moldura (fundo por cima) deve ser TRANSPARENTE nas partes onde a foto aparece.
    for c, r in cells:
        x_target = start_x + c * tile_size
        y_target = start_y + r * tile_size
        
        y0, y1 = max(0, y_target), min(height, y_target+tile_size)
        x0, x1 = max(0, x_target), min(width, x_target+tile_size)
        
        if y1 > y0 and x1 > x0:
            is_red = (c, r) in red_cells
            if is_red:
                # Onde a logo original eh vermelha (red_mask_bin == True), a foto deve aparecer.
                # Portanto, a moldura deve ficar transparente.
                tile_mask = red_mask_bin[y0:y1, x0:x1]
                # Modifica o canal Alpha: se tile_mask for True (foto visivel), Alpha = 0 (transparente)
                # Senao mantem o que ja tem (255)
                alpha_roi = final_rgba[y0:y1, x0:x1, 3]
                alpha_roi[tile_mask] = 0
                final_rgba[y0:y1, x0:x1, 3] = alpha_roi
            else:
                # No meio, a foto fica inteira quadrada, entao a moldura deve sumir 100% nesse tile.
                final_rgba[y0:y1, x0:x1, 3] = 0

    # Redimensiona para Full HD (1920x1080) para compensar a compressao do chat
    final_rgba_resized = cv2.resize(final_rgba, (1920, 1080), interpolation=cv2.INTER_NEAREST)

    out_img = Image.fromarray(final_rgba_resized, "RGBA")
    out_img.save(out_path, "PNG")
    print(f"Moldura salva com sucesso em: {out_path} no tamanho 1920x1080")

if __name__ == "__main__":
    main()
