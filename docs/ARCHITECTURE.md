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
cabine → S3 → S3Watcher (poll 5s) → hot_folder/
                                        ↓ watchdog (on_created + on_moved)
                              dedup por hash MD5
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
- A cabine publica a **mesma foto com dois nomes**; a deduplicação é por hash de
  conteúdo, não por nome.
- As chaves já importadas do S3 são **persistidas** em `storage/s3_seen.json`;
  sem isso, todo restart reimportava o bucket inteiro.

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
