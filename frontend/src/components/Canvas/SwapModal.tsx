import React, { useEffect, useState } from 'react';
import { useMosaicStore } from '../../store/mosaicStore';
import { X, Sparkles } from 'lucide-react';

interface Suggestion {
  id: string;
  url: string;
  score: number;
}

export const SwapModal: React.FC = () => {
  const { swapModalCell, setSwapModalCell, placeTile, screenWidth, screenHeight, rows, cols } = useMosaicStore();
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!swapModalCell) return;
    setLoading(true);
    fetch(`/api/mosaic/suggestions/${swapModalCell.row}/${swapModalCell.col}`)
      .then((res) => res.json())
      .then((data) => {
        setSuggestions(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [swapModalCell]);

  if (!swapModalCell) return null;

  const handleSelectPhoto = (photo: Suggestion) => {
    const tileW = screenWidth / cols;
    const tileH = screenHeight / rows;
    
    placeTile({
      photo_id: photo.id,
      url: photo.url,
      row: swapModalCell.row,
      col: swapModalCell.col,
      target_x: swapModalCell.col * tileW,
      target_y: swapModalCell.row * tileH,
      score: photo.score,
    });
    
    setSwapModalCell(null);
  };

  return (
    <div className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700/80 rounded-xl p-5 max-w-lg w-full shadow-2xl flex flex-col gap-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2 text-cyan-400">
            <Sparkles className="w-5 h-5" />
            <h3 className="font-bold text-sm uppercase tracking-wider">
              Substituição Manual (Top 5 Sugestões)
            </h3>
          </div>
          <button
            onClick={() => setSwapModalCell(null)}
            className="text-slate-400 hover:text-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="text-xs text-slate-300">
          Substituir foto no Ladrilho{' '}
          <span className="font-mono text-cyan-400">
            [{swapModalCell.row}, {swapModalCell.col}]
          </span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-32 text-xs text-slate-500">
            Calculando melhores combinações de cor...
          </div>
        ) : suggestions.length === 0 ? (
          <div className="text-center text-xs text-slate-500 py-8">
            Nenhuma foto candidata disponível no momento.
          </div>
        ) : (
          <div className="grid grid-cols-5 gap-3">
            {suggestions.map((item, idx) => (
              <button
                key={item.id}
                onClick={() => handleSelectPhoto(item)}
                className="group flex flex-col gap-1.5 items-center bg-slate-800/80 hover:bg-cyan-950/40 p-2 rounded-lg border border-slate-700 hover:border-cyan-500 transition shadow"
              >
                <img
                  src={item.url}
                  alt={`Option ${idx + 1}`}
                  className="w-full h-16 object-cover rounded border border-slate-700 group-hover:scale-105 transition"
                />
                <span className="text-[10px] font-mono text-slate-400 group-hover:text-cyan-300">
                  #{idx + 1}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
