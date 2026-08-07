import React, { useState } from 'react';
import { useMosaicStore } from '../../store/mosaicStore';
import { CheckCircle, XCircle, Clock, CheckCheck, Trash2 } from 'lucide-react';

export const ModerationQueue: React.FC = () => {
  const { pendingPhotos, removePendingPhoto } = useMosaicStore();
  const [approving, setApproving] = useState<string | null>(null);
  const [approvingAll, setApprovingAll] = useState(false);

  const getFilleSequence = () => {
    try {
      return useMosaicStore.getState().fillSequence || 'color_match';
    } catch {
      return 'color_match';
    }
  };

  const handleApprove = async (id: string) => {
    setApproving(id);
    try {
      const seq = getFilleSequence();
      // IMPORTANTE: Primeiro chama o backend, depois remove do estado
      const res = await fetch(`/api/moderation/approve/${id}?fill_sequence=${seq}&force=true`, { method: 'POST' });
      if (res.ok) {
        removePendingPhoto(id);
      } else {
        console.error('[Approve] Falha na aprovação:', await res.text());
      }
    } catch (err) {
      console.error('[Approve] Erro de rede:', err);
    } finally {
      setApproving(null);
    }
  };

  const handleReject = async (id: string) => {
    await fetch(`/api/moderation/reject/${id}`, { method: 'POST' });
    removePendingPhoto(id);
  };

  const handleApproveAll = async () => {
    if (pendingPhotos.length === 0) return;
    setApprovingAll(true);
    const seq = getFilleSequence();
    const toApprove = [...pendingPhotos];

    for (const photo of toApprove) {
      try {
        const res = await fetch(`/api/moderation/approve/${photo.id}?fill_sequence=${seq}&force=true`, { method: 'POST' });
        if (res.ok) {
          removePendingPhoto(photo.id);
        }
        // Pequena pausa para não sobrecarregar e permitir animações
        await new Promise(r => setTimeout(r, 700));
      } catch (err) {
        console.error('[ApproveAll] Erro:', err);
      }
    }
    setApprovingAll(false);
  };

  const handleRejectAll = async () => {
    const toReject = [...pendingPhotos];
    for (const photo of toReject) {
      await fetch(`/api/moderation/reject/${photo.id}`, { method: 'POST' });
      removePendingPhoto(photo.id);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border-r border-slate-800 p-4 text-slate-100 w-80">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2 text-cyan-400">
          <Clock className="w-5 h-5" />
          <h3 className="font-bold text-sm uppercase tracking-wider">Fila de Moderação</h3>
        </div>
        <span className="px-2 py-0.5 bg-cyan-500/20 text-cyan-300 text-xs font-mono rounded-full border border-cyan-500/30">
          {pendingPhotos.length}
        </span>
      </div>

      {/* Bulk Actions */}
      {pendingPhotos.length > 0 && (
        <div className="flex gap-2 mb-3">
          <button
            onClick={handleApproveAll}
            disabled={approvingAll}
            className="flex-1 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-xs font-bold py-2 px-2 rounded-lg flex items-center justify-center gap-1.5 transition shadow border border-emerald-500/30"
          >
            <CheckCheck className="w-3.5 h-3.5" />
            {approvingAll ? '⟳ Aprovando...' : `✅ Aprovar Todas (${pendingPhotos.length})`}
          </button>
          <button
            onClick={handleRejectAll}
            className="bg-rose-900/60 hover:bg-rose-700 text-rose-300 text-xs font-bold py-2 px-3 rounded-lg flex items-center justify-center gap-1 transition"
            title="Rejeitar todas"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Photo List */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {pendingPhotos.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-slate-500 text-xs gap-2">
            <Clock className="w-8 h-8 stroke-1" />
            <span>Aguardando novas fotos do terminal...</span>
          </div>
        ) : (
          pendingPhotos.map((photo) => (
            <div
              key={photo.id}
              className={`bg-slate-800/80 border rounded-lg p-2.5 flex gap-3 items-center shadow-lg transition ${
                approving === photo.id
                  ? 'border-cyan-500/60 bg-cyan-900/20'
                  : 'border-slate-700/60 hover:border-slate-600'
              }`}
            >
              <img
                src={photo.url}
                alt="Pending Candidate"
                className="w-16 h-16 object-cover rounded border border-slate-700 bg-slate-950"
              />
              <div className="flex-1 flex flex-col justify-between h-full gap-2">
                <span className="text-[11px] font-mono text-slate-400 truncate">{photo.id}</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprove(photo.id)}
                    disabled={approving === photo.id || approvingAll}
                    className="flex-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold py-1.5 px-2 rounded flex items-center justify-center gap-1 transition shadow-sm"
                  >
                    {approving === photo.id ? (
                      <span className="animate-spin inline-block">⟳</span>
                    ) : (
                      <CheckCircle className="w-3.5 h-3.5" />
                    )}
                    {approving === photo.id ? 'Colocando...' : 'Aprovar'}
                  </button>
                  <button
                    onClick={() => handleReject(photo.id)}
                    disabled={approving === photo.id}
                    className="flex-1 bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white text-xs font-semibold py-1.5 px-2 rounded flex items-center justify-center gap-1 transition shadow-sm"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                    Rejeitar
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};



