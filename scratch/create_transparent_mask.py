import cv2
import numpy as np
from PIL import Image

def main():
    img_path = r"C:\Users\jrval\.gemini\antigravity-ide\brain\db23e326-ec59-4067-801b-9e0f6c5f2338\media__1785978057370.png"
    out_path = r"C:\Users\jrval\Desktop\Mosaico_Pixel\assets\backgrounds\mascara_hsbc_transparente.png"
    out_desktop = r"C:\Users\jrval\Desktop\mascara_hsbc_transparente.png"

    # Abre a imagem
    img = Image.open(img_path).convert("RGBA")
    data = np.array(img) # Shape: (H, W, 4)

    # Identifica pixels vermelhos: R alto, G e B baixos
    r = data[:,:,0]
    g = data[:,:,1]
    b = data[:,:,2]

    # Threshold para detectar os losangos vermelhos vibrantes
    # Na imagem do HSBC, o vermelho eh bem forte (ex: R > 150, G < 80, B < 80)
    red_mask = (r > 120) & (g < 80) & (b < 80)

    # Torna esses pixels 100% transparentes (Alpha = 0)
    data[red_mask, 3] = 0

    # Salva o resultado
    out_img = Image.fromarray(data, "RGBA")
    out_img.save(out_path, "PNG")
    out_img.save(out_desktop, "PNG")

    print(f"Mascara salva em:\n{out_path}\n{out_desktop}")

if __name__ == "__main__":
    main()
