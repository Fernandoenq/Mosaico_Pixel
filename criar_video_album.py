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
# Para atingir 30s com ~35 ondas: tempo_total = (num_ondas - 1) * DELAY + DURACAO
# 30s = 34 * 0.8 + 2.8 = 27.2 + 2.8 = 30s ✓
DURACAO_POR_ONDA = 2.8  # Segundos que cada onda leva para aparecer/desaparecer
DELAY_ENTRE_ONDAS = 0.8  # Segundos de delay entre início de cada onda (sobreposição)
DURACAO_PAUSA_MEIO = 0  # Sem pausa (vai direto da entrada para saída) - Para 1min total (30s+30s)
TRANSPARENCIA_MASCARA = 0.85  # Transparência da máscara aplicada em cada foto (0.0 = invisível, 1.0 = opaca)

# Configurações de destaque e variação de tamanho (compartilhadas)
NUM_FOTOS_GIGANTES = 100  # Número mínimo de fotos que aparecem GIGANTES na tela

# FOTOS GIGANTES - Efeito especial de entrada
ESCALA_GIGANTE_SUPER_MIN = 15.0  # Escala SUPER inicial - começam MUITO maiores (invisíveis/transparentes)
ESCALA_GIGANTE_SUPER_MAX = 20.0  # Escala SUPER inicial máxima
ESCALA_GIGANTE_MIN = 6.0  # Tamanho gigante FINAL - quando ficam totalmente opacas (600%)
ESCALA_GIGANTE_MAX = 10.0  # Tamanho gigante FINAL máximo (1000%)
# EFEITO: Começam 15x-20x maiores e INVISÍVEIS → vão diminuindo e ficando OPACAS → 
#         quando atingem 6x-10x já estão 100% visíveis → continuam até 1x (tamanho normal)
# NOTA: Fotos gigantes se movem MAIS DEVAGAR (easing quadrático vs quintic) criando efeito de "peso"

PORCENTAGEM_DESTAQUE = 0.5  # 12% das fotos aparecem em destaque (maiores)
ESCALA_MINIMA = 5.6  # Fotos normais podem entrar com 60% do tamanho
ESCALA_MAXIMA = 6.0  # Fotos normais podem entrar com 160% do tamanho
ESCALA_DESTAQUE_MIN = 6.5  # Fotos em destaque entram com 250% do tamanho
ESCALA_DESTAQUE_MAX = 7.0  # Fotos em destaque entram com até 400% do tamanho

