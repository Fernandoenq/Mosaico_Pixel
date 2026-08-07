from pathlib import Path
import os

class Settings:
    PROJECT_NAME: str = "True Photo Mosaic Corporate Engine"
    API_V1_STR: str = "/api"
    
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    # Pasta ASSISTIDA pelo watcher: só entram fotos cruas da câmera.
    HOT_FOLDER_DIR: Path = STORAGE_DIR / "hot_folder"
    # Saída dos recortes servidos ao telão. Precisa ficar FORA da pasta assistida,
    # senão cada recorte gravado dispara o watcher de novo, em cascata infinita.
    TILES_DIR: Path = STORAGE_DIR / "tiles"
    BRAND_FALLBACKS_DIR: Path = STORAGE_DIR / "brand_fallbacks"
    PRINT_OUT_DIR: Path = STORAGE_DIR / "print_out"
    
    # Defaults de Display e Grid
    DEFAULT_SCREEN_WIDTH: int = 1920
    DEFAULT_SCREEN_HEIGHT: int = 1080
    DEFAULT_GRID_ROWS: int = 30
    DEFAULT_GRID_COLS: int = 40
    
    # Tolerância de Cor e Distância
    DEFAULT_DUPLICATE_DIST_LIMIT: int = 3
    DEFAULT_COLOR_STRICTNESS: float = 1.0

settings = Settings()

# Garante a existência dos diretórios do sistema
for path in [settings.STORAGE_DIR, settings.HOT_FOLDER_DIR, settings.TILES_DIR, settings.BRAND_FALLBACKS_DIR, settings.PRINT_OUT_DIR]:
    path.mkdir(parents=True, exist_ok=True)
