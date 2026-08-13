# Mosaico Pixel — Arquitetura

Conformidade: **PICBRAND ARCH**. Este documento substitui a versão anterior, que
descrevia um sistema desktop em Tkinter (`main.py`, `simple_frontend.py`)
aposentado — esse código está preservado em [`legacy/`](../legacy/).

## 1. Objetivo

Telão ao vivo para ativações de marca. As fotos da cabine chegam por S3, viram
ladrilhos de um mosaico que desenha o logo do cliente, e cada foto ganha um
momento de destaque no centro da tela antes de pousar no seu lugar.

## 2. Stack

| Camada | Tecnologia | Porta |
| --- | --- | --- |
| Backend | FastAPI + Uvicorn (Python 3.10) | 8000 |
| Frontend | Vite + React + TypeScript + PixiJS + GSAP | 3000 |
| Estado do cliente | Zustand (com persistência em localStorage) | — |
| Transporte ao vivo | WebSocket (`/ws`) | — |
| Visão computacional | OpenCV (Haar Cascade para recorte de rosto) | — |
| Storage externo | AWS S3 (`sa-east-1`) | — |

Arquitetura de aplicação: **MVVM**. O telão é uma experiência interativa com
estado complexo (fila de animação, camadas, transporte do show), e o painel é o
autor da configuração — a separação view/estado é o que sustenta os dois.

## 3. Estrutura

```text
Mosaico_Pixel/
├── backend/
│   ├── app/
│   │   ├── core/          config.py · state.py · run_config.py
│   │   ├── services/      mosaic_engine · watcher · s3_watcher · smart_crop
│   │   │                  queue_manager · video_export · video_marca
│   │   └── main.py        rotas, WebSocket, health, ingestão
│   └── storage/           saídas em runtime (fora do git)
├── frontend/src/
│   ├── components/Canvas/ PixiViewport — o telão
│   ├── components/Sidebar/ painel de controle
│   ├── store/             mosaicStore (Zustand) — contrato da RunConfig
│   └── utils/             gsapAnimations — presets de voo
├── tools/                 gerar_overlay_marca.py
├── docs/                  esta doc, animação, decisões
└── legacy/                sistema Tkinter e scripts históricos
```

## 4. Fluxo de uma foto

```text
cabine → S3 → S3Watcher (poll 5s, ignora `*masked*`) → hot_folder/
                                        ↓ watchdog (on_created + on_moved)
                    trava por nome (sempre) + por hash MD5 (opcional)
                                        ↓
                            smart_crop_face → storage/tiles/ (512px)
                                        ↓
                      engine.find_best_tile_position (cor + sequência)
                                        ↓
                          WebSocket TILE_PLACED → telão
                                        ↓
                   preview central → voo → pousa na célula
```

Pontos que já custaram caro e estão documentados no código:

- O download do boto3 grava temporário e **renomeia**: o watcher precisa de
  `on_moved`, não só `on_created`. Há ainda uma varredura de segurança a cada 10s.
- A cabine publica **duas versões da mesma foto**: a original
  (`hsbc/totem_0017.jpg`, `originals/...`) e um recorte (`totem_masked/...`,
  `img_Nmasked.png`). **Quem vai para o mosaico é a original.** O S3Watcher nem
  baixa o recorte — filtro por trecho do nome em `S3_IGNORE_PATTERNS` (padrão
  `masked`; vazio desliga o filtro). A chave ignorada **não** entra em
  `s3_seen.json`, para voltar a ser candidata se o filtro mudar.
- Depois do filtro ainda existem **duas travas de duplicata**:
  - **Por nome** (`photo_id`), sempre ligada. A varredura inicial da hot folder
    reprocessa a pasta inteira a cada restart — sem ela, reiniciar o backend no
    meio do evento duplicaria o mosaico.
  - **Por hash de conteúdo** (MD5), controlada por `permitirFotosRepetidas`.
    Desligada (padrão), duas fotos byte a byte iguais viram um tile só. Ligada,
    viram dois: o mosaico enche mais rápido e a mesma pessoa aparece duas vezes
    — é uma decisão de operação, não um bug. Com o filtro do S3 no lugar, esta
    trava raramente dispara.
  - Ligar a flag **não é retroativo**: as cópias já recusadas nesta rodada ficam
    de fora, porque o `photo_id` delas já está registrado. Vale a partir do
    próximo restart do backend ou do próximo reset do mosaico.
- As chaves já importadas do S3 são **persistidas** em `storage/s3_seen.json`;
  sem isso, todo restart reimportava o bucket inteiro.

## 4.1 Enchendo o mosaico

O desenho da marca tem mais células do que gente na fila. Quatro caminhos fecham
a diferença, e eles se somam:

