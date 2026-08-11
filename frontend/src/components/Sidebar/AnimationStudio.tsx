import React, { useState } from 'react';
import { useMosaicStore } from '../../store/mosaicStore';
import { AUTO_EASE, AnimationPreset, PRESET_DEFAULT_EASE } from '../../utils/gsapAnimations';
import { playMosaicOutro } from '../../lib/api';
import { AnimationPreview } from './AnimationPreview';
import { Sparkles, RotateCw, Activity, Bomb, Eye } from 'lucide-react';

interface PresetOption {
  id: AnimationPreset;
  name: string;
  tag: string;
  desc: string;
  icon: string;
}

const PRESETS: PresetOption[] = [
  {
    id: 'fly_parabolic',
    name: 'Voo Parabólico',
    tag: 'PADRÃO',
    desc: 'Foto surge no centro em preview e voa suave em arco até o ladrilho.',
    icon: '🚀',
  },
  {
    id: 'hsbc_cascade',
    name: 'Cascata HSBC',
    tag: 'DIAMANTE',
    desc: 'Entrada veloz com máscara de diamante e efeito vermelho HSBC.',
    icon: '💎',
  },
  {
    id: 'spiral',
    name: 'Entrada Espiral',
    tag: '3D ROTATE',
    desc: 'Ladrilho gira em 720° enquanto reduz a escala até travar no lugar.',
    icon: '🌀',
  },
  {
    id: 'wave',
    name: 'Onda Sequencial',
    tag: 'RIPPLE',
    desc: 'Efeito onda expansiva com amortecimento elástico (Bounce).',
    icon: '🌊',
  },
  {
    id: 'flip_3d',
    name: 'Efeito Flip 3D',
    tag: 'SUBSTITUIÇÃO',
    desc: 'Giro de 180° no eixo Y ideal para trocas manuais de foto.',
    icon: '🔄',
  },
];

const EASE_OPTIONS: { value: string; label: string }[] = [
  { value: AUTO_EASE, label: 'Automático (curva natural do preset)' },
  { value: 'power3.inOut', label: 'Power3 InOut (Suave)' },
  { value: 'cubic.out', label: 'Cubic Out (HSBC Rápido)' },
  { value: 'elastic.out(1, 0.5)', label: 'Elastic Out (Bounce)' },
  { value: 'back.out(1.7)', label: 'Back Out (Pop)' },
];

