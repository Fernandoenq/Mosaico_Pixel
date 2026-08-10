import React, { useState } from 'react';
import { useMosaicStore } from '../../store/mosaicStore';
import { Palette, Paintbrush, Sparkles, Trash2, Clock, Check } from 'lucide-react';

interface FilterOption {
  id: string;
  name: string;
  color: string;
  bgGradient: string;
  description: string;
}

const FILTER_PALETTE: FilterOption[] = [
  { id: 'red', name: 'Vermelho HSBC', color: '#ff0044', bgGradient: 'from-red-600 to-rose-700', description: 'Tom vermelho marca' },
  { id: 'red_suave', name: 'Vermelho Suave', color: '#ff8899', bgGradient: 'from-rose-400 to-red-500', description: 'Marca sem apagar o rosto' },
  { id: 'gold', name: 'Dourado Gold', color: '#ffcc00', bgGradient: 'from-amber-400 to-yellow-600', description: 'Efeito dourado premium' },
  { id: 'cyan', name: 'Ciano Cyber', color: '#00ffff', bgGradient: 'from-cyan-400 to-teal-600', description: 'Estilo neon ciano' },
  { id: 'green', name: 'Verde Neon', color: '#00ff66', bgGradient: 'from-emerald-400 to-green-600', description: 'Tom verde vibrante' },
  { id: 'sepia', name: 'Sépia Vintage', color: '#ffb380', bgGradient: 'from-amber-700 to-orange-800', description: 'Filtro quente sepia' },
  { id: 'grayscale', name: 'P&B Monocromático', color: '#aaaaaa', bgGradient: 'from-slate-400 to-slate-700', description: 'Preto e branco clássico' },
  { id: 'none', name: 'Original / Borracha', color: '#ffffff', bgGradient: 'from-slate-700 to-slate-900', description: 'Limpa filtro da célula' },
];