| Caminho | Rota | Comportamento |
| --- | --- | --- |
| Duplicação gradual | `PUT /api/config {autoDuplicateToFill}` | Laço no backend copia em rodízio as fotos já pousadas. Cada cópia sai por `TILE_PLACED`, com a animação de foto nova. Quem chega no meio do evento entra no rodízio. |
| Preenchimento imediato | `POST /api/mosaic/auto-fill-duplicates` | Fecha tudo de uma vez, sem animação. Para a foto oficial e a gravação do vídeo. |
| Fechamento animado | `POST /api/mosaic/fechar-animado` | Fecha o que falta foto a foto, com a animação inteira, e para sozinho no fim. `GET` na mesma rota diz se ainda roda; `/parar` interrompe. |
| Desfazer | `POST /api/mosaic/remove-duplicates` | Apaga só os ladrilhos com sufixo `_dup_` e emite `TILES_REMOVED`. As fotos reais ficam. |

Gradual e fechamento animado colocam pela MESMA função (`_duplicar_uma_foto`) e
só diferem em quando param: o interruptor roda enquanto estiver ligado e absorve
quem chega no meio do evento; o fechamento é um gesto de encerramento, começa e
acaba. Os dois obedecem ao mesmo respiro (`duplicateIntervalSeconds` somado ao
tempo que o telão leva para exibir a cópia anterior), então o slider do painel
manda nos dois.

O fechamento animado **precisa parar sozinho** — é um laço de fundo num sistema
que roda ao vivo. Ele acaba quando a grade fecha, quando não há foto real para
copiar, e quando o rodízio inteiro falha duas voltas seguidas (arquivo sumido do
disco). Sem a última condição, um lote de arquivos ilegíveis viraria laço eterno
cuspindo erro no log a noite toda.

O ritmo NÃO é o valor cru de `duplicateIntervalSeconds`: o laço soma o tempo que
o telão leva para exibir a cópia anterior (hold do preview + voo + respiro).
Sem isso ele soltava uma cópia a cada 3s enquanto cada uma leva uns 12s na
tela, e a fila crescia sem fim.

O **miolo da marca** estende a malha de losangos para dentro da chapa preta do
meio do logo: recorta um losango por célula vaga do contorno e soma essas
células à máscara, sem pintura — a foto fica na cor original. Os respiros do
halftone não são tapados (blocos contínuos sim, células soltas não), senão o
degradê da ponta da marca some. Há dois caminhos:

- **Na preparação**, para as artes listadas em `ABRIR_MIOLO` no
  `tools/preparar_cenarios.py`. O cenário já nasce com o miolo aberto, o número
  de células no manifesto é o real e o agrupamento de ladrilhos parte da máscara
  inteira. É o caminho preferido.
- **Ao vivo**, por `POST /api/mosaic/abrir-miolo-da-marca`. A arte original vai
  para `<overlay>_sem_miolo.png` e `POST /api/mosaic/restaurar-marca-original` a
  devolve. Aqui a ordem importa: escolha o agrupamento ANTES, porque trocá-lo
  recalcula a máscara sem as células do miolo e o meio vira buraco preto.

### Tamanho do ladrilho (`cenarioAgrupamento`)

`POST /api/cenarios/{id}/aplicar?agrupamento=N` junta blocos de NxN células da
malha numa célula só. **O logo não muda de tamanho na tela** — a área da grade é
a mesma —, então cada ladrilho fica N vezes maior e o mosaico fecha com menos
fotos. É o botão para encurtar o evento sem trocar a arte:

| Fator | Grade (branco_logo) | Células | Ladrilho |
| --- | --- | --- | --- |
| 1× | 25×45 | 823 | 38px |
| 2× | 13×23 | 215 | 74px |
| 3× | 9×15 | 96 | 113px |
| 4× | 7×12 | 59 | 141px |

Uma célula agrupada entra na máscara quando **metade ou mais** das originais
dentro dela estavam na máscara; mais frouxo transborda o contorno do logo, mais
apertado come as bordas. A pintura segue a maioria do bloco. O desenho se lê bem
até 2×; de 3× em diante as pontas ficam quadradas.

### Quando o mosaico fecha

Com `autoOutroOnComplete` ligado, encher a última célula dispara um ciclo:

```text
CHEIO ──autoOutroDelaySeconds──▶ DESFAZ (outroMode) ──▶ REMONTA COMPLETO
                                                              │
   ┌────── limpa e volta a encher ◀── outroHoldSeconds parado ─┘
```

Durante todo o ciclo a fila do telão **congela**: foto que chegar espera. É isso
que garante os segundos de mosaico completo e imóvel — o respiro para o público
fotografar o resultado. O backend só libera as células no fim (`hold` +
`OUTRO_MARGEM_ANIMACAO`), e não junto com o `MOSAIC_OUTRO`: limpar antes deixaria
uma foto nova entrar por baixo da imagem final.

