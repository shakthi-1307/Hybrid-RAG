import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Mirrors the nginx /api proxy used in the container image, so `npm run dev`
// and the built image behave identically and neither needs CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
