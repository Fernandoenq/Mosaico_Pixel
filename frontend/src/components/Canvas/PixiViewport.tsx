import React, { useEffect, useRef, useState } from 'react';
import * as PIXI from 'pixi.js';
import { useMosaicStore, MosaicStore } from '../../store/mosaicStore';
import { animateMosaicOutro, animateMosaicReturn, animateTileFlight, applySpriteFilter, previewCardSize } from '../../utils/gsapAnimations';
import { MiniMap } from './MiniMap';
import { MagnifierLens } from './MagnifierLens';
import { TileContextMenu } from './TileContextMenu';
import { SwapModal } from './SwapModal';

const isCellInsideContainerMask = (
  cx: number,
  cy: number,
  ox: number,
  oy: number,
  gw: number,
  gh: number,
  shape: string
): boolean => {
  if (shape === 'rectangle') return true;
  const boxCenterX = ox + gw / 2;
  const boxCenterY = oy + gh / 2;
  const rx = gw / 2;
  const ry = gh / 2;
  if (rx <= 0 || ry <= 0) return true;

  const dx = Math.abs((cx - boxCenterX) / rx);
  const dy = Math.abs((cy - boxCenterY) / ry);

  if (shape === 'diamond_mask') {
    return dx + dy <= 1.02; // Losango HSBC
  } else if (shape === 'hexagon_mask' || shape === 'hexagon_halftone') {
    return dx <= 1.01 && dy <= 1.01 && (dx * 0.5 + dy * 0.866 <= 1.01);
  } else if (shape === 'circle_mask') {
    return dx * dx + dy * dy <= 1.04;
  }
  return true;
};

