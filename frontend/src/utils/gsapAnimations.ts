import gsap from 'gsap';
import * as PIXI from 'pixi.js';

export type AnimationPreset = 'fly_parabolic' | 'hsbc_cascade' | 'spiral' | 'wave' | 'flip_3d';

/** Valor de easing que significa "usa a curva natural do preset". */
export const AUTO_EASE = 'auto';

/**
 * Curva característica de cada preset. É o que roda enquanto o painel estiver
 * em "Automático" — assim o visual de fábrica de cada preset é preservado e o
 * seletor de easing continua valendo quando o operador escolhe uma curva.
 */
export const PRESET_DEFAULT_EASE: Record<AnimationPreset, string> = {
  fly_parabolic: 'power3.inOut',
  hsbc_cascade: 'cubic.out',
  spiral: 'power3.inOut',
  wave: 'elastic.out(1, 0.5)',
  flip_3d: 'power2.out',
};

const resolveEase = (ease: string | undefined, preset: AnimationPreset): string =>
  !ease || ease === AUTO_EASE ? PRESET_DEFAULT_EASE[preset] : ease;

/** Tamanho do cartão de preview central, proporcional à altura do telão. */
export const previewCardSize = (screenHeight: number): number =>
  Math.max(80, Math.round(screenHeight * 0.278));

export interface FlyAnimationParams {
  flyingContainer: PIXI.Container;
  landedContainer: PIXI.Container;
  texture: PIXI.Texture;
  startX: number;
  startY: number;
  targetX: number;
  targetY: number;
  targetWidth: number;
  targetHeight: number;
  gridShape?: 'square' | 'diamond' | 'hexagon' | 'circle';
  preset?: AnimationPreset;
  duration?: number;
  centralPreviewDuration?: number;
  cellFilter?: string;
  ease?: string;
  /** Lado do cartão central em px do palco. Default 300 (telão 1080p). */
  cardSize?: number;
  onComplete?: () => void;
}

export const applySpriteFilter = (sprite: PIXI.Sprite, filterId?: string) => {
  if (!filterId || filterId === 'none') {
    sprite.tint = 0xFFFFFF;
    sprite.filters = [];
    return;
  }
  if (filterId === 'red') sprite.tint = 0xFF0044;
  else if (filterId === 'gold') sprite.tint = 0xFFCC00;
  else if (filterId === 'cyan') sprite.tint = 0x00FFFF;
  else if (filterId === 'green') sprite.tint = 0x00FF66;
  else if (filterId === 'sepia') sprite.tint = 0xFFB380;
  else if (filterId === 'grayscale') {
    const cm = new PIXI.ColorMatrixFilter();
    cm.blackAndWhite(true);
    sprite.filters = [cm];
  } else {
    sprite.tint = 0xFFFFFF;
    sprite.filters = [];
  }
};

/**
 * Orquestra as Animações GSAP da Viewport com suporte a múltiplos presets:
 * - fly_parabolic: Hold no centro + planeio parabólico
 * - hsbc_cascade: Entrada em cascata com diamante
 * - spiral: Entrada em espiral giratória (720deg)
 * - wave: Expansão em onda com efeito elástico
 * - flip_3d: Rotação 3D no eixo Y
 *
 * O easing do voo principal vem do painel; em "auto" cada preset usa a sua
 * curva característica (ver PRESET_DEFAULT_EASE).
 */
