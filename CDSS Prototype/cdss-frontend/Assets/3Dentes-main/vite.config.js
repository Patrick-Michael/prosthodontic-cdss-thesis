import { defineConfig } from 'vite';
import pkg from './package.json' with { type: 'json' };
import { VitePWA } from 'vite-plugin-pwa';

// GitHub Pages serves this from https://natesaindon.github.io/3Dentes/, so every
// asset URL needs that prefix. Code reads it back via import.meta.env.BASE_URL.
const BASE = '/3Dentes/';

export default defineConfig({
  // The version shown in the corner comes from package.json, so it cannot
  // drift from the changelog: both move in the same commit.
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  base: BASE,
  // Two pages: the atlas, and the radiograph harness from Phase 3 of
  // docs/drr-plan.md. Listing drr.html explicitly is what gets it into the
  // production build -- vite only walks index.html otherwise, and the page
  // would work in dev and silently vanish from the deploy.
  build: {
    target: 'es2022',
    assetsDir: 'assets',
    rollupOptions: { input: { main: 'index.html', drr: 'drr.html' } },
  },
  plugins: [
    VitePWA({
      registerType: 'autoUpdate',
      // OFF: src/sw-update.js does the registration. The injected one-liner
      // registers and then ignores the update it downloads, so a push only
      // became visible on the visit AFTER the one that fetched it.
      injectRegister: false,
      includeAssets: ['dentition.glb', 'teeth.json', 'trabecular.bin'],
      workbox: {
        // Take over the open page as soon as the new worker is ready; the
        // reload in src/sw-update.js is what makes that visible.
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        // `bin` IS LOAD-BEARING and was missed on the first pass: adding
        // trabecular.bin to public/ took 19 precache entries but only 0.77 KiB,
        // because the pattern had no extension that matched 4 MB of measured
        // bone. The build reported success and the app would have failed
        // offline, which is the one thing the precache exists to prevent.
        globPatterns: ['**/*.{js,css,html,glb,json,svg,png,bin}'],
        // Workbox drops anything over 2MB from the precache, which would break
        // offline use — the whole point of installing this to a home screen.
        //
        // THIS CAP HAS TO LEAD THE MESH, and it has twice failed to. The
        // comment here said "~6MB" while the file was 12.3; 0.6.0 took it to
        // 13.7 and the deploy failed on the 12 MiB limit AFTER the push, which
        // is the worst place to find out. The mesh grows about 1.4 MB a release
        // as anatomy lands, so this is set well ahead of it rather than to the
        // current size. `npm run build` catches a breach locally — run it
        // before pushing a release, not just `build:assets`.
        maximumFileSizeToCacheInBytes: 32 * 1024 * 1024,
      },
      manifest: {
        name: '3Dentes — Interactive Oral Anatomy',
        short_name: '3Dentes',
        description: 'Interactive 3D atlas of human oral anatomy, segmented from '
          + 'one cone-beam CT — and it takes its own radiograph.',
        theme_color: '#14161a',
        background_color: '#14161a',
        display: 'standalone',
        orientation: 'any',
        start_url: BASE,
        scope: BASE,
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
});
