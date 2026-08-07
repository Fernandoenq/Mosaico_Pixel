import React, { useEffect } from 'react';
import { PixiViewport } from '../components/Canvas/PixiViewport';
import { useMosaicStore } from '../store/mosaicStore';
import { fetchRunConfig } from '../lib/api';

/**
 * Telão. Não edita nada: a configuração e o estado do show vêm do backend
 * (GET /api/config na abertura, WebSocket depois). Fotos só pousam com o show
 * em `running` — é isso que o Play do painel controla.
 */
export const MosaicoAoVivo: React.FC = () => {
  const pendingPhotos = useMosaicStore((s) => s.pendingPhotos);
  const runState = useMosaicStore((s) => s.runState);
  const { removePendingPhoto, setDisplayMode, applyServerConfig, setRunState } = useMosaicStore();

  // Modo telão: desliga as alças de edição, minimapa, lupa e pincel.
  useEffect(() => {
    setDisplayMode(true);
    return () => setDisplayMode(false);
  }, []);

  // Hidrata do servidor antes do primeiro frame — nunca dos defaults locais.
  useEffect(() => {
    fetchRunConfig()
      .then(({ config, run_state }) => {
        applyServerConfig(config);
        setRunState(run_state);
      })
      .catch((err) => console.error('[Telão] Falha ao carregar configuração:', err));
  }, []);

  // Auto-aprovação silenciosa: só enquanto o show estiver rodando.
  useEffect(() => {
    if (runState !== 'running' || pendingPhotos.length === 0) return;

    const seq = useMosaicStore.getState().fillSequence || 'color_match';
    const photo = pendingPhotos[0];
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(
          `/api/moderation/approve/${photo.id}?fill_sequence=${seq}`,
          { method: 'POST' }
        );
        // 409 = o show parou entre o agendamento e o envio; a foto fica na fila.
        if (res.ok) removePendingPhoto(photo.id);
      } catch {}
    }, 300);
    return () => clearTimeout(timer);
  }, [pendingPhotos, runState]);

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#000', cursor: 'none' }}>
      <PixiViewport />

      {runState !== 'running' && (
        <div className="absolute bottom-4 right-4 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-950/70 border border-slate-700 text-[11px] font-bold tracking-wider text-slate-400">
          <span className={`w-2 h-2 rounded-full ${runState === 'paused' ? 'bg-amber-400' : 'bg-slate-500'}`} />
          {runState === 'paused' ? 'PAUSADO' : 'AGUARDANDO PLAY'}
        </div>
      )}
    </div>
  );
};

export default MosaicoAoVivo;
