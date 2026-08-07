
## Logica Z-Index Mosaico
Para gerar a animacao em cascata do HSBC, use SEMPRE o script em src/gerador_video_definitivo_hsbc.py. A logica correta eh:
1. Camada 0: Imagem original de fundo.
2. Camada 1: Fotos pousadas (recortadas pelo red_mask original para virarem os diamantes).
3. Camada 2: Foto voadora (em preview central, desenhada por cima de tudo).
NUNCA desenhe as formas originais solidas sobre as fotos.