export const AnimationStudio: React.FC = () => {
  const {
    animationPreset,
    animationDuration,
    animationEase,
    centralPreviewEnabled,
    centralPreviewDuration,
    previewCardScale,
    previewGapSeconds,
    screenHeight,
    gridShape,
    idleReplayEnabled,
    idleReplayDelay,
    idleReplayInterval,
    setAnimationConfig,
    setCentralPreviewDuration,
    setCentralPreviewEnabled,
    setPreviewCardScale,
    setPreviewGapSeconds,
    setIdleReplay,
  } = useMosaicStore();

  const [replayKey, setReplayKey] = useState(0);
  const [dispersing, setDispersing] = useState(false);

  const handleSelectPreset = (id: AnimationPreset) => {
    setAnimationConfig(id, animationDuration, animationEase);
    setReplayKey((k) => k + 1);
  };

  const handleOutro = async (modo: 'retorno' | 'dispersar' | 'espalhar') => {
    const descricao =
      modo === 'espalhar'
        ? 'Cada ladrilho se solta numa direção, anda pouco e apaga — o final do vídeo de referência.'
        : modo === 'retorno'
          ? 'As fotos refazem o voo até o centro, crescem e somem — a entrada ao contrário.'
          : 'Os ladrilhos voam para fora da tela, do centro para as bordas.';
    if (!window.confirm(`Encerrar o mosaico no telão?\n\n${descricao}\n\nA grade fica vazia; as fotos aprovadas são preservadas.`)) {
      return;
    }
    setDispersing(true);
    try {
      await playMosaicOutro(modo);
    } catch (err) {
      console.error('[Outro] Falha ao encerrar:', err);
    } finally {
      setDispersing(false);
    }
  };

  const effectiveEase = animationEase === AUTO_EASE ? PRESET_DEFAULT_EASE[animationPreset] : animationEase;

  return (
    <div className="flex flex-col gap-5 p-4 bg-slate-900 border-r border-slate-800 text-slate-100 w-80 h-full max-h-full overflow-y-auto">
      <div className="flex items-center gap-2 text-cyan-400 border-b border-slate-800 pb-2">
        <Sparkles className="w-5 h-5" />
        <h3 className="font-bold text-sm uppercase tracking-wider">Estúdio de Animações</h3>
      </div>

      {/* PREVIEW FIEL: roda o mesmo motor GSAP/Pixi do telão */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
            <Eye className="w-4 h-4 text-cyan-400" />
            <span>Preview Real do Telão</span>
          </div>
          <button
            onClick={() => setReplayKey((k) => k + 1)}
            className="flex items-center gap-1 text-[10px] font-semibold text-slate-400 hover:text-cyan-300 transition"
            title="Repetir a animação agora"
          >
            <RotateCw className="w-3 h-3" />
            Repetir
          </button>
        </div>

        <AnimationPreview
          preset={animationPreset}
          duration={animationDuration}
          ease={animationEase}
          centralPreviewDuration={centralPreviewDuration}
          gridShape={gridShape}
          replayKey={replayKey}
        />

        <span className="text-[10px] text-slate-500 leading-snug">
          Mesmo motor do telão, em escala reduzida. Curva em uso:{' '}
          <span className="font-mono text-slate-400">{effectiveEase}</span>
        </span>
      </div>

      {/* Lista de Presets */}
      <div className="flex flex-col gap-2">
        {PRESETS.map((preset) => {
          const isSelected = animationPreset === preset.id;

          return (
            <button
              key={preset.id}
              onClick={() => handleSelectPreset(preset.id)}
              className={`group text-left flex flex-col gap-1 p-3 rounded-lg border transition shadow-md ${
                isSelected
                  ? 'bg-cyan-500/20 border-cyan-400 ring-2 ring-cyan-500/30'
                  : 'bg-slate-800/70 border-slate-700/80 hover:border-slate-600 hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{preset.icon}</span>
                  <span className="text-xs font-bold text-slate-200">{preset.name}</span>
                </div>
                <span
                  className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded ${
                    isSelected ? 'bg-cyan-400 text-slate-950' : 'bg-slate-700 text-slate-300'
                  }`}
                >
                  {preset.tag}
                </span>
              </div>

              <p className="text-[10px] text-slate-400 leading-tight">{preset.desc}</p>
            </button>
          );
        })}
      </div>

      {/* Ajustes Finos de Duração & Easing */}
      <div className="flex flex-col gap-3 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Activity className="w-4 h-4 text-cyan-400" />
          <span>Ajustes Finos de Tempo</span>
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Duração do Voo</span>
            <span className="font-mono text-cyan-300">{animationDuration.toFixed(1)}s</span>
          </div>
          <input
            type="range"
            min="0.3"
            max="2.5"
            step="0.1"
            value={animationDuration}
            onChange={(e) => setAnimationConfig(animationPreset, parseFloat(e.target.value), animationEase)}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        {/* Liga/desliga o cartão central. Desligado, a foto vai direto para a
            célula — útil quando a fila da cabine está grande e o telão precisa
            acompanhar o ritmo. */}
        <label className="flex items-center justify-between cursor-pointer pt-1">
          <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
            <Eye className="w-4 h-4 text-cyan-400" />
            Preview Central
          </span>
          <input
            type="checkbox"
            checked={centralPreviewEnabled}
            onChange={(e) => setCentralPreviewEnabled(e.target.checked)}
            className="w-4 h-4 accent-cyan-400 cursor-pointer"
          />
        </label>
        {!centralPreviewEnabled && (
          <span className="text-[10px] text-amber-400/90 leading-snug">
            Desligado: a foto voa direto para o lugar dela, sem parar no centro.
          </span>
        )}

        <div className={`flex flex-col gap-1 ${centralPreviewEnabled ? '' : 'opacity-40 pointer-events-none'}`}>
          <div className="flex justify-between text-xs text-slate-400">
            <span>Preview no Centro</span>
            <span className="font-mono text-cyan-300">{centralPreviewDuration.toFixed(1)}s</span>
          </div>
          <input
            type="range"
            min="0"
            max="15"
            step="0.1"
            value={centralPreviewDuration}
            onChange={(e) => setCentralPreviewDuration(parseFloat(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <div className={`flex flex-col gap-1 ${centralPreviewEnabled ? '' : 'opacity-40 pointer-events-none'}`}>
          <div className="flex justify-between text-xs text-slate-400">
            <span>Tamanho do Preview</span>
            <span className="font-mono text-cyan-300">
              {Math.round(previewCardScale * 100)}% · {Math.round(screenHeight * previewCardScale)}px
            </span>
          </div>
          <input
            type="range"
            min="0.3"
            max="1"
            step="0.05"
            value={previewCardScale}
            onChange={(e) => setPreviewCardScale(parseFloat(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
          <span className="text-[10px] text-slate-500">
            Fração da altura do telão. Acima de 90% o cartão encosta nas bordas.
          </span>
        </div>

        {/* Vale mesmo com o preview desligado: é o ritmo da fila, não do cartão. */}
        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Respiro entre Previews</span>
            <span className="font-mono text-cyan-300">{previewGapSeconds.toFixed(1)}s</span>
          </div>
          <input
            type="range"
            min="0"
            max="15"
            step="0.5"
            value={previewGapSeconds}
            onChange={(e) => setPreviewGapSeconds(parseFloat(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
          <span className="text-[10px] text-slate-500">
            Pausa entre uma foto e a seguinte. Em rajada — duplicação ligada ou
            várias pessoas fotografando junto — sem isso elas entram coladas.
          </span>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">Curva Easing (Suavização)</span>
          <select
            value={animationEase}
            onChange={(e) => setAnimationConfig(animationPreset, animationDuration, e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded p-1.5 text-xs text-slate-200"
          >
            {EASE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <span className="text-[10px] text-slate-500 leading-snug">
            Vale para todos os presets. Em "Automático", cada um usa a curva com que foi desenhado.
          </span>
        </div>
      </div>

      {/* MODO OCIOSO: a tela não pode ficar parada nos intervalos da cabine */}
      <div className="flex flex-col gap-3 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <label className="flex items-center justify-between cursor-pointer">
          <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
            <RotateCw className="w-4 h-4 text-cyan-400" />
            Destacar fotos antigas
          </span>
          <input
            type="checkbox"
            checked={idleReplayEnabled}
            onChange={(e) => setIdleReplay(e.target.checked, idleReplayDelay, idleReplayInterval)}
            className="w-4 h-4 accent-cyan-400 cursor-pointer"
          />
        </label>

        <span className="text-[10px] text-slate-500 leading-snug">
          Sem foto nova, o telão sorteia uma foto já no mosaico e a mostra no preview central.
          Ela volta para a mesma célula — o mosaico não muda.
        </span>

        <div className={`flex flex-col gap-3 ${idleReplayEnabled ? '' : 'opacity-40 pointer-events-none'}`}>
          <div className="flex flex-col gap-1">
            <div className="flex justify-between text-xs text-slate-400">
              <span>Começa após</span>
              <span className="font-mono text-cyan-300">{idleReplayDelay.toFixed(0)}s sem foto</span>
            </div>
            <input
              type="range"
              min="5"
              max="120"
              step="5"
              value={idleReplayDelay}
              onChange={(e) => setIdleReplay(idleReplayEnabled, parseFloat(e.target.value), idleReplayInterval)}
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
            />
          </div>

          <div className="flex flex-col gap-1">
            <div className="flex justify-between text-xs text-slate-400">
              <span>Intervalo entre destaques</span>
              <span className="font-mono text-cyan-300">{idleReplayInterval.toFixed(0)}s</span>
            </div>
            <input
              type="range"
              min="0"
              max="60"
              step="1"
              value={idleReplayInterval}
              onChange={(e) => setIdleReplay(idleReplayEnabled, idleReplayDelay, parseFloat(e.target.value))}
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
            />
          </div>
        </div>
      </div>

      {/* Encerramento do evento */}
      <div className="flex flex-col gap-2.5 bg-slate-800/80 p-3 rounded-lg border border-rose-900/50 shadow-md mb-6">
        <div className="flex items-center gap-1.5 text-xs font-bold text-rose-300">
          <Bomb className="w-4 h-4 text-rose-400" />
          <span>Encerramento do Evento</span>
        </div>

        <p className="text-[10px] text-slate-400 leading-snug">
          Três saídas para o fim do evento — nenhuma é preset de entrada.
          <strong className="text-slate-300"> Dispersar</strong> é o final do
          vídeo que o cliente mandou: cada ladrilho se solta numa direção, anda
          pouco e apaga, tudo em menos de um segundo.{' '}
          <strong className="text-slate-300">Recolher</strong> é a chegada ao
          contrário, e <strong className="text-slate-300">para fora</strong> joga
          os ladrilhos para fora da tela.
        </p>

        <button
          onClick={() => handleOutro('espalhar')}
          disabled={dispersing}
          className="w-full bg-gradient-to-r from-rose-700 to-orange-700 hover:from-rose-600 hover:to-orange-600 disabled:opacity-50 text-white font-bold text-xs py-2 rounded-lg transition shadow-md flex items-center justify-center gap-1.5 border border-rose-500/40 active:scale-95"
        >
          <Bomb className="w-4 h-4" />
          {dispersing ? 'Encerrando...' : '✨ Dispersar (referência do cliente)'}
        </button>

        <button
          onClick={() => handleOutro('retorno')}
          disabled={dispersing}
          className="w-full bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-300 font-semibold text-[11px] py-1.5 rounded-lg transition border border-slate-700 active:scale-95"
        >
          🌀 Recolher para o Centro
        </button>

        <button
          onClick={() => handleOutro('dispersar')}
          disabled={dispersing}
          className="w-full bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-300 font-semibold text-[11px] py-1.5 rounded-lg transition border border-slate-600 active:scale-95"
        >
          💥 Dispersar para Fora
        </button>
      </div>
    </div>
  );
};
