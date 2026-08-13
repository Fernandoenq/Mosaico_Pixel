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

/**
 * Tamanho do cartão de preview central, em px do palco.
 *
 * A fração vem da config (slider "Tamanho do Preview" no painel) e não do
 * código: assim o operador vê o efeito na hora, sem recarregar o telão.
 * 1.0 = a foto mais a moldura ocupam a altura inteira do telão.
 */
export const previewCardSize = (screenHeight: number, scale = 1.0): number => {
  const fracao = Math.min(1, Math.max(0.2, scale));
  // 0.97 reserva o espaco da moldura: em 100% o conjunto ocupa a altura
  // inteira do telao sem passar das bordas.
  return Math.max(150, Math.round(screenHeight * fracao * 0.97));
};

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
  /** Falso: sem cartao no centro, a foto vai direto para a celula. */
  centralPreviewEnabled?: boolean;
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
  // Vermelho da marca sem apagar o rosto. O tint MULTIPLICA: com 0xFF0044 o
  // verde e o azul da pele vão quase a zero e sobra uma silhueta chapada.
  // Mantendo um piso alto nos três canais a foto continua legível e ainda
  // lê como vermelho.
  else if (filterId === 'red_suave') sprite.tint = 0xFF8899;
  else if (filterId === 'branco_leve') {
    // Véu branco leve. `tint` MULTIPLICA, então nunca clareia — o máximo que
    // 0xFFFFFF faz é não mexer. Para lavar a foto é preciso somar branco, e
    // quem soma é o deslocamento da ColorMatrix (a 5ª coluna).
    const k = 0.35;
    const cm = new PIXI.ColorMatrixFilter();
    cm.matrix = [
      1 - k, 0, 0, 0, k,
      0, 1 - k, 0, 0, k,
      0, 0, 1 - k, 0, k,
      0, 0, 0, 1, 0,
    ];
    sprite.tint = 0xFFFFFF;
    sprite.filters = [cm];
  }
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
  centralPreviewEnabled = true,
  centralPreviewDuration = 10.0,
  cellFilter,
  ease = AUTO_EASE,
  cardSize = 1000,
  onComplete,
}: FlyAnimationParams): gsap.core.Timeline => {
  const flightEase = resolveEase(ease, preset);

  // Container wrapper para o Preview Central com moldura (Camada 2 - Foto Voadora)
  const wrapper = new PIXI.Container();
  wrapper.x = startX;
  wrapper.y = startY;

  const pad = cardSize / 90;
  const cardBorder = new PIXI.Graphics();

  // Sprite de preview central com anchor em 0.5 (centro)
  const previewSprite = new PIXI.Sprite(texture);
  previewSprite.anchor.set(0.5);

  // Largura efetiva do preview. Vira `cardSize` só quando a foto é quadrada;
  // o voo é escalado a partir dela para o cartão pousar do tamanho do ladrilho.
  let previewWidth = cardSize;

  /**
   * Encaixa a foto no cartão preservando a proporção e centralizada nos dois
   * eixos. Antes o sprite era forçado a cardSize×cardSize: como a cabine entrega
   * retrato 9:16, o rosto saía achatado na horizontal.
   */
  const applyPreviewDims = () => {
    const tw = texture.width;
    const th = texture.height;
    if (!texture.valid || tw <= 0 || th <= 0) return;

    const escala = Math.min(cardSize / tw, cardSize / th);
    const w = Math.round(tw * escala);
    const h = Math.round(th * escala);

    previewSprite.width = w;
    previewSprite.height = h;
    previewWidth = w;

    // A moldura acompanha a foto — num cartão quadrado sobraria borda vazia
    // dos lados e o conjunto pareceria desalinhado no centro do telão.
    cardBorder.clear();
    cardBorder.lineStyle(Math.max(1, cardSize / 100), 0x00ffff, 0.9);
    cardBorder.drawRoundedRect(
      -(w / 2 + pad),
      -(h / 2 + pad),
      w + pad * 2,
      h + pad * 2,
      cardSize * 0.053,
    );
  };
  applyPreviewDims();
  if (!texture.valid) {
    texture.baseTexture.once('loaded', applyPreviewDims);
  }

  // A moldura ciano só faz sentido no cartão central; no voo direto ela viraria
  // um retângulo brilhante atravessando a tela.
  cardBorder.visible = centralPreviewEnabled;
  wrapper.addChild(cardBorder);
  // Em voo a foto vai na cor ORIGINAL: o cartão central existe para a pessoa se
  // ver, e com o tinte da célula de destino ela se via vermelha ou dourada. A
  // cor da marca entra só no pouso — é o mesmo que o vídeo de referência faz.
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

    const applyLandedDims = () => {
      if (texture.valid && texture.width > 0 && texture.height > 0) {
        landedSprite.width = targetWidth;
        landedSprite.height = targetHeight;
      }
    };
    applyLandedDims();
    if (!texture.valid) {
      texture.baseTexture.once('loaded', applyLandedDims);
    }

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

  // Escala em que o cartão encosta no tamanho real do ladrilho. Sai da largura
  // efetiva do preview (não do cartão), senão o pouso dá um salto de tamanho.
  const landScale = Math.max(0.02, targetWidth / previewWidth);

  const tl = gsap.timeline({ onComplete: finishAnimation });

  /**
   * A escala é animada pelo ObservablePoint (`wrapper.scale`), nunca pela
   * propriedade `wrapper.scale` do Container.
   *
   * Sem o PixiPlugin, `gsap.to(wrapper, {scale: 1})` SUBSTITUI o ponto por um
   * número; o setter do PIXI então faz `copyFrom(1)`, lê `(1).x` — undefined —
   * e a escala do cartão vira NaN. O preview central simplesmente não era
   * desenhado: por isso aumentar `cardSize` não mudava nada na tela.
   */
  const escala = wrapper.scale;
  const escalarPara = (valor: number, vars: gsap.TweenVars) =>
    ({ ...vars, x: valor, y: valor });

  // 🌟 FASE 1: PREVIEW CENTRAL NO CENTRO DA TELA (CAMADA 2)
  if (centralPreviewEnabled) {
    escala.set(0.1);
    tl.to(escala, escalarPara(1.0, { duration: 0.35, ease: 'back.out(1.7)' }))
      // Hold no centro em tamanho de cartão. Sem propriedade que mude, o GSAP
      // ainda respeita a duração — é justamente o tempo de a pessoa se ver.
      .to(escala, { duration: centralPreviewDuration, ease: 'none' });
  } else {
    // Preview desligado: nada de cartão no centro. A foto entra já pequena e só
    // faz o voo até a célula — o ritmo do telão passa a ser o da fila de fotos.
    escala.set(Math.min(1, landScale * 2.5));
  }

  // 🌟 FASE 2: VOO DO CENTRO ATÉ O TILE ALVO (CAMADA 2 → CAMADA 1)
  const targetCX = targetX + targetWidth / 2;
  const targetCY = targetY + targetHeight / 2;

  // `'<'` alinha o tween ao início do anterior: posição e escala precisam
  // correr juntas, senão o voo vira dois movimentos em sequência.
  if (preset === 'spiral') {
    // 🌀 Entrada em Espiral Giratória (720°)
    tl.to(escala, escalarPara(0.8, { duration: duration * 0.4, ease: 'power2.out' }))
      .to(wrapper, { duration: duration * 0.4, rotation: Math.PI * 2, ease: 'power2.out' }, '<')
      .to(wrapper, {
        duration: duration * 0.6,
        x: targetCX,
        y: targetCY,
        rotation: Math.PI * 4,
        ease: flightEase,
      })
      .to(escala, escalarPara(landScale, { duration: duration * 0.6, ease: flightEase }), '<');
  } else if (preset === 'hsbc_cascade') {
    // 💎 Cascata HSBC (Hold Central + Deslize em Diamante)
    tl.to(escala, escalarPara(1.02, { duration: 0.3, ease: 'back.out(2)' }))
      .to(wrapper, { duration, x: targetCX, y: targetCY, ease: flightEase })
      .to(escala, escalarPara(landScale, { duration, ease: flightEase }), '<');
  } else if (preset === 'wave') {
    // 🌊 Onda Sequencial com Bounce Elástico
    tl.to(wrapper, { duration, x: targetCX, y: targetCY, ease: flightEase })
      .to(escala, escalarPara(landScale, { duration, ease: flightEase }), '<');
  } else if (preset === 'flip_3d') {
    // 🔄 Efeito Flip 3D (Rotação no Eixo Y): colapsa no caminho e reabre no tile
    tl.to(wrapper, { duration: duration * 0.5, x: targetCX, y: targetCY, ease: 'power2.in' })
      .to(escala, { duration: duration * 0.5, x: 0, ease: 'power2.in' }, '<')
      .to(escala, escalarPara(landScale, { duration: duration * 0.5, ease: flightEase }));
  } else {
    // 🚀 Padrão: Voo Parabólico (Hold Central + Planeio Suave)
    tl.to(escala, escalarPara(1.1, { duration: 0.4, ease: 'back.out(1.7)' }))
      .to(wrapper, { duration, x: targetCX, y: targetCY, ease: flightEase })
      .to(escala, escalarPara(landScale, { duration, ease: flightEase }), '<');
  }

  // Devolvida para quem precisa interromper o voo (ex.: replay do preview).
  return tl;
};

