# variasfoto_Vi

## 📸 Criador de Vídeo de Álbum de Fotos

Este projeto cria um vídeo animado com TODAS as fotos da pasta MOSAIC em um único grid gigante, como um álbum de fotos.

### ⚠️  IMPORTANTE: Erro 0xC00D36B4?

Se o vídeo não abrir (erro 0xC00D36B4), **ajuste a resolução** editando a variável `ESCALA` no arquivo `criar_video_album.py`:

```python
ESCALA = 0.5  # Use 0.5 para resolução 3192x672 (recomendado)
```

Quanto menor a escala, mais compatível será o vídeo! ✅

### 🎯 Funcionalidades

- ✨ **Todas as fotos em um único grid completo** (38x8 = 304 células QUADRADAS ⬛)
- 📐 **Células quadradas (168x168)** - Preenche 100% da tela, sem barras brancas
- 🎯 **Usa TODAS as 178 fotos originais** + duplicações para preencher o grid
- 🌊 **Ondas simultâneas**: múltiplas fotos entram ao mesmo tempo (grupos de 1 a 40 fotos)
- 🔥 **Fotos GIGANTES**: Mínimo 5 fotos aparecem **ENORMES** (6x a 10x maiores!) 🚀
- ⭐ **Fotos em destaque**: ~12% das fotos aparecem **MAIORES** (2.5x a 4x) antes de ir para seus lugares
- 📏 **Tamanhos variados**: cada foto entra com tamanho diferente (0.6x a 1.4x) e se ajusta
- 🎲 **Entrada completamente aleatória**: 
  - Ordem de entrada randomizada
  - Tamanho dos grupos varia (às vezes 1 foto, às vezes 10, 30...)
  - Escala inicial varia para cada foto
- 🎯 **Direções variadas**: cada foto vem de um canto/lado diferente (8 direções possíveis)
- 🔄 **Rotação dinâmica**: fotos entram tortas (até 45°) e vão se endireitando
- ⚡ **Animação rápida e fluida**: ondas sobrepostas com transições suaves
- 🎬 Animação suave com movimento deslizante, rotação, escala e efeito de fade
- 🎭 Usa `fundo.jpg` como **máscara semi-transparente** sobreposta às fotos
- ⬜ Fundo branco puro
- 🖼️ Suporta múltiplos formatos: JPG, JPEG, PNG, BMP, WEBP, JFIF
- 📐 Vídeo em resolução ultra-wide (6384x1344) personalizada

### 💡 Por que Células Quadradas de 168x168?

O tamanho **168x168 pixels** foi escolhido matematicamente para:

**1. Preenchimento Perfeito (SEM BARRAS BRANCAS!)** ✅
- 6384 ÷ 168 = **38 colunas exatas** (sem sobras)
- 1344 ÷ 168 = **8 linhas exatas** (sem sobras)
- 38 × 168 = **6384 pixels** (100% da largura)
- 8 × 168 = **1344 pixels** (100% da altura)
- **Zero pixels desperdiçados** - preenche COMPLETAMENTE a tela!

**2. Células Quadradas (1:1)** 📐
- Fotos normalmente têm proporção 3:2, 4:3 ou 16:9
- Células quadradas cortam **muito menos** que retangulares
- Exemplo: Corta apenas ~25% de fotos 4:3 (vs ~62% em retangulares)

**3. Grid Otimizado** ⚡
- 38×8 = **304 posições** - equilibrado e eficiente
- Usa **TODAS as 178 fotos originais** + duplicações inteligentes
- Boa proporção entre qualidade e performance

### 🚀 Como usar

#### ⚙️  Antes de Executar: Configure a Resolução

Abra o arquivo `criar_video_album.py` e encontre a linha (~42):

```python
ESCALA = 0.5  # Ajuste aqui se o vídeo não abrir
```

**Valores recomendados:**
- `ESCALA = 0.5` → Resolução 3192x672 ✅ **RECOMENDADO**
- `ESCALA = 1.0` → Resolução original 6384x1344 (pode causar erro 0xC00D36B4)
- `ESCALA = 0.25` → Resolução 1596x336 (máxima compatibilidade)

