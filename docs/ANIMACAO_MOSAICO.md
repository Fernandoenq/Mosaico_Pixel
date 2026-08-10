## Logica Z-Index Mosaico
Para gerar a animacao em cascata do HSBC, use SEMPRE o script em src/gerador_video_definitivo_hsbc.py. A logica correta eh:
1. Camada 0: Imagem original de fundo.
2. Camada 1: Fotos pousadas (recortadas pelo red_mask original para virarem os diamantes).
3. Camada 2: Foto voadora (em preview central, desenhada por cima de tudo).
NUNCA desenhe as formas originais solidas sobre as fotos.
4. Preenchimento: Mapeie as bordas de cada linha (`row_bounds`) e preencha também o vazio entre as formas para formar a logo completa (ex: gravata-borboleta).
5. Cores/Filtros: Apenas as células que fazem parte da logo original (`red_cells`) devem receber o filtro colorido (ex: `apply_red_tint`). As fotos que caem no "vazio/meio" devem manter as cores originais, sem filtro.
