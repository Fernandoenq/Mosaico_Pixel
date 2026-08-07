import React from 'react';
import { useMosaicStore } from '../../store/mosaicStore';
import { Lock, Unlock, Trash2, RefreshCw } from 'lucide-react';

export const TileContextMenu: React.FC = () => {
  const { contextMenu, setContextMenu, lockTile, unlockTile, deleteTile, lockedTiles, setSwapModalCell } =
    useMosaicStore();

  if (!contextMenu) return null;

  const key = `${contextMenu.row}_${contextMenu.col}`;
  const isLocked = lockedTiles.has(key);

  const handleLockToggle = () => {
    if (isLocked) unlockTile(contextMenu.row, contextMenu.col);
    else lockTile(contextMenu.row, contextMenu.col);
    setContextMenu(null);
  };

  const handleDelete = () => {
    deleteTile(contextMenu.row, contextMenu.col);
    setContextMenu(null);
  };

  const handleSwap = () => {
    setSwapModalCell({ row: contextMenu.row, col: contextMenu.col });
    setContextMenu(null);
  };

  return (
    <div
      style={{ left: contextMenu.x, top: contextMenu.y }}
      className="fixed bg-slate-900 border border-slate-700/90 rounded-lg shadow-2xl py-1.5 w-44 z-50 text-slate-200 text-xs flex flex-col gap-0.5"
    >
      <div className="px-3 py-1 text-[10px] font-mono text-slate-400 border-b border-slate-800">
        Ladrilho [{contextMenu.row}, {contextMenu.col}]
      </div>
      
      <button
        onClick={handleLockToggle}
        className="flex items-center gap-2 px-3 py-1.5 hover:bg-slate-800 text-left transition"
      >
        {isLocked ? (
          <>
            <Unlock className="w-3.5 h-3.5 text-amber-400" />
            <span>Destravar Imagem</span>
          </>
        ) : (
          <>
            <Lock className="w-3.5 h-3.5 text-cyan-400" />
            <span>Travar Imagem (Lock)</span>
          </>
        )}
      </button>

      <button
        onClick={handleSwap}
        className="flex items-center gap-2 px-3 py-1.5 hover:bg-slate-800 text-left transition"
      >
        <RefreshCw className="w-3.5 h-3.5 text-emerald-400" />
        <span>Substituir Foto</span>
      </button>

      <button
        onClick={handleDelete}
        className="flex items-center gap-2 px-3 py-1.5 hover:bg-rose-900/40 text-rose-400 text-left transition"
      >
        <Trash2 className="w-3.5 h-3.5" />
        <span>Deletar Ladrilho</span>
      </button>
    </div>
  );
};
