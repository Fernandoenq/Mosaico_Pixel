import cv2
import numpy as np
from PIL import Image
import os
import uuid
import math
import asyncio
from typing import Dict, Any

from app.core.config import settings

# Track ongoing exports
exports: Dict[str, Dict[str, Any]] = {}

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

def run_export_video_task(export_id: str, mosaic_state_payload: list[dict], bg_bgr_base: np.ndarray, config: dict):
    try:
        exports[export_id]["status"] = "running"
        exports[export_id]["progress"] = 0
        
        rows = int(config.get("rows", 30))
        cols = int(config.get("cols", 40))
        width = int(config.get("screenWidth", 1920))
        height = int(config.get("screenHeight", 1080))
        
        tile_w = width // cols
        tile_h = height // rows
        start_x = 0
        start_y = 0
        
        export_dir = settings.STORAGE_DIR / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        out_video_path = str(export_dir / f"export_{export_id}.mp4")
        exports[export_id]["local_path"] = out_video_path
        
        custom_mask = config.get("customMaskCells", [])
        shape = config.get("gridContainerShape", "rectangle")
        cells = []
        for r in range(rows):
            for c in range(cols):
                if shape == "custom_mask" and custom_mask:
                    if f"{r}_{c}" in custom_mask:
                        cells.append((c, r))
                else:
                    cells.append((c, r))
                    
        placed_cell_set = {(p["col"], p["row"]): p["url"] for p in mosaic_state_payload}
        active_cells = [c for c in cells if c in placed_cell_set]
        
        if not active_cells:
            exports[export_id]["status"] = "error"
            exports[export_id]["error"] = "Nenhuma foto posicionada na máscara."
            return
            
        source_images_cache = {}
        for (c, r) in active_cells:
            url = placed_cell_set[(c, r)]
            local_path = url.lstrip("/") 
            if os.path.exists(local_path):
                img_pil = Image.open(local_path).convert("RGB")
                source_images_cache[(c, r)] = img_pil
            else:
                img_pil = Image.new("RGB", (tile_w, tile_h), color=(100, 100, 100))
                source_images_cache[(c, r)] = img_pil
                
        level_blocks = {}
        for lvl in range(8):
            level_blocks[lvl] = {}
            for c, r in active_cells:
                b_key = get_block_key(c, r, lvl)
                if b_key not in level_blocks[lvl]:
                    level_blocks[lvl][b_key] = []
                level_blocks[lvl][b_key].append((c, r))
                
            for b_key, b_cells in level_blocks[lvl].items():
                c_min = min(cc for cc, rr in b_cells)
                c_max = max(cc for cc, rr in b_cells)
                r_min = min(rr for cc, rr in b_cells)
                r_max = max(rr for cc, rr in b_cells)
                
                bx = start_x + c_min * tile_w
                by = start_y + r_min * tile_h
                bw = (c_max - c_min + 1) * tile_w
                bh = (r_max - r_min + 1) * tile_h
                
                level_blocks[lvl][b_key] = {
                    'cells': b_cells,
                    'bbox': (bx, by, bw, bh)
                }
                
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
            level_idx = min(int(t // step_duration), total_levels - 1)
            t_in_step = t - level_idx * step_duration
            
            tiles_layer = np.zeros((height, width, 3), dtype=np.uint8)
            
            if level_idx == 0:
                if "0_0" in level_blocks[0]:
                    bbox = level_blocks[0]["0_0"]['bbox']
                    bx, by, bw, bh = bbox
                    c_val, r_val = level_blocks[0]["0_0"]['cells'][0]
                    img_pil = source_images_cache[(c_val, r_val)]
                    resized = np.array(img_pil.resize((bw, bh), Image.Resampling.BILINEAR))[:, :, ::-1].copy()
                    tiles_layer[by:by+bh, bx:bx+bw] = resized
            elif t_in_step < transition_duration and level_idx < total_levels:
                p = t_in_step / transition_duration
                ep = ease_out_cubic(p)
                prev_level = level_idx - 1
                curr_level = level_idx
                
                for b_key, b_data in level_blocks[curr_level].items():
                    c_val, r_val = b_data['cells'][0]
                    p_key = get_block_key(c_val, r_val, prev_level)
                    if p_key not in level_blocks[prev_level]:
                        continue
                    px, py, pw, ph = level_blocks[prev_level][p_key]['bbox']
                    tx, ty, tw, th = b_data['bbox']
                    
                    img_pil = source_images_cache[(c_val, r_val)]
                    
                    parent_children = sorted(
                        [k for k, v in level_blocks[curr_level].items() 
                         if get_block_key(v['cells'][0][0], v['cells'][0][1], prev_level) == p_key]
                    )
                    
                    if parent_children and b_key == parent_children[0]:
                        cx_now = int(round(px + (tx - px) * ep))
                        cy_now = int(round(py + (ty - py) * ep))
                        cw_now = max(2, int(round(pw + (tw - pw) * ep)))
                        ch_now = max(2, int(round(ph + (th - ph) * ep)))
                        
                        resized = np.array(img_pil.resize((cw_now, ch_now), Image.Resampling.BILINEAR))[:, :, ::-1].copy()
                        y0, y1 = max(0, cy_now), min(height, cy_now + ch_now)
                        x0, x1 = max(0, cx_now), min(width, cx_now + cw_now)
                        h_d, w_d = y1 - y0, x1 - x0
                        if h_d > 0 and w_d > 0:
                            tiles_layer[y0:y1, x0:x1] = resized[y0-cy_now:y0-cy_now+h_d, x0-cx_now:x0-cx_now+w_d]
                    else:
                        cx_now = int(round(centerX - 125 + (tx - (centerX - 125)) * ep))
                        cy_now = int(round(centerY - 125 + (ty - (centerY - 125)) * ep))
                        cw_now = max(2, int(round(250 + (tw - 250) * ep)))
                        ch_now = max(2, int(round(250 + (th - 250) * ep)))
                        
                        resized = np.array(img_pil.resize((cw_now, ch_now), Image.Resampling.BILINEAR))[:, :, ::-1].copy()
                        border_w = max(0, int(round(2 * (1 - ep))))
                        if border_w > 0:
                            cv2.rectangle(resized, (0, 0), (cw_now-1, ch_now-1), (255, 255, 255), border_w)
                        
                        y0, y1 = max(0, cy_now), min(height, cy_now + ch_now)
                        x0, x1 = max(0, cx_now), min(width, cx_now + cw_now)
                        h_d, w_d = y1 - y0, x1 - x0
                        if h_d > 0 and w_d > 0:
                            src_roi = resized[y0-cy_now:y0-cy_now+h_d, x0-cx_now:x0-cx_now+w_d]
                            dst_roi = tiles_layer[y0:y1, x0:x1].astype(float)
                            blend = dst_roi * (1.0 - ep) + src_roi.astype(float) * ep
                            tiles_layer[y0:y1, x0:x1] = blend.clip(0, 255).astype(np.uint8)
            else:
                for b_key, b_data in level_blocks[level_idx].items():
                    bx, by, bw, bh = b_data['bbox']
                    c_val, r_val = b_data['cells'][0]
                    img_pil = source_images_cache[(c_val, r_val)]
                    resized = np.array(img_pil.resize((bw, bh), Image.Resampling.BILINEAR))[:, :, ::-1].copy()
                    tiles_layer[by:by+bh, bx:bx+bw] = resized

            tile_mask = (tiles_layer.sum(axis=2) > 0).astype(float)[..., np.newaxis]
            final_frame = tiles_layer.astype(float) * tile_mask + bg_bgr_base.astype(float) * (1.0 - tile_mask)
            
            if config.get("cellFilters"):
                filters = config.get("cellFilters", {})
                red_mask = np.zeros((height, width, 1), dtype=np.float32)
                for (c, r) in active_cells:
                    if filters.get(f"{r}_{c}") == "red":
                        red_mask[r*tile_h:(r+1)*tile_h, c*tile_w:(c+1)*tile_w] = 1.0
                
                tinted = final_frame.copy()
                tinted[:, :, 0] = tinted[:, :, 0] * 0.4
                tinted[:, :, 1] = tinted[:, :, 1] * 0.4
                tinted[:, :, 2] = np.clip(tinted[:, :, 2] * 1.5, 0, 255)
                final_frame = tinted * red_mask + final_frame * (1.0 - red_mask)

            out.write(final_frame.clip(0, 255).astype(np.uint8))
            
            if f_idx % 10 == 0:
                exports[export_id]["progress"] = int((f_idx / total_frames) * 100)
                
        out.release()
        exports[export_id]["status"] = "completed"
        exports[export_id]["progress"] = 100
        exports[export_id]["file_path"] = f"/api/export/video/download/{export_id}"
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        exports[export_id]["status"] = "error"
        exports[export_id]["error"] = str(e)
