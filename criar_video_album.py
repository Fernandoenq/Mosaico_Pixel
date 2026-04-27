#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para criar um vídeo de álbum de fotos com animação dinâmica super caótica!

⚠️  RESOLUÇÃO DO VÍDEO:
Se você receber erro 0xC00D36B4 ao tentar abrir o vídeo, ajuste a variável ESCALA:
- ESCALA = 1.0 → Resolução original 6384x1344 (pode não funcionar em todos os players)
- ESCALA = 0.5 → Resolução reduzida 3192x672 (mais compatível) ✅ RECOMENDADO
- ESCALA = 0.25 → Resolução menor 1596x336 (máxima compatibilidade)

Características:
- Todas as fotos da pasta MOSAIC aparecem em um único grid
- ONDAS SOBREPOSTAS: antes de uma onda terminar, a próxima já começa
  * Delay de 0.3s entre ondas cria movimento fluido e contínuo
  * Múltiplas fotos entram ao mesmo tempo (1 a 40 por onda)
- FOTOS GIGANTES: Mínimo 20 fotos aparecem ENORMES (6x a 10x) e se movem DEVAGAR
  * Criam impacto visual extremo
  * Movimento mais lento (easing quadrático) dá sensação de "peso"
- TAMANHOS VARIADOS: 3 categorias (gigantes, destaque, normais)
  * 12% em destaque (2.5x a 4x)
  * Resto varia entre 0.6x e 1.4x
- Entrada TOTALMENTE ALEATÓRIA: 
  * Grupos variados (às vezes 1 foto sozinha, às vezes 30 juntas)
  * Ordem completamente randomizada
- DIREÇÕES VARIADAS: cada foto vem de um canto/lado diferente
  (esquerda, direita, cima, baixo, ou diagonais)
- ROTAÇÃO DINÂMICA: fotos entram tortas (até ±45°) e vão se endireitando
- EFEITO DE CAMADAS NA SAÍDA: fotos que saem ficam POR CIMA das outras
  * Cria profundidade visual
  * Ordenadas por progresso (mais progresso = mais por cima)
- SEM FADE: fotos aparecem e desaparecem opacas (sem transparência)
- MÁSCARA INDIVIDUAL: cada foto recebe sua "fatia" do fundo.jpg
  * A máscara é aplicada em cada foto do mosaico, não no frame todo
  * A máscara já está presente desde que a foto aparece
  * Quando todas estão posicionadas, formam juntas a imagem do fundo.jpg
- Fundo branco puro

