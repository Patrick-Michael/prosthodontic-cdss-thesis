// Make an already-installed copy of the atlas update itself on the next visit.
//
// THE PROBLEM THIS SOLVES. vite-plugin-pwa's injected registration is one line:
// it calls navigator.serviceWorker.register() and stops. On a repeat visit the
// OLD service worker serves the old precached app and the page renders it;
// only afterwards does the new worker install, activate and claim the page —
// and nothing reloads it. So a push is never visible on the visit that fetches
// it, and is visible on the NEXT one. That is not a bug in the cache, it is the
// registration doing nothing about the update it just downloaded.
//
// Two changes fix it:
//
//   updateViaCache: 'none'  GitHub Pages serves sw.js with max-age=600, so for
//                           ten minutes after a push the browser could satisfy
//                           its update check from the HTTP cache and conclude
//                           nothing had changed. This forces revalidation.
//
//   controllerchange        When the new worker takes control, reload once, so
//                           the update lands on the visit that fetched it.
//
// WRITTEN BY HAND rather than imported from `virtual:pwa-register`, because the
// behaviour is six lines and this way there is exactly one registration path in
// the app that a reader can follow. `injectRegister` is off in vite.config.js.
//
// THE TRADE, stated: the precache is what makes this work offline and start
// instantly, so a visit that finds an update still paints the old app for the
// moment it takes to install, then reloads. Fetching the HTML from the network
// first would remove that flicker and cost a round trip on every launch — the
// wrong way round for something meant to work on a phone in a clinic.

export function registerServiceWorker(base) {
  if (!('serviceWorker' in navigator)) return;
  if (!window.isSecureContext) return;       // no SW on plain http, incl. LAN dev

  window.addEventListener('load', async () => {
    let reg;
    try {
      reg = await navigator.serviceWorker.register(`${base}sw.js`, {
        scope: base,
        updateViaCache: 'none',
      });
    } catch {
      return;                                 // an atlas that loads is enough
    }

    // Reload when a NEW worker takes over — but not on the first install, where
    // there was no controller and nothing stale on screen to replace. Guarded
    // against firing twice, because a reload loop would be far worse than a
    // stale page.
    const hadController = !!navigator.serviceWorker.controller;
    let reloading = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!hadController || reloading) return;
      reloading = true;
      window.location.reload();
    });

    // Installed to a home screen, the atlas can stay open for days and never
    // navigate. Check again whenever it comes back to the foreground.
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') reg.update().catch(() => {});
    });
  });
}