`espalhar` é o modo do vídeo de referência do cliente, medido quadro a quadro: em
`t=12,70s` o mosaico está inteiro e em `t=12,80s` sumiu — os ladrilhos andam
pouco e apagam quase juntos, sem voar para fora da tela.

`check_auto_outro()` é chamada de dentro do event loop (duplicação, auto-fill),
de **thread** (ingestão, aprovação) e no Play. As três importam: sem a da
ingestão o mosaico enchia de fotos reais e a animação nunca vinha; sem a do Play
um mosaico preenchido em `idle` ficava travado cheio para sempre, porque as
outras só rodam quando um tile pousa e não havia mais onde pousar.

## 4.2 Cenários do evento

Cada arte que o cliente manda vira um **cenário**: um telão inteiro (overlay +
grade + máscara de células) que o painel aplica com um clique.

`tools/preparar_cenarios.py` lê as artes de `fundos/`, escreve os overlays e o
manifesto em `backend/storage/cenarios/`, e o painel os lista por
`GET /api/cenarios`. `POST /api/cenarios/{id}/aplicar` grava o conjunto no
RunConfig e retransmite. Roda uma vez, quando chega arte nova:

```bash
python tools/preparar_cenarios.py
```

O manifesto **preserva** cenário cuja arte já saiu de `fundos/`, enquanto o
overlay dele estiver no disco: a pasta é área de trabalho e a faxina de lá não
pode apagar do painel um cenário que ainda roda.

**A foto entra POR BAIXO da logo vazada.** Cada losango do halftone é recortado
no formato dele e vira janela transparente; o fundo, a malha entre um losango e
outro e os textos ficam opacos por cima do mosaico. Abrir toda célula que cai
dentro do contorno do logo — já tentado, para não sobrar quadro vazio — dissolve
a malha numa chapa de fotos e o cliente perde o desenho da marca. Quem quiser
foto no meio do logo usa `abrir-miolo-da-marca`, que é opt-in e reversível.

Duas armadilhas do detector, ambas já pagas em tela:

- **Texto virando janela.** Todo pixel claro da arte inclui "HSBC Brazil Decade"
  e as tarjas da borda. Só entra a chapa filtrada por tamanho nos dois eixos —
  e, nas artes de miolo picotado, o losango claro que está DENTRO do contorno da
  malha vermelha. Letra graúda tem o tamanho de um losango; o que a exclui é o
  lugar, não a área.
- **Losango sem célula.** Um centróide por componente perde os losangos que se
  encostam: o antisserrilhado cola quatro num borrão só e os outros nunca
  recebem foto. Por isso a célula também vale pela fração de janela que ocupa
  (`COBERTURA_LOSANGO`) — os dois critérios se somam.

## 5. Configuração (RunConfig)

Fonte única da verdade, em `backend/app/core/run_config.py`, espelhada em
`frontend/src/store/mosaicStore.ts` (mesmos nomes, camelCase). O painel publica
via `PUT /api/config`, o backend valida e persiste em `storage/run_config.json`,
e retransmite por WebSocket. **O telão apenas consome.**

O `run_state` (idle/running/paused) é persistido à parte, em
`storage/run_state.json`, para sobreviver a um restart no meio do evento.

## 6. Health (§11)

| Rota | Uso |
| --- | --- |
| `GET /health` | Público e simples. Só confirma que o processo responde. |
| `GET /ready` | 503 se storage, hot folder, watcher ou engine não estiverem prontos. |
| `GET /admin/health` | Operacional: uptime, tiles pousados, fila, watchers, conexões. |

## 7. Decisões registradas

| Tema | Decisão |
| --- | --- |
| Admin | Sem área `/admin` de UI. Só `/admin/health`, em rede local durante o evento. |
| Docker | Não usado: o sistema roda na máquina do evento, sem orquestração. |
| Banco de dados | Nenhum. O estado do evento vive em JSON no `storage/` e é efêmero por evento. |
| Mídia no git | Não versionada. São gigabytes de fotos que não pertencem ao histórico. |
| Legado | Preservado em `legacy/`, fora do caminho de execução. |

## 8. Riscos operacionais conhecidos

- **`--reload` no backend trava.** O WebSocket do telão impede o uvicorn de
  encerrar o worker; o reload fica pendurado e o código antigo continua servindo.
  Rode sem `--reload` e reinicie à mão.
- **Vite só escuta em `[::1]:3000`.** Telão em outra máquina exige `host: true`
  em `vite.config.ts`.
- **Sem `.env`,** o S3Watcher inicia desligado e só a hot folder local alimenta
  o mosaico.
