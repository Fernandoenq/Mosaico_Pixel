import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { AUTO_EASE, AnimationPreset } from '../utils/gsapAnimations';

export interface Layer {
  id: string;
  name: string;
  visible: boolean;
  opacity: number;
  blur: number;
  zIndex: number;
}

export interface PendingPhoto {
  id: string;
  url: string;
  status: string;
  timestamp?: number;
}

export interface TilePlacement {
  photo_id: string;
  url: string;
  row: number;
  col: number;
  target_x: number;
  target_y: number;
  score: number;
}

export type RunState = 'idle' | 'running' | 'paused';

/**
 * Campos que compõem a RunConfig — o contrato de configuração entre painel e
 * telão. Precisa espelhar backend/app/core/run_config.py (mesmos nomes).
 */
export const RUN_CONFIG_KEYS = [
  'screenWidth',
  'screenHeight',
  'rows',
  'cols',
  'gridOffsetX',
  'gridOffsetY',
  'gridWidth',
  'gridHeight',
  'gridColor',
  'gridThickness',
  'gridOpacity',
  'gridShape',
  'gridContainerShape',
  'animationPreset',
  'animationDuration',
  'animationEase',
  'centralPreviewEnabled',
  'centralPreviewDuration',
  'previewCardScale',
  'previewGapSeconds',
  'idleReplayEnabled',
  'idleReplayDelay',
  'idleReplayInterval',
  'cellFilters',
  'customMaskCells',
  'selectedBrushFilter',
  'fillSequence',
  'autoDuplicateToFill',
  'duplicateIntervalSeconds',
  'duplicateDistLimit',
  'colorStrictness',
  'hotFolderDir',
  'autoPlaceMode',
  'targetBaseUrl',
  'foregroundUrl',
  'photosAboveBrand',
  'autoOutroOnComplete',
  'outroMode',
  'autoOutroDelaySeconds',
  'layers',
] as const;

export type RunConfigKey = (typeof RUN_CONFIG_KEYS)[number];

export interface MosaicStore {
  // Grid & Display & Telão
  screenWidth: number;
  screenHeight: number;
  rows: number;
  cols: number;
  gridOffsetX: number;
  gridOffsetY: number;
  gridWidth: number;
  gridHeight: number;
  gridColor: string;
  gridThickness: number;
  gridOpacity: number;
  gridShape: 'square' | 'diamond' | 'hexagon' | 'circle';
  gridContainerShape: 'rectangle' | 'diamond_mask' | 'hexagon_mask' | 'circle_mask' | 'hexagon_halftone' | 'auto_color_mask' | 'custom_mask';

  // Configurações de Animação & Preview Central
  animationPreset: AnimationPreset;
  animationDuration: number;
  animationEase: string;
  /** Desligado, a foto voa direto para a celula, sem cartao no centro. */
  centralPreviewEnabled: boolean;
  centralPreviewDuration: number;
  /** Lado do cartao de preview como fracao da altura do telao. */
  previewCardScale: number;
  /** Respiro entre um preview e o proximo, em segundos. */
  previewGapSeconds: number;
  /** Sem foto nova, o telao volta a destacar fotos ja pousadas. */
  idleReplayEnabled: boolean;
  /** Segundos sem foto nova ate o modo ocioso comecar. */
  idleReplayDelay: number;
  /** Pausa entre um destaque e o proximo. */
  idleReplayInterval: number;

  // Editor de Filtros & Pintura de Áreas na Grade
  cellFilters: Record<string, string>; // key: "r_c" -> filterId ('red' | 'gold' | 'cyan' | 'grayscale' | 'sepia' | 'green' | 'none')
  customMaskCells: string[]; // ['r_c', 'r_c']
  brushModeActive: boolean;
  selectedBrushFilter: string;

  // Ordem de Preenchimento & Auto-Duplicação
  fillSequence: 'color_match' | 'top_to_bottom' | 'bottom_to_top' | 'center_out' | 'random' | 'brand_first';
  autoDuplicateToFill: boolean;
  // Ritmo da duplicação gradual: uma cópia a cada N segundos.
  duplicateIntervalSeconds: number;

