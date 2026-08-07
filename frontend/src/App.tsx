import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { PixiViewport } from './components/Canvas/PixiViewport';
import { IngestionPanel } from './components/Sidebar/IngestionPanel';
import { ModerationQueue } from './components/Sidebar/ModerationQueue';
import { LayerStack } from './components/Sidebar/LayerStack';
import { AnimationStudio } from './components/Sidebar/AnimationStudio';
import { FilterEditorPanel } from './components/Sidebar/FilterEditorPanel';
import { ExportTools } from './components/Sidebar/ExportTools';
import { TransportBar } from './components/TransportBar';
import { Monitor, Clock, Layers, Sparkles, Palette, Printer, Radio } from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'ingestion' | 'moderation' | 'layers' | 'animation' | 'filters' | 'export'>('moderation');

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-950 font-sans text-slate-100 antialiased">
      {/* Barra de Transporte: aplica config e comanda o telão */}
      <TransportBar />

      <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* Mini Bar de Navegação da Sidebar */}
      <div className="flex flex-col bg-slate-950 border-r border-slate-800 p-2 gap-3 z-20">
        <button
          onClick={() => setActiveTab('ingestion')}
          className={`p-2.5 rounded-lg transition ${
            activeTab === 'ingestion' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' : 'text-slate-500 hover:text-slate-300'
          }`}
          title="Display & Ingestão"
        >
          <Monitor className="w-5 h-5" />
        </button>

        <button
          onClick={() => setActiveTab('moderation')}
          className={`p-2.5 rounded-lg transition relative ${
            activeTab === 'moderation' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' : 'text-slate-500 hover:text-slate-300'
          }`}
          title="Fila de Moderação"
        >
          <Clock className="w-5 h-5" />
        </button>

        <button
          onClick={() => setActiveTab('layers')}
          className={`p-2.5 rounded-lg transition ${
            activeTab === 'layers' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' : 'text-slate-500 hover:text-slate-300'
          }`}
          title="Sistema de Camadas"
        >
          <Layers className="w-5 h-5" />
        </button>

        <button
          onClick={() => setActiveTab('animation')}
          className={`p-2.5 rounded-lg transition ${
            activeTab === 'animation' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' : 'text-slate-500 hover:text-slate-300'
          }`}
          title="Estúdio de Animações"
        >
          <Sparkles className="w-5 h-5" />
        </button>

        <button
          onClick={() => setActiveTab('filters')}
          className={`p-2.5 rounded-lg transition ${
            activeTab === 'filters' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-500 hover:text-slate-300'
          }`}
          title="Filtros & Pintura de Áreas"
        >
          <Palette className="w-5 h-5" />
        </button>

        <button
          onClick={() => setActiveTab('export')}
          className={`p-2.5 rounded-lg transition ${
            activeTab === 'export' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' : 'text-slate-500 hover:text-slate-300'
          }`}
          title="Exportação & Impressão"
        >
          <Printer className="w-5 h-5" />
        </button>

        {/* Separador */}
        <div className="w-full h-px bg-slate-800 my-1" />

        {/* Botão AO VIVO */}
        <Link
          to="/mosaicoaovivo"
          className="flex flex-col items-center gap-1 p-2 rounded-lg bg-red-600/20 hover:bg-red-600/40 border border-red-500/40 hover:border-red-400/70 text-red-400 hover:text-red-300 transition group"
          title="Abrir Mosaico Ao Vivo (Fullscreen)"
        >
          <Radio className="w-5 h-5 group-hover:animate-pulse" />
          <span className="text-[9px] font-black tracking-wider leading-tight text-center">
            AO<br/>VIVO
          </span>
          <span className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse" />
        </Link>
      </div>

      {/* Conteúdo Dinâmico da Sidebar (Zona 1) */}
      <div className="flex-none z-10 shadow-2xl">
        {activeTab === 'ingestion' && <IngestionPanel />}
        {activeTab === 'moderation' && <ModerationQueue />}
        {activeTab === 'layers' && <LayerStack />}
        {activeTab === 'animation' && <AnimationStudio />}
        {activeTab === 'filters' && <FilterEditorPanel />}
        {activeTab === 'export' && <ExportTools />}
      </div>

      {/* Area Principal Canvas (Zona 2) */}
      <div className="flex-1 relative h-full">
        <PixiViewport />
      </div>
      </div>
    </div>
  );
};

export default App;
