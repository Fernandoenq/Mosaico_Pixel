import React, { useEffect, useRef, useState } from 'react';
import * as PIXI from 'pixi.js';
import { useMosaicStore } from '../../store/mosaicStore';
import { animateMosaicOutro, animateTileFlight, applySpriteFilter, previewCardSize } from '../../utils/gsapAnimations';
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
    brushModeActive,
    selectedBrushFilter,
    paintCell,
    placedTiles,
    layers,
    targetBaseUrl,
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
    c2.zIndex = 2;
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
    drawGrid();

    return () => {
      app.destroy(true, { children: true });
      appRef.current = null;
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
        } else if (data.type === 'MOSAIC_OUTRO') {
          // Dispersa o que está na tela e só então zera o store, senão o efeito
          // de camada redesenharia os tiles por baixo da animação.
          if (landed) {
            animateMosaicOutro({
              landedContainer: landed,
              screenWidth: store.screenWidth,
              screenHeight: store.screenHeight,
              duration: store.animationDuration * 1.6,
              onComplete: () => clearMosaic(),
            });
          } else {
            clearMosaic();
          }
        } else if (data.type === 'TARGET_BASE_UPDATED') {
          if (data.payload?.url) {
            setTargetBaseUrl(data.payload.url);
          }
        } else if (data.type === 'PHOTO_INGESTED') {
          addPendingPhoto(data.payload);
        } else if (data.type === 'TILE_PLACED') {
          const payload = data.payload;
          placeTile(payload);

          if (flying && landed) {
            const texture = PIXI.Texture.from(payload.url);
            const gw = store.gridWidth > 0 ? store.gridWidth : store.screenWidth;
            const gh = store.gridHeight > 0 ? store.gridHeight : store.screenHeight;
            const tileW = gw / store.cols;
            const tileH = gh / store.rows;

            const targetX = store.gridOffsetX + payload.col * tileW;
            const targetY = store.gridOffsetY + payload.row * tileH;
            const cx = targetX + tileW / 2;
            const cy = targetY + tileH / 2;

            const cellFilter = store.cellFilters[`${payload.row}_${payload.col}`];

            if (isCellInsideContainerMask(cx, cy, store.gridOffsetX, store.gridOffsetY, gw, gh, store.gridContainerShape)) {
              animateTileFlight({
                flyingContainer: flying,
                landedContainer: landed,
                texture,
                startX: store.screenWidth / 2,
                startY: store.screenHeight / 2,
                targetX,
                targetY,
                targetWidth: tileW,
                targetHeight: tileH,
                gridShape: store.gridShape,
                preset: store.animationPreset,
                duration: store.animationDuration,
                centralPreviewDuration: store.centralPreviewDuration,
                cellFilter,
                ease: store.animationEase,
                cardSize: previewCardSize(store.screenHeight),
              });
            }
          }
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
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      ws?.close();
      setSocketConnected(false);
    };
  }, []);

  useEffect(() => {
    drawBaseImage();
  }, [targetBaseUrl, screenWidth, screenHeight]);

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
      if (!isCellInsideContainerMask(cx, cy, gridOffsetX, gridOffsetY, gw, gh, gridContainerShape)) {
        return;
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
  }, [placedTiles, cellFilters, gridOffsetX, gridOffsetY, gridWidth, gridHeight, rows, cols, gridShape, gridContainerShape, screenWidth, screenHeight]);

  useEffect(() => {
    if (!layer3Grid.current) return;
    drawGrid();
  }, [rows, cols, gridOffsetX, gridOffsetY, gridWidth, gridHeight, gridColor, gridThickness, gridOpacity, gridShape, gridContainerShape, cellFilters, placedTiles]);

  const drawGrid = () => {
    const g = layer3Grid.current;
    if (!g) return;

    g.clear();
    const hexColor = parseInt(gridColor.replace('#', '0x'), 16) || 0x00ffff;
    g.lineStyle(gridThickness, hexColor, gridOpacity);

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
      if (filterId === 'gold') colorHex = 0xffcc00;
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

    g.lineStyle(gridThickness, hexColor, gridOpacity);

    if (gridContainerShape === 'diamond_mask') {
      // Borda Externa em Formato de Losango / Diamante (HSBC Logo Bounding Diamond)
      const cx = gridOffsetX + gw / 2;
      const cy = gridOffsetY + gh / 2;
      g.lineStyle(gridThickness + 2, hexColor, Math.min(1.0, gridOpacity + 0.25));
      g.moveTo(cx, gridOffsetY);
      g.lineTo(gridOffsetX + gw, cy);
      g.lineTo(cx, gridOffsetY + gh);
      g.lineTo(gridOffsetX, cy);
      g.lineTo(cx, gridOffsetY);
      g.lineStyle(gridThickness, hexColor, gridOpacity);
    } else if (gridContainerShape === 'hexagon_mask' || gridContainerShape === 'hexagon_halftone') {
      // Borda Externa em Formato de Hexágono
      const cx = gridOffsetX + gw / 2;
      const cy = gridOffsetY + gh / 2;
      const rx = gw / 2;
      const ry = gh / 2;
      g.lineStyle(gridThickness + 2, hexColor, Math.min(1.0, gridOpacity + 0.25));
      for (let k = 0; k < 6; k++) {
        const angle = (Math.PI / 3) * k - Math.PI / 6;
        const x = cx + rx * Math.cos(angle);
        const y = cy + ry * Math.sin(angle);
        if (k === 0) g.moveTo(x, y);
        else g.lineTo(x, y);
      }
      const firstAngle = -Math.PI / 6;
      g.lineTo(cx + rx * Math.cos(firstAngle), cy + ry * Math.sin(firstAngle));
      g.lineStyle(gridThickness, hexColor, gridOpacity);
    } else if (gridContainerShape === 'circle_mask') {
      // Borda Externa em Formato Circular / Elipse
      const cx = gridOffsetX + gw / 2;
      const cy = gridOffsetY + gh / 2;
      g.lineStyle(gridThickness + 2, hexColor, Math.min(1.0, gridOpacity + 0.25));
      g.drawEllipse(cx, cy, gw / 2, gh / 2);
      g.lineStyle(gridThickness, hexColor, gridOpacity);
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

          if (!isCellInsideContainerMask(cx, cy, gridOffsetX, gridOffsetY, gw, gh, gridContainerShape)) continue;

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

          // Filtra linhas de grade para NUNCA desenhar fora do contorno da forma
          if (!isCellInsideContainerMask(cx, cy, gridOffsetX, gridOffsetY, gw, gh, gridContainerShape)) {
            continue;
          }

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

          if (!isCellInsideContainerMask(cx, cy, gridOffsetX, gridOffsetY, gw, gh, gridContainerShape)) {
            continue;
          }

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

          if (!isCellInsideContainerMask(cx, cy, gridOffsetX, gridOffsetY, gw, gh, gridContainerShape)) {
            continue;
          }

          const rad = Math.min(tileW, tileH) / 2;
          g.drawCircle(cx, cy, rad);
        }
      }
    } else {
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const cx = gridOffsetX + (c + 0.5) * tileW;
          const cy = gridOffsetY + (r + 0.5) * tileH;

          if (!isCellInsideContainerMask(cx, cy, gridOffsetX, gridOffsetY, gw, gh, gridContainerShape)) {
            continue;
          }

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

    const rect = containerRef.current.getBoundingClientRect();
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
    const rect = containerRef.current.getBoundingClientRect();
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
    const rect = containerRef.current.getBoundingClientRect();
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
    const rect = containerRef.current.getBoundingClientRect();
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
