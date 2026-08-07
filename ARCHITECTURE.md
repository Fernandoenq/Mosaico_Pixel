# Mosaico Pixel - Documentação de Arquitetura (PICBRAND ARCH)

Este documento descreve a arquitetura, estrutura de diretórios e fluxo de dados do sistema **Mosaico Pixel**, alinhado com as diretrizes do **PICBRAND ARCH** para organização, escalabilidade e padronização.

## 1. Visão Geral do Sistema

O **Mosaico Pixel** é um sistema completo para geração de painéis visuais interativos e vídeos a partir de galerias de fotos. Ele é composto por:
- **Painel de Controle Desktop:** Desenvolvido em Python/Tkinter (`main.py`).
- **Frontend Web/API:** Um servidor HTTP embutido (`simple_frontend.py`) para interação e controle remoto.
- **Motor de Renderização de Vídeo:** Scripts dedicados (`criar_video_mosaico.py`, `criar_video_album.py`) para gerar vídeos ultrawide e mosaicos de fotos com detecção de rostos e aplicação de overlays.
- **Monitoramento de Galeria:** Sistema que escuta modificações de pastas em tempo real e processa novas imagens (`galeria_monitor.py`).

## 2. Estrutura de Diretórios Organizacional

O projeto está organizado da seguinte forma para facilitar o desenvolvimento e a manutenção, mantendo separação clara entre código e ativos (assets).

```
Mosaico_Pixel/
│
├── assets/                  # Central de recursos visuais estáticos e saídas
│   ├── backgrounds/         # Máscaras, fundos (fundo.jpg, amarelo, etc) e overlays
│   └── videos/              # Arquivos de vídeo gerados e convertidos (.mp4)
│
├── MOSAIC/                  # Diretório alvo principal: fotos para o mosaico (inputs)
├── Galeria/                 # Diretórios de processamento e serviços auxiliares
│
├── main.py                  # Ponto de entrada principal: UI Desktop (Tkinter) e orquestrador
├── simple_frontend.py       # Servidor HTTP local, WebSockets e lógica da interface web
│
├── criar_video_mosaico.py   # Motor de geração de vídeos (entrada/saída e animações)
├── criar_video_album.py     # Lógica detalhada para cálculo e renderização matemática do grid
├── converter_video.py       # Utilitário para conversão/compressão de vídeo via FFmpeg (H.264)
│
├── detectar_rosto.py        # Módulo de visão computacional (OpenCV/Dlib) para recorte inteligente centrado
├── image_orientation.py     # Utilitário para corrigir metadados EXIF e orientação de imagens
├── injeta_fotos.py          # Script para automatizar a injeção/cópia rápida de lotes de fotos
├── live_mosaic_panel.py     # Lógica do painel de visualização ao vivo (UI secundária)
└── galeria_monitor.py       # Observer de arquivos de sistema (Watchdog) para a galeria
```

## 3. Fluxo de Dados e Componentes Principais

### 3.1. Orquestração (`main.py`)
- Inicia a UI desktop, permitindo que o usuário selecione pastas, gerencie configurações (resolução, diretórios) e lance o servidor web.
- Integra e invoca os subprocessos de renderização de vídeos de forma assíncrona para não travar a UI.

### 3.2. Servidor Web / API (`simple_frontend.py`)
- Hospeda uma interface em HTML/JS/CSS (inline) para exibição e controle do painel em tempo real por clientes (celulares, tablets).
- Processa requisições locais e controla o _Video Lock_ para garantir que apenas um processo de ffmpeg/renderização de vídeo ocorra por vez.
- Usa a pasta `assets/backgrounds/` para servir máscaras dinâmicas e logomarcas atualizadas no frontend.

### 3.3. Processamento e Composição Visual (`criar_video_*.py`)
- Consome fotos em tempo real ou em batch da pasta `MOSAIC/`.
- Usa `detectar_rosto.py` para efetuar recortes inteligentes (ex: células quadradas de 168x168 perfeitamente enquadradas no rosto das pessoas, garantindo a estética).
- Mescla as imagens utilizando a técnica de _alpha compositing_ com as máscaras (`fundo.jpg`, `overlay.png`) hospedadas em `assets/backgrounds/`.
- Processa ondas de animações matemáticas matriciais.
- Exporta o resultado final compilado em alta velocidade para a pasta `assets/videos/`.

## 4. Padrões de Qualidade e Boas Práticas (PICBRAND ARCH)

- **Desacoplamento de Assets:** Imagens de background e vídeos gerados nunca ficam misturados ao código-fonte raiz. Todos referenciam suas respectivas subpastas em `assets/`.
- **Caminhos Dinâmicos, Relativos e Seguros:** Os scripts utilizam `Path(__file__).resolve().parent` assegurando que os módulos encontrem seus dependentes independentemente do _Current Working Directory_ (CWD) de onde o usuário rodou o executável.
- **Isolamento de Processamento Pesado:** Operações intensivas de CPU (OpenCV, manipulação de matriz NumPy, FFmpeg) estão isoladas em scripts independentes que podem ser rodados via CLI puro ou chamados como `subprocess`, evitando concorrência na *Main Thread* do Tkinter.

## 5. Próximos Passos Recomendados
Para levar a arquitetura ao máximo nível de maturidade:
1. **Migração do Source Code:** Mover todos os arquivos `.py` para uma pasta `src/`, deixando a raiz apenas com documentação, scripts `.bat` e `requirements.txt`.
2. **Refatoração Web:** Extrair o HTML, CSS e JS contidos dentro de `simple_frontend.py` para templates independentes (`templates/` e `static/`), adotando frameworks como Flask/FastAPI caso o painel web exija escala maior.
