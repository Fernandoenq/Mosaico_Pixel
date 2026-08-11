import React, { useEffect, useState } from 'react';
import { useMosaicStore } from '../../store/mosaicStore';
import { Monitor, Grid, FolderOpen, Image as ImageIcon, Upload, Check, Sliders, Move, Save, Trash2 } from 'lucide-react';

export const IngestionPanel: React.FC = () => {
  const {
    rows,
    cols,
    screenWidth,
    screenHeight,
    gridOffsetX,
    gridOffsetY,
    gridWidth,
    gridHeight,
    gridColor,
    gridThickness,
    gridOpacity,
    gridShape,
    gridContainerShape,
    customMaskCells,
    duplicateDistLimit,
    colorStrictness,
    fillSequence,
    photosAboveBrand,
    setPhotosAboveBrand,
    autoDuplicateToFill,
    duplicateIntervalSeconds,
    setAutoDuplicateToFill,
    setDuplicateIntervalSeconds,
    markConfigApplied,
    hotFolderDir,
    targetBaseUrl,
    setTargetBaseUrl,
    setScreenSize,
    setGridSettings,
    setGridBounds,
    setGridStyle,
    setGridShape,
    setGridContainerShape,
  } = useMosaicStore();

  const [localRows, setLocalRows] = useState(rows);
  const [localCols, setLocalCols] = useState(cols);
  const [localWidth, setLocalWidth] = useState(screenWidth);
  const [localHeight, setLocalHeight] = useState(screenHeight);
  
  const [localOffsetX, setLocalOffsetX] = useState(gridOffsetX);
  const [localOffsetY, setLocalOffsetY] = useState(gridOffsetY);
  const [localGridW, setLocalGridW] = useState(gridWidth);
  const [localGridH, setLocalGridH] = useState(gridHeight);

  const [hotFolderInput, setHotFolderInput] = useState(hotFolderDir);
  const [brandImages, setBrandImages] = useState<string[]>([]);
  const [uploadingTarget, setUploadingTarget] = useState(false);
  const [generatingPhotos, setGeneratingPhotos] = useState(false);
  
  // Video Export State
  const [exportState, setExportState] = useState<'idle' | 'exporting' | 'completed' | 'error'>('idle');
  const [exportProgress, setExportProgress] = useState(0);
  const [exportId, setExportId] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string>('');

  const [duplicando, setDuplicando] = useState(false);
  const [resultadoDuplicar, setResultadoDuplicar] = useState<{ texto: string; erro: boolean } | null>(null);
  const [intervaloDup, setIntervaloDup] = useState(duplicateIntervalSeconds);

  // O servidor manda no ritmo enquanto o laço roda; o controle local só
  // acompanha o que veio do INIT_STATE.
  useEffect(() => setIntervaloDup(duplicateIntervalSeconds), [duplicateIntervalSeconds]);

  /**
   * Preenche as células vagas duplicando fotos já aprovadas.
   *
   * O botão antes disparava e esquecia: um 400 (sem foto para duplicar) ou um
   * 500 passavam sem nenhum sinal na tela, e dava para clicar várias vezes
   * enquanto o servidor ainda preenchia.
   */
  /**
   * Liga/desliga a duplicação gradual.
   *
   * O backend é quem dita o ritmo: uma cópia a cada N segundos, cada uma com a
   * animação de foto nova. Aqui só publicamos o interruptor — e, ao desligar,
   * primeiro paramos o laço e só então mandamos limpar, senão ele repõe as
   * cópias que acabaram de sair.
   */
  const handleDuplicar = async (ligar: boolean) => {
    setDuplicando(true);
    setResultadoDuplicar(null);
    try {
      // Publica direto, sem passar pelo "Aplicar": arrastaria junto qualquer
      // rascunho ainda não publicado das outras abas.
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ autoDuplicateToFill: ligar, duplicateIntervalSeconds: intervaloDup }),
      });
      if (!res.ok) throw new Error(await res.text());
      setAutoDuplicateToFill(ligar);
      markConfigApplied();

      if (ligar) {
        setResultadoDuplicar({
          erro: false,
          texto: `Duplicando aos poucos: a próxima cópia entra ${intervaloDup}s depois de o telão terminar a anterior.`,
        });
        return;
      }

      const limpeza = await fetch('/api/mosaic/remove-duplicates', { method: 'POST' });
      const dados = await limpeza.json();
      if (!limpeza.ok) throw new Error(dados?.detail || 'Falha ao remover as cópias');
      setResultadoDuplicar({
        erro: false,
        texto:
          dados.removed_count === 0
            ? 'Não havia cópia no mosaico.'
            : `${dados.removed_count} cópia(s) removida(s). ${dados.originais} foto(s) real(is) no mosaico.`,
      });
    } catch (err) {
      setResultadoDuplicar({
        erro: true,
        texto: err instanceof Error ? err.message : 'Falha ao mudar a duplicação',
      });
    } finally {
      setDuplicando(false);
    }
  };

  /** Publica o ritmo só ao soltar o slider: a cada pixel arrastado seria um
   *  PUT, e cada PUT retransmite a config inteira para todos os telões. */
  const aplicarIntervaloDup = async () => {
    if (intervaloDup === duplicateIntervalSeconds) return;
    setDuplicateIntervalSeconds(intervaloDup);
    try {
      await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duplicateIntervalSeconds: intervaloDup }),
      });
      markConfigApplied();
    } catch {
      setResultadoDuplicar({ erro: true, texto: 'Falha ao mudar o ritmo da duplicação' });
    }
  };

  /** Preenche tudo de uma vez, sem animação de chegada. Para fechar o mosaico
   *  na hora do vídeo ou da foto oficial, quando esperar não é opção. */
  const handlePreencherAgora = async () => {
    setDuplicando(true);
    setResultadoDuplicar(null);
    try {
      const seq = useMosaicStore.getState().fillSequence;
      const res = await fetch(`/api/mosaic/auto-fill-duplicates?fill_sequence=${seq}`, { method: 'POST' });
      const dados = await res.json();
      if (!res.ok) throw new Error(dados?.detail || 'Falha ao preencher');
      setResultadoDuplicar({
        erro: false,
        texto:
          dados.placed_count === 0
            ? 'Nada a preencher — o mosaico já está completo.'
            : `${dados.placed_count} célula(s) preenchida(s).` +
              (dados.restantes ? ` ${dados.restantes} ainda vaga(s).` : ' Mosaico completo.'),
      });
    } catch (err) {
      setResultadoDuplicar({
        erro: true,
        texto: err instanceof Error ? err.message : 'Falha ao preencher o mosaico',
      });
    } finally {
      setDuplicando(false);
    }
  };

  const [coberturaGrade, setCoberturaGrade] = useState(0.05);
  const [distribuicaoGrade, setDistribuicaoGrade] = useState('aleatorio');
  const [gerandoGrade, setGerandoGrade] = useState(false);
  const [resultadoGrade, setResultadoGrade] = useState<string>('');

  /**
   * Recorta a grade no formato do logo. O backend devolve a config nova e o
   * telão já recebe por WebSocket — aqui só refletimos o resultado no painel.
   */
  const handleGradeDaMarca = async () => {
    setGerandoGrade(true);
    setResultadoGrade('');
    try {
      const res = await fetch(`/api/mosaic/grade-da-marca?cobertura=${coberturaGrade}&distribuicao=${distribuicaoGrade}`, { method: 'POST' });
      const dados = await res.json();
      if (!res.ok) throw new Error(dados?.detail || 'Falha ao encaixar a grade');
      setResultadoGrade(`${dados.celulas} células no formato do logo (de ${dados.total}).`);
      // Traz a config recém-aplicada para o painel não ficar defasado.
      const cfg = await fetch('/api/config').then((r) => r.json());
      useMosaicStore.getState().applyServerConfig(cfg.config);
      useMosaicStore.getState().markConfigApplied();
    } catch (err) {
      setResultadoGrade('');
      alert(err instanceof Error ? err.message : 'Falha ao encaixar a grade');
    } finally {
      setGerandoGrade(false);
    }
  };

  /**
   * Fotos por cima ou por baixo do logo. Publica direto: é escolha de visual
   * que se decide olhando o telão, não parte da montagem prévia.
   */
  const handleFotosAcima = async (acima: boolean) => {
    setPhotosAboveBrand(acima);
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photosAboveBrand: acima }),
      });
      if (!res.ok) throw new Error(await res.text());
      markConfigApplied();
    } catch (err) {
      setPhotosAboveBrand(!acima);
      alert(err instanceof Error ? err.message : 'Falha ao mudar a ordem das camadas');
    }
  };

  // --- Cenários do evento (telão + arte + grade + máscara, tudo junto) ---
  type Cenario = {
    id: string; rotulo: string; telao: string; grade: string;
    celulas: number; vermelhas: number; claras: number;
  };
  const [cenarios, setCenarios] = useState<Cenario[]>([]);
  const [cenarioAtual, setCenarioAtual] = useState<string | null>(null);
  const [fotosClaras, setFotosClaras] = useState<'original' | 'branco'>('original');
  const [trocandoCenario, setTrocandoCenario] = useState<string | null>(null);
  const [resultadoCenario, setResultadoCenario] = useState<string>('');

  useEffect(() => {
    fetch('/api/cenarios')
      .then((r) => r.json())
      .then((d) => {
        setCenarios(d.cenarios || []);
        setCenarioAtual(d.atual ?? null);
      })
      .catch(() => setResultadoCenario('Não consegui listar os cenários.'));
  }, []);

  /**
   * Troca o cenário inteiro: resolução, arte, grade, recorte no logo e a
   * pintura das células. Tudo vem pronto do backend — os valores foram
   * calculados em cima da arte do cliente e conferidos uma vez.
   */
  const handleCenario = async (id: string, claras: 'original' | 'branco') => {
    setTrocandoCenario(id);
    setResultadoCenario('');
    try {
      const res = await fetch(`/api/cenarios/${id}/aplicar?fotosClaras=${claras}`, { method: 'POST' });
      const dados = await res.json();
      if (!res.ok) throw new Error(dados?.detail || 'Falha ao aplicar o cenário');
      setCenarioAtual(id);
      setFotosClaras(claras);
      setResultadoCenario(
        `${dados.telao} · grade ${dados.grade} · ${dados.celulas} células` +
        (dados.liberados ? ` · ${dados.liberados} ladrilho(s) fora do novo desenho foram liberados` : ''),
      );
      const cfg = await fetch('/api/config').then((r) => r.json());
      useMosaicStore.getState().applyServerConfig(cfg.config);
      useMosaicStore.getState().markConfigApplied();
    } catch (err) {
      setResultadoCenario(err instanceof Error ? err.message : 'Falha ao aplicar o cenário');
    } finally {
      setTrocandoCenario(null);
    }
  };

  const [publicandoOrdem, setPublicandoOrdem] = useState(false);

  /**
   * Troca a ordem de preenchimento e publica na hora.
   *
   * O `select` daqui só mexia no store e esperava o "Aplicar" — e ainda lia o
   * valor por `getState()`, fora do hook, então nem refletia mudança vinda do
   * servidor. Trocar o desenho do mosaico é decisão de operação, tem que valer
   * no clique.
   */
  const handleOrdemRapida = async (seq: string) => {
    setPublicandoOrdem(true);
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fillSequence: seq }),
      });
      if (!res.ok) throw new Error(await res.text());
      useMosaicStore.getState().setFillSequence(seq as any);
      useMosaicStore.getState().markConfigApplied();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Falha ao mudar a ordem de preenchimento');
    } finally {
      setPublicandoOrdem(false);
    }
  };

  const [limpando, setLimpando] = useState(false);
  const [confirmandoLimpeza, setConfirmandoLimpeza] = useState(false);
  const [limparBucket, setLimparBucket] = useState(false);
  const [resultadoLimpeza, setResultadoLimpeza] = useState<{ texto: string; erro: boolean } | null>(null);

  /**
   * Limpeza geral entre um evento e outro.
   *
   * Exige dois cliques: o primeiro arma, o segundo executa. É a única ação do
   * painel que apaga foto de verdade — um clique errado no meio do evento não
   * tem volta, e a barra fica ao alcance do mouse o tempo todo.
   */
  const handleLimpezaGeral = async () => {
    if (!confirmandoLimpeza) {
      setConfirmandoLimpeza(true);
      window.setTimeout(() => setConfirmandoLimpeza(false), 5000);
      return;
    }
    setConfirmandoLimpeza(false);
    setLimpando(true);
    setResultadoLimpeza(null);
    try {
      const res = await fetch(`/api/admin/limpeza-geral?bucket=${limparBucket}&galeria=true`, { method: 'POST' });
      const dados = await res.json();
      if (!res.ok) throw new Error(dados?.detail || 'Falha na limpeza');
      const d = dados.disco || {};
      const partes = Object.entries(d).map(
        ([nome, v]: [string, any]) => `${nome}: ${v.arquivos} (${v.mb} MB)`,
      );
      if (limparBucket) {
        partes.push(
          dados.bucket?.ok
            ? `bucket: ${dados.bucket.apagados} objetos`
            : `bucket: FALHOU — ${dados.bucket?.detalhe || dados.bucket?.falhas?.join(', ')}`,
        );
      }
      const aviso =
        dados.run_state && dados.run_state !== 'running'
          ? ' O show voltou para PAUSADO — dê Play antes de soltar as fotos.'
          : '';
      setResultadoLimpeza({ erro: false, texto: `Limpo — ${partes.join(' · ')}.${aviso}` });
      useMosaicStore.getState().clearMosaic();
      if (dados.run_state) useMosaicStore.getState().setRunState(dados.run_state);
    } catch (err) {
      setResultadoLimpeza({ erro: true, texto: err instanceof Error ? err.message : 'Falha na limpeza' });
    } finally {
      setLimpando(false);
    }
  };

  /**
   * Abre o miolo da marca (ou devolve a arte como veio do cliente).
   *
   * As duas ações mexem no MESMO arquivo de overlay e na máscara, então
   * compartilham o estado de "ocupado" e a mesma linha de resultado.
   */
  const handleMiolo = async (abrir: boolean) => {
    setGerandoGrade(true);
    setResultadoGrade('');
    try {
      const rota = abrir ? '/api/mosaic/abrir-miolo-da-marca' : '/api/mosaic/restaurar-marca-original';
      const res = await fetch(rota, { method: 'POST' });
      const dados = await res.json();
      if (!res.ok) throw new Error(dados?.detail || 'Falha ao mudar o miolo da marca');
      setResultadoGrade(
        abrir
          ? dados.novas === 0
            ? 'O miolo já estava aberto.'
            : `${dados.novas} célula(s) abertas no miolo, na cor original. Máscara com ${dados.mascara}.`
          : dados.detalhe || 'Arte restaurada.',
      );
      const cfg = await fetch('/api/config').then((r) => r.json());
      useMosaicStore.getState().applyServerConfig(cfg.config);
      useMosaicStore.getState().markConfigApplied();
    } catch (err) {
      setResultadoGrade('');
      alert(err instanceof Error ? err.message : 'Falha ao mudar o miolo da marca');
    } finally {
      setGerandoGrade(false);
    }
  };

  // Ajustes do vídeo no modelo da marca. Os defaults são os valores aprovados
  // pelo cliente — mexer aqui só muda a exportação, nunca o telão ao vivo.
  const RESOLUCOES = [
    { rotulo: 'Rápida — 1152×688', largura: 1152, altura: 688 },
    { rotulo: 'Cheia — 1920×1147', largura: 1920, altura: 1147 },
    { rotulo: 'Telão — 2304×1377', largura: 2304, altura: 1377 },
  ];
  const [videoRes, setVideoRes] = useState(0);
  const [videoFps, setVideoFps] = useState(30);
  const [videoIntervalo, setVideoIntervalo] = useState(0.12);
  const [videoHold, setVideoHold] = useState(0.5);
  const [videoVoo, setVideoVoo] = useState(0.6);
  const [videoCor, setVideoCor] = useState('#e21c1c');
  const [videoOpcoesAbertas, setVideoOpcoesAbertas] = useState(false);
  const [videoFotos, setVideoFotos] = useState<number | null>(null);

  // Quantas fotos já existem — serve para estimar a duração antes de gerar.
  useEffect(() => {
    fetch('/api/export/video-marca/info')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setVideoFotos(d.celulas ?? null))
      .catch(() => {});
  }, []);

  const duracaoEstimada = videoFotos
    ? (videoFotos * videoIntervalo + videoHold + videoVoo + 3).toFixed(0)
    : null;

  /**
   * Espelha no painel o que veio do store.
   *
   * Os campos são estado local (rascunho antes de publicar), inicializado uma
   * única vez no mount. Quando a config chega pronta de outro caminho — o
   * "Encaixar Grade no Logo", uma carga inicial — os campos ficavam mostrando
   * os valores antigos e pareciam travados.
   */
  useEffect(() => {
    setLocalOffsetX(gridOffsetX);
    setLocalOffsetY(gridOffsetY);
    setLocalGridW(gridWidth);
    setLocalGridH(gridHeight);
  }, [gridOffsetX, gridOffsetY, gridWidth, gridHeight]);

  useEffect(() => {
    setLocalRows(rows);
    setLocalCols(cols);
  }, [rows, cols]);

  useEffect(() => {
    setLocalWidth(screenWidth);
    setLocalHeight(screenHeight);
  }, [screenWidth, screenHeight]);

  const handleGalleryTestPhotos = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;
    setGeneratingPhotos(true);
    const files = Array.from(e.target.files).slice(0, 5); // Limit to 5 photos as requested
    
    for (let i = 0; i < files.length; i++) {
      const formData = new FormData();
      formData.append('file', files[i]);
      try {
        await fetch('/api/ingest/upload', { method: 'POST', body: formData });
      } catch (e) {
        console.error(e);
      }
    }
    setGeneratingPhotos(false);
    // Clear input
    e.target.value = '';
  };

  const handleSelectFolder = async () => {
    try {
      const res = await fetch('/api/system/select-folder');
      const data = await res.json();
      if (data.path) {
        setHotFolderInput(data.path);
        // Atualiza a config no backend, o que vai recriar o watcher
        await fetch('/api/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ hotFolderDir: data.path })
        });
      }
    } catch (err) {
      console.error('Erro ao selecionar pasta:', err);
    }
  };

  /** Reflete no painel o enquadramento que o store reescalou. */
  const syncLocalBoundsFromStore = () => {
    const s = useMosaicStore.getState();
    setLocalOffsetX(s.gridOffsetX);
    setLocalOffsetY(s.gridOffsetY);
    setLocalGridW(s.gridWidth);
    setLocalGridH(s.gridHeight);
  };

  const handleApplyScreenSize = (w: number, h: number) => {
    setLocalWidth(w);
    setLocalHeight(h);
    setScreenSize(w, h);
    syncLocalBoundsFromStore();
  };

  /**
   * Comita a resolução só ao sair do campo ou no Enter. Aplicar a cada tecla
   * recriaria o palco PixiJS a cada dígito ("3", "38", "384", "3840").
   */
  const commitScreenSize = () => {
    const w = Math.min(16384, Math.max(320, localWidth || screenWidth));
    const h = Math.min(16384, Math.max(240, localHeight || screenHeight));
    setLocalWidth(w);
    setLocalHeight(h);
    if (w !== screenWidth || h !== screenHeight) {
      setScreenSize(w, h);
      syncLocalBoundsFromStore();
    }
  };

  const handlePresetChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (val === '1920x1080') handleApplyScreenSize(1920, 1080);
    else if (val === '3840x2160') handleApplyScreenSize(3840, 2160);
    else if (val === '1080x1920') handleApplyScreenSize(1080, 1920);
    else if (val === '3840x1080') handleApplyScreenSize(3840, 1080);
  };

  // Só rascunho local — quem publica no telão é o "Aplicar" da barra superior.
  const handleApplyGrid = () => {
    setGridSettings(localRows, localCols, duplicateDistLimit, colorStrictness);
  };

  const handleGridPreset = (rows: number, cols: number) => {
    setLocalRows(rows);
    setLocalCols(cols);
    setGridSettings(rows, cols, duplicateDistLimit, colorStrictness);
  };

  const handleApplyBounds = (ox: number, oy: number, gw: number, gh: number) => {
    setLocalOffsetX(ox);
    setLocalOffsetY(oy);
    setLocalGridW(gw);
    setLocalGridH(gh);
    setGridBounds(ox, oy, gw, gh);
  };

  const handleTargetBaseUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;
    setUploadingTarget(true);
    const formData = new FormData();
    formData.append('file', e.target.files[0]);
    try {
      const res = await fetch('/api/ingest/target-base', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (data.url) {
        setTargetBaseUrl(data.url);
      }
    } catch (err) {
      console.error('Target Base Upload Error:', err);
    } finally {
      setUploadingTarget(false);
    }
  };

  const handleBrandUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;
    const formData = new FormData();
    formData.append('file', e.target.files[0]);
    const res = await fetch('/api/ingest/brand-fallback', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (data.item) {
      setBrandImages((prev) => [...prev, data.item.url]);
    }
  };

  const handleExportVideo = async (endpoint = '/api/export/video', opcoes?: Record<string, unknown>) => {
    try {
      setExportState('exporting');
      setExportProgress(0);
      setExportError('');

      const res = await fetch(endpoint, {
        method: 'POST',
        ...(opcoes
          ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opcoes) }
          : {}),
      });
      if (!res.ok) {
        // O backend explica o que falta (overlay ausente, sem fotos...).
        const detalhe = await res.json().catch(() => null);
        throw new Error(detalhe?.detail || 'Falha ao iniciar exportação');
      }

      const data = await res.json();
      const id = data.export_id;
      setExportId(id);
      
      const interval = setInterval(async () => {
        try {
          const statusRes = await fetch(`/api/export/video/status/${id}`);
          if (statusRes.ok) {
            const statusData = await statusRes.json();
            // O backend responde 'done'; aceitar só 'completed' deixava a barra
            // travada em 99% com o vídeo já pronto no disco.
            if (statusData.status === 'done' || statusData.status === 'completed') {
              setExportState('completed');
              setExportProgress(100);
              clearInterval(interval);
            } else if (statusData.status === 'error') {
              setExportState('error');
              setExportError(statusData.error || 'Erro desconhecido');
              clearInterval(interval);
            } else {
              setExportProgress(statusData.progress || 0);
            }
          }
        } catch (e) {
          // Keep polling unless severe error
        }
      }, 2000);
    } catch (e: any) {
      setExportState('error');
      setExportError(e.message);
    }
  };

  return (
    <div className="flex flex-col gap-5 p-4 bg-slate-900 border-r border-slate-800 text-slate-100 w-80 h-full max-h-full overflow-y-auto pr-2 font-sans">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2 text-cyan-400">
          <Monitor className="w-5 h-5" />
          <h3 className="font-bold text-sm uppercase tracking-wider">Display & Ingestão</h3>
        </div>
      </div>

      {/* Onde as configurações efetivamente são publicadas */}
      <div className="flex items-start gap-2 bg-slate-800/60 border border-slate-700/60 rounded-lg p-2.5">
        <Save className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
        <p className="text-[10px] text-slate-400 leading-snug">
          As mudanças desta aba são um rascunho. Use{' '}
          <span className="font-bold text-cyan-300">Aplicar no Telão</span> na barra superior para publicá-las
          e salvá-las no servidor.
        </p>
      </div>

      {/* 0. Cenário do evento — primeiro card da coluna porque troca TUDO:
             resolução do telão, arte, grade, recorte no logo e pintura. Aplica
             direto, sem passar pelo "Aplicar". */}
      <div className="flex flex-col gap-2.5 bg-slate-800/80 p-3 rounded-lg border border-cyan-800/60 shadow-md">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
          <Monitor className="w-4 h-4 text-cyan-400" />
          <span>Cenário do Evento</span>
        </div>

        <p className="text-[10px] text-slate-400 leading-snug">
          Cada cenário é um telão + a arte do cliente + a grade já encaixada no
          logo. Um clique troca tudo junto.
        </p>

        {cenarios.length === 0 && (
          <span className="text-[10px] text-amber-400/90">
            Nenhum cenário preparado. Rode <code>python tools/preparar_cenarios.py</code> com
            as artes em <code>fundos/</code>.
          </span>
        )}

        <div className="flex flex-col gap-1.5">
          {cenarios.map((cen) => (
            <button
              key={cen.id}
              onClick={() => handleCenario(cen.id, fotosClaras)}
              disabled={trocandoCenario !== null}
              className={`text-left px-2.5 py-2 rounded-lg border transition active:scale-95 disabled:opacity-50 ${
                cenarioAtual === cen.id
                  ? 'bg-cyan-600/20 border-cyan-400/50'
                  : 'bg-slate-900 border-slate-700 hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-slate-100">{cen.telao}</span>
                <span className="text-[9px] text-slate-500">grade {cen.grade}</span>
              </div>
              <div className="text-[9px] text-slate-400 leading-snug">
                {trocandoCenario === cen.id
                  ? 'aplicando...'
                  : `${cen.celulas} células — ${cen.vermelhas} no vermelho, ${cen.claras} no branco`}
              </div>
            </button>
          ))}
        </div>

        {/* O que acontece nas células do BRANCO do logo. */}
        <div className="flex flex-col gap-1">
          <span className="text-[10px] text-slate-400">Fotos na parte branca do logo</span>
          <div className="flex gap-1.5">
            {([
              { valor: 'original', rotulo: 'Cor original' },
              { valor: 'branco', rotulo: 'Filtro branco' },
            ] as const).map((op) => (
              <button
                key={op.valor}
                onClick={() => cenarioAtual && handleCenario(cenarioAtual, op.valor)}
                disabled={trocandoCenario !== null || !cenarioAtual}
                className={`flex-1 text-[10px] font-bold py-1.5 rounded-lg border transition active:scale-95 disabled:opacity-40 ${
                  fotosClaras === op.valor
                    ? 'bg-cyan-600 text-white border-cyan-400/50'
                    : 'bg-slate-900 text-slate-400 border-slate-700 hover:bg-slate-800'
                }`}
              >
                {op.rotulo}
              </button>
            ))}
          </div>
        </div>

        {resultadoCenario && (
          <span className="text-[10px] text-emerald-400 leading-snug">{resultadoCenario}</span>
        )}
      </div>

      {/* 1. Target Base Image (Imagem de Fundo do Mosaico) */}
      <div className="flex flex-col gap-2 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
            <Upload className="w-4 h-4 text-cyan-400" />
            <span>Imagem de Fundo do Mosaico</span>
          </div>
          {targetBaseUrl && (
            <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded flex items-center gap-1">
              <Check className="w-3 h-3" /> Ativa
            </span>
          )}
        </div>

        {targetBaseUrl ? (
          <div className="relative group overflow-hidden rounded border border-slate-700">
            <img src={targetBaseUrl} alt="Target Base" className="w-full h-24 object-cover" />
            <label className="absolute inset-0 bg-slate-950/80 opacity-0 group-hover:opacity-100 transition flex items-center justify-center cursor-pointer text-xs font-semibold text-cyan-300">
              Trocar Imagem de Fundo
              <input type="file" accept="image/*" onChange={handleTargetBaseUpload} className="hidden" />
            </label>
          </div>
        ) : (
          <label className="cursor-pointer bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 text-xs text-center py-4 rounded-lg transition border border-dashed border-cyan-500/50 flex flex-col items-center gap-1.5 shadow-inner">
            <Upload className="w-5 h-5 text-cyan-400" />
            <span>{uploadingTarget ? 'Enviando Imagem...' : '+ Carregar Fundo do Mosaico'}</span>
            <span className="text-[10px] text-slate-400">JPG/PNG alta resolução</span>
            <input type="file" accept="image/*" onChange={handleTargetBaseUpload} className="hidden" />
          </label>
        )}
      </div>

      {/* 2. Dimensões de Telões (Simulador de Telões) */}
      <div className="flex flex-col gap-2 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Monitor className="w-4 h-4 text-cyan-400" />
          <span>Simulação de Telões</span>
        </div>
        
        <select
          onChange={handlePresetChange}
          className="bg-slate-900 border border-slate-700 rounded p-1.5 text-xs text-slate-200"
        >
          <option value="1920x1080">Full HD (1920x1080) - 16:9</option>
          <option value="3840x2160">4K UHD (3840x2160) - 16:9</option>
          <option value="1080x1920">Vertical LED (1080x1920) - 9:16</option>
          <option value="3840x1080">Painel Ultra-Wide (3840x1080)</option>
        </select>

        <div className="grid grid-cols-2 gap-2 mt-1">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-slate-400">Largura (px)</span>
            <input
              type="number"
              value={localWidth}
              onChange={(e) => setLocalWidth(parseInt(e.target.value) || 0)}
              onBlur={() => commitScreenSize()}
              onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
              className="bg-slate-900 border border-slate-700 rounded p-1 text-xs font-mono text-cyan-300 text-center"
            />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-slate-400">Altura (px)</span>
            <input
              type="number"
              value={localHeight}
              onChange={(e) => setLocalHeight(parseInt(e.target.value) || 0)}
              onBlur={() => commitScreenSize()}
              onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
              className="bg-slate-900 border border-slate-700 rounded p-1 text-xs font-mono text-cyan-300 text-center"
            />
          </div>
        </div>

        <div className="flex items-center justify-between text-[10px] pt-0.5">
          <span className="text-slate-500">Ativo no telão</span>
          <span className={`font-mono ${screenWidth === localWidth && screenHeight === localHeight ? 'text-slate-400' : 'text-amber-400'}`}>
            {screenWidth}×{screenHeight}
          </span>
        </div>
      </div>

      {/* 3. Posicionamento e Dimensionamento da Grade no Fundo */}
      <div className="flex flex-col gap-3 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Move className="w-4 h-4 text-cyan-400" />
          <span>Dimensionar / Mover Grade</span>
        </div>

        {/* Posição e tamanho da área do mosaico.
            Os limites acompanham o telão mas vão além dele: a grade pode
            legitimamente extrapolar a tela (sangria) e usar offset negativo,
            que é o caso quando ela é alinhada a uma arte. Com os limites presos
            em 0..telão, o slider travava no fim e o valor não voltava mais. */}
        {([
          ['Offset X (Posição H)', localOffsetX, -localWidth, localWidth,
            (v: number) => handleApplyBounds(v, localOffsetY, localGridW, localGridH)],
          ['Offset Y (Posição V)', localOffsetY, -localHeight, localHeight,
            (v: number) => handleApplyBounds(localOffsetX, v, localGridW, localGridH)],
          ['Largura da Grade', localGridW, 100, localWidth * 2,
            (v: number) => handleApplyBounds(localOffsetX, localOffsetY, v, localGridH)],
          ['Altura da Grade', localGridH, 100, localHeight * 2,
            (v: number) => handleApplyBounds(localOffsetX, localOffsetY, localGridW, v)],
        ] as const).map(([rotulo, valor, min, max, aplicar]) => (
          <div key={rotulo} className="flex flex-col gap-1">
            <div className="flex justify-between items-center text-xs text-slate-400">
              <span>{rotulo}</span>
              <div className="flex items-center gap-1">
                {/* Campo numérico: para valor exato o slider não serve. */}
                <input
                  type="number"
                  value={valor}
                  onChange={(e) => {
                    const n = parseInt(e.target.value, 10);
                    if (!Number.isNaN(n)) aplicar(n);
                  }}
                  className="w-20 bg-slate-900 border border-slate-700 rounded px-1 py-0.5 text-[11px] font-mono text-cyan-300 text-right"
                />
                <span className="text-[10px] text-slate-500">px</span>
              </div>
            </div>
            <input
              type="range"
              min={min}
              max={max}
              value={Math.min(max, Math.max(min, valor))}
              onChange={(e) => aplicar(parseInt(e.target.value, 10))}
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
            />
          </div>
        ))}
      </div>

      {/* 4. Estilo Visual das Linhas da Grade */}
      <div className="flex flex-col gap-3 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <Sliders className="w-4 h-4 text-cyan-400" />
          <span>Estilo Visual da Grade</span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">Cor das Linhas</span>
          <div className="flex gap-1.5">
            {['#00ffff', '#ffffff', '#ffea00', '#ff0055', '#00ff66'].map((c) => (
              <button
                key={c}
                onClick={() => setGridStyle(c, gridThickness, gridOpacity)}
                style={{ backgroundColor: c }}
                className={`w-5 h-5 rounded-full border border-slate-600 transition ${
                  gridColor === c ? 'scale-125 ring-2 ring-cyan-400' : 'hover:scale-110'
                }`}
              />
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Espessura das Linhas</span>
            <span className="font-mono text-cyan-300">{gridThickness}px</span>
          </div>
          <input
            type="range"
            min="1"
            max="6"
            value={gridThickness}
            onChange={(e) => setGridStyle(gridColor, parseInt(e.target.value), gridOpacity)}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Opacidade da Grade</span>
            <span className="font-mono text-cyan-300">{Math.round(gridOpacity * 100)}%</span>
          </div>
          <input
            type="range"
            min="0.1"
            max="1.0"
            step="0.05"
            value={gridOpacity}
            onChange={(e) => setGridStyle(gridColor, gridThickness, parseFloat(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>
      </div>

      {/* 5. Forma Geométrica da Grade (Losangos / Quadrados / Hexágonos / Círculos) */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
          <Grid className="w-4 h-4 text-cyan-400" />
          <span>Forma Geométrica da Grade</span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => setGridShape('diamond')}
            className={`flex flex-col items-center justify-center p-2.5 rounded-lg border transition gap-1 ${
              gridShape === 'diamond'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base font-bold">💎</span>
            <span className="text-[11px] font-semibold">Losango 45°</span>
            <span className="text-[9px] text-slate-400">Padrão HSBC</span>
          </button>

          <button
            onClick={() => setGridShape('square')}
            className={`flex flex-col items-center justify-center p-2.5 rounded-lg border transition gap-1 ${
              gridShape === 'square'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base font-bold">🔲</span>
            <span className="text-[11px] font-semibold">Quadrados</span>
            <span className="text-[9px] text-slate-400">Ortogonal</span>
          </button>

          <button
            onClick={() => setGridShape('hexagon')}
            className={`flex flex-col items-center justify-center p-2.5 rounded-lg border transition gap-1 ${
              gridShape === 'hexagon'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base font-bold">⬡</span>
            <span className="text-[11px] font-semibold">Hexagonal</span>
            <span className="text-[9px] text-slate-400">Colmeia</span>
          </button>

          <button
            onClick={() => setGridShape('circle')}
            className={`flex flex-col items-center justify-center p-2.5 rounded-lg border transition gap-1 ${
              gridShape === 'circle'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base font-bold">⚪</span>
            <span className="text-[11px] font-semibold">Círculos</span>
            <span className="text-[9px] text-slate-400">Dots / Pontos</span>
          </button>

          {/* Ocupa a linha inteira porque não é irmão dos outros quatro: eles
              mudam o formato do ladrilho, este recorta a REGIÃO no desenho da
              marca. Fica aqui porque é onde se procura "a forma do logo". */}
          <button
            onClick={handleGradeDaMarca}
            disabled={gerandoGrade}
            className={`col-span-2 flex flex-col items-center justify-center p-2.5 rounded-lg border transition gap-1 ${
              gridContainerShape === 'custom_mask'
                ? 'bg-red-500/20 border-red-400 text-red-200 ring-2 ring-red-500/30'
                : 'bg-slate-900/60 border-red-900/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            } disabled:opacity-50`}
          >
            <span className="text-base font-bold">◆</span>
            <span className="text-[11px] font-semibold">
              {gerandoGrade ? 'Calculando...' : 'Formato do Logo'}
            </span>
            <span className="text-[9px] text-slate-400">
              {gridContainerShape === 'custom_mask'
                ? `${customMaskCells.length} células no desenho da marca`
                : 'Recorta a região pelo overlay da Camada 4'}
            </span>
          </button>
        </div>

        <label className="flex items-center justify-between text-[10px] text-slate-400">
          <span>Detalhe do logo</span>
          <select
            value={coberturaGrade}
            onChange={(e) => setCoberturaGrade(parseFloat(e.target.value))}
            className="bg-slate-900 border border-slate-700 rounded p-1 text-[10px] text-slate-200"
          >
            <option value={0.05}>Completo (com os pontinhos)</option>
            <option value={0.15}>Equilibrado</option>
            <option value={0.3}>Só os losangos cheios</option>
          </select>
        </label>

        {/* Define a ORDEM gravada na máscara, que a sequência "Desenho da Marca"
            segue. É o que decide se o logo cresce por região ou por inteiro. */}
        <label className="flex items-center justify-between text-[10px] text-slate-400">
          <span>Como o logo enche</span>
          <select
            value={distribuicaoGrade}
            onChange={(e) => setDistribuicaoGrade(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded p-1 text-[10px] text-slate-200"
          >
            <option value="aleatorio">Aleatório (espalha sem padrão)</option>
            <option value="espalhado">Espalhado (rodízio por região)</option>
            <option value="visibilidade">Por visibilidade (do lado mais denso)</option>
          </select>
        </label>

        {/* Ordem das camadas entre mosaico e marca. */}
        <label className="flex items-center gap-2 text-[10px] text-slate-300 cursor-pointer bg-slate-900/60 px-2 py-1.5 rounded-lg border border-slate-700">
          <input
            type="checkbox"
            checked={photosAboveBrand}
            onChange={(e) => handleFotosAcima(e.target.checked)}
            className="w-3.5 h-3.5 accent-cyan-500 cursor-pointer"
          />
          <span>
            Fotos <strong className="text-slate-100">por cima</strong> do logo
            <span className="text-slate-500"> — o mosaico cobre a marca conforme enche</span>
          </span>
        </label>

        {/* O miolo da arte é chapa preta e nenhuma foto aparece ali. Aqui a
            malha de losangos é estendida para dentro dele. */}
        <div className="flex gap-1.5">
          <button
            onClick={() => handleMiolo(true)}
            disabled={gerandoGrade}
            title="Recorta losangos no miolo preto da marca e libera essas células. As fotos do miolo ficam na cor original."
            className="flex-1 bg-slate-700/70 hover:bg-slate-600/70 disabled:bg-slate-800 disabled:text-slate-600 text-slate-200 font-semibold text-[10px] py-1.5 rounded-lg transition border border-slate-600 active:scale-95"
          >
            ◇ Abrir o miolo (cor original)
          </button>
          <button
            onClick={() => handleMiolo(false)}
            disabled={gerandoGrade}
            title="Volta a arte como o cliente entregou. Depois reencaixe em Formato do Logo."
            className="bg-slate-800 hover:bg-slate-700 disabled:text-slate-600 text-slate-400 text-[10px] px-2 py-1.5 rounded-lg transition border border-slate-700 active:scale-95"
          >
            Desfazer
          </button>
        </div>

        {resultadoGrade && <span className="text-[10px] text-emerald-400">{resultadoGrade}</span>}

        <span className="text-[10px] text-slate-500 leading-snug">
          As quatro primeiras mudam o formato de cada ladrilho. "Formato do Logo"
          é diferente: recorta a <strong>região</strong> do mosaico no desenho da
          marca, usando o overlay da Camada 4. Ajuste a grade e a área antes — o
          recorte é calculado em cima delas.
        </span>
      </div>

      {/* 6. Contorno / Máscara da Área do Mosaico (Bounding Mask Container) */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
          <Move className="w-4 h-4 text-cyan-400" />
          <span>Contorno da Região do Mosaico</span>
        </div>

        <div className="flex flex-col gap-2">
          <button
            onClick={() => setGridContainerShape('diamond_mask')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'diamond_mask'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">🔷</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Máscara Losango (HSBC Shape)</span>
              <span className="text-[10px] text-slate-400">Contorno no formato de diamante</span>
            </div>
          </button>

          <button
            onClick={() => setGridContainerShape('hexagon_halftone')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'hexagon_halftone'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">✨</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Gradiente Meio-Tom Hexagonal</span>
              <span className="text-[10px] text-slate-400">Pontos grandes nas pontas, pequenos no centro</span>
            </div>
          </button>

          <button
            onClick={() => setGridContainerShape('hexagon_mask')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'hexagon_mask'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">⬡</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Máscara Hexagonal</span>
              <span className="text-[10px] text-slate-400">Contorno no formato de hexágono</span>
            </div>
          </button>

          <button
            onClick={() => setGridContainerShape('circle_mask')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'circle_mask'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">⚪</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Máscara Circular / Elipse</span>
              <span className="text-[10px] text-slate-400">Contorno em formato circular</span>
            </div>
          </button>

          <button
            onClick={() => setGridContainerShape('rectangle')}
            className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-left transition ${
              gridContainerShape === 'rectangle'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span className="text-base">🔲</span>
            <div className="flex flex-col">
              <span className="text-xs font-bold">Retângulo Completo</span>
              <span className="text-[10px] text-slate-400">Caixa delimitadora padrão</span>
            </div>
          </button>
        </div>
      </div>

      {/* 5. Tamanho dos Quadrados & Matriz de Ladrilhos */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
          <Grid className="w-4 h-4 text-cyan-400" />
          <span>Tamanho dos Quadrados & Resolução</span>
        </div>

        {/* Presets Rápidos de Tamanho de Quadrado */}
        <div className="grid grid-cols-3 gap-1.5">
          <button
            onClick={() => handleGridPreset(15, 20)}
            className={`flex flex-col items-center p-2 rounded border text-center transition ${
              localRows === 15 && localCols === 20
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            <span className="text-sm font-bold">🔲</span>
            <span className="text-[11px] font-bold">Grandes</span>
            <span className="text-[9px] text-slate-400">15 × 20</span>
          </button>

          <button
            onClick={() => handleGridPreset(30, 40)}
            className={`flex flex-col items-center p-2 rounded border text-center transition ${
              localRows === 30 && localCols === 40
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            <span className="text-sm font-bold">⬛</span>
            <span className="text-[11px] font-bold">Médios</span>
            <span className="text-[9px] text-slate-400">30 × 40</span>
          </button>

          <button
            onClick={() => handleGridPreset(60, 80)}
            className={`flex flex-col items-center p-2 rounded border text-center transition ${
              localRows === 60 && localCols === 80
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 ring-2 ring-cyan-500/30'
                : 'bg-slate-900/60 border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            <span className="text-sm font-bold">▫️</span>
            <span className="text-[11px] font-bold">Pequenos</span>
            <span className="text-[9px] text-slate-400">60 × 80</span>
          </button>
        </div>
        
        <div className="flex flex-col gap-1 mt-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Linhas (Rows)</span>
            <span className="font-mono text-cyan-300">{localRows}</span>
          </div>
          <input
            type="range"
            min="10"
            max="100"
            value={localRows}
            onChange={(e) => setLocalRows(parseInt(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Colunas (Cols)</span>
            <span className="font-mono text-cyan-300">{localCols}</span>
          </div>
          <input
            type="range"
            min="10"
            max="100"
            value={localCols}
            onChange={(e) => setLocalCols(parseInt(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
          />
        </div>

        <button
          onClick={handleApplyGrid}
          className="mt-1 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold py-1.5 rounded transition shadow-sm"
        >
          Aplicar Linhas/Colunas Personalizadas
        </button>
      </div>

      {/* 6. Ordem de Preenchimento do Mosaico (Sequência de Início) */}
      <div className="flex flex-col gap-2.5 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300">
          <Sliders className="w-4 h-4 text-cyan-400" />
          <span>Ordem de Preenchimento do Mosaico</span>
        </div>

        {/* Atalho das duas ordens que se usa no evento. Publica direto, sem
            passar pelo "Aplicar": trocar o desenho no meio do show não pode
            arrastar junto o rascunho das outras abas. */}
        <div className="flex gap-1.5">
          {([
            { valor: 'top_to_bottom', rotulo: '⬇ Linha a linha' },
            { valor: 'random', rotulo: '🎲 Aleatório' },
          ] as const).map((opcao) => (
            <button
              key={opcao.valor}
              onClick={() => handleOrdemRapida(opcao.valor)}
              disabled={publicandoOrdem}
              className={`flex-1 text-[11px] font-bold py-1.5 rounded-lg border transition active:scale-95 disabled:opacity-50 ${
                fillSequence === opcao.valor
                  ? 'bg-cyan-600 text-white border-cyan-400/50'
                  : 'bg-slate-900 text-slate-400 border-slate-700 hover:bg-slate-800'
              }`}
            >
              {opcao.rotulo}
            </button>
          ))}
        </div>

        <select
          value={fillSequence}
          onChange={(e) => handleOrdemRapida(e.target.value as any)}
          disabled={publicandoOrdem}
          className="bg-slate-900 border border-slate-700 rounded p-2 text-xs text-slate-200"
        >
          <option value="brand_first">◆ Desenho da Marca (mais visível primeiro)</option>
          <option value="color_match">🎨 Melhor Combinação de Cores (LAB Perceptual)</option>
          <option value="top_to_bottom">⬇️ Cima para Baixo (Linha por Linha)</option>
          <option value="bottom_to_top">⬆️ Baixo para Cima</option>
          <option value="center_out">🎯 Do Centro para as Bordas (Espiral)</option>
          <option value="random">🎲 Aleatório (Random)</option>
        </select>
        <span className="text-[10px] text-slate-500 leading-snug">
          "Linha a linha" desenha o mosaico de cima para baixo, com o logo sempre
          por cima. "Desenho da Marca" usa o recorte do logo: as primeiras fotos
          vão para os losangos cheios, onde aparecem inteiras, e o halftone das
          pontas fica para o fim — precisa do contorno em "Formato do Logo".
        </span>
      </div>

      {/* 7. Duplicar Fotos para Fechar o Mosaico */}
      <div className="flex flex-col gap-2.5 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md">
        <div className="flex items-center justify-between text-xs font-bold text-emerald-300">
          <div className="flex items-center gap-1.5">
            <ImageIcon className="w-4 h-4 text-emerald-400" />
            <span>Completar Mosaico (Duplicar Fotos)</span>
          </div>
        </div>

        <p className="text-[10px] text-slate-400 leading-snug">
          Ligado, as fotos que já estão no mosaico vão sendo copiadas aos poucos,
          em rodízio: cada cópia entra com a mesma animação de uma foto nova, até
          fechar a grade. Quem chegar no meio do evento entra no rodízio na hora.
          Desligado, as cópias somem e ficam só as fotos reais.
        </p>

        {/* Interruptor, não gatilho: ligar preenche, desligar desfaz. Sem o
            caminho de volta, a única forma de tirar as cópias era resetar o
            mosaico inteiro e perder as fotos reais junto. */}
        <label
          className={`flex items-center gap-2.5 w-full px-3 py-2 rounded-lg border transition cursor-pointer select-none ${
            duplicando
              ? 'bg-slate-800 border-slate-600 text-slate-500 cursor-wait'
              : autoDuplicateToFill
                ? 'bg-emerald-600/20 border-emerald-400/50 text-emerald-200 hover:bg-emerald-600/30'
                : 'bg-slate-800/80 border-slate-600 text-slate-300 hover:bg-slate-700/80'
          }`}
        >
          <input
            type="checkbox"
            checked={autoDuplicateToFill}
            disabled={duplicando}
            onChange={(e) => handleDuplicar(e.target.checked)}
            className="w-4 h-4 accent-emerald-500 cursor-pointer disabled:cursor-wait"
          />
          <span className="text-xs font-bold">
            {duplicando
              ? autoDuplicateToFill
                ? 'Removendo cópias...'
                : 'Ligando...'
              : 'Duplicar as fotos do mosaico (gradual)'}
          </span>
        </label>

        <label className="flex items-center justify-between gap-2 text-[10px] text-slate-400">
          <span title="Contado DEPOIS que o telão termina de exibir a cópia anterior, para as fotos não se atropelarem.">
            Respiro entre cópias
          </span>
          <div className="flex items-center gap-1.5 flex-1 max-w-[150px]">
            <input
              type="range"
              min={0.5}
              max={20}
              step={0.5}
              value={intervaloDup}
              onChange={(e) => setIntervaloDup(Number(e.target.value))}
              onMouseUp={() => aplicarIntervaloDup()}
              onTouchEnd={() => aplicarIntervaloDup()}
              className="flex-1 accent-emerald-500"
            />
            <span className="w-10 text-right font-mono text-emerald-300">{intervaloDup}s</span>
          </div>
        </label>

        {/* Fechar na hora, sem esperar o rodízio: serve para a foto oficial e
            para a gravação do vídeo, quando não dá para esperar. */}
        <button
          onClick={handlePreencherAgora}
          disabled={duplicando}
          className="w-full bg-slate-700/70 hover:bg-slate-600/70 disabled:bg-slate-800 disabled:text-slate-600 text-slate-200 font-semibold text-[11px] py-1.5 rounded-lg transition border border-slate-600 active:scale-95"
        >
          ⚡ Fechar o mosaico agora (sem animação)
        </button>

        {resultadoDuplicar && (
          <span className={`text-[10px] leading-snug ${resultadoDuplicar.erro ? 'text-rose-400' : 'text-emerald-400'}`}>
            {resultadoDuplicar.texto}
          </span>
        )}
      </div>

      {/* 6. Hot Folder Watcher Input */}
      <div className="flex flex-col gap-2 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
          <FolderOpen className="w-4 h-4 text-cyan-400" />
          <span>Hot Folder Watcher (Câmera)</span>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={hotFolderInput}
            readOnly
            className="flex-1 bg-slate-900 border border-slate-700 rounded p-1.5 text-xs font-mono text-slate-300 cursor-not-allowed"
            placeholder="Nenhuma pasta selecionada"
          />
          <button 
            onClick={handleSelectFolder}
            className="bg-slate-700 hover:bg-slate-600 px-3 rounded border border-slate-500 text-xs text-white font-medium transition"
          >
            Selecionar
          </button>
        </div>
        <span className="text-[10px] text-emerald-400 flex items-center gap-1">
          <span className="w-2 h-2 bg-emerald-500 rounded-full animate-ping" />
          Watcher Ativo (Monitorando diretório)
        </span>
        
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-slate-700/50">
          <input
            type="checkbox"
            id="autoPlaceMode"
            checked={useMosaicStore.getState().autoPlaceMode}
            onChange={(e) => {
              const val = e.target.checked;
              useMosaicStore.getState().setAutoPlaceMode(val);
              fetch('/api/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ autoPlaceMode: val })
              });
            }}
            className="w-4 h-4 accent-emerald-500 bg-slate-800 border-slate-600 rounded cursor-pointer"
          />
          <label htmlFor="autoPlaceMode" className="text-[11px] text-emerald-300 font-bold cursor-pointer">
            Auto-Preenchimento (Aprovar e Enviar para Tela 100% Automático)
          </label>
        </div>
      </div>

      {/* 7. Brand / Fallback Images */}
      <div className="flex flex-col gap-2 bg-slate-800/60 p-3 rounded-lg border border-slate-700/50">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
          <div className="flex items-center gap-1.5">
            <ImageIcon className="w-4 h-4 text-cyan-400" />
            <span>Imagens da Marca (Fallback)</span>
          </div>
          <span className="text-[10px] text-slate-500">{brandImages.length} prontas</span>
        </div>
        <label className="cursor-pointer bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs text-center py-2 rounded transition border border-dashed border-slate-500">
          + Upload Imagens Institucionais
          <input type="file" accept="image/*" onChange={handleBrandUpload} className="hidden" />
        </label>
        {brandImages.length > 0 && (
          <div className="grid grid-cols-4 gap-1.5 mt-2">
            {brandImages.map((url, i) => (
              <img key={i} src={url} alt="Brand" className="w-full h-10 object-cover rounded border border-slate-700" />
            ))}
          </div>
        )}
      </div>

      {/* 8. Fotos de Teste & Ingestão Rápida */}
      <div className="flex flex-col gap-3 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md mb-6">
        <div className="flex items-center justify-between text-xs font-bold text-cyan-300">
          <div className="flex items-center gap-1.5">
            <Upload className="w-4 h-4 text-cyan-400" />
            <span>Fotos de Teste (Galeria)</span>
          </div>
        </div>

        <p className="text-[10px] text-slate-400 leading-snug">
          Selecione fotos da sua galeria para testar o envio para a fila de moderação e a animação do telão. (Máximo de 5)
        </p>

        <label
          className={`cursor-pointer bg-gradient-to-r from-cyan-600 to-teal-600 hover:from-cyan-500 hover:to-teal-500 text-white font-bold text-xs py-2 rounded-lg transition shadow-md flex items-center justify-center gap-2 ${
            generatingPhotos ? 'opacity-50 pointer-events-none' : ''
          }`}
        >
          {generatingPhotos ? (
            <span className="animate-pulse">Enviando Fotos...</span>
          ) : (
            <>
              <span>⚡ Ingerir 5 Fotos de Teste</span>
              <input 
                type="file" 
                multiple 
                accept="image/*" 
                onChange={handleGalleryTestPhotos} 
                className="hidden" 
              />
            </>
          )}
        </label>
      </div>

      {/* 9. Exportação de Vídeo MP4 */}
      <div className="flex flex-col gap-2 bg-slate-800/80 p-3 rounded-lg border border-slate-700/80 shadow-md mb-6">
        <div className="flex items-center gap-1.5 text-xs font-bold text-cyan-300 border-b border-slate-700 pb-1 mb-1">
          <Monitor className="w-3.5 h-3.5" /> Exportação MP4 (Subdivisão)
        </div>
        
        {exportState === 'idle' && (
          <div className="flex flex-col gap-2">
            {/* Modelo aprovado pelo cliente: a foto surge colorida no centro,
                voa e pousa tingida na cor da marca, desenhando o logo. */}
            <button
              onClick={() =>
                handleExportVideo('/api/export/video-marca', {
                  largura: RESOLUCOES[videoRes].largura,
                  altura: RESOLUCOES[videoRes].altura,
                  fps: videoFps,
                  intervaloEntreFotos: videoIntervalo,
                  holdCentral: videoHold,
                  duracaoVoo: videoVoo,
                  corMarca: videoCor,
                })
              }
              className="w-full bg-red-600 hover:bg-red-500 text-white text-xs font-bold py-2 rounded-md transition-colors"
            >
              🎬 Exportar no Modelo da Marca
            </button>
            <span className="text-[10px] text-slate-500 leading-snug">
              Usa o overlay da Camada 4 e todas as fotos já recebidas — não precisa
              do mosaico montado na tela.
              {videoFotos !== null && duracaoEstimada && (
                <> {videoFotos} células · vídeo de ~<span className="text-cyan-300 font-mono">{duracaoEstimada}s</span>.</>
              )}
            </span>

            <button
              onClick={() => setVideoOpcoesAbertas((v) => !v)}
              className="text-[10px] text-slate-400 hover:text-cyan-300 text-left transition"
            >
              {videoOpcoesAbertas ? '▾' : '▸'} Ajustes do vídeo
            </button>

            {videoOpcoesAbertas && (
              <div className="flex flex-col gap-2.5 bg-slate-900/70 p-2.5 rounded border border-slate-700/60">
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-slate-400">Resolução</span>
                  <select
                    value={videoRes}
                    onChange={(e) => setVideoRes(parseInt(e.target.value, 10))}
                    className="bg-slate-900 border border-slate-700 rounded p-1 text-[11px] text-slate-200"
                  >
                    {RESOLUCOES.map((r, i) => (
                      <option key={r.rotulo} value={i}>{r.rotulo}</option>
                    ))}
                  </select>
                  <span className="text-[9px] text-slate-500">
                    Quanto maior, mais demora para gerar.
                  </span>
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-slate-400">Quadros por segundo</span>
                  <select
                    value={videoFps}
                    onChange={(e) => setVideoFps(parseInt(e.target.value, 10))}
                    className="bg-slate-900 border border-slate-700 rounded p-1 text-[11px] text-slate-200"
                  >
                    <option value={24}>24 fps (cinema)</option>
                    <option value={30}>30 fps (padrão)</option>
                    <option value={60}>60 fps (suave)</option>
                  </select>
                </label>

                {([
                  ['Intervalo entre fotos', videoIntervalo, setVideoIntervalo, 0.02, 1, 0.01],
                  ['Parada no centro', videoHold, setVideoHold, 0, 3, 0.1],
                  ['Duração do voo', videoVoo, setVideoVoo, 0.1, 2, 0.1],
                ] as const).map(([rotulo, valor, setter, min, max, step]) => (
                  <div key={rotulo} className="flex flex-col gap-1">
                    <div className="flex justify-between text-[10px] text-slate-400">
                      <span>{rotulo}</span>
                      <span className="font-mono text-cyan-300">{valor.toFixed(2)}s</span>
                    </div>
                    <input
                      type="range"
                      min={min}
                      max={max}
                      step={step}
                      value={valor}
                      onChange={(e) => setter(parseFloat(e.target.value))}
                      className="w-full h-1 bg-slate-700 rounded appearance-none cursor-pointer accent-cyan-400"
                    />
                  </div>
                ))}

                <label className="flex items-center justify-between gap-2">
                  <span className="text-[10px] text-slate-400">Cor da marca</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[10px] text-slate-400">{videoCor}</span>
                    <input
                      type="color"
                      value={videoCor}
                      onChange={(e) => setVideoCor(e.target.value)}
                      className="w-8 h-6 bg-transparent border border-slate-700 rounded cursor-pointer"
                    />
                  </div>
                </label>
                <span className="text-[9px] text-slate-500 leading-snug">
                  As fotos pousadas são tingidas nessa cor para desenhar o logo.
                </span>

                <button
                  onClick={() => {
                    setVideoRes(0); setVideoFps(30); setVideoIntervalo(0.12);
                    setVideoHold(0.5); setVideoVoo(0.6); setVideoCor('#e21c1c');
                  }}
                  className="text-[10px] text-slate-500 hover:text-cyan-300 transition"
                >
                  Restaurar valores aprovados
                </button>
              </div>
            )}

            <button
              onClick={() => handleExportVideo('/api/export/video')}
              className="w-full bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-semibold py-2 rounded-md transition-colors"
            >
              Exportar Mosaico Atual (Subdivisão)
            </button>
          </div>
        )}
        
        {exportState === 'exporting' && (
          <div className="flex flex-col gap-1">
            <div className="flex justify-between text-[10px] text-cyan-200">
              <span>Gerando frames...</span>
              <span>{exportProgress}%</span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-1.5">
              <div 
                className="bg-cyan-400 h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${exportProgress}%` }}
              ></div>
            </div>
          </div>
        )}
        
        {exportState === 'completed' && (
          <div className="flex flex-col gap-2">
            <p className="text-[10px] text-emerald-400 text-center">Exportação Concluída!</p>
            <a 
              href={`/api/export/video/download/${exportId}`}
              download
              className="block w-full text-center bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold py-2 rounded-md transition-colors"
            >
              ⬇️ Baixar MP4
            </a>
            <button 
              onClick={() => setExportState('idle')}
              className="text-[10px] text-slate-400 hover:text-white"
            >
              Exportar novamente
            </button>
          </div>
        )}
        
        {exportState === 'error' && (
          <div className="flex flex-col gap-2">
            <p className="text-[10px] text-red-400">Erro: {exportError}</p>
            <button 
              onClick={() => setExportState('idle')}
              className="w-full bg-slate-700 hover:bg-slate-600 text-white text-[10px] py-1 rounded-md"
            >
              Tentar Novamente
            </button>
          </div>
        )}
      </div>

      {/* Zona de risco: fica no FIM do painel, longe dos controles do evento. */}
      <div className="flex flex-col gap-2 bg-rose-950/30 p-3 rounded-lg border border-rose-900/60">
        <div className="flex items-center gap-1.5 text-xs font-bold text-rose-300">
          <Trash2 className="w-4 h-4 text-rose-400" />
          <span>Limpeza Geral</span>
        </div>

        <p className="text-[10px] text-slate-400 leading-snug">
          Zera o evento: mosaico, fila, ladrilhos, hot folder e a galeria.
          <strong className="text-slate-300"> Não mexe</strong> na configuração
          nem nos arquivos da marca — overlay, imagem-base, encaixe da grade e
          vídeos exportados ficam.
        </p>

        <label className="flex items-center gap-2 text-[10px] text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={limparBucket}
            onChange={(e) => setLimparBucket(e.target.checked)}
            disabled={limpando}
            className="w-3.5 h-3.5 accent-rose-500 cursor-pointer"
          />
          <span>
            Esvaziar também o bucket S3
            <span className="text-rose-400/80"> (não tem volta)</span>
          </span>
        </label>

        <button
          onClick={handleLimpezaGeral}
          disabled={limpando}
          className={`w-full font-bold text-xs py-2 rounded-lg transition border active:scale-95 ${
            limpando
              ? 'bg-slate-800 text-slate-500 border-slate-700'
              : confirmandoLimpeza
                ? 'bg-rose-500 hover:bg-rose-400 text-white border-rose-300'
                : 'bg-rose-900/60 hover:bg-rose-800/70 text-rose-200 border-rose-700'
          }`}
        >
          {limpando
            ? 'Limpando...'
            : confirmandoLimpeza
              ? 'Confirmar — apagar tudo agora'
              : '🗑 Limpeza geral'}
        </button>

        {confirmandoLimpeza && !limpando && (
          <span className="text-[10px] text-amber-400">
            Clique de novo para confirmar. A confirmação expira em 5s.
          </span>
        )}

        {resultadoLimpeza && (
          <span className={`text-[10px] leading-snug ${resultadoLimpeza.erro ? 'text-rose-400' : 'text-emerald-400'}`}>
            {resultadoLimpeza.texto}
          </span>
        )}
      </div>

    </div>
  );
};
