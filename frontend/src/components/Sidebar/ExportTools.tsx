import React, { useState } from 'react';
import { useMosaicStore } from '../../store/mosaicStore';
import { Printer, Save, Palette, Check } from 'lucide-react';

export const ExportTools: React.FC = () => {
  const { duplicateDistLimit, colorStrictness, setGridSettings, rows, cols } = useMosaicStore();
  const [distLimit, setDistLimit] = useState(duplicateDistLimit);
  const [strictness, setStrictness] = useState(colorStrictness);
  const [isExporting, setIsExporting] = useState(false);
  const [exportedMsg, setExportedMsg] = useState(false);

  // Rascunho local — publicar é papel exclusivo do "Aplicar no Telão". Um POST
  // aqui devolveria um CONFIG_UPDATED com a config inteira, apagando o que
  // estivesse pendente nas outras abas.
  const handleSaveSettings = () => {
    setGridSettings(rows, cols, distLimit, strictness);
  };

  const handleSaveStateJSON = async () => {
    const res = await fetch('/api/mosaic/save-state');
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mosaic_project_state_${Date.now()}.json`;
    a.click();
  };

  const handleExportToPrintSpooler = async () => {
    setIsExporting(true);
    setExportedMsg(false);
    await fetch('/api/export/print-spooler', { method: 'POST' });
    setTimeout(() => {
      setIsExporting(false);
      setExportedMsg(true);
      setTimeout(() => setExportedMsg(false), 4000);
    }, 1200);
  };

  return (
    <div className="flex flex-col gap-5 p-4 bg-slate-900 border-r border-slate-800 text-slate-100 w-80 overflow-y-auto">
      <div className="flex items-center gap-2 text-cyan-400 border-b border-slate-800 pb-2">
        <Printer className="w-5 h-5" />
        <h3 className="font-bold text-sm uppercase tracking-wider">Exportação & Save State</h3>
      </div>

      {/* Algoritmo & Color Bias */}
      <div className="flex flex-col gap-3 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Palette className="w-4 h-4 text-cyan-400" />
          <span>Controle de Cor & Duplicatas</span>
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Duplicate Distance Limit</span>
            <span className="font-mono text-cyan-300">{distLimit} ladrilhos</span>
          </div>
          <input
            type="range"
            min="1"
            max="10"
            value={distLimit}
            onChange={(e) => setDistLimit(parseInt(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Color Matching Strictness</span>
            <span className="font-mono text-cyan-300">{strictness.toFixed(1)}x</span>
          </div>
          <input
            type="range"
            min="0.2"
            max="3.0"
            step="0.1"
            value={strictness}
            onChange={(e) => setStrictness(parseFloat(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <button
          onClick={handleSaveSettings}
          className="mt-1 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-semibold py-1.5 rounded transition"
        >
          Atualizar Regras de Match
        </button>
      </div>

      {/* Save Project State */}
      <button
        onClick={handleSaveStateJSON}
        className="flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold py-2 rounded shadow transition"
      >
        <Save className="w-4 h-4 text-cyan-400" />
        Save Project State (JSON)
      </button>

      {/* Export to Print Spooler */}
      <div className="flex flex-col gap-2">
        <button
          onClick={handleExportToPrintSpooler}
          disabled={isExporting}
          className="flex items-center justify-center gap-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold py-2.5 rounded shadow-lg transition disabled:opacity-50"
        >
          <Printer className="w-4 h-4" />
          {isExporting ? 'Exportando Alta Resolução...' : 'Export to Print Spooler (300 DPI)'}
        </button>
        {exportedMsg && (
          <span className="text-[11px] text-emerald-400 font-mono text-center flex items-center justify-center gap-1">
            <Check className="w-3.5 h-3.5" />
            Composição enviada para /storage/print_out
          </span>
        )}
      </div>
    </div>
  );
};