export const PixiViewport: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<PIXI.Application | null>(null);

  const {
    screenWidth,
    screenHeight,
    rows,
    cols,
    gridOffsetX,
    gridOffsetY,
    gridWidth,
    gridHeight,
    gridColor,
    gridThickness,
    gridOpacity,
    gridShape,
    gridContainerShape,
    animationPreset,
    animationDuration,
    animationEase,
    centralPreviewDuration,
    cellFilters,
    customMaskCells,
    brushModeActive,
    selectedBrushFilter,
    paintCell,
    placedTiles,
    layers,
    targetBaseUrl,
    foregroundUrl,
    photosAboveBrand,
    setTargetBaseUrl,
    setGridBounds,
    setContextMenu,
    setSwapModalCell,
    placeTile,
    addPendingPhoto,
    displayMode,
    applyServerConfig,
    setRunState,
    clearMosaic,
    setSocketConnected,
  } = useMosaicStore();

  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const [lensActive, setLensActive] = useState(false);
  const [isBrushPainting, setIsBrushPainting] = useState(false);

  // Estado para drag & resize estilo Paint das alças da grade
  const [dragState, setDragState] = useState<{
    active: boolean;
    handle: string | null;
    startX: number;
    startY: number;
    initOx: number;
    initOy: number;
    initGw: number;
    initGh: number;
  }>({
    active: false,
    handle: null,
    startX: 0,
    startY: 0,
    initOx: 0,
    initOy: 0,
    initGw: 1920,
    initGh: 1080,
  });

  // Refs para armazenar os containers ativos da instância atual do PixiJS
  const layer0Base = useRef<PIXI.Container | null>(null);
  const layer1Landed = useRef<PIXI.Container | null>(null);
  const layer2Flying = useRef<PIXI.Container | null>(null);
  const layer3Grid = useRef<PIXI.Graphics | null>(null);
  const layer4Logo = useRef<PIXI.Container | null>(null);
  const layer5Text = useRef<PIXI.Container | null>(null);

  const animationQueue = useRef<any[]>([]);
  /**
   * Ciclo de saída em curso (desfaz → remonta → segura parado).
   *
   * Enquanto está ligado a fila NÃO drena: foto que chegar espera o ciclo
   * acabar. É isso que garante os segundos de mosaico completo e imóvel na
   * tela — sem a trava, a primeira foto nova entrava voando por cima da
   * imagem final que o público está fotografando.
   */
  const outroEmCurso = useRef(false);
  /** Ação a executar depois que os ladrilhos forem redesenhados nas células. */
  const aposRemontagem = useRef<null | (() => void)>(null);
  /** Bump força o efeito de camada a redesenhar o mosaico do zero. */
  const [remontagem, setRemontagem] = useState(0);
  // Faixas de montagem em voo agora. Era um booleano — vira contador porque o
  // telão pode animar várias fotos ao mesmo tempo com o preview desligado.
  const faixasAtivas = useRef(0);
  const pendingOutro = useRef<any>(null);

  /**
   * Teto por foto antes de destravar a fila à força.
   *
   * Era fixo em 15s, mas a animação já passa disso com o preview central no
   * máximo (0,35s de entrada + 15s de hold + o voo): o guarda disparava NO MEIO
   * do preview, a fila seguia e a foto seguinte entrava por cima da que ainda
   * estava na tela — duas ao mesmo tempo. Agora o teto acompanha o que está
   * configurado, com folga.
   */
  const tempoLimiteDaAnimacao = (store: MosaicStore) => {
    const hold = store.centralPreviewEnabled ? store.centralPreviewDuration : 0;
    const previsto = 0.75 + hold + store.animationDuration * 2;
    return Math.max(15000, Math.round(previsto * 1000 * 1.5));
  };

  const drawBaseImage = () => {
    const targetUrl = useMosaicStore.getState().targetBaseUrl;
    if (!layer0Base.current || !targetUrl) return;

    const baseContainer = layer0Base.current;
    baseContainer.removeChildren();

    const texture = PIXI.Texture.from(targetUrl);
    const sprite = new PIXI.Sprite(texture);
    sprite.width = screenWidth;
    sprite.height = screenHeight;
    baseContainer.addChild(sprite);
  };

  const drawForegroundLogo = () => {
    const fgUrl = useMosaicStore.getState().foregroundUrl;
    if (!layer4Logo.current) return;
    
    const logoContainer = layer4Logo.current;
    logoContainer.removeChildren();

    if (fgUrl) {
      const texture = PIXI.Texture.from(fgUrl);
      const sprite = new PIXI.Sprite(texture);
      const { screenWidth, screenHeight } = useMosaicStore.getState();
      sprite.width = screenWidth;
      sprite.height = screenHeight;
      logoContainer.addChild(sprite);
    }
  };

  useEffect(() => {
    if (!containerRef.current) return;

    containerRef.current.innerHTML = '';

    const app = new PIXI.Application({
      width: screenWidth,
      height: screenHeight,
      backgroundColor: 0x07090e,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
    });

    const canvas = app.view as HTMLCanvasElement;
    canvas.style.maxWidth = '100%';
    canvas.style.maxHeight = '100%';
    canvas.style.objectFit = 'contain';

    containerRef.current.appendChild(canvas);
    appRef.current = app;

    app.stage.sortableChildren = true;

    const c0 = new PIXI.Container();
    const c1 = new PIXI.Container();
    const c2 = new PIXI.Container();
    const g3 = new PIXI.Graphics();
    const c4 = new PIXI.Container();
    const c5 = new PIXI.Container();

    c0.zIndex = 0;
    c1.zIndex = 1;
    c2.zIndex = 99; // Camada 2: Foto voadora (preview central) desenhada por cima de TUDO!
    g3.zIndex = 3;
    c4.zIndex = 4;
    c5.zIndex = 5;

    app.stage.addChild(c0);
    app.stage.addChild(c1);
    app.stage.addChild(c2);
    app.stage.addChild(g3);
    app.stage.addChild(c4);
    app.stage.addChild(c5);

    layer0Base.current = c0;
    layer1Landed.current = c1;
    layer2Flying.current = c2;
    layer3Grid.current = g3;
    layer4Logo.current = c4;
    layer5Text.current = c5;

    drawBaseImage();
    drawForegroundLogo();
    drawGrid();

    return () => {
      app.destroy(true, { children: true });
      appRef.current = null;
      // As refs precisam cair junto: apontando para containers já destruídos,
      // a animação rodaria sobre objetos mortos e a foto sumiria sem preview.
      layer0Base.current = null;
      layer1Landed.current = null;
      layer2Flying.current = null;
      layer3Grid.current = null;
      layer4Logo.current = null;
      layer5Text.current = null;
    };
  }, [screenWidth, screenHeight]);

  /**
   * WebSocket com ciclo de vida próprio (deps []).
   *
   * NÃO pode ficar junto do effect do palco: mudar a resolução recriaria a
   * conexão, e o INIT_STATE da reconexão sobrescreveria justamente o valor de
   * tamanho de telão que o operador acabou de digitar — o campo voltava sozinho
   * e nunca chegava a ser aplicado. As camadas são lidas por ref para que a
   * conexão sobreviva à recriação do palco.
   */
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let attempt = 0;
    let unmounted = false;

    /**
     * Anima UMA foto e resolve quando ela pousou. Todo caminho de saída pousa o
     * tile — uma textura que não carrega não pode deixar a célula em branco.
     */
    const animateOne = async (payload: any) => {
      const store = useMosaicStore.getState();
      const flying = layer2Flying.current;
      const landed = layer1Landed.current;

      if (!flying || !landed) {
        console.warn('[Mosaico] camadas ausentes — foto pousou SEM preview:', payload.photo_id);
        placeTile(payload);
        return;
      }

      let texture: PIXI.Texture | null = null;
      try {
        texture = await PIXI.Assets.load(payload.url);
      } catch {
        // `Texture.from` também lança em URL inválida — antes essa exceção
        // escapava da async function e a trava nunca era liberada.
        try {
          texture = PIXI.Texture.from(payload.url);
        } catch {
          texture = null;
        }
      }

      if (unmounted) return;

      if (!texture) {
        console.warn(`[Mosaico] Textura não carregou: ${payload.url}`);
        placeTile(payload);
        return;
      }

      const gw = store.gridWidth > 0 ? store.gridWidth : store.screenWidth;
      const gh = store.gridHeight > 0 ? store.gridHeight : store.screenHeight;
      const tileW = gw / store.cols;
      const tileH = gh / store.rows;

      const targetX = store.gridOffsetX + payload.col * tileW;
      const targetY = store.gridOffsetY + payload.row * tileH;
      const cx = targetX + tileW / 2;
      const cy = targetY + tileH / 2;

      const cellFilter = store.cellFilters[`${payload.row}_${payload.col}`];

      const dentroDaMascara = isCellInsideContainerMask(
        cx, cy, store.gridOffsetX, store.gridOffsetY, gw, gh, store.gridContainerShape,
      );

      if (!dentroDaMascara) {
        // Fora do contorno não há voo: a foto pousa direto, sem preview nenhum.
        placeTile(payload);
        return;
      }

      await new Promise<void>((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          window.clearTimeout(guard);
          placeTile(payload);
          resolve();
        };
        // Rede de segurança: se a animação nunca chamar onComplete, a fila
        // seguiria parada para sempre e o telão congelava no meio do evento.
        const guard = window.setTimeout(() => {
          console.warn('[Mosaico] Animação não completou a tempo; seguindo a fila.');
          finish();
        }, tempoLimiteDaAnimacao(store));

        try {
          animateTileFlight({
            flyingContainer: flying,
            landedContainer: landed,
            texture: texture as PIXI.Texture,
            startX: store.screenWidth / 2,
            startY: store.screenHeight / 2,
            targetX,
            targetY,
            targetWidth: tileW,
            targetHeight: tileH,
            gridShape: store.gridShape,
            preset: store.animationPreset,
            duration: store.animationDuration,
            centralPreviewEnabled: store.centralPreviewEnabled,
            centralPreviewDuration: store.centralPreviewDuration,
            cellFilter,
            ease: store.animationEase,
            cardSize: previewCardSize(store.screenHeight, store.previewCardScale),
            onComplete: finish,
          });
        } catch (e) {
          console.error('[Mosaico] animateTileFlight falhou:', e);
          finish();
        }
      });
    };

    /**
     * Ciclo de saída, quando o mosaico fica 100% cheio:
     *
     *   completo → desfaz (`modo`) → remonta completo → segura `hold` segundos
     *   parado → limpa e volta a encher.
     *
     * A remontagem não redesenha à mão: o `setRemontagem` força o efeito de
     * camada a reconstruir os ladrilhos nas células a partir de `placedTiles`,
     * que continua intacto — é por isso que o backend não apaga os tiles junto
     * com o MOSAIC_OUTRO. Só depois disso a animação de volta roda por cima.
     */
    const triggerOutroAnimation = (payload: any) => {
      const store = useMosaicStore.getState();
      const landed = layer1Landed.current;
      const hold = Number.isFinite(payload?.hold) ? Math.max(0, Number(payload.hold)) : 3;

      const finalizarCiclo = () => {
        clearMosaic();
        outroEmCurso.current = false;
        // A fila parou de drenar durante o ciclo; o que chegou nesse meio-tempo
        // entra agora, no mosaico já vazio.
        processQueue();
      };

      if (landed) {
        outroEmCurso.current = true;
        animateMosaicOutro({
          landedContainer: landed,
          screenWidth: store.screenWidth,
          screenHeight: store.screenHeight,
          duration: store.animationDuration * 1.6,
          modo: ['dispersar', 'espalhar', 'retorno'].includes(payload?.modo)
            ? payload.modo
            : 'espalhar',
          cardSize: previewCardSize(store.screenHeight, store.previewCardScale),
          onComplete: () => {
            aposRemontagem.current = () => {
              const container = layer1Landed.current;
              if (!container) {
                finalizarCiclo();
                return;
              }
              animateMosaicReturn({
                landedContainer: container,
                duration: 1.2,
                onComplete: () => {
                  window.setTimeout(finalizarCiclo, hold * 1000);
                },
              });
            };
            setRemontagem((n) => n + 1);
          },
        });
      } else {
        clearMosaic();
      }
    };

    /**
     * Quantas fotos podem voar AO MESMO TEMPO.
     *
     * Com o cartão central ligado a resposta é sempre 1: existe um só centro de
     * tela, e duas fotos ali viram aquela sobreposição que já custou caro. Com o
     * preview desligado não há esse limite — e é aí que dá para montar rápido:
     * 600 células a 3s cada levam meia hora em fila única, e um sexto disso com
     * seis voos simultâneos.
     */
    const faixasDeMontagem = (store: MosaicStore) =>
      store.centralPreviewEnabled ? 1 : Math.max(1, Math.min(8, Math.round(store.montagemSimultanea || 1)));

    /**
     * Drena a fila com N voos em paralelo. O `finally` garante que o contador
     * sempre caia: sem ele, um único erro deixava a faixa presa e o mosaico
     * parava de receber.
     */
    const faixaDeTrabalho = async () => {
      try {
        while (animationQueue.current.length > 0 && !unmounted && !outroEmCurso.current) {
          const payload = animationQueue.current.shift();
          if (!payload) continue;
          try {
            await animateOne(payload);
          } catch (e) {
            console.error('[Mosaico] Falha ao animar tile; seguindo a fila:', e);
            try {
              placeTile(payload);
            } catch {
              /* pousar é best-effort; a fila não pode parar por causa disso */
            }
          }

          // Respiro entre um preview e o próximo. Numa rajada — a duplicação
          // gradual, ou várias pessoas fotografando junto — as fotos entravam
          // coladas e ninguém acompanhava quem tinha acabado de aparecer.
          const respiro = useMosaicStore.getState().previewGapSeconds;
          if (respiro > 0 && animationQueue.current.length > 0 && !unmounted) {
            await new Promise<void>((resolve) => {
              window.setTimeout(resolve, respiro * 1000);
            });
          }
        }
      } finally {
        faixasAtivas.current -= 1;
        if (faixasAtivas.current <= 0) {
          faixasAtivas.current = 0;
          if (pendingOutro.current && animationQueue.current.length === 0 && !unmounted) {
            const outroPayload = pendingOutro.current;
            pendingOutro.current = null;
            triggerOutroAnimation(outroPayload);
          }
        }
      }
    };

    const processQueue = () => {
      // Durante o ciclo de saída a tela pertence à imagem final: nada voa.
      if (outroEmCurso.current) return;
      const limite = faixasDeMontagem(useMosaicStore.getState());
      // Só abre faixa nova se houver foto esperando por ela: abrir à toa
      // deixaria uma faixa girando em falso e atrasaria o encerramento.
      while (faixasAtivas.current < limite && animationQueue.current.length > faixasAtivas.current) {
        faixasAtivas.current += 1;
        void faixaDeTrabalho();
      }
    };

    /**
     * MODO OCIOSO — sem foto nova, o telão volta a destacar fotos que já estão
     * no mosaico.
     *
     * Numa ativação, o fluxo da cabine tem buracos (fila, troca de grupo, café)
     * e a tela ficava congelada. Aqui a foto sorteada refaz o mesmo caminho de
     * sempre: cartão no centro e voo de volta para a MESMA célula — nada é
     * duplicado e o mosaico não muda.
     */
    const ultimoTileEm = { valor: Date.now() };
    const ultimoReplayEm = { valor: 0 };
    let ultimoReplayId: string | null = null;

    const talvezDestacarFotoAntiga = () => {
      const store = useMosaicStore.getState();
      if (!store.idleReplayEnabled || store.runState !== 'running') return;
      // Só entra em cena quando não há nada de verdade acontecendo.
      if (faixasAtivas.current > 0 || animationQueue.current.length > 0) return;

      const agora = Date.now();
      if (agora - ultimoTileEm.valor < store.idleReplayDelay * 1000) return;
      if (agora - ultimoReplayEm.valor < store.idleReplayInterval * 1000) return;

      const pousadas = Object.values(store.placedTiles).filter((t) => t.url);
      if (pousadas.length === 0) return;

      // Evita repetir a mesma foto duas vezes seguidas quando há alternativa.
      let escolhida = pousadas[Math.floor(Math.random() * pousadas.length)];
      if (pousadas.length > 1 && escolhida.photo_id === ultimoReplayId) {
        const outras = pousadas.filter((t) => t.photo_id !== ultimoReplayId);
        escolhida = outras[Math.floor(Math.random() * outras.length)];
      }

      ultimoReplayId = escolhida.photo_id;
      ultimoReplayEm.valor = agora;
      animationQueue.current.push({ ...escolhida });
      processQueue();
    };

    const idleTimer = window.setInterval(talvezDestacarFotoAntiga, 1000);

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        // Valores sempre do estado atual; as actions do zustand são estáveis.
        const store = useMosaicStore.getState();
        const landed = layer1Landed.current;
        const flying = layer2Flying.current;

        if (data.type === 'INIT_STATE') {
          // Só o telão se hidrata daqui. No painel a carga inicial é feita uma
          // única vez pela TransportBar; aplicar a cada reconexão descartaria
          // as alterações ainda não publicadas.
          if (store.displayMode && data.payload?.config) {
            applyServerConfig(data.payload.config);
          }
          if (data.payload?.run_state) {
            setRunState(data.payload.run_state);
          }
          if (data.payload?.target_base_url) {
            setTargetBaseUrl(data.payload.target_base_url);
          }
          if (data.payload?.foreground_url) {
            useMosaicStore.getState().setForegroundUrl(data.payload.foreground_url);
          }
          if (Array.isArray(data.payload?.placed_tiles)) {
            data.payload.placed_tiles.forEach((tile: any) => placeTile(tile));
          }
        } else if (data.type === 'CONFIG_UPDATED') {
          // Idem: só o telão obedece a broadcast de config. O painel é o AUTOR
          // da configuração — aceitar o eco do servidor faria qualquer ação que
          // publica algo (mexer numa camada, subir um fundo) sobrescrever todo
          // o rascunho ainda não aplicado das outras abas.
          if (store.displayMode) {
            applyServerConfig(data.payload);
          }
        } else if (data.type === 'RUN_STATE_CHANGED') {
          setRunState(data.payload?.run_state ?? 'idle');
        } else if (data.type === 'MOSAIC_RESET') {
          clearMosaic();
        } else if (data.type === 'TILES_REMOVED') {
          // Desligar a duplicação esvazia só as células das cópias; as fotos
          // reais do evento continuam onde estão.
          (data.payload?.cells ?? []).forEach((cell: { row: number; col: number }) => {
            store.deleteTile(cell.row, cell.col);
          });
        } else if (data.type === 'MOSAIC_OUTRO') {
          // Dispersa o que está na tela e só então zera o store, senão o efeito
          // de camada redesenharia os tiles por baixo da animação.
          if (faixasAtivas.current > 0 || animationQueue.current.length > 0) {
            pendingOutro.current = data.payload || { modo: 'dispersar' };
          } else {
            triggerOutroAnimation(data.payload);
          }
        } else if (data.type === 'TARGET_BASE_UPDATED') {
          if (data.payload?.url) {
            setTargetBaseUrl(data.payload.url);
          }
        } else if (data.type === 'PHOTO_INGESTED') {
          addPendingPhoto(data.payload);
        } else if (data.type === 'TILE_PLACED') {
          // Só foto vinda do backend adia o modo ocioso; o destaque de uma foto
          // antiga não pode reiniciar o próprio relógio, senão nunca repetiria.
          ultimoTileEm.valor = Date.now();
          animationQueue.current.push(data.payload);
          processQueue();
        }
      } catch (e) {
        console.error('WS Error:', e);
      }
    };

    /**
     * Reconexão com backoff. Num evento ao vivo o telão TEM que voltar sozinho
     * se o backend reiniciar — sem isso o socket morre calado, o HTTP continua
     * funcionando e as fotos param de aparecer sem nenhum sinal na tela.
     */
    const connect = () => {
      if (unmounted) return;

      // Mesma origem: o Vite (dev) e o backend (prod) já servem /ws, então o
      // telão funciona em outra máquina sem precisar da porta 8000 exposta.
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);

      ws.onopen = () => {
        attempt = 0;
        setSocketConnected(true);
      };

      ws.onmessage = handleMessage;

      ws.onclose = () => {
        setSocketConnected(false);
        if (unmounted) return;
        const delay = Math.min(15000, 500 * 2 ** attempt);
        attempt += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      };

      ws.onerror = () => ws?.close();
    };

    connect();

    return () => {
      unmounted = true;
      // O ref sobrevive ao remount do effect (StrictMode em dev): sem este reset
      // a próxima montagem herdava a trava e nunca processava a fila.
      faixasAtivas.current = 0;
      window.clearInterval(idleTimer);
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      ws?.close();
      setSocketConnected(false);
    };
  }, []);

  useEffect(() => {
    drawBaseImage();
  }, [targetBaseUrl, screenWidth, screenHeight]);

  useEffect(() => {
    drawForegroundLogo();
  }, [foregroundUrl, screenWidth, screenHeight]);

  /**
   * Fotos por cima ou por baixo do logo.
   *
   * Por baixo (padrão) o logo é a moldura e o mosaico só aparece pelos recortes
   * dele. Por cima o mosaico vai cobrindo a marca conforme enche — o logo
   * começa inteiro e some atrás das fotos.
   *
   * A camada voadora (99) fica acima dos dois nos dois casos: o cartão central
   * não pode ter o logo atravessado no rosto de quem acabou de se fotografar.
   */
  useEffect(() => {
    const pousadas = layer1Landed.current;
    if (pousadas) pousadas.zIndex = photosAboveBrand ? 6 : 1;
  }, [photosAboveBrand]);

  /**
   * No painel a grade sobe para cima do overlay da marca; no telão volta para o
   * lugar dela. Com um overlay opaco na Camada 4, a grade (Camada 3) ficava
   * escondida atrás dele e não dava para enxergar onde as fotos vão cair.
   */
  useEffect(() => {
    const grade = layer3Grid.current;
    if (grade) grade.zIndex = displayMode ? 3 : 98;
    drawGrid();
  }, [displayMode, foregroundUrl]);

  useEffect(() => {
    const layerMap: Record<string, PIXI.Container | PIXI.Graphics | null> = {
      base: layer0Base.current,
      landed: layer1Landed.current,
      flying: layer2Flying.current,
      grid: layer3Grid.current,
      logo: layer4Logo.current,
      text: layer5Text.current,
    };

    layers.forEach((l) => {
      const target = layerMap[l.id];
      if (target) {
        target.visible = l.visible;
        target.alpha = l.opacity;
      }
    });
  }, [layers]);

  useEffect(() => {
    if (!layer1Landed.current) return;
    const landedContainer = layer1Landed.current;
    landedContainer.removeChildren();

    const gw = gridWidth > 0 ? gridWidth : screenWidth;
    const gh = gridHeight > 0 ? gridHeight : screenHeight;
    const tileW = gw / cols;
    const tileH = gh / rows;

    Object.values(placedTiles).forEach((tile) => {
      const targetX = gridOffsetX + tile.col * tileW;
      const targetY = gridOffsetY + tile.row * tileH;
      const cx = targetX + tileW / 2;
      const cy = targetY + tileH / 2;

      // Filtra fotos para que NUNCA apareçam fora do contorno da forma
      if (gridContainerShape === 'custom_mask') {
        if (!customMaskCells.includes(`${tile.row}_${tile.col}`)) {
          return;
        }
      } else {
        if (!isCellInsideContainerMask(cx, cy, gridOffsetX, gridOffsetY, gw, gh, gridContainerShape)) {
          return;
        }
      }

      const texture = PIXI.Texture.from(tile.url);

      // Sub-container garante que sprite e máscara ficam no mesmo espaço de coordenadas
      const tileContainer = new PIXI.Container();
      tileContainer.x = targetX;
      tileContainer.y = targetY;

      const landedSprite = new PIXI.Sprite(texture);
      // x=0, y=0 relativo ao tileContainer
      landedSprite.x = 0;
      landedSprite.y = 0;
      landedSprite.width = tileW;
      landedSprite.height = tileH;

      // Aplica o filtro de cor da célula (se houver pintura de área)
      const cellFilter = cellFilters[`${tile.row}_${tile.col}`];
      applySpriteFilter(landedSprite, cellFilter);

      if (gridShape === 'diamond') {
        const mask = new PIXI.Graphics();
        mask.beginFill(0xffffff);
        const hw = tileW / 2;
        const hh = tileH / 2;
        // Coords relativas ao tileContainer (origem 0,0)
        mask.moveTo(hw, 0);
        mask.lineTo(tileW, hh);
        mask.lineTo(hw, tileH);
        mask.lineTo(0, hh);
        mask.lineTo(hw, 0);
        mask.endFill();
        tileContainer.addChild(landedSprite);
        tileContainer.addChild(mask);
        landedSprite.mask = mask;
      } else if (gridShape === 'hexagon') {
        const mask = new PIXI.Graphics();
        mask.beginFill(0xffffff);
        const mcx = tileW / 2;
        const mcy = tileH / 2;
        const rad = Math.min(tileW, tileH) / 2;
        for (let k = 0; k < 6; k++) {
          const angle = (Math.PI / 3) * k - Math.PI / 6;
          const x = mcx + rad * Math.cos(angle);
          const y = mcy + rad * Math.sin(angle);
          if (k === 0) mask.moveTo(x, y);
          else mask.lineTo(x, y);
        }
        mask.endFill();
        tileContainer.addChild(landedSprite);
        tileContainer.addChild(mask);
        landedSprite.mask = mask;
      } else if (gridShape === 'circle') {
        const mask = new PIXI.Graphics();
        mask.beginFill(0xffffff);
        const rad = Math.min(tileW, tileH) / 2;
        mask.drawCircle(tileW / 2, tileH / 2, rad);
        mask.endFill();
        tileContainer.addChild(landedSprite);
        tileContainer.addChild(mask);
        landedSprite.mask = mask;
      } else {
        tileContainer.addChild(landedSprite);
      }

      landedContainer.addChild(tileContainer);
    });
    // `remontagem` entra aqui para o ciclo de saída conseguir reconstruir os
    // ladrilhos depois que a dispersão esvaziou o container. `placedTiles` não
    // muda nessa hora, então sem este contador o efeito não rodaria de novo.
  }, [placedTiles, cellFilters, gridOffsetX, gridOffsetY, gridWidth, gridHeight, rows, cols, gridShape, gridContainerShape, screenWidth, screenHeight, customMaskCells, remontagem]);

  /**
   * Roda a animação de volta DEPOIS que o efeito acima redesenhou os ladrilhos.
   * A ordem importa: declarado após o efeito de camada, este roda em seguida no
   * mesmo commit, com os filhos já no container.
   */
  useEffect(() => {
    if (remontagem === 0) return;
    const acao = aposRemontagem.current;
    aposRemontagem.current = null;
    acao?.();
  }, [remontagem]);

  useEffect(() => {
    if (!layer3Grid.current) return;
    drawGrid();
  }, [rows, cols, gridOffsetX, gridOffsetY, gridWidth, gridHeight, gridColor, gridThickness, gridOpacity, gridShape, gridContainerShape, cellFilters, customMaskCells, placedTiles]);

  const drawGrid = () => {
    const g = layer3Grid.current;
    if (!g) return;

    g.clear();
    const hexColor = parseInt(gridColor.replace('#', '0x'), 16) || 0x00ffff;

    /**
     * No painel a grade é a ferramenta de trabalho: precisa ser visível mesmo
     * com a opacidade zerada para o telão. Com um overlay de marca por cima,
     * sem isso o operador fica sem nenhuma referência de onde as fotos caem.
     * No telão o valor da config é respeitado como está.
     */
    const opacidadeGrade = displayMode ? gridOpacity : Math.max(0.55, gridOpacity);
    g.lineStyle(gridThickness, hexColor, opacidadeGrade);

    /**
     * Uma célula só é desenhada se estiver dentro do contorno em vigor.
     *
     * `isCellInsideContainerMask` não sabe nada sobre `custom_mask` — ela cai no
     * `return true` final. Cada forma precisava tratar esse caso, e só losango e
     * hexágono tratavam: com quadrado ou círculo a grade era desenhada inteira,
     * ignorando o recorte no logo.
     */
    const celulaVisivel = (r: number, c: number, cx: number, cy: number): boolean => {
      if (gridContainerShape === 'custom_mask') {
        return customMaskCells.includes(`${r}_${c}`);
      }
      return isCellInsideContainerMask(
        cx, cy, gridOffsetX, gridOffsetY,
        gridWidth > 0 ? gridWidth : screenWidth,
        gridHeight > 0 ? gridHeight : screenHeight,
        gridContainerShape,
      );
    };

    const gw = gridWidth > 0 ? gridWidth : screenWidth;
    const gh = gridHeight > 0 ? gridHeight : screenHeight;

    const tileW = gw / cols;
    const tileH = gh / rows;

    // 🎨 INDICADOR VISUAL DAS CÉLULAS PINTADAS COM O PINCEL (CAMADA 3 DE GRADE)
    Object.entries(cellFilters).forEach(([key, filterId]) => {
      if (!filterId || filterId === 'none') return;
      const [rStr, cStr] = key.split('_');
      const r = parseInt(rStr, 10);
      const c = parseInt(cStr, 10);

      if (r < 0 || r >= rows || c < 0 || c >= cols) return;
      if (placedTiles[`${r}_${c}`]) return; // Fotos pousadas cobrem o indicador

      const targetX = gridOffsetX + c * tileW;
      const targetY = gridOffsetY + r * tileH;
      const cx = targetX + tileW / 2;
      const cy = targetY + tileH / 2;

      if (!isCellInsideContainerMask(cx, cy, gridOffsetX, gridOffsetY, gw, gh, gridContainerShape)) return;

      let colorHex = 0xff0044;
      if (filterId === 'red_suave') colorHex = 0xff8899;
      else if (filterId === 'branco_leve') colorHex = 0xf2f4f8;
      else if (filterId === 'gold') colorHex = 0xffcc00;
      else if (filterId === 'cyan') colorHex = 0x00ffff;
      else if (filterId === 'green') colorHex = 0x00ff66;
      else if (filterId === 'sepia') colorHex = 0xffb380;
      else if (filterId === 'grayscale') colorHex = 0xaaaaaa;

      g.beginFill(colorHex, 0.40);
      g.lineStyle(1.5, colorHex, 0.85);

      if (gridShape === 'diamond') {
        const hw = tileW / 2;
        const hh = tileH / 2;
        g.moveTo(cx, cy - hh);
        g.lineTo(cx + hw, cy);
        g.lineTo(cx, cy + hh);
        g.lineTo(cx - hw, cy);
        g.lineTo(cx, cy - hh);
      } else if (gridShape === 'hexagon') {
        const rad = Math.min(tileW, tileH) / 2;
        for (let k = 0; k < 6; k++) {
          const angle = (Math.PI / 3) * k - Math.PI / 6;
          const x = cx + rad * Math.cos(angle);
          const y = cy + rad * Math.sin(angle);
          if (k === 0) g.moveTo(x, y);
          else g.lineTo(x, y);
        }
      } else if (gridShape === 'circle') {
        g.drawCircle(cx, cy, Math.min(tileW, tileH) / 2);
      } else {
        g.drawRect(targetX, targetY, tileW, tileH);
      }
      g.endFill();
    });

    g.lineStyle(gridThickness, hexColor, opacidadeGrade);

    if (gridContainerShape === 'diamond_mask') {
      // Borda Externa em Formato de Losango / Diamante (HSBC Logo Bounding Diamond)
      const cx = gridOffsetX + gw / 2;
      const cy = gridOffsetY + gh / 2;
      g.lineStyle(gridThickness + 2, hexColor, Math.min(1.0, opacidadeGrade + 0.25));
      g.moveTo(cx, gridOffsetY);
      g.lineTo(gridOffsetX + gw, cy);
      g.lineTo(cx, gridOffsetY + gh);
      g.lineTo(gridOffsetX, cy);
      g.lineTo(cx, gridOffsetY);
      g.lineStyle(gridThickness, hexColor, opacidadeGrade);
    } else if (gridContainerShape === 'hexagon_mask' || gridContainerShape === 'hexagon_halftone') {
      // Borda Externa em Formato de Hexágono
      const cx = gridOffsetX + gw / 2;
      const cy = gridOffsetY + gh / 2;
      const rx = gw / 2;
      const ry = gh / 2;
      g.lineStyle(gridThickness + 2, hexColor, Math.min(1.0, opacidadeGrade + 0.25));
      for (let k = 0; k < 6; k++) {
        const angle = (Math.PI / 3) * k - Math.PI / 6;
        const x = cx + rx * Math.cos(angle);
        const y = cy + ry * Math.sin(angle);
        if (k === 0) g.moveTo(x, y);
        else g.lineTo(x, y);
      }
      const firstAngle = -Math.PI / 6;
      g.lineTo(cx + rx * Math.cos(firstAngle), cy + ry * Math.sin(firstAngle));
      g.lineStyle(gridThickness, hexColor, opacidadeGrade);
    } else if (gridContainerShape === 'circle_mask') {
      // Borda Externa em Formato Circular / Elipse
      const cx = gridOffsetX + gw / 2;
      const cy = gridOffsetY + gh / 2;
      g.lineStyle(gridThickness + 2, hexColor, Math.min(1.0, opacidadeGrade + 0.25));
      g.drawEllipse(cx, cy, gw / 2, gh / 2);
      g.lineStyle(gridThickness, hexColor, opacidadeGrade);
    } else {
      // Borda Retangular Padrão
      g.drawRect(gridOffsetX, gridOffsetY, gw, gh);
    }

    if (gridContainerShape === 'hexagon_halftone') {
      // 🔷 MEIO-TOM GRADIENTE HEXAGONAL (Halftone Gradient: Pontos grandes nas pontas externas, pequenos no centro)
      const boxCenterX = gridOffsetX + gw / 2;
      const boxCenterY = gridOffsetY + gh / 2;
      const rx = gw / 2;
      const ry = gh / 2;

      for (let r = 0; r < rows; r++) {
        const rowOffset = r % 2 === 1 ? tileW / 2 : 0;
        for (let c = 0; c < cols; c++) {
          const cx = gridOffsetX + c * tileW + rowOffset + tileW / 2;
          const cy = gridOffsetY + r * (tileH * 0.75) + tileH / 2;

          if (!celulaVisivel(r, c, cx, cy)) continue;

          const dx = (cx - boxCenterX) / (rx || 1);
          const dy = (cy - boxCenterY) / (ry || 1);
          const normDist = Math.hypot(dx, dy);

          const halftoneScale = Math.min(1.0, Math.max(0.12, Math.pow(normDist, 1.3)));
          const rad = (Math.min(tileW, tileH) / 2) * halftoneScale;

          g.drawCircle(cx, cy, rad);
        }
      }
    } else if (gridShape === 'diamond') {
      // 💎 FORMA GEOMÉTRICA INTERNA: LOSANGOS (45° Diagonal - Padrão HSBC)
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const cx = gridOffsetX + (c + 0.5) * tileW;
          const cy = gridOffsetY + (r + 0.5) * tileH;

          if (!celulaVisivel(r, c, cx, cy)) continue;

          const hw = tileW / 2;
          const hh = tileH / 2;

          g.moveTo(cx, cy - hh);
          g.lineTo(cx + hw, cy);
          g.lineTo(cx, cy + hh);
          g.lineTo(cx - hw, cy);
          g.lineTo(cx, cy - hh);
        }
      }
    } else if (gridShape === 'hexagon') {
      for (let r = 0; r < rows; r++) {
        const rowOffset = r % 2 === 1 ? tileW / 2 : 0;
        for (let c = 0; c < cols; c++) {
          const cx = gridOffsetX + c * tileW + rowOffset + tileW / 2;
          const cy = gridOffsetY + r * (tileH * 0.75) + tileH / 2;

          if (!celulaVisivel(r, c, cx, cy)) continue;

          const rad = Math.min(tileW, tileH) / 2;

          for (let k = 0; k < 6; k++) {
            const angle = (Math.PI / 3) * k - Math.PI / 6;
            const x = cx + rad * Math.cos(angle);
            const y = cy + rad * Math.sin(angle);
            if (k === 0) g.moveTo(x, y);
            else g.lineTo(x, y);
          }
          const firstAngle = -Math.PI / 6;
          g.lineTo(cx + rad * Math.cos(firstAngle), cy + rad * Math.sin(firstAngle));
        }
      }
    } else if (gridShape === 'circle') {
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const cx = gridOffsetX + (c + 0.5) * tileW;
          const cy = gridOffsetY + (r + 0.5) * tileH;

          if (!celulaVisivel(r, c, cx, cy)) continue;

          const rad = Math.min(tileW, tileH) / 2;
          g.drawCircle(cx, cy, rad);
        }
      }
    } else {
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const cx = gridOffsetX + (c + 0.5) * tileW;
          const cy = gridOffsetY + (r + 0.5) * tileH;

          if (!celulaVisivel(r, c, cx, cy)) continue;

          const x = gridOffsetX + c * tileW;
          const y = gridOffsetY + r * tileH;
          g.drawRect(x, y, tileW, tileH);
        }
      }
    }
  };

  // --- INTERACTION & PAINT-STYLE MOUSE RESIZING HANDLES ---

  const handleHandleMouseDown = (e: React.MouseEvent, handle: string) => {
    e.stopPropagation();
    e.preventDefault();
    setDragState({
      active: true,
      handle,
      startX: e.clientX,
      startY: e.clientY,
      initOx: gridOffsetX,
      initOy: gridOffsetY,
      initGw: gridWidth,
      initGh: gridHeight,
    });
  };

  const handleGlobalMouseMove = (e: React.MouseEvent) => {
    setMousePos({ x: e.clientX, y: e.clientY });

    if (!dragState.active || !containerRef.current) return;

    const target = containerRef.current.querySelector('canvas') || containerRef.current;
    const rect = target.getBoundingClientRect();
    const scaleX = screenWidth / rect.width;
    const scaleY = screenHeight / rect.height;

    const dx = (e.clientX - dragState.startX) * scaleX;
    const dy = (e.clientY - dragState.startY) * scaleY;

    let newOx = dragState.initOx;
    let newOy = dragState.initOy;
    let newGw = dragState.initGw;
    let newGh = dragState.initGh;

    const h = dragState.handle;

    if (h === 'move') {
      newOx = Math.max(0, Math.min(screenWidth - newGw, dragState.initOx + dx));
      newOy = Math.max(0, Math.min(screenHeight - newGh, dragState.initOy + dy));
    } else {
      if (h?.includes('w')) {
        const maxDx = dragState.initGw - 100;
        const clampedDx = Math.min(dx, maxDx);
        newOx = dragState.initOx + clampedDx;
        newGw = dragState.initGw - clampedDx;
      }
      if (h?.includes('e')) {
        newGw = Math.max(100, dragState.initGw + dx);
      }
      if (h?.includes('n')) {
        const maxDy = dragState.initGh - 100;
        const clampedDy = Math.min(dy, maxDy);
        newOy = dragState.initOy + clampedDy;
        newGh = dragState.initGh - clampedDy;
      }
      if (h?.includes('s')) {
        newGh = Math.max(100, dragState.initGh + dy);
      }
    }

    setGridBounds(Math.round(newOx), Math.round(newOy), Math.round(newGw), Math.round(newGh));
  };

  const handleGlobalMouseUp = () => {
    if (dragState.active) {
      setDragState((prev) => ({ ...prev, active: false, handle: null }));
    }
  };

  const handleCanvasContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!containerRef.current) return;
    const target = containerRef.current.querySelector('canvas') || containerRef.current;
    const rect = target.getBoundingClientRect();
    const scaleX = screenWidth / rect.width;
    const scaleY = screenHeight / rect.height;

    const clickX = (e.clientX - rect.left) * scaleX;
    const clickY = (e.clientY - rect.top) * scaleY;

    const gw = gridWidth > 0 ? gridWidth : screenWidth;
    const gh = gridHeight > 0 ? gridHeight : screenHeight;
    const tileW = gw / cols;
    const tileH = gh / rows;

    const col = Math.floor((clickX - gridOffsetX) / tileW);
    const row = Math.floor((clickY - gridOffsetY) / tileH);

    if (col >= 0 && col < cols && row >= 0 && row < rows) {
      setContextMenu({ x: e.clientX, y: e.clientY, row, col });
    }
  };

  const paintCellFromMouseEvent = (e: React.MouseEvent) => {
    if (!containerRef.current) return;
    const target = containerRef.current.querySelector('canvas') || containerRef.current;
    const rect = target.getBoundingClientRect();
    const scaleX = screenWidth / rect.width;
    const scaleY = screenHeight / rect.height;

    const clickX = (e.clientX - rect.left) * scaleX;
    const clickY = (e.clientY - rect.top) * scaleY;

    const gw = gridWidth > 0 ? gridWidth : screenWidth;
    const gh = gridHeight > 0 ? gridHeight : screenHeight;
    const tileW = gw / cols;
    const tileH = gh / rows;

    const col = Math.floor((clickX - gridOffsetX) / tileW);
    const row = Math.floor((clickY - gridOffsetY) / tileH);

    if (col >= 0 && col < cols && row >= 0 && row < rows) {
      paintCell(row, col);
    }
  };

  const handleCanvasMouseDown = (e: React.MouseEvent) => {
    if (brushModeActive) {
      setIsBrushPainting(true);
      paintCellFromMouseEvent(e);
    }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent) => {
    if (brushModeActive && isBrushPainting) {
      paintCellFromMouseEvent(e);
    }
  };

  const handleCanvasMouseUp = () => {
    if (isBrushPainting) {
      setIsBrushPainting(false);
    }
  };

  const handleCanvasClick = (e: React.MouseEvent) => {
    if (brushModeActive) {
      paintCellFromMouseEvent(e);
      return;
    }
    if (dragState.active || !containerRef.current) return;
    const target = containerRef.current.querySelector('canvas') || containerRef.current;
    const rect = target.getBoundingClientRect();
    const scaleX = screenWidth / rect.width;
    const scaleY = screenHeight / rect.height;

    const clickX = (e.clientX - rect.left) * scaleX;
    const clickY = (e.clientY - rect.top) * scaleY;

    const gw = gridWidth > 0 ? gridWidth : screenWidth;
    const gh = gridHeight > 0 ? gridHeight : screenHeight;
    const tileW = gw / cols;
    const tileH = gh / rows;

    const col = Math.floor((clickX - gridOffsetX) / tileW);
    const row = Math.floor((clickY - gridOffsetY) / tileH);

    if (col >= 0 && col < cols && row >= 0 && row < rows) {
      setSwapModalCell({ row, col });
    }
  };

  // Cálculo da caixa delimitadora em porcentagem da Viewport para sobreposição das alças no DOM
  const leftPct = (gridOffsetX / screenWidth) * 100;
  const topPct = (gridOffsetY / screenHeight) * 100;
  const widthPct = (gridWidth / screenWidth) * 100;
  const heightPct = (gridHeight / screenHeight) * 100;

  return (
    <div
      className={`relative w-full h-full flex items-center justify-center overflow-hidden select-none ${
        displayMode ? 'bg-black' : 'bg-slate-950 p-4'
      }`}
      onMouseMove={displayMode ? undefined : handleGlobalMouseMove}
      onMouseUp={displayMode ? undefined : handleGlobalMouseUp}
      onMouseEnter={displayMode ? undefined : () => setLensActive(true)}
      onMouseLeave={displayMode ? undefined : () => setLensActive(false)}
    >
      <div className="relative max-w-full max-h-full flex items-center justify-center">
        {/* Canvas PixiJS WebGL */}
        <div
          ref={containerRef}
          onContextMenu={displayMode ? undefined : handleCanvasContextMenu}
          onClick={displayMode ? undefined : handleCanvasClick}
          onMouseDown={displayMode ? undefined : handleCanvasMouseDown}
          onMouseMove={displayMode ? undefined : handleCanvasMouseMove}
          onMouseUp={displayMode ? undefined : handleCanvasMouseUp}
          className={
            displayMode
              ? 'overflow-hidden bg-black'
              : `cursor-crosshair shadow-2xl border rounded-lg overflow-hidden bg-slate-900 ${
                  brushModeActive ? 'ring-2 ring-emerald-400 border-emerald-500' : 'border-slate-800'
                }`
          }
        />

        {/* OVERLAY INTERATIVO ESTILO PAINT: ALÇAS DE DIMENSIONAMENTO E MOVIMENTO DAS FORMAS */}
        {!displayMode && (
        <div
          style={{
            left: `${leftPct}%`,
            top: `${topPct}%`,
            width: `${widthPct}%`,
            height: `${heightPct}%`,
          }}
          onMouseDown={(e) => !brushModeActive && handleHandleMouseDown(e, 'move')}
          className={`absolute border-2 border-dashed border-cyan-400/80 cursor-move group z-20 ${
            brushModeActive ? 'pointer-events-none opacity-30' : 'pointer-events-auto'
          }`}
        >
          {/* Indicador Central de Mover */}
          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition bg-cyan-950/20 pointer-events-none">
            <span className="text-[10px] font-mono text-cyan-300 bg-slate-900/90 px-2 py-0.5 rounded border border-cyan-500/50">
              Arraste para Mover Grade
            </span>
          </div>

          {/* 8 Alças Quadradas estilo Paint nas bordas e vértices */}
          {/* Top-Left NW */}
          <div
            onMouseDown={(e) => handleHandleMouseDown(e, 'nw')}
            className="absolute -top-1.5 -left-1.5 w-3.5 h-3.5 bg-cyan-400 border border-slate-950 rounded-sm cursor-nwse-resize shadow-md hover:scale-125 transition"
          />
          {/* Top-Center N */}
          <div
            onMouseDown={(e) => handleHandleMouseDown(e, 'n')}
            className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3.5 h-3.5 bg-cyan-400 border border-slate-950 rounded-sm cursor-ns-resize shadow-md hover:scale-125 transition"
          />
          {/* Top-Right NE */}
          <div
            onMouseDown={(e) => handleHandleMouseDown(e, 'ne')}
            className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 bg-cyan-400 border border-slate-950 rounded-sm cursor-nesw-resize shadow-md hover:scale-125 transition"
          />
          {/* Right-Center E */}
          <div
            onMouseDown={(e) => handleHandleMouseDown(e, 'e')}
            className="absolute top-1/2 -right-1.5 -translate-y-1/2 w-3.5 h-3.5 bg-cyan-400 border border-slate-950 rounded-sm cursor-ew-resize shadow-md hover:scale-125 transition"
          />
          {/* Bottom-Right SE */}
          <div
            onMouseDown={(e) => handleHandleMouseDown(e, 'se')}
            className="absolute -bottom-1.5 -right-1.5 w-3.5 h-3.5 bg-cyan-400 border border-slate-950 rounded-sm cursor-nwse-resize shadow-md hover:scale-125 transition"
          />
          {/* Bottom-Center S */}
          <div
            onMouseDown={(e) => handleHandleMouseDown(e, 's')}
            className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3.5 h-3.5 bg-cyan-400 border border-slate-950 rounded-sm cursor-ns-resize shadow-md hover:scale-125 transition"
          />
          {/* Bottom-Left SW */}
          <div
            onMouseDown={(e) => handleHandleMouseDown(e, 'sw')}
            className="absolute -bottom-1.5 -left-1.5 w-3.5 h-3.5 bg-cyan-400 border border-slate-950 rounded-sm cursor-nesw-resize shadow-md hover:scale-125 transition"
          />
          {/* Left-Center W */}
          <div
            onMouseDown={(e) => handleHandleMouseDown(e, 'w')}
            className="absolute top-1/2 -left-1.5 -translate-y-1/2 w-3.5 h-3.5 bg-cyan-400 border border-slate-950 rounded-sm cursor-ew-resize shadow-md hover:scale-125 transition"
          />
        </div>
        )}
      </div>

      {/* Ferramentas de edição: só no painel, nunca no telão */}
      {!displayMode && (
        <>
          <MiniMap />
          <MagnifierLens mousePos={mousePos} active={lensActive} />
          <TileContextMenu />
          <SwapModal />
        </>
      )}
    </div>
  );
};
