# variasfoto_Vi

## 📸 Criador de Vídeo de Álbum de Fotos

Este projeto cria um vídeo animado com TODAS as fotos da pasta MOSAIC em um único grid gigante, como um álbum de fotos.

### 🎯 Funcionalidades

- ✨ **Todas as fotos em um único grid completo** (15x12 = 180 posições, duplica fotos se necessário)
- 🌊 **Ondas simultâneas**: múltiplas fotos entram ao mesmo tempo (grupos de 1 a 40 fotos)
- 🎲 **Entrada completamente aleatória**: 
  - Ordem de entrada randomizada
  - Tamanho dos grupos varia (às vezes 1 foto, às vezes 10, 30...)
- 🎯 **Direções variadas**: cada foto vem de um canto/lado diferente (8 direções possíveis)
- 🔄 **Rotação dinâmica**: fotos entram tortas (até 45°) e vão se endireitando
- 🎬 Animação suave com movimento deslizante, rotação e efeito de fade
- 🎭 Usa `fundo.jpg` como **máscara semi-transparente** sobreposta às fotos
- ⬜ Fundo branco puro
- 🖼️ Suporta múltiplos formatos: JPG, JPEG, PNG, BMP, WEBP, JFIF
- 📐 Vídeo em resolução 4K (3840x2160) para melhor qualidade

### 🚀 Como usar

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

### ⚙️ Configurações

Você pode editar as seguintes configurações no início do arquivo `criar_video_album.py`:

- `FOTOS_POR_LINHA`: Número de fotos por linha no grid (padrão: 15)
- `FOTOS_POR_COLUNA`: Número de fotos por coluna no grid (padrão: 12)
- `DURACAO_POR_ONDA`: Tempo que cada onda leva para entrar/sair (padrão: 4.0 segundos - bem lento e suave)
- `DELAY_ENTRE_ONDAS`: Delay entre início de cada onda (padrão: 0.8 segundos - ondas se sobrepõem)
- `DURACAO_PAUSA_MEIO`: Tempo com todas as fotos visíveis antes da saída (padrão: 3 segundos)
- `LARGURA_VIDEO`: Largura do vídeo em pixels (padrão: 3840 - 4K)
- `ALTURA_VIDEO`: Altura do vídeo em pixels (padrão: 2160 - 4K)
- `FPS`: Frames por segundo (padrão: 30)
- `TRANSPARENCIA_MASCARA`: Transparência da máscara aplicada em cada foto (padrão: 0.30 = 30%)

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
   - Define tamanho de cada foto no grid
   - Se faltarem fotos para completar o grid, duplica fotos aleatórias automaticamente

2. **Carrega a máscara:**
   - Carrega e redimensiona `fundo.jpg` para o tamanho do vídeo (3840x2160)
   - Divide a máscara em 180 regiões correspondentes às posições do grid

3. **Processa todas as imagens:**
   - Para cada foto do MOSAIC:
     - Carrega e redimensiona para o tamanho correto
     - Extrai a "fatia" correspondente do `fundo.jpg`
     - Aplica a máscara (30% de transparência) na foto
     - Salva a foto processada em memória
   
4. **Gera o resultado final:**
   - Monta o frame final com todas as fotos posicionadas (grid completo)
   - Este será usado no final do vídeo

**Resultado da Fase 1:** 180 imagens prontas (grid completo), cada uma já com sua parte do `fundo.jpg` aplicada

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
   - Cria arquivo MP4 com resolução 4K
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

📸 Encontradas 178 imagens na pasta MOSAIC

📏 Configuração do Grid:
   • Resolução do vídeo: 3840x2160
   • Grid: 15x12 = 180 posições
   • Tamanho de cada foto: 248x172 pixels

⚠️  Faltam 2 fotos para completar o grid
   → Duplicando fotos aleatórias para completar
   ✅ Grid completo com 180 fotos (incluindo 2 duplicadas)

🎭 Carregando máscara de fundo: fundo.jpg
   ✅ Máscara carregada com sucesso
   • Transparência: 30%

