import React, { useState } from 'react';
import { useMosaicStore } from '../../store/mosaicStore';
import { Monitor, Grid, FolderOpen, Image as ImageIcon, Upload, Check, Sliders, Move, Save } from 'lucide-react';

export const IngestionPanel: React.FC = () => {
  const {
    rows,
    cols,
    screenWidth,
    screenHeight,
    gridOffsetX,
    gridOffsetY,
    gridWidth,
    gridHeight,
    gridColor,
    gridThickness,
    gridOpacity,
    gridShape,
    gridContainerShape,
    duplicateDistLimit,
    colorStrictness,
    hotFolderDir,
    targetBaseUrl,
    setTargetBaseUrl,
    setScreenSize,
    setGridSettings,
    setGridBounds,
    setGridStyle,
    setGridShape,
    setGridContainerShape,
  } = useMosaicStore();

  const [localRows, setLocalRows] = useState(rows);
  const [localCols, setLocalCols] = useState(cols);
  const [localWidth, setLocalWidth] = useState(screenWidth);
  const [localHeight, setLocalHeight] = useState(screenHeight);
  
  const [localOffsetX, setLocalOffsetX] = useState(gridOffsetX);
  const [localOffsetY, setLocalOffsetY] = useState(gridOffsetY);
  const [localGridW, setLocalGridW] = useState(gridWidth);
  const [localGridH, setLocalGridH] = useState(gridHeight);

  const [hotFolderInput, setHotFolderInput] = useState(hotFolderDir);
  const [brandImages, setBrandImages] = useState<string[]>([]);
  const [uploadingTarget, setUploadingTarget] = useState(false);
  const [generatingPhotos, setGeneratingPhotos] = useState(false);

  const handleGalleryTestPhotos = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;
    setGeneratingPhotos(true);
    const files = Array.from(e.target.files).slice(0, 5); // Limit to 5 photos as requested
    
    for (let i = 0; i < files.length; i++) {
      const formData = new FormData();
      formData.append('file', files[i]);
      try {
        await fetch('/api/ingest/upload', { method: 'POST', body: formData });
      } catch (e) {
        console.error(e);
      }
    }
    setGeneratingPhotos(false);
    // Clear input
    e.target.value = '';
  };

  const handleSelectFolder = async () => {
    try {
      const res = await fetch('/api/system/select-folder');
      const data = await res.json();
      if (data.path) {
        setHotFolderInput(data.path);
        // Atualiza a config no backend, o que vai recriar o watcher
        await fetch('/api/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ hotFolderDir: data.path })
        });
      }
    } catch (err) {
      console.error('Erro ao selecionar pasta:', err);
    }
  };

  /** Reflete no painel o enquadramento que o store reescalou. */
  const syncLocalBoundsFromStore = () => {
    const s = useMosaicStore.getState();
    setLocalOffsetX(s.gridOffsetX);
    setLocalOffsetY(s.gridOffsetY);
    setLocalGridW(s.gridWidth);
    setLocalGridH(s.gridHeight);
  };

  const handleApplyScreenSize = (w: number, h: number) => {
    setLocalWidth(w);
    setLocalHeight(h);
    setScreenSize(w, h);
    syncLocalBoundsFromStore();
  };

  /**
   * Comita a resolução só ao sair do campo ou no Enter. Aplicar a cada tecla
   * recriaria o palco PixiJS a cada dígito ("3", "38", "384", "3840").
   */
  const commitScreenSize = () => {
    const w = Math.min(16384, Math.max(320, localWidth || screenWidth));
    const h = Math.min(16384, Math.max(240, localHeight || screenHeight));
    setLocalWidth(w);
    setLocalHeight(h);
    if (w !== screenWidth || h !== screenHeight) {
      setScreenSize(w, h);
      syncLocalBoundsFromStore();
    }
  };

  const handlePresetChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (val === '1920x1080') handleApplyScreenSize(1920, 1080);
    else if (val === '3840x2160') handleApplyScreenSize(3840, 2160);
    else if (val === '1080x1920') handleApplyScreenSize(1080, 1920);
    else if (val === '3840x1080') handleApplyScreenSize(3840, 1080);
  };

  // Só rascunho local — quem publica no telão é o "Aplicar" da barra superior.
  const handleApplyGrid = () => {
    setGridSettings(localRows, localCols, duplicateDistLimit, colorStrictness);
  };

  const handleGridPreset = (rows: number, cols: number) => {
    setLocalRows(rows);
    setLocalCols(cols);
    setGridSettings(rows, cols, duplicateDistLimit, colorStrictness);
  };

  const handleApplyBounds = (ox: number, oy: number, gw: number, gh: number) => {
    setLocalOffsetX(ox);
    setLocalOffsetY(oy);
    setLocalGridW(gw);
    setLocalGridH(gh);
    setGridBounds(ox, oy, gw, gh);
  };

  const handleTargetBaseUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;
    setUploadingTarget(true);
    const formData = new FormData();
    formData.append('file', e.target.files[0]);
    try {
      const res = await fetch('/api/ingest/target-base', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (data.url) {
        setTargetBaseUrl(data.url);
      }
    } catch (err) {
      console.error('Target Base Upload Error:', err);
    } finally {
      setUploadingTarget(false);
    }
  };

  const handleBrandUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;
    const formData = new FormData();
    formData.append('file', e.target.files[0]);
    const res = await fetch('/api/ingest/brand-fallback', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (data.item) {
      setBrandImages((prev) => [...prev, data.item.url]);
    }
  };

  return (
    <div className="flex flex-col gap-5 p-4 bg-slate-900 border-r border-slate-800 text-slate-100 w-80 h-full max-h-full overflow-y-auto pr-2 font-sans">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2 text-cyan-400">
          <Monitor className="w-5 h-5" />
          <h3 className="font-bold text-sm uppercase tracking-wider">Display & Ingestão</h3>
        </div>
      </div>

      {/* Onde as configurações efetivamente são publicadas */}
      <div className="flex items-start gap-2 bg-slate-800/60 border border-slate-700/60 rounded-lg p-2.5">
        <Save className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
        <p className="text-[10px] text-slate-400 leading-snug">
          As mudanças desta aba são um rascunho. Use{' '}
          <span className="font-bold text-cyan-300">Aplicar no Telão</span> na barra superior para publicá-las
          e salvá-las no servidor.
        </p>
      </div>

      {/* 1. Target Base Image (Imagem de Fundo do Mosaico) */}
      <div className="flex flex-col gap-2 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
            <Upload className="w-4 h-4 text-cyan-400" />
            <span>Imagem de Fundo do Mosaico</span>
          </div>
          {targetBaseUrl && (
            <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded flex items-center gap-1">
              <Check className="w-3 h-3" /> Ativa
            </span>
          )}
        </div>

        {targetBaseUrl ? (
          <div className="relative group overflow-hidden rounded border border-slate-700">
            <img src={targetBaseUrl} alt="Target Base" className="w-full h-24 object-cover" />
            <label className="absolute inset-0 bg-slate-950/80 opacity-0 group-hover:opacity-100 transition flex items-center justify-center cursor-pointer text-xs font-semibold text-cyan-300">
              Trocar Imagem de Fundo
              <input type="file" accept="image/*" onChange={handleTargetBaseUpload} className="hidden" />
            </label>
          </div>
        ) : (
          <label className="cursor-pointer bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 text-xs text-center py-4 rounded-lg transition border border-dashed border-cyan-500/50 flex flex-col items-center gap-1.5 shadow-inner">
            <Upload className="w-5 h-5 text-cyan-400" />
            <span>{uploadingTarget ? 'Enviando Imagem...' : '+ Carregar Fundo do Mosaico'}</span>
            <span className="text-[10px] text-slate-400">JPG/PNG alta resolução</span>
            <input type="file" accept="image/*" onChange={handleTargetBaseUpload} className="hidden" />
          </label>
        )}
      </div>

      {/* 2. Dimensões de Telões (Simulador de Telões) */}
      <div className="flex flex-col gap-2 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Monitor className="w-4 h-4 text-cyan-400" />
          <span>Simulação de Telões</span>
        </div>
        
        <select
          onChange={handlePresetChange}
          className="bg-slate-900 border border-slate-700 rounded p-1.5 text-xs text-slate-200"
        >
          <option value="1920x1080">Full HD (1920x1080) - 16:9</option>
          <option value="3840x2160">4K UHD (3840x2160) - 16:9</option>
          <option value="1080x1920">Vertical LED (1080x1920) - 9:16</option>
          <option value="3840x1080">Painel Ultra-Wide (3840x1080)</option>
        </select>

        <div className="grid grid-cols-2 gap-2 mt-1">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-slate-400">Largura (px)</span>
            <input
              type="number"
              value={localWidth}
              onChange={(e) => setLocalWidth(parseInt(e.target.value) || 0)}
              onBlur={() => commitScreenSize()}
              onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
              className="bg-slate-900 border border-slate-700 rounded p-1 text-xs font-mono text-cyan-300 text-center"
            />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-slate-400">Altura (px)</span>
            <input
              type="number"
              value={localHeight}
              onChange={(e) => setLocalHeight(parseInt(e.target.value) || 0)}
              onBlur={() => commitScreenSize()}
              onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
              className="bg-slate-900 border border-slate-700 rounded p-1 text-xs font-mono text-cyan-300 text-center"
            />
          </div>
        </div>

        <div className="flex items-center justify-between text-[10px] pt-0.5">
          <span className="text-slate-500">Ativo no telão</span>
          <span className={`font-mono ${screenWidth === localWidth && screenHeight === localHeight ? 'text-slate-400' : 'text-amber-400'}`}>
            {screenWidth}×{screenHeight}
          </span>
        </div>
      </div>

      {/* 3. Posicionamento e Dimensionamento da Grade no Fundo */}
      <div className="flex flex-col gap-3 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Move className="w-4 h-4 text-cyan-400" />
          <span>Dimensionar / Mover Grade</span>
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Offset X (Posição H)</span>
            <span className="font-mono text-cyan-300">{localOffsetX}px</span>
          </div>
          <input
            type="range"
            min="0"
            max={localWidth}
            value={localOffsetX}
            onChange={(e) => handleApplyBounds(parseInt(e.target.value), localOffsetY, localGridW, localGridH)}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Offset Y (Posição V)</span>
            <span className="font-mono text-cyan-300">{localOffsetY}px</span>
          </div>
          <input
            type="range"
            min="0"
            max={localHeight}
            value={localOffsetY}
            onChange={(e) => handleApplyBounds(localOffsetX, parseInt(e.target.value), localGridW, localGridH)}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Largura da Grade</span>
            <span className="font-mono text-cyan-300">{localGridW}px</span>
          </div>
          <input
            type="range"
            min="100"
            max={localWidth}
            value={localGridW}
            onChange={(e) => handleApplyBounds(localOffsetX, localOffsetY, parseInt(e.target.value), localGridH)}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Altura da Grade</span>
            <span className="font-mono text-cyan-300">{localGridH}px</span>
          </div>
          <input
            type="range"
            min="100"
            max={localHeight}
            value={localGridH}
            onChange={(e) => handleApplyBounds(localOffsetX, localOffsetY, localGridW, parseInt(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>
      </div>

      {/* 4. Estilo Visual das Linhas da Grade */}
      <div className="flex flex-col gap-3 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Sliders className="w-4 h-4 text-cyan-400" />
          <span>Estilo Visual da Grade</span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">Cor das Linhas</span>
          <div className="flex gap-1.5">
            {['#00ffff', '#ffffff', '#ffea00', '#ff0055', '#00ff66'].map((c) => (
              <button
                key={c}
                onClick={() => setGridStyle(c, gridThickness, gridOpacity)}
                style={{ backgroundColor: c }}
                className={`w-5 h-5 rounded-full border border-slate-600 transition ${
                  gridColor === c ? 'scale-125 ring-2 ring-cyan-400' : 'hover:scale-110'
                }`}
              />
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Espessura das Linhas</span>
            <span className="font-mono text-cyan-300">{gridThickness}px</span>
          </div>
          <input
            type="range"
            min="1"
            max="6"
            value={gridThickness}
            onChange={(e) => setGridStyle(gridColor, parseInt(e.target.value), gridOpacity)}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Opacidade da Grade</span>
            <span className="font-mono text-cyan-300">{Math.round(gridOpacity * 100)}%</span>
          </div>
          <input
            type="range"
            min="0.1"
            max="1.0"
            step="0.05"
            value={gridOpacity}
            onChange={(e) => setGridStyle(gridColor, gridThickness, parseFloat(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>
      </div>

      {/* 5. Forma Geométrica da Grade (Losangos / Quadrados / Hexágonos / Círculos) */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
          <Grid className="w-4 h-4 text-cyan-400" />
          <span>Forma Geométrica da Grade</span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => setGridShape('diamond')}
            className={`flex flex-col items-center justify-center p-2.5 rounded-lg border transition gap-1 ${
              gridShape === 'diamond'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base font-bold">💎</span>
            <span className="text-[11px] font-semibold">Losango 45°</span>
            <span className="text-[9px] text-slate-400">Padrão HSBC</span>
          </button>

          <button
            onClick={() => setGridShape('square')}
            className={`flex flex-col items-center justify-center p-2.5 rounded-lg border transition gap-1 ${
              gridShape === 'square'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base font-bold">🔲</span>
            <span className="text-[11px] font-semibold">Quadrados</span>
            <span className="text-[9px] text-slate-400">Ortogonal</span>
          </button>

          <button
            onClick={() => setGridShape('hexagon')}
            className={`flex flex-col items-center justify-center p-2.5 rounded-lg border transition gap-1 ${
              gridShape === 'hexagon'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base font-bold">⬡</span>
            <span className="text-[11px] font-semibold">Hexagonal</span>
            <span className="text-[9px] text-slate-400">Colmeia</span>
          </button>

          <button
            onClick={() => setGridShape('circle')}
            className={`flex flex-col items-center justify-center p-2.5 rounded-lg border transition gap-1 ${
              gridShape === 'circle'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base font-bold">⚪</span>
            <span className="text-[11px] font-semibold">Círculos</span>
            <span className="text-[9px] text-slate-400">Dots / Pontos</span>
          </button>
        </div>
      </div>

      {/* 6. Contorno / Máscara da Área do Mosaico (Bounding Mask Container) */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
          <Move className="w-4 h-4 text-cyan-400" />
          <span>Contorno da Região do Mosaico</span>
        </div>

        <div className="flex flex-col gap-2">
          <button
            onClick={() => setGridContainerShape('diamond_mask')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'diamond_mask'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">🔷</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Máscara Losango (HSBC Shape)</span>
              <span className="text-[10px] text-slate-400">Contorno no formato de diamante</span>
            </div>
          </button>

          <button
            onClick={() => setGridContainerShape('hexagon_halftone')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'hexagon_halftone'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">✨</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Gradiente Meio-Tom Hexagonal</span>
              <span className="text-[10px] text-slate-400">Pontos grandes nas pontas, pequenos no centro</span>
            </div>
          </button>

          <button
            onClick={() => setGridContainerShape('hexagon_mask')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'hexagon_mask'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">⬡</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Máscara Hexagonal</span>
              <span className="text-[10px] text-slate-400">Contorno no formato de hexágono</span>
            </div>
          </button>

          <button
            onClick={() => setGridContainerShape('circle_mask')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'circle_mask'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">⚪</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Máscara Circular / Elipse</span>
              <span className="text-[10px] text-slate-400">Contorno em formato circular</span>
            </div>
          </button>

          <button
            onClick={() => setGridContainerShape('rectangle')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'rectangle'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">🔲</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Retângulo Completo</span>
              <span className="text-[10px] text-slate-400">Caixa delimitadora padrão</span>
            </div>
          </button>
        </div>
      </div>

      {/* 5. Tamanho dos Quadrados & Matriz de Ladrilhos */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
          <Grid className="w-4 h-4 text-cyan-400" />
          <span>Tamanho dos Quadrados & Resolução</span>
        </div>

        {/* Presets Rápidos de Tamanho de Quadrado */}
        <div className="grid grid-cols-3 gap-1.5">
          <button
            onClick={() => handleGridPreset(15, 20)}
            className={`flex flex-col items-center p-2 rounded border text-center transition ${
              localRows === 15 && localCols === 20
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            <span className="text-sm font-bold">🔲</span>
            <span className="text-[11px] font-bold">Grandes</span>
            <span className="text-[9px] text-slate-400">15 × 20</span>
          </button>

          <button
            onClick={() => handleGridPreset(30, 40)}
            className={`flex flex-col items-center p-2 rounded border text-center transition ${
              localRows === 30 && localCols === 40
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            <span className="text-sm font-bold">⬛</span>
            <span className="text-[11px] font-bold">Médios</span>
            <span className="text-[9px] text-slate-400">30 × 40</span>
          </button>

          <button
            onClick={() => handleGridPreset(60, 80)}
            className={`flex flex-col items-center p-2 rounded border text-center transition ${
              localRows === 60 && localCols === 80
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            <span className="text-sm font-bold">▫️</span>
            <span className="text-[11px] font-bold">Pequenos</span>
            <span className="text-[9px] text-slate-400">60 × 80</span>
          </button>
        </div>
        
        <div className="flex flex-col gap-1 mt-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Linhas (Rows)</span>
            <span className="font-mono text-cyan-300">{localRows}</span>
          </div>
          <input
            type="range"
            min="10"
            max="100"
            value={localRows}
            onChange={(e) => setLocalRows(parseInt(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Colunas (Cols)</span>
            <span className="font-mono text-cyan-300">{localCols}</span>
          </div>
          <input
            type="range"
            min="10"
            max="100"
            value={localCols}
            onChange={(e) => setLocalCols(parseInt(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <button
          onClick={handleApplyGrid}
          className="mt-1 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold py-1.5 rounded transition shadow-sm"
        >
          Aplicar Linhas/Colunas Personalizadas
        </button>
      </div>

      {/* 6. Ordem de Preenchimento do Mosaico (Sequência de Início) */}
      <div className="flex flex-col gap-2.5 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
          <Sliders className="w-4 h-4 text-cyan-400" />
          <span>Ordem de Preenchimento do Mosaico</span>
        </div>

        <select
          value={useMosaicStore.getState().fillSequence}
          onChange={(e) => useMosaicStore.getState().setFillSequence(e.target.value as any)}
          className="bg-slate-900 border border-slate-700 rounded p-2 text-xs text-slate-200"
        >
          <option value="color_match">🎨 Melhor Combinação de Cores (LAB Perceptual)</option>
          <option value="top_to_bottom">⬇️ Cima para Baixo (Linha por Linha)</option>
          <option value="bottom_to_top">⬆️ Baixo para Cima</option>
          <option value="center_out">🎯 Do Centro para as Bordas (Espiral)</option>
          <option value="random">🎲 Aleatório (Random)</option>
        </select>
      </div>

      {/* 7. Duplicar Fotos para Fechar o Mosaico */}
      <div className="flex flex-col gap-2.5 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center justify-between text-xs font-bold text-emerald-300">
          <div className="flex items-center gap-1.5">
            <ImageIcon className="w-4 h-4 text-emerald-400" />
            <span>Completar Mosaico (Duplicar Fotos)</span>
          </div>
        </div>

        <p className="text-[10px] text-slate-400 leading-snug">
          Se faltarem fotos para fechar o mosaico, clique no botão abaixo para reutilizar as fotos existentes e preencher 100% da grade.
        </p>

        <button
          onClick={async () => {
            const seq = useMosaicStore.getState().fillSequence;
            await fetch(`/api/mosaic/auto-fill-duplicates?fill_sequence=${seq}`, { method: 'POST' });
          }}
          className="w-full bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs py-2 rounded-lg transition shadow-md flex items-center justify-center gap-1.5 border border-emerald-400/40 active:scale-95"
        >
          <Check className="w-4 h-4 text-emerald-200" />
          <span>⚡ Preencher Todo o Mosaico (Duplicar Fotos)</span>
        </button>
      </div>

      {/* 6. Hot Folder Watcher Input */}
      <div className="flex flex-col gap-2 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <FolderOpen className="w-4 h-4 text-cyan-400" />
          <span>Hot Folder Watcher (Câmera)</span>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={hotFolderInput}
            readOnly
            className="flex-1 bg-slate-900 border border-slate-700 rounded p-1.5 text-xs font-mono text-slate-300 cursor-not-allowed"
            placeholder="Nenhuma pasta selecionada"
          />
          <button 
            onClick={handleSelectFolder}
            className="bg-slate-700 hover:bg-slate-600 px-3 rounded border border-slate-500 text-xs text-white font-medium transition"
          >
            Selecionar
          </button>
        </div>
        <span className="text-[10px] text-emerald-400 flex items-center gap-1">
          <span className="w-2 h-2 bg-emerald-500 rounded-full animate-ping" />
          Watcher Ativo (Monitorando diretório)
        </span>
      </div>

      {/* 7. Brand / Fallback Images */}
      <div className="flex flex-col gap-2 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
          <div className="flex items-center gap-1.5">
            <ImageIcon className="w-4 h-4 text-cyan-400" />
            <span>Imagens da Marca (Fallback)</span>
          </div>
          <span className="text-[10px] text-slate-500">{brandImages.length} prontas</span>
        </div>
        <label className="cursor-pointer bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs text-center py-2 rounded transition border border-dashed border-slate-500">
          + Upload Imagens Institucionais
          <input type="file" accept="image/*" onChange={handleBrandUpload} className="hidden" />
        </label>
        {brandImages.length > 0 && (
          <div className="grid grid-cols-4 gap-1.5 mt-2">
            {brandImages.map((url, i) => (
              <img key={i} src={url} alt="Brand" className="w-full h-10 object-cover rounded border border-slate-700" />
            ))}
          </div>
        )}
      </div>

      {/* 8. Fotos de Teste & Ingestão Rápida */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md mb-6">
        <div className="flex items-center justify-between text-xs font-bold text-cyan-300">
          <div className="flex items-center gap-1.5">
            <Upload className="w-4 h-4 text-cyan-400" />
            <span>Fotos de Teste (Galeria)</span>
          </div>
        </div>

        <p className="text-[10px] text-slate-400 leading-snug">
          Selecione fotos da sua galeria para testar o envio para a fila de moderação e a animação do telão. (Máximo de 5)
        </p>

        <label
          className={`cursor-pointer bg-gradient-to-r from-cyan-600 to-teal-600 hover:from-cyan-500 hover:to-teal-500 text-white font-bold text-xs py-2 rounded-lg transition shadow-md flex items-center justify-center gap-2 ${
            generatingPhotos ? 'opacity-50 pointer-events-none' : ''
          }`}
        >
          {generatingPhotos ? (
            <span className="animate-pulse">Enviando Fotos...</span>
          ) : (
            <>
              <span>⚡ Ingerir 5 Fotos de Teste</span>
              <input 
                type="file" 
                multiple 
                accept="image/*" 
                onChange={handleGalleryTestPhotos} 
                className="hidden" 
              />
            </>
          )}
        </label>
      </div>
    </div>
  );
};