#### Método 1: Arquivo Batch (Windows - mais fácil)
```bash
instalar_e_executar.bat
```
Este arquivo irá instalar automaticamente as dependências e executar o script.

#### Método 2: Manual

1. **Instale as dependências:**
```bash
pip install -r requirements.txt
```

2. **Execute o script:**
```bash
python criar_video_album.py
```

3. **Aguarde o processamento** (pode levar vários minutos com 178 fotos)

4. **O vídeo será gerado como `album_fotos.mp4`**

### 🎥 Codec e Formato de Vídeo

O vídeo é gerado em formato **MP4** com codec **mp4v (MPEG-4 Part 2)**:

- ✅ **Máxima compatibilidade** - funciona em QUALQUER player
- ✅ **Sem dependências externas** (nativo no OpenCV)
- ✅ **Alta qualidade** de vídeo
- ✅ **Formato universal** - Windows, Mac, Linux, celulares
- ✅ **Abre nativamente** no Windows Media Player
- ✅ **Arquivo compacto** e fácil de compartilhar

**Arquivo gerado**: `album_fotos.mp4`

**Requisitos**: OpenCV instalado (`opencv-python` via pip).

### ⚠️  Erro 0xC00D36B4? Ajuste a Resolução!

Se você receber o erro **0xC00D36B4** ao tentar abrir o vídeo, o problema é a resolução muito alta. Ajuste a variável `ESCALA` no arquivo `criar_video_album.py` (linha ~42):

```python
ESCALA = 0.5  # 0.5 = metade da resolução (RECOMENDADO)
```

**Opções de escala:**
- `ESCALA = 1.0` → **6384x1344** (resolução original - pode não funcionar)
- `ESCALA = 0.5` → **3192x672** (recomendado) ✅
- `ESCALA = 0.25` → **1596x336** (máxima compatibilidade)

💡 Quanto menor a escala, mais compatível será o vídeo!

### ⚙️ Configurações

Você pode editar as seguintes configurações no início do arquivo `criar_video_album.py`:

#### Grid e Resolução:
- `ESCALA`: **AJUSTE PRINCIPAL** - Controla o tamanho do vídeo (padrão: 0.5) ⚠️
  - 1.0 = Resolução original 6384x1344 (pode causar erro)
  - 0.5 = Resolução reduzida 3192x672 ✅ **RECOMENDADO**
  - 0.25 = Resolução menor 1596x336 (máxima compatibilidade)
- `TAMANHO_CELULA`: Escala proporcionalmente (base: 168 pixels)
- `FOTOS_POR_LINHA`: Calculado automaticamente (38 colunas na escala 0.5)
- `FOTOS_POR_COLUNA`: Calculado automaticamente (8 linhas na escala 0.5)
- **Total: 38×8 = 304 posições** (usa TODAS as 178 fotos + duplicações)

#### Timing e Animação:
- `DURACAO_POR_ONDA`: Tempo que cada onda leva para entrar/sair (padrão: 1.5 segundos - rápido)
- `DELAY_ENTRE_ONDAS`: Delay entre início de cada onda (padrão: 0.3 segundos - ondas se sobrepõem)
- `DURACAO_PAUSA_MEIO`: Tempo com todas as fotos visíveis antes da saída (padrão: 3 segundos)
- `FPS`: Frames por segundo (padrão: 30)

#### Efeitos Visuais:
- `TRANSPARENCIA_MASCARA`: Transparência da máscara aplicada em cada foto (padrão: 0.70 = 70%)

**Fotos GIGANTES** (aparecem ENORMES na tela):
- `NUM_FOTOS_GIGANTES`: Número mínimo de fotos gigantes (padrão: 5) 🔥
- `ESCALA_GIGANTE_MIN`: Escala mínima das fotos gigantes (padrão: 6.0 = 600%)
- `ESCALA_GIGANTE_MAX`: Escala máxima das fotos gigantes (padrão: 10.0 = 1000%)