/**
 * `dispersar`: para fora da tela.
 * `retorno`: de volta ao centro, o caminho da entrada ao contrário.
 * `espalhar`: o final do vídeo de referência — cada ladrilho se solta numa
 *   direção própria, anda pouco e apaga junto, em menos de um segundo.
 */
export type OutroModo = 'dispersar' | 'retorno' | 'espalhar';

export interface MosaicOutroParams {
  landedContainer: PIXI.Container;
  screenWidth: number;
  screenHeight: number;
  duration?: number;
  ease?: string;
  modo?: OutroModo;
  /** Lado do cartão central, para o retorno terminar do mesmo tamanho da entrada. */
  cardSize?: number;
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
  modo = 'dispersar',
  cardSize = 600,
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

  const terminar = () => {
    remaining -= 1;
    if (remaining === 0) {
      landedContainer.removeChildren();
      onComplete?.();
    }
  };

  if (modo === 'espalhar') {
    /**
     * O final do vídeo de referência, medido quadro a quadro: o mosaico inteiro
     * se desfaz em ~0,75s. Os ladrilhos NÃO voam para fora da tela — cada um
     * anda pouco, numa direção própria, e apaga quase junto. Explodir tudo
     * radialmente dá um efeito de fogos que não é o que o cliente aprovou.
     */
    const duracao = Math.min(0.9, Math.max(0.5, duration * 0.55));
    tiles.forEach((tile, index) => {
      // Direção "aleatória" sem Math.random: o índice do ladrilho já espalha o
      // suficiente e o resultado é o mesmo em todo telão conectado — dois
      // telões lado a lado se desfazem igual.
      const angulo = (index * 2.39996) % (Math.PI * 2); // ângulo áureo
      const alcance = 40 + ((index * 37) % 90);
      const atraso = ((index * 13) % 100) / 100 * 0.18;

      gsap.to(tile, {
        duration: duracao,
        delay: atraso,
        x: tile.x + Math.cos(angulo) * alcance,
        y: tile.y + Math.sin(angulo) * alcance,
        rotation: (((index % 5) - 2) * 0.25),
        ease: 'power1.out',
      });
      gsap.to(tile, {
        duration: duracao * 0.7,
        delay: atraso + duracao * 0.3,
        alpha: 0,
        ease: 'power2.in',
        onComplete: terminar,
      });
    });
    return;
  }

