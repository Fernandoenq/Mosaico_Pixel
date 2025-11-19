#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para criar um vídeo de álbum de fotos com animação dinâmica super caótica!

Características:
- Todas as fotos da pasta MOSAIC aparecem em um único grid
- ONDAS SOBREPOSTAS: antes de uma onda terminar, a próxima já começa
  * Delay de 0.8s entre ondas cria movimento fluido e contínuo
  * Múltiplas fotos entram ao mesmo tempo (1 a 40 por onda)
- Entrada TOTALMENTE ALEATÓRIA: 
  * Grupos variados (às vezes 1 foto sozinha, às vezes 30 juntas)
  * Ordem completamente randomizada
- DIREÇÕES VARIADAS: cada foto vem de um canto/lado diferente
  (esquerda, direita, cima, baixo, ou diagonais)
- ROTAÇÃO DINÂMICA: fotos entram tortas (até ±45°) e vão se endireitando
- ANIMAÇÃO BEM LENTA E SUAVE: movimento com easing quintic ease-out (4.0s por onda)
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

# Configurações
PASTA_IMAGENS = "MOSAIC"
FOTO_MASCARA = "fundo.jpg"  # Imagem usada como máscara semi-transparente
VIDEO_SAIDA = "album_fotos.mp4"
LARGURA_VIDEO = 3840  # 4K para caber todas as fotos
ALTURA_VIDEO = 2160
FPS = 30
FOTOS_POR_LINHA = 15  # Número de fotos por linha no grid
FOTOS_POR_COLUNA = 12  # Número de fotos por coluna no grid
DURACAO_POR_ONDA = 4.0  # Segundos que cada onda leva para aparecer/desaparecer (bem mais lento e suave)
DELAY_ENTRE_ONDAS = 0.8  # Segundos de delay entre início de cada onda (sobreposição)
DURACAO_PAUSA_MEIO = 3  # Segundos mostrando todas as fotos antes de começar a saída
TRANSPARENCIA_MASCARA = 0.70  # Transparência da máscara aplicada em cada foto (0.0 = invisível, 1.0 = opaca)

def carregar_e_redimensionar(caminho_imagem, largura, altura):
    """Carrega e redimensiona uma imagem mantendo a proporção"""
    try:
        # Tenta abrir a imagem
        img = Image.open(caminho_imagem)
        
        # Converte para RGB se necessário
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Redimensiona mantendo a proporção
        img.thumbnail((largura, altura), Image.Resampling.LANCZOS)
        
        # Cria um fundo branco do tamanho desejado
        nova_img = Image.new('RGB', (largura, altura), (255, 255, 255))
        
        # Centraliza a imagem
        x = (largura - img.width) // 2
        y = (altura - img.height) // 2
        nova_img.paste(img, (x, y))
        
        return np.array(nova_img)
    except Exception as e:
        print(f"Erro ao carregar {caminho_imagem}: {e}")
        # Retorna uma imagem branca em caso de erro
        return np.ones((altura, largura, 3), dtype=np.uint8) * 255

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

def desenhar_foto_em_posicao(frame, foto, x, y, largura_foto, altura_foto, largura_video, altura_video, angulo=0):
    """Desenha a foto no frame, com rotação opcional"""
    if angulo != 0:
        # Rotaciona a foto
        foto_rotacionada, nova_largura, nova_altura = rotacionar_imagem(
            foto, angulo, largura_foto // 2, altura_foto // 2
        )
        
        # Ajusta a posição para manter o centro
        x_ajustado = x - (nova_largura - largura_foto) // 2
        y_ajustado = y - (nova_altura - altura_foto) // 2
        
        largura_atual = nova_largura
        altura_atual = nova_altura
        foto_atual = foto_rotacionada
        x_atual = x_ajustado
        y_atual = y_ajustado
    else:
        foto_atual = foto
        x_atual = x
        y_atual = y
        largura_atual = largura_foto
        altura_atual = altura_foto
    
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