export const animateTileFlight = ({
  flyingContainer,
  landedContainer,
  texture,
  startX,
  startY,
  targetX,
  targetY,
  targetWidth,
  targetHeight,
  gridShape = 'square',
  preset = 'hsbc_cascade',
  duration = 0.8,
  centralPreviewDuration = 0.8,
  cellFilter,
  ease = AUTO_EASE,
  cardSize = 300,
  onComplete,
}: FlyAnimationParams): gsap.core.Timeline => {
  const flightEase = resolveEase(ease, preset);

  // Escala em que o cartão central encosta no tamanho real do ladrilho. Derivada
  // do cartão para o pouso casar em qualquer resolução de telão.
  const landScale = Math.max(0.02, targetWidth / cardSize);

  // Container wrapper para o Preview Central com moldura (Camada 2 - Foto Voadora)
  const wrapper = new PIXI.Container();
  wrapper.x = startX;
  wrapper.y = startY;

  const half = cardSize / 2;
  const pad = cardSize / 60;
  const cardBorder = new PIXI.Graphics();
  cardBorder.lineStyle(Math.max(1, cardSize / 100), 0x00ffff, 0.9);
  cardBorder.drawRoundedRect(-(half + pad), -(half + pad), cardSize + pad * 2, cardSize + pad * 2, cardSize * 0.053);
  wrapper.addChild(cardBorder);

  // Sprite de preview central com anchor em 0.5 (centro)
  const previewSprite = new PIXI.Sprite(texture);
  previewSprite.anchor.set(0.5);
  previewSprite.width = cardSize;
  previewSprite.height = cardSize;
  applySpriteFilter(previewSprite, cellFilter);
  wrapper.addChild(previewSprite);

  flyingContainer.addChild(wrapper);

  /**
   * finishAnimation: Cria o sprite final que pousa no tile.
   * IMPORTANTE: O sprite final NÃO usa anchor.set(0.5) - ele usa x=targetX, y=targetY
   * e width/height para preencher o tile completamente.
   * A máscara é criada num sub-container para que sprite e máscara ficam juntos.
   */
  const finishAnimation = () => {
    flyingContainer.removeChild(wrapper);

    // Sub-container agrupa sprite + máscara no mesmo espaço
    const tileContainer = new PIXI.Container();
    
    const landedSprite = new PIXI.Sprite(texture);
    // SEM anchor (padrão 0,0) para posicionamento correto no tile
    landedSprite.x = 0;
    landedSprite.y = 0;
    landedSprite.width = targetWidth;
    landedSprite.height = targetHeight;
    applySpriteFilter(landedSprite, cellFilter);

    if (gridShape === 'diamond') {
      const mask = new PIXI.Graphics();
      mask.beginFill(0xffffff);
      const hw = targetWidth / 2;
      const hh = targetHeight / 2;
      mask.moveTo(hw, 0);         // topo
      mask.lineTo(targetWidth, hh); // direita
      mask.lineTo(hw, targetHeight);// baixo
      mask.lineTo(0, hh);          // esquerda
      mask.lineTo(hw, 0);
      mask.endFill();
      tileContainer.addChild(landedSprite);
      tileContainer.addChild(mask);
      landedSprite.mask = mask;
    } else if (gridShape === 'hexagon') {
      const mask = new PIXI.Graphics();
      mask.beginFill(0xffffff);
      const cx = targetWidth / 2;
      const cy = targetHeight / 2;
      const rad = Math.min(targetWidth, targetHeight) / 2;
      for (let k = 0; k < 6; k++) {
        const angle = (Math.PI / 3) * k - Math.PI / 6;
        const x = cx + rad * Math.cos(angle);
        const y = cy + rad * Math.sin(angle);
        if (k === 0) mask.moveTo(x, y);
        else mask.lineTo(x, y);
      }
      mask.endFill();
      tileContainer.addChild(landedSprite);
      tileContainer.addChild(mask);
      landedSprite.mask = mask;
    } else if (gridShape === 'circle') {
      const mask = new PIXI.Graphics();
      mask.beginFill(0xffffff);
      const cx = targetWidth / 2;
      const cy = targetHeight / 2;
      const rad = Math.min(targetWidth, targetHeight) / 2;
      mask.drawCircle(cx, cy, rad);
      mask.endFill();
      tileContainer.addChild(landedSprite);
      tileContainer.addChild(mask);
      landedSprite.mask = mask;
    } else {
      tileContainer.addChild(landedSprite);
    }

    tileContainer.x = targetX;
    tileContainer.y = targetY;
    landedContainer.addChild(tileContainer);

    if (onComplete) onComplete();
  };

  const tl = gsap.timeline({ onComplete: finishAnimation });

  // 🌟 FASE 1: PREVIEW CENTRAL NO CENTRO DA TELA (CAMADA 2)
  wrapper.scale.set(0.1);
  tl.to(wrapper, {
    duration: 0.35,
    scale: 1.0,
    ease: 'back.out(1.7)',
  }).to(wrapper, {
    duration: centralPreviewDuration, // Hold no centro em tamanho de cartão
    scale: 1.05,
    ease: 'none',
  });

  // 🌟 FASE 2: VOO DO CENTRO ATÉ O TILE ALVO (CAMADA 2 → CAMADA 1)
  const targetCX = targetX + targetWidth / 2;
  const targetCY = targetY + targetHeight / 2;

  if (preset === 'spiral') {
    // 🌀 Entrada em Espiral Giratória (720°)
    tl.to(wrapper, {
      duration: duration * 0.4,
      scale: 0.8,
      rotation: Math.PI * 2,
      ease: 'power2.out',
    }).to(wrapper, {
      duration: duration * 0.6,
      x: targetCX,
      y: targetCY,
      scale: landScale,
      rotation: Math.PI * 4,
      ease: flightEase,
    });
  } else if (preset === 'hsbc_cascade') {
    // 💎 Cascata HSBC (Hold Central + Deslize em Diamante)
    tl.to(wrapper, {
      duration: 0.3,
      scale: 1.1,
      ease: 'back.out(2)',
    }).to(wrapper, {
      duration: duration,
      x: targetCX,
      y: targetCY,
      scale: landScale,
      ease: flightEase,
    });
  } else if (preset === 'wave') {
    // 🌊 Onda Sequencial com Bounce Elástico
    tl.to(wrapper, {
      duration: duration,
      x: targetCX,
      y: targetCY,
      scale: landScale,
      ease: flightEase,
    });
  } else if (preset === 'flip_3d') {
    // 🔄 Efeito Flip 3D (Rotação no Eixo Y): colapsa no caminho e reabre no tile
    tl.to(wrapper, {
      duration: duration * 0.5,
      x: targetCX,
      y: targetCY,
      scaleX: 0,
      ease: 'power2.in',
    }).to(wrapper, {
      duration: duration * 0.5,
      scale: landScale,
      ease: flightEase,
    });
  } else {
    // 🚀 Padrão: Voo Parabólico (Hold Central + Planeio Suave)
    tl.to(wrapper, {
      duration: 0.4,
      scale: 1.1,
      ease: 'back.out(1.7)',
    }).to(wrapper, {
      duration: duration,
      x: targetCX,
      y: targetCY,
      scale: landScale,
      ease: flightEase,
    });
  }

  // Devolvida para quem precisa interromper o voo (ex.: replay do preview).
  return tl;
};