  if (modo === 'retorno') {
    // Saída = entrada ao contrário. Cada ladrilho refaz o voo de volta ao
    // centro, cresce até o tamanho do cartão de preview e só então some. O
    // mosaico se desfaz pelo mesmo caminho por onde se formou.
    const distanciaMaxima = Math.max(
      1,
      ...tiles.map((t) => Math.hypot(t.x + (t.width || 1) / 2 - centerX, t.y + (t.height || 1) / 2 - centerY)),
    );

    tiles.forEach((tile) => {
      const limites = tile.getLocalBounds();
      const largura = limites.width || 1;
      const altura = limites.height || 1;

      // Sem pivô no centro, o ladrilho cresce para a direita e para baixo e o
      // voo chega torto no meio da tela.
      tile.pivot.set(limites.x + largura / 2, limites.y + altura / 2);
      tile.x += largura / 2;
      tile.y += altura / 2;

      const distancia = Math.hypot(tile.x - centerX, tile.y - centerY);
      // Os de fora saem primeiro: o mosaico se recolhe de fora para dentro.
      const atraso = (1 - distancia / distanciaMaxima) * 0.5;
      const alvo = Math.max(1, cardSize / largura);

      // A escala é o ObservablePoint, campos x/y — nunca a propriedade `scale`
      // do Container. Sem o PixiPlugin o GSAP troca o ponto por um número, o
      // PIXI faz copyFrom(n), lê (n).x — undefined — e o ladrilho some do nada.
      gsap.to(tile, { duration, delay: atraso, x: centerX, y: centerY, ease });
      gsap.to(tile.scale, { duration, delay: atraso, x: alvo, y: alvo, ease });
      gsap.to(tile, {
        duration: duration * 0.35,
        delay: atraso + duration * 0.65,
        alpha: 0,
        ease: 'power2.in',
        onComplete: terminar,
      });
    });
    return;
  }

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
      onComplete: terminar,
    });
  });
};