**Fotos em Destaque** (aparecem grandes):
- `PORCENTAGEM_DESTAQUE`: % de fotos que aparecem em destaque (padrão: 0.12 = 12%)
- `ESCALA_DESTAQUE_MIN`: Escala mínima das fotos em destaque (padrão: 2.5 = 250%)
- `ESCALA_DESTAQUE_MAX`: Escala máxima das fotos em destaque (padrão: 4.0 = 400%)

**Fotos Normais**:
- `ESCALA_MINIMA`: Escala mínima inicial das fotos normais (padrão: 0.6 = 60%)
- `ESCALA_MAXIMA`: Escala máxima inicial das fotos normais (padrão: 1.4 = 140%)

### 📁 Estrutura do Projeto

```
variasfoto_Vi/
├── MOSAIC/                    # Pasta com todas as fotos (178 imagens)
├── fundo.jpg                  # Imagem usada como máscara semi-transparente
├── criar_video_album.py       # Script principal
├── requirements.txt           # Dependências Python
├── instalar_e_executar.bat    # Script para instalação e execução automática
└── album_fotos.mp4           # Vídeo gerado (após executar)
```

### 🎨 Como funciona

O script é executado em **3 fases bem definidas**:

#### 📦 FASE 1: PREPARAÇÃO DAS IMAGENS

1. **Análise inicial:**
   - Lê todas as imagens da pasta `MOSAIC`
   - Calcula o grid de 15x12 (180 posições)
   - Define tamanho de cada foto no grid (sem margens - grudadas)
   - Se faltarem fotos para completar o grid, duplica fotos aleatórias automaticamente

2. **Carrega a máscara:**
   - Carrega e redimensiona `fundo.jpg` para o tamanho do vídeo (6384x1344)
   - Divide a máscara em 180 regiões correspondentes às posições do grid

3. **Processa todas as imagens:**
   - Para cada foto do MOSAIC:
     - Carrega e **recorta (crop centralizado)** para preencher completamente o quadrado
     - A imagem é ajustada para cobrir todo o espaço (sem bordas brancas)
     - Extrai a "fatia" correspondente do `fundo.jpg`
     - Aplica a máscara (60% de transparência) na foto
     - Salva a foto processada em memória
   
4. **Gera o resultado final:**
   - Monta o frame final com todas as fotos posicionadas (grid completo)
   - Este será usado no final do vídeo

**Resultado da Fase 1:** 304 imagens prontas (grid completo de células quadradas), cada uma já com sua parte do `fundo.jpg` aplicada

#### 🎲 FASE 2: PLANEJAMENTO DA ANIMAÇÃO

1. **Define movimentos:**
   - Para cada foto, sorteia:
     - Direção de entrada (8 opções: ←, →, ↑, ↓, ↖, ↗, ↙, ↘)
     - Ângulo de rotação inicial (entre -45° e +45°)
     - Ponto de origem fora da tela

2. **Randomiza ordem:**
   - Embaralha completamente a ordem de entrada das fotos

3. **Cria ondas:**
   - Divide as fotos em grupos (ondas) de tamanhos aleatórios
   - Cada onda pode ter de 1 a 40 fotos
   - Distribuição ponderada: mais comum ter grupos de 5-15 fotos
   - Exemplo: Onda 1 com 12 fotos, Onda 2 com 1 foto, Onda 3 com 28 fotos...

**Resultado da Fase 2:** Plano completo de como cada foto vai entrar no vídeo

#### 🎬 FASE 3: GERAÇÃO DO VÍDEO

1. **Inicializa o vídeo:**
   - Cria arquivo MP4 com resolução ultra-wide (6384x1344)
   - Fundo branco puro

2. **Gera animação com ondas sobrepostas:**
   - **Ondas se sobrepõem**: antes de uma onda terminar, a próxima já começa
   - Delay de 0.8s entre ondas cria movimento contínuo e fluido
   - Para cada onda (4.0s de duração - bem lento e natural):
     - **Múltiplas fotos entram simultaneamente**
     - Cada foto:
       - Desliza de fora da tela até sua posição final (bem devagar)
       - Começa torta e vai se endireitando (rotação → 0°)
       - Fade suave (transparente → opaco)
       - Movimento com easing quintic ease-out (muito suave e natural)
       - **Já aparece com a máscara aplicada desde o início**
     - Fotos que já chegaram ficam paradas
   - Efeito visual: fotos chegando continuamente, sem pausas aparentes