export interface MosaicOutroParams {
  landedContainer: PIXI.Container;
  screenWidth: number;
  screenHeight: number;
  duration?: number;
  ease?: string;
  onComplete?: () => void;
}

/**
 * 💥 Encerramento: dispersa o mosaico inteiro para fora da tela.
 *
 * É uma ação de fim de evento disparada pelo painel, não um preset por foto —
 * cada ladrilho sai radialmente a partir do centro do telão, com um leve
 * escalonamento por posição para a onda parecer orgânica.
 */
export const animateMosaicOutro = ({
  landedContainer,
  screenWidth,
  screenHeight,
  duration = 1.4,
  ease = 'power3.in',
  onComplete,
}: MosaicOutroParams) => {
  const tiles = [...landedContainer.children] as PIXI.Container[];
  if (tiles.length === 0) {
    onComplete?.();
    return;
  }

  const centerX = screenWidth / 2;
  const centerY = screenHeight / 2;
  const flightDistance = Math.hypot(screenWidth, screenHeight);
  let remaining = tiles.length;

  tiles.forEach((tile, index) => {
    const dx = tile.x + (tile.width || 1) / 2 - centerX;
    const dy = tile.y + (tile.height || 1) / 2 - centerY;
    const length = Math.hypot(dx, dy) || 1;
    // Quem está mais perto do centro sai depois: a dispersão abre de dentro pra fora.
    const delay = (1 - Math.min(1, length / (flightDistance / 2))) * 0.35;

    gsap.to(tile, {
      duration,
      delay,
      x: tile.x + (dx / length) * flightDistance,
      y: tile.y + (dy / length) * flightDistance,
      rotation: ((index % 7) - 3) * 0.4,
      alpha: 0,
      ease,
      onComplete: () => {
        remaining -= 1;
        if (remaining === 0) {
          landedContainer.removeChildren();
          onComplete?.();
        }
      },
    });
  });
};

/**
 * Animação de FLIP (troca manual de foto via modal Left-Click).
 */
export const animateTileFlip = (
  sprite: PIXI.Sprite,
  newTexture: PIXI.Texture,
  onComplete?: () => void
) => {
  gsap.timeline({
    onComplete: () => {
      sprite.texture = newTexture;
      gsap.to(sprite, { duration: 0.3, scaleX: 1, ease: 'power2.out', onComplete });
    }
  }).to(sprite, {
    duration: 0.3,
    scaleX: 0,
    ease: 'power2.in'
  });
};