export interface MosaicReturnParams {
  landedContainer: PIXI.Container;
  duration?: number;
  onComplete?: () => void;
}

/**
 * ↩️ A volta: o mosaico se remonta inteiro depois de se desfazer.
 *
 * É o `espalhar` ao contrário. Cada ladrilho já está desenhado na célula certa
 * (quem redesenha é o efeito de camada do PixiViewport); aqui ele é jogado para
 * trás — deslocado, transparente e um pouco menor — e trazido de volta ao
 * lugar. O resultado é o mosaico se juntando no ar em vez de simplesmente
 * reaparecer num piscar.
 *
 * O deslocamento inicial usa o mesmo ângulo áureo da saída, então cada ladrilho
 * volta pelo caminho por onde saiu, e sem `Math.random` dois telões lado a lado
 * remontam idênticos.
 */
export const animateMosaicReturn = ({
  landedContainer,
  duration = 1.2,
  onComplete,
}: MosaicReturnParams) => {
  const tiles = [...landedContainer.children] as PIXI.Container[];
  if (tiles.length === 0) {
    onComplete?.();
    return;
  }

  let remaining = tiles.length;
  const terminar = () => {
    remaining -= 1;
    if (remaining === 0) onComplete?.();
  };

  tiles.forEach((tile, index) => {
    const angulo = (index * 2.39996) % (Math.PI * 2); // mesmo ângulo áureo da saída
    const alcance = 40 + ((index * 37) % 90);
    const atraso = (((index * 13) % 100) / 100) * 0.25;

    const destinoX = tile.x;
    const destinoY = tile.y;

    // Ponto de partida: onde o ladrilho estaria no fim da dispersão.
    tile.x = destinoX + Math.cos(angulo) * alcance;
    tile.y = destinoY + Math.sin(angulo) * alcance;
    tile.alpha = 0;

    gsap.to(tile, {
      duration,
      delay: atraso,
      x: destinoX,
      y: destinoY,
      rotation: 0,
      ease: 'power2.out',
    });
    gsap.to(tile, {
      duration: duration * 0.6,
      delay: atraso,
      alpha: 1,
      ease: 'power1.out',
      onComplete: terminar,
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
  // `scaleX` não existe no PIXI — animar esse nome só criava uma propriedade
  // solta no sprite e o flip não acontecia. O eixo certo é `scale.x`.
  const larguraOriginal = sprite.scale.x;

  gsap.timeline({
    onComplete: () => {
      sprite.texture = newTexture;
      gsap.to(sprite.scale, { duration: 0.3, x: larguraOriginal, ease: 'power2.out', onComplete });
    }
  }).to(sprite.scale, {
    duration: 0.3,
    x: 0,
    ease: 'power2.in'
  });
};