🖼️  Processando todas as imagens...
   [1/180] foto1.jpg
   [2/180] foto2.jpg
   ...
   ✅ 180 imagens processadas e prontas!

============================================================
PREPARAÇÃO CONCLUÍDA!
============================================================

============================================================
FASE 2: PLANEJAMENTO DA ANIMAÇÃO
============================================================

🌊 Criando ondas de entrada aleatórias...
   ✅ Criadas 15 ondas de entrada
      Onda 1: 12 fotos
      Onda 2: 8 fotos
      ...

============================================================
PLANEJAMENTO CONCLUÍDO!
============================================================

============================================================
FASE 3: GERAÇÃO DO VÍDEO
============================================================

🎥 Inicializando gerador de vídeo...
   ✅ Vídeo inicializado: album_fotos.mp4

🎞️  Gerando animação com ondas sobrepostas...

  🌊 Onda 1/15: 12 fotos
     Inicia no frame 0 | Termina no frame 75
  🌊 Onda 2/15: 8 fotos
     Inicia no frame 9 | Termina no frame 84
  🌊 Onda 3/15: 15 fotos
     Inicia no frame 18 | Termina no frame 93
  ...

  📊 Total de frames de animação: 201 (6.7 segundos)
  ⏱️  Ondas se sobrepõem com delay de 0.3s entre elas

  🎬 Gerando 201 frames...
     Frame 0/201 (0.0%)
     Frame 30/201 (14.9%)
     Frame 60/201 (29.9%)
     ...

============================================================
VÍDEO CONCLUÍDO!
============================================================

✅ Arquivo gerado: album_fotos.mp4

📊 Estatísticas:
   • Resolução: 3840x2160
   • Duração total: 29.0 segundos
   • Duração da entrada: 13.0 segundos
   • Duração da pausa: 3 segundos
   • Duração da saída: 13.0 segundos
   • Total de fotos: 180 (incluindo 2 duplicadas)
   • Total de ondas: 15
   • Duração por onda: 4.0 segundos
   • Delay entre ondas: 0.8 segundos (sobreposição)

🔄 Estrutura do vídeo:
   1. Entrada das fotos: 13.0s
   2. Pausa (todas visíveis): 3s
   3. Saída das fotos: 13.0s
```

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

### 🌊 Sistema de Ondas Sobrepostas

O script divide as fotos em ondas aleatórias que **se sobrepõem**:

#### Tamanhos de Ondas:
- **Onda pequena**: 1-5 fotos entram juntas
- **Onda média**: 6-20 fotos entram juntas  
- **Onda grande**: 21-40 fotos entram juntas

#### Como funciona a sobreposição:

```
Linha do tempo (segundos):
0.0s ━━━ Onda 1 inicia (12 fotos, 4.0s de duração) ━━━━━━━━━━━━━━━━━━━━━┓
0.8s         ━━━ Onda 2 inicia (8 fotos, 4.0s) ━━━━━━━━━━━━━━━━━━━┓    ┃
1.6s                 ━━━ Onda 3 inicia (15 fotos, 4.0s) ━━━━━━━━━━┃━━┓ ┃
2.4s                         ━━━ Onda 4 inicia... ━━━━━━━━━━━━━━━━┃  ┃ ┃
...                                                                 ┃  ┃ ┃
4.0s ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ Onda 1 termina ━━━━━━━━━┛  ┃ ┃
4.8s ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ Onda 2 termina ━━━━━━━━┛ ┃
5.6s ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ Onda 3 termina ━━━━━┛
```

**Vantagens:**
- ✨ Movimento contínuo e fluido
- 🎭 Não fica óbvio quando uma onda começa/termina
- 🌊 Fotos chegam em fluxo constante
- 💫 Efeito mais natural e orgânico

**Exemplo de execução:**
```
Onda 1: 12 fotos (0.0s - 4.0s)
Onda 2: 1 foto (0.8s - 4.8s)    ← Começa antes da Onda 1 terminar!
Onda 3: 28 fotos (1.6s - 5.6s)  ← Começa antes da Onda 2 terminar!
Onda 4: 7 fotos (2.4s - 6.4s)
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

