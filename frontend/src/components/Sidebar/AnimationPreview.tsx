import React, { useEffect, useRef } from 'react';
import * as PIXI from 'pixi.js';
import gsap from 'gsap';
import { AnimationPreset, animateTileFlight } from '../../utils/gsapAnimations';

const STAGE_W = 288;
const STAGE_H = 150;
const PREVIEW_COLS = 8;
const PREVIEW_ROWS = 5;
const TILE_W = STAGE_W / PREVIEW_COLS;
const TILE_H = STAGE_H / PREVIEW_ROWS;

/** Textura sintética que lê como "foto" sem depender de arquivo no disco. */
const buildSampleTexture = (): PIXI.Texture => {
  const canvas = document.createElement('canvas');
  canvas.width = 64;
  canvas.height = 64;
  const ctx = canvas.getContext('2d')!;

  const gradient = ctx.createLinearGradient(0, 0, 64, 64);
  gradient.addColorStop(0, '#22d3ee');
  gradient.addColorStop(1, '#0f766e');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 64, 64);

  // Silhueta simples de pessoa, para o recorte parecer um retrato
  ctx.fillStyle = 'rgba(15, 23, 42, 0.55)';
  ctx.beginPath();
  ctx.arc(32, 25, 11, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(32, 58, 20, 16, 0, 0, Math.PI * 2);
  ctx.fill();

  return PIXI.Texture.from(canvas);
};

interface AnimationPreviewProps {
  preset: AnimationPreset;
  duration: number;
  ease: string;
  centralPreviewDuration: number;
  gridShape: 'square' | 'diamond' | 'hexagon' | 'circle';
  /** Muda para forçar um replay imediato da animação. */
  replayKey: number;
}

/**
 * Preview fiel: roda o MESMO `animateTileFlight` do telão, num palco reduzido.
 *
 * A aplicação PixiJS é criada UMA vez e vive até desmontar — recriar o contexto
 * WebGL a cada passo do slider estouraria o limite de contextos do navegador.
 * Os parâmetros entram por ref e valem a partir da próxima repetição.
 */
export const AnimationPreview: React.FC<AnimationPreviewProps> = ({
  preset,
  duration,
  ease,
  centralPreviewDuration,
  gridShape,
  replayKey,
}) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const paramsRef = useRef({ preset, duration, ease, centralPreviewDuration, gridShape });
  const restartRef = useRef<() => void>(() => {});

  paramsRef.current = { preset, duration, ease, centralPreviewDuration, gridShape };

  useEffect(() => {
    if (!hostRef.current) return;

    const app = new PIXI.Application({
      width: STAGE_W,
      height: STAGE_H,
      backgroundColor: 0x020617,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
    });
    hostRef.current.innerHTML = '';
    hostRef.current.appendChild(app.view as HTMLCanvasElement);

    // Grade de referência para dar noção de onde o ladrilho vai pousar
    const grid = new PIXI.Graphics();
    grid.lineStyle(1, 0x1e293b, 1);
    for (let c = 0; c <= PREVIEW_COLS; c++) grid.moveTo(c * TILE_W, 0).lineTo(c * TILE_W, STAGE_H);
    for (let r = 0; r <= PREVIEW_ROWS; r++) grid.moveTo(0, r * TILE_H).lineTo(STAGE_W, r * TILE_H);
    app.stage.addChild(grid);

    const landed = new PIXI.Container();
    const flying = new PIXI.Container();
    app.stage.addChild(landed);
    app.stage.addChild(flying);

    const texture = buildSampleTexture();
    let timeline: gsap.core.Timeline | null = null;
    let timer: number | undefined;
    let cancelled = false;
    let shot = 0;

    const playOnce = () => {
      if (cancelled) return;
      landed.removeChildren();
      flying.removeChildren();

      // Percorre células diferentes a cada repetição para a trajetória variar
      const col = [1, 6, 3, 5, 0, 7][shot % 6];
      const row = [1, 3, 0, 4, 2][shot % 5];
      shot += 1;

      const current = paramsRef.current;
      timeline = animateTileFlight({
        flyingContainer: flying,
        landedContainer: landed,
        texture,
        startX: STAGE_W / 2,
        startY: STAGE_H / 2,
        targetX: col * TILE_W,
        targetY: row * TILE_H,
        targetWidth: TILE_W,
        targetHeight: TILE_H,
        gridShape: current.gridShape,
        preset: current.preset,
        duration: current.duration,
        centralPreviewDuration: current.centralPreviewDuration,
        ease: current.ease,
        // Cartão proporcional ao palco reduzido, mesma razão do telão
        cardSize: Math.round(STAGE_H * 0.55),
        onComplete: () => {
          timer = window.setTimeout(playOnce, 700);
        },
      });
    };

    restartRef.current = () => {
      if (timer) window.clearTimeout(timer);
      timeline?.kill();
      playOnce();
    };

    playOnce();

    return () => {
      cancelled = true;
      restartRef.current = () => {};
      if (timer) window.clearTimeout(timer);
      timeline?.kill();
      app.destroy(true, { children: true });
    };
  }, []);

  // Troca de preset, ajuste de curva ou clique em "Repetir": reinicia na hora.
  useEffect(() => {
    restartRef.current();
  }, [preset, ease, gridShape, replayKey]);

  return (
    <div
      ref={hostRef}
      className="rounded-lg overflow-hidden border border-slate-700 bg-slate-950 shadow-inner"
      style={{ width: STAGE_W, height: STAGE_H }}
    />
  );
};

export default AnimationPreview;