3. **Pausa no meio:**
   - Usa o resultado pré-calculado da Fase 1
   - Mantém todas as fotos visíveis por 3 segundos

4. **Animação de saída (retorno):**
   - **Movimento reverso**: fotos voltam da mesma forma que entraram
   - Mesmas ondas, mesma ordem de saída
   - Cada foto:
     - Sai de sua posição final em direção ao ponto de origem
     - Começa reta e vai ficando torta (rotação 0° → ângulo inicial)
     - Fade reverso (opaco → transparente)
     - Movimento com easing quintic ease-out (bem suave)
   - Ondas se sobrepõem na saída também (delay de 0.8s)

5. **Finaliza:**
   - Salva o vídeo como `album_fotos.mp4`

**Resultado da Fase 3:** Vídeo completo com ida e volta!

---

### 🖥️ O que você verá durante a execução

```
============================================================
FASE 1: PREPARAÇÃO DAS IMAGENS
============================================================

✅ Grid calculado automaticamente para CÉLULAS QUADRADAS:
   • Resolução do vídeo: 6384x1344
   • Tamanho da célula: 168x168 pixels (1:1 - quadrada perfeita)
   • Grid resultante: 38 colunas x 8 linhas
   • Total de posições: 304

📸 Encontradas 178 imagens na pasta MOSAIC

📏 Configuração do Grid:
   • Resolução do vídeo: 6384x1344 (ultra-wide)
   • Grid: 38x8 = 304 posições (100% preenchido - SEM BARRAS BRANCAS!)
   • Tamanho de cada célula: 168x168 pixels ✅ QUADRADA
   • Proporção da célula: 1:1 (quadrada - mínimo corte possível)

⚠️  Faltam 126 fotos para completar o grid
   → Duplicando fotos aleatórias para completar
   ✅ Grid completo com 304 fotos (incluindo 126 duplicadas)

🎭 Carregando máscara de fundo: fundo.jpg
   ✅ Máscara carregada com sucesso
   • Transparência: 30%

🖼️  Processando todas as imagens...
   [1/304] foto1.jpg
   [2/304] foto2.jpg
   ...
   ✅ 304 imagens processadas e prontas!

============================================================
PREPARAÇÃO CONCLUÍDA!
============================================================

============================================================
FASE 2: PLANEJAMENTO DA ANIMAÇÃO
============================================================

🌊 Criando ondas de entrada aleatórias...
   ✅ Criadas ~15 ondas de entrada (varia a cada execução)
      Onda 1: 23 fotos
      Onda 2: 15 fotos
      Onda 3: 31 fotos
      ... (mostra apenas as primeiras 10)

============================================================
PLANEJAMENTO CONCLUÍDO!
============================================================

============================================================
FASE 3: GERAÇÃO DO VÍDEO
============================================================

🎥 Inicializando gerador de vídeo...
   📁 Arquivo de saída: album_fotos.mp4
   🔧 Usando codec: mp4v (MPEG-4 Part 2 - máxima compatibilidade)
   ✅ Vídeo inicializado com sucesso!

🎞️  Gerando animação com ondas sobrepostas...

  🌊 Onda 1/15: 12 fotos
     Inicia no frame 0 | Termina no frame 75
  🌊 Onda 2/15: 8 fotos
     Inicia no frame 9 | Termina no frame 84
  🌊 Onda 3/15: 15 fotos
     Inicia no frame 18 | Termina no frame 93
  ...

  📊 Total de frames de animação de entrada: ~140 (~4.7 segundos)
  ⏱️  Ondas se sobrepõem com delay de 0.3s entre elas
  🔥 5 fotos GIGANTES (6x a 10x maiores - ENORMES!)
  ⭐ ~36 fotos em destaque (2.5x a 4x maiores)
  📷 ~263 fotos normais (0.6x a 1.4x)

  🎬 Gerando frames de entrada...
     Frame 0/140 (0.0%)
     Frame 50/140 (35.7%)
     Frame 100/140 (71.4%)
     ...

💾 Finalizando e salvando vídeo...
   ⏳ Aguarde, escrevendo arquivo no disco...
   ✅ Vídeo salvo com sucesso!
   📦 Tamanho do arquivo: ~120 MB

============================================================
VÍDEO CONCLUÍDO!
============================================================

✅ Arquivo gerado: album_fotos.mp4

📊 Estatísticas:
   • Resolução: 6384x1344 (ultra-wide) - 100% PREENCHIDO
   • Duração total: ~12.4 segundos
   • Duração da entrada: ~4.7 segundos
   • Duração da pausa: 3 segundos
   • Duração da saída: ~4.7 segundos
   • Total de fotos: 304 células quadradas (178 originais + 126 duplicadas)
   • Total de ondas: ~15 (varia a cada execução)
   • Fotos GIGANTES: 5 (aparecem 6x a 10x maiores) 🔥
   • Fotos em destaque: ~36 (aparecem 2.5x a 4x maiores) ⭐
   • Fotos normais: ~263 (0.6x a 1.4x)
   • Duração por onda: 1.5 segundos ⚡
   • Delay entre ondas: 0.3 segundos (sobreposição rápida)

🔄 Estrutura do vídeo:
   1. Entrada das fotos: ~4.7s (ondas sobrepostas rápidas, fotos em tamanhos variados)
   2. Pausa (todas visíveis): 3s
   3. Saída das fotos: ~4.7s (reverso da entrada, **fotos que saem ficam POR CIMA**)
```

