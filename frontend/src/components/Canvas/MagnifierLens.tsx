import React from 'react';

interface Props {
  mousePos: { x: number; y: number } | null;
  active: boolean;
}

export const MagnifierLens: React.FC<Props> = ({ mousePos, active }) => {
  if (!active || !mousePos) return null;

  const lensSize = 140;
  const radius = lensSize / 2;

  return (
    <div
      style={{
        left: mousePos.x - radius,
        top: mousePos.y - radius,
        width: lensSize,
        height: lensSize,
      }}
      className="fixed pointer-events-none rounded-full border-2 border-cyan-400 shadow-2xl overflow-hidden z-40 bg-slate-950/80 backdrop-blur-sm"
    >
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="w-2 h-2 rounded-full bg-cyan-400 shadow" />
      </div>
      <span className="absolute bottom-1 right-2 text-[9px] font-mono text-cyan-300 bg-slate-900/80 px-1 rounded">
        2.5x
      </span>
    </div>
  );
};
