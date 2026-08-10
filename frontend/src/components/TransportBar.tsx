import React, { useEffect, useState } from 'react';
import { Play, Pause, Square, RotateCcw, UploadCloud, Check, AlertTriangle, ExternalLink, Wifi, WifiOff, Eye, EyeOff } from 'lucide-react';
import { configSignature, pickRunConfig, RunState, useMosaicStore } from '../store/mosaicStore';
import { fetchRunConfig, pushRunConfig, runTransport, TransportAction } from '../lib/api';

const STATE_STYLE: Record<RunState, { label: string; className: string; dot: string }> = {
  idle: {
    label: 'PARADO',
    className: 'bg-slate-800 text-slate-400 border-slate-700',
    dot: 'bg-slate-500',
  },
  running: {
    label: 'AO VIVO',
    className: 'bg-red-600/20 text-red-300 border-red-500/50',
    dot: 'bg-red-500 animate-pulse',
  },
  paused: {
    label: 'PAUSADO',
    className: 'bg-amber-500/20 text-amber-300 border-amber-500/50',
    dot: 'bg-amber-400',
  },
};

export const TransportBar: React.FC = () => {
  const runState = useMosaicStore((s) => s.runState);
  const socketConnected = useMosaicStore((s) => s.socketConnected);
  const signature = useMosaicStore(configSignature);
  const lastApplied = useMosaicStore((s) => s.lastAppliedConfig);
  const centralPreviewEnabled = useMosaicStore((s) => s.centralPreviewEnabled);
  const { setRunState, applyServerConfig, markConfigApplied, clearMosaic, setCentralPreviewEnabled } = useMosaicStore();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [justApplied, setJustApplied] = useState(false);

  const dirty = signature !== lastApplied;

  // Na abertura do painel o servidor manda no que está valendo hoje.
  useEffect(() => {
    fetchRunConfig()
      .then(({ config, run_state }) => {
        applyServerConfig(config);
        setRunState(run_state);
      })
      .catch(() => setError('Backend offline — inicie o servidor em :8000'));
  }, []);

  /**
   * Publica SÓ o estado do preview, direto na API.
   *
   * Passar pelo "Aplicar" arrastaria junto qualquer rascunho ainda não
   * publicado das outras abas — e desligar o preview no meio de um ajuste não
   * pode ter esse efeito colateral.
   */
  const handleTogglePreview = async () => {
    const novoValor = !centralPreviewEnabled;
    setBusy('preview');
    setError(null);
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ centralPreviewEnabled: novoValor }),
      });
      if (!res.ok) throw new Error(await res.text());
      setCentralPreviewEnabled(novoValor);
      // Mantém a assinatura em dia: o valor já está publicado, então o painel
      // não deve passar a acusar "alterações não aplicadas" por causa dele.
      markConfigApplied();
    } catch (err) {
      setError(`Falha ao alternar o preview: ${err instanceof Error ? err.message : err}`);
    } finally {
      setBusy(null);
    }
  };

  const handleApply = async () => {
    setBusy('apply');
    setError(null);
    try {
      const { config, run_state } = await pushRunConfig(pickRunConfig(useMosaicStore.getState()));
      applyServerConfig(config);
      setRunState(run_state);
      markConfigApplied();
      setJustApplied(true);
      setTimeout(() => setJustApplied(false), 2500);
    } catch (err) {
      setError(`Falha ao aplicar: ${err instanceof Error ? err.message : err}`);
    } finally {
      setBusy(null);
    }
  };

  const handleTransport = async (action: TransportAction) => {
    if (action === 'reset') {
      const total = Object.keys(useMosaicStore.getState().placedTiles).length;
      const confirmed = window.confirm(
        `Zerar o mosaico? ${total} foto(s) pousada(s) serão removidas da tela e da fila.\n\nAs configurações são preservadas.`
      );
      if (!confirmed) return;
    }

    setBusy(action);
    setError(null);
    try {
      // Play sempre publica a config atual antes de começar: nunca sobe no
      // telão um show com configuração diferente da que está na tela do painel.
      if (action === 'start' && dirty) {
        const { config } = await pushRunConfig(pickRunConfig(useMosaicStore.getState()));
        applyServerConfig(config);
        markConfigApplied();
      }
      const { run_state } = await runTransport(action);
      setRunState(run_state);
      if (action === 'reset') clearMosaic();
    } catch (err) {
      setError(`Falha em "${action}": ${err instanceof Error ? err.message : err}`);
    } finally {
      setBusy(null);
    }
  };

  const state = STATE_STYLE[runState];
  const disabled = busy !== null;

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-slate-900 border-b border-slate-800 z-30 shadow-lg">
      {/* Indicador de estado do show */}
      <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-black tracking-wider ${state.className}`}>
        <span className={`w-2 h-2 rounded-full ${state.dot}`} />
        {state.label}
      </div>

      {/* Saúde do WebSocket: sem ele o painel envia comandos mas não recebe
          nada de volta — fotos param de chegar sem qualquer aviso na tela. */}
      <div
        className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-[10px] font-bold ${
          socketConnected
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            : 'bg-rose-500/15 text-rose-300 border-rose-500/40 animate-pulse'
        }`}
        title={socketConnected ? 'Recebendo eventos do servidor' : 'Sem conexão com o servidor — tentando reconectar'}
      >
        {socketConnected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
        {socketConnected ? 'AO VIVO' : 'RECONECTANDO'}
      </div>

      <div className="w-px h-6 bg-slate-800" />

      {/* Aplicar configurações no telão */}
      <button
        onClick={handleApply}
        disabled={disabled || (!dirty && !justApplied)}
        title={dirty ? 'Publicar as configurações atuais no telão' : 'Nada alterado desde a última aplicação'}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold border transition active:scale-95 disabled:cursor-not-allowed ${
          dirty
            ? 'bg-cyan-600 hover:bg-cyan-500 text-white border-cyan-400/50 shadow-md'
            : 'bg-slate-800/60 text-slate-500 border-slate-700'
        }`}
      >
        {justApplied && !dirty ? <Check className="w-4 h-4" /> : <UploadCloud className="w-4 h-4" />}
        {busy === 'apply' ? 'Aplicando...' : justApplied && !dirty ? 'Aplicado' : 'Aplicar no Telão'}
      </button>

      {dirty && (
        <span className="text-[10px] font-semibold text-amber-400 flex items-center gap-1">
          <AlertTriangle className="w-3.5 h-3.5" />
          Alterações não aplicadas
        </span>
      )}

      <div className="w-px h-6 bg-slate-800" />

      {/* Transporte do show */}
      <button
        onClick={() => handleTransport('start')}
        disabled={disabled || runState === 'running'}
        title="Iniciar o mosaico no telão"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-600 text-white border border-emerald-400/40 disabled:border-slate-700 transition active:scale-95"
      >
        <Play className="w-4 h-4" />
        {runState === 'paused' ? 'Retomar' : 'Play'}
      </button>

      <button
        onClick={() => handleTransport('pause')}
        disabled={disabled || runState !== 'running'}
        title="Congela a entrada de fotos; o mosaico continua na tela"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-amber-600 hover:bg-amber-500 disabled:bg-slate-800 disabled:text-slate-600 text-white border border-amber-400/40 disabled:border-slate-700 transition active:scale-95"
      >
        <Pause className="w-4 h-4" />
        Pause
      </button>

      <button
        onClick={() => handleTransport('stop')}
        disabled={disabled || runState === 'idle'}
        title="Encerra o show; o mosaico permanece na tela"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-slate-100 border border-slate-600 disabled:border-slate-700 transition active:scale-95"
      >
        <Square className="w-4 h-4" />
        Stop
      </button>

      <button
        onClick={() => handleTransport('reset')}
        disabled={disabled}
        title="Zera os ladrilhos e as filas para o próximo evento"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-rose-900/50 hover:bg-rose-700 text-rose-300 hover:text-white border border-rose-700/60 transition active:scale-95"
      >
        <RotateCcw className="w-4 h-4" />
        Reset
      </button>

      <div className="w-px h-6 bg-slate-800" />

      {/* Liga/desliga o cartão central. Publica sozinho, sem passar pelo
          "Aplicar": é um controle de operação durante o ajuste, não parte da
          configuração que se monta antes do evento. */}
      <button
        onClick={handleTogglePreview}
        disabled={disabled || busy === 'preview'}
        title={
          centralPreviewEnabled
            ? 'Desligar o preview central — a foto vai direto para a célula'
            : 'Religar o preview central'
        }
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border transition active:scale-95 disabled:opacity-50 ${
          centralPreviewEnabled
            ? 'bg-cyan-600 hover:bg-cyan-500 text-white border-cyan-400/40'
            : 'bg-slate-800 hover:bg-slate-700 text-slate-400 border-slate-600'
        }`}
      >
        {centralPreviewEnabled ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
        {busy === 'preview' ? '...' : centralPreviewEnabled ? 'Preview' : 'Preview off'}
      </button>

      <div className="flex-1" />

      {error && (
        <span className="text-[11px] text-rose-300 bg-rose-950/60 border border-rose-800 px-2 py-1 rounded max-w-md truncate" title={error}>
          {error}
        </span>
      )}

      <a
        href="/mosaicoaovivo"
        target="_blank"
        rel="noreferrer"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-slate-400 hover:text-cyan-300 border border-slate-700 hover:border-cyan-500/50 transition"
        title="Abrir o telão em outra janela (arraste para o projetor e dê F11)"
      >
        <ExternalLink className="w-4 h-4" />
        Abrir Telão
      </a>
    </div>
  );
};

export default TransportBar;
