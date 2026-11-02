// FamilyOS web UI (WEB_UI_PLAN.md). A static SPA: `npm run build` writes
// dist/, which any static host (or a FastAPI StaticFiles mount, see
// WEB_UI_REPORT.md) can serve. Set FAMILYOS_WEB_BASE when it is served
// under a sub-path, e.g. FAMILYOS_WEB_BASE=/web/ npm run build.
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: process.env.FAMILYOS_WEB_BASE ?? '/',
  plugins: [react()],
  // `VITE_FAMILYOS_API=on npm run dev` talks to the backend through this proxy, on the page's own origin as when the
  // backend serves the build (the session cookie and its CSRF check need that). FAMILYOS_API_PROXY points elsewhere.
  server: { port: 5175, host: true, proxy: { '/v1': process.env.FAMILYOS_API_PROXY ?? 'http://localhost:8000' } },
  preview: { port: 4175, host: true },
  build: { target: 'es2022', chunkSizeWarningLimit: 700 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