  duplicateDistLimit: number;
  colorStrictness: number;
  hotFolderDir: string;
  autoPlaceMode: boolean;
  targetBaseUrl: string | null;
  foregroundUrl: string | null;
  /** Fotos desenhadas POR CIMA do overlay da marca. */
  photosAboveBrand: boolean;
  /** Dispersão / Saída automática quando o mosaico estiver 100% preenchido. */
  autoOutroOnComplete: boolean;
  outroMode: 'dispersar' | 'retorno' | 'espalhar';
  autoOutroDelaySeconds: number;

  // State Arrays
  pendingPhotos: PendingPhoto[];
  approvedPhotos: PendingPhoto[];
  placedTiles: Record<string, TilePlacement>; // key: "r_c"
  lockedTiles: Set<string>; // "r_c"
  layers: Layer[];

  // Selection & Interactivity
  selectedTile: { row: number; col: number } | null;
  contextMenu: { x: number; y: number; row: number; col: number } | null;
  swapModalCell: { row: number; col: number } | null;

  // Transporte & sincronização com o backend
  runState: RunState;
  displayMode: boolean;
  lastAppliedConfig: string | null;
  socketConnected: boolean;

  // Actions
  setSocketConnected: (socketConnected: boolean) => void;
  setRunState: (runState: RunState) => void;
  setDisplayMode: (displayMode: boolean) => void;
  applyServerConfig: (config: Record<string, unknown>) => void;
  markConfigApplied: () => void;
  clearMosaic: () => void;
  setTargetBaseUrl: (url: string | null) => void;
  setForegroundUrl: (url: string | null) => void;
  setPhotosAboveBrand: (acima: boolean) => void;
  setScreenSize: (width: number, height: number) => void;
  setGridSettings: (rows: number, cols: number, distLimit: number, strictness: number) => void;
  setGridBounds: (offsetX: number, offsetY: number, width: number, height: number) => void;
  setGridStyle: (color: string, thickness: number, opacity: number) => void;
  setGridShape: (shape: 'square' | 'diamond' | 'hexagon' | 'circle') => void;
  setGridContainerShape: (shape: 'rectangle' | 'diamond_mask' | 'hexagon_mask' | 'circle_mask' | 'hexagon_halftone' | 'auto_color_mask') => void;
  setAnimationConfig: (preset: AnimationPreset, duration: number, ease: string) => void;
  setCentralPreviewDuration: (duration: number) => void;
  setCentralPreviewEnabled: (enabled: boolean) => void;
  setPreviewCardScale: (scale: number) => void;
  setPreviewGapSeconds: (segundos: number) => void;
  setIdleReplay: (enabled: boolean, delay: number, interval: number) => void;
  setBrushModeActive: (active: boolean) => void;
  setSelectedBrushFilter: (filterId: string) => void;
  setFillSequence: (seq: 'color_match' | 'top_to_bottom' | 'bottom_to_top' | 'center_out' | 'random' | 'brand_first') => void;
  setAutoDuplicateToFill: (enabled: boolean) => void;
  setDuplicateIntervalSeconds: (segundos: number) => void;
  setAutoPlaceMode: (enabled: boolean) => void;
  paintCell: (row: number, col: number, filterId?: string) => void;
  clearCellFilters: () => void;
  setLayers: (layers: Layer[]) => void;
  updateLayer: (id: string, changes: Partial<Layer>) => void;
  addPendingPhoto: (photo: PendingPhoto) => void;
  removePendingPhoto: (id: string) => void;
  placeTile: (tile: TilePlacement) => void;
  lockTile: (row: number, col: number) => void;
  unlockTile: (row: number, col: number) => void;
  deleteTile: (row: number, col: number) => void;
  setContextMenu: (menu: { x: number; y: number; row: number; col: number } | null) => void;
  setSwapModalCell: (cell: { row: number; col: number } | null) => void;
}