export const FilterEditorPanel: React.FC = () => {
  const {
    cellFilters,
    brushModeActive,
    selectedBrushFilter,
    centralPreviewDuration,
    setBrushModeActive,
    setSelectedBrushFilter,
    setCentralPreviewDuration,
    clearCellFilters,
  } = useMosaicStore();

  const paintedCount = Object.keys(cellFilters).length;

  const [isApplyingHSBC, setIsApplyingHSBC] = useState(false);

  const handleApplyHSBC = async () => {
    setIsApplyingHSBC(true);
    try {
      const res = await fetch('/api/hsbc/apply-bowtie', { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        alert(`Erro ao aplicar HSBC: ${err.detail || err.message}`);
      }
    } catch (err) {
      console.error(err);
      alert('Erro na conexão com o servidor.');
    } finally {
      setIsApplyingHSBC(false);
    }
  };

  const handleRestoreDefault = async () => {
    // Limpa a pintura no frontend
    clearCellFilters();
    
    // Reseta o estado local
    useMosaicStore.getState().setGridContainerShape('rectangle');
    
    // Sincroniza com o backend limpando a logo HSBC
    try {
      await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          cellFilters: {}, 
          customMaskCells: [],
          gridContainerShape: 'rectangle'
        })
      });
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex flex-col gap-5 p-4 bg-slate-900 border-r border-slate-800 text-slate-100 w-80 h-screen max-h-screen overflow-y-auto pr-2 font-sans select-none">
      {/* Cabeçalho do Painel */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2 text-emerald-400">
          <Palette className="w-5 h-5" />
          <h3 className="font-bold text-sm uppercase tracking-wider">Filtros & Pintura</h3>
        </div>
        <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full font-mono border border-slate-700">
          {paintedCount} células pintadas
        </span>
      </div>

      {/* 1. Modo Pincel Interativo (Pintar Grade) */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3.5 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-bold text-emerald-300">
            <Paintbrush className="w-4 h-4 text-emerald-400" />
            <span>Pincel de Pintura na Grade</span>
          </div>
          {brushModeActive && (
            <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full flex items-center gap-1 font-semibold animate-pulse border border-emerald-500/40">
              <Check className="w-3 h-3" /> Ativo
            </span>
          )}
        </div>

        <p className="text-[10px] text-slate-400 leading-snug">
          Com o modo pincel ativo, clique ou arraste o mouse sobre a grade no canvas para aplicar o filtro de cor escolhido nas fotos daquela área.
        </p>

        <button
          onClick={() => setBrushModeActive(!brushModeActive)}
          className={`w-full py-2.5 rounded-lg text-xs font-bold transition flex items-center justify-center gap-2 shadow-md ${
            brushModeActive
              ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white ring-2 ring-emerald-400 border border-emerald-300'
              : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700'
          }`}
        >
          <Paintbrush className={`w-4 h-4 ${brushModeActive ? 'animate-bounce' : ''}`} />
          <span>{brushModeActive ? 'Desativar Modo Pincel' : '⚡ Ativar Modo Pincel (Pintar Grade)'}</span>
        </button>
      </div>

      {/* 2. Paleta de Tintas de Cor e Filtros */}
      <div className="flex flex-col gap-3 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Sparkles className="w-4 h-4 text-cyan-400" />
          <span>Paleta de Cores e Filtros</span>
        </div>

        <div className="flex flex-col gap-2">
          {FILTER_PALETTE.map((f) => {
            const isSelected = selectedBrushFilter === f.id;
            return (
              <button
                key={f.id}
                onClick={() => setSelectedBrushFilter(f.id)}
                className={`flex items-center justify-between p-2.5 rounded-lg border transition text-left ${
                  isSelected
                    ? 'bg-slate-800 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30 shadow-inner'
                    : 'bg-slate-900/60 border-slate-700/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div
                    style={{ backgroundColor: f.color }}
                    className="w-5 h-5 rounded-full border border-slate-950 shadow-sm flex items-center justify-center shrink-0"
                  >
                    {isSelected && <Check className="w-3 h-3 text-slate-950 stroke-[3]" />}
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs font-bold">{f.name}</span>
                    <span className="text-[10px] text-slate-400">{f.description}</span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {paintedCount > 0 && (
          <button
            onClick={clearCellFilters}
            className="mt-1 bg-red-950/60 hover:bg-red-900/80 text-red-300 text-xs font-semibold py-2 rounded-lg border border-red-800/50 transition flex items-center justify-center gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Limpar Todos os Filtros ({paintedCount})</span>
          </button>
        )}

        <hr className="border-slate-700/50 my-1" />
        <div className="flex flex-col gap-2">
          <button
            onClick={handleApplyHSBC}
            disabled={isApplyingHSBC}
            className="bg-red-600 hover:bg-red-500 text-white text-xs font-bold py-2 rounded-lg transition flex items-center justify-center gap-1.5 shadow-md disabled:opacity-50"
          >
            <span>{isApplyingHSBC ? 'Aplicando...' : '♦ Aplicar Logo HSBC (Gravata-Borboleta)'}</span>
          </button>
          
          <button
            onClick={handleRestoreDefault}
            className="bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs font-semibold py-1.5 rounded-lg transition flex items-center justify-center gap-1.5 shadow-sm border border-slate-600"
          >
            <span>🔲 Voltar para Mosaico Quadrado Normal</span>
          </button>
        </div>
      </div>

      {/* 3. Duração do Preview Central no Centro da Tela (Camada 2) */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md mb-6">
        <div className="flex items-center justify-between text-xs font-bold text-cyan-300">
          <div className="flex items-center gap-1.5">
            <Clock className="w-4 h-4 text-cyan-400" />
            <span>Preview Central da Foto Aprovada</span>
          </div>
          <span className="font-mono text-cyan-300 text-xs">{centralPreviewDuration.toFixed(1)}s</span>
        </div>

        <p className="text-[10px] text-slate-400 leading-snug">
          Tempo que a foto aprovada fica em destaque no centro da tela (Camada 2) antes de voar para o seu lugar no mosaico.
        </p>

        <input
          type="range"
          min="0.2"
          max="3.0"
          step="0.1"
          value={centralPreviewDuration}
          onChange={(e) => setCentralPreviewDuration(parseFloat(e.target.value))}
          className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
        />

        <div className="flex justify-between text-[10px] text-slate-500 font-mono">
          <span>0.2s (Rápido)</span>
          <span>1.0s (Padrão)</span>
          <span>3.0s (Longo)</span>
        </div>
      </div>
    </div>
  );
};
