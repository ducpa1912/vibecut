import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Pages serves the static build; `/api` is the Worker. In dev, Vite proxies to
// `wrangler dev` so the SPA always talks to the API on its own origin.
const API_ORIGIN = process.env.DUCKCLEAN_API_ORIGIN ?? 'http://127.0.0.1:8787';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: API_ORIGIN, changeOrigin: false },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
