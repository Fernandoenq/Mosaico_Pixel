# AGENTS.md — Mosaico Pixel

Instruções para agentes de IA que trabalham neste repositório.
Conformidade: **PICBRAND ARCH**. Detalhes em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## O que é o sistema

Telão ao vivo para eventos. As fotos tiradas na cabine sobem para um bucket S3,
o backend baixa, recorta o rosto e as posiciona num mosaico que forma a marca do
cliente. O telão anima cada foto: ela aparece grande no centro (para a pessoa se
ver) e voa até a célula dela.

## Estrutura

| Pasta | Papel |
| --- | --- |
| `backend/` | FastAPI: ingestão, motor do mosaico, WebSocket, exportação de vídeo |
| `frontend/` | Vite + React + PixiJS: painel de controle e telão |
| `tools/` | Utilitários de operação (gerador de overlay da marca) |
| `tools/dev/` | Scripts de simulação e teste manual |
| `scripts/` | Inicialização (.bat) |
| `tests/` | Testes automatizados (pytest) |
| `docs/` | Documentação do padrão, decisões e runbooks |
| `legacy/` | Sistema antigo (Tkinter) e scripts históricos de vídeo — **não usar** |
| `assets/`, `Galeria/`, `MOSAIC/`, `video/` | Mídia. Ficam no disco, fora do git |

## Regras que não podem ser quebradas

**Nunca comite credenciais.** `.env` está no gitignore; mudanças de variáveis vão
para `.env.example` sem valores.

**Nunca versione mídia nem `node_modules`.** Já estão no `.gitignore` — se
aparecerem no `git status`, algo foi adicionado com `-f`.

**O padrão do preview central (GSAP + PixiJS):** a escala é animada pelo
`ObservablePoint` (`wrapper.scale`, campos `x`/`y`), NUNCA pela propriedade
`scale` do Container. Sem o PixiPlugin, o GSAP substitui o ponto por um número,
o PIXI faz `copyFrom(1)`, a escala vira NaN e o cartão não é desenhado.

**O backend roda sem `--reload`.** O WebSocket do telão impede o uvicorn de
encerrar o worker, então o reload trava e deixa código antigo servindo em
silêncio. Depois de mexer no backend, reinicie o processo à mão.

**Health é obrigatório**: `/health`, `/ready`, `/admin/health`.

## Comandos

```bash
# backend (porta 8000)
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000

# frontend (porta 3000)
cd frontend && npm run dev

# testes / typecheck
cd backend && pytest
cd frontend && npx tsc --noEmit

# overlay da marca a partir da arte do cliente
python tools/gerar_overlay_marca.py --enviar
```

## Ao alterar algo

Atualize a documentação junto da mudança (§17 do padrão): este arquivo,
`docs/ARCHITECTURE.md` e o README quando o comportamento externo mudar.
