import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Portas configuráveis para conviver com outros projetos na mesma máquina.
// Sem variáveis definidas, o comportamento é o padrão: front 3000, backend 8000.
const frontPort = Number(process.env.MOSAICO_FRONT_PORT ?? 3000);
const backPort = Number(process.env.MOSAICO_BACK_PORT ?? 8000);
const backHttp = `http://127.0.0.1:${backPort}`;
const backWs = `ws://127.0.0.1:${backPort}`;

export default defineConfig({
  plugins: [react()],
  server: {
    port: frontPort,
    proxy: {
      '/api': {
        target: backHttp,
        changeOrigin: true,
      },
      '/ws': {
        target: backWs,
        ws: true,
      },
      '/storage': {
        target: backHttp,
        changeOrigin: true,
      },
    },
  },
});