# CONFIGURAÇÕES DOS VÍDEOS A GERAR
# O script irá gerar TODOS os vídeos listados abaixo
# NOTA: A resolução 6384x1344 causa erro 0xC00D36B4 (incompatível com codec mp4v)
#       Por isso usamos 3192x672 (50% da original) que funciona perfeitamente
# CADA VÍDEO USA SUA PRÓPRIA MÁSCARA (já no tamanho correto!)
VIDEOS_PARA_GERAR = [
    {
        'nome': 'Mosaico_Pixel_6k.mp4',
        'largura': 3192,  # 50% de 6384 (resolução compatível)
        'altura': 672,    # 50% de 1344 (resolução compatível)
        'descricao': 'Video em alta resolucao (50% da original 6384x1344)',
        'mascara': 'fundoalto.png'  # Máscara específica para alta resolução (3192x672)
    },
    {
        'nome': 'Mosaico_Pixel_2k.mp4',
        'largura': 1680,
        'altura': 1176,
        'descricao': 'Video em resolucao alternativa',
        'mascara': 'fundobaixo.png'  # Máscara específica para resolução alternativa (1680x1176)
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

def calcular_posicao_origem(x_final, y_final, largura_foto, altura_foto, largura_video, altura_video, direcao):
    """Calcula a posição de origem da foto baseada na direção de entrada"""
    if direcao == 0:  # Esquerda
        return -largura_foto, y_final
    elif direcao == 1:  # Direita
        return largura_video, y_final
    elif direcao == 2:  # Cima
        return x_final, -altura_foto
    elif direcao == 3:  # Baixo
        return x_final, altura_video
    elif direcao == 4:  # Diagonal superior esquerda
        return -largura_foto, -altura_foto
    elif direcao == 5:  # Diagonal superior direita
        return largura_video, -altura_foto
    elif direcao == 6:  # Diagonal inferior esquerda
        return -largura_foto, altura_video
    else:  # direcao == 7: Diagonal inferior direita
        return largura_video, altura_video

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
    
    # Aplica a rotação com fundo branco
    imagem_rotacionada = cv2.warpAffine(imagem, matriz_rotacao, (nova_largura, nova_altura),
                                        borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    
    return imagem_rotacionada, nova_largura, nova_altura

def desenhar_foto_em_posicao(frame, foto, x, y, largura_foto, altura_foto, largura_video, altura_video, angulo=0, escala=1.0):
    """Desenha a foto no frame, com rotação e escala opcionais"""
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
        # Sobrepõe apenas pixels não-brancos se houver rotação
        if angulo != 0:
            regiao = frame[y_dst_start:y_dst_end, x_dst_start:x_dst_end]
            foto_regiao = foto_atual[y_src_start:y_src_end, x_src_start:x_src_end]
            
            # Cria máscara para pixels não-brancos
            mascara = np.any(foto_regiao < 250, axis=2)
            regiao[mascara] = foto_regiao[mascara]
        else:
            frame[y_dst_start:y_dst_end, x_dst_start:x_dst_end] = \
                foto_atual[y_src_start:y_src_end, x_src_start:x_src_end]
        
        # Adiciona borda apenas se estiver sem rotação e dentro dos limites
        if angulo == 0 and x >= 0 and y >= 0 and x + largura_foto <= largura_video and y + altura_foto <= altura_video:
            cv2.rectangle(frame, (x-1, y-1), (x+largura_foto+1, y+altura_foto+1), 
                        (220, 220, 220), 1)

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

def criar_video_album(largura_video, altura_video, nome_saida, caminho_mascara):
    """Cria o vídeo com efeito de álbum de fotos - todas as fotos em um único grid
    
    Args:
        largura_video: Largura do vídeo em pixels
        altura_video: Altura do vídeo em pixels
        nome_saida: Nome do arquivo de vídeo a ser gerado
        caminho_mascara: Caminho para o arquivo de máscara (fundo) específico desta resolução
    """
    
    # Calcula configurações específicas para esta resolução
    # Grid com células QUADRADAS que PREENCHEM COMPLETAMENTE o vídeo
    # TAMANHO_CELULA_BASE reduzido para DOBRAR a quantidade de imagens!
    # 56px = células menores = mais imagens (aprox. 2x mais que 84px)
    TAMANHO_CELULA_BASE = 56  # Reduzido de 168 para ter ~2x mais imagens
    
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
    
    # Carrega a máscara completa (já no tamanho correto para esta resolução!)
    print(f"\n🎭 Carregando máscara de fundo: {caminho_mascara}")
    print(f"   • Resolução esperada: {largura_video}x{altura_video}")
    mascara_completa = carregar_mascara(caminho_mascara, largura_video, altura_video)
    if mascara_completa is not None:
        print(f"   ✅ Máscara carregada com sucesso")
        print(f"   • Transparência: {int(TRANSPARENCIA_MASCARA * 100)}%")
        print(f"   • A máscara será dividida em {len(lista_imagens)} regiões")
    
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
    
    # Processa todas as fotos: carrega + redimensiona + cria 2 versões (original e com máscara)
    print(f"\n🖼️  Processando todas as imagens...")
    print(f"   (Carregando, redimensionando e criando 2 versoes: original e com mascara)")
    
    todas_fotos_originais = []  # Fotos originais (sem máscara)
    todas_fotos_com_mascara = []  # Fotos com máscara aplicada
    
    for i, caminho_imagem in enumerate(lista_imagens):
        nome_foto = Path(caminho_imagem).name
        x, y = todas_posicoes[i]
        
        print(f"   [{i + 1}/{len(lista_imagens)}] {nome_foto}")
        
        # Carrega e redimensiona a foto ORIGINAL
        foto_original = carregar_e_redimensionar(caminho_imagem, largura_foto, altura_foto)
        
        # Extrai a região específica da máscara para esta posição
        regiao_mascara = extrair_regiao_mascara(mascara_completa, x, y, largura_foto, altura_foto)
        
        # Aplica a máscara na foto (cria a versão com máscara)
        foto_com_mascara = aplicar_mascara_na_foto(foto_original, regiao_mascara, TRANSPARENCIA_MASCARA)
        
        todas_fotos_originais.append(foto_original)
        todas_fotos_com_mascara.append(foto_com_mascara)
    
    print(f"\n   ✅ {len(todas_fotos_originais)} imagens processadas!")
    print(f"   • Versao original (sem mascara): para animacao de entrada/saida")
    print(f"   • Versao com mascara (fundo.jpg aplicado): para estado final")
    
    # Gera imagem de resultado final (preview)
    print(f"\n🖼️  Gerando preview do resultado final...")
    frame_final = np.ones((altura_video, largura_video, 3), dtype=np.uint8) * 255
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
    
    # Define quantas fotos serão GIGANTES (mínimo 5)
    num_gigantes = max(NUM_FOTOS_GIGANTES, int(len(todas_fotos_com_mascara) * 0.02))  # Mínimo 5 ou 2%
    indices_gigantes = random.sample(range(len(todas_fotos_com_mascara)), num_gigantes)
    
    # Define quantas fotos serão destacadas (excluindo as gigantes)
    indices_disponiveis = [i for i in range(len(todas_fotos_com_mascara)) if i not in indices_gigantes]
    num_destaques = min(int(len(todas_fotos_com_mascara) * PORCENTAGEM_DESTAQUE), len(indices_disponiveis))
    indices_destaque = random.sample(indices_disponiveis, num_destaques)
    
    for i in range(len(todas_fotos_com_mascara)):
        direcao_entrada = random.randint(0, 7)  # 8 direções possíveis
        x_final, y_final = todas_posicoes[i]
        x_origem, y_origem = calcular_posicao_origem(
            x_final, y_final, largura_foto, altura_foto, 
            largura_video, altura_video, direcao_entrada
        )
        
        # Ângulo de rotação inicial (entre -45 e 45 graus)
        angulo_inicial = random.uniform(-45, 45)
        
        # Define se esta foto é GIGANTE, destaque ou normal
        eh_gigante = i in indices_gigantes
        em_destaque = i in indices_destaque
        
        # Define a escala inicial baseado na categoria
        if eh_gigante:
            # Fotos GIGANTES: começam SUPER grandes (15-20x) e INVISÍVEIS
            escala_super_inicial = random.uniform(ESCALA_GIGANTE_SUPER_MIN, ESCALA_GIGANTE_SUPER_MAX)
            escala_final_gigante = random.uniform(ESCALA_GIGANTE_MIN, ESCALA_GIGANTE_MAX)  # Tamanho quando ficam opacas (6-10x)
            escala_inicial = escala_super_inicial  # Usa a super escala como ponto de partida
            tipo = 'gigante'
        elif em_destaque:
            escala_inicial = random.uniform(ESCALA_DESTAQUE_MIN, ESCALA_DESTAQUE_MAX)
            escala_final_gigante = 1.0  # Não é gigante
            tipo = 'destaque'
        else:
            escala_inicial = random.uniform(ESCALA_MINIMA, ESCALA_MAXIMA)
            escala_final_gigante = 1.0  # Não é gigante
            tipo = 'normal'
        
        info_fotos.append({
            'indice': i,
            'foto_original': todas_fotos_originais[i],  # Foto ORIGINAL (sem máscara) - usada durante animação
            'foto_com_mascara': todas_fotos_com_mascara[i],  # Foto COM MÁSCARA - usada na posição final
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
    
    # Randomiza a ordem de entrada
    random.shuffle(info_fotos)
    
    print(f"   ✅ {len(info_fotos)} fotos configuradas")
    print(f"   🔥 {num_gigantes} fotos GIGANTES (6x a 10x maiores - ENORMES!)")
    print(f"   ⭐ {num_destaques} fotos em destaque (2.5x a 4x maiores)")
    print(f"   📷 {len(info_fotos) - num_gigantes - num_destaques} fotos normais (0.6x a 1.4x)")
    
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
    
    # Frame base branco puro
    frame_base_branco = np.ones((altura_video, largura_video, 3), dtype=np.uint8) * 255
    
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
                    
                    # APLICA FADE DE OPACIDADE (para fotos gigantes que começam invisíveis)
                    if progresso_fade_opacidade < 1.0:
                        # Mistura com fundo branco para criar efeito de transparência/invisibilidade
                        fundo_branco = np.ones_like(foto_atual) * 255
                        foto_atual = (
                            foto_atual * progresso_fade_opacidade +
                            fundo_branco * (1 - progresso_fade_opacidade)
                        ).astype(np.uint8)
                    
                    # Desenha a foto com escala variável
                    desenhar_foto_em_posicao(
                        frame, foto_atual,
                        x_atual, y_atual,
                        largura_foto, altura_foto,
                        largura_video, altura_video,
                        angulo=angulo_atual,
                        escala=escala_atual
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
                        escala=1.0
                    )
        
        # Escreve o frame
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        video.write(frame_bgr)
    
    print(f"  ✅ Animação de entrada completa! {len(info_fotos)} fotos no grid")
    
    # Pausa no meio - todas as fotos visíveis
    print(f"\n⏸️  Gerando pausa do meio ({DURACAO_PAUSA_MEIO} segundos)...")
    print(f"   Todas as fotos estáticas...")
    
    for _ in range(int(FPS * DURACAO_PAUSA_MEIO)):
        frame_bgr = cv2.cvtColor(frame_final, cv2.COLOR_RGB2BGR)
        video.write(frame_bgr)
    
    # ANIMAÇÃO DE SAÍDA - Reverso da entrada
    print("\n🔙 Gerando animação de saída (retorno)...")
    print("   As fotos voltam da mesma forma que entraram!")
    
    # Calcula frames para a saída (mesma lógica da entrada)
    ondas_saida_info = []
    for num_onda, onda in enumerate(ondas):
        frame_inicio = num_onda * delay_frames
        frame_fim = frame_inicio + frames_por_onda
        ondas_saida_info.append({
            'onda': onda,
            'frame_inicio': frame_inicio,
            'frame_fim': frame_fim,
            'numero': num_onda + 1
        })
        
        print(f"  🌊 Onda {num_onda + 1}/{len(ondas)}: {len(onda)} fotos saindo")
        print(f"     Inicia no frame {frame_inicio} | Termina no frame {frame_fim}")
    
    total_frames_saida = max(info['frame_fim'] for info in ondas_saida_info)
    print(f"\n  📊 Total de frames de saída: {total_frames_saida} ({total_frames_saida/FPS:.1f} segundos)")
    
    # Gera frames de saída
    print(f"\n  🎬 Gerando {total_frames_saida} frames de saída...")
    print(f"  ⏱️  Ondas se sobrepõem com delay de {DELAY_ENTRE_ONDAS}s entre elas (igual à entrada)")
    
    for frame_atual in range(total_frames_saida):
        # Progresso geral
        if frame_atual % 300 == 0:
            progresso_geral = (frame_atual / total_frames_saida) * 100
            print(f"     Frame {frame_atual}/{total_frames_saida} ({progresso_geral:.1f}%)")
        
        # Começa com fundo branco
        frame = frame_base_branco.copy()
        
        # Conta ondas ativas para debug
        ondas_ativas = 0
        fotos_estaticas = 0
        fotos_animando = 0
        
        # Coleta fotos estáticas e animando em listas separadas
        fotos_estaticas_lista = []
        fotos_animando_lista = []
        
        # Processa cada onda e determina seu estado
        for onda_info in ondas_saida_info:
            if frame_atual < onda_info['frame_inicio']:
                # Onda ainda não começou a sair - foto DEVE estar estática na posição final
                for info in onda_info['onda']:
                    fotos_estaticas_lista.append({
                        'info': info,
                        'x': info['x_final'],
                        'y': info['y_final'],
                        'angulo': 0,
                        'escala': 1.0
                    })
                    fotos_estaticas += 1
            
            elif frame_atual < onda_info['frame_fim']:
                # Onda está ATIVA - saindo
                ondas_ativas += 1
                frame_local = frame_atual - onda_info['frame_inicio']
                progresso = frame_local / frames_por_onda
                # Para saída, usa ease-in (inverso do ease-out) para movimento mais suave
                progresso_suave = progresso ** 5  # Ease-in (quintic)
                
                # Anima todas as fotos desta onda (movimento reverso)
                for info in onda_info['onda']:
                    # Fotos GIGANTES se movem mais devagar na saída também
                    if info['eh_gigante']:
                        progresso_foto = progresso ** 2  # Mais lento que fotos normais
                    else:
                        progresso_foto = progresso_suave  # Velocidade normal
                    
                    # Posição reversa: vai da posição final para a origem
                    x_atual = int(info['x_final'] + (info['x_origem'] - info['x_final']) * progresso_foto)
                    y_atual = int(info['y_final'] + (info['y_origem'] - info['y_final']) * progresso_foto)
                    
                    # Ângulo reverso: vai de 0 para o angulo_inicial
                    angulo_atual = info['angulo_inicial'] * progresso_foto
                    
                    # Escala reversa: vai de 1.0 para a escala_inicial
                    escala_atual = 1.0 + (info['escala_inicial'] - 1.0) * progresso_foto
                    
                    # FADE DE OPACIDADE PARA FOTOS GIGANTES (REVERSO)
                    # Começam VISÍVEIS, vão ficando INVISÍVEIS conforme aumentam de tamanho
                    if info['eh_gigante']:
                        escala_final_gigante = info['escala_final_gigante']
                        
                        # Calcula opacidade baseada no tamanho atual (reverso da entrada)
                        if escala_atual > escala_final_gigante:
                            # Já está maior que o tamanho "gigante" - em processo de fade out
                            # progresso_fade_opacidade: 1 = visível, 0 = invisível
                            progresso_fade_opacidade = 1 - ((escala_atual - escala_final_gigante) / 
                                                            (info['escala_inicial'] - escala_final_gigante))
                            progresso_fade_opacidade = max(0, min(1, progresso_fade_opacidade))
                        else:
                            # Ainda não passou do tamanho gigante - totalmente visível
                            progresso_fade_opacidade = 1.0
                    else:
                        # Fotos normais e destaque: sempre visíveis (sem fade)
                        progresso_fade_opacidade = 1.0
                    
                    # TRANSIÇÃO DE FOTO NA SAÍDA: Com Máscara → Original
                    # Nos primeiros 20%: faz fade de com máscara para original
                    # Depois (20% a 100%): usa foto original
                    if progresso_foto < 0.20:
                        # Começando a sair: FADE de com máscara para original
                        # progresso_fade vai de 0 (em 0%) até 1 (em 20%)
                        progresso_fade = progresso_foto / 0.20
                        # Mistura as duas versões (inverso da entrada)
                        foto_atual = (
                            info['foto_com_mascara'] * (1 - progresso_fade) +
                            info['foto_original'] * progresso_fade
                        ).astype(np.uint8)
                    else:
                        # Já saindo: usa foto ORIGINAL (sem máscara)
                        foto_atual = info['foto_original']
                    
                    # APLICA FADE DE OPACIDADE (para fotos gigantes que vão ficando invisíveis)
                    if progresso_fade_opacidade < 1.0:
                        # Mistura com fundo branco para criar efeito de transparência/invisibilidade
                        fundo_branco = np.ones_like(foto_atual) * 255
                        foto_atual = (
                            foto_atual * progresso_fade_opacidade +
                            fundo_branco * (1 - progresso_fade_opacidade)
                        ).astype(np.uint8)
                    
                    # Adiciona à lista de fotos animando com seu progresso
                    fotos_animando_lista.append({
                        'info': info,
                        'foto': foto_atual,  # Foto com fade aplicado
                        'x': x_atual,
                        'y': y_atual,
                        'angulo': angulo_atual,
                        'escala': escala_atual,
                        'progresso': progresso_foto  # Para ordenar depois
                    })
                    fotos_animando += 1
            
            # else: onda já terminou de sair - não desenha (foto já saiu)
        
        # CAMADAS INVERTIDAS NA SAÍDA:
        # Garante que fotos saindo ficam POR CIMA das estáticas
        
        # 1. CAMADA INFERIOR: Todas as fotos ESTÁTICAS (não saindo ainda)
        #    Usam versão COM MÁSCARA pois estão na posição final
        for foto_data in fotos_estaticas_lista:
            desenhar_foto_em_posicao(
                frame, foto_data['info']['foto_com_mascara'],  # COM MÁSCARA quando estática
                foto_data['x'], foto_data['y'],
                largura_foto, altura_foto,
                largura_video, altura_video,
                angulo=0,
                escala=1.0
            )
        
        # 2. CAMADAS SUPERIORES: Todas as fotos ANIMANDO (saindo)
        #    Usam versão calculada com FADE (com máscara → original)
        #    Ordenadas por progresso INVERSO para criar profundidade
        #    MAIOR progresso = desenhada POR ÚLTIMO = fica mais POR CIMA
        fotos_animando_lista.sort(key=lambda x: x['progresso'], reverse=False)
        
        for foto_data in fotos_animando_lista:
            desenhar_foto_em_posicao(
                frame, foto_data['foto'],  # Usa foto com fade já aplicado
                foto_data['x'], foto_data['y'],
                largura_foto, altura_foto,
                largura_video, altura_video,
                angulo=foto_data['angulo'],
                escala=foto_data['escala']
            )
        
        # Debug a cada 5 segundos
        if frame_atual % 150 == 0 and frame_atual > 0:
            print(f"       Debug: {fotos_estaticas} estáticas (por baixo), {fotos_animando} animando (POR CIMA), {ondas_ativas} ondas ativas")
            if fotos_animando > 0:
                # Mostra as primeiras fotos animando para debug
                print(f"       Ordem de desenho: estáticas primeiro, depois {len(fotos_animando_lista)} fotos saindo por cima")
        
        # Escreve o frame
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        video.write(frame_bgr)
    
    print(f"  ✅ Animação de saída completa!")
    
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
    print(f"   • Duração da pausa: {DURACAO_PAUSA_MEIO} segundos")
    print(f"   • Duração da saída: {duracao_saida:.1f} segundos")
    print(f"   • FPS: {FPS}")
    print(f"   • Total de fotos: {len(lista_imagens)}")
    print(f"   • Total de ondas: {len(ondas)}")
    print(f"   • Duração por onda: {DURACAO_POR_ONDA} segundos")
    print(f"   • Delay entre ondas: {DELAY_ENTRE_ONDAS} segundos (sobreposição)")
    print(f"   • Total de frames: {total_frames + int(FPS * DURACAO_PAUSA_MEIO) + total_frames_saida}")
    print(f"\n🎭 Máscara aplicada: {caminho_mascara} ({int(TRANSPARENCIA_MASCARA * 100)}%)")
    print(f"\n🔄 Estrutura do vídeo:")
    print(f"   1. Entrada das fotos: {duracao_entrada:.1f}s")
    print(f"   2. Pausa (todas visíveis): {DURACAO_PAUSA_MEIO}s")
    print(f"   3. Saída das fotos: {duracao_saida:.1f}s")
    print("\n" + "="*60)

if __name__ == "__main__":
    print("\n" + "="*80)
    print("GERADOR DE VIDEOS DE ALBUM DE FOTOS")
    print("="*80)
    print(f"\nConfiguracao:")
    print(f"   Total de videos a gerar: {len(VIDEOS_PARA_GERAR)}")
    for i, config in enumerate(VIDEOS_PARA_GERAR, 1):
        print(f"   {i}. {config['nome']} - {config['largura']}x{config['altura']} - {config['descricao']}")
    print("\n" + "="*80)
    
    # Gera cada vídeo configurado
    for i, config in enumerate(VIDEOS_PARA_GERAR, 1):
        print(f"\n\n{'='*80}")
        print(f"GERANDO VIDEO {i}/{len(VIDEOS_PARA_GERAR)}")
        print(f"{'='*80}")
        
        criar_video_album(
            largura_video=config['largura'],
            altura_video=config['altura'],
            nome_saida=config['nome'],
            caminho_mascara=config['mascara']
        )
    
    print("\n\n" + "="*80)
    print("TODOS OS VIDEOS FORAM GERADOS COM SUCESSO!")
    print("="*80)
    print("\nArquivos gerados:")
    for i, config in enumerate(VIDEOS_PARA_GERAR, 1):
        if os.path.exists(config['nome']):
            tamanho_mb = os.path.getsize(config['nome']) / (1024 * 1024)
            print(f"   {i}. OK: {config['nome']} ({tamanho_mb:.1f} MB)")
        else:
            print(f"   {i}. ERRO: {config['nome']} (FALHOU na geracao)")
    print("\n" + "="*80)