def criar_video_album():
    """Cria o vídeo com efeito de álbum de fotos - todas as fotos em um único grid"""
    print("🎬 Iniciando criação do vídeo de álbum de fotos...")
    print("📐 Todas as fotos aparecerão em um único grid!")
    
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
    
    # Calcula dimensões de cada foto no grid
    margem = 10
    largura_foto = (LARGURA_VIDEO - (FOTOS_POR_LINHA + 1) * margem) // FOTOS_POR_LINHA
    altura_foto = (ALTURA_VIDEO - (FOTOS_POR_COLUNA + 1) * margem) // FOTOS_POR_COLUNA
    
    total_posicoes = FOTOS_POR_LINHA * FOTOS_POR_COLUNA
    
    print(f"\n📏 Configuração do Grid:")
    print(f"   • Resolução do vídeo: {LARGURA_VIDEO}x{ALTURA_VIDEO}")
    print(f"   • Grid: {FOTOS_POR_LINHA}x{FOTOS_POR_COLUNA} = {total_posicoes} posições")
    print(f"   • Tamanho de cada foto: {largura_foto}x{altura_foto} pixels")
    
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
    
    # Carrega a máscara completa
    print(f"\n🎭 Carregando máscara de fundo: {FOTO_MASCARA}")
    mascara_completa = carregar_mascara(FOTO_MASCARA, LARGURA_VIDEO, ALTURA_VIDEO)
    if mascara_completa is not None:
        print(f"   ✅ Máscara carregada com sucesso")
        print(f"   • Transparência: {int(TRANSPARENCIA_MASCARA * 100)}%")
        print(f"   • A máscara será dividida em {len(lista_imagens)} regiões")
    
    # Calcula posições finais de todas as fotos no grid
    print(f"\n📐 Calculando posições finais no grid...")
    todas_posicoes = []
    indice = 0
    for linha in range(FOTOS_POR_COLUNA):
        for coluna in range(FOTOS_POR_LINHA):
            if indice >= len(lista_imagens):
                break
            x = margem + coluna * (largura_foto + margem)
            y = margem + linha * (altura_foto + margem)
            todas_posicoes.append((x, y))
            indice += 1
        if indice >= len(lista_imagens):
            break
    
    print(f"   ✅ {len(todas_posicoes)} posições calculadas")
    
    # Processa todas as fotos: carrega + redimensiona + aplica máscara
    print(f"\n🖼️  Processando todas as imagens...")
    print(f"   (Carregando, redimensionando e aplicando máscara)")
    
    todas_fotos_com_mascara = []  # Fotos finais prontas para o vídeo
    
    for i, caminho_imagem in enumerate(lista_imagens):
        nome_foto = Path(caminho_imagem).name
        x, y = todas_posicoes[i]
        
        print(f"   [{i + 1}/{len(lista_imagens)}] {nome_foto}")
        
        # Carrega e redimensiona a foto
        foto = carregar_e_redimensionar(caminho_imagem, largura_foto, altura_foto)
        
        # Extrai a região específica da máscara para esta posição
        regiao_mascara = extrair_regiao_mascara(mascara_completa, x, y, largura_foto, altura_foto)
        
        # Aplica a máscara na foto (cria a imagem final)
        foto_final = aplicar_mascara_na_foto(foto, regiao_mascara, TRANSPARENCIA_MASCARA)
        
        todas_fotos_com_mascara.append(foto_final)
    
    print(f"\n   ✅ {len(todas_fotos_com_mascara)} imagens processadas e prontas!")
    print(f"   • Todas as fotos já têm o efeito do fundo.jpg aplicado")
    
    # Gera imagem de resultado final (preview)
    print(f"\n🖼️  Gerando preview do resultado final...")
    frame_final = np.ones((ALTURA_VIDEO, LARGURA_VIDEO, 3), dtype=np.uint8) * 255
    for i, (foto, (x, y)) in enumerate(zip(todas_fotos_com_mascara, todas_posicoes)):
        desenhar_foto_em_posicao(
            frame_final, foto, x, y,
            largura_foto, altura_foto,
            LARGURA_VIDEO, ALTURA_VIDEO
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
    print("\n🎲 Definindo ordem e direções de entrada...")
    info_fotos = []
    for i in range(len(todas_fotos_com_mascara)):
        direcao_entrada = random.randint(0, 7)  # 8 direções possíveis
        x_final, y_final = todas_posicoes[i]
        x_origem, y_origem = calcular_posicao_origem(
            x_final, y_final, largura_foto, altura_foto, 
            LARGURA_VIDEO, ALTURA_VIDEO, direcao_entrada
        )
        
        # Ângulo de rotação inicial (entre -45 e 45 graus)
        angulo_inicial = random.uniform(-45, 45)
        
        info_fotos.append({
            'indice': i,
            'foto': todas_fotos_com_mascara[i],  # Foto já processada com máscara
            'x_final': x_final,
            'y_final': y_final,
            'x_origem': x_origem,
            'y_origem': y_origem,
            'direcao': direcao_entrada,
            'angulo_inicial': angulo_inicial,
            'nome': Path(lista_imagens[i]).name
        })
    
    # Randomiza a ordem de entrada
    random.shuffle(info_fotos)
    
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
    
    # Cria o vídeo
    print("\n🎥 Inicializando gerador de vídeo...")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video = cv2.VideoWriter(VIDEO_SAIDA, fourcc, FPS, (LARGURA_VIDEO, ALTURA_VIDEO))
    print(f"   ✅ Vídeo inicializado: {VIDEO_SAIDA}")
    
    # Frame base branco puro
    frame_base_branco = np.ones((ALTURA_VIDEO, LARGURA_VIDEO, 3), dtype=np.uint8) * 255
    
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
                    # Calcula posição atual
                    x_atual = int(info['x_origem'] + (info['x_final'] - info['x_origem']) * progresso_suave)
                    y_atual = int(info['y_origem'] + (info['y_final'] - info['y_origem']) * progresso_suave)
                    
                    # Calcula ângulo atual
                    angulo_atual = info['angulo_inicial'] * (1 - progresso_suave)
                    
                    # Aplica fade
                    foto_com_fade = (info['foto'] * progresso + 255 * (1 - progresso)).astype(np.uint8)
                    
                    # Desenha a foto
                    desenhar_foto_em_posicao(
                        frame, foto_com_fade,
                        x_atual, y_atual,
                        largura_foto, altura_foto,
                        LARGURA_VIDEO, ALTURA_VIDEO,
                        angulo=angulo_atual
                    )
            
            else:
                # Onda já terminou - desenha estática na posição final
                for info in onda_info['onda']:
                    desenhar_foto_em_posicao(
                        frame, info['foto'],
                        info['x_final'], info['y_final'],
                        largura_foto, altura_foto,
                        LARGURA_VIDEO, ALTURA_VIDEO,
                        angulo=0
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
        
        # Processa cada onda e determina seu estado (EXATAMENTE como na entrada, mas invertido)
        for onda_info in ondas_saida_info:
            if frame_atual < onda_info['frame_inicio']:
                # Onda ainda não começou a sair - foto DEVE estar estática na posição final
                for info in onda_info['onda']:
                    desenhar_foto_em_posicao(
                        frame, info['foto'],
                        info['x_final'], info['y_final'],
                        largura_foto, altura_foto,
                        LARGURA_VIDEO, ALTURA_VIDEO,
                        angulo=0
                    )
                    fotos_estaticas += 1
            
            elif frame_atual < onda_info['frame_fim']:
                # Onda está ATIVA - saindo
                ondas_ativas += 1
                frame_local = frame_atual - onda_info['frame_inicio']
                progresso = frame_local / frames_por_onda
                # Para saída, usa ease-in (inverso do ease-out) para movimento mais suave
                # Isso faz a foto começar devagar e acelerar gradualmente
                progresso_suave = progresso ** 5  # Ease-in (quintic)
                
                # Anima todas as fotos desta onda (movimento reverso)
                for info in onda_info['onda']:
                    # Posição reversa: vai da posição final para a origem
                    x_atual = int(info['x_final'] + (info['x_origem'] - info['x_final']) * progresso_suave)
                    y_atual = int(info['y_final'] + (info['y_origem'] - info['y_final']) * progresso_suave)
                    
                    # Ângulo reverso: vai de 0 para o angulo_inicial (mesma progressão)
                    angulo_atual = info['angulo_inicial'] * progresso_suave
                    
                    # Fade reverso: vai de opaco para transparente (progressão suave também)
                    foto_com_fade = (info['foto'] * (1 - progresso_suave) + 255 * progresso_suave).astype(np.uint8)
                    
                    # Desenha a foto
                    desenhar_foto_em_posicao(
                        frame, foto_com_fade,
                        x_atual, y_atual,
                        largura_foto, altura_foto,
                        LARGURA_VIDEO, ALTURA_VIDEO,
                        angulo=angulo_atual
                    )
                    fotos_animando += 1
            
            # else: onda já terminou de sair - não desenha (foto já saiu)
        
        # Debug a cada 5 segundos
        if frame_atual % 150 == 0 and frame_atual > 0:
            print(f"       Debug: {fotos_estaticas} estáticas, {fotos_animando} animando, {ondas_ativas} ondas ativas")
        
        # Escreve o frame
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        video.write(frame_bgr)
    
    print(f"  ✅ Animação de saída completa!")
    
    # Finaliza o vídeo
    video.release()
    duracao_entrada = total_frames / FPS
    duracao_saida = total_frames_saida / FPS
    duracao_total = duracao_entrada + DURACAO_PAUSA_MEIO + duracao_saida
    
    print("\n" + "="*60)
    print("VÍDEO CONCLUÍDO!")
    print("="*60)
    print(f"\n✅ Arquivo gerado: {VIDEO_SAIDA}")
    print(f"\n📊 Estatísticas:")
    print(f"   • Resolução: {LARGURA_VIDEO}x{ALTURA_VIDEO}")
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
    print(f"\n🎭 Máscara aplicada: {FOTO_MASCARA} ({int(TRANSPARENCIA_MASCARA * 100)}%)")
    print(f"\n🔄 Estrutura do vídeo:")
    print(f"   1. Entrada das fotos: {duracao_entrada:.1f}s")
    print(f"   2. Pausa (todas visíveis): {DURACAO_PAUSA_MEIO}s")
    print(f"   3. Saída das fotos: {duracao_saida:.1f}s")
    print("\n" + "="*60)

if __name__ == "__main__":
    criar_video_album()

