import React from 'react';
import { useMosaicStore, Layer } from '../../store/mosaicStore';
import { Layers, Eye, EyeOff, Sliders } from 'lucide-react';

export const LayerStack: React.FC = () => {
  const { layers, updateLayer } = useMosaicStore();

  /**
   * Rascunho local, igual às outras abas — quem publica é o "Aplicar no Telão".
   *
   * Antes isso fazia um POST por movimento de slider (208 numa sessão curta), e
   * cada POST devolvia um CONFIG_UPDATED com a config inteira que sobrescrevia
   * o rascunho das outras abas. Mexer numa camada zerava tamanho de telão,
   * grade e animação ainda não aplicados.
   */
  const applyLayerChange = (id: string, changes: Partial<Layer>) => {
    updateLayer(id, changes);
  };

  const handleToggleVisible = (id: string, current: boolean) => applyLayerChange(id, { visible: !current });
  const handleOpacityChange = (id: string, opacity: number) => applyLayerChange(id, { opacity });
  const handleBlurChange = (id: string, blur: number) => applyLayerChange(id, { blur });

  return (
    <div className="flex flex-col gap-4 p-4 bg-slate-900 border-r border-slate-800 text-slate-100 w-80 overflow-y-auto">
      <div className="flex items-center gap-2 text-cyan-400 border-b border-slate-800 pb-2">
        <Layers className="w-5 h-5" />
        <h3 className="font-bold text-sm uppercase tracking-wider">Edição Avançada & Camadas</h3>
      </div>

      <div className="flex items-start gap-2 bg-slate-800/60 border border-slate-700/60 rounded-lg p-2.5">
        <Sliders className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
        <p className="text-[10px] text-slate-400 leading-snug">
          Rascunho local. Use <span className="font-bold text-cyan-300">Aplicar no Telão</span> para publicar.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        {layers.map((layer) => (
          <div
            key={layer.id}
            className={`flex flex-col gap-2 p-3 rounded-lg border transition ${
              layer.visible ? 'bg-slate-800/80 border-slate-700' : 'bg-slate-950/40 border-slate-900 opacity-60'
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-cyan-400">Z-{layer.zIndex}</span>
                <span className="text-xs font-medium text-slate-200">{layer.name}</span>
              </div>
              <button
                onClick={() => handleToggleVisible(layer.id, layer.visible)}
                className="text-slate-400 hover:text-cyan-300 transition"
              >
                {layer.visible ? <Eye className="w-4 h-4 text-cyan-400" /> : <EyeOff className="w-4 h-4 text-slate-600" />}
              </button>
            </div>

            {/* Slider de Opacidade */}
            <div className="flex flex-col gap-1 mt-1">
              <div className="flex justify-between text-[10px] text-slate-400 font-mono">
                <span>Opacidade</span>
                <span>{Math.round(layer.opacity * 100)}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={layer.opacity}
                onChange={(e) => handleOpacityChange(layer.id, parseFloat(e.target.value))}
                className="w-full h-1 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
              />
            </div>

            {/* Slider de Gaussian Blur (apenas em Logo Overlay) */}
            {layer.id === 'logo' && (
              <div className="flex flex-col gap-1 mt-1">
                <div className="flex justify-between text-[10px] text-slate-400 font-mono">
                  <span>Gaussian Blur</span>
                  <span>{layer.blur}px</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="20"
                  step="1"
                  value={layer.blur}
                  onChange={(e) => handleBlurChange(layer.id, parseInt(e.target.value))}
                  className="w-full h-1 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