### ⭐ Sistema de Fotos em Destaque e GIGANTES

O script usa **3 categorias** de tamanhos diferentes para criar impacto visual:

#### 🔥 Fotos GIGANTES (Mínimo 5):
- Entram com escala **6.0x a 10.0x** (600% a 1000% do tamanho!) 🚀
- Aparecem **ENORMES** ocupando grande parte da tela
- **Se movem mais DEVAGAR** (metade da velocidade) criando efeito de "peso" 🐌
- Criam impacto visual EXTREMO antes de encolher
- Selecionadas aleatoriamente para máximo efeito surpresa
- **Exemplo**: Uma foto que entra com 10x ocupa quase a tela inteira e se move lentamente!

#### ⭐ Fotos em Destaque (~12%):
- Entram com escala **2.5x a 4.0x** (250% a 400% do tamanho)
- Aparecem **MUITO maiores** que as normais
- Destacam-se no meio das outras fotos
- Gradualmente diminuem até o tamanho normal

#### 📷 Fotos Normais (~85%):
- Entram com escala variável entre **0.6x a 1.4x** (60% a 140%)
- Criam dinamismo e variedade visual
- Gradualmente se ajustam para o tamanho normal (1.0x)

**Exemplo visual:**
```
Foto Normal (0.8x)   →  [pequena] →→→→ [normal]      (velocidade normal)
Foto Destaque (3.5x) →  [GRANDE] →→→→ [normal]       (velocidade normal)
Foto GIGANTE (8x)    →  [ENOOORME!!!] ➔➔ [normal]   (velocidade LENTA - efeito dramático!)
```

Isso cria um efeito visual **ESPETACULAR** onde:
- Fotos gigantes literalmente **"EXPLODEM" na tela** 🎆
- Se movem **mais lentamente** criando efeito de "peso" e drama 🐌
- Destacam-se MUITO mais que as outras por serem maiores E mais lentas! 🔥

### 🎯 Exemplo de Direções

As fotos podem entrar de 8 direções diferentes:
- ← **Esquerda**: foto desliza da esquerda para direita
- → **Direita**: foto desliza da direita para esquerda  
- ↑ **Cima**: foto desliza de cima para baixo
- ↓ **Baixo**: foto desliza de baixo para cima
- ↖ **Diagonal superior esquerda**
- ↗ **Diagonal superior direita**
- ↙ **Diagonal inferior esquerda**
- ↘ **Diagonal inferior direita**

