#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para calcular o tempo estimado dos vídeos
"""

# Configurações dos vídeos
VIDEOS = [
    {'nome': 'album_fotos_3192x672.mp4', 'largura': 3192, 'altura': 672},
    {'nome': 'album_fotos_1680x1176.mp4', 'largura': 1680, 'altura': 1176}
]

# Configurações de animação
DURACAO_POR_ONDA = 2.8
DELAY_ENTRE_ONDAS = 0.8
DURACAO_PAUSA_MEIO = 0

print("\n" + "="*60)
print("CALCULO DE DURACAO DOS VIDEOS")
print("="*60)

for video in VIDEOS:
    print(f"\n{video['nome']}:")
    print(f"  Resolucao: {video['largura']}x{video['altura']}")
    
    # Tenta encontrar o melhor tamanho de célula
    TAMANHO_CELULA_BASE = 56
    melhor_tamanho = None
    melhor_diferenca = float('inf')
    
    for tentativa in range(30, 150):
        cols = video['largura'] // tentativa
        rows = video['altura'] // tentativa
        
        if cols * tentativa == video['largura'] and rows * tentativa == video['altura']:
            diferenca = abs(tentativa - TAMANHO_CELULA_BASE)
            if diferenca < melhor_diferenca:
                melhor_tamanho = tentativa
                melhor_diferenca = diferenca
    
    if melhor_tamanho is None:
        melhor_tamanho = video['largura'] // (video['largura'] // TAMANHO_CELULA_BASE)
    
    TAMANHO_CELULA = melhor_tamanho
    FOTOS_POR_LINHA = video['largura'] // TAMANHO_CELULA
    FOTOS_POR_COLUNA = video['altura'] // TAMANHO_CELULA
    total_posicoes = FOTOS_POR_LINHA * FOTOS_POR_COLUNA
    
    print(f"  Tamanho celula: {TAMANHO_CELULA}x{TAMANHO_CELULA} pixels")
    print(f"  Grid: {FOTOS_POR_LINHA}x{FOTOS_POR_COLUNA} = {total_posicoes} imagens")
    
    # Estima número de ondas (média de 20 fotos por onda)
    num_ondas_estimado = total_posicoes // 20
    
    # Calcula tempo total
    # Última onda começa em: (num_ondas - 1) * DELAY
    # Última onda termina em: (num_ondas - 1) * DELAY + DURACAO
    tempo_entrada = (num_ondas_estimado - 1) * DELAY_ENTRE_ONDAS + DURACAO_POR_ONDA
    tempo_saida = tempo_entrada  # Simétrico
    tempo_total = tempo_entrada + DURACAO_PAUSA_MEIO + tempo_saida
    
    print(f"  Ondas estimadas: ~{num_ondas_estimado}")
    print(f"  Tempo entrada: ~{tempo_entrada:.1f}s")
    print(f"  Tempo pausa: {DURACAO_PAUSA_MEIO}s")
    print(f"  Tempo saida: ~{tempo_saida:.1f}s")
    print(f"  TEMPO TOTAL: ~{tempo_total:.1f}s (~{tempo_total/60:.1f}min)")

print("\n" + "="*60)

