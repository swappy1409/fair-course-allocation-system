import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// `npm run dev` proxies API calls to the backend on :8000; production is served by FastAPI itself.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
