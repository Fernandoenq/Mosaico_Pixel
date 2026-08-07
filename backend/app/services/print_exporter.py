import cv2
import numpy as np
from pathlib import Path
import time

def export_mosaic_to_print_spooler(
    placed_tiles: dict[tuple[int, int], str],
    approved_photos_map: dict[str, str], # photo_id -> local_path
    output_dir: Path,
    rows: int = 30,
    cols: int = 40,
    print_dpi: int = 300,
    print_size_cm: tuple[float, float] = (15.0, 10.0) # (largura, altura) em cm
) -> str:
    """
    Renderiza o mosaico completo em alta resolução (300 DPI) para impressoras térmicas
    e salva silenciosamente na pasta monitorada pelo bot de impressão.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1 cm = 0.393701 polegadas
    width_px = int((print_size_cm[0] / 2.54) * print_dpi)
    height_px = int((print_size_cm[1] / 2.54) * print_dpi)
    
    high_res_canvas = np.zeros((height_px, width_px, 3), dtype=np.uint8)
    high_res_canvas[:, :] = (240, 240, 240)
    
    tile_h = height_px // rows
    tile_w = width_px // cols
    
    for (r, c), photo_id in placed_tiles.items():
        local_path = approved_photos_map.get(photo_id)
        if not local_path or not Path(local_path).exists():
            continue
            
        img = cv2.imread(local_path)
        if img is None:
            continue
            
        resized = cv2.resize(img, (tile_w, tile_h), interpolation=cv2.INTER_LANCZOS4)
        
        y0, y1 = r * tile_h, (r + 1) * tile_h
        x0, x1 = c * tile_w, (c + 1) * tile_w
        
        high_res_canvas[y0:y1, x0:x1] = resized
        
    output_path = output_dir / f"mosaic_print_{int(time.time())}.jpg"
    cv2.imwrite(str(output_path), high_res_canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 98])
    
    print(f"[PrintExporter] Composição 300 DPI gerada com sucesso em: {output_path}")
    return str(output_path)
