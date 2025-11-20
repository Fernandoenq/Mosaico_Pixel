#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo para detecção de rostos em imagens usando OpenCV Haar Cascade.
Usado para centralizar o corte das imagens nos rostos detectados.
"""

import cv2
import numpy as np
from PIL import Image


def detectar_rosto_principal(imagem_pil):
    """
    Detecta o rosto principal em uma imagem PIL e retorna suas coordenadas.
    
    Args:
        imagem_pil: Imagem PIL (RGB)
    
    Returns:
        tuple: (centro_x, centro_y, largura_rosto, altura_rosto) ou None se não detectar rosto
    """
    # Converte PIL para OpenCV (BGR)
    imagem_cv = cv2.cvtColor(np.array(imagem_pil), cv2.COLOR_RGB2BGR)
    
    # Converte para escala de cinza (melhor para detecção)
    gray = cv2.cvtColor(imagem_cv, cv2.COLOR_BGR2GRAY)
    
    # Carrega o classificador Haar Cascade para rostos
    # Este é um modelo pré-treinado que vem com o OpenCV
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    # Detecta rostos
    # scaleFactor: quanto a imagem é reduzida em cada escala (1.1 = 10% menor a cada vez)
    # minNeighbors: quantos vizinhos cada retângulo candidato deve ter para ser mantido
    # minSize: tamanho mínimo do rosto em pixels
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30)
    )
    
    if len(faces) == 0:
        # Nenhum rosto detectado
        return None
    
    # Se detectou múltiplos rostos, pega o maior (provavelmente o principal)
    if len(faces) > 1:
        # Ordena por área (largura * altura) em ordem decrescente
        faces = sorted(faces, key=lambda face: face[2] * face[3], reverse=True)
    
    # Pega o primeiro (maior) rosto
    x, y, w, h = faces[0]
    
    # Calcula o centro do rosto
    centro_x = x + w // 2
    centro_y = y + h // 2
    
    return (centro_x, centro_y, w, h)


def calcular_crop_centralizado_no_rosto(imagem_pil, largura_alvo, altura_alvo):
    """
    Calcula as coordenadas de corte para centralizar a imagem no rosto detectado.
    Se não detectar rosto, retorna corte centralizado normal.
    
    Args:
        imagem_pil: Imagem PIL (RGB)
        largura_alvo: Largura desejada do corte
        altura_alvo: Altura desejada do corte
    
    Returns:
        tuple: (x_inicio, y_inicio, x_fim, y_fim) - coordenadas do corte
    """
    largura_img = imagem_pil.width
    altura_img = imagem_pil.height
    
    # Tenta detectar rosto
    rosto = detectar_rosto_principal(imagem_pil)
    
    if rosto is not None:
        # Rosto detectado! Usa o centro do rosto como ponto de referência
        centro_x, centro_y, rosto_w, rosto_h = rosto
    else:
        # Nenhum rosto detectado - usa centro da imagem
        centro_x = largura_img // 2
        centro_y = altura_img // 2
    
    # Calcula a proporção necessária para preencher o tamanho alvo
    proporcao_alvo = largura_alvo / altura_alvo
    proporcao_img = largura_img / altura_img
    
    if proporcao_img > proporcao_alvo:
        # Imagem é mais larga - ajusta pela altura e corta as laterais
        nova_altura = altura_img
        nova_largura = int(altura_img * proporcao_alvo)
        
        # Calcula posição X para centralizar no rosto
        x_inicio = centro_x - nova_largura // 2
        
        # Garante que não sai dos limites
        if x_inicio < 0:
            x_inicio = 0
        elif x_inicio + nova_largura > largura_img:
            x_inicio = largura_img - nova_largura
        
        y_inicio = 0
        x_fim = x_inicio + nova_largura
        y_fim = altura_img
        
    else:
        # Imagem é mais alta - ajusta pela largura e corta topo/fundo
        nova_largura = largura_img
        nova_altura = int(largura_img / proporcao_alvo)
        
        # Calcula posição Y para centralizar no rosto
        y_inicio = centro_y - nova_altura // 2
        
        # Garante que não sai dos limites
        if y_inicio < 0:
            y_inicio = 0
        elif y_inicio + nova_altura > altura_img:
            y_inicio = altura_img - nova_altura
        
        x_inicio = 0
        x_fim = largura_img
        y_fim = y_inicio + nova_altura
    
    return (x_inicio, y_inicio, x_fim, y_fim)


def carregar_e_redimensionar_com_deteccao_rosto(caminho_imagem, largura, altura, verbose=False):
    """
    Carrega e recorta a imagem CENTRALIZANDO NO ROSTO detectado.
    Se não detectar rosto, faz corte centralizado normal.
    
    Args:
        caminho_imagem: Caminho para o arquivo de imagem
        largura: Largura desejada final
        altura: Altura desejada final
        verbose: Se True, imprime informações sobre detecção
    
    Returns:
        numpy.ndarray: Imagem processada (RGB)
    """
    try:
        # Abre a imagem
        img = Image.open(caminho_imagem)
        
        # Converte para RGB se necessário
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Calcula coordenadas de corte centralizadas no rosto
        x_inicio, y_inicio, x_fim, y_fim = calcular_crop_centralizado_no_rosto(img, largura, altura)
        
        # Faz o corte
        img_cortada = img.crop((x_inicio, y_inicio, x_fim, y_fim))
        
        # Redimensiona para o tamanho final
        img_final = img_cortada.resize((largura, altura), Image.Resampling.LANCZOS)
        
        if verbose:
            # Verifica se tinha rosto
            rosto = detectar_rosto_principal(img)
            if rosto:
                print(f"      ✓ Rosto detectado - cortado centralizado no rosto")
            else:
                print(f"      ○ Sem rosto - cortado no centro")
        
        return np.array(img_final)
        
    except Exception as e:
        if verbose:
            print(f"      ✗ Erro ao processar: {e}")
        # Em caso de erro, retorna imagem branca
        return np.ones((altura, largura, 3), dtype=np.uint8) * 255


# Função de teste
if __name__ == "__main__":
    import sys
    
    print("\n" + "="*60)
    print("TESTE DE DETECÇÃO DE ROSTOS")
    print("="*60)
    
    if len(sys.argv) > 1:
        # Testa com imagem fornecida
        caminho = sys.argv[1]
        print(f"\nTestando com: {caminho}")
        
        img = Image.open(caminho)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        print(f"Tamanho original: {img.width}x{img.height}")
        
        rosto = detectar_rosto_principal(img)
        if rosto:
            centro_x, centro_y, w, h = rosto
            print(f"✓ ROSTO DETECTADO!")
            print(f"  • Centro: ({centro_x}, {centro_y})")
            print(f"  • Tamanho: {w}x{h} pixels")
        else:
            print("✗ Nenhum rosto detectado")
        
        print("\nTestando corte 100x100 centralizado no rosto...")
        img_cortada = carregar_e_redimensionar_com_deteccao_rosto(caminho, 100, 100, verbose=True)
        print(f"Imagem final: {img_cortada.shape}")
        
    else:
        print("\nUso: python detectar_rosto.py <caminho_imagem>")
    
    print("\n" + "="*60)