export type RunConfig = Pick<MosaicStore, RunConfigKey>;

/** Extrai do store apenas o que é publicado para o telão. */
export const pickRunConfig = (state: MosaicStore): RunConfig =>
  RUN_CONFIG_KEYS.reduce((acc, key) => {
    (acc as Record<string, unknown>)[key] = state[key];
    return acc;
  }, {} as RunConfig);

/**
 * Assinatura estável da config, usada para saber se há alterações pendentes de
 * aplicar. cellFilters é ordenado porque a ordem de pintura não muda o conteúdo.
 */
export const configSignature = (state: MosaicStore): string => {
  const config = pickRunConfig(state);
  const cellFilters = Object.keys(config.cellFilters)
    .sort()
    .reduce<Record<string, string>>((acc, key) => {
      acc[key] = config.cellFilters[key];
      return acc;
    }, {});
  return JSON.stringify({ ...config, cellFilters });
};

/** Mantém só as chaves conhecidas de um payload vindo do servidor. */
const sanitizeIncomingConfig = (config: Record<string, unknown>): Partial<RunConfig> => {
  const clean: Record<string, unknown> = {};
  RUN_CONFIG_KEYS.forEach((key) => {
    const value = config[key];
    if (value === undefined) return;
    if (value === null && key !== 'targetBaseUrl' && key !== 'foregroundUrl') return;
    clean[key] = value;
  });
  return clean as Partial<RunConfig>;
};

