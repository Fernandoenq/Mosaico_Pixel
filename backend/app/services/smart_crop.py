import cv2
import numpy as np

# Carrega o classificador de rostos Haar Cascade nativo do OpenCV
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

def smart_crop_face(image_bgr: np.ndarray, target_size: tuple[int, int] = (250, 250)) -> np.ndarray:
    """
    Detecta o rosto principal via OpenCV Haar Cascade e realiza um corte quadrado
    centralizado no rosto. Se nenhum rosto for encontrado, realiza um corte proporcional no centro.
    
    Args:
        image_bgr: Imagem de entrada em formato BGR (OpenCV)
        target_size: Dimensões (largura, altura) da imagem recortada final
    
    Returns:
        numpy.ndarray: Imagem recortada e redimensionada (BGR)
    """
    if image_bgr is None or image_bgr.size == 0:
        return np.ones((*target_size, 3), dtype=np.uint8) * 255

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    try:
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )
    except Exception as e:
        print(f"[SmartCrop] Erro detectMultiScale: {e}")
        faces = []
    
    h, w = image_bgr.shape[:2]
    
    if len(faces) > 0:
        # Pega o maior rosto por área (largura * altura)
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        fx, fy, fw, fh = faces[0]
        
        # Ponto central da face detectada
        center_x = fx + fw // 2
        center_y = fy + fh // 2
        
        # Define o tamanho do corte (1.8x o tamanho da face para dar contexto de ombros/cabelo)
        crop_dim = int(max(fw, fh) * 1.8)
        crop_dim = min(crop_dim, min(w, h))
        
        x0 = max(0, min(center_x - crop_dim // 2, w - crop_dim))
        y0 = max(0, min(center_y - crop_dim // 2, h - crop_dim))
        
        cropped = image_bgr[y0:y0 + crop_dim, x0:x0 + crop_dim]
    else:
        # Center crop proporcional clássico
        min_dim = min(w, h)
        x0 = (w - min_dim) // 2
        y0 = (h - min_dim) // 2
        cropped = image_bgr[y0:y0 + min_dim, x0:x0 + min_dim]
        
    return cv2.resize(cropped, target_size, interpolation=cv2.INTER_AREA)