### 🎬 Efeito de Camadas na Saída

Durante a **animação de saída**, as fotos que estão saindo aparecem **POR CIMA** das outras, criando um efeito de profundidade:

**Ordem de desenho (de baixo para cima):**
1. 🟦 **Fotos estáticas** (ainda não começaram a sair) - camada mais baixa
2. 🟨 **Fotos saindo com menos progresso** - camadas intermediárias  
3. 🟥 **Fotos saindo com mais progresso** - camada mais alta (por cima de tudo)

**Resultado visual:**
```
[Foto estática] ← por baixo
  [Foto saindo 20%] ← meio
    [Foto saindo 50%] ← meio-cima
      [Foto saindo 80%] ← POR CIMA!
```

Isso cria um efeito **dramático** onde as fotos parecem "descolar" do grid e sair flutuando por cima das outras! 🎆

### 🌊 Sistema de Ondas Sobrepostas

O script divide as fotos em ondas aleatórias que **se sobrepõem**:

#### Tamanhos de Ondas:
- **Onda pequena**: 1-5 fotos entram juntas
- **Onda média**: 6-20 fotos entram juntas  
- **Onda grande**: 21-40 fotos entram juntas

#### Como funciona a sobreposição:

```
Linha do tempo (segundos):
0.0s ━━━ Onda 1 inicia (12 fotos, 1.5s) ━━━━━━━━┓
0.3s     ━━━ Onda 2 inicia (8 fotos, 1.5s) ━━━━━┃━━━┓
0.6s         ━━━ Onda 3 inicia (15 fotos, 1.5s) ━┃━━━┃━━┓
0.9s             ━━━ Onda 4 inicia... ━━━━━━━━━━━┃  ┃  ┃
...                                               ┃  ┃  ┃
1.5s ━━━━━━━━━━━ Onda 1 termina ━━━━━━━━━━━━━━━━┛  ┃  ┃
1.8s ━━━━━━━━━━━━━━━ Onda 2 termina ━━━━━━━━━━━━━━━┛  ┃
2.1s ━━━━━━━━━━━━━━━━━━━ Onda 3 termina ━━━━━━━━━━━━━┛
```

**Vantagens:**
- ⚡ Animação rápida e dinâmica
- ✨ Movimento contínuo e fluido
- 🎭 Não fica óbvio quando uma onda começa/termina
- 🌊 Fotos chegam em fluxo constante e acelerado
- 💫 Efeito mais natural e orgânico

**Exemplo de execução:**
```
Onda 1: 12 fotos (0.0s - 1.5s)
Onda 2: 1 foto (0.3s - 1.8s)    ← Começa antes da Onda 1 terminar!
Onda 3: 28 fotos (0.6s - 2.1s)  ← Começa antes da Onda 2 terminar!
Onda 4: 7 fotos (0.9s - 2.4s)
...
```

Cada execução gera um vídeo completamente diferente! 🎲

### 🎭 Sobre a Máscara (fundo.jpg)

**Importante:** A imagem `fundo.jpg` NÃO é um fundo de tela!

- A máscara é aplicada **individualmente em cada foto** do mosaico
- Cada foto recebe uma "fatia" específica do `fundo.jpg` correspondente à sua posição no grid
- Quando todas as fotos estão no lugar (180 posições), elas formam juntas a imagem completa do `fundo.jpg`
- É como se o `fundo.jpg` fosse "recortado" em 180 pedaços e cada pedaço fosse sobreposto em uma foto
- Se houver menos fotos que posições, o script duplica fotos aleatórias para completar o grid

**Efeito visual:** 
- Durante a animação: fotos já aparecem com o efeito do `fundo.jpg` desde o primeiro frame
- Conforme mais fotos chegam: o `fundo.jpg` vai se formando gradualmente através do mosaico
- Resultado final: um mosaico completo com a imagem do `fundo.jpg` "transparecendo" através dele
- É como ver o `fundo.jpg` sendo montado pedaço por pedaço, conforme as fotos vão chegando

#   g a l e r i a - - - m o s a i c o  
 