export const useMosaicStore = create<MosaicStore>()(
  persist(
    (set) => ({
      screenWidth: 1920,
      screenHeight: 1080,
      rows: 30,
      cols: 40,
      gridOffsetX: 0,
      gridOffsetY: 0,
      gridWidth: 1920,
      gridHeight: 1080,
      gridColor: "#00ffff",
      gridThickness: 2,
      gridOpacity: 0.6,
      gridShape: "diamond",
      gridContainerShape: "diamond_mask",

      animationPreset: "hsbc_cascade",
      animationDuration: 0.8,
      animationEase: AUTO_EASE,
      centralPreviewEnabled: true,
      centralPreviewDuration: 10.0,
      previewCardScale: 1.0,
      previewGapSeconds: 1.5,
      idleReplayEnabled: true,
      idleReplayDelay: 20,
      idleReplayInterval: 5,

      cellFilters: {},
      customMaskCells: [],
      brushModeActive: false,
      selectedBrushFilter: "red",

      fillSequence: "color_match",
      autoDuplicateToFill: false,
      duplicateIntervalSeconds: 3.0,

      duplicateDistLimit: 3,
      colorStrictness: 2.0,
      hotFolderDir: 'storage/hot_folder',
      autoPlaceMode: true,
      targetBaseUrl: null,
      foregroundUrl: null,
      photosAboveBrand: false,
      autoOutroOnComplete: true,
      outroMode: "dispersar",
      autoOutroDelaySeconds: 3.0,

      pendingPhotos: [],
      approvedPhotos: [],
      placedTiles: {},
      lockedTiles: new Set(),
      layers: [
        { id: "base", name: "Camada 0: Imagem Base", visible: true, opacity: 1.0, blur: 0, zIndex: 0 },
        { id: "landed", name: "Camada 1: Fotos Pousadas", visible: true, opacity: 1.0, blur: 0, zIndex: 1 },
        { id: "flying", name: "Camada 2: Foto Voadora Preview", visible: true, opacity: 1.0, blur: 0, zIndex: 2 },
        { id: "grid", name: "Camada 3: Linhas de Grade", visible: true, opacity: 0.6, blur: 0, zIndex: 3 },
        { id: "logo", name: "Camada 4: Logo Overlay", visible: true, opacity: 0.8, blur: 0, zIndex: 4 },
        { id: "text", name: "Camada 5: Texto Overlay", visible: true, opacity: 1.0, blur: 0, zIndex: 5 },
      ],

      selectedTile: null,
      contextMenu: null,
      swapModalCell: null,

      runState: 'idle',
      displayMode: false,
      lastAppliedConfig: null,
      socketConnected: false,

      setSocketConnected: (socketConnected) => set({ socketConnected }),
      setRunState: (runState) => set({ runState }),
      setDisplayMode: (displayMode) => set({ displayMode }),

      applyServerConfig: (config) =>
        set((state) => {
          const incoming = sanitizeIncomingConfig(config);
          const merged = { ...state, ...incoming } as MosaicStore;
          return { ...incoming, lastAppliedConfig: configSignature(merged) };
        }),

      markConfigApplied: () => set((state) => ({ lastAppliedConfig: configSignature(state) })),

      clearMosaic: () =>
        set({ placedTiles: {}, lockedTiles: new Set(), pendingPhotos: [], approvedPhotos: [] }),

      setTargetBaseUrl: (targetBaseUrl) => set({ targetBaseUrl }),
      setForegroundUrl: (foregroundUrl) => set({ foregroundUrl }),
      setPhotosAboveBrand: (photosAboveBrand) => set({ photosAboveBrand }),
      // Reescala o enquadramento da grade junto com o palco. Zerar para tela
      // cheia descartaria o posicionamento que o operador ajustou à mão.
      setScreenSize: (screenWidth, screenHeight) =>
        set((state) => {
          const scaleX = state.screenWidth > 0 ? screenWidth / state.screenWidth : 1;
          const scaleY = state.screenHeight > 0 ? screenHeight / state.screenHeight : 1;
          return {
            screenWidth,
            screenHeight,
            gridOffsetX: Math.round(state.gridOffsetX * scaleX),
            gridOffsetY: Math.round(state.gridOffsetY * scaleY),
            gridWidth: Math.round((state.gridWidth || state.screenWidth) * scaleX),
            gridHeight: Math.round((state.gridHeight || state.screenHeight) * scaleY),
          };
        }),

      setGridSettings: (rows, cols, duplicateDistLimit, colorStrictness) =>
        set({ rows, cols, duplicateDistLimit, colorStrictness }),

      setGridBounds: (gridOffsetX, gridOffsetY, gridWidth, gridHeight) =>
        set({ gridOffsetX, gridOffsetY, gridWidth, gridHeight }),

      setGridStyle: (gridColor, gridThickness, gridOpacity) =>
        set({ gridColor, gridThickness, gridOpacity }),

      setGridShape: (gridShape) => set({ gridShape }),
      setGridContainerShape: (gridContainerShape) => set({ gridContainerShape }),
      setAnimationConfig: (animationPreset, animationDuration, animationEase) => set({ animationPreset, animationDuration, animationEase }),
      setCentralPreviewDuration: (centralPreviewDuration) => set({ centralPreviewDuration }),
      setCentralPreviewEnabled: (centralPreviewEnabled) => set({ centralPreviewEnabled }),
      setPreviewCardScale: (previewCardScale) => set({ previewCardScale }),
      setPreviewGapSeconds: (previewGapSeconds) => set({ previewGapSeconds }),
      setIdleReplay: (idleReplayEnabled, idleReplayDelay, idleReplayInterval) =>
        set({ idleReplayEnabled, idleReplayDelay, idleReplayInterval }),

      setBrushModeActive: (brushModeActive) => set({ brushModeActive }),
      setSelectedBrushFilter: (selectedBrushFilter) => set({ selectedBrushFilter }),
      setFillSequence: (fillSequence) => set({ fillSequence }),
      setAutoDuplicateToFill: (enabled) => set({ autoDuplicateToFill: enabled, lastAppliedConfig: null }),
      setDuplicateIntervalSeconds: (segundos) =>
        set({ duplicateIntervalSeconds: segundos, lastAppliedConfig: null }),
      setAutoPlaceMode: (enabled) => set({ autoPlaceMode: enabled, lastAppliedConfig: null }),

      paintCell: (row, col, filterId) => {
        set((state) => {
          const key = `${row}_${col}`;
          const targetFilter = filterId || state.selectedBrushFilter;
          if (targetFilter === 'none' || targetFilter === 'clear') {
            const updated = { ...state.cellFilters };
            delete updated[key];
            return { cellFilters: updated };
          }
          return {
            cellFilters: {
              ...state.cellFilters,
              [key]: targetFilter,
            },
          };
        });
      },

      clearCellFilters: () => set({ cellFilters: {} }),

      setLayers: (layers) => set({ layers }),

      updateLayer: (id, changes) =>
        set((state) => ({
          layers: state.layers.map((l) => (l.id === id ? { ...l, ...changes } : l)),
        })),

      addPendingPhoto: (photo) =>
        set((state) => ({
          pendingPhotos: [photo, ...state.pendingPhotos],
        })),

      removePendingPhoto: (id) =>
        set((state) => ({
          pendingPhotos: state.pendingPhotos.filter((p) => p.id !== id),
        })),

      placeTile: (tile) =>
        set((state) => ({
          placedTiles: {
            ...state.placedTiles,
            [`${tile.row}_${tile.col}`]: tile,
          },
        })),

      lockTile: (row, col) =>
        set((state) => {
          const newLocked = new Set(state.lockedTiles);
          newLocked.add(`${row}_${col}`);
          return { lockedTiles: newLocked };
        }),

      unlockTile: (row, col) =>
        set((state) => {
          const newLocked = new Set(state.lockedTiles);
          newLocked.delete(`${row}_${col}`);
          return { lockedTiles: newLocked };
        }),

      deleteTile: (row, col) =>
        set((state) => {
          const key = `${row}_${col}`;
          const newTiles = { ...state.placedTiles };
          delete newTiles[key];
          const newLocked = new Set(state.lockedTiles);
          newLocked.delete(key);
          return { placedTiles: newTiles, lockedTiles: newLocked };
        }),

      setContextMenu: (contextMenu) => set({ contextMenu }),
      setSwapModalCell: (swapModalCell) => set({ swapModalCell }),
    }),
    {
      name: 'mosaic-studio-config-storage',
      partialize: (state) => ({
        screenWidth: state.screenWidth,
        screenHeight: state.screenHeight,
        rows: state.rows,
        cols: state.cols,
        gridOffsetX: state.gridOffsetX,
        gridOffsetY: state.gridOffsetY,
        gridWidth: state.gridWidth,
        gridHeight: state.gridHeight,
        gridColor: state.gridColor,
        gridThickness: state.gridThickness,
        gridOpacity: state.gridOpacity,
        gridShape: state.gridShape,
        gridContainerShape: state.gridContainerShape,
        animationPreset: state.animationPreset,
        animationDuration: state.animationDuration,
        animationEase: state.animationEase,
        centralPreviewEnabled: state.centralPreviewEnabled,
        centralPreviewDuration: state.centralPreviewDuration,
        previewCardScale: state.previewCardScale,
        previewGapSeconds: state.previewGapSeconds,
        idleReplayEnabled: state.idleReplayEnabled,
        idleReplayDelay: state.idleReplayDelay,
        idleReplayInterval: state.idleReplayInterval,
        cellFilters: state.cellFilters,
        customMaskCells: state.customMaskCells,
        selectedBrushFilter: state.selectedBrushFilter,
        fillSequence: state.fillSequence,
        autoDuplicateToFill: state.autoDuplicateToFill,
        duplicateIntervalSeconds: state.duplicateIntervalSeconds,
        duplicateDistLimit: state.duplicateDistLimit,
        colorStrictness: state.colorStrictness,
        targetBaseUrl: state.targetBaseUrl,
        foregroundUrl: state.foregroundUrl,
        photosAboveBrand: state.photosAboveBrand,
        hotFolderDir: state.hotFolderDir,
        layers: state.layers,
        lastAppliedConfig: state.lastAppliedConfig,
      }),
    }
  )
);
