import React from 'react';

interface Props {
  width?: number;
  height?: number;
  viewportX?: number;
  viewportY?: number;
  zoomScale?: number;
}

export const MiniMap: React.FC<Props> = ({
  width = 180,
  height = 100,
  viewportX = 0,
  viewportY = 0,
  zoomScale = 1,
}) => {
  return (
    <div
      style={{ width, height }}
      className="absolute bottom-4 right-4 bg-slate-900/90 border border-slate-700/80 rounded-lg p-1.5 shadow-2xl backdrop-blur flex flex-col gap-1 pointer-events-none z-30"
    >
      <span className="text-[9px] font-mono font-semibold text-slate-400 tracking-wider">
        MINI-MAP NAVIGATOR ({Math.round(zoomScale * 100)}%)
      </span>
      <div className="relative flex-1 bg-slate-950 rounded overflow-hidden border border-slate-800">
        {/* Retângulo que indica a posição visível no zoom */}
        <div
          style={{
            left: `${Math.max(0, Math.min(80, (viewportX / 1920) * 100))}%`,
            top: `${Math.max(0, Math.min(80, (viewportY / 1080) * 100))}%`,
            width: `${100 / zoomScale}%`,
            height: `${100 / zoomScale}%`,
          }}
          className="absolute border-2 border-cyan-400 bg-cyan-400/20 rounded-sm shadow-sm transition-all duration-75"
        />
      </div>
    </div>
  );
};