Cada execução gera um vídeo completamente diferente!
"""

import os
import cv2
import numpy as np
from PIL import Image
import glob
from pathlib import Path
import math
import random
import time
import sys
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

# Importa módulo de detecção de rosto
from detectar_rosto import carregar_e_redimensionar_com_deteccao_rosto

# Configura encoding UTF-8 para o console no Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass  # Se falhar, continuamos sem emojis renderizados corretamente

# Configurações GLOBAIS (usadas por todas as versões do vídeo)
PASTA_IMAGENS = "MOSAIC"
# FOTO_MASCARA agora é definida individualmente para cada vídeo (ver VIDEOS_PARA_GERAR)
FPS = 30

# Configurações de animação (compartilhadas)
# Entrada: ~30 segundos | Pausa: 7 segundos (4s fade + 3s estático)
DURACAO_POR_ONDA = 3.0  # Segundos que cada onda leva para aparecer
DELAY_ENTRE_ONDAS = 0.8  # Segundos de delay entre início de cada onda (sobreposição)
DURACAO_PAUSA_MEIO = 7  # 4s fade Máscara1→Máscara2 + 3s mantém Máscara2 (vídeo termina na Máscara2)
TRANSPARENCIA_MASCARA = 0.85  # Transparência da máscara aplicada em cada foto (0.0 = invisível, 1.0 = opaca)
OPACIDADE_FOTO_ENCAIXADA = 0.55  # Opacidade das fotos após encaixarem no mosaico

# Configurações de destaque e variação de tamanho (compartilhadas)
# NUM_FOTOS_GIGANTES = 100  # [COMENTADO] Número mínimo de fotos que aparecem GIGANTES na tela

# FOTOS GIGANTES - Efeito especial de entrada [COMENTADO - NÃO ESTÁ SENDO USADO]
# ESCALA_GIGANTE_SUPER_MIN = 15.0  # Escala SUPER inicial - começam MUITO maiores (invisíveis/transparentes)
# ESCALA_GIGANTE_SUPER_MAX = 20.0  # Escala SUPER inicial máxima
# ESCALA_GIGANTE_MIN = 9.0  # Tamanho gigante FINAL - quando ficam totalmente opacas (600%)
# ESCALA_GIGANTE_MAX = 10.0  # Tamanho gigante FINAL máximo (1000%)
# EFEITO: Começam 15x-20x maiores e INVISÍVEIS → vão diminuindo e ficando OPACAS → 
#         quando atingem 6x-10x já estão 100% visíveis → continuam até 1x (tamanho normal)
# NOTA: Fotos gigantes se movem MAIS DEVAGAR (easing quadrático vs quintic) criando efeito de "peso"

PORCENTAGEM_DESTAQUE = 1.0  # 100% das fotos aparecem em destaque (todas com mesmo tamanho)
ESCALA_MINIMA = 8.0  # Fotos normais podem entrar com 60% do tamanho
ESCALA_MAXIMA = 8.5  # Fotos normais podem entrar com 160% do tamanho
ESCALA_DESTAQUE_MIN = 8.5  # Fotos em destaque entram com 250% do tamanho (TODAS AS FOTOS USAM ISSO)
ESCALA_DESTAQUE_MAX = 9.0  # Fotos em destaque entram com até 400% do tamanho

# CONFIGURAÇÕES DOS VÍDEOS A GERAR
# O script irá gerar TODOS os vídeos listados abaixo
# NOTA: A resolução 6384x1344 causa erro 0xC00D36B4 (incompatível com codec mp4v)
#       Por isso usamos 3192x672 (50% da original) que funciona perfeitamente
# CADA VÍDEO USA SUA PRÓPRIA MÁSCARA (já no tamanho correto!)
VIDEOS_PARA_GERAR = [
    {
        'nome': 'Mosaico_Pixel_6384x1344.mp4',
        'largura': 6384,  # Resolução COMPLETA (100%)
        'altura': 1344,   # Resolução COMPLETA (aspect ratio 4.75:1 ultrawide)
        'descricao': 'Video em resolucao COMPLETA 6384x1344',
        'mascara': 'fundoaltosemtexto.png',  # Máscara será redimensionada automaticamente
        'mascara2': 'fundoalto.png',
        'celula_base': 112  # Células maiores = menos imagens (~684 imagens)
    },
    {
        'nome': 'Mosaico_Pixel_1680x1176.mp4',
        'largura': 1680,
        'altura': 1176,
        'descricao': 'Video em resolucao alternativa',
        'mascara': 'fundobaixosemtexto.png',  # Máscara específica para resolução alternativa (1680x1176)
        'mascara2': 'fundobaixo.png',
        'celula_base': 56   # Células menores = mais imagens (mantém original ~900 imagens)
    }
]

def carregar_e_redimensionar(caminho_imagem, largura, altura):
    """Carrega e recorta a imagem para preencher completamente a célula QUADRADA.
    AGORA COM DETECÇÃO DE ROSTO: centraliza o corte no rosto detectado!
    Se não detectar rosto, usa corte centralizado normal."""
    # Usa a função do módulo detectar_rosto que já faz tudo isso
    return carregar_e_redimensionar_com_deteccao_rosto(caminho_imagem, largura, altura, verbose=True)

def carregar_mascara(caminho_mascara, largura, altura):
    """Carrega a imagem de máscara redimensionada para o tamanho do vídeo"""
    try:
        img_mascara = Image.open(caminho_mascara)
        if img_mascara.mode != 'RGB':
            img_mascara = img_mascara.convert('RGB')
        img_mascara = img_mascara.resize((largura, altura), Image.Resampling.LANCZOS)
        mascara_array = np.array(img_mascara).astype(np.float32) / 255.0
        return mascara_array
    except Exception as e:
        print(f"⚠️ Não foi possível carregar a máscara: {e}")
        print("   Continuando sem máscara...")
        return None

def extrair_regiao_mascara(mascara_completa, x, y, largura, altura):
    """Extrai uma região específica da máscara para aplicar em uma foto"""
    if mascara_completa is None:
        return None
    
    # Garante que não ultrapasse os limites
    x_end = min(x + largura, mascara_completa.shape[1])
    y_end = min(y + altura, mascara_completa.shape[0])
    x = max(0, x)
    y = max(0, y)
    
    return mascara_completa[y:y_end, x:x_end]

def aplicar_mascara_na_foto(foto, regiao_mascara, alpha):
    """Aplica uma região da máscara diretamente em uma foto"""
    if regiao_mascara is None:
        return foto
    
    # Ajusta o tamanho se necessário
    if regiao_mascara.shape[:2] != foto.shape[:2]:
        # Redimensiona a região da máscara para o tamanho da foto
        h, w = foto.shape[:2]
        regiao_mascara = cv2.resize(regiao_mascara, (w, h))
    
    # Blending: foto * (1 - alpha) + mascara * alpha
    foto_float = foto.astype(np.float32) / 255.0
    resultado = foto_float * (1 - alpha) + regiao_mascara * alpha
    return (resultado * 255).astype(np.uint8)

def calcular_posicao_origem(x_final, y_final, largura_foto, altura_foto, largura_video, altura_video, direcao, escala_inicial=1.0):
    """Calcula a posição de origem da foto baseada na direção de entrada
    
    IMPORTANTE: Considera a escala inicial para garantir que a foto comece COMPLETAMENTE fora da tela
    """
    # Calcula o tamanho real da foto quando escalada
    largura_real = int(largura_foto * escala_inicial)
    altura_real = int(altura_foto * escala_inicial)
    
    # Margem extra para garantir que está completamente fora (20% do tamanho escalado)
    margem_extra = int(max(largura_real, altura_real) * 0.2)
    
    if direcao == 0:  # Esquerda
        return -(largura_real + margem_extra), y_final
    elif direcao == 1:  # Direita
        return largura_video + margem_extra, y_final
    elif direcao == 2:  # Cima
        return x_final, -(altura_real + margem_extra)
    elif direcao == 3:  # Baixo
        return x_final, altura_video + margem_extra
    elif direcao == 4:  # Diagonal superior esquerda
        return -(largura_real + margem_extra), -(altura_real + margem_extra)
    elif direcao == 5:  # Diagonal superior direita
        return largura_video + margem_extra, -(altura_real + margem_extra)
    elif direcao == 6:  # Diagonal inferior esquerda
        return -(largura_real + margem_extra), altura_video + margem_extra
    else:  # direcao == 7: Diagonal inferior direita
        return largura_video + margem_extra, altura_video + margem_extra

def rotacionar_imagem(imagem, angulo, centro_x, centro_y):
    """Rotaciona uma imagem em torno de um ponto central"""
    altura, largura = imagem.shape[:2]
    matriz_rotacao = cv2.getRotationMatrix2D((centro_x, centro_y), angulo, 1.0)
    
    # Calcula o tamanho da imagem rotacionada
    cos = abs(matriz_rotacao[0, 0])
    sin = abs(matriz_rotacao[0, 1])
    nova_largura = int((altura * sin) + (largura * cos))
    nova_altura = int((altura * cos) + (largura * sin))
    
    # Ajusta a matriz de rotação para levar em conta a translação
    matriz_rotacao[0, 2] += (nova_largura / 2) - centro_x
    matriz_rotacao[1, 2] += (nova_altura / 2) - centro_y
    
    # Aplica a rotação com fundo cor #f4c866 (RGB: 244, 200, 102)
    # IMPORTANTE: A imagem vem do PIL em RGB, então usamos RGB aqui também!
    # Só convertemos para BGR na hora de escrever no vídeo
    imagem_rotacionada = cv2.warpAffine(imagem, matriz_rotacao, (nova_largura, nova_altura),
                                        borderMode=cv2.BORDER_CONSTANT, borderValue=(244, 200, 102))
    
    return imagem_rotacionada, nova_largura, nova_altura

def desenhar_foto_em_posicao(frame, foto, x, y, largura_foto, altura_foto, largura_video, altura_video, angulo=0, escala=1.0, respeitar_limites_celula=False, opacidade=1.0):
    """Desenha a foto no frame, com rotação e escala opcionais.
    
    Args:
        respeitar_limites_celula: Se True, a imagem nunca ultrapassa os limites da sua célula.
                                  Se False (padrão), a imagem pode sobrepor outras células (usado na animação).
    """
    
    # Guarda os limites originais da célula (caso precise respeitar)
    celula_x_min = x
    celula_y_min = y
    celula_x_max = x + largura_foto
    celula_y_max = y + altura_foto
    
    # Aplica escala se diferente de 1.0
    if escala != 1.0:
        nova_largura_escala = int(largura_foto * escala)
        nova_altura_escala = int(altura_foto * escala)
        foto_escalada = cv2.resize(foto, (nova_largura_escala, nova_altura_escala), interpolation=cv2.INTER_LINEAR)
        
        # Ajusta posição para manter o centro
        x_centralizado = x - (nova_largura_escala - largura_foto) // 2
        y_centralizado = y - (nova_altura_escala - altura_foto) // 2
        
        foto_trabalho = foto_escalada
        largura_trabalho = nova_largura_escala
        altura_trabalho = nova_altura_escala
        x_trabalho = x_centralizado
        y_trabalho = y_centralizado
    else:
        foto_trabalho = foto
        largura_trabalho = largura_foto
        altura_trabalho = altura_foto
        x_trabalho = x
        y_trabalho = y
    
    if angulo != 0:
        # Rotaciona a foto (já escalada se necessário)
        foto_rotacionada, nova_largura, nova_altura = rotacionar_imagem(
            foto_trabalho, angulo, largura_trabalho // 2, altura_trabalho // 2
        )
        
        # Ajusta a posição para manter o centro
        x_ajustado = x_trabalho - (nova_largura - largura_trabalho) // 2
        y_ajustado = y_trabalho - (nova_altura - altura_trabalho) // 2
        
        largura_atual = nova_largura
        altura_atual = nova_altura
        foto_atual = foto_rotacionada
        x_atual = x_ajustado
        y_atual = y_ajustado
    else:
        foto_atual = foto_trabalho
        x_atual = x_trabalho
        y_atual = y_trabalho
        largura_atual = largura_trabalho
        altura_atual = altura_trabalho
    
    # Calcula os limites válidos
    if respeitar_limites_celula:
        # Modo GRID: a imagem nunca pode desenhar fora da sua célula
        x_src_start = max(0, -x_atual, celula_x_min - x_atual)
        y_src_start = max(0, -y_atual, celula_y_min - y_atual)
        x_src_end = min(largura_atual, largura_video - x_atual, celula_x_max - x_atual)
        y_src_end = min(altura_atual, altura_video - y_atual, celula_y_max - y_atual)
        
        x_dst_start = max(0, x_atual, celula_x_min)
        y_dst_start = max(0, y_atual, celula_y_min)
        x_dst_end = min(largura_video, x_atual + largura_atual, celula_x_max)
        y_dst_end = min(altura_video, y_atual + altura_atual, celula_y_max)
    else:
        # Modo ANIMAÇÃO: a imagem pode sobrepor outras células
        x_src_start = max(0, -x_atual)
        y_src_start = max(0, -y_atual)
        x_src_end = min(largura_atual, largura_video - x_atual)
        y_src_end = min(altura_atual, altura_video - y_atual)
        
        x_dst_start = max(0, x_atual)
        y_dst_start = max(0, y_atual)
        x_dst_end = min(largura_video, x_atual + largura_atual)
        y_dst_end = min(altura_video, y_atual + altura_atual)
    
    # Verifica se há alguma área visível
    if x_src_end > x_src_start and y_src_end > y_src_start:
        # Sobrepõe apenas pixels que NÃO sejam da cor de fundo se houver rotação
        if angulo != 0:
            regiao = frame[y_dst_start:y_dst_end, x_dst_start:x_dst_end]
            foto_regiao = foto_atual[y_src_start:y_src_end, x_src_start:x_src_end]
            
            # Cria máscara para pixels que NÃO são da cor de fundo #f4c866 (RGB: 244, 200, 102)
            # Tolerância de ±5 para lidar com compressão/interpolação
            cor_fundo = np.array([244, 200, 102])
            diferenca = np.abs(foto_regiao.astype(np.int16) - cor_fundo)
            mascara = np.any(diferenca > 5, axis=2)  # Pixel é diferente do fundo
            if opacidade >= 0.999:
                regiao[mascara] = foto_regiao[mascara]
            else:
                regiao_float = regiao.astype(np.float32)
                foto_float = foto_regiao.astype(np.float32)
                regiao_float[mascara] = (
                    regiao_float[mascara] * (1.0 - opacidade) +
                    foto_float[mascara] * opacidade
                )
                regiao[:] = regiao_float.astype(np.uint8)
        else:
            destino = frame[y_dst_start:y_dst_end, x_dst_start:x_dst_end]
            origem = foto_atual[y_src_start:y_src_end, x_src_start:x_src_end]
            if opacidade >= 0.999:
                destino[:] = origem
            else:
                destino[:] = (
                    destino.astype(np.float32) * (1.0 - opacidade) +
                    origem.astype(np.float32) * opacidade
                ).astype(np.uint8)
        
        # [BORDA REMOVIDA] - Imagens ficam encostadas sem separação visual
        # if angulo == 0 and x >= 0 and y >= 0 and x + largura_foto <= largura_video and y + altura_foto <= altura_video:
        #     cv2.rectangle(frame, (x-1, y-1), (x+largura_foto+1, y+altura_foto+1), 
        #                 (220, 220, 220), 1)

def listar_imagens(pasta):
    """Lista todas as imagens na pasta"""
    extensoes = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.webp', '*.jfif']
    imagens = []
    for ext in extensoes:
        imagens.extend(glob.glob(os.path.join(pasta, ext)))
        # Também busca maiúsculas
        imagens.extend(glob.glob(os.path.join(pasta, ext.upper())))
    
    # Remove duplicatas e ordena
    imagens = sorted(list(set(imagens)))
    return imagens

def criar_video_album(largura_video, altura_video, nome_saida, caminho_mascara, caminho_mascara2, tamanho_celula_base=56):
    """Cria o vídeo com efeito de álbum de fotos - todas as fotos em um único grid
    
    Args:
        largura_video: Largura do vídeo em pixels
        altura_video: Altura do vídeo em pixels
        nome_saida: Nome do arquivo de vídeo a ser gerado
        caminho_mascara: Caminho para o arquivo de máscara principal (usada durante entrada/saída)
        caminho_mascara2: Caminho para o arquivo de máscara secundária (usada durante a pausa)
        tamanho_celula_base: Tamanho base da célula em pixels (padrão: 56)
    """
    
    # Calcula configurações específicas para esta resolução
    # Grid com células QUADRADAS que PREENCHEM COMPLETAMENTE o vídeo
    # TAMANHO_CELULA_BASE específico por vídeo (passado como parâmetro)
    # Vídeo 6K: 112px (células maiores = menos imagens ~684)
    # Vídeo 1680x1176: 56px (células menores = mais imagens ~900)
    TAMANHO_CELULA_BASE = tamanho_celula_base  # Usa o valor passado por parâmetro
    
    # Calcula o tamanho da célula que melhor se ajusta à resolução atual
    # Tenta encontrar um divisor comum que resulte em células próximas de 56px
    melhor_tamanho = None
    melhor_diferenca = float('inf')
    
    for tentativa in range(30, 150):  # Testa tamanhos entre 30 e 150 pixels (células menores)
        cols = largura_video // tentativa
        rows = altura_video // tentativa
        
        # Verifica se divide perfeitamente (sem barras brancas)
        if cols * tentativa == largura_video and rows * tentativa == altura_video:
            diferenca = abs(tentativa - TAMANHO_CELULA_BASE)
            if diferenca < melhor_diferenca:
                melhor_tamanho = tentativa
                melhor_diferenca = diferenca
    
    # Se não encontrou divisor perfeito, usa o mais próximo possível
    if melhor_tamanho is None:
        melhor_tamanho = largura_video // (largura_video // TAMANHO_CELULA_BASE)
    
    TAMANHO_CELULA = melhor_tamanho
    FOTOS_POR_LINHA = largura_video // TAMANHO_CELULA
    FOTOS_POR_COLUNA = altura_video // TAMANHO_CELULA
    
    print("\n" + "="*70)
    print(f"GERANDO VIDEO: {nome_saida}")
    print("="*70)
    print(f"Resolucao: {largura_video}x{altura_video}")
    print(f"\nGrid calculado automaticamente para CELULAS QUADRADAS:")
    print(f"   Resolucao do video: {largura_video}x{altura_video}")
    print(f"   Tamanho da celula: {TAMANHO_CELULA}x{TAMANHO_CELULA} pixels (1:1 - quadrada)")
    print(f"   Grid resultante: {FOTOS_POR_LINHA} colunas x {FOTOS_POR_COLUNA} linhas")
    print(f"   Total de posicoes: {FOTOS_POR_LINHA * FOTOS_POR_COLUNA}")
    
    # ============================================================
    # FASE 1: PREPARAÇÃO - Análise e Processamento das Imagens
    # ============================================================
    print("\n" + "="*60)
    print("FASE 1: PREPARAÇÃO DAS IMAGENS")
    print("="*60)
    
    # Lista todas as imagens
    lista_imagens = listar_imagens(PASTA_IMAGENS)
    print(f"\n📸 Encontradas {len(lista_imagens)} imagens na pasta MOSAIC")
    
    if not lista_imagens:
        print("❌ Nenhuma imagem encontrada na pasta MOSAIC!")
        return
    
    # Calcula dimensões de cada foto no grid (CÉLULAS QUADRADAS - sem margens)
    margem = 0
    largura_foto = TAMANHO_CELULA  # Células quadradas
    altura_foto = TAMANHO_CELULA   # Células quadradas
    
    total_posicoes = FOTOS_POR_LINHA * FOTOS_POR_COLUNA
    
    print(f"\n📏 Configuração do Grid:")
    print(f"   • Resolução do vídeo: {largura_video}x{altura_video}")
    print(f"   • Grid: {FOTOS_POR_LINHA}x{FOTOS_POR_COLUNA} = {total_posicoes} posições")
    print(f"   • Tamanho de cada célula: {largura_foto}x{altura_foto} pixels ✅ QUADRADA")
    print(f"   • Proporção da célula: 1:1 (quadrada - mínimo corte possível)")
    
    # Ajusta a lista de imagens para preencher o grid
    if len(lista_imagens) > total_posicoes:
        print(f"\n⚠️  Existem {len(lista_imagens)} fotos mas apenas {total_posicoes} posições")
        print(f"   → Usando apenas as primeiras {total_posicoes} fotos")
        lista_imagens = lista_imagens[:total_posicoes]
    elif len(lista_imagens) < total_posicoes:
        fotos_faltantes = total_posicoes - len(lista_imagens)
        print(f"\n⚠️  Faltam {fotos_faltantes} fotos para completar o grid")
        print(f"   → Duplicando fotos aleatórias para completar")
        
        # Sorteia fotos aleatórias para duplicar
        fotos_originais = lista_imagens.copy()
        for _ in range(fotos_faltantes):
            foto_duplicada = random.choice(fotos_originais)
            lista_imagens.append(foto_duplicada)
        
        print(f"   ✅ Grid completo com {len(lista_imagens)} fotos (incluindo {fotos_faltantes} duplicadas)")
    
    # Carrega as 2 máscaras completas (já no tamanho correto para esta resolução!)
    print(f"\n🎭 Carregando máscara principal (entrada/saída): {caminho_mascara}")
    print(f"   • Resolução esperada: {largura_video}x{altura_video}")
    mascara_completa = carregar_mascara(caminho_mascara, largura_video, altura_video)
    if mascara_completa is not None:
        print(f"   ✅ Máscara principal carregada com sucesso")
        print(f"   • Transparência: {int(TRANSPARENCIA_MASCARA * 100)}%")
        print(f"   • A máscara será dividida em {len(lista_imagens)} regiões")
    
    print(f"\n🎭 Carregando máscara secundária (pausa): {caminho_mascara2}")
    print(f"   • Resolução esperada: {largura_video}x{altura_video}")
    mascara_completa2 = carregar_mascara(caminho_mascara2, largura_video, altura_video)
    if mascara_completa2 is not None:
        print(f"   ✅ Máscara secundária carregada com sucesso")
        print(f"   • Transparência: {int(TRANSPARENCIA_MASCARA * 100)}%")
        print(f"   • Será usada durante a pausa entre entrada e saída")
    
    # Calcula posições finais de todas as fotos no grid (sem margens)
    print(f"\n📐 Calculando posições finais no grid...")
    todas_posicoes = []
    
    # Cria TODAS as posições do grid (38 colunas x 8 linhas = 304)
    for linha in range(FOTOS_POR_COLUNA):
        for coluna in range(FOTOS_POR_LINHA):
            x = coluna * largura_foto
            y = linha * altura_foto
            todas_posicoes.append((x, y))
    
    print(f"   ✅ {len(todas_posicoes)} posições calculadas (deve ser {FOTOS_POR_LINHA}x{FOTOS_POR_COLUNA} = {FOTOS_POR_LINHA * FOTOS_POR_COLUNA})")
    
    # Garante que temos exatamente o número correto de imagens
    if len(lista_imagens) != len(todas_posicoes):
        print(f"   ⚠️  ATENÇÃO: {len(lista_imagens)} imagens vs {len(todas_posicoes)} posições!")
        if len(lista_imagens) < len(todas_posicoes):
            # Duplica mais imagens se necessário
            fotos_faltantes = len(todas_posicoes) - len(lista_imagens)
            fotos_originais = lista_imagens[:178]  # Usa apenas as originais para duplicar
            for _ in range(fotos_faltantes):
                lista_imagens.append(random.choice(fotos_originais))
            print(f"   ✅ Ajustado: {len(lista_imagens)} imagens")
    
    # Processa todas as fotos: carrega + redimensiona + cria 3 versões (original e com 2 máscaras)
    print(f"\n🖼️  Processando todas as imagens...")
    print(f"   (Carregando, redimensionando e criando 3 versoes: original, mascara1 e mascara2)")
    
    todas_fotos_originais = []  # Fotos originais (sem máscara)
    todas_fotos_com_mascara = []  # Fotos com máscara principal
    todas_fotos_com_mascara2 = []  # Fotos com máscara secundária (para pausa)
    
    for i, caminho_imagem in enumerate(lista_imagens):
        nome_foto = Path(caminho_imagem).name
        x, y = todas_posicoes[i]
        
        print(f"   [{i + 1}/{len(lista_imagens)}] {nome_foto}")
        
        # Carrega e redimensiona a foto ORIGINAL
        foto_original = carregar_e_redimensionar(caminho_imagem, largura_foto, altura_foto)
        
        # Extrai a região específica da máscara PRINCIPAL para esta posição
        regiao_mascara = extrair_regiao_mascara(mascara_completa, x, y, largura_foto, altura_foto)
        
        # Aplica a máscara PRINCIPAL na foto
        foto_com_mascara = aplicar_mascara_na_foto(foto_original, regiao_mascara, TRANSPARENCIA_MASCARA)
        
        # Extrai a região específica da máscara SECUNDÁRIA para esta posição
        regiao_mascara2 = extrair_regiao_mascara(mascara_completa2, x, y, largura_foto, altura_foto)
        
        # Aplica a máscara SECUNDÁRIA na foto
        foto_com_mascara2 = aplicar_mascara_na_foto(foto_original, regiao_mascara2, TRANSPARENCIA_MASCARA)
        
        todas_fotos_originais.append(foto_original)
        todas_fotos_com_mascara.append(foto_com_mascara)
        todas_fotos_com_mascara2.append(foto_com_mascara2)
    
    print(f"\n   ✅ {len(todas_fotos_originais)} imagens processadas!")
    print(f"   • Versao original (sem mascara): para animacao de entrada/saida")
    print(f"   • Versao com mascara principal: para estado final (entrada/saida)")
    print(f"   • Versao com mascara secundaria: para exibicao durante a pausa")
    
    # Gera imagem de resultado final (preview)
    print(f"\n🖼️  Gerando preview do resultado final...")
    # Fundo cor #f4c866 (RGB: 244, 200, 102)
    frame_final = np.ones((altura_video, largura_video, 3), dtype=np.uint8)
    frame_final[:, :] = [244, 200, 102]  # RGB
    for i, (foto, (x, y)) in enumerate(zip(todas_fotos_com_mascara, todas_posicoes)):
        desenhar_foto_em_posicao(
            frame_final, foto, x, y,
            largura_foto, altura_foto,
            largura_video, altura_video
        )
    print(f"   ✅ Resultado final preparado")
    
    print("\n" + "="*60)
    print("PREPARAÇÃO CONCLUÍDA!")
    print("="*60)
    
    # ============================================================
    # FASE 2: PLANEJAMENTO DA ANIMAÇÃO
    # ============================================================
    print("\n" + "="*60)
    print("FASE 2: PLANEJAMENTO DA ANIMAÇÃO")
    print("="*60)
    
    # Cria uma lista com as informações de cada foto para animação
    print("\n🎲 Definindo ordem, direções, tamanhos e destaques...")
    info_fotos = []
    
    # [COMENTADO] Define quantas fotos serão GIGANTES (mínimo 5)
    # num_gigantes = max(NUM_FOTOS_GIGANTES, int(len(todas_fotos_com_mascara) * 0.02))  # Mínimo 5 ou 2%
    # indices_gigantes = random.sample(range(len(todas_fotos_com_mascara)), num_gigantes)
    
    # [COMENTADO] Define quantas fotos serão destacadas (excluindo as gigantes)
    # indices_disponiveis = [i for i in range(len(todas_fotos_com_mascara)) if i not in indices_gigantes]
    # num_destaques = min(int(len(todas_fotos_com_mascara) * PORCENTAGEM_DESTAQUE), len(indices_disponiveis))
    # indices_destaque = random.sample(indices_disponiveis, num_destaques)
    
    for i in range(len(todas_fotos_com_mascara)):
        direcao_entrada = random.randint(0, 7)  # 8 direções possíveis
        x_final, y_final = todas_posicoes[i]
        
        # [MODIFICADO] TODAS as fotos usam ESCALA_DESTAQUE (sem gigantes ou normais)
        eh_gigante = False  # Desabilitado
        em_destaque = True  # TODAS em destaque
        
        # TODAS as fotos entram com ESCALA_DESTAQUE
        escala_inicial = random.uniform(ESCALA_DESTAQUE_MIN, ESCALA_DESTAQUE_MAX)
        escala_final_gigante = 1.0  # Não usa gigante
        tipo = 'destaque'
        
        # Calcula posição de origem DEPOIS de ter a escala (para garantir que começa fora da tela)
        x_origem, y_origem = calcular_posicao_origem(
            x_final, y_final, largura_foto, altura_foto, 
            largura_video, altura_video, direcao_entrada,
            escala_inicial  # IMPORTANTE: passa a escala para calcular corretamente
        )
        
        # Ângulo de rotação inicial limitado a ±45° (evita imagens de cabeça para baixo)
        # -45° = rotação anti-horária | +45° = rotação horária
        angulo_inicial = random.uniform(-45, 45)
        
        info_fotos.append({
            'indice': i,
            'foto_original': todas_fotos_originais[i],  # Foto ORIGINAL (sem máscara) - usada durante animação
            'foto_com_mascara': todas_fotos_com_mascara[i],  # Foto COM MÁSCARA PRINCIPAL - usada na posição final
            'foto_com_mascara2': todas_fotos_com_mascara2[i],  # Foto COM MÁSCARA SECUNDÁRIA - usada durante pausa
            'x_final': x_final,
            'y_final': y_final,
            'x_origem': x_origem,
            'y_origem': y_origem,
            'direcao': direcao_entrada,
            'angulo_inicial': angulo_inicial,
            'eh_gigante': eh_gigante,
            'em_destaque': em_destaque,
            'tipo': tipo,
            'escala_inicial': escala_inicial,
            'escala_final_gigante': escala_final_gigante,  # Tamanho onde fica 100% opaca
            'nome': Path(lista_imagens[i]).name
        })
    
    # Mantém a ordem natural das posições do mosaico (sem embaralhar)
    
    print(f"   ✅ {len(info_fotos)} fotos configuradas")
    print(f"   ⭐ TODAS as fotos usam ESCALA_DESTAQUE ({ESCALA_DESTAQUE_MIN}x a {ESCALA_DESTAQUE_MAX}x)")
    # [COMENTADO] print(f"   🔥 {num_gigantes} fotos GIGANTES (6x a 10x maiores - ENORMES!)")
    # [COMENTADO] print(f"   ⭐ {num_destaques} fotos em destaque (2.5x a 4x maiores)")
    # [COMENTADO] print(f"   📷 {len(info_fotos) - num_gigantes - num_destaques} fotos normais (0.6x a 1.4x)")
    
    # Divide as fotos em grupos (ondas) de tamanhos aleatórios
    print("\n🌊 Criando ondas de entrada aleatórias...")
    ondas = []
    indice_atual = 0
    
    while indice_atual < len(info_fotos):
        # Define tamanho aleatório da onda (1 a 40 fotos)
        # Pesos: mais chance de grupos médios (5-15)
        pesos = [5, 10, 15, 20, 15, 10, 5]  # Distribuição para 1-5, 6-10, 11-15, 16-20, 21-25, 26-30, 31+
        escolha = random.choices(range(7), weights=pesos)[0]
        
        if escolha == 0:
            tamanho_onda = random.randint(1, 5)
        elif escolha == 1:
            tamanho_onda = random.randint(6, 10)
        elif escolha == 2:
            tamanho_onda = random.randint(11, 15)
        elif escolha == 3:
            tamanho_onda = random.randint(16, 20)
        elif escolha == 4:
            tamanho_onda = random.randint(21, 25)
        elif escolha == 5:
            tamanho_onda = random.randint(26, 30)
        else:
            tamanho_onda = random.randint(31, 40)
        
        # Não ultrapassa o número de fotos restantes
        tamanho_onda = min(tamanho_onda, len(info_fotos) - indice_atual)
        
        onda_atual = info_fotos[indice_atual:indice_atual + tamanho_onda]
        ondas.append(onda_atual)
        
        indice_atual += tamanho_onda
    
    print(f"   ✅ Criadas {len(ondas)} ondas de entrada")
    for i, onda in enumerate(ondas[:10]):  # Mostra as primeiras 10
        print(f"      Onda {i+1}: {len(onda)} fotos")
    if len(ondas) > 10:
        print(f"      ... e mais {len(ondas) - 10} ondas")
    
    print("\n" + "="*60)
    print("PLANEJAMENTO CONCLUÍDO!")
    print("="*60)
    
    # ============================================================
    # FASE 3: GERAÇÃO DO VÍDEO
    # ============================================================
    print("\n" + "="*60)
    print("FASE 3: GERAÇÃO DO VÍDEO")
    print("="*60)
    
    # Cria o vídeo MP4 com codec mp4v (MPEG-4 Part 2 - compatível)
    print("\n🎥 Inicializando gerador de vídeo...")
    print(f"   📁 Arquivo de saída: {nome_saida}")
    print(f"   📁 Resolução: {largura_video}x{altura_video}")
    print(f"   🔧 Usando codec: mp4v (MPEG-4 Part 2 - máxima compatibilidade)")
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video = cv2.VideoWriter(nome_saida, fourcc, FPS, (largura_video, altura_video))
    
    if not video.isOpened():
        print("\n   ❌ ERRO: Não foi possível inicializar o vídeo!")
        print("   💡 Solução: Reinstale o OpenCV com:")
        print("      pip uninstall opencv-python")
        print("      pip install opencv-python")
        return
    
    print(f"   ✅ Vídeo inicializado com sucesso!")
    
    # Frame base cor #f4c866 (RGB: 244, 200, 102)
    frame_base_branco = np.ones((altura_video, largura_video, 3), dtype=np.uint8)
    frame_base_branco[:, :] = [244, 200, 102]  # RGB
    
    print("\n🎞️  Gerando animação com ondas sobrepostas...")
    
    # Calcula o frame de início de cada onda (com delays entre elas)
    frames_por_onda = int(FPS * DURACAO_POR_ONDA)
    delay_frames = int(FPS * DELAY_ENTRE_ONDAS)
    
    ondas_info = []
    for num_onda, onda in enumerate(ondas):
        frame_inicio = num_onda * delay_frames
        frame_fim = frame_inicio + frames_por_onda
        ondas_info.append({
            'onda': onda,
            'frame_inicio': frame_inicio,
            'frame_fim': frame_fim,
            'numero': num_onda + 1
        })
        
        print(f"  🌊 Onda {num_onda + 1}/{len(ondas)}: {len(onda)} fotos")
        print(f"     Inicia no frame {frame_inicio} | Termina no frame {frame_fim}")
    
    # Calcula total de frames necessários
    ultimo_frame = max(info['frame_fim'] for info in ondas_info)
    total_frames = ultimo_frame
    
    print(f"\n  📊 Total de frames de animação: {total_frames} ({total_frames/FPS:.1f} segundos)")
    print(f"  ⏱️  Ondas se sobrepõem com delay de {DELAY_ENTRE_ONDAS}s entre elas")
    
    # Gera todos os frames
    print(f"\n  🎬 Gerando {total_frames} frames...")
    for frame_atual in range(total_frames):
        # Progresso geral
        if frame_atual % 300 == 0:  # A cada 10 segundos
            progresso_geral = (frame_atual / total_frames) * 100
            print(f"     Frame {frame_atual}/{total_frames} ({progresso_geral:.1f}%)")
        
        # Começa com fundo branco
        frame = frame_base_branco.copy()
        
        # Processa cada onda e determina seu estado
        for onda_info in ondas_info:
            if frame_atual < onda_info['frame_inicio']:
                # Onda ainda não começou - não faz nada
                continue
            
            elif frame_atual < onda_info['frame_fim']:
                # Onda está ativa - anima
                frame_local = frame_atual - onda_info['frame_inicio']
                progresso = frame_local / frames_por_onda
                # Easing bem suave (quintic ease-out)
                progresso_suave = 1 - (1 - progresso) ** 5
                
                # Anima todas as fotos desta onda
                for info in onda_info['onda']:
                    # Fotos GIGANTES se movem mais devagar (easing mais suave = movimento mais lento)
                    if info['eh_gigante']:
                        # Usa easing quadrático ao invés de quintic (movimento mais lento e pesado)
                        progresso_foto = 1 - (1 - progresso) ** 2  # Mais lento que fotos normais
                    else:
                        progresso_foto = progresso_suave  # Velocidade normal
                    
                    # Calcula posição atual
                    x_atual = int(info['x_origem'] + (info['x_final'] - info['x_origem']) * progresso_foto)
                    y_atual = int(info['y_origem'] + (info['y_final'] - info['y_origem']) * progresso_foto)
                    
                    # Calcula ângulo atual
                    angulo_atual = info['angulo_inicial'] * (1 - progresso_foto)
                    
                    # Calcula escala atual (vai da escala_inicial para 1.0)
                    escala_atual = info['escala_inicial'] + (1.0 - info['escala_inicial']) * progresso_foto
                    
                    # FADE DE OPACIDADE PARA FOTOS GIGANTES
                    # Começam INVISÍVEIS quando muito grandes, vão ficando VISÍVEIS conforme diminuem
                    if info['eh_gigante']:
                        escala_final_gigante = info['escala_final_gigante']
                        
                        # Calcula opacidade baseada no tamanho atual
                        if escala_atual > escala_final_gigante:
                            # Ainda está maior que o tamanho "gigante" - em processo de fade in
                            # progresso_fade_opacidade: 0 = invisível, 1 = totalmente visível
                            progresso_fade_opacidade = 1 - ((escala_atual - escala_final_gigante) / 
                                                            (info['escala_inicial'] - escala_final_gigante))
                            progresso_fade_opacidade = max(0, min(1, progresso_fade_opacidade))
                        else:
                            # Já atingiu o tamanho gigante final - totalmente visível
                            progresso_fade_opacidade = 1.0
                    else:
                        # Fotos normais e destaque: sempre visíveis (sem fade)
                        progresso_fade_opacidade = 1.0
                    
                    # TRANSIÇÃO DE FOTO: Original → Com Máscara
                    # Durante o movimento (0 a 80%): usa foto original
                    # Nos últimos 20%: faz fade de original para com máscara
                    if progresso_foto < 0.80:
                        # Ainda se movendo: usa foto ORIGINAL (sem máscara)
                        foto_atual = info['foto_original']
                    else:
                        # Chegando na posição final: FADE de original para com máscara
                        # progresso_fade vai de 0 (em 80%) até 1 (em 100%)
                        progresso_fade = (progresso_foto - 0.80) / 0.20
                        # Mistura as duas versões
                        foto_atual = (
                            info['foto_original'] * (1 - progresso_fade) +
                            info['foto_com_mascara'] * progresso_fade
                        ).astype(np.uint8)
                    
                    # Ao encaixar, a foto fica parcialmente transparente
                    # para revelar melhor a imagem de fundo formada pela máscara.
                    if progresso_foto < 0.80:
                        opacidade_encaixe = 1.0
                    else:
                        progresso_transparencia = (progresso_foto - 0.80) / 0.20
                        opacidade_encaixe = 1.0 + (OPACIDADE_FOTO_ENCAIXADA - 1.0) * progresso_transparencia
                    
                    # APLICA FADE DE OPACIDADE (para fotos gigantes que começam invisíveis)
                    if progresso_fade_opacidade < 1.0:
                        # Mistura com fundo cor #f4c866 para criar efeito de transparência/invisibilidade
                        fundo_cor = np.ones_like(foto_atual)
                        fundo_cor[:, :] = [244, 200, 102]  # RGB: #f4c866
                        foto_atual = (
                            foto_atual * progresso_fade_opacidade +
                            fundo_cor * (1 - progresso_fade_opacidade)
                        ).astype(np.uint8)
                    
                    # Desenha a foto com escala variável
                    desenhar_foto_em_posicao(
                        frame, foto_atual,
                        x_atual, y_atual,
                        largura_foto, altura_foto,
                        largura_video, altura_video,
                        angulo=angulo_atual,
                        escala=escala_atual,
                        opacidade=opacidade_encaixe
                    )
            
            else:
                # Onda já terminou - desenha estática na posição final COM MÁSCARA (escala 1.0 = tamanho normal)
                for info in onda_info['onda']:
                    desenhar_foto_em_posicao(
                        frame, info['foto_com_mascara'],  # Usa versão COM MÁSCARA quando estática
                        info['x_final'], info['y_final'],
                        largura_foto, altura_foto,
                        largura_video, altura_video,
                        angulo=0,
                        escala=1.0,
                        respeitar_limites_celula=True,  # Posição final: cada imagem na sua célula!
                        opacidade=OPACIDADE_FOTO_ENCAIXADA
                    )
        
        # Escreve o frame
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        video.write(frame_bgr)
    
    print(f"  ✅ Animação de entrada completa! {len(info_fotos)} fotos no grid")
    
    # Pausa no meio - com transição entre máscaras
    print(f"\n⏸️  Gerando transição final ({DURACAO_PAUSA_MEIO} segundos)...")
    print(f"   4s: Fade Máscara1 → Máscara2 | 3s: Mantém Máscara2 (fim do vídeo)")
    
    total_frames_pausa = int(FPS * DURACAO_PAUSA_MEIO)
    
    # Define as 2 fases da pausa:
    # Fase 1: Fade para máscara2 (4 segundos)
    # Fase 2: Mantém máscara2 até o final (3 segundos quando DURACAO_PAUSA_MEIO=7)
    frames_fade_entrada = int(FPS * 4)  # 4 segundos para o fade
    frames_meio = total_frames_pausa - frames_fade_entrada  # Resto mantém máscara2 (3s)
    
    print(f"   • Fade para máscara2: {frames_fade_entrada / FPS:.1f}s")
    print(f"   • Mantém máscara2 até o final: {frames_meio / FPS:.1f}s")
    print(f"   • O vídeo termina com a Máscara2 aplicada")
    
    frame_pausa_count = 0
    
    for frame_idx in range(total_frames_pausa):
        # Cria frame com cor #f4c866
        frame = np.ones((altura_video, largura_video, 3), dtype=np.uint8)
        frame[:, :] = [244, 200, 102]  # RGB: #f4c866
        
        # Calcula qual fase da pausa estamos
        if frame_idx < frames_fade_entrada:
            # FASE 1: Fade de máscara1 para máscara2 (primeiros 3 segundos)
            progresso_fade = frame_idx / frames_fade_entrada
            
            # Desenha todas as fotos com fade entre máscaras
            for info in info_fotos:
                # Mistura entre máscara1 e máscara2
                foto_atual = (
                    info['foto_com_mascara'] * (1 - progresso_fade) +
                    info['foto_com_mascara2'] * progresso_fade
                ).astype(np.uint8)
                
                desenhar_foto_em_posicao(
                    frame, foto_atual,
                    info['x_final'], info['y_final'],
                    largura_foto, altura_foto,
                    largura_video, altura_video,
                    respeitar_limites_celula=True,  # Grid parado: cada imagem na sua célula!
                    opacidade=OPACIDADE_FOTO_ENCAIXADA
                )
        
        else:
            # FASE 2: Mantém máscara2 até o final do vídeo (10 segundos se DURACAO_PAUSA_MEIO=13)
            for info in info_fotos:
                desenhar_foto_em_posicao(
                    frame, info['foto_com_mascara2'],
                    info['x_final'], info['y_final'],
                    largura_foto, altura_foto,
                    largura_video, altura_video,
                    respeitar_limites_celula=True,  # Grid parado: cada imagem na sua célula!
                    opacidade=OPACIDADE_FOTO_ENCAIXADA
                )
        
        # Escreve frame no vídeo
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        video.write(frame_bgr)
        
        frame_pausa_count += 1
    
    print(f"  ✅ Pausa completa! {frame_pausa_count} frames gerados")
    
    # ============================================================================
    # ANIMAÇÃO DE SAÍDA - COMENTADA A PEDIDO DO USUÁRIO
    # O vídeo agora termina após a pausa (entrada + pausa)
    # ============================================================================
    
    # # ANIMAÇÃO DE SAÍDA - Reverso da entrada
    # print("\n🔙 Gerando animação de saída (retorno)...")
    # print("   As fotos voltam da mesma forma que entraram!")
    
    # # Calcula frames para a saída (mesma lógica da entrada)
    # ondas_saida_info = []
    # for num_onda, onda in enumerate(ondas):
    #     frame_inicio = num_onda * delay_frames
    #     frame_fim = frame_inicio + frames_por_onda
    #     ondas_saida_info.append({
    #         'onda': onda,
    #         'frame_inicio': frame_inicio,
    #         'frame_fim': frame_fim,
    #         'numero': num_onda + 1
    #     })
    #     
    #     print(f"  🌊 Onda {num_onda + 1}/{len(ondas)}: {len(onda)} fotos saindo")
    #     print(f"     Inicia no frame {frame_inicio} | Termina no frame {frame_fim}")
    # 
    # total_frames_saida = max(info['frame_fim'] for info in ondas_saida_info)
    # print(f"\n  📊 Total de frames de saída: {total_frames_saida} ({total_frames_saida/FPS:.1f} segundos)")
    # 
    # # Gera frames de saída
    # print(f"\n  🎬 Gerando {total_frames_saida} frames de saída...")
    # print(f"  ⏱️  Ondas se sobrepõem com delay de {DELAY_ENTRE_ONDAS}s entre elas (igual à entrada)")
    # 
    # for frame_atual in range(total_frames_saida):
    #     # Progresso geral
    #     if frame_atual % 300 == 0:
    #         progresso_geral = (frame_atual / total_frames_saida) * 100
    #         print(f"     Frame {frame_atual}/{total_frames_saida} ({progresso_geral:.1f}%)")
    #     
    #     # Começa com fundo branco
    #     frame = frame_base_branco.copy()
    #     
    #     # Conta ondas ativas para debug
    #     ondas_ativas = 0
    #     fotos_estaticas = 0
    #     fotos_animando = 0
    #     
    #     # Coleta fotos estáticas e animando em listas separadas
    #     fotos_estaticas_lista = []
    #     fotos_animando_lista = []
    #     
    #     # Processa cada onda e determina seu estado
    #     for onda_info in ondas_saida_info:
    #         if frame_atual < onda_info['frame_inicio']:
    #             # Onda ainda não começou a sair - foto DEVE estar estática na posição final
    #             for info in onda_info['onda']:
    #                 fotos_estaticas_lista.append({
    #                     'info': info,
    #                     'x': info['x_final'],
    #                     'y': info['y_final'],
    #                     'angulo': 0,
    #                     'escala': 1.0
    #                 })
    #                 fotos_estaticas += 1
    #         
    #         elif frame_atual < onda_info['frame_fim']:
    #             # Onda está ATIVA - saindo
    #             ondas_ativas += 1
    #             frame_local = frame_atual - onda_info['frame_inicio']
    #             progresso = frame_local / frames_por_onda
    #             # Para saída, usa ease-in (inverso do ease-out) para movimento mais suave
    #             progresso_suave = progresso ** 5  # Ease-in (quintic)
    # ... [CÓDIGO DE ANIMAÇÃO DE SAÍDA COMENTADO] ...
    # 
    # A animação de saída foi comentada a pedido do usuário.
    # O vídeo agora termina após a pausa (entrada + pausa apenas).
    
    # Define total_frames_saida como 0 para compatibilidade com estatísticas
    total_frames_saida = 0
    
    # Finaliza o vídeo corretamente
    print("\n💾 Finalizando e salvando vídeo...")
    print("   ⏳ Aguarde, escrevendo arquivo no disco...")
    
    # Garante que todos os frames foram escritos
    video.release()
    cv2.destroyAllWindows()
    
    # Aguarda um pouco para garantir que o arquivo foi escrito
    import time
    time.sleep(0.5)
    
    # Verifica se o arquivo foi criado
    import os
    if os.path.exists(nome_saida):
        tamanho_mb = os.path.getsize(nome_saida) / (1024 * 1024)
        print(f"   ✅ Vídeo salvo com sucesso!")
        print(f"   📦 Tamanho do arquivo: {tamanho_mb:.1f} MB")
    else:
        print(f"   ❌ ERRO: Arquivo não foi criado!")
    
    duracao_entrada = total_frames / FPS
    duracao_saida = total_frames_saida / FPS
    duracao_total = duracao_entrada + DURACAO_PAUSA_MEIO + duracao_saida
    
    print("\n" + "="*70)
    print(f"✅ VÍDEO CONCLUÍDO: {nome_saida}")
    print("="*70)
    print(f"\n📊 Estatísticas:")
    print(f"   • Resolução: {largura_video}x{altura_video}")
    print(f"   • Duração total: {duracao_total:.1f} segundos ({duracao_total/60:.1f} minutos)")
    print(f"   • Duração da entrada: {duracao_entrada:.1f} segundos")
    print(f"   • Duração da transição final: {DURACAO_PAUSA_MEIO} segundos (4s fade + 3s estático)")
    # Sem saída - vídeo termina na Máscara2
    print(f"   • FPS: {FPS}")
    print(f"   • Total de fotos: {len(lista_imagens)}")
    print(f"   • Total de ondas: {len(ondas)}")
    print(f"   • Duração por onda: {DURACAO_POR_ONDA} segundos")
    print(f"   • Delay entre ondas: {DELAY_ENTRE_ONDAS} segundos (sobreposição)")
    print(f"   • Total de frames: {total_frames + int(FPS * DURACAO_PAUSA_MEIO) + total_frames_saida}")
    print(f"\n🎭 Máscaras aplicadas:")
    print(f"   • Máscara 1 (entrada): {caminho_mascara} ({int(TRANSPARENCIA_MASCARA * 100)}%)")
    print(f"   • Máscara 2 (final): {caminho_mascara2} ({int(TRANSPARENCIA_MASCARA * 100)}%)")
    print(f"\n🔄 Estrutura do vídeo:")
    print(f"   1. Entrada das fotos: {duracao_entrada:.1f}s (Fade: Original → Máscara1)")
    print(f"   2. Transição final: {DURACAO_PAUSA_MEIO}s (Fade: Máscara1 → Máscara2 em 4s + 3s estático)")
    print(f"   3. Vídeo termina com Máscara2 aplicada")
    print("\n" + "="*60)

def gerar_video_por_config(config):
    """Wrapper para gerar um único vídeo a partir de uma config."""
    criar_video_album(
        largura_video=config['largura'],
        altura_video=config['altura'],
        nome_saida=config['nome'],
        caminho_mascara=config['mascara'],
        caminho_mascara2=config['mascara2'],
        tamanho_celula_base=config.get('celula_base', 56)
    )
    return config['nome']


def gerar_todos_os_videos(paralelo=True, nomes_videos=None):
    """Gera todos os vídeos configurados em VIDEOS_PARA_GERAR."""
    videos_para_gerar = VIDEOS_PARA_GERAR
    if nomes_videos:
        nomes_set = set(nomes_videos)
        videos_para_gerar = [cfg for cfg in VIDEOS_PARA_GERAR if cfg["nome"] in nomes_set]
        if not videos_para_gerar:
            print("⚠️ Nenhum vídeo selecionado para geração.")
            return

    print("\n" + "="*80)
    print("GERADOR DE VIDEOS DE ALBUM DE FOTOS")
    print("="*80)
    print(f"\nConfiguracao:")
    print(f"   Total de videos a gerar: {len(videos_para_gerar)}")
    for i, config in enumerate(videos_para_gerar, 1):
        print(f"   {i}. {config['nome']} - {config['largura']}x{config['altura']} - {config['descricao']}")
    print("\n" + "="*80)
    
    if paralelo and len(videos_para_gerar) > 1:
        max_workers = min(len(videos_para_gerar), max(1, multiprocessing.cpu_count() - 1))
        print(f"\n⚙️ Modo paralelo ativado (multiprocessing)")
        print(f"   • Workers: {max_workers}")
        print(f"   • Vídeos serão gerados em paralelo")

        try:
            contexto = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(max_workers=max_workers, mp_context=contexto) as executor:
                futuros = {
                    executor.submit(gerar_video_por_config, config): config
                    for config in videos_para_gerar
                }

                concluidos = 0
                for futuro in as_completed(futuros):
                    config = futuros[futuro]
                    concluidos += 1
                    try:
                        nome = futuro.result()
                        print(f"\n✅ [{concluidos}/{len(videos_para_gerar)}] Concluído: {nome}")
                    except Exception as e:
                        print(f"\n❌ [{concluidos}/{len(videos_para_gerar)}] Falha em {config['nome']}: {e}")
        except Exception as e:
            print(f"\n⚠️ Falha no modo paralelo: {e}")
            print("   Revertendo para geração sequencial...")
            for i, config in enumerate(videos_para_gerar, 1):
                print(f"\n\n{'='*80}")
                print(f"GERANDO VIDEO {i}/{len(videos_para_gerar)}")
                print(f"{'='*80}")
                gerar_video_por_config(config)
    else:
        # Geração sequencial (caso haja um vídeo só, ou paralelo desativado)
        for i, config in enumerate(videos_para_gerar, 1):
            print(f"\n\n{'='*80}")
            print(f"GERANDO VIDEO {i}/{len(videos_para_gerar)}")
            print(f"{'='*80}")
            gerar_video_por_config(config)
    
    print("\n\n" + "="*80)
    print("TODOS OS VIDEOS FORAM GERADOS COM SUCESSO!")
    print("="*80)
    print("\nArquivos gerados:")
    for i, config in enumerate(videos_para_gerar, 1):
        if os.path.exists(config['nome']):
            tamanho_mb = os.path.getsize(config['nome']) / (1024 * 1024)
            print(f"   {i}. OK: {config['nome']} ({tamanho_mb:.1f} MB)")
        else:
            print(f"   {i}. ERRO: {config['nome']} (FALHOU na geracao)")
    print("\n" + "="*80)


if __name__ == "__main__":
    gerar_todos_os_videos